"""The simulation backend: a ping is rendered from a scene.

A scene holds a layout (point transducers), one medium, flat reflecting
planes, point reflectors (fixed, or moving back and forth between two points
at a set speed), noise, and the simulated rig: which transducers share a device, each
device's sample rate and clock, and which inputs carry an electrical
loopback of which outputs. The recording a receiver gets has the same
structure as hardware gives, so processing sees no difference.

How a recording is built (see docs/design.md, Scene):
- Every path (direct, and one image source per reflecting plane) is rendered
  in the frequency domain, so its delay is exact to any fraction of a
  sample (models/channel.py has the padding rules).
- Clocks are part of the delay. A sender's emission time goes through its
  device's clock and an arrival time through the receiver's: a device's local
  time is (true time - start_delay) * (1 + drift). What this leaves out is
  the stretching of a signal by drift during its own duration; it is stated
  in `truth` ("unmodelled_stretch_s") rather than hidden.
- Times are float64 throughout. No global delay is added and no filtering is
  applied: the truth matches the recording.

A point reflector is a target of "strength": the path emitter - target -
receiver is rendered like any other, with spreading over its whole length and
the strength as the reflection factor. A mover's place depends on when the
ping is made: ping n of a run is at time n * `period_s` (the ping's own meta,
set by a page that pings at a rate; 0.1 s if it is not), however fast the
simulation is run, so the target moves as it would at that rate. Its place
during one ping is not followed (no Doppler, no stretching: design.md, Scene,
"Motion (later)"); `truth` says where each mover was.

Time zero of a recording is the start of its buffer. Each emission leaves
`lead_in` seconds after that, plus its own start time, so there is silence
before the first one.
"""
import copy
import datetime
from fractions import Fraction

import numpy as np
from scipy import fft as sfft
from scipy import signal

from ..models import channel, media
from .base import Backend, Cancelled, Capture, Recording, TransducerInfo, never_cancel, no_progress


def sound_speed(medium):
    """Sound speed in m/s for a scene's medium dict."""
    if medium.get("type") == "air":
        return float(media.sound_speed_air(medium["temperature_c"]))
    raise ValueError(f"medium type {medium.get('type')!r} is not simulated yet "
                     "(water comes with the sound speed page)")


def noise_samples(rng, n, rms, slope_db_per_octave=0.0):
    """Gaussian noise, n samples, with the given rms (full-scale units).
    slope 0 is white; -3 dB per octave is pink; the power falls (or rises)
    with frequency by that much per doubling."""
    white = rng.normal(0.0, 1.0, n)
    if slope_db_per_octave:
        spectrum = sfft.rfft(white)
        f = np.maximum(sfft.rfftfreq(n), 1.0 / n)       # keep DC finite
        spectrum *= (f / f[1]) ** (slope_db_per_octave / 6.0206)
        white = sfft.irfft(spectrum, n)
    return rms * white / max(float(np.std(white)), 1e-30)


DEFAULT_PERIOD_S = 0.1      # time between pings of a run, if the ping does not say


def mover_position(mover, clock):
    """Where a mover is at `clock` seconds: it walks from `a` to `b` and back
    again at `speed` m/s, starting at `a`."""
    a = np.asarray(mover["a"], dtype=float)
    b = np.asarray(mover["b"], dtype=float)
    length = float(np.linalg.norm(b - a))
    if length == 0 or mover.get("speed", 0.0) <= 0:
        return a
    along = (mover["speed"] * clock) % (2 * length)
    if along > length:
        along = 2 * length - along
    return a + (b - a) * (along / length)


def _resample(samples, from_rate, to_rate):
    if from_rate == to_rate:
        return np.asarray(samples, dtype=np.float64)
    ratio = Fraction(to_rate / from_rate).limit_denominator(1000)
    return signal.resample_poly(samples, ratio.numerator, ratio.denominator)


class SimulationBackend(Backend):
    name = "Simulation"
    realtime = False

    def __init__(self, scene, layout, scene_id=""):
        self.scene, self.layout, self.scene_id = scene, layout, scene_id
        self.count = 0              # pings made, so each gets different noise
        self._position = {t["id"]: np.array(t["position"], dtype=float)
                          for t in layout["transducers"]}
        self._info = {t["id"]: t for t in layout["transducers"]}
        self._device = {}
        for device in scene["devices"]:
            for tid in device["transducers"]:
                if tid not in self._info:
                    raise ValueError(f"device {device['id']!r}: the layout has "
                                     f"no transducer {tid!r}")
                self._device[tid] = device
        for lb in scene.get("loopbacks", []):
            rd, ed = self._device.get(lb["receiver"]), self._device.get(lb["emitter"])
            if rd is None or ed is None or rd is not ed:
                raise ValueError("a loopback needs its input and output on "
                                 f"the same device ({lb['emitter']} -> {lb['receiver']})")

    @classmethod
    def from_workspace(cls, workspace, scene_id):
        scene = workspace.get("scenes", scene_id)
        if scene is None:
            raise ValueError(f"no scene with ID {scene_id!r}")
        layout = workspace.get("layouts", scene["layout"])
        return cls(scene, layout, scene_id)

    # ---- the interface -------------------------------------------------

    def transducers(self):
        return [TransducerInfo(
            id=t["id"], name=t.get("name", t["id"]),
            can_send=t.get("can_send", False),
            can_receive=t.get("can_receive", False),
            rate=self._device[t["id"]]["rate"] if t["id"] in self._device else 0.0)
            for t in self.layout["transducers"]]

    def sound_speed(self):
        return sound_speed(self.scene["medium"])

    def _started(self, device):
        """The device clock's reading when its buffer starts, s."""
        drift = device.get("clock_drift_ppm", 0.0) * 1e-6
        return device.get("clock_offset", 0.0) + device.get("start_delay", 0.0) * (1 + drift)

    def fire(self, ping, progress=no_progress, cancel=never_cancel):
        scene, c = self.scene, self.sound_speed()
        lead_in = scene.get("lead_in", 0.1)
        for e in ping.emissions:
            info = self._info.get(e.transducer)
            if info is None or not info.get("can_send") or e.transducer not in self._device:
                raise ValueError(f"{e.transducer!r} cannot send in this scene")
        for rid in ping.receivers:
            info = self._info.get(rid)
            if info is None or not info.get("can_receive") or rid not in self._device:
                raise ValueError(f"{rid!r} cannot receive in this scene")
        if not ping.emissions:
            raise ValueError("the ping has no emissions")

        index = self.count
        self.count += 1
        clock = index * float(ping.meta.get("period_s", DEFAULT_PERIOD_S))
        last_end = max(e.start + e.samples.size / e.rate for e in ping.emissions)
        link_gain = scene.get("link_gain", 1.0)
        alpha = scene["medium"].get("absorption_db_per_m_per_khz2", 0.0)
        noise = scene.get("noise", {})
        recordings, paths_truth, stretch = {}, [], {}

        for r, rid in enumerate(ping.receivers):
            progress(r / len(ping.receivers), f"rendering {rid}")
            rdev = self._device[rid]
            rate = float(rdev["rate"])
            drift_r = rdev.get("clock_drift_ppm", 0.0) * 1e-6
            n_out = int(np.ceil((lead_in + last_end + ping.listen) * rate))
            out = np.zeros(n_out)
            for ei, e in enumerate(ping.emissions):
                if cancel():
                    raise Cancelled()
                sdev = self._device[e.transducer]
                drift_t = sdev.get("clock_drift_ppm", 0.0) * 1e-6
                x = _resample(e.samples, e.rate, rate)
                # True time (s since the ping began) of the first sample leaving.
                sent = sdev.get("start_delay", 0.0) + (lead_in + e.start) / (1 + drift_t)
                to_local = lambda true: (true - rdev.get("start_delay", 0.0)) * (1 + drift_r)
                routes = self._routes(e.transducer, rid, clock)
                paths = []
                for route, length, factor, history in routes:
                    local = to_local(sent + length / c)
                    gain = link_gain * channel.spreading_gain(length) * factor
                    paths.append((local, gain, alpha * length))
                    paths_truth.append(dict(
                        emission=ei, emitter=e.transducer, receiver=rid,
                        route=route, length_m=length, travel_s=length / c,
                        arrival_s=local, arrival_sample=local * rate,
                        gain=gain, reflections=history))
                for lb in scene.get("loopbacks", []):
                    if lb["receiver"] == rid and lb["emitter"] == e.transducer:
                        local = to_local(sent)
                        paths.append((local, lb["gain"], 0.0))
                        paths_truth.append(dict(
                            emission=ei, emitter=e.transducer, receiver=rid,
                            route="loopback", length_m=0.0, travel_s=0.0,
                            arrival_s=local, arrival_sample=local * rate,
                            gain=lb["gain"], reflections=[]))
                if min(p[0] for p in paths) < 0:
                    raise ValueError(f"{rid}: the signal from {e.transducer} "
                                     "arrives before the recording starts")
                out += channel.render_paths(x, rate, paths, n_out)
                stretch[ei] = x.size / rate * abs(drift_r - drift_t)
            if noise.get("rms", 0.0) > 0:
                rng = np.random.default_rng(
                    [noise.get("seed", 0), index, r])
                out += noise_samples(rng, n_out, noise["rms"],
                                     noise.get("slope_db_per_octave", 0.0))
            loopback_of = sorted({lb["emitter"] for lb in scene.get("loopbacks", [])
                                  if lb["receiver"] == rid})
            recordings[rid] = Recording(
                samples=out, rate=rate, clock=rdev["id"],
                started=self._started(rdev), loopback_of=loopback_of)
        progress(1.0, "done")

        emitted = {}
        for e in ping.emissions:
            emitted.setdefault(e.transducer, self._started(self._device[e.transducer])
                               + lead_in + e.start)
        truth = dict(paths=paths_truth, sound_speed=c, lead_in=lead_in,
                     unmodelled_stretch_s=stretch, time_s=clock,
                     movers={m["name"]: [float(v) for v in mover_position(m, clock)]
                             for m in self.scene.get("movers", [])})
        meta = dict(
            backend=self.name, scene_id=self.scene_id, scene_name=self.scene.get("name", ""),
            sound_speed=c, ping_index=index, lead_in=lead_in,
            time=datetime.datetime.now().astimezone().isoformat(),
            scene=copy.deepcopy(self.scene), layout=copy.deepcopy(self.layout),
            ping=copy.deepcopy(ping.meta))
        return Capture(recordings=recordings, emitted=emitted, truth=truth,
                       meta=meta, ping=ping)

    # ---- paths ---------------------------------------------------------

    def _routes(self, emitter, receiver, clock=0.0):
        """Paths from one transducer to another: (name, length in m,
        amplitude factor from reflections, names of planes hit). The direct
        path, then one per plane that both ends are in front of, then one via
        each point reflector and mover (where it is at `clock`, s)."""
        src, dst = self._position[emitter], self._position[receiver]
        routes = [("direct", channel.path_length(src, dst), 1.0, [])]
        for target in self.scene.get("reflectors", []):
            at = np.asarray(target["position"], dtype=float)
            routes.append((f"reflector:{target['name']}",
                           channel.path_length(src, at) + channel.path_length(at, dst),
                           float(target.get("strength", 1.0)), [target["name"]]))
        for target in self.scene.get("movers", []):
            at = mover_position(target, clock)
            routes.append((f"mover:{target['name']}",
                           channel.path_length(src, at) + channel.path_length(at, dst),
                           float(target.get("strength", 1.0)), [target["name"]]))
        for plane in self.scene.get("planes", []):
            image = channel.image_source(src, plane["point"], plane["normal"])
            if image is None:
                continue
            height = np.dot(dst - np.asarray(plane["point"], dtype=float),
                            np.asarray(plane["normal"], dtype=float))
            if height <= 0:
                continue        # the receiver is behind the plane
            routes.append((f"plane:{plane['name']}", channel.path_length(image, dst),
                           plane["reflection"], [plane["name"]]))
        return routes
