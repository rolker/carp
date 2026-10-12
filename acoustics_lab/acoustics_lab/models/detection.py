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

SEARCH = 0.03       # how far either side of its expected time an event is looked for, s
DETECT = 8.0        # an arrival must be this many times the typical noise level


def matched_filter(recording, template):
    """Envelope of the recording correlated against the template.

    Index i of the result is the template starting at sample i of the
    recording. The template is normally peak 1.0, so the envelope height is
    in the recording's own units.
    """
    recording = np.asarray(recording, dtype=np.float64)
    recording = recording - recording.mean()
    correlation = signal.correlate(recording, template, mode="valid",
                                   method="fft")
    return np.abs(signal.hilbert(correlation))


def resolution(f0, f1):
    """Rough spacing, in seconds, below which two arrivals merge into one.

    About 3 / bandwidth for the default fully tapered chirp.
    """
    return 3.0 / abs(f1 - f0)


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


def inseparable(events):
    """Groups of events that share a signal and fire within the search
    window of each other. Their sounds add together, so the analysis sees
    one arrival and reports it for each of them."""
    groups = []
    for i, a in enumerate(events):
        if any(i in g for g in groups):
            continue
        group = [j for j, b in enumerate(events)
                 if b.key == a.key and abs(b.time - a.time) < 2 * SEARCH]
        if len(group) > 1:
            groups.append(group)
    return groups


def leaking(events, rate, worse_than_db=-25.0):
    """Pairs of events with different signals that overlap in time and are
    poorly separated by their filters.

    Returns (i, j, isolation_db): how far below its own peak signal j shows
    up in signal i's filter. Separate bands give -40 dB or better; an
    up-chirp against a down-chirp over the same band gives only about -10 to
    -20 dB, and the leak is smeared over the length of the chirp, so it
    lands at the wrong time.
    """
    pairs = []
    for i, a in enumerate(events):
        for j, b in enumerate(events):
            if j <= i or a.key == b.key:
                continue
            da, db_ = a.template.size / rate, b.template.size / rate
            if abs(a.time - b.time) > max(da, db_) + SEARCH:
                continue
            pad = np.zeros(max(a.template.size, b.template.size))
            cross = matched_filter(
                np.concatenate([pad, b.template, pad]), a.template).max()
            own = matched_filter(
                np.concatenate([pad, a.template, pad]), a.template).max()
            isolation = 20 * np.log10(max(cross, 1e-12) / own)
            if isolation > worse_than_db:
                pairs.append((i, j, float(isolation)))
    return pairs


def _window_peak(envelope, centre, half):
    lo, hi = max(centre - half, 0), min(centre + half, envelope.size)
    return float(envelope[lo:hi].max()) if hi - lo > 0 else 0.0


def analyse_events(recording, rate, events, first_threshold=0.3):
    """Find each event's first arrival (and later ones) in a recording.

    first_threshold is the fraction of an event's strongest peak that an
    arrival must reach to count as its first. Events that were not found are
    None in `results`; the reasons are in `warnings`.
    """
    recording = np.asarray(recording)
    analysis = Analysis(events=list(events), rate=rate,
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
            envelope = matched_filter(recording, e.template)
            analysis.envelopes[e.key] = envelope
            noise[e.key] = float(np.median(envelope)) or 1e-12
    sent = [int(round(e.time * rate)) for e in events]
    half = int(SEARCH * rate)
    envelopes = analysis.envelopes

    # Anchor on the clearest peak of any signal. It belongs to one of the
    # events that use that signal; each choice puts the start of the ping
    # somewhere different. Keep the choice under which the other events
    # turn up where they should.
    anchor = max(envelopes, key=lambda k: envelopes[k].max() / noise[k])
    peak = int(np.argmax(envelopes[anchor]))
    if envelopes[anchor][peak] < DETECT * noise[anchor]:
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
            if strength >= DETECT:
                score += strength
        if score > best_score:
            best_start, best_score = start, score

    for j, e in enumerate(events):
        envelope = envelopes[e.key]
        centre = best_start + sent[j]
        lo, hi = max(centre - half, 0), min(centre + half, envelope.size)
        if hi - lo < 16 or envelope[lo:hi].max() < DETECT * noise[e.key]:
            continue
        window = envelope[lo:hi]
        found = find_arrivals(window, rate, first_threshold)
        if found:
            every = find_arrivals(window, rate, 0.05)
            analysis.results[j] = EventResult(
                first=found[0].sample + lo, level=float(window.max()),
                snr=float(window.max() / noise[e.key]),
                arrivals=[Arrival(a.sample + lo, a.level) for a in every])

    for group in inseparable(events):
        analysis.warnings.append(
            "events " + " and ".join(str(i + 1) for i in group)
            + " use the same signal at nearly the same time: they are one "
              "combined sound and cannot be told apart")
    for i, j, isolation in leaking(events, rate):
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
