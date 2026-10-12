"""What the workspace's objects look like, and how they refer to each other.

Objects are plain dicts (the JSON in the files). Their kind is the folder
they live in. This module knows the shapes, the references between kinds
and the checks on a change; it does not touch files or Qt.

  signals/<id>.json   a waveform: a chirp or tone, or one derived from another
  designs/<id>.json   a ping design: which signal goes out of which
                      transducer at what time, and who listens
  layouts/<id>.json   transducers: where they are and what they can do
  scenes/<id>.json    what the simulator simulates: a layout, a medium,
                      noise, devices and loopbacks
"""
import copy
import re

KINDS = ("signals", "designs", "layouts", "scenes")
SINGULAR = {"signals": "signal", "designs": "design", "layouts": "layout",
            "scenes": "scene"}

DERIVED_OPS = ("time_reverse", "invert")


class WorkspaceError(ValueError):
    """A change the workspace refuses. The message says why, for a person."""


class InUseError(WorkspaceError):
    """Something is still used by other objects, listed in `users`."""

    def __init__(self, what, users):
        self.users = users
        super().__init__(
            f"{what} is used by " + ", ".join(f"{k[:-1]} '{i}'" for k, i in users)
            + "; delete or repoint those first")


def slug(name, fallback="item"):
    """A short readable ID from a name: lower case letters, digits and
    underscores. 'Chirp up 2-20k' becomes 'chirp_up_2_20k'."""
    text = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    return text or fallback


def unique_id(name, taken, fallback="item"):
    """slug(name), with _2, _3... added if it is already taken."""
    base = slug(name, fallback)
    candidate, n = base, 1
    while candidate in taken:
        n += 1
        candidate = f"{base}_{n}"
    return candidate


def references(kind, data):
    """The objects this one points at, as a set of (kind, id)."""
    refs = set()
    if kind == "signals" and data.get("type") == "derived":
        refs.add(("signals", data.get("source", "")))
    elif kind == "designs":
        for event in data.get("events", []):
            refs.add(("signals", event.get("signal", "")))
    elif kind == "scenes":
        refs.add(("layouts", data.get("layout", "")))
    return refs


def derived_chain_has_cycle(get, signal_id, data):
    """True if signal `signal_id`, with contents `data`, would be derived
    from itself through any chain. `get(id)` returns another signal's dict
    or None."""
    seen = {signal_id}
    current = data
    while current is not None and current.get("type") == "derived":
        source = current.get("source", "")
        if source in seen:
            return True
        seen.add(source)
        current = get(source)
    return False


def check(kind, data, exists, get_signal):
    """Raise WorkspaceError if `data` is not acceptable as a `kind` object.

    exists(kind, id) says whether another object is there; get_signal(id)
    gives a signal's dict. `data["name"]` must be a non-empty string.
    """
    if not isinstance(data.get("name"), str) or not data["name"].strip():
        raise WorkspaceError("every object needs a name")
    for ref_kind, ref_id in sorted(references(kind, data)):
        if not exists(ref_kind, ref_id):
            raise WorkspaceError(f"no {SINGULAR[ref_kind]} with ID '{ref_id}'")
    if kind == "signals":
        if data.get("type") == "chirp":
            for key in ("f0", "f1", "duration", "amplitude"):
                if not isinstance(data.get(key), (int, float)):
                    raise WorkspaceError(f"signal needs a number for {key}")
            if data["duration"] <= 0:
                raise WorkspaceError("the length must be above zero")
            if min(data["f0"], data["f1"]) < 0:
                raise WorkspaceError("frequencies cannot be negative")
            if not 0 <= data["amplitude"] <= 1:
                raise WorkspaceError("the level must be between 0 and 1")
        elif data.get("type") == "derived":
            if data.get("op") not in DERIVED_OPS:
                raise WorkspaceError(f"unknown operation {data.get('op')!r}")
        else:
            raise WorkspaceError(f"unknown signal type {data.get('type')!r}")
    elif kind == "designs":
        for event in data.get("events", []):
            if not event.get("transducer"):
                raise WorkspaceError("every event needs a transducer")
            if event.get("time", 0) < 0:
                raise WorkspaceError("event times cannot be negative")
        if data.get("listen", 0.3) < 0:
            raise WorkspaceError("the listening time cannot be negative")
    elif kind == "layouts":
        ids = [t.get("id") for t in data.get("transducers", [])]
        if len(set(ids)) != len(ids) or not all(ids):
            raise WorkspaceError("transducer IDs must be present and unique")


def new_chirp(name, f0=2000.0, f1=20000.0, duration=0.02, amplitude=0.5,
              taper=1.0):
    """A chirp signal's data. Equal f0 and f1 make a tone."""
    return dict(name=name, type="chirp", f0=float(f0), f1=float(f1),
                duration=float(duration), amplitude=float(amplitude),
                taper=float(taper))


def new_derived(name, op, source):
    """A signal derived from another by `op` (one of DERIVED_OPS)."""
    return dict(name=name, type="derived", op=op, source=source)


def new_design(name, events=(), receivers=("mic",), listen=0.3, roles=("bench",)):
    """A ping design's data. events are dicts with transducer, signal and
    time (s after the start of the ping)."""
    return dict(name=name, roles=list(roles), receivers=list(receivers),
                listen=float(listen), events=[dict(e) for e in events])


def copy_of(data):
    return copy.deepcopy(data)


def transducer(tid, name, position, can_send=False, can_receive=False,
               facing=(0.0, 0.0, 1.0), element="point"):
    """One transducer of a layout. position is x, y, z in m; facing is the
    direction it points (unused until directivity arrives, with element)."""
    return dict(id=tid, name=name, position=[float(v) for v in position],
                facing=[float(v) for v in facing], element=element,
                can_send=can_send, can_receive=can_receive)


def new_layout(name, transducers):
    return dict(name=name, transducers=list(transducers))


def new_scene(name, layout, devices, loopbacks=(), planes=(), temperature_c=20.0,
              link_gain=0.15, noise_rms=0.003, lead_in=0.1, seed=1):
    """A scene's data. link_gain is the amplitude one metre from a point
    transducer per unit of output signal, standing in for the sensitivities
    of real transducers until rigs hold them."""
    return dict(
        name=name, layout=layout,
        medium=dict(type="air", temperature_c=float(temperature_c),
                    absorption_db_per_m_per_khz2=0.0015),
        planes=[dict(p) for p in planes],
        link_gain=float(link_gain), lead_in=float(lead_in),
        noise=dict(rms=float(noise_rms), slope_db_per_octave=0.0, seed=seed),
        devices=[dict(d) for d in devices],
        loopbacks=[dict(lb) for lb in loopbacks])


def device(device_id, transducers, rate=48000, clock_offset=0.0,
           clock_drift_ppm=0.0, start_delay=0.0):
    """A simulated sound device: its transducers, sample rate and clock."""
    return dict(id=device_id, transducers=list(transducers), rate=rate,
                clock_offset=clock_offset, clock_drift_ppm=clock_drift_ppm,
                start_delay=start_delay)
