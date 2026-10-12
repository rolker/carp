"""Rigs, their as-built scenes, and the laptop template.

A rig says which real device and channel each transducer of a layout is on,
which input carries which loopback, and how each device is taken hold of
(exclusive or shared, mixer values to apply). Pages and ping designs never
mention devices, only transducer IDs; the rig is what makes the hardware
backend able to play them.

Each rig has an **as-built scene**: its twin for the simulator, holding the
layout the rig is wired to, one simulated device per rig device, the
loopbacks, and the bench medium and reflecting surfaces. It is made with the
rig and kept in step with it by `create_rig` and `update_rig`; whatever else
is in the scene (medium, planes, noise, reflectors) stays as it was, so the
bench's surfaces survive edits to the rig. Hardware can only ever be the
bench as built, so switching the backend to hardware activates this scene.
"""
import copy
import os
import socket

from . import schema as s
from .schema import WorkspaceError

LAPTOP_LAYOUT = "laptop"
LAPTOP_RIG = "laptop_speaker_and_mic"
LAPTOP_DEMO = "laptop_in_a_room"
LAPTOP_SIGNAL = "room_chirp"
LAPTOP_DESIGN = "room_chirp_from_the_laptop"
NEAR_M = 0.5                   # "near": an output and an input this close
# What worked on the laptop's built-in card (2026-10-12, speaker to internal
# mic): the desktop leaves the mic at +30 dB capture and +20 dB boost, which
# clips with a large DC offset. Control names are the card's own; one that a
# card does not have is a warning, and the rest are still set. All are put
# back when the card is given back.
LAPTOP_MIXER = {"Master Playback Volume": "-15dB", "Capture Volume": "5dB",
                "Internal Mic Boost Volume": "0dB"}


def placements(rig):
    """{transducer ID: its entry on the rig}."""
    return {t["id"]: t for t in rig.get("transducers", [])}


def device_of(rig, device_id):
    return next((d for d in rig.get("devices", []) if d["id"] == device_id), None)


def problems(rig, layout):
    """Plain sentences about what is wrong or missing in a rig for its
    layout: transducers the layout does not have, outputs and inputs the
    layout says cannot work that way, layout transducers not placed."""
    found = []
    info = {t["id"]: t for t in layout.get("transducers", [])}
    placed = placements(rig)
    for tid in placed:
        if tid not in info:
            found.append(f"the rig places '{tid}', which the layout does not have")
    for tid, t in info.items():
        if tid not in placed:
            found.append(f"'{t.get('name', tid)}' ({tid}) is not placed on a device; "
                         "the hardware cannot use it")
    inputs = {}
    for tid, p in placed.items():
        t = info.get(tid)
        if t is None:
            continue
        if t.get("can_receive"):
            inputs.setdefault(p["device"], set()).add(int(p.get("channel", 0)))
    for device, channels in inputs.items():
        if len(channels) > 1:
            found.append(f"device '{device}': receivers on different input channels "
                         f"({sorted(channels)}); one input channel per device is "
                         "recorded in this version")
    return found


def sim_devices(rig, layout):
    """The simulated devices of an as-built scene: one per rig device that
    carries a layout transducer, with its rate."""
    info = {t["id"] for t in layout.get("transducers", [])}
    out = []
    for d in rig.get("devices", []):
        mine = [t["id"] for t in rig.get("transducers", [])
                if t["device"] == d["id"] and t["id"] in info]
        if mine:
            out.append(s.device(d["id"], mine, rate=d.get("rate", 48000)))
    return out


def sim_loopbacks(rig, layout, gain=0.2):
    info = {t["id"] for t in layout.get("transducers", [])}
    return [dict(receiver=lb["receiver"], emitter=lb["emitter"],
                 gain=lb.get("gain", gain)) for lb in rig.get("loopbacks", [])
            if lb["receiver"] in info and lb["emitter"] in info]


def as_built_scene(rig, layout, layout_id, existing=None, name=None):
    """The data of the rig's as-built scene: structure from the rig, the rest
    (medium, planes, noise, reflectors) from `existing` or the defaults."""
    scene = copy.deepcopy(existing) if existing else s.new_scene(
        name or f"{rig['name']} (as built)", layout_id, [])
    scene["layout"] = layout_id
    scene["devices"] = sim_devices(rig, layout)
    scene["loopbacks"] = sim_loopbacks(rig, layout)
    scene["as_built_of"] = rig.get("name", "")
    if name:
        scene["name"] = name
    return scene


def create_rig(workspace, name, layout_id, devices, transducers, loopbacks=(),
               machine=None):
    """Make a rig and its as-built scene (one undo step). `machine` is the
    name of the computer whose devices it names (default: this one). Returns
    the rig ID."""
    machine = machine if machine is not None else machine_name()
    ws = workspace
    layout = ws.get("layouts", layout_id)
    if layout is None:
        raise WorkspaceError(f"no layout with ID '{layout_id}'")
    with ws.macro(f"add rig {name}"):
        rig_id = ws.create("rigs", name, s.new_rig("", layout_id, devices,
                                                   transducers, loopbacks,
                                                   machine=machine))
        sync_as_built(ws, rig_id)
    return rig_id


def update_rig(workspace, rig_id, text=None, **changes):
    """Change a rig and bring its as-built scene in step (one undo step)."""
    ws = workspace
    rig = ws.get("rigs", rig_id)
    if rig is not None and all(rig.get(k) == v for k, v in changes.items()):
        return                      # nothing would change: no empty undo step
    with ws.macro(text or f"edit rig {ws.name_of('rigs', rig_id)}"):
        ws.update("rigs", rig_id, **changes)
        sync_as_built(ws, rig_id)


def as_built_is_current(workspace, rig_id):
    """True if the rig has an as-built scene that is in step with it."""
    ws = workspace
    rig = ws.get("rigs", rig_id)
    scene = ws.get("scenes", rig.get("as_built") or "")
    layout = ws.get("layouts", rig["layout"])
    return bool(scene and layout and scene == as_built_scene(rig, layout, rig["layout"], scene))


def sync_as_built(workspace, rig_id):
    """Create the rig's as-built scene, or bring it in step with the rig and
    its layout. Does nothing if it already is. Returns the scene ID."""
    ws = workspace
    rig = ws.get("rigs", rig_id)
    layout = ws.get("layouts", rig["layout"])
    scene_id = rig.get("as_built")
    existing = ws.get("scenes", scene_id) if scene_id else None
    wanted = as_built_scene(rig, layout, rig["layout"], existing,
                            None if existing else f"{rig['name']} (as built)")
    if existing is None:
        scene_id = ws.create("scenes", wanted["name"], wanted)
        ws.update("rigs", rig_id, as_built=scene_id)
    elif wanted != existing:
        ws.replace("scenes", scene_id, wanted,
                   f"bring {existing['name']} in step with its rig")
    return scene_id


def delete_rig(workspace, rig_id):
    """Delete a rig and its as-built scene (one undo step), unless something
    else uses that scene."""
    ws = workspace
    rig = ws.get("rigs", rig_id)
    if rig is None:
        return
    with ws.macro(f"delete rig {rig['name']}"):
        ws.delete("rigs", rig_id)
        scene_id = rig.get("as_built")
        if scene_id and ws.exists("scenes", scene_id) and not ws.uses("scenes", scene_id):
            ws.delete("scenes", scene_id)


def is_as_built(workspace, scene_id):
    """The rig whose as-built scene this is, as an ID, or None."""
    for rig_id in workspace.ids("rigs"):
        if workspace.get("rigs", rig_id).get("as_built") == scene_id:
            return rig_id
    return None


# ---- what a page needs, and the template that fits ----------------------------

def near_pairs(layout, limit=NEAR_M):
    """(output ID, input ID, distance m) for every output of a layout that has
    an input within `limit` m of it, nearest first."""
    out = []
    ts = layout.get("transducers", [])
    for a in ts:
        for b in ts:
            if a.get("can_send") and b.get("can_receive") and a["id"] != b["id"]:
                d = sum((x - y) ** 2 for x, y in zip(a["position"], b["position"])) ** 0.5
                if d <= limit:
                    out.append((a["id"], b["id"], d))
    return sorted(out, key=lambda p: p[2])


LEFT, RIGHT, MIC = "left", "right", "mic"    # the laptop's transducers
SAME_CHIRP = "both_speakers_same_chirp"
UP_AND_DOWN = "both_speakers_up_and_down_chirps"
SPLIT_BANDS = "both_speakers_split_bands"
LEFT_THEN_RIGHT = "left_then_right"
LAPTOP_DEFAULT_DESIGN = SPLIT_BANDS        # the one that places targets best
# Laptop templates. The positions are guesses, not measurements: speakers near
# the left and right side edges, symmetric, and the microphone where Dell and
# Alienware laptops usually have it, in the display bezel by the webcam:
# centred, up in the screen (with the lid open) and a little behind the
# keyboard's front edge. The lid angle changes the height.
LAPTOP_TEMPLATES = {
    "17": dict(name="17-inch Alienware", spacing=0.34, behind=0.05, up=0.25,
               width_cm=40, layout=LAPTOP_LAYOUT, rig=LAPTOP_RIG, demo=LAPTOP_DEMO),
    "15": dict(name="15-inch Alienware", spacing=0.30, behind=0.05, up=0.22,
               width_cm=36, layout="15_inch_alienware", rig="15_inch_alienware_speakers_and_mic",
               demo="15_inch_alienware_in_a_room")}
LAPTOP_SPEAKER_SPACING_M = LAPTOP_TEMPLATES["17"]["spacing"]       # the default laptop
LAPTOP_MIC_BEHIND_M = LAPTOP_TEMPLATES["17"]["behind"]
LAPTOP_MIC_UP_M = LAPTOP_TEMPLATES["17"]["up"]


def laptop_note(size="17"):
    t = LAPTOP_TEMPLATES[size]
    return (f"Positions are a guess for a {t['name']} (about {t['width_cm']} cm wide): "
            f"speakers {100 * t['spacing']:.0f} cm apart, symmetric; microphone at the top "
            f"centre of the screen, {100 * t['up']:.0f} cm above them and "
            f"{100 * t['behind']:.0f} cm behind. Measure yours and edit them.")


LAPTOP_NOTE = laptop_note("17")


def machine_name():
    """This computer's name, as recorded on the rigs made here."""
    return socket.gethostname()


def on_wsl():
    """True when running under WSL: audio then goes through the Windows sound
    bridge, in shared mode only, and the bridge does not keep the spacing of
    events sent at different times."""
    if os.environ.get("WSL_DISTRO_NAME") or os.environ.get("WSL_INTEROP"):
        return True
    try:
        with open("/proc/version") as f:
            return "microsoft" in f.read().lower()
    except OSError:
        return False


def is_measured(layout):
    """False for a layout whose positions are a guess (the laptop's, until a
    person has entered their own)."""
    return layout.get("measured", True) if layout else True


def laptop_layout(size="17"):
    """A laptop of one of the LAPTOP_TEMPLATES: two speakers and a microphone
    at the top centre of the screen; x across, y forward (towards the room),
    z up. The positions are guesses and the layout says so (`measured`
    False)."""
    t = LAPTOP_TEMPLATES[size]
    half = t["spacing"] / 2.0
    return s.new_layout("", [
        s.transducer(LEFT, "Left speaker", (-half, 0.0, 0.0), can_send=True),
        s.transducer(RIGHT, "Right speaker", (half, 0.0, 0.0), can_send=True),
        s.transducer(MIC, "Microphone", (0.0, -t["behind"], t["up"]), can_receive=True)],
        measured=False, note=laptop_note(size))


def old_laptop_layout(layout):
    """True for the layout the laptop template made before it had two speakers
    (one speaker and a microphone 0.2 m apart)."""
    return bool(layout) and {t["id"] for t in layout.get("transducers", [])} == {"speaker", "mic"}


def stereo_outputs(layout, limit=NEAR_M):
    """(left ID, right ID, input ID) for a layout with two outputs close to
    one input, the two outputs ordered by x; None if it has no such trio."""
    ts = layout.get("transducers", []) if layout else []
    for mic in (t for t in ts if t.get("can_receive")):
        near = [t for t in ts if t.get("can_send") and t["id"] != mic["id"]
                and sum((x - y) ** 2 for x, y in zip(t["position"], mic["position"])) ** 0.5 <= limit]
        if len(near) >= 2:
            near = sorted(near, key=lambda t: t["position"][0])
            return near[0]["id"], near[-1]["id"], mic["id"]
    return None


def ensure_stereo_designs(workspace, left=LEFT, right=RIGHT):
    """Make, if they are not there, the signals and the ping designs for two
    speakers and one microphone: both speakers with the same chirp; with an
    up- and a down-chirp of one band; with two separate bands; and the left
    then the right. Names are plain; IDs are made from them. Returns the
    list of the designs' IDs. Does not change anything that exists."""
    ws = workspace
    detection = ws.ids("detection_designs")
    named = detection[0] if detection else None
    made = []
    with ws.macro("add the two-speaker ping designs"):
        if not ws.exists("signals", LAPTOP_SIGNAL):
            ws.create("signals", "room chirp", s.new_chirp("", 2000, 20000, 0.01, amplitude=0.3))
        if not ws.exists("signals", "room_chirp_down"):
            ws.create("signals", "room chirp down", s.new_derived("", "time_reverse", LAPTOP_SIGNAL))
        if not ws.exists("signals", "room_low_band"):
            ws.create("signals", "room low band", s.new_chirp("", 2000, 10000, 0.01, amplitude=0.3))
        if not ws.exists("signals", "room_high_band"):
            ws.create("signals", "room high band", s.new_chirp("", 11000, 20000, 0.01, amplitude=0.3))
        wanted = (
            ("both speakers, same chirp", SAME_CHIRP,
             [(left, LAPTOP_SIGNAL, 0.0), (right, LAPTOP_SIGNAL, 0.0)]),
            ("both speakers, up and down chirps", UP_AND_DOWN,
             [(left, LAPTOP_SIGNAL, 0.0), (right, "room_chirp_down", 0.0)]),
            ("both speakers, split bands", SPLIT_BANDS,
             [(left, "room_low_band", 0.0), (right, "room_high_band", 0.0)]),
            ("left then right", LEFT_THEN_RIGHT,
             [(left, LAPTOP_SIGNAL, 0.0), (right, LAPTOP_SIGNAL, 0.08)]))
        for name, design_id, events in wanted:
            if not ws.exists("ping_designs", design_id):
                ws.create("ping_designs", name, s.new_design(
                    "", [dict(transducer=t, signal=sig, time=at) for t, sig, at in events],
                    receivers=[MIC], listen=0.04, roles=["bench"], detection_design=named))
                made.append(design_id)
    return made


def laptop_template(workspace, size="17"):
    """Make what the room sonar needs on a laptop of one of the
    LAPTOP_TEMPLATES ("17": 17-inch Alienware, "15": 15-inch Alienware), if it
    is not there yet: the layout (two speakers and a microphone, positions a
    guess), a rig on the built-in card (borrowed from the desktop, the mixer
    left alone; under WSL shared through the Windows sound bridge, the only way
    there; the speakers on its left and right outputs; the machine's name is
    kept on it), the rig's as-built scene, a demo scene of a room with people
    walking about, a room chirp, the ping design for one speaker and the
    two-speaker designs. A 17-inch laptop made before it had two speakers is
    brought up to date. Returns a dict of IDs: layout, rig, as_built, demo,
    signal, design (the one for the room sonar to start with), and upgraded
    (True if an older laptop was changed)."""
    ws = workspace
    spec = LAPTOP_TEMPLATES[size]
    layout_id, rig_id, demo_id = spec["layout"], spec["rig"], spec["demo"]
    upgraded = False
    with ws.macro(f"add the {spec['name']} laptop speakers and microphone"):
        old = ws.get("layouts", layout_id)
        if old is None:
            ws.create("layouts", spec["name"] if size != "17" else "Laptop", laptop_layout(size))
        elif size == "17" and old_laptop_layout(old):
            upgraded = True
            ws.replace("layouts", layout_id, dict(laptop_layout(size), name=old["name"]))
        rig_transducers = [dict(id=LEFT, device="laptop", channel="left"),
                           dict(id=RIGHT, device="laptop", channel="right"),
                           dict(id=MIC, device="laptop", channel=0)]
        if not ws.exists("rigs", rig_id):
            wsl = on_wsl()
            device = s.device_config("laptop", access="shared" if wsl else "exclusive",
                                     mixer={} if wsl else dict(LAPTOP_MIXER))
            create_rig(ws, "Laptop speaker and mic" if size == "17" else f"{spec['name']} speakers and mic",
                       layout_id, devices=[device], transducers=rig_transducers,
                       machine=machine_name())
        elif upgraded:
            update_rig(ws, rig_id, transducers=rig_transducers)
        rig = ws.get("rigs", rig_id)
        if not ws.exists("signals", LAPTOP_SIGNAL):
            ws.create("signals", "room chirp",
                      s.new_chirp("", 2000, 20000, 0.01, amplitude=0.3))
        if not ws.exists("ping_designs", LAPTOP_DESIGN):
            detection = ws.ids("detection_designs")
            ws.create("ping_designs", "room chirp from the laptop", s.new_design(
                "", [dict(transducer=LEFT, signal=LAPTOP_SIGNAL, time=0.0)],
                receivers=[MIC], listen=0.04, roles=["bench"],
                detection_design=detection[0] if detection else None))
        elif upgraded:
            design = ws.get("ping_designs", LAPTOP_DESIGN)
            ws.update("ping_designs", LAPTOP_DESIGN, events=[
                dict(e, transducer=LEFT if e["transducer"] == "speaker" else e["transducer"])
                for e in design["events"]])
        ensure_stereo_designs(ws)
        if not ws.exists("scenes", demo_id):
            built = ws.get("scenes", rig["as_built"])
            demo = copy.deepcopy(built)
            demo.pop("as_built_of", None)
            demo.update(room_scene(demo))
            ws.create("scenes", "Laptop in a room" if size == "17" else f"{spec['name']} in a room", demo)
        elif upgraded:
            demo = ws.get("scenes", demo_id)
            built = ws.get("scenes", rig["as_built"])
            ws.update("scenes", demo_id, devices=copy.deepcopy(built["devices"]),
                      loopbacks=copy.deepcopy(built["loopbacks"]),
                      movers=room_scene(demo)["movers"])
    return dict(layout=layout_id, rig=rig_id, as_built=rig["as_built"],
                demo=demo_id, signal=LAPTOP_SIGNAL, design=LAPTOP_DEFAULT_DESIGN,
                upgraded=upgraded)


def room_scene(scene):
    """The parts of a room for a scene whose laptop sits at the origin, the
    front of the room towards +y: walls, a ceiling, a cabinet and a chair
    (fixed), and a person and a trolley moving back and forth in front of it."""
    planes = [
        dict(name="front wall", point=[0.0, 3.5, 0.0], normal=[0.0, -1.0, 0.0],
             reflection=0.5),
        dict(name="left wall", point=[-2.0, 0.0, 0.0], normal=[1.0, 0.0, 0.0],
             reflection=0.4),
        dict(name="right wall", point=[2.5, 0.0, 0.0], normal=[-1.0, 0.0, 0.0],
             reflection=0.4),
        dict(name="ceiling", point=[0.0, 0.0, 1.4], normal=[0.0, 0.0, -1.0],
             reflection=0.3)]
    reflectors = [
        dict(name="cabinet", position=[-1.2, 1.2, 0.0], strength=1.0),
        dict(name="chair", position=[1.3, 2.0, -0.2], strength=0.8)]
    movers = [dict(name="person", a=[-0.3, 1.3, 0.0], b=[0.4, 2.8, 0.0],
                   speed=0.5, strength=1.5),
              dict(name="trolley", a=[1.1, 0.8, 0.0], b=[0.9, 2.3, 0.0],
                   speed=0.3, strength=1.0)]
    return dict(planes=planes, reflectors=reflectors, movers=movers)
