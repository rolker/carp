"""Chirp generation and arrival-time estimation for the acoustic ranging tests.

No audio hardware here: everything works on arrays, so it runs the same on a
live recording, a WAV file or a simulated signal. See docs/navigation.md,
Method 4.
"""
from dataclasses import dataclass

import numpy as np
from scipy import signal


def sound_speed_air(temperature_c=20.0):
    """Speed of sound in dry air, m/s."""
    return 331.3 * np.sqrt(1.0 + temperature_c / 273.15)


def make_chirp(rate, f0, f1, duration, taper=1.0):
    """Linear sweep from f0 to f1 Hz, peak 1.0, with tapered ends.

    taper is the fraction of the length that is faded, split between both
    ends. The default fades the whole chirp (a Hann window): correlation
    sidelobes drop to about -46 dB, against -14 dB at 0.25, so a sidelobe
    is not mistaken for an arrival. The cost is a main lobe about three
    times wider.
    """
    if max(f0, f1) > 0.45 * rate:
        raise ValueError(
            f"{max(f0, f1):.0f} Hz is too high for a {rate} Hz sample rate")
    n = int(round(duration * rate))
    t = np.arange(n) / rate
    sweep = signal.chirp(t, f0, duration, f1, method="linear")
    return (sweep * signal.windows.tukey(n, taper)).astype(np.float32)


def matched_filter(recording, chirp):
    """Envelope of the recording correlated against the chirp.

    Index i of the result is the chirp starting at sample i of the recording.
    """
    recording = np.asarray(recording, dtype=np.float64)
    recording = recording - recording.mean()
    correlation = signal.correlate(recording, chirp, mode="valid", method="fft")
    return np.abs(signal.hilbert(correlation))


def resolution(f0, f1):
    """Rough spacing, in seconds, below which two arrivals merge into one.

    About 3 / bandwidth for the default fully tapered chirp.
    """
    return 3.0 / abs(f1 - f0)


@dataclass
class Arrival:
    sample: float    # start of the chirp in the recording, sub-sample
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


def simulate_recording(chirp, rate, delays, gains, noise=0.01, lead_in=0.1,
                       tail=0.2, seed=0):
    """Mono recording with a copy of the chirp at each delay (seconds).

    The first delay stands in for the electrical loopback copy, later ones
    for acoustic arrivals. Delays need not fall on whole samples.
    """
    rng = np.random.default_rng(seed)
    n = int(round((lead_in + max(delays) + tail) * rate)) + chirp.size
    recording = rng.normal(0.0, noise, n)
    spectrum = np.fft.rfft(chirp, n)
    freqs = np.fft.rfftfreq(n, 1.0 / rate)
    for delay, gain in zip(delays, gains):
        shift = np.exp(-2j * np.pi * freqs * (lead_in + delay))
        recording += gain * np.fft.irfft(spectrum * shift, n)
    return recording.astype(np.float32)


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


def simulate_noise(rate, seconds, seed=0):
    """Made-up background noise: hiss, low rumble, a steady 17 kHz whine
    and one short broadband burst."""
    rng = np.random.default_rng(seed)
    n = int(seconds * rate)
    t = np.arange(n) / rate
    noise = rng.normal(0.0, 0.003, n)
    low = signal.butter(2, 300.0, btype="low", fs=rate, output="sos")
    rumble = signal.sosfilt(low, rng.normal(0.0, 0.1, n))
    whine = 0.002 * np.sin(2 * np.pi * 17000.0 * t) if rate > 40000 else 0.0
    burst = np.zeros(n)
    at = n // 2
    burst[at:at + int(0.05 * rate)] = rng.normal(0.0, 0.03, min(int(0.05 * rate), n - at))
    return (noise + rumble + whine + burst).astype(np.float32)
