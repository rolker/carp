"""One ping, start to finish: build the output, record, and pick out arrivals.

A ping is described by a Design:
  signals   a named list of chirps (start and end frequency, length, level)
  events    which signal goes out on which output channel, and when

So the same chirp can fire on the left and then the right, a channel can
repeat a signal or chain several, and different signals can overlap.

All events of a ping go out in one output buffer, so their spacing is exact
to the sample. What is not known is when the buffer starts relative to the
recording: one unknown offset per ping. analyse() finds it from the
recording itself, using the spacing of the events.

No GUI code here, and audio hardware is only touched in record(), so
everything else runs on saved or simulated recordings.

Found 2026-10-11, TV speakers to a laptop mic through WSL:
- An up-chirp and a down-chirp sent at the same instant leaked into each
  other's filter only 10 dB down, so they could not be told apart.
- Separate bands at the same instant (2-9 kHz and 11-20 kHz) separated
  cleanly: the other channel's leak was 39 dB down or not detected.
- The WSL sound bridge does not keep the spacing between events: the same
  chirp sent three times on one channel came back 5 to 25 ms late, in steps
  of about 5 ms. So on WSL only events sent at the same instant can be
  compared in time. A real sound card should not do this - check it with
  designs/timing-check.json.
"""
from dataclasses import asdict, dataclass, field
import json

import numpy as np

import ranging_dsp as dsp

CHANNELS = ("left", "right")
SETTLE = 0.15       # dropped from the start of a live recording, s
LEAD_IN = 0.4       # silence before the first event, s
SEARCH = 0.03       # how far either side of its expected time an event is looked for, s
DETECT = 8.0        # an arrival must be this many times the typical noise level


@dataclass
class Signal:
    name: str
    f0: float = 2000.0          # start frequency, Hz
    f1: float = 20000.0         # end frequency, Hz (below f0 for a down-chirp)
    duration: float = 0.02      # s
    amplitude: float = 0.5      # 0 to 1

    def samples(self, rate):
        return dsp.make_chirp(rate, self.f0, self.f1, self.duration)


@dataclass
class Event:
    channel: str                # "left" or "right"
    signal: str                 # a Signal's name
    time: float = 0.0           # seconds after the start of the ping


@dataclass
class Design:
    signals: list = field(default_factory=list)
    events: list = field(default_factory=list)

    def signal(self, name):
        for s in self.signals:
            if s.name == name:
                return s
        raise ValueError(f"no signal named {name!r}")

    def check(self, rate):
        """Raise ValueError if the design cannot be played at this rate."""
        if not self.events:
            raise ValueError("the ping design has no events")
        for e in self.events:
            if e.channel not in CHANNELS:
                raise ValueError(f"unknown channel {e.channel!r}")
            if e.time < 0:
                raise ValueError("event times cannot be negative")
            s = self.signal(e.signal)
            if s.duration <= 0:
                raise ValueError(f"{s.name}: length must be above zero")
            s.samples(rate)     # rejects a band too high for the rate

    def inseparable(self):
        """Groups of events that share a signal and fire within the search
        window of each other. Their sounds add together, so the analysis
        sees one arrival and reports it for each of them."""
        groups = []
        for i, a in enumerate(self.events):
            if any(i in g for g in groups):
                continue
            group = [j for j, b in enumerate(self.events)
                     if b.signal == a.signal and abs(b.time - a.time) < 2 * SEARCH]
            if len(group) > 1:
                groups.append(group)
        return groups

    def leaking(self, rate, worse_than_db=-25.0):
        """Pairs of events with different signals that overlap in time and
        are poorly separated by their filters.

        Returns (i, j, isolation_db): how far below its own peak signal j
        shows up in signal i's filter. Separate bands give -40 dB or
        better; an up-chirp against a down-chirp over the same band gives
        only about -10 to -20 dB, and the leak is smeared over the length
        of the chirp, so it lands at the wrong time.
        """
        pairs = []
        for i, a in enumerate(self.events):
            for j, b in enumerate(self.events):
                if j <= i or a.signal == b.signal:
                    continue
                sa, sb = self.signal(a.signal), self.signal(b.signal)
                if abs(a.time - b.time) > max(sa.duration, sb.duration) + SEARCH:
                    continue
                xa, xb = sa.samples(rate), sb.samples(rate)
                pad = np.zeros(max(xa.size, xb.size))
                cross = dsp.matched_filter(np.concatenate([pad, xb, pad]), xa).max()
                own = dsp.matched_filter(np.concatenate([pad, xa, pad]), xa).max()
                isolation = 20 * np.log10(max(cross, 1e-12) / own)
                if isolation > worse_than_db:
                    pairs.append((i, j, float(isolation)))
        return pairs

    def to_json(self):
        return json.dumps(asdict(self), indent=1)

    @staticmethod
    def from_dict(data):
        return Design(signals=[Signal(**s) for s in data["signals"]],
                      events=[Event(**e) for e in data["events"]])

    def label(self, index):
        e = self.events[index]
        return f"{index + 1}: {e.channel} {e.signal} @ {e.time * 1e3:g} ms"


def default_design():
    """The same chirp on the left, then on the right 150 ms later."""
    return Design(
        signals=[Signal("chirp up", 2000.0, 20000.0),
                 Signal("chirp down", 20000.0, 2000.0)],
        events=[Event("left", "chirp up", 0.0),
                Event("right", "chirp up", 0.15)])


@dataclass
class Setup:
    """How a ping is played and analysed, apart from its design."""
    rate: int = 48000
    listen: float = 0.3             # recording time after the last event, s
    first_threshold: float = 0.3    # first arrival: fraction of the event's peak
    sound_speed: float = float(dsp.sound_speed_air())
    input_device: int = None
    output_device: int = None


@dataclass
class EventResult:
    first: float        # sample of the first arrival in the recording
    level: float        # height of the event's strongest peak
    snr: float          # strongest peak over the typical noise level


@dataclass
class PingResult:
    design: Design
    setup: Setup
    recording: np.ndarray
    envelopes: dict = field(default_factory=dict)   # signal name -> envelope
    events: list = field(default_factory=list)      # EventResult or None, per event
    warnings: list = field(default_factory=list)

    def detected(self):
        return [i for i, e in enumerate(self.events) if e is not None]

    def _sent(self, index):
        return int(round(self.design.events[index].time * self.setup.rate))

    @property
    def reference(self):
        """Time zero for display, as a sample in the recording: the loudest
        event's first arrival, moved back to the start of the ping."""
        found = self.detected()
        if not found:
            return None
        loudest = max(found, key=lambda i: self.events[i].level)
        return self.events[loudest].first - self._sent(loudest)

    def top(self):
        return max(self.events[i].level for i in self.detected())

    def delay_ms(self, index):
        """An event's first arrival in ms after the reference, with the
        event's own sending time taken out."""
        first = self.events[index].first - self._sent(index)
        return (first - self.reference) / self.setup.rate * 1e3

    def trace_db(self, index, before_ms, span_ms, floor_db):
        """An event's matched-filter output around when it was due, in dB
        below the ping's strongest peak. Works for an undetected event."""
        rate = self.setup.rate
        envelope = self.envelopes[self.design.events[index].signal]
        start = (int(round(self.reference)) + self._sent(index)
                 - int(before_ms / 1e3 * rate))
        count = int((before_ms + span_ms) / 1e3 * rate)
        out = np.full(count, float(floor_db))
        lo, hi = max(start, 0), min(start + count, envelope.size)
        if hi > lo:
            db = 20 * np.log10(np.maximum(envelope[lo:hi], 1e-12) / self.top())
            out[lo - start:hi - start] = np.maximum(db, floor_db)
        return out


def build_playback(design, setup):
    """Stereo output for one ping, float32, shape (samples, 2)."""
    rate = setup.rate
    lead = int(LEAD_IN * rate)
    placed = []
    for e in design.events:
        s = design.signal(e.signal)
        start = lead + int(round(e.time * rate))
        placed.append((CHANNELS.index(e.channel), start,
                       s.amplitude * s.samples(rate)))
    total = max(start + x.size for _, start, x in placed) + int(setup.listen * rate)
    playback = np.zeros((total, 2), dtype=np.float32)
    for column, start, x in placed:
        playback[start:start + x.size, column] += x
    return playback


def record(design, setup):
    """Send one ping through the sound card. Returns (recording, warnings)."""
    import audio_io
    playback = build_playback(design, setup)
    warnings = []
    if np.max(np.abs(playback)) > 1.0:
        warnings.append("overlapping signals exceed full level and were clipped")
    recording, more = audio_io.play_and_record(
        playback, setup.rate, setup.input_device, setup.output_device)
    return recording[int(SETTLE * setup.rate):], warnings + more


def simulate(design, setup, index=0):
    """A made-up recording: each channel is heard directly and by one
    reflection, the right one further away and drifting from ping to ping."""
    rate, speed = setup.rate, setup.sound_speed
    paths = {"left": [(1.5, 0.1), (2.6, 0.03)],
             "right": [(1.9 + 0.01 * index, 0.06), (3.3, 0.024)]}
    rng = np.random.default_rng(index)
    last = max(e.time + design.signal(e.signal).duration for e in design.events)
    total = int((LEAD_IN - SETTLE + last + 0.02 + setup.listen) * rate)
    recording = rng.normal(0.0, 0.002, total)
    freqs = np.fft.rfftfreq(total, 1.0 / rate)
    for e in design.events:
        s = design.signal(e.signal)
        spectrum = np.fft.rfft(s.amplitude * s.samples(rate), total)
        for metres, gain in paths[e.channel]:
            delay = LEAD_IN - SETTLE + e.time + metres / speed
            recording += gain * np.fft.irfft(
                spectrum * np.exp(-2j * np.pi * freqs * delay), total)
    return recording.astype(np.float32)


def _window_peak(envelope, centre, half):
    lo, hi = max(centre - half, 0), min(centre + half, envelope.size)
    return float(envelope[lo:hi].max()) if hi - lo > 0 else 0.0


def analyse(recording, design, setup, warnings=()):
    """Find each event's first arrival in a recording."""
    rate = setup.rate
    result = PingResult(design=design, setup=setup, recording=recording,
                        events=[None] * len(design.events),
                        warnings=list(warnings))
    longest = max(design.signal(e.signal).samples(rate).size
                  for e in design.events)
    if recording.size < longest + 16:
        result.warnings.append("recording too short")
        return result
    if np.max(np.abs(recording)) < 10 ** (-70 / 20):
        result.warnings.append("recording is silent")
        return result

    noise = {}
    for name in {e.signal for e in design.events}:
        envelope = dsp.matched_filter(recording, design.signal(name).samples(rate))
        result.envelopes[name] = envelope
        noise[name] = float(np.median(envelope)) or 1e-12
    sent = [int(round(e.time * rate)) for e in design.events]
    half = int(SEARCH * rate)

    # Anchor on the clearest peak of any signal. It belongs to one of the
    # events that use that signal; each choice puts the start of the ping
    # somewhere different. Keep the choice under which the other events
    # turn up where they should.
    anchor = max(result.envelopes, key=lambda n: result.envelopes[n].max() / noise[n])
    peak = int(np.argmax(result.envelopes[anchor]))
    if result.envelopes[anchor][peak] < DETECT * noise[anchor]:
        result.warnings.append("nothing stands out from the noise")
        return result
    best_start, best_score = None, -1.0
    for k, e in enumerate(design.events):
        if e.signal != anchor:
            continue
        start = peak - sent[k]
        score = 0.0
        for j, other in enumerate(design.events):
            if j == k:
                continue
            strength = (_window_peak(result.envelopes[other.signal],
                                     start + sent[j], half) / noise[other.signal])
            if strength >= DETECT:
                score += strength
        if score > best_score:
            best_start, best_score = start, score

    for j, e in enumerate(design.events):
        envelope = result.envelopes[e.signal]
        centre = best_start + sent[j]
        lo, hi = max(centre - half, 0), min(centre + half, envelope.size)
        if hi - lo < 16 or envelope[lo:hi].max() < DETECT * noise[e.signal]:
            continue
        window = envelope[lo:hi]
        arrivals = dsp.find_arrivals(window, rate, setup.first_threshold)
        if arrivals:
            result.events[j] = EventResult(
                first=arrivals[0].sample + lo, level=float(window.max()),
                snr=float(window.max() / noise[e.signal]))

    for group in design.inseparable():
        result.warnings.append(
            "events " + " and ".join(str(i + 1) for i in group)
            + " use the same signal at nearly the same time: they are one "
              "combined sound and cannot be told apart")
    for i, j, isolation in design.leaking(rate):
        result.warnings.append(
            f"events {i + 1} and {j + 1} overlap in time and band: each leaks "
            f"into the other's filter only {-isolation:.0f} dB down, smeared "
            f"in time, so the weaker one's arrival is not reliable")
    missing = len(design.events) - len(result.detected())
    if missing and len(result.detected()) == 1 and len(design.events) > 1:
        result.warnings.append(
            "only one event was heard, so which one it is may be wrong")
    elif missing:
        result.warnings.append(f"{missing} event(s) not heard")
    return result


def rows(result):
    """Per-event results as dicts, for a table or a log."""
    out = []
    for i, e in enumerate(result.design.events):
        row = dict(number=i + 1, channel=e.channel, signal=e.signal,
                   sent_ms=e.time * 1e3, heard=result.events[i] is not None,
                   combined_with=[j + 1 for g in result.design.inseparable()
                                  if i in g for j in g if j != i])
        if row["heard"]:
            delay = result.delay_ms(i)
            row.update(delay_ms=delay,
                       path_m=delay * result.setup.sound_speed / 1e3,
                       level_db=20 * np.log10(result.events[i].level / result.top()),
                       snr=result.events[i].snr)
        out.append(row)
    return out


def describe(result):
    """One line summing up a ping, for a status bar or a log."""
    if not result.detected():
        return "No ping detected: " + "; ".join(result.warnings)
    parts = []
    for row in rows(result):
        if row["heard"]:
            parts.append(f"{row['number']} {row['channel']}: "
                         f"{row['delay_ms']:+.3f} ms, {row['level_db']:+.1f} dB")
        else:
            parts.append(f"{row['number']} {row['channel']}: not heard")
    return "   |   ".join(parts + result.warnings)


# ---- frequency sweep ---------------------------------------------------
#
# Which band does a given speaker, room and microphone pass best? Send a run
# of short, narrow chirps that step up through the range, and see how
# strongly each comes back. Each chirp is found by its own filter, without
# using the spacing between them, so this also works where the sound path
# does not keep time (the WSL bridge).

SWEEP_GAP = 0.06        # between the starts of successive bands, s


def sweep_design(f_start, f_end, step=1000.0, channel="left", amplitude=0.1,
                 duration=0.03):
    """A ping design that steps one channel through f_start..f_end in
    bands `step` Hz wide."""
    if channel not in CHANNELS:
        raise ValueError(f"unknown channel {channel!r}")
    if step <= 0 or f_start <= 0 or f_end - f_start < step:
        raise ValueError("the sweep needs a range at least one step wide")
    design = Design()
    count = int((f_end - f_start) / step + 1e-9)
    for i in range(count):
        lo = f_start + i * step
        name = f"{lo / 1e3:g}-{(lo + step) / 1e3:g} kHz"
        design.signals.append(Signal(name, lo, lo + step, duration, amplitude))
        design.events.append(Event(channel, name, i * SWEEP_GAP))
    return design


def analyse_sweep(recording, design, setup):
    """How strongly each band of a sweep_design came back.

    Returns one dict per band: f0, f1, peak (matched-filter height, the same
    scale for every band), snr (peak over that filter's typical output) and
    heard.
    """
    quiet = (recording.size == 0
             or np.max(np.abs(recording)) < 10 ** (-70 / 20))
    bands = []
    for s in design.signals:
        chirp = s.samples(setup.rate)
        peak, snr = 0.0, 0.0
        if not quiet and recording.size > chirp.size + 16:
            envelope = dsp.matched_filter(recording, chirp)
            peak = float(envelope.max())
            snr = peak / (float(np.median(envelope)) or 1e-12)
        bands.append(dict(f0=s.f0, f1=s.f1, peak=peak, snr=snr,
                          heard=snr >= DETECT))
    return bands


def average_sweeps(runs):
    """Combine repeats of the same sweep: mean power per band."""
    out = []
    for group in zip(*runs):
        peak = float(np.sqrt(np.mean([b["peak"] ** 2 for b in group])))
        snr = float(np.sqrt(np.mean([b["snr"] ** 2 for b in group])))
        out.append(dict(group[0], peak=peak, snr=snr, heard=snr >= DETECT))
    return out


def suggest_band(channels, within_db=10.0):
    """The widest unbroken run of bands that every channel passes well.

    channels maps a name to its list of bands. A band counts if it was heard
    on every channel and is within `within_db` of that channel's best band.
    Returns (f0, f1) in Hz, or None.
    """
    runs = list(channels.values())
    if not runs or not runs[0]:
        return None
    good = []
    for group in zip(*runs):
        ok = True
        for bands, band in zip(runs, group):
            best = max(b["peak"] for b in bands)
            ok &= band["heard"] and best > 0 and (
                20 * np.log10(band["peak"] / best) >= -within_db)
        good.append(ok)
    best_run, start = None, None
    for i, ok in enumerate(good + [False]):
        if ok and start is None:
            start = i
        elif not ok and start is not None:
            if best_run is None or i - start > best_run[1] - best_run[0]:
                best_run = (start, i)
            start = None
    if best_run is None:
        return None
    first = runs[0]
    return first[best_run[0]]["f0"], first[best_run[1] - 1]["f1"]


def simulate_sweep(design, setup, index=0, passband=(4500.0, 13000.0)):
    """A made-up sweep recording from a system that only passes `passband`."""
    from scipy import signal
    clean = simulate(design, setup, index)
    sos = signal.butter(4, passband, btype="band", fs=setup.rate, output="sos")
    noise = np.random.default_rng(index + 1000).normal(0.0, 0.002, clean.size)
    return (signal.sosfilt(sos, clean) + noise).astype(np.float32)
