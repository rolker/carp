"""Sound paths between points: straight lines, flat reflecting planes, loss,
and rendering a sent signal as heard along those paths.

Pure functions; nothing here knows about scenes or files. Distances are in
metres, times in seconds, frequencies in Hz.

Step 1 has point sources and receivers (no directivity), one uniform medium
(travel time is length over sound speed), and spreading as 1/length. Rays
bend with ray tracing, later.
"""
import numpy as np
from scipy import fft as sfft

MIN_LENGTH = 0.01       # m; spreading loss is not allowed to blow up below this


def image_source(source, plane_point, plane_normal):
    """The mirror image of a source across a plane (all 3-vectors, m).

    The normal points into the side of the plane where the sound travels.
    Returns None if the source is behind the plane.
    """
    n = np.asarray(plane_normal, dtype=float)
    n = n / np.linalg.norm(n)
    p = np.asarray(source, dtype=float)
    height = float(np.dot(p - np.asarray(plane_point, dtype=float), n))
    if height <= 0:
        return None
    return p - 2.0 * height * n


def path_length(a, b):
    """Straight-line distance between two points, m."""
    return float(np.linalg.norm(np.asarray(a, dtype=float)
                                - np.asarray(b, dtype=float)))


def spreading_gain(length):
    """Amplitude factor for spherical spreading, relative to 1 m: 1 / length."""
    return 1.0 / max(length, MIN_LENGTH)


def absorption_db(frequency, length, db_per_m_per_khz2):
    """Absorption in dB over a path, with loss growing as frequency squared:
    db_per_m_per_khz2 * (f / 1 kHz)^2 * length. A stand-in until the
    propagation page brings real air and water absorption (ISO 9613-1,
    Francois-Garrison)."""
    return db_per_m_per_khz2 * (np.asarray(frequency) / 1e3) ** 2 * length


def render_length(n_out, max_delay, n_signal, rate, pad=2048):
    """Length of the working buffer for render_paths: the longest of the
    wanted output and (latest arrival + signal), plus `pad` samples of
    room at each end for filter ringing, rounded up to a fast even FFT size."""
    need = max(n_out, int(np.ceil(max_delay * rate)) + n_signal) + 2 * pad
    n = sfft.next_fast_len(need, real=True)
    if n % 2:
        n = sfft.next_fast_len(n + 1, real=True)
    return n


def render_paths(samples, rate, paths, n_out, pad=2048):
    """The sent signal as heard along several paths, summed.

    samples is what was sent (float, full-scale units) at `rate` Hz, its
    first sample at time 0. Each path is (delay, gain, absorption) with
    delay in seconds from time 0 to the arrival of the first sample (>= 0,
    any fraction of a sample), gain an amplitude factor (negative for a
    polarity flip) and absorption in dB per kHz^2 of frequency for this
    path (its length already included, see absorption_db).

    The delay is a phase ramp on the spectrum, so it is exact to any
    fraction of a sample, with no interpolation kernel to truncate. A
    spectrum delay is circular, so the work is done in a buffer with `pad`
    samples of room after the latest arrival and before the earliest, then
    cut to n_out samples. Returns float64 of length n_out, in which sample k
    is time k / rate.
    """
    samples = np.asarray(samples, dtype=np.float64)
    delays = [p[0] for p in paths]
    if not paths:
        return np.zeros(n_out)
    if min(delays) < 0:
        raise ValueError("a path cannot arrive before the signal is sent")
    n = render_length(n_out, max(delays), samples.size, rate, pad)
    freqs = sfft.rfftfreq(n, 1.0 / rate)
    spectrum = sfft.rfft(samples, n)
    total = np.zeros(freqs.size, dtype=complex)
    for delay, gain, absorb in paths:
        h = gain * np.exp(-2j * np.pi * freqs * delay)
        if absorb:
            h = h * 10.0 ** (-absorption_db(freqs, 1.0, absorb) / 20.0)
        total += spectrum * h
    # The Nyquist bin of a real signal is real; a delay turns it into
    # X cos(pi d), which is what dropping the imaginary part gives.
    total[-1] = total[-1].real
    return sfft.irfft(total, n)[:n_out]
