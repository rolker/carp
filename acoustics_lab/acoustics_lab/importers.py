"""Bringing in what carp/acoustic made.

Ping designs (acoustic/designs/*.json): each signal becomes a signal object
and each design a ping design, in the workspace. The old output channels
`left` and `right` become transducers of the same names in the "stereo
dongle" layout, which also gets simulated scenes, and the user can rename
them. Recordings (acoustic/runs/) need no import: they open in replay
(backends/replay.py).
"""
import json
from pathlib import Path

from .objects import schema as s
from .objects.starter import ensure_stereo_dongle


def _same_chirp(data, new):
    return data.get("type") == "chirp" and all(
        data.get(k) == new[k] for k in ("f0", "f1", "duration", "amplitude"))


def import_designs(workspace, folder):
    """Import every design file in a folder. Safe to repeat: signals and
    designs that are already there, unchanged, are reused. Returns a list of
    messages for the user, one per file."""
    ws, messages = workspace, []
    files = sorted(Path(folder).glob("*.json"))
    if not files:
        return [f"no .json design files in {folder}"]
    with ws.macro("import carp/acoustic designs"):
        ensure_stereo_dongle(ws)
        for file in files:
            try:
                messages.append(_import_one(ws, file))
            except (ValueError, KeyError, OSError) as error:
                messages.append(f"{file.name}: skipped ({error})")
    return messages


def _import_one(ws, file):
    with open(file) as f:
        old = json.load(f)
    if "signals" not in old or "events" not in old:
        raise ValueError("not a ping design")
    ids = {}
    for sig in old["signals"]:
        new = s.new_chirp(sig["name"], sig["f0"], sig["f1"], sig["duration"],
                          sig.get("amplitude", 0.5))
        match = next((i for i in ws.ids("signals")
                      if ws.get("signals", i)["name"] == sig["name"]
                      and _same_chirp(ws.get("signals", i), new)), None)
        if match is None:
            clash = any(ws.get("signals", i)["name"] == sig["name"]
                        for i in ws.ids("signals"))
            name = f"{sig['name']} ({file.stem})" if clash else sig["name"]
            match = ws.create("signals", name, new)
        ids[sig["name"]] = match
    events = [dict(transducer=e["channel"], signal=ids[e["signal"]], time=e["time"])
              for e in old["events"]]
    design = s.new_design(file.stem, events, receivers=["mic"])
    for i in ws.ids("ping_designs"):
        existing = ws.get("ping_designs", i)
        if existing["name"] == file.stem and existing["events"] == design["events"]:
            return f"{file.name}: already imported"
    ws.create("ping_designs", file.stem, design)
    return f"{file.name}: imported ({len(ids)} signals, {len(events)} events)"
