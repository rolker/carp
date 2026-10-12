"""The two checks to run on a new dongle, as functions on any `DuplexDevice`.

**Offset test.** Play a short chirp on one output channel every half second.
A resistor feeds that output into the same dongle's mic input, so each ping
is heard again a little later, by the electrical path only. The distance in
samples from the output sample where the ping was scheduled to the input
sample where it is found is the output-to-input offset of that device. It
is the truth about timing; PortAudio's own figure is printed beside it for
comparison and is not used. Its spread over many pings is the jitter, and
its slope over minutes is drift.

**Schedule test.** A rehearsal of a transponder with a fixed turnaround time:
find each loopback arrival as it comes in and schedule the next pulse
exactly N samples after it. The pulse can only start on a whole output
sample, so some error is unavoidable (uniform within +-0.5 sample); the test
reports how much more there is.

Positions are in samples on the device's clock; seconds are samples divided
by the rate. Amplitudes are in int16 steps unless a name says dBFS.
"""
import csv
import json
import os
import platform
import time
from dataclasses import dataclass, field

import numpy as np
from scipy import signal

from ..models.signals import make_chirp
from .stream import LateError

SETTLE = 64                 # samples of context either side of a peak
UPSAMPLE = 16               # sub-sample search resolution is 1/16 sample
HALF = 48                   # samples either side of a peak that are upsampled
QUANTISATION = 1.0 / np.sqrt(12.0)   # rms of int16 rounding, in steps


# -- the ping and finding it --------------------------------------------------

def make_ping(rate, kind="chirp", f0=2000.0, f1=20000.0, duration=0.010):
    """The test signal, peak 1.0: a chirp (default 2-20 kHz, 10 ms, fully
    tapered like the other chirps here) or a click (an 8-sample Hann pulse,
    broad but short)."""
    if kind == "click":
        return signal.windows.hann(10)[1:-1]
    if kind != "chirp":
        raise ValueError("ping kind is 'chirp' or 'click'")
    return make_chirp(rate, f0, f1, duration)


def correlation(window, template):
    """Analytic matched-filter output of `window` against `template`.

    Index i is the template starting at sample i of the window. The mean is
    removed first (mic bias). Returns (complex array, envelope array).
    """
    data = np.asarray(window, dtype=np.float64)
    data = data - data.mean()
    c = signal.correlate(data, template, mode="valid", method="fft")
    analytic = signal.hilbert(c)
    return analytic, np.abs(analytic)


def refine(analytic, i):
    """Position of the envelope peak near index `i`, to a fraction of a
    sample: the analytic correlation around `i` is interpolated 16 times
    (it is band-limited, so FFT interpolation is exact in principle), then a
    parabola is fitted through the top. Needs HALF samples either side."""
    lo, hi = i - HALF, i + HALF
    if lo < 0 or hi > len(analytic):
        return float(i)
    up = np.abs(signal.resample(analytic[lo:hi], 2 * HALF * UPSAMPLE))
    j = int(np.argmax(up))
    if 0 < j < len(up) - 1:
        left, mid, right = up[j - 1], up[j], up[j + 1]
        bend = left - 2 * mid + right
        shift = 0.5 * (left - right) / bend if bend else 0.0
    else:
        shift = 0.0
    return lo + (j + shift) / UPSAMPLE


def locate(window, template, snr=10.0):
    """Strongest arrival of `template` in `window`, or None.

    Returns (position in window samples as a float, level_dbfs, snr_db).
    Used for tests and one-off captures; `ArrivalDetector` is the streaming
    version.
    """
    analytic, env = correlation(window, template)
    if len(env) == 0:
        return None
    i = int(np.argmax(env))
    ratio = env[i] / _noise(env, template)
    if ratio < snr:
        return None
    return refine(analytic, i), _level_dbfs(env[i], template), 20 * np.log10(ratio)


def _noise(env, template):
    """Typical envelope level of noise alone: the median of the envelope,
    but never below what int16 rounding noise alone would give."""
    floor = 1.18 * QUANTISATION * np.sqrt(np.sum(template ** 2))
    return max(float(np.median(env)), floor)


def _level_dbfs(peak, template):
    """Peak amplitude of an arrival, dB below full scale, from the height of
    its matched-filter peak (which is amplitude times the template energy)."""
    amplitude = peak / np.sum(template ** 2) / 32768.0
    return 20 * np.log10(max(amplitude, 1e-12))


FIRST_FRACTION = 0.3         # an earlier peak this fraction of the strongest
                             # (-10.5 dB) or more counts as the first arrival
SETTLE_S = 2.0               # s of input to let go by after the stream opens


def leading(env, i, length, floor):
    """Index of the first arrival belonging to the peak at `i`: the earliest
    peak in the template length before `i` that reaches FIRST_FRACTION of
    env[i] (and `floor`), else `i` itself. On an acoustic path a reflection
    (off a screen, a table) can be stronger than the direct sound; the
    direct sound is the one that arrives first."""
    lo = max(0, i - length)
    if i - lo < 3:
        return i
    earlier, _ = signal.find_peaks(env[lo:i], height=max(floor, FIRST_FRACTION * env[i]))
    return lo + int(earlier[0]) if len(earlier) else i


@dataclass
class Arrival:
    position: float          # input sample (float) where the template starts
    level_dbfs: float        # peak amplitude, dB re full scale
    snr_db: float            # peak over typical noise level
    to_strongest: float = 0.0    # samples from this (first) arrival to the
                                 # strongest one, if a later copy was stronger


class ArrivalDetector:
    """Finds copies of a template in a device's input as they arrive.

    Call `poll()` as often as convenient; it returns the arrivals that are
    new and final. An arrival is reported once the input holds the template
    length plus a margin beyond it, twice over: once for the matched filter
    to finish, once to be sure no stronger peak follows within a template
    length (correlation sidelobes of a loud ping rise above a quiet
    threshold). That is about 2 template lengths + 64 samples of delay
    (21 ms for the default chirp), the reaction time of this detector.
    """

    def __init__(self, device, template, snr=10.0, start=None):
        self.device = device
        self.template = np.asarray(template, dtype=np.float64)
        self.length = len(self.template)
        self.snr = snr
        self.cursor = device.in_position if start is None else int(start)
        self.last = None          # position of the last arrival reported

    def poll(self):
        """New arrivals since the last call, oldest first."""
        end = self.device.in_position
        final = end - 2 * self.length - SETTLE
        if final < self.cursor + 128:
            return []
        first = max(0, self.cursor - SETTLE)
        window = self.device.read_input(first, end)
        analytic, env = correlation(window, self.template)
        threshold = self.snr * _noise(env, self.template)
        peaks, _ = signal.find_peaks(env, height=threshold, distance=self.length)
        found = []
        for strongest in peaks:
            i = leading(env, int(strongest), self.length, threshold)
            absolute = first + int(i)
            if not self.cursor <= absolute <= final:
                continue
            position = first + refine(analytic, int(i))
            if self.last is not None and abs(position - self.last) < self.length:
                continue          # a sidelobe of the one just reported
            self.last = position
            found.append(Arrival(
                position, _level_dbfs(env[i], self.template),
                20 * np.log10(env[i] / _noise(env, self.template)),
                float(strongest - i)))
        self.cursor = final + 1
        return found


# -- input check ----------------------------------------------------------------

def input_check(samples):
    """What the input sounds like with nothing played: a dict of DC offset,
    noise level and clipping, with plain-language warnings. A built-in
    laptop mic left at the desktop's gain can sit at full scale with a large
    DC offset, which hides every chirp."""
    x = np.asarray(samples, dtype=np.float64)
    if len(x) == 0:
        return dict(seconds=0.0, warnings=["No input to check."])
    dc = float(x.mean())
    ac = x - dc
    rms_db = 20 * np.log10(max(float(np.sqrt(np.mean(ac ** 2))), 1e-9) / 32768.0)
    clipped = float(np.mean(np.abs(x) >= 32767))
    warnings = []
    if clipped > 0.001:
        warnings.append(f"The input is clipping ({100 * clipped:.1f} % of samples "
                        "at full scale) with nothing playing: lower the capture "
                        "gain or mic boost, or chirps will not be found.")
    if abs(dc) > 0.02 * 32768:
        warnings.append(f"The input has a large DC offset ({100 * dc / 32768:+.0f} % "
                        "of full scale), usually too much capture gain or a mic "
                        "input still settling.")
    if rms_db > -30 and clipped <= 0.001:
        warnings.append(f"The input is noisy with nothing playing ({rms_db:.0f} dBFS "
                        "rms): too much capture gain, or a loud room.")
    return dict(dc_fraction=dc / 32768.0, noise_rms_dbfs=rms_db,
                clipped_fraction=clipped, warnings=warnings)


def settle_and_check(device, settle=SETTLE_S, check_s=1.0):
    """Let the first `settle` s of input go by (inputs often start with a
    thump or a DC offset that takes a moment to die away), then check the
    last `check_s` of it. Returns the input_check dict."""
    rate = device.rate
    want = max(int(settle * rate), 4 * device.frames_per_buffer)
    device.wait_input(want, timeout=settle + 5)
    end = device.in_position
    start = max(0, end - int(check_s * rate))
    try:
        quiet = device.read_input(start, end)
    except Exception:            # older than the ring holds: skip the check
        quiet = []
    result = input_check(quiet)
    result["seconds"] = (end - start) / rate
    return result


# -- statistics ---------------------------------------------------------------

def spread(values):
    """mean, standard deviation (n-1), largest deviation from the mean, and
    the range of a list of numbers; zeros for fewer than two."""
    v = np.asarray(values, dtype=np.float64)
    if len(v) == 0:
        return dict(n=0, mean=0.0, std=0.0, max_dev=0.0, min=0.0, max=0.0)
    mean = float(v.mean())
    return dict(n=len(v), mean=mean,
                std=float(v.std(ddof=1)) if len(v) > 1 else 0.0,
                max_dev=float(np.max(np.abs(v - mean))),
                min=float(v.min()), max=float(v.max()))


def trend(times, values):
    """Slope of values against times (seconds) by least squares, in value
    units per second; 0.0 for fewer than three points."""
    if len(values) < 3:
        return 0.0
    return float(np.polyfit(np.asarray(times, float), np.asarray(values, float), 1)[0])


def level_text(level_db):
    amplitude = 10 ** (level_db / 20)
    return (f"{level_db:g} dBFS peak (amplitude {amplitude:.3g} of full scale, "
            f"{amplitude * 32767:.0f} of 32767)")


# -- offset test --------------------------------------------------------------

@dataclass
class PingRow:
    k: int
    scheduled: int                   # output sample
    arrival: float = float("nan")    # input sample, or nan if not found
    offset: float = float("nan")     # arrival - scheduled, samples
    level_dbfs: float = float("nan")
    snr_db: float = float("nan")
    xrun: bool = False
    note: str = ""

    @property
    def valid(self):
        return self.offset == self.offset and not self.xrun


@dataclass
class TestResult:
    kind: str                        # "offset" or "schedule"
    rows: list
    summary: dict
    verdict: list                    # plain-language lines
    folder: str = ""


def run_offset_test(device, seconds, level_db=-20.0, channel="left",
                    interval=0.5, ping="chirp", progress=None,
                    should_stop=lambda: False, settle=SETTLE_S):
    """Ping every `interval` s for `seconds`, find each loopback copy and
    measure the offset from its scheduled output sample.

    The device must be started. progress(done, total) is called per ping.
    Returns a TestResult.
    """
    rate = device.rate
    template = make_ping(rate, ping)
    gain = 10 ** (level_db / 20)
    total = max(1, int(seconds / interval))
    step = max(1, int(round(interval * rate)))
    check = settle_and_check(device, settle)
    first = device.out_position + int(0.5 * rate)
    plan = [first + k * step for k in range(total)]
    rows = [PingRow(k, s) for k, s in enumerate(plan)]
    detector = ArrivalDetector(device, template)
    scheduled = 0
    stray = 0
    wall0 = time.monotonic()
    deadline = plan[-1] + step
    while device.in_position < deadline and not should_stop():
        while scheduled < total and plan[scheduled] < device.out_position + int(2 * rate):
            try:
                device.schedule(template, plan[scheduled], channel, gain)
            except LateError as error:
                rows[scheduled].note = f"scheduled {error.late_by} samples late"
            scheduled += 1
        device.wait_input(device.in_position + 2048, timeout=5)
        for arrival in detector.poll():
            k = _owner(plan, arrival.position)
            row = rows[k] if k is not None else None
            if row is None or row.arrival == row.arrival:
                stray += 1
                continue
            row.arrival = arrival.position
            row.offset = arrival.position - row.scheduled
            row.level_dbfs = arrival.level_dbfs
            row.snr_db = arrival.snr_db
            if progress:
                progress(sum(r.offset == r.offset for r in rows), total)
    for row in rows:
        stop = (row.arrival if row.arrival == row.arrival
                else row.scheduled + step) + len(template) + device.frames_per_buffer
        if device.xruns_between(row.scheduled - device.frames_per_buffer, stop):
            row.xrun = True
    return _offset_result(device, rows, template, level_db, channel, interval,
                          ping, stray, time.monotonic() - wall0, check)


def _xruns_since(device, sample):
    """(counts by kind, events) for xruns from `sample` on. Those before it
    (ALSA often flags the first blocks while the stream starts) are not the
    test's business."""
    counts = {}
    events = [e for e in device.xruns() if e.sample + e.frames > sample]
    for e in events:
        for kind in e.kinds:
            counts[kind] = counts.get(kind, 0) + 1
    return counts, events


def _owner(plan, position):
    """Index of the scheduled ping that `position` belongs to: the last one
    that starts at or before it (a copy never comes earlier than its ping)."""
    k = int(np.searchsorted(plan, position + 2, side="right")) - 1
    return k if k >= 0 else None


GROUP_SAMPLES = 5.0          # offsets this close to the median are one group


def _offset_result(device, rows, template, level_db, channel, interval, ping,
                   stray, wall_seconds, check=None):
    rate = device.rate
    valid = [r for r in rows if r.valid]
    # The steady offset is the main group of measurements. A few may land
    # elsewhere: an echo found when the direct sound was too weak, or noise
    # taken for a ping. Those are counted and shown, not averaged in.
    centre = float(np.median([r.offset for r in valid])) if valid else 0.0
    good = [r for r in valid if abs(r.offset - centre) <= GROUP_SAMPLES]
    outliers = [r for r in valid if abs(r.offset - centre) > GROUP_SAMPLES]
    for r in outliers:
        r.note = (r.note + "; " if r.note else "") + "outside the main group"
    if len(good) < 3:
        good, outliers = valid, []
    found = [r for r in rows if r.offset == r.offset]
    times = [(r.scheduled - rows[0].scheduled) / rate for r in good]
    offsets = [r.offset for r in good]
    stats = spread(offsets)
    slope = trend(times, offsets)                  # samples per second
    duration = (rows[-1].scheduled - rows[0].scheduled) / rate if rows else 0.0
    timing = device.timing()
    counts, events = _xruns_since(device, rows[0].scheduled - device.frames_per_buffer)
    summary = dict(
        test="offset", when=time.strftime("%Y-%m-%d %H:%M:%S"),
        device=device.describe(), ping=ping, level_dbfs=level_db,
        channel=channel, interval_s=interval, rate=rate,
        pings=len(rows), found=len(found), missed=len(rows) - len(found),
        stray=stray, in_xrun=sum(r.xrun for r in found), used=len(good),
        offset_mean_samples=stats["mean"], offset_std_samples=stats["std"],
        offset_max_dev_samples=stats["max_dev"],
        offset_min_samples=stats["min"], offset_max_samples=stats["max"],
        offset_mean_ms=1000 * stats["mean"] / rate,
        drift_samples_per_min=60 * slope,
        drift_ppm=1e6 * slope / rate,
        duration_s=duration, wall_s=wall_seconds,
        portaudio_claimed_offset_samples=timing["claimed_offset_samples"],
        clock_ratio=timing["clock_ratio"],
        xruns=counts, startup_xruns=device.xrun_count - len(events),
        xrun_events=[dict(sample=e.sample, kinds=e.kinds) for e in events[:200]],
        level_seen_dbfs=float(np.mean([r.level_dbfs for r in good])) if good else None,
        outliers=len(outliers),
        outlier_offsets_samples=[round(r.offset - centre, 1) for r in outliers[:50]],
        input_check=check or {},
        python=platform.python_version())
    summary["verdict_ok"], summary["verdict_lines"] = offset_verdict(summary)
    return TestResult("offset", rows, summary, summary["verdict_lines"])


def _minutes_text(seconds):
    if seconds >= 90:
        return f"{seconds / 60:.0f} min" if seconds >= 600 else f"{seconds / 60:.1f} min"
    return f"{seconds:.0f} s"


def offset_verdict(s):
    """(ok, lines): the result in plain words. ok means no cause for worry."""
    lines = []
    problems = 0
    span = _minutes_text(s["duration_s"])
    for warning in s.get("input_check", {}).get("warnings", []):
        lines.append("Before the test: " + warning)
        problems += 1
    if s["used"] < 3:
        lines.append(f"Only {s['used']} of {s['pings']} pings gave a usable "
                     "measurement. With a loopback: is the resistor connected, "
                     "and is the output channel the one wired to it? Through the "
                     "air (speaker to mic): is the output loud enough and the "
                     "capture gain sensible?")
        return False, lines
    dev = s["offset_max_dev_samples"]
    rate = s["rate"]
    steady = (f"Offset steady to +-{dev:.2f} sample over {span}"
              if dev < 10 else f"Offset varies by +-{dev:.1f} samples over {span}")
    lines.append(f"{steady} (mean {s['offset_mean_samples']:.2f} samples = "
                 f"{s['offset_mean_ms']:.2f} ms; spread {s['offset_std_samples']:.3f} "
                 f"sample = {1e6 * s['offset_std_samples'] / rate:.1f} us, "
                 f"about {1000 * 343 * s['offset_std_samples'] / rate:.1f} mm of air).")
    if dev > 0.5:
        problems += 1
        lines.append("That is more than half a sample of jitter: a fixed "
                     "turnaround time cannot be better than this.")
    total_drift = abs(s["drift_samples_per_min"]) * s["duration_s"] / 60
    if s["duration_s"] >= 60 and total_drift > max(0.3, 3 * s["offset_std_samples"]):
        problems += 1
        lines.append(f"Drift: the offset moves {s['drift_samples_per_min']:+.2f} "
                     f"samples per minute ({s['drift_ppm']:+.1f} ppm), "
                     f"{total_drift:.1f} samples over the run.")
    elif s["duration_s"] >= 60:
        lines.append("No drift beyond the noise.")
    if s["xruns"] and any(s["xruns"].values()):
        counts = ", ".join(f"{n} {k}" for k, n in s["xruns"].items() if n)
        lines.append(f"Dropouts: {counts}; {s['in_xrun']} pings fall in or "
                     "next to one and were left out of the figures above.")
        problems += 1
    else:
        lines.append("No dropouts." + (
            f" ({s['startup_xruns']} flagged while the stream was starting; "
            "ignored.)" if s["startup_xruns"] else ""))
    if s["missed"]:
        lines.append(f"{s['missed']} of {s['pings']} pings were not found.")
        problems += 1
    if s.get("outliers"):
        lines.append(f"{s['outliers']} pings were found away from the main group "
                     "(an echo found when the direct sound was too weak, or noise "
                     "taken for a ping) and are left out of the figures above.")
    if s["stray"]:
        lines.append(f"{s['stray']} extra detections that belong to no ping "
                     "(noise, or an echo from the speaker side).")
    claimed = s["portaudio_claimed_offset_samples"]
    if claimed is not None:
        lines.append(f"PortAudio claimed {claimed:.1f} samples; measured "
                     f"{s['offset_mean_samples']:.1f}. Only the measured figure is used.")
    ratio = s["clock_ratio"]
    if ratio is not None:
        lines.append(f"Device clock against the system clock: "
                     f"{1e6 * (ratio - 1):+.1f} ppm.")
    if s["level_seen_dbfs"] is not None and s["level_seen_dbfs"] > -3:
        problems += 1
        lines.append(f"The loopback arrives at {s['level_seen_dbfs']:.0f} dBFS, "
                     "close to clipping the input. Lower the output level or "
                     "the capture gain.")
    elif s["level_seen_dbfs"] is not None and s["level_seen_dbfs"] < -60:
        lines.append(f"The ping arrives weak ({s['level_seen_dbfs']:.0f} dBFS); "
                     "timing is less exact and pings are missed. Raise the level "
                     "or the capture gain.")
    return problems == 0, lines


# -- schedule test ------------------------------------------------------------

@dataclass
class ReplyRow:
    k: int
    heard: float                 # input sample of the arrival that triggered it
    scheduled: int               # output sample the reply was scheduled at
    margin: int                  # samples between "now" and the schedule time
    arrival: float = float("nan")    # input sample of the reply's own arrival
    rounding: float = float("nan")   # scheduled - (heard + N), within +-0.5
    error: float = float("nan")      # (arrival - heard) - (N + mean offset), samples
    note: str = ""


def run_schedule_test(device, tat, pulses=40, level_db=-20.0, channel="left",
                      ping="chirp", progress=None, should_stop=lambda: False,
                      settle=SETTLE_S):
    """Chain `pulses` replies: each loopback arrival schedules the next
    pulse at arrival + N samples, N = tat * rate rounded.

    The first pulse is a seed at a known output sample; after a miss or a
    late schedule the chain is seeded again. Returns a TestResult.
    """
    rate = device.rate
    template = make_ping(rate, ping)
    gain = 10 ** (level_db / 20)
    n_tat = int(round(tat * rate))
    block = device.frames_per_buffer
    check = settle_and_check(device, settle)
    detector = ArrivalDetector(device, template)
    started = device.in_position
    rows = []
    seeds = 0
    late = 0
    lost = 0
    wall0 = time.monotonic()

    def seed():
        nonlocal seeds
        seeds += 1
        start = device.out_position + int(0.3 * rate)
        device.schedule(template, start, channel, gain)
        return start

    seed()
    pending = None                   # the ReplyRow waiting for its arrival
    waited_from = device.in_position
    give_up = device.in_position + int((pulses * (tat + 1.0) + 10) * rate)
    while (len(rows) < pulses and late + lost < 10 and
           device.in_position < give_up and not should_stop()):
        device.wait_input(device.in_position + block, timeout=5)
        arrivals = detector.poll()
        for arrival in arrivals:
            if pending is not None:
                pending.arrival = arrival.position
                rows.append(pending)
                if progress:
                    progress(len(rows), pulses)
                pending = None
            if len(rows) >= pulses:
                break
            wanted = arrival.position + n_tat
            start = int(round(wanted))
            now = device.out_position
            try:
                device.schedule(template, start, channel, gain)
            except LateError:
                late += 1
                pending = None
                seed()
                waited_from = device.in_position
                break
            pending = ReplyRow(len(rows), arrival.position, start, start - now,
                               rounding=start - wanted)
            waited_from = device.in_position
        if not arrivals and device.in_position - waited_from > int(1.5 * rate) + n_tat:
            lost += 1               # a pulse that never came back
            pending = None
            seed()
            waited_from = device.in_position
    return _schedule_result(device, rows, template, level_db, channel, tat,
                            n_tat, ping, seeds, late, lost,
                            time.monotonic() - wall0, started, check)


def _schedule_result(device, rows, template, level_db, channel, tat, n_tat,
                     ping, seeds, late, lost, wall_seconds, started, check=None):
    rate = device.rate
    # Turnaround as seen through the loopback: the reply's arrival minus the
    # arrival that triggered it, against N plus the device's own offset.
    offsets = [r.arrival - r.scheduled for r in rows]
    mean_offset = float(np.mean(offsets)) if offsets else 0.0
    for r in rows:
        r.error = (r.arrival - r.heard) - (n_tat + mean_offset)
    errors = spread([r.error for r in rows])
    rounding = spread([r.rounding for r in rows])
    jitter = spread(offsets)
    margins = [r.margin for r in rows]
    counts, events = _xruns_since(device, started)
    in_xrun = 0
    for r in rows:
        if device.xruns_between(int(r.heard), int(r.arrival) + len(template)):
            r.note = "xrun"
            in_xrun += 1
    clean = [r.error for r in rows if r.note != "xrun"]
    summary = dict(
        test="schedule", when=time.strftime("%Y-%m-%d %H:%M:%S"),
        device=device.describe(), ping=ping, level_dbfs=level_db,
        channel=channel, rate=rate, tat_s=tat, tat_samples=n_tat,
        replies=len(rows), seeds=seeds, late=late, lost=lost,
        in_xrun=in_xrun,
        offset_mean_samples=mean_offset, offset_std_samples=jitter["std"],
        error_mean_samples=errors["mean"], error_std_samples=errors["std"],
        error_max_abs_samples=float(np.max(np.abs(clean))) if clean else 0.0,
        error_max_abs_us=(1e6 * float(np.max(np.abs(clean))) / rate) if clean else 0.0,
        rounding_min=rounding["min"], rounding_max=rounding["max"],
        margin_min_samples=int(min(margins)) if margins else 0,
        margin_min_ms=1000 * min(margins) / rate if margins else 0.0,
        xruns=counts, startup_xruns=device.xrun_count - len(events),
        wall_s=wall_seconds, input_check=check or {},
        python=platform.python_version())
    summary["verdict_ok"], summary["verdict_lines"] = schedule_verdict(summary)
    return TestResult("schedule", rows, summary, summary["verdict_lines"])


def schedule_verdict(s):
    lines = ["Before the test: " + w
             for w in s.get("input_check", {}).get("warnings", [])]
    if s["replies"] < 3:
        lines.append(f"Only {s['replies']} replies landed ({s['late']} scheduled "
                     f"too late, {s['lost']} never heard). A turnaround of "
                     f"{s['tat_s'] * 1000:.0f} ms may be too short for this "
                     "machine, or the loopback is not heard.")
        return False, lines
    rate = s["rate"]
    worst = s["error_max_abs_samples"]
    lines.append(
        f"{s['replies']} replies at a turnaround of {s['tat_s'] * 1000:.0f} ms "
        f"({s['tat_samples']} samples) landed to within +-{worst:.2f} sample "
        f"({s['error_max_abs_us']:.0f} us, about "
        f"{1000 * 343 * worst / rate:.1f} mm of air); spread "
        f"{s['error_std_samples']:.3f} sample.")
    lines.append("Whole-sample start alone accounts for up to +-0.5 sample "
                 f"(seen: {s['rounding_min']:+.2f} to {s['rounding_max']:+.2f}).")
    lines.append(f"Reply offset through the device: {s['offset_mean_samples']:.2f} "
                 f"samples, spread {s['offset_std_samples']:.3f}. It should agree "
                 "with the offset test.")
    lines.append(f"Tightest decision margin: {s['margin_min_samples']} samples "
                 f"({s['margin_min_ms']:.1f} ms) between deciding and the output "
                 "reaching that sample.")
    dropouts = any(s["xruns"].values())
    ok = (worst <= 1.0 and not s["late"] and not s["lost"] and not dropouts
          and not s.get("input_check", {}).get("warnings"))
    if worst > 1.0:
        lines.append("Worse than one sample: something other than rounding "
                     "is adding jitter (scheduling latency, dropouts).")
    if s["late"]:
        lines.append(f"{s['late']} replies were decided too late and dropped; "
                     "use a longer turnaround or a smaller block.")
    if s["lost"]:
        lines.append(f"{s['lost']} pulses were never heard back.")
    if dropouts:
        lines.append(f"Dropouts during the test ({s['in_xrun']} replies "
                     "overlapped one); results are suspect.")
    if ok:
        lines.append("No late schedules, no dropouts.")
    return ok, lines


# -- saving -------------------------------------------------------------------

def save(result, runs_dir, label):
    """Write `<kind>.csv` and `summary.json` into a new folder
    `<runs_dir>/<date time>_<label>/` and return its path."""
    stamp = time.strftime("%Y%m%d_%H%M%S")
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in label)
    base = os.path.join(runs_dir, f"{stamp}_{safe}_{result.kind}")
    folder, n = base, 1
    while True:                 # two runs in the same second get _2, _3, ...
        try:
            os.makedirs(folder, exist_ok=False)
            break
        except FileExistsError:
            n += 1
            folder = f"{base}_{n}"
    rows = result.rows
    with open(os.path.join(folder, f"{result.kind}.csv"), "w", newline="") as handle:
        writer = csv.writer(handle)
        if result.kind == "offset":
            writer.writerow(["k", "scheduled_out_sample", "arrival_in_sample",
                             "offset_samples", "level_dbfs", "snr_db", "xrun",
                             "note"])
            for r in rows:
                writer.writerow([r.k, r.scheduled, _num(r.arrival, 4),
                                 _num(r.offset, 4), _num(r.level_dbfs, 1),
                                 _num(r.snr_db, 1), int(r.xrun), r.note])
        else:
            writer.writerow(["k", "heard_in_sample", "scheduled_out_sample",
                             "margin_samples", "arrival_in_sample",
                             "rounding_samples", "error_samples", "note"])
            for r in rows:
                writer.writerow([r.k, _num(r.heard, 4), r.scheduled, r.margin,
                                 _num(r.arrival, 4), _num(r.rounding, 4),
                                 _num(r.error, 4), r.note])
    with open(os.path.join(folder, "summary.json"), "w") as handle:
        json.dump(result.summary, handle, indent=2, default=_json_default)
    result.folder = folder
    return folder


def _num(value, digits):
    return "" if value != value else f"{value:.{digits}f}"


def _json_default(value):
    if isinstance(value, (np.floating, np.integer)):
        return value.item()
    if isinstance(value, np.bool_):
        return bool(value)
    return str(value)
