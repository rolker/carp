"""Small builders shared by the tests."""
import numpy as np
from scipy import signal

from acoustics_lab.models import channel, detection
from acoustics_lab.models.signals import make_chirp

RATE = 48000


def event(key, f0, f1, duration, time, rate=RATE):
    """An EventSpec for a chirp."""
    return detection.EventSpec(
        label=f"{key} @ {time * 1e3:g} ms", key=key,
        template=make_chirp(rate, f0, f1, duration), time=time)


def recording(sounds, noise=0.01, lead_in=0.1, tail=0.2, seed=0, rate=RATE):
    """A mono recording. sounds is a list of (event, [(delay, gain), ...]):
    each event is heard once per (delay, gain), delays in seconds after it
    was sent. Delays need not fall on whole samples."""
    end = max(e.time + max(d for d, _ in paths) + e.template.size / rate
              for e, paths in sounds)
    n = int(round((lead_in + end + tail) * rate))
    out = np.random.default_rng(seed).normal(0.0, noise, n)
    for e, paths in sounds:
        out += channel.render_paths(
            e.template, rate, [(lead_in + e.time + d, g, 0.0) for d, g in paths], n)
    return out


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
    return noise + rumble + whine + burst
