"""The stereo-dongle bench, as a layout and simulated scenes, and the
objects a new workspace starts with."""
from ..models import detection_design
from . import rigs
from . import schema as s

DEFAULT_DETECTION = "default_arrival_detection"
LAYOUT = "stereo_dongle"
BENCH = "dongle_bench"
BENCH_LOOPBACK = "dongle_bench_loopback"


def ensure_stereo_dongle(workspace):
    """Make the 'stereo dongle' layout and two simulated scenes of it if
    they are not there: a stereo USB sound device with two outputs (left,
    right) and one input (mic), with and without an electrical loopback of
    both outputs into the input. Returns (layout ID, bench scene ID, bench
    with loopback scene ID).

    The positions stand in for a bench: the left output at the origin, the
    right 0.4 m behind it, the mic 1.5 m in front, and a wall 1 m to the
    side that makes an echo.
    """
    ws = workspace
    if not ws.exists("layouts", LAYOUT):
        ws.create("layouts", "Stereo dongle", s.new_layout("", [
            s.transducer("left", "Left output", (0, 0, 0), can_send=True),
            s.transducer("right", "Right output", (-0.4, 0, 0), can_send=True),
            s.transducer("mic", "Microphone", (1.5, 0, 0), can_receive=True)]))
    device = s.device("dongle", ["left", "right", "mic"])
    wall = dict(name="wall", point=[0.0, 1.0, 0.0], normal=[0.0, -1.0, 0.0],
                reflection=0.3)
    if not ws.exists("scenes", BENCH):
        ws.create("scenes", "Dongle bench",
                  s.new_scene("", LAYOUT, [device], planes=[wall]))
    if not ws.exists("scenes", BENCH_LOOPBACK):
        loopbacks = [dict(receiver="mic", emitter=e, gain=0.2) for e in ("left", "right")]
        ws.create("scenes", "Dongle bench loopback",
                  s.new_scene("", LAYOUT, [device], loopbacks=loopbacks, planes=[wall]))
    return LAYOUT, BENCH, BENCH_LOOPBACK


def ensure_default_detection(workspace):
    """Make the default detection design if the workspace has none at all
    (a new workspace, or one from before detection designs). Returns its ID,
    or None if the workspace already has detection designs."""
    ws = workspace
    if ws.ids("detection_designs"):
        return None
    return ws.create("detection_designs", detection_design.DEFAULT.name,
                     detection_design.new_default())


def populate(workspace):
    """What a new workspace starts with: the default detection design, the
    dongle bench, a few signals (one of them derived) and two ping designs
    that name the default detection design, and the ping designs for two
    speakers and a microphone (they name transducers "left", "right" and "mic",
    which the dongle bench and the laptop both have)."""
    ws = workspace
    with ws.macro("start the workspace"):
        ensure_default_detection(ws)
        ensure_stereo_dongle(ws)
        up = ws.create("signals", "chirp up", s.new_chirp("", 2000, 20000, 0.02))
        ws.create("signals", "chirp down", s.new_chirp("", 20000, 2000, 0.02))
        hi = ws.create("signals", "16-20 up", s.new_chirp("", 16000, 20000, 0.04))
        ws.create("signals", "16-20 down", s.new_derived("", "time_reverse", hi))
        low = ws.create("signals", "low band", s.new_chirp("", 2000, 9000, 0.03))
        high = ws.create("signals", "high band", s.new_chirp("", 11000, 20000, 0.03))
        ws.create("ping_designs", "left then right", s.new_design("", [
            dict(transducer="left", signal=up, time=0.0),
            dict(transducer="right", signal=up, time=0.15)],
            detection_design=DEFAULT_DETECTION))
        ws.create("ping_designs", "two bands at once", s.new_design("", [
            dict(transducer="left", signal=low, time=0.0),
            dict(transducer="right", signal=high, time=0.0)],
            detection_design=DEFAULT_DETECTION))
        rigs.ensure_stereo_designs(ws)
    ws.undo_stack.clear()
