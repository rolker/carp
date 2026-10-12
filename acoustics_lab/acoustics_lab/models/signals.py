"""Waveforms to send: chirps, tones, and simple things done to them.

Arrays in, arrays out. Sample values are in full-scale units (1.0 is the
largest value the output can carry).
"""
import numpy as np
from scipy import signal


def make_chirp(rate, f0, f1, duration, taper=1.0):
    """Linear sweep from f0 to f1 Hz, peak 1.0, with tapered ends.

    rate is the sample rate in Hz, duration is in seconds. Equal f0 and f1
    make a tone. taper is the fraction of the length that is faded, split
    between both ends. The default fades the whole chirp (a Hann window):
    correlation sidelobes drop to about -46 dB, against -14 dB at 0.25, so a
    sidelobe is not mistaken for an arrival. The cost is a main lobe about
    three times wider.
    """
    if max(f0, f1) > 0.45 * rate:
        raise ValueError(
            f"{max(f0, f1):.0f} Hz is too high for a {rate} Hz sample rate")
    if min(f0, f1) < 0 or duration <= 0:
        raise ValueError("frequencies cannot be negative and the length "
                         "must be above zero")
    n = int(round(duration * rate))
    t = np.arange(n) / rate
    sweep = signal.chirp(t, f0, duration, f1, method="linear")
    return sweep * signal.windows.tukey(n, taper)


def time_reverse(samples):
    """The signal played backwards. The reverse of an up-chirp is a
    down-chirp over the same band."""
    return np.asarray(samples)[::-1].copy()


def invert(samples):
    """The signal with its sign flipped (a half-cycle phase shift)."""
    return -np.asarray(samples)


def bandwidth(f0, f1):
    """Width of the swept band in Hz."""
    return abs(f1 - f0)


def processing_gain_db(f0, f1, duration):
    """Gain of the matched filter against white noise, dB:
    10 log10(duration x bandwidth). A tapered signal gets a little less."""
    return 10 * np.log10(max(duration * bandwidth(f0, f1), 1.0))
