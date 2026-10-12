"""Matched filter, arrivals, and finding where each transmission of a ping
turned up in a recording.

No audio, no Qt, no workspace: arrays and numbers in, numbers out, so it
runs the same on a live recording, a WAV file or a simulated one. Ported
from carp/acoustic ranging_dsp.py and pinger.py; see docs/navigation.md,
Method 4, for what it is used for.

Found 2026-10-11, TV speakers to a laptop mic through WSL:
- An up-chirp and a down-chirp sent at the same instant leaked into each
  other's filter only 10 dB down, so they could not be told apart.
- Separate bands at the same instant (2-9 kHz and 11-20 kHz) separated
  cleanly: the other signal's leak was 39 dB down or not detected.
"""
from dataclasses import dataclass, field

import numpy as np
from scipy import signal

from .detection_design import DEFAULT, DetectionDesign

QUANTISATION = 1.0 / np.sqrt(12.0)   # rms of int16 rounding, in steps
INT16_STEP = 1.0 / 32768.0           # one int16 step in full-scale units

# The defaults of the detection design, under their old names.
SEARCH = DEFAULT.search_s       # how far either side of its expected time an event is looked for, s
DETECT = DEFAULT.detect_snr     # an arrival must be this many times the typical noise level


def smoothed_envelope(data, length):
    """Energy envelope of a signal without a template: the analytic signal's
    power averaged over `length` samples, as a root, scaled so that a steady
    sine of amplitude A reads A. Index i covers samples i..i+length-1, like
    a template starting at i. Returns (the analytic signal's smoothed
    envelope, the same) for use where a matched filter's pair is wanted."""
    power = np.abs(signal.hilbert(data)) ** 2
    mean = signal.correlate(power, np.ones(length) / length, mode="valid",
                            method="fft")
    return np.sqrt(2.0 * np.maximum(mean, 0.0))


def correlation(window, template, method="matched"):
    """Matched-filter output of `window` against `template`, or with
    method="envelope" the template-free energy envelope over its length.

    Index i is the template starting at sample i of the window. The mean is
    removed first (mic bias). Returns (analytic array, envelope array); for
    the envelope method both are the envelope.
    """
    data = np.asarray(window, dtype=np.float64)
    data = data - data.mean()
    if method == "envelope":
        env = smoothed_envelope(data, len(template))
        return env, env
    c = signal.correlate(data, template, mode="valid", method="fft")
    analytic = signal.hilbert(c)
    return analytic, np.abs(analytic)


def matched_filter(recording, template, method="matched"):
    """Envelope of the recording correlated against the template.

    Index i of the result is the template starting at sample i of the
    recording. The template is normally peak 1.0, so the envelope height is
    in the recording's own units.
    """
    return correlation(recording, template, method)[1]


def refine(analytic, i, design=DEFAULT):
    """Position of the envelope peak near index `i`, to a fraction of a
    sample: the analytic correlation around `i` is interpolated
    `design.upsample` times (it is band-limited, so FFT interpolation is
    exact in principle), then a parabola is fitted through the top. Needs
    `design.refine_half` samples either side."""
    half, up_by = design.refine_half, design.upsample
    lo, hi = i - half, i + half
    if lo < 0 or hi > len(analytic):
        return float(i)
    up = np.abs(signal.resample(analytic[lo:hi], 2 * half * up_by))
    j = int(np.argmax(up))
    if 0 < j < len(up) - 1:
        left, mid, right = up[j - 1], up[j], up[j + 1]
        bend = left - 2 * mid + right
        shift = 0.5 * (left - right) / bend if bend else 0.0
    else:
        shift = 0.0
    return lo + (j + shift) / up_by


def noise_level(env, template, unit=INT16_STEP):
    """Typical envelope level of noise alone: the median of the envelope,
    but never below what rounding to int16 alone would give. `unit` is the
    size of one recording unit in full scale: 1/32768 for int16 data (the
    default), 1.0 for floats in full-scale units."""
    floor = 1.18 * QUANTISATION * (INT16_STEP / unit) * np.sqrt(
        np.sum(np.asarray(template) ** 2))
    return max(float(np.median(env)), floor)


def level_dbfs(peak, template, method="matched", unit=INT16_STEP):
    """Peak amplitude of an arrival, dB re full scale, from the height of
    its filter peak. A matched-filter peak is amplitude times the template
    energy; an envelope peak is the amplitude itself, relative to the
    template's own rms. `unit` as for noise_level."""
    template = np.asarray(template, dtype=np.float64)
    if method == "envelope":
        amplitude = peak / np.sqrt(2.0 * np.mean(template ** 2)) * unit
    else:
        amplitude = peak / np.sum(template ** 2) * unit
    return 20 * np.log10(max(amplitude, 1e-12))


def leading(env, i, length, floor, fraction=DEFAULT.first_fraction):
    """Index of the first arrival belonging to the peak at `i`: the earliest
    peak in the template length before `i` that reaches `fraction` of env[i]
    (and `floor`), else `i` itself. On an acoustic path a reflection (off a
    screen, a table) can be stronger than the direct sound; the direct sound
    is the one that arrives first."""
    lo = max(0, i - length)
    if i - lo < 3:
        return i
    earlier, _ = signal.find_peaks(env[lo:i], height=max(floor, fraction * env[i]))
    return lo + int(earlier[0]) if len(earlier) else i


def locate(window, template, design=DEFAULT, snr=None, unit=INT16_STEP):
    """Strongest arrival of `template` in `window`, or None.

    Returns (position in window samples as a float, level_dbfs, snr_db).
    Used for tests and one-off captures; `checks.ArrivalDetector` is the
    streaming version. `snr` overrides design.hit_snr.
    """
    analytic, env = correlation(window, template, design.method)
    if len(env) == 0:
        return None
    i = int(np.argmax(env))
    ratio = env[i] / noise_level(env, template, unit)
    if ratio < (design.hit_snr if snr is None else snr):
        return None
    return (refine(analytic, i, design),
            level_dbfs(env[i], template, design.method, unit),
            20 * np.log10(ratio))


def input_check(samples, design=DEFAULT, unit=INT16_STEP):
    """What the input sounds like with nothing played: a dict of DC offset,
    noise level and clipping, with plain-language warnings. A built-in
    laptop mic left at the desktop's gain can sit at full scale with a large
    DC offset, which hides every chirp. `samples` are int16 steps, or floats
    in full-scale units if `unit` is 1.0. The limits are the design's."""
    x = np.asarray(samples, dtype=np.float64)
    if len(x) == 0:
        return dict(seconds=0.0, warnings=["No input to check."])
    full_scale = 1.0 / unit
    dc = float(x.mean())
    ac = x - dc
    rms_db = 20 * np.log10(max(float(np.sqrt(np.mean(ac ** 2))), 1e-9) / full_scale)
    clipped = float(np.mean(np.abs(x) >= full_scale * 32767.0 / 32768.0))
    warnings = []
    if clipped > design.clip_fraction:
        warnings.append(f"The input is clipping ({100 * clipped:.1f} % of samples "
                        "at full scale) with nothing playing: lower the capture "
                        "gain or mic boost, or chirps will not be found.")
    if abs(dc) > design.dc_fraction * full_scale:
        warnings.append(f"The input has a large DC offset ({100 * dc / full_scale:+.0f} % "
                        "of full scale), usually too much capture gain or a mic "
                        "input still settling.")
    if rms_db > design.noise_dbfs and clipped <= design.clip_fraction:
        warnings.append(f"The input is noisy with nothing playing ({rms_db:.0f} dBFS "
                        "rms): too much capture gain, or a loud room.")
    return dict(dc_fraction=dc / full_scale, noise_rms_dbfs=rms_db,
                clipped_fraction=clipped, warnings=warnings)


def resolution(f0, f1, duration=None, rate=48000.0, taper=1.0,
               measure="first_null", template=None):
    """Spacing, in seconds, below which two arrivals merge into one, read off
    the signal's own matched-filter peak (its autocorrelation envelope), so
    it follows the taper and band of the actual signal.

    `measure` (a detection design's "resolution" setting): "first_null", the
    first null either side of the peak (equal echoes this far apart do not
    overlap at all); "minus3db" / "minus6db", the peak's full width that far
    down. For the lab's default fully tapered chirp these come to about
    3.0, 1.9 and 2.6 / bandwidth; for an untapered chirp to about 1.0, 0.9
    and 1.2. Pass `template` (samples at `rate`) for a signal that is not a
    plain chirp. Without a duration, falls back to 3 / bandwidth.
    """
    if template is None:
        if duration is None:
            return 3.0 / abs(f1 - f0)
        from .signals import make_chirp
        template = make_chirp(rate, f0, f1, duration, taper)
    return _peak_width(np.asarray(template, dtype=np.float64), rate, measure)


def _peak_width(template, rate, measure, upsample=16):
    """Seconds: see `resolution`. The envelope of the autocorrelation is
    interpolated `upsample` times, then read either side of its peak."""
    corr = signal.correlate(template, template, mode="full", method="fft")
    env = np.abs(signal.hilbert(corr))
    centre = int(np.argmax(env))
    half = min(centre, len(env) - 1 - centre, 4 * len(template))
    piece = signal.resample(env[centre - half:centre + half + 1], (2 * half + 1) * upsample)
    piece = np.abs(piece) / np.max(np.abs(piece))
    top = int(np.argmax(piece))
    right = piece[top:]
    if measure == "first_null":
        rising = np.nonzero(np.diff(right) > 0)[0]
        i = int(rising[0]) if len(rising) else len(right) - 1
        return i / upsample / rate
    level = {"minus3db": 10 ** (-3 / 20), "minus6db": 0.5}.get(measure)
    if level is None:
        raise ValueError(f"unknown resolution measure {measure!r}")
    below = np.nonzero(right < level)[0]
    i = int(below[0]) if len(below) else len(right) - 1
    return 2 * i / upsample / rate


@dataclass
class Arrival:
    sample: float    # start of the template in the recording, sub-sample
    level: float     # envelope height, same units as the matched filter


def find_arrivals(envelope, rate, threshold=0.1, min_separation=0.0005,
                  max_arrivals=8):
    """Peaks of the matched-filter envelope, in time order.

    threshold is a fraction of the tallest peak; min_separation is in
    seconds. Peak position is refined by a parabola through three points.
    """
    if envelope.size < 3 or envelope.max() <= 0:
        return []
    distance = max(1, int(round(min_separation * rate)))
    peaks, _ = signal.find_peaks(
        envelope, height=threshold * envelope.max(), distance=distance)
    # Keep the tallest ones, then put them back in time order.
    peaks = sorted(sorted(peaks, key=lambda p: envelope[p])[-max_arrivals:])
    arrivals = []
    for p in peaks:
        offset = 0.0
        if 0 < p < envelope.size - 1:
            a, b, c = envelope[p - 1], envelope[p], envelope[p + 1]
            curvature = a - 2 * b + c
            if curvature < 0:
                offset = 0.5 * (a - c) / curvature
        arrivals.append(Arrival(sample=p + offset, level=float(envelope[p])))
    return arrivals


def noise_spectrum(recording, rate, resolution=50.0):
    """Typical power spectrum of a recording.

    Welch's method with the median over time, so the result is the steady
    background: a short bang or click does not raise it. Returns
    (frequencies in Hz, level in dB per Hz relative to full scale).
    """
    recording = np.asarray(recording, dtype=np.float64)
    segment = min(max(int(rate / resolution), 64), max(recording.size, 64))
    freqs, power = signal.welch(recording, rate, nperseg=segment,
                                average="median")
    return freqs, 10 * np.log10(power + 1e-20)


def band_levels(recording, rate, step=1000.0):
    """Noise level in each `step`-wide band, as dicts with f0, f1 and
    level_db (rms within the band, dB relative to full scale)."""
    freqs, db = noise_spectrum(recording, rate)
    power = 10 ** (db / 10)
    width = freqs[1] - freqs[0]
    bands = []
    for lo in np.arange(0.0, rate / 2 - step / 2, step):
        inside = (freqs >= lo) & (freqs < lo + step)
        if inside.any():
            bands.append(dict(f0=float(lo), f1=float(lo + step), level_db=float(
                10 * np.log10(power[inside].sum() * width + 1e-20))))
    return bands


# ---- the transmissions of one ping -------------------------------------

@dataclass
class EventSpec:
    """One transmission to look for in a recording."""
    label: str              # for display: "1: left chirp up @ 0 ms"
    key: str                # events with the same key share a filter
    template: np.ndarray    # what was sent, scaled to peak 1.0
    time: float             # s after the start of the ping


@dataclass
class EventResult:
    first: float        # sample of the first arrival in the recording
    level: float        # height of the event's strongest peak
    snr: float          # strongest peak over the typical noise level
    arrivals: list      # every peak above 5% of the strongest, in time order


@dataclass
class Analysis:
    """What was found in one recording. Events are numbered as in `events`."""
    events: list
    rate: float
    design: DetectionDesign = DEFAULT                # the settings it was made with
    envelopes: dict = field(default_factory=dict)    # key -> envelope
    results: list = field(default_factory=list)      # EventResult or None, per event
    warnings: list = field(default_factory=list)

    def detected(self):
        return [i for i, r in enumerate(self.results) if r is not None]

    def _sent(self, index):
        return int(round(self.events[index].time * self.rate))

    @property
    def reference(self):
        """Time zero for display, as a sample in the recording: the loudest
        event's first arrival, moved back to the start of the ping."""
        found = self.detected()
        if not found:
            return None
        loudest = max(found, key=lambda i: self.results[i].level)
        return self.results[loudest].first - self._sent(loudest)

    def top(self):
        return max(self.results[i].level for i in self.detected())

    def delay_ms(self, index):
        """An event's first arrival in ms after the reference, with the
        event's own sending time taken out."""
        first = self.results[index].first - self._sent(index)
        return (first - self.reference) / self.rate * 1e3

    def trace_db(self, index, before_ms, span_ms, floor_db):
        """An event's matched-filter output around when it was due, in dB
        below the ping's strongest peak. Works for an undetected event."""
        envelope = self.envelopes[self.events[index].key]
        start = (int(round(self.reference)) + self._sent(index)
                 - int(before_ms / 1e3 * self.rate))
        count = int((before_ms + span_ms) / 1e3 * self.rate)
        out = np.full(count, float(floor_db))
        lo, hi = max(start, 0), min(start + count, envelope.size)
        if hi > lo:
            db = 20 * np.log10(np.maximum(envelope[lo:hi], 1e-12) / self.top())
            out[lo - start:hi - start] = np.maximum(db, floor_db)
        return out


def inseparable(events, design=DEFAULT):
    """Groups of events that share a signal and fire within the search
    window of each other. Their sounds add together, so the analysis sees
    one arrival and reports it for each of them."""
    search = design.search_s
    groups = []
    for i, a in enumerate(events):
        if any(i in g for g in groups):
            continue
        group = [j for j, b in enumerate(events)
                 if b.key == a.key and abs(b.time - a.time) < 2 * search]
        if len(group) > 1:
            groups.append(group)
    return groups


def isolation_db(own, other):
    """How far below its own peak `other` shows up in the matched filter of
    `own`, in dB (negative: -17 means 17 dB down). Two signals that share
    time and band leak into each other's filters: an up-chirp and a down-chirp
    of one band only about 17 dB down, two separate bands 100 dB or more."""
    own, other = np.asarray(own, dtype=np.float64), np.asarray(other, dtype=np.float64)
    pad = np.zeros(max(own.size, other.size))
    cross = matched_filter(np.concatenate([pad, other, pad]), own).max()
    peak = matched_filter(np.concatenate([pad, own, pad]), own).max()
    return float(20 * np.log10(max(cross, 1e-12) / peak))


def leaking(events, rate, design=DEFAULT, worse_than_db=None):
    """Pairs of events with different signals that overlap in time and are
    poorly separated by their filters.

    Returns (i, j, isolation_db): how far below its own peak signal j shows
    up in signal i's filter. Separate bands give -40 dB or better; an
    up-chirp against a down-chirp over the same band gives only about -10 to
    -20 dB, and the leak is smeared over the length of the chirp, so it
    lands at the wrong time. The threshold is design.leak_db unless
    `worse_than_db` is given. With the envelope method there is no filter to
    leak into, so there is nothing to find.
    """
    if worse_than_db is None:
        worse_than_db = design.leak_db
    pairs = []
    if design.method != "matched":
        return pairs
    for i, a in enumerate(events):
        for j, b in enumerate(events):
            if j <= i or a.key == b.key:
                continue
            da, db_ = a.template.size / rate, b.template.size / rate
            if abs(a.time - b.time) > max(da, db_) + design.search_s:
                continue
            isolation = isolation_db(a.template, b.template)
            if isolation > worse_than_db:
                pairs.append((i, j, float(isolation)))
    return pairs


def _window_peak(envelope, centre, half):
    lo, hi = max(centre - half, 0), min(centre + half, envelope.size)
    return float(envelope[lo:hi].max()) if hi - lo > 0 else 0.0


def analyse_events(recording, rate, events, first_threshold=None,
                   design=DEFAULT):
    """Find each event's first arrival (and later ones) in a recording.

    How is the design's business: its method, thresholds and windows (see
    detection_design.SETTINGS). `first_threshold`, if given, replaces the
    design's first-arrival fraction. Events that were not found are None in
    `results`; the reasons are in `warnings`.
    """
    first_fraction = design.first_fraction if first_threshold is None else first_threshold
    detect = design.detect_snr
    recording = np.asarray(recording)
    analysis = Analysis(events=list(events), rate=rate, design=design,
                        results=[None] * len(events))
    if not events:
        analysis.warnings.append("the ping has no events")
        return analysis
    longest = max(e.template.size for e in events)
    if recording.size < longest + 16:
        analysis.warnings.append("recording too short")
        return analysis
    if np.max(np.abs(recording)) < 10 ** (-70 / 20):
        analysis.warnings.append("recording is silent")
        return analysis

    noise = {}
    for e in events:
        if e.key not in analysis.envelopes:
            envelope = matched_filter(recording, e.template, design.method)
            analysis.envelopes[e.key] = envelope
            noise[e.key] = float(np.median(envelope)) or 1e-12
    sent = [int(round(e.time * rate)) for e in events]
    half = int(design.search_s * rate)
    envelopes = analysis.envelopes

    # Anchor on the clearest peak of any signal. It belongs to one of the
    # events that use that signal; each choice puts the start of the ping
    # somewhere different. Keep the choice under which the other events
    # turn up where they should.
    anchor = max(envelopes, key=lambda k: envelopes[k].max() / noise[k])
    peak = int(np.argmax(envelopes[anchor]))
    if envelopes[anchor][peak] < detect * noise[anchor]:
        analysis.warnings.append("nothing stands out from the noise")
        return analysis
    best_start, best_score = None, -1.0
    for k, e in enumerate(events):
        if e.key != anchor:
            continue
        start = peak - sent[k]
        score = 0.0
        for j, other in enumerate(events):
            if j == k:
                continue
            strength = (_window_peak(envelopes[other.key], start + sent[j], half)
                        / noise[other.key])
            if strength >= detect:
                score += strength
        if score > best_score:
            best_start, best_score = start, score

    for j, e in enumerate(events):
        envelope = envelopes[e.key]
        centre = best_start + sent[j]
        lo, hi = max(centre - half, 0), min(centre + half, envelope.size)
        if hi - lo < 16 or envelope[lo:hi].max() < detect * noise[e.key]:
            continue
        window = envelope[lo:hi]
        found = find_arrivals(window, rate, first_fraction, design.min_separation_s,
                              design.max_arrivals)
        if found:
            every = find_arrivals(window, rate, design.listed_fraction,
                                  design.min_separation_s, design.max_arrivals)
            analysis.results[j] = EventResult(
                first=found[0].sample + lo, level=float(window.max()),
                snr=float(window.max() / noise[e.key]),
                arrivals=[Arrival(a.sample + lo, a.level) for a in every])

    for group in inseparable(events, design):
        analysis.warnings.append(
            "events " + " and ".join(str(i + 1) for i in group)
            + " use the same signal at nearly the same time: they are one "
              "combined sound and cannot be told apart")
    for i, j, isolation in leaking(events, rate, design):
        analysis.warnings.append(
            f"events {i + 1} and {j + 1} overlap in time and band: each leaks "
            f"into the other's filter only {-isolation:.0f} dB down, smeared "
            f"in time, so the weaker one's arrival is not reliable")
    missing = len(events) - len(analysis.detected())
    if missing and len(analysis.detected()) == 1 and len(events) > 1:
        analysis.warnings.append(
            "only one event was heard, so which one it is may be wrong")
    elif missing:
        analysis.warnings.append(f"{missing} event(s) not heard")
    return analysis
