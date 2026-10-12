"""Saved captures: a WAV file with a JSON file beside it (p_0001.wav.json).

The format is the one carp/acoustic wrote (ping_gui.save_ping), so old runs
open, and the one this tool writes. Three sidecars are understood:

- ping_gui: `setup` (rate, listen, sound_speed) and `design` (signals with
  f0, f1, duration, amplitude; events with channel, signal, time).
- loopback_test: rate, f0, f1, duration, amplitude, channel, sound_speed.
  Its first arrival is the loopback copy, so the channels are listed as
  loopbacks.
- this tool's, which is the ping_gui one plus an `acoustics_lab` entry with
  the receiver, loopbacks and clock.

A WAV with no sidecar cannot be used: what was sent is not known.

Limit: a signal is rebuilt from its band, length and level, so a signal that
was derived by time reversal comes back as the down-chirp of the same band,
the same sound up to a constant phase. The matched filter's envelope does not
care.
"""
import datetime
from pathlib import Path

import numpy as np

from . import wav_io
from .backends.base import Capture, Emission, Ping, Recording
from .models.signals import make_chirp

RECEIVER = "mic"        # old recordings have one input
CLOCK = "replay"


def find_recordings(path):
    """WAV files at a path: the file itself, or all under a folder, in order."""
    path = Path(path)
    if path.is_dir():
        return sorted(path.rglob("*.wav"))
    return [path] if path.exists() else []


def _chirp(rate, spec):
    return spec.get("amplitude", 0.5) * make_chirp(
        rate, spec["f0"], spec["f1"], spec["duration"], spec.get("taper", 1.0))


def load_capture(wav_path):
    """A saved recording as a Capture. Raises ValueError with a plain
    message if it cannot be used."""
    wav_path = str(wav_path)
    samples, rate = wav_io.read_wav(wav_path)
    meta = wav_io.read_meta(wav_path)
    if not meta:
        raise ValueError(f"{Path(wav_path).name} has no .json file beside it, "
                         "so what was sent is not known")
    loopback_of, extra = [], meta.get("acoustics_lab", {})
    if "design" in meta:
        setup, design = meta.get("setup", {}), meta["design"]
        rate = setup.get("rate", rate)
        listen = setup.get("listen", 0.3)
        speed = setup.get("sound_speed")
        specs = {s["name"]: s for s in design["signals"]}
        events = [(e["channel"], e["signal"], e["time"]) for e in design["events"]]
        loopback_of = list(extra.get("loopback_of", []))
    elif "f0" in meta:
        rate = meta.get("rate", rate)
        listen, speed = 0.3, meta.get("sound_speed")
        specs = {"chirp": dict(meta)}
        channels = {"left": ["left"], "right": ["right"],
                    "both": ["left", "right"]}.get(meta.get("channel", "left"), ["left"])
        events = [(c, "chirp", 0.0) for c in channels]
        loopback_of = list(channels)
    else:
        raise ValueError(f"{Path(wav_path).name}: the .json file does not "
                         "describe a ping")
    try:
        emissions = [Emission(transducer=c, samples=_chirp(rate, specs[s]), start=t,
                              rate=rate, signal=s) for c, s, t in events]
    except KeyError as missing:
        raise ValueError(f"{Path(wav_path).name}: no signal named {missing}") from None
    receiver = extra.get("receiver", RECEIVER)
    ping_meta = dict(extra.get("ping") or {})       # design ID and name, as made
    ping_meta["signals"] = specs
    ping = Ping(emissions=emissions, receivers=[receiver], listen=listen,
                meta=ping_meta)
    recording = Recording(samples=samples.astype(np.float64), rate=rate,
                          clock=extra.get("clock", CLOCK),
                          started=extra.get("started", 0.0), loopback_of=loopback_of)
    return Capture(
        recordings={receiver: recording}, emitted={}, truth=None,
        meta=dict(backend="replay", source=wav_path, sound_speed=speed,
                  recorded=meta.get("time"), original=meta,
                  layout=extra.get("layout"),
                  recorded_with=extra.get("detection_design")),
        ping=ping)


def save_capture(folder, number, capture, receiver=None):
    """Save one receiver's recording of a capture, with the ping that made
    it, in the format above. Returns the WAV path. The sidecar holds copies
    of the signals' settings (and, for a simulation, of the scene), so a
    recording can always be traced to what produced it."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    receiver = receiver or sorted(capture.recordings)[0]
    recording = capture.recordings[receiver]
    suffix = "" if len(capture.recordings) == 1 else f"_{receiver}"
    path = folder / f"p_{number:04d}{suffix}.wav"
    wav_io.write_wav(str(path), recording.samples, int(recording.rate))
    specs = capture.ping.meta.get("signals", {}) if capture.ping else {}
    names = {sid: spec.get("name", sid) for sid, spec in specs.items()}
    design = dict(
        signals=[dict(name=spec.get("name", sid), f0=spec["f0"], f1=spec["f1"],
                      duration=spec["duration"], amplitude=spec["amplitude"])
                 for sid, spec in specs.items()],
        events=[dict(channel=e.transducer, signal=names.get(e.signal, e.signal),
                     time=e.start) for e in capture.ping.emissions])
    wav_io.write_meta(str(path), dict(
        time=datetime.datetime.now().astimezone().isoformat(),
        setup=dict(rate=recording.rate, listen=capture.ping.listen,
                   sound_speed=capture.meta.get("sound_speed")),
        design=design,
        acoustics_lab=dict(receiver=receiver, clock=recording.clock,
                           started=recording.started,
                           loopback_of=recording.loopback_of,
                           backend=capture.meta.get("backend"),
                           scene=capture.meta.get("scene"),
                           layout=capture.meta.get("layout"),
                           rig=capture.meta.get("rig"),
                           devices=capture.meta.get("devices"),
                           warnings=capture.meta.get("warnings"),
                           detection_design=capture.meta.get("detection_design"),
                           ping=capture.meta.get("ping"))))
    return str(path)
