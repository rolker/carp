"""Room sonar: ping a room from a speaker near a microphone and read the
returns against range.

An in-air sonar from whatever the computer has. Time zero of every ping is
the direct sound from speaker to microphone, found in that ping's own
recording, so output and input need not share a clock (different cards, the
shared mode) and the unknown output-to-input delay of the device does not
matter. An echo that arrives `t` after the direct sound has travelled
`c * t` further than the direct path, so with the speaker-to-microphone
distance `d` known its range, taking speaker and microphone as one place, is

    range = (c * t + d) / 2.

Nothing here draws anything or opens a device.
"""
from dataclasses import dataclass, field

import numpy as np

from ..backends.base import Emission, Ping
from ..models import detection, media
from ..models.detection_design import DEFAULT
from ..objects import signals as signal_objects
from ..objects.schema import WorkspaceError
from . import ranging

FLOOR_DB = -80.0                 # levels are shown down to here, relative to the direct sound
MARGIN_S = 0.002                 # extra listening beyond the range asked for
DEFAULT_MAX_RANGE_M = 5.0
LISTEN_NOTE = ("The listening time is set by the range asked for: an echo from "
               "R metres arrives (2R - d)/c after the direct sound.")


def separation(layout, output, input_):
    """Distance between two transducers of a layout, m; 0.0 if either is not
    there."""
    if not layout:
        return 0.0
    pos = {t["id"]: np.asarray(t["position"], dtype=float) for t in layout["transducers"]}
    if output not in pos or input_ not in pos:
        return 0.0
    return float(np.linalg.norm(pos[output] - pos[input_]))


def listen_for(max_range_m, speed, baseline_m=0.0):
    """Seconds to keep recording after the sound, for echoes from
    `max_range_m`."""
    return max((2.0 * max_range_m - baseline_m) / speed, 0.0) + MARGIN_S


def build_ping(workspace, design_id, output, input_, infos, max_range_m,
               speed, baseline_m=0.0):
    """A backend Ping for the room sonar: the ping design's first event, sent
    from `output`, heard on `input_`, listening long enough for
    `max_range_m`. Raises ValueError with a message a person can act on."""
    design = workspace.get("ping_designs", design_id)
    if design is None:
        raise ValueError("no ping design is selected")
    if not design["events"]:
        raise ValueError(f"ping design '{design['name']}' has no events")
    info = {t.id: t for t in infos}
    if output not in info or not info[output].can_send:
        raise ValueError(f"'{output}' cannot send with this backend and scene")
    if input_ not in info or not info[input_].can_receive:
        raise ValueError(f"'{input_}' cannot receive with this backend and scene")
    event = design["events"][0]
    rate = info[output].rate
    try:
        samples = signal_objects.samples(workspace.get_signal, event["signal"], rate)
        f0, f1, duration = signal_objects.band(workspace.get_signal, event["signal"])
        amplitude = signal_objects.level(workspace.get_signal, event["signal"])
    except WorkspaceError as error:
        raise ValueError(str(error)) from None
    spec = dict(name=workspace.name_of("signals", event["signal"]), f0=f0, f1=f1,
                duration=duration, amplitude=amplitude)
    return Ping(
        emissions=[Emission(transducer=output, samples=samples, start=0.0, rate=rate,
                            signal=event["signal"])],
        receivers=[input_], listen=listen_for(max_range_m, speed, baseline_m),
        meta=dict(design_id=design_id, design_name=design["name"],
                  detection_design=design.get("detection_design"),
                  signals={event["signal"]: spec}, room=True,
                  max_range_m=max_range_m, output=output, input=input_))


def numbers(spec, speed, rate, baseline_m, max_range_m, ping_interval_s,
            measure="first_null"):
    """What the ping design and the settings make of the room sonar, as a
    dict of plain numbers: range resolution (read off the signal's own
    matched-filter peak by `measure`, the detection design's resolution
    setting), range bin, listening time, the unambiguous range of the ping
    rate. `spec` is the signal's f0, f1, duration and, optionally, taper or
    its samples ("template")."""
    f0, f1, duration = spec["f0"], spec["f1"], spec["duration"]
    bandwidth = abs(f1 - f0)
    resolution_s = (detection.resolution(f0, f1, duration,
                                         spec.get("template_rate", rate),
                                         spec.get("taper", 1.0), measure,
                                         spec.get("template"))
                    if bandwidth > 0 else duration)
    return dict(
        bandwidth_hz=bandwidth, duration_s=duration,
        resolution_s=resolution_s, resolution_m=speed * resolution_s / 2.0,
        resolution_measure=measure,
        bin_m=speed / (2.0 * rate), listen_s=listen_for(max_range_m, speed, baseline_m),
        max_range_m=max_range_m,
        pulse_m=speed * duration / 2.0,
        ambiguity_m=(speed * ping_interval_s / 2.0) if ping_interval_s else None,
        wavelength_mm=1e3 * media.wavelength(speed, max((f0 + f1) / 2.0, 1.0)),
        baseline_m=baseline_m)


@dataclass
class RoomPing:
    """One ping read as a return against range."""
    output: str
    input: str
    range_m: np.ndarray = field(default_factory=lambda: np.zeros(0))
    level: np.ndarray = field(default_factory=lambda: np.zeros(0))   # envelope / direct peak
    heard: bool = False                  # the direct sound was found
    direct_sample: float = float("nan")  # where, in the recording (sub-sample)
    direct_dbfs: float = float("nan")    # its level, dB re full scale
    direct_snr: float = float("nan")
    noise_db: float = float("nan")       # typical (median) level, dB re the direct sound
    sound_speed: float = 343.2
    baseline_m: float = 0.0
    design: detection.DetectionDesign = DEFAULT
    design_id: str = ""
    warnings: list = field(default_factory=list)
    truth: list = field(default_factory=list)     # simulation: (route name, range m)

    @property
    def level_db(self):
        return to_db(self.level)


def to_db(level, floor=FLOOR_DB):
    """Linear level (re the direct sound) as dB, never below `floor`."""
    return np.maximum(20 * np.log10(np.maximum(np.asarray(level, dtype=float), 1e-12)), floor)


def analyse(capture, output, input_, design=DEFAULT, design_id="",
            max_range_m=DEFAULT_MAX_RANGE_M, baseline_m=None):
    """Read one capture as a RoomPing: find the direct sound in the `input_`
    recording (the strongest peak, moved back to the first peak that is at
    least the design's first-arrival fraction of it), call it time zero, and
    give the matched-filter output against range up to `max_range_m`.

    The grid is one sample of travel (c / 2 / rate, 3.6 mm at 48 kHz in air)
    per bin, so every ping has the same bins however its direct sound fell
    between samples; values between samples are interpolated.
    """
    recording = capture.recordings[input_]
    ping = capture.ping
    rate = recording.rate
    speed = capture.meta.get("sound_speed") or ranging.DEFAULT_SOUND_SPEED
    if baseline_m is None:
        baseline_m = separation(capture.meta.get("layout"), output, input_)
    result = RoomPing(output=output, input=input_, sound_speed=speed,
                      baseline_m=baseline_m, design=design, design_id=design_id)
    emission = next((e for e in ping.emissions if e.transducer == output), None)
    if emission is None:
        result.warnings.append(f"the ping has no signal from '{output}'")
        return result
    template = ranging._template(emission, rate)
    samples = np.asarray(recording.samples, dtype=np.float64)
    if samples.size < template.size + 16:
        result.warnings.append("the recording is too short")
        return result
    analytic, env = detection.correlation(samples, template, design.method)
    noise = detection.noise_level(env, template, unit=1.0)
    strongest = int(np.argmax(env))
    if env[strongest] < design.hit_snr * noise:
        result.warnings.append(
            "the direct sound from the speaker was not found above the noise "
            f"(strongest peak {env[strongest] / noise:.1f} x the typical level, the "
            f"detection design wants {design.hit_snr:g}): is the output on, loud enough, "
            "and the right input chosen?")
        return result
    first = detection.leading(env, strongest, template.size, design.hit_snr * noise,
                              design.first_fraction)
    position = detection.refine(analytic, first, design)
    peak = float(np.interp(position, np.arange(env.size), env))
    result.heard = True
    result.direct_sample = position
    result.direct_dbfs = detection.level_dbfs(peak, template, design.method, unit=1.0)
    result.direct_snr = peak / noise
    result.noise_db = float(20 * np.log10(noise / peak))
    if output in recording.loopback_of:
        result.warnings.append(
            f"this input carries an electrical loopback of '{output}': time zero is the "
            "first arrival, which is then the loopback and not the sound through the air")
    if np.max(np.abs(samples)) >= 0.999:
        result.warnings.append("the input reaches full scale: it is clipping, which "
                               "blunts the direct sound and shifts every echo")

    bins = int(max_range_m / (speed / (2.0 * rate)))
    result.range_m = np.arange(bins) * speed / (2.0 * rate)
    delay_s = (2.0 * result.range_m - baseline_m) / speed
    at = position + delay_s * rate
    inside = (at >= 0) & (at <= env.size - 1)
    level = np.zeros(bins)
    level[inside] = np.interp(at[inside], np.arange(env.size), env) / peak
    result.level = level
    if np.any(~inside & (at > 0)):
        result.warnings.append(
            f"the recording ends before {max_range_m:g} m: the ranges beyond "
            f"{result.range_m[inside].max():.2f} m are blank")
    truth = getattr(capture, "truth", None)
    if truth:
        direct = [p for p in truth["paths"] if p["receiver"] == input_
                  and p["emitter"] == output and p["route"] == "direct"]
        if direct:
            for p in truth["paths"]:
                if p["receiver"] == input_ and p["emitter"] == output \
                        and p["route"] not in ("direct", "loopback"):
                    t = p["arrival_s"] - direct[0]["arrival_s"]
                    result.truth.append((p["route"], (speed * t + baseline_m) / 2.0))
    return result


def background(history, memory):
    """Mean level of the last `memory` pings in `history` (a list of level
    arrays of one length), or None if there are none."""
    recent = [h for h in history[-memory:] if h is not None and h.size]
    if not recent:
        return None
    n = recent[-1].size
    recent = [h for h in recent if h.size == n]
    return np.mean(recent, axis=0)


def difference(level, mean):
    """What changed since the background: |level - background|, same units
    (envelope re the direct sound). Zeros when there is no background yet."""
    if mean is None or mean.size != level.size:
        return np.zeros_like(level)
    return np.abs(level - mean)
