"""Room sonar: ping a room from the speakers near a microphone and read the
returns against range, and with two speakers, against place.

An in-air sonar from whatever the computer has. Time zero of every sound of a
ping is that sound's own direct arrival from its speaker to the microphone,
found in that ping's own recording, so output and input need not share a
clock (different cards, the shared mode) and the unknown output-to-input delay
of the device does not matter. An echo that arrives `t` after the direct sound
has travelled `c * t` further than the direct path, so with the
speaker-to-microphone distance `d` known the whole path speaker - target -
microphone is `L = c * t + d`, and its range, taking speaker and microphone as
one place, is `L / 2`.

**Two speakers.** Every event of the ping design is sent. Events of one signal
that start together are one combined sound (nothing says which speaker an echo
came from); every other signal gets its own matched filter, its own time zero
and its own return. With two such returns, an echo of one speaker and an echo
of the other that belong to the same target give two path lengths, and a
target lies on the ellipse of points whose speaker and microphone distances add
to each: two paths, two curves, one point in front of the laptop (the other
intersection is behind it, and is not reported). `solve_position` is that
intersection; `pair_echoes` decides which echoes go together. The geometry is
three-dimensional (a laptop's microphone is in the screen, 25 cm above the
speakers), and a target is taken to be at the speakers' height: one above or
below it is placed where its path lengths put it at that height
(`placement_error` says by how much).

Nothing here draws anything or opens a device.
"""
from dataclasses import dataclass, field

import numpy as np
from scipy import signal as sps
from scipy.optimize import linear_sum_assignment

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


def positions(layout):
    """{transducer ID: (x, y, z) in m} of a layout; empty without one."""
    if not layout:
        return {}
    return {t["id"]: np.asarray(t["position"], dtype=float) for t in layout["transducers"]}


@dataclass
class Geometry:
    """Where the speakers and the microphone are: x across, y forward (the
    room is at +y), z up, in m. `assumed` is True when the layout says its
    positions are a guess and not a measurement."""
    speakers: dict                  # transducer ID -> position (3,)
    mic: np.ndarray
    assumed: bool = False

    def xy(self, transducer):
        return self.speakers[transducer][:2]

    @property
    def centre(self):
        """The middle of the speakers, in the plane."""
        return np.mean([s[:2] for s in self.speakers.values()], axis=0)

    def spacing(self, a, b):
        """Distance between two speakers, in the plane, m."""
        return float(np.linalg.norm(self.speakers[a][:2] - self.speakers[b][:2]))


def geometry(layout, outputs, input_):
    """The Geometry of the given outputs and input in a layout, or None if
    the layout lacks any of them."""
    pos = positions(layout)
    if input_ not in pos or any(o not in pos for o in outputs):
        return None
    return Geometry(speakers={o: pos[o] for o in outputs}, mic=pos[input_],
                    assumed=not (layout or {}).get("measured", True))


def separation(layout, output, input_):
    """Distance between two transducers of a layout, m; 0.0 if either is not
    there."""
    pos = positions(layout)
    if output not in pos or input_ not in pos:
        return 0.0
    return float(np.linalg.norm(pos[output] - pos[input_]))


def listen_for(max_range_m, speed, baseline_m=0.0):
    """Seconds to keep recording after the sound, for echoes from
    `max_range_m`."""
    return max((2.0 * max_range_m - baseline_m) / speed, 0.0) + MARGIN_S


# ---- which events are one sound, and steering ------------------------------------

def group_events(events, combine_s):
    """Group events given as (signal key, start in s) into sounds: lists of
    event numbers. Events of one signal that start within `combine_s` of the
    group's first are one combined sound."""
    groups = []
    for i, (key, start) in enumerate(events):
        for g in groups:
            if events[g[0]][0] == key and abs(start - events[g[0]][1]) < combine_s:
                g.append(i)
                break
        else:
            groups.append([i])
    return groups


def sounds(ping, design=DEFAULT):
    """The ping's emissions grouped into sounds: lists of emission numbers.
    Emissions of one signal that start within the design's same-sound window
    of the group's first are one combined sound (the analysis cannot tell
    which speaker an echo came from); everything else is a sound of its own."""
    return group_events([(e.signal or f"#{i}", e.start) for i, e in enumerate(ping.emissions)],
                        design.combine_s)


def steering_delays(geom, outputs, angle_deg, speed):
    """Seconds each of `outputs` is delayed so that sounds sent together add
    up in the direction `angle_deg` (0 straight ahead, positive to the right,
    +x): the speaker nearest the target in that direction starts last. A
    plane wave from the speakers towards that direction then has them all in
    step; the far field is assumed (the target is far beyond the spacing)."""
    theta = np.radians(angle_deg)
    towards = np.array([np.sin(theta), np.cos(theta)])
    along = {o: float(geom.xy(o) @ towards) for o in outputs}
    least = min(along.values())
    return {o: (along[o] - least) / speed for o in outputs}


def steered_zone(spacing_x_m, resolution_s, speed, angle_deg=0.0):
    """(low, high) bearing in degrees between which two copies of one chirp,
    sent together from speakers `spacing_x_m` apart (along x), reach a target
    less than half the matched filter's resolution apart: they then add up to
    one peak and the pair acts as one speaker steered to `angle_deg`. Outside
    it the target is heard twice. The half-width is about
    asin(c * resolution / 2 / spacing)."""
    if spacing_x_m <= 0:
        return -90.0, 90.0
    h = speed * resolution_s / 2.0 / spacing_x_m
    s0 = np.sin(np.radians(angle_deg))
    low = np.degrees(np.arcsin(np.clip(s0 - h, -1.0, 1.0)))
    high = np.degrees(np.arcsin(np.clip(s0 + h, -1.0, 1.0)))
    return float(low), float(high)


def fringe_step_deg(spacing_x_m, frequency_hz, speed):
    """Bearing between the peaks of the fringes (grating lobes) of a steady
    tone sent from two speakers: sin(theta) steps by wavelength / spacing.
    Degrees at straight ahead; None if the spacing is below half a
    wavelength (one lobe only)."""
    step = speed / max(frequency_hz, 1.0) / max(spacing_x_m, 1e-9)
    return float(np.degrees(np.arcsin(step))) if step < 1.0 else None


# ---- the ping --------------------------------------------------------------------

def build_ping(workspace, design_id, input_, infos, max_range_m, speed,
               layout=None, steer_deg=0.0, design=DEFAULT, wsl=False):
    """A backend Ping for the room sonar: every event of the ping design,
    each from its own transducer with its own signal and time, heard on
    `input_`, listening long enough for `max_range_m`. Where several events
    share one signal and start together (one sound from several speakers),
    `steer_deg` delays all but the first-reached speaker so that the sound adds
    up towards that bearing (`steering_delays`). `design` is the detection
    design (its same-sound window decides what is "together"). `wsl` is True
    when the sound goes through WSL's Windows sound bridge, which does not keep
    the spacing of events sent at different times: the ping then carries a
    warning (in `meta["warnings"]`) if the design staggers its events. Raises
    ValueError with a message a person can act on."""
    ping_design = workspace.get("ping_designs", design_id)
    if ping_design is None:
        raise ValueError("no ping design is selected")
    if not ping_design["events"]:
        raise ValueError(f"ping design '{ping_design['name']}' has no events")
    info = {t.id: t for t in infos}
    if input_ not in info or not info[input_].can_receive:
        raise ValueError(f"'{input_}' cannot receive with this backend and scene")
    emissions, specs = [], {}
    for n, event in enumerate(ping_design["events"], 1):
        tid = event["transducer"]
        if tid not in info or not info[tid].can_send:
            raise ValueError(f"event {n}: '{tid}' cannot send with this backend and scene")
        rate = info[tid].rate
        try:
            samples = signal_objects.samples(workspace.get_signal, event["signal"], rate)
            f0, f1, duration = signal_objects.band(workspace.get_signal, event["signal"])
            amplitude = signal_objects.level(workspace.get_signal, event["signal"])
        except WorkspaceError as error:
            raise ValueError(f"event {n}: {error}") from None
        emissions.append(Emission(transducer=tid, samples=samples, start=event["time"],
                                  rate=rate, signal=event["signal"]))
        specs.setdefault(event["signal"], dict(
            name=workspace.name_of("signals", event["signal"]), f0=f0, f1=f1,
            duration=duration, amplitude=amplitude))
    outputs = list(dict.fromkeys(e.transducer for e in emissions))
    baselines = [separation(layout, o, input_) for o in outputs]
    ping = Ping(
        emissions=emissions, receivers=[input_],
        listen=listen_for(max_range_m, speed, min(baselines) if baselines else 0.0),
        meta=dict(design_id=design_id, design_name=ping_design["name"],
                  detection_design=ping_design.get("detection_design"),
                  signals=specs, room=True, max_range_m=max_range_m,
                  input=input_, outputs=outputs, steer_deg=float(steer_deg),
                  warnings=[]))
    delays = {}
    geom = geometry(layout, outputs, input_)
    for group in sounds(ping, design):
        members = [ping.emissions[i] for i in group]
        if len(members) < 2:
            continue
        ids = [e.transducer for e in members]
        if len(set(ids)) < len(ids):
            continue
        if geom is None:
            if steer_deg:
                ping.meta["warnings"].append(
                    "not steered: the layout does not give the positions of "
                    + " and ".join(ids))
            continue
        for e, wait in zip(members, steering_delays(geom, ids, steer_deg, speed).values()):
            e.start += wait
            delays[e.transducer] = wait
    ping.meta["steering_delays_s"] = delays
    if wsl:
        ping.meta["warnings"] += stagger_warnings(ping, design)
    return ping


WSL_STAGGER = ("on WSL the Windows sound bridge does not keep the spacing between sounds "
               "sent at different times (it slips by 5-25 ms), while sounds sent at the same "
               "instant are fine")


def stagger_warnings(ping, design=DEFAULT):
    """Plain sentences about a ping whose events are not all sent at the same
    instant, for a machine whose sound path cannot keep their spacing (WSL):
    sounds at different times ('left then right') and steering delays.
    Recommends simultaneous coded designs."""
    starts = [e.start for e in ping.emissions]
    out = []
    staggered = len(sounds(ping, design)) > 1 and (max(starts) - min(starts)) >= design.combine_s
    steered = any(v > 0 for v in ping.meta.get("steering_delays_s", {}).values())
    if staggered:
        out.append("this ping design staggers its events in time, and " + WSL_STAGGER
                   + ", so the second speaker's echoes would be misplaced. Use a design that "
                     "sends both at once with coded signals: both speakers, up and down "
                     "chirps, or both speakers, split bands")
    elif steered:
        out.append("steering delays the second speaker by a fraction of a millisecond, and "
                   + WSL_STAGGER + ", so the steering may not be as set")
    return out


def signal_specs(workspace, design_id, rate=48000.0):
    """The ping design's events as dicts for the numbers: transducer, time,
    signal ID and name, f0, f1, duration, and the samples at `rate`. Empty
    for a design that is missing or has a signal that cannot be made."""
    design = workspace.get("ping_designs", design_id or "")
    if not design:
        return []
    out = []
    for event in design["events"]:
        try:
            f0, f1, duration = signal_objects.band(workspace.get_signal, event["signal"])
            template = signal_objects.samples(workspace.get_signal, event["signal"], rate)
        except Exception:                       # noqa: a broken signal: leave it out
            return []
        out.append(dict(transducer=event["transducer"], time=event["time"],
                        signal=event["signal"],
                        name=workspace.name_of("signals", event["signal"]),
                        f0=f0, f1=f1, duration=duration, template=template,
                        template_rate=rate))
    return out


def leak_pairs(specs, max_range_m, speed):
    """For every two events with different signals that are in the room at
    the same time (within the time an echo from `max_range_m` takes): (i, j,
    isolation_db), how far below its own peak event j's signal shows up in
    event i's matched filter. Negative numbers: -17 is 17 dB down."""
    out = []
    reach = 2.0 * max_range_m / speed
    for i, a in enumerate(specs):
        for j, b in enumerate(specs):
            if j <= i or a["signal"] == b["signal"]:
                continue
            if abs(a["time"] - b["time"]) > reach + max(a["duration"], b["duration"]):
                continue
            out.append((i, j, detection.isolation_db(a["template"], b["template"])))
    return out


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


# ---- what is read from a ping ------------------------------------------------------

@dataclass
class Echo:
    """One peak of a return that is taken for a target."""
    range_m: float           # half the path speaker - target - microphone
    level: float             # envelope re the direct sound (linear)
    snr: float               # re the typical level of the return

    @property
    def path_m(self):
        return 2.0 * self.range_m

    @property
    def level_db(self):
        return float(20 * np.log10(max(self.level, 1e-12)))


@dataclass
class RoomPing:
    """One sound of a ping (one signal from one speaker, or from several
    together) read as a return against range."""
    output: str                          # the first transducer that sent it
    input: str
    range_m: np.ndarray = field(default_factory=lambda: np.zeros(0))
    level: np.ndarray = field(default_factory=lambda: np.zeros(0))   # envelope / direct peak
    heard: bool = False                  # the direct sound was found
    direct_sample: float = float("nan")  # where, in the recording (sub-sample)
    direct_dbfs: float = float("nan")    # its level, dB re full scale
    direct_snr: float = float("nan")
    noise_db: float = float("nan")       # typical (median) level, dB re the direct sound
    sound_speed: float = 343.2
    baseline_m: float = 0.0              # speaker to microphone (mean over the speakers)
    design: detection.DetectionDesign = DEFAULT
    design_id: str = ""
    warnings: list = field(default_factory=list)
    truth: list = field(default_factory=list)     # simulation: (route name, range m)
    outputs: list = field(default_factory=list)   # every transducer that sent it
    members: list = field(default_factory=list)   # their emission numbers in the ping
    signal: str = ""                     # signal ID (or name)
    rate: float = 48000.0                # sample rate of the recording, Hz
    echoes: list = field(default_factory=list)    # of Echo, from `level`
    start_s: float = 0.0                 # when the sound was sent in the ping, s

    @property
    def level_db(self):
        return to_db(self.level)

    @property
    def combined(self):
        return len(self.outputs) > 1


@dataclass
class Fix:
    """A target placed in the plane from one echo of each of two speakers."""
    x: float                 # across, m (right is +)
    y: float                 # forward, m
    range_m: float           # from the middle of the speakers
    bearing_deg: float       # from straight ahead, positive to the right
    level_db: float          # the mean of the two echoes, re their direct sounds
    paths: tuple             # the two path lengths, m
    channels: tuple          # which two returns (indices into the result's channels)
    echoes: tuple            # which echo of each


@dataclass
class RoomResult:
    """A whole ping: a RoomPing per sound, what was found in each, and where
    the targets are."""
    input: str
    channels: list = field(default_factory=list)       # of RoomPing
    geometry: Geometry = None
    sound_speed: float = 343.2
    design: detection.DetectionDesign = DEFAULT
    design_id: str = ""
    warnings: list = field(default_factory=list)       # about the ping as a whole
    leaks: list = field(default_factory=list)          # (i, j, isolation dB) between sounds
    steer_deg: float = 0.0
    fixes: list = field(default_factory=list)          # of Fix, from every echo
    mic: dict = None                                   # what the direct sounds say of the microphone
    truth_targets: list = field(default_factory=list)  # simulation: (name, kind, x, y)

    @property
    def heard(self):
        return any(c.heard for c in self.channels)

    @property
    def primary(self):
        """The first sound whose direct sound was heard, else the first."""
        return next((c for c in self.channels if c.heard), self.channels[0] if self.channels else None)

    @property
    def all_warnings(self):
        out = list(self.warnings)
        for c in self.channels:
            out += [w for w in c.warnings if w not in out]
        return out


def to_db(level, floor=FLOOR_DB):
    """Linear level (re the direct sound) as dB, never below `floor`."""
    return np.maximum(20 * np.log10(np.maximum(np.asarray(level, dtype=float), 1e-12)), floor)


def _name(layout, tid):
    for t in (layout or {}).get("transducers", []):
        if t["id"] == tid:
            return t.get("name", tid)
    return tid


def read(capture, input_, design=DEFAULT, design_id="", max_range_m=DEFAULT_MAX_RANGE_M,
         baseline_m=None, layout=None):
    """Read a capture as a RoomResult: a RoomPing for every sound of the ping
    (`sounds`), each with its own matched filter and its own time zero, the
    echoes found in each, and, where two sounds come from two speakers whose
    positions the layout gives, the targets those echoes place in the plane.

    A sound's time zero is its own direct sound in the `input_` recording:
    the strongest peak of the clearest signal anchors the ping; the other
    sounds' direct sounds are looked for where the ping design and the layout
    put them relative to it (within the design's direct-sound window); each is
    moved back to the first peak at least the design's first-arrival fraction
    of it, and located to a fraction of a sample. `baseline_m`, if given,
    replaces the speaker-to-microphone distances taken from the layout.
    `layout` defaults to the one in the capture."""
    recording = capture.recordings[input_]
    ping = capture.ping
    rate = recording.rate
    speed = capture.meta.get("sound_speed") or ranging.DEFAULT_SOUND_SPEED
    layout = layout if layout is not None else capture.meta.get("layout")
    result = RoomResult(input=input_, sound_speed=speed, design=design, design_id=design_id,
                        steer_deg=float(ping.meta.get("steer_deg", 0.0)))
    result.warnings += list(ping.meta.get("warnings", []))
    groups = sounds(ping, design)
    for group in groups:
        first = ping.emissions[group[0]]
        outs = list(dict.fromkeys(ping.emissions[i].transducer for i in group))
        d = (baseline_m if baseline_m is not None else
             float(np.mean([separation(layout, o, input_) for o in outs])))
        result.channels.append(RoomPing(
            output=outs[0], input=input_, sound_speed=speed, baseline_m=d, design=design,
            design_id=design_id, outputs=outs, members=list(group),
            signal=first.signal or f"#{group[0]}", rate=rate, start_s=first.start))
    singles = [c.outputs[0] for c in result.channels if not c.combined]
    result.geometry = geometry(layout, singles, input_) if len(singles) >= 2 else None
    if result.geometry is None and len(singles) >= 2:
        result.warnings.append(
            "the layout does not give the positions of "
            + ", ".join(singles) + " and " + input_ + ", so the returns cannot be placed")

    samples = np.asarray(recording.samples, dtype=np.float64)
    templates = {}
    for c in result.channels:
        e = ping.emissions[c.members[0]]
        templates.setdefault(c.signal, ranging._template(e, rate))
    if samples.size < max(t.size for t in templates.values()) + 16:
        for c in result.channels:
            c.warnings.append("the recording is too short")
        return result

    filters = {}
    for key, template in templates.items():
        analytic, env = detection.correlation(samples, template, design.method)
        filters[key] = (analytic, env, detection.noise_level(env, template, unit=1.0))
    anchor_key = max(filters, key=lambda k: filters[k][1].max() / filters[k][2])
    _, aenv, anoise = filters[anchor_key]
    strongest = int(np.argmax(aenv))
    if aenv[strongest] < design.hit_snr * anoise:
        text = ("the direct sound from the speaker was not found above the noise "
                f"(strongest peak {aenv[strongest] / anoise:.1f} x the typical level, the "
                f"detection design wants {design.hit_snr:g}): is the output on, loud enough, "
                "and the right input chosen?")
        for c in result.channels:
            c.warnings.append(text)
        return result

    window = max(1, int(design.direct_window_s * rate))

    def start(c):
        return ping.emissions[c.members[0]].start

    def expected(c, ref):
        """Where channel c's direct sound should be if channel `ref[0]`'s is at
        sample `ref[1]`."""
        other, at = ref
        return at + ((start(c) - start(other)) + (c.baseline_m - other.baseline_m) / speed) * rate

    def strongest_in(c, centre):
        env = filters[c.signal][1]
        lo, hi = max(int(round(centre)) - window, 0), min(int(round(centre)) + window + 1, env.size)
        if hi - lo < 3:
            return None
        return lo + int(np.argmax(env[lo:hi]))

    candidates = [c for c in result.channels if c.signal == anchor_key]
    best, best_score = candidates[0], -1.0
    if len(result.channels) > 1:
        for cand in candidates:
            score = 0.0
            for c in result.channels:
                if c is cand:
                    continue
                at = strongest_in(c, expected(c, (cand, strongest)))
                if at is not None:
                    ratio = filters[c.signal][1][at] / filters[c.signal][2]
                    if ratio >= design.hit_snr:
                        score += ratio
            if score > best_score:
                best, best_score = cand, score

    for c in result.channels:
        analytic, env, noise = filters[c.signal]
        template = templates[c.signal]
        peak_at = strongest if c is best else strongest_in(c, expected(c, (best, strongest)))
        if peak_at is None or env[peak_at] < design.hit_snr * noise:
            c.warnings.append(
                f"the direct sound of {c.signal} from {' and '.join(c.outputs)} was not "
                "found where the other sound puts it "
                f"(within {1e3 * design.direct_window_s:g} ms; the detection design's "
                "direct-sound window): is that speaker playing?")
            continue
        first = detection.leading(env, peak_at, template.size, design.hit_snr * noise,
                                  design.first_fraction)
        position = detection.refine(analytic, first, design)
        peak = float(np.interp(position, np.arange(env.size), env))
        c.heard = True
        c.direct_sample = position
        c.direct_dbfs = detection.level_dbfs(peak, template, design.method, unit=1.0)
        c.direct_snr = peak / noise
        c.noise_db = float(20 * np.log10(noise / peak))
        if any(o in recording.loopback_of for o in c.outputs):
            c.warnings.append(
                "this input carries an electrical loopback of "
                f"'{[o for o in c.outputs if o in recording.loopback_of][0]}': time zero is the "
                "first arrival, which is then the loopback and not the sound through the air")
        bins = int(max_range_m / (speed / (2.0 * rate)))
        c.range_m = np.arange(bins) * speed / (2.0 * rate)
        delay_s = (2.0 * c.range_m - c.baseline_m) / speed
        at = position + delay_s * rate
        inside = (at >= 0) & (at <= env.size - 1)
        level = np.zeros(bins)
        level[inside] = np.interp(at[inside], np.arange(env.size), env) / peak
        c.level = level
        if np.any(~inside & (at > 0)):
            c.warnings.append(
                f"the recording ends before {max_range_m:g} m: the ranges beyond "
                f"{c.range_m[inside].max():.2f} m are blank")
    if np.max(np.abs(samples)) >= 0.999:
        result.warnings.append("the input reaches full scale: it is clipping, which "
                               "blunts the direct sound and shifts every echo")

    _truth(result, capture, input_, speed)
    # Leakage between the sounds' filters (only the ones that share the room's time).
    reach = 2.0 * max_range_m / speed
    for i, a in enumerate(result.channels):
        for j, b in enumerate(result.channels):
            if j <= i or a.signal == b.signal:
                continue
            ta, tb = templates[a.signal], templates[b.signal]
            if abs(start(a) - start(b)) > reach + max(ta.size, tb.size) / rate:
                continue
            result.leaks.append((i, j, detection.isolation_db(ta, tb)))
    if design.method == "matched":
        for i, j, db in result.leaks:
            if db > design.leak_db:
                result.warnings.append(
                    f"{_name(layout, result.channels[i].output)} and "
                    f"{_name(layout, result.channels[j].output)} overlap in time and band: "
                    f"each leaks into the other's filter only {-db:.0f} dB down, smeared in "
                    "time, so a weak echo near a strong one may be taken for the other "
                    "speaker's")
    for c in result.channels:
        c.echoes = find_echoes(c, c.level, design)
    result.fixes = place(result.channels, [c.level for c in result.channels], design,
                         result.geometry)
    result.mic = mic_offset(result)
    return result


def _truth(result, capture, input_, speed):
    """Fill in, for a simulated capture, the true ranges of every echo and the
    places of the targets (reflectors and movers)."""
    truth = getattr(capture, "truth", None)
    if not truth:
        return
    for c in result.channels:
        for ei in c.members:
            paths = [p for p in truth["paths"] if p["receiver"] == input_ and p["emission"] == ei]
            direct = [p for p in paths if p["route"] == "direct"]
            if not direct:
                continue
            for p in paths:
                if p["route"] not in ("direct", "loopback"):
                    t = p["arrival_s"] - direct[0]["arrival_s"]
                    c.truth.append((p["route"], (speed * t + c.baseline_m) / 2.0))
    scene = capture.meta.get("scene") or {}
    for r in scene.get("reflectors", []):
        result.truth_targets.append((r["name"], "reflector", r["position"][0], r["position"][1]))
    for name, at in (truth.get("movers") or {}).items():
        result.truth_targets.append((name, "mover", at[0], at[1]))


# ---- echoes, pairs and places ----------------------------------------------------

def find_echoes(channel, level, design=DEFAULT):
    """The echoes in one return: peaks of `level` (envelope re the direct
    sound, on the channel's range grid) that reach the design's echo threshold
    times the return's typical level, are further than its nearest-echo range
    and are further apart than its echo separation; the tallest few, in range
    order, each placed to a fraction of a bin by a parabola through its top."""
    level = np.asarray(level, dtype=float)
    if not channel.heard or level.size < 3:
        return []
    noise = 10 ** (channel.noise_db / 20.0)
    step = float(channel.range_m[1] - channel.range_m[0])
    distance = max(1, int(round(design.echo_separation_s * channel.rate)))
    peaks, _ = sps.find_peaks(level, height=design.echo_snr * noise, distance=distance)
    peaks = [p for p in peaks if 0 < p < level.size - 1
             and channel.range_m[p] >= design.nearest_m]
    peaks = sorted(sorted(peaks, key=lambda p: level[p])[-design.max_echoes:])
    echoes = []
    for p in peaks:
        a, b, c = level[p - 1], level[p], level[p + 1]
        bend = a - 2 * b + c
        shift = 0.5 * (a - c) / bend if bend < 0 else 0.0
        echoes.append(Echo(range_m=float(channel.range_m[p] + shift * step),
                           level=float(b - 0.25 * (a - c) * shift), snr=float(b / noise)))
    return echoes


def _solve_plane(source_a, source_b, mic, path_a, path_b):
    """The in-plane closed form, for a microphone in the plane of the
    speakers (and a seed for `solve_position`): see there. Returns (x, y) or
    None."""
    a = np.asarray(source_a, dtype=float)[:2] - np.asarray(mic, dtype=float)[:2]
    b = np.asarray(source_b, dtype=float)[:2] - np.asarray(mic, dtype=float)[:2]
    alpha = path_a ** 2 - a @ a
    beta = path_b ** 2 - b @ b
    if alpha <= 0 or beta <= 0:
        return None
    w = alpha * b - beta * a
    k = alpha * path_b - beta * path_a
    norm = float(np.hypot(*w))
    if norm < 1e-12:
        return None
    c = k / norm
    if abs(c) > 1.0:
        if abs(c) > 1.0 + 1e-6:
            return None
        c = float(np.sign(c))
    along = w / norm
    across = np.array([-along[1], along[0]])
    found = []
    for sign in (1.0, -1.0):
        u = c * along + sign * np.sqrt(max(1.0 - c * c, 0.0)) * across
        denominator = path_a - a @ u
        if denominator <= 0:
            continue
        r = alpha / (2.0 * denominator)
        if r <= 0 or r >= path_a:
            continue
        found.append(np.asarray(mic, dtype=float)[:2] + r * u)
    if not found:
        return None
    best = max(found, key=lambda p: p[1])
    return float(best[0]), float(best[1])


def solve_position(source_a, source_b, mic, path_a, path_b, height=None):
    """Where a target is, from the two paths speaker A - target - microphone
    and speaker B - target - microphone (m), given the positions (x, y, z) of
    A, B and the microphone. The target is taken to be at `height` (z; default
    the speakers' mean height), so the microphone can be above or below it
    (a laptop's is in the screen, 25 cm up). Returns (x, y), or None if the
    two paths cannot belong to one target in front of the laptop.

    Each path is an ellipsoid of possible places (foci: that speaker and the
    microphone); at the target's height each is a curve, and two curves meet
    in two points, front and back of the laptop. With the microphone in the
    plane of the speakers the solution is closed form: with r the target's
    distance from the microphone and u the direction to it, a path L from a
    speaker at offset a from the microphone gives r = (L^2 - |a|^2) /
    (2 (L - a . u)); equal r for the two speakers is one linear equation in u,
    which with |u| = 1 has two solutions (`_solve_plane`). With the microphone
    at another height that seeds a few Newton steps on the two path
    equations. The solution with the larger y (in front) is returned."""
    sa, sb, m = (np.asarray(v, dtype=float) for v in (source_a, source_b, mic))
    z0 = float(height) if height is not None else float(0.5 * (sa[2] + sb[2]))
    seeds = []
    seed = _solve_plane(sa, sb, m, path_a, path_b)
    if seed is not None:
        seeds.append(np.array(seed))
    seeds += [np.array([x, 0.5 * path_a]) for x in (0.0, -0.4 * path_a, 0.4 * path_a)]
    found = []
    for p in seeds:
        p = p.copy()
        for _ in range(40):
            f, jac = [], []
            for s, length in ((sa, path_a), (sb, path_b)):
                ds = np.array([p[0] - s[0], p[1] - s[1], z0 - s[2]])
                dm = np.array([p[0] - m[0], p[1] - m[1], z0 - m[2]])
                ns, nm = np.linalg.norm(ds), np.linalg.norm(dm)
                if ns < 1e-9 or nm < 1e-9:
                    break
                f.append(ns + nm - length)
                jac.append(ds[:2] / ns + dm[:2] / nm)
            else:
                f, jac = np.array(f), np.array(jac)
                if np.max(np.abs(f)) < 1e-10:
                    found.append(p)
                    break
                try:
                    step = np.linalg.solve(jac, -f)
                except np.linalg.LinAlgError:
                    break
                size = np.linalg.norm(step)
                p = p + step * min(1.0, 0.5 * path_a / max(size, 1e-12))
                continue
            break
        if found:
            break
    if not found:
        return None
    best = found[0]
    if best[1] <= min(sa[1], sb[1]) - 1e-9:
        return None
    return float(best[0]), float(best[1])


def placement_error(geom, target, ignore_mic_height=False):
    """For a simulated or imagined target at (x, y, z), the distance in m
    between where it is and where the two echoes place it, when the paths are
    exact. The target's height away from the speakers' plane is what it
    cannot know; with `ignore_mic_height` the microphone is also taken to be
    in the speakers' plane, as if its height had not been entered. None if
    it is not placed. Uses the first two speakers of `geom`."""
    (a, sa), (b, sb) = list(geom.speakers.items())[:2]
    target = np.asarray(target, dtype=float)
    la = np.linalg.norm(sa - target) + np.linalg.norm(geom.mic - target)
    lb = np.linalg.norm(sb - target) + np.linalg.norm(geom.mic - target)
    mic = geom.mic.copy()
    if ignore_mic_height:
        mic[2] = 0.5 * (sa[2] + sb[2])
    at = solve_position(sa, sb, mic, la, lb)
    return None if at is None else float(np.hypot(at[0] - target[0], at[1] - target[1]))


def mic_offset(result):
    """What the two direct sounds say about where the microphone is across:
    from a ping read with two sounds from two speakers whose positions the
    layout gives, the difference of their direct arrival times (the device's
    latency is the same for both and cancels) times c is the difference of
    the two speaker-to-microphone distances, which fixes the microphone's x
    (given its y and z from the layout). Returns a dict (x_m: the estimate;
    layout_x_m; path_difference_m), or None."""
    geom = result.geometry
    singles = [c for c in result.channels if not c.combined and c.heard]
    if geom is None or len(singles) < 2:
        return None
    a, b = singles[0], singles[1]
    sa, sb = geom.speakers[a.outputs[0]], geom.speakers[b.outputs[0]]
    delta = result.sound_speed * ((a.direct_sample - a.start_s * a.rate)
                                  - (b.direct_sample - b.start_s * b.rate)) / a.rate
    my, mz = geom.mic[1], geom.mic[2]

    def difference(x):
        return (np.linalg.norm([x - sa[0], my - sa[1], mz - sa[2]])
                - np.linalg.norm([x - sb[0], my - sb[1], mz - sb[2]]))
    lo, hi = min(sa[0], sb[0]) - 1.0, max(sa[0], sb[0]) + 1.0
    if not difference(lo) <= delta <= difference(hi):
        return None
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        if difference(mid) < delta:
            lo = mid
        else:
            hi = mid
    return dict(x_m=0.5 * (lo + hi), layout_x_m=float(geom.mic[0]), path_difference_m=float(delta),
                towards=a.outputs[0] if 0.5 * (lo + hi) < geom.mic[0] else b.outputs[0])


def pair_echoes(echoes_a, echoes_b, source_a, source_b, mic, design=DEFAULT):
    """Which echo of speaker A goes with which of speaker B: (i, j, x, y)
    for each pair, one target each.

    A pair is possible only if the paths differ by no more than the speakers'
    spacing plus the design's pairing tolerance, the levels by no more than
    its pairing level difference, and the two ellipses meet in front of the
    laptop (`solve_position`). Among the possible ones each echo is used at
    most once, choosing the combination whose pairs have the most alike
    levels."""
    spacing = float(np.linalg.norm(np.asarray(source_a[:2]) - np.asarray(source_b[:2])))
    big = 1e6
    cost = np.full((len(echoes_a), len(echoes_b)), big)
    where = {}
    for i, ea in enumerate(echoes_a):
        for j, eb in enumerate(echoes_b):
            gap = abs(ea.path_m - eb.path_m)
            if gap > spacing + design.pair_tolerance_m:
                continue
            db = abs(ea.level_db - eb.level_db)
            if db > design.pair_level_db:
                continue
            at = solve_position(source_a, source_b, mic, ea.path_m, eb.path_m)
            if at is None:
                continue
            cost[i, j] = db + 1e-3 * gap
            where[i, j] = at
    if not where:
        return []
    rows, cols = linear_sum_assignment(cost)
    return [(int(i), int(j), *where[i, j]) for i, j in zip(rows, cols) if (i, j) in where]


def place(channels, levels, design, geom):
    """The targets that the echoes of the first two single-speaker returns
    place in the plane, as Fixes. `levels` are the arrays to take echoes from
    (the returns' own, or what changed since the background). Returns [] if
    there are not two such returns or the geometry is not known."""
    if geom is None:
        return []
    singles = [(n, c) for n, c in enumerate(channels) if not c.combined and c.heard]
    if len(singles) < 2:
        return []
    (na, a), (nb, b) = singles[0], singles[1]
    ea = find_echoes(a, levels[na], design)
    eb = find_echoes(b, levels[nb], design)
    sa, sb = geom.speakers[a.outputs[0]], geom.speakers[b.outputs[0]]
    centre = geom.centre
    fixes = []
    for i, j, x, y in pair_echoes(ea, eb, sa, sb, geom.mic, design):
        dx, dy = x - centre[0], y - centre[1]
        fixes.append(Fix(
            x=x, y=y, range_m=float(np.hypot(dx, dy)),
            bearing_deg=float(np.degrees(np.arctan2(dx, dy))),
            level_db=0.5 * (ea[i].level_db + eb[j].level_db),
            paths=(ea[i].path_m, eb[j].path_m), channels=(na, nb), echoes=(i, j)))
    return fixes


def analyse(capture, output, input_, design=DEFAULT, design_id="",
            max_range_m=DEFAULT_MAX_RANGE_M, baseline_m=None):
    """The return of the sound that `output` sent, read from the `input_`
    recording (a RoomPing): `read`, keeping the one sound."""
    result = read(capture, input_, design, design_id, max_range_m, baseline_m)
    for c in result.channels:
        if output in c.outputs:
            c.warnings += [w for w in result.warnings if w not in c.warnings]
            return c
    empty = RoomPing(output=output, input=input_, design=design, design_id=design_id,
                     sound_speed=result.sound_speed)
    empty.warnings.append(f"the ping has no signal from '{output}'")
    return empty


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
