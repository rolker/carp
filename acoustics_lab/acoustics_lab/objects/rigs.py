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


def create_rig(workspace, name, layout_id, devices, transducers, loopbacks=()):
    """Make a rig and its as-built scene (one undo step). Returns the rig ID."""
    ws = workspace
    layout = ws.get("layouts", layout_id)
    if layout is None:
        raise WorkspaceError(f"no layout with ID '{layout_id}'")
    with ws.macro(f"add rig {name}"):
        rig_id = ws.create("rigs", name, s.new_rig("", layout_id, devices,
                                                   transducers, loopbacks))
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


def laptop_layout():
    """A laptop: speaker and microphone 0.2 m apart on the same device."""
    return s.new_layout("", [
        s.transducer("speaker", "Speaker", (0.0, 0.0, 0.0), can_send=True),
        s.transducer("mic", "Microphone", (0.2, 0.0, 0.0), can_receive=True)])


def laptop_template(workspace):
    """Make what the room sonar needs on a laptop, if it is not there yet:
    the layout (speaker and microphone), a rig on the built-in card (borrowed
    from the desktop, the mixer left alone), the rig's as-built scene, a demo
    scene of a room with a person walking about, a room chirp and a ping
    design for it. Returns a dict of IDs: layout, rig, as_built, demo,
    signal, design."""
    ws = workspace
    with ws.macro("add the laptop speaker and microphone"):
        if not ws.exists("layouts", LAPTOP_LAYOUT):
            ws.create("layouts", "Laptop", laptop_layout())
        if not ws.exists("rigs", LAPTOP_RIG):
            create_rig(
                ws, "Laptop speaker and mic", LAPTOP_LAYOUT,
                devices=[s.device_config("laptop", mixer=dict(LAPTOP_MIXER))],
                transducers=[dict(id="speaker", device="laptop", channel="left"),
                             dict(id="mic", device="laptop", channel=0)])
        rig = ws.get("rigs", LAPTOP_RIG)
        if not ws.exists("signals", LAPTOP_SIGNAL):
            ws.create("signals", "room chirp",
                      s.new_chirp("", 2000, 20000, 0.01, amplitude=0.3))
        if not ws.exists("ping_designs", LAPTOP_DESIGN):
            detection = ws.ids("detection_designs")
            ws.create("ping_designs", "room chirp from the laptop", s.new_design(
                "", [dict(transducer="speaker", signal=LAPTOP_SIGNAL, time=0.0)],
                receivers=["mic"], listen=0.04, roles=["bench"],
                detection_design=detection[0] if detection else None))
        if not ws.exists("scenes", LAPTOP_DEMO):
            built = ws.get("scenes", rig["as_built"])
            demo = copy.deepcopy(built)
            demo.pop("as_built_of", None)
            demo.update(room_scene(demo))
            ws.create("scenes", "Laptop in a room", demo)
    return dict(layout=LAPTOP_LAYOUT, rig=LAPTOP_RIG, as_built=rig["as_built"],
                demo=LAPTOP_DEMO, signal=LAPTOP_SIGNAL, design=LAPTOP_DESIGN)


def room_scene(scene):
    """The parts of a room for a scene whose laptop sits at the origin, the
    front of the room towards +y: walls, a ceiling, a cabinet and a chair
    (fixed), and a person walking back and forth in front of it."""
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
                   speed=0.5, strength=1.5)]
    return dict(planes=planes, reflectors=reflectors, movers=movers)
