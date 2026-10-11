"""16-bit WAV files for the acoustic ranging tests, each with an optional
JSON file beside it (run1.wav.json) describing the chirp that was sent.
Stdlib and numpy only.
"""
import json
import os
import wave

import numpy as np

def write_wav(path, recording, rate):
    """Save a mono float recording as 16-bit WAV."""
    data = (np.clip(recording, -1.0, 1.0) * 32767).astype("<i2")
    with wave.open(path, "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(rate)
        f.writeframes(data.tobytes())


def read_wav(path):
    """Read a 16-bit WAV. Returns (first channel as float32, sample rate)."""
    with wave.open(path, "rb") as f:
        if f.getsampwidth() != 2:
            raise ValueError(f"{path}: only 16-bit WAV is supported")
        data = np.frombuffer(f.readframes(f.getnframes()), dtype="<i2")
        data = data.reshape(-1, f.getnchannels())[:, 0]
        return data.astype(np.float32) / 32768.0, f.getframerate()


def write_meta(path, meta):
    """Save the settings for a recording next to it, as <path>.json."""
    with open(path + ".json", "w") as f:
        json.dump(meta, f, indent=1)
        f.write("\n")


def read_meta(path):
    """Settings saved beside a recording, or {} if there are none."""
    if not os.path.exists(path + ".json"):
        return {}
    with open(path + ".json") as f:
        return json.load(f)
