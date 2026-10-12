"""The desktop's own volumes for a sound card: save, restore, verify.

The desktop's sound server (PipeWire with WirePlumber, speaking the
PulseAudio protocol to programs) keeps its own volume and mute for every
sink (speaker, headphones) and source (microphone) it makes from a sound
card. When a test borrows the card (`reserve`) those sinks and sources
disappear; when it is given back, WirePlumber makes them again and may apply
what it saw of the hardware mixer meanwhile. On real hardware the built-in
speaker volume went 0.13 -> 0.56 and the microphone 0.70 -> 0.15 that way.
Restoring the hardware mixer is therefore not enough, so:

1. `save(card)` before borrowing: volume (per channel) and mute of every
   sink and source of the card, and which ones are the defaults;
2. the test runs and the mixer is put back (`mixer.restore`) before the card
   is given back, as before;
3. `restore(saved)` after the card is given back: waits (with a timeout) for
   the server to make the sinks and sources again, waits a moment for it to
   finish its own setup, sets the saved volume and mute, and reads them back
   to be sure they stayed. It reports each one plainly.

Volumes are fractions where 1.0 is 100 % (the number `wpctl get-volume`
prints, and what the PulseAudio protocol calls 65536). A sink or source
belongs to a card by its `alsa.card` (or `api.alsa.card`) property.

Backends, all with `nodes()`, `set_volume(node, volumes)`, `set_mute(node,
mute)` and `defaults()`:

- `PulsectlBackend`: python3-pulsectl, a binding of libpulse (apt:
  python3-pulsectl), the right way;
- `PactlBackend`: the `pactl` command with its JSON output, used with a
  warning when pulsectl cannot be imported;
- none: `default_backend()` returns None and the callers warn that the
  desktop volumes are not protected.

Tests use a fake with the same methods.
"""
import json
import logging
import os
import shutil
import subprocess
import time
from dataclasses import dataclass, field

log = logging.getLogger(__name__)

SINK = "sink"
SOURCE = "source"
TOLERANCE = 0.005                 # volumes this close are the same (the
                                  # protocol keeps 1/65536 steps)
INVALID_INDEX = 0xFFFFFFFF
TIMEOUT_S = 15.0                  # wait for the server to make the nodes again
SETTLE_S = 1.0                    # let it finish its own setup, and check
POLL_S = 0.25
RAW_FULL = 65536                  # the protocol's raw value for 1.0

UNCHANGED = "unchanged"           # was already as saved
RESTORED = "restored"             # was different, set back and read back
MISSING = "missing"               # the server never made it again
DIFFERS = "differs"               # set, but it did not stay as saved


class DesktopError(Exception):
    """The sound server cannot be reached or refused."""


@dataclass
class Node:
    """A sink or source of the sound server."""
    kind: str                     # SINK or SOURCE
    name: str                     # the server's name for it
    index: int = 0
    card: int = None              # ALSA card number, if it is on one
    description: str = ""
    volumes: list = field(default_factory=list)    # per channel, 1.0 = 100 %
    mute: bool = False

    def label(self):
        return f"{self.kind} '{self.description or self.name}'"

    def volume_text(self):
        return volume_text(self.volumes, self.mute)


def volume_text(volumes, mute=False):
    """"0.13", "0.13/0.20" for unequal channels, and ", muted"."""
    if not volumes:
        text = "no volume"
    elif max(volumes) - min(volumes) < 0.0005:
        text = f"{volumes[0]:.2f}"
    else:
        text = "/".join(f"{v:.2f}" for v in volumes)
    return text + (", muted" if mute else "")


def card_of(properties):
    """The ALSA card number in a sink's or source's properties, or None."""
    for key in ("alsa.card", "api.alsa.card"):
        value = properties.get(key)
        try:
            return int(value)
        except (TypeError, ValueError):
            continue
    return None


# -- backends -----------------------------------------------------------------

class PulsectlBackend:
    """The sound server through python3-pulsectl (libpulse)."""
    name = "pulsectl"

    def __init__(self, client="acoustics_lab"):
        import pulsectl
        self.pulsectl = pulsectl
        self.client = client

    def _connect(self):
        try:
            return self.pulsectl.Pulse(self.client)
        except self.pulsectl.PulseError as error:
            raise DesktopError(f"cannot reach the sound server: {error}")

    def nodes(self):
        out = []
        with self._connect() as pulse:
            try:
                for kind, items in ((SINK, pulse.sink_list()),
                                    (SOURCE, pulse.source_list())):
                    for item in items:
                        if kind == SOURCE and _is_monitor(
                                item.name, getattr(item, "monitor_of_sink", None)):
                            continue
                        out.append(Node(kind, item.name, item.index,
                                        card_of(item.proplist), item.description,
                                        [float(v) for v in item.volume.values],
                                        bool(item.mute)))
            except self.pulsectl.PulseError as error:
                raise DesktopError(f"cannot list sinks and sources: {error}")
        return out

    def _find(self, pulse, node):
        items = pulse.sink_list() if node.kind == SINK else pulse.source_list()
        for item in items:
            if item.name == node.name:
                return item
        raise DesktopError(f"{node.label()} is gone")

    def set_volume(self, node, volumes):
        with self._connect() as pulse:
            try:
                item = self._find(pulse, node)
                pulse.volume_set(item, self.pulsectl.PulseVolumeInfo(list(volumes)))
            except self.pulsectl.PulseError as error:
                raise DesktopError(f"cannot set the volume of {node.label()}: {error}")

    def set_mute(self, node, mute):
        with self._connect() as pulse:
            try:
                pulse.mute(self._find(pulse, node), bool(mute))
            except self.pulsectl.PulseError as error:
                raise DesktopError(f"cannot set the mute of {node.label()}: {error}")

    def defaults(self):
        """(default sink name, default source name)."""
        with self._connect() as pulse:
            try:
                info = pulse.server_info()
            except self.pulsectl.PulseError as error:
                raise DesktopError(f"cannot read the server: {error}")
            return info.default_sink_name, info.default_source_name


def _is_monitor(name, monitor_of):
    return name.endswith(".monitor") or monitor_of not in (None, INVALID_INDEX)


def run_pactl(args):
    """Text printed by `pactl` with these arguments (C locale)."""
    path = shutil.which("pactl")
    if path is None:
        raise DesktopError("pactl is not installed (apt: pulseaudio-utils)")
    env = dict(os.environ, LC_ALL="C")
    result = subprocess.run([path] + list(args), capture_output=True, text=True,
                            env=env, timeout=10)
    if result.returncode:
        raise DesktopError(f"pactl {' '.join(args)}: "
                           f"{(result.stderr or result.stdout).strip()}")
    return result.stdout


class PactlBackend:
    """The sound server through the `pactl` command (`--format=json`); the
    fallback where python3-pulsectl is not installed. `runner(args)` returns
    pactl's text (tests pass a fake)."""
    name = "pactl"

    def __init__(self, runner=run_pactl):
        self.runner = runner

    def nodes(self):
        out = []
        for kind, word in ((SINK, "sinks"), (SOURCE, "sources")):
            try:
                items = json.loads(self.runner(["--format=json", "list", word]))
            except ValueError as error:
                raise DesktopError(f"pactl list {word}: unreadable output ({error})")
            for item in items:
                if kind == SOURCE and _is_monitor(
                        item.get("name", ""), item.get("monitor_of_sink")):
                    continue
                channels = (item.get("volume") or {}).values()
                out.append(Node(kind, item["name"], item.get("index", 0),
                                card_of(item.get("properties") or {}),
                                item.get("description", ""),
                                [c["value"] / RAW_FULL for c in channels],
                                bool(item.get("mute"))))
        return out

    def set_volume(self, node, volumes):
        raw = [str(int(round(v * RAW_FULL))) for v in volumes]
        self.runner([f"set-{node.kind}-volume", node.name] + raw)

    def set_mute(self, node, mute):
        self.runner([f"set-{node.kind}-mute", node.name, "1" if mute else "0"])

    def defaults(self):
        return (self.runner(["get-default-sink"]).strip(),
                self.runner(["get-default-source"]).strip())


def default_backend():
    """(backend, note): pulsectl where it imports; else pactl, with a note to
    show as a warning; else (None, note) - the desktop volumes then cannot be
    protected."""
    try:
        return PulsectlBackend(), ""
    except ImportError:
        pass
    if shutil.which("pactl"):
        return PactlBackend(), ("python3-pulsectl is not installed (apt: "
                                "python3-pulsectl); using the pactl command "
                                "for the desktop volumes instead")
    return None, ("neither python3-pulsectl nor pactl is available (apt: "
                  "python3-pulsectl): the desktop's volumes cannot be saved")


# -- save ---------------------------------------------------------------------

@dataclass
class Saved:
    """The desktop's volumes for one card, from `save`."""
    card: int
    nodes: list = field(default_factory=list)
    default_sink: str = ""
    default_source: str = ""
    backend: str = ""

    def lines(self):
        if not self.nodes:
            return [f"The desktop has no sink or source on card {self.card}: "
                    "no desktop volumes to save."]
        return [f"Desktop volumes saved for card {self.card}: "
                + "; ".join(f"{n.label()} {n.volume_text()}" for n in self.nodes)
                + f" (through {self.backend})."]


def nodes_of_card(nodes, card):
    return [n for n in nodes if n.card == card]


def save(card, backend):
    """The volume and mute of every sink and source of ALSA card `card`, and
    the server's defaults. Raises DesktopError."""
    saved = Saved(card, nodes_of_card(backend.nodes(), card), backend=backend.name)
    try:
        saved.default_sink, saved.default_source = backend.defaults()
    except DesktopError as error:
        log.info("defaults not read: %s", error)
    return saved


# -- restore ------------------------------------------------------------------

def _strip(name):
    """A node name without the numeric suffix the server adds on re-creating
    it ("alsa_output....analog-stereo.14")."""
    head, dot, tail = name.rpartition(".")
    return head if dot and tail.isdigit() else name


def match(saved_nodes, current):
    """{saved index: current Node} for the saved nodes that exist again: by
    name, else by name without its numeric suffix, else the only one of its
    kind on the card."""
    found = {}
    taken = set()
    for i, node in enumerate(saved_nodes):
        for test in (lambda c: c.name == node.name,
                     lambda c: _strip(c.name) == _strip(node.name)):
            hit = [c for c in current if c.kind == node.kind
                   and c.name not in taken and test(c)]
            if len(hit) == 1:
                found[i] = hit[0]
                taken.add(hit[0].name)
                break
    for i, node in enumerate(saved_nodes):
        if i in found:
            continue
        same = [n for n in saved_nodes if n.kind == node.kind]
        free = [c for c in current if c.kind == node.kind and c.name not in taken]
        if len(same) == 1 and len(free) == 1:
            found[i] = free[0]
            taken.add(free[0].name)
    return found


def same(a, b):
    """True when two nodes have the same volumes and mute."""
    if bool(a.mute) != bool(b.mute):
        return False
    if len(a.volumes) != len(b.volumes):
        return False
    return all(abs(x - y) <= TOLERANCE for x, y in zip(a.volumes, b.volumes))


@dataclass
class Entry:
    saved: Node
    status: str
    now: Node = None              # as last read, if it exists
    first_seen: str = ""          # volume text before it was put back

    def line(self):
        label = self.saved.label()
        if self.status == UNCHANGED:
            return f"{label}: {self.saved.volume_text()}, as before."
        if self.status == RESTORED:
            return (f"{label}: put back to {self.saved.volume_text()} "
                    f"(was {self.first_seen}).")
        if self.status == MISSING:
            return f"{label}: the sound server has not made it again."
        return (f"{label}: should be {self.saved.volume_text()} but is "
                f"{self.now.volume_text()}.")


@dataclass
class Result:
    card: int
    entries: list = field(default_factory=list)
    waited: float = 0.0           # s until the server had made them again
    default_changes: list = field(default_factory=list)   # text lines
    error: str = ""

    @property
    def ok(self):
        return not self.error and all(e.status in (UNCHANGED, RESTORED)
                                      for e in self.entries)

    def lines(self):
        out = []
        if self.error:
            out.append(f"Desktop volumes of card {self.card} not restored: "
                       f"{self.error}")
        for entry in self.entries:
            out.append(entry.line())
        out += self.default_changes
        return out

    def fix_commands(self):
        """Commands that set the saved volumes by hand."""
        commands = []
        for e in self.entries:
            if e.status in (UNCHANGED, RESTORED):
                continue
            name, kind = e.now.name if e.now else e.saved.name, e.saved.kind
            raw = " ".join(str(int(round(v * RAW_FULL))) for v in e.saved.volumes)
            commands.append(f"pactl set-{kind}-volume {name} {raw}")
            commands.append(f"pactl set-{kind}-mute {name} "
                            f"{1 if e.saved.mute else 0}")
        return commands


def restore(saved, backend, timeout=None, settle=None, rounds=4, poll=None,
            sleep=time.sleep, clock=time.monotonic):
    """Put the desktop's volumes back after the card has been given back.

    Waits up to `timeout` s (TIMEOUT_S, 15) for the server to make the card's sinks and
    sources again, then `settle` s (SETTLE_S, 1) for it to finish setting them up, and
    sets the saved volume and mute of each that differs. Reads them back
    after `settle` s more, and again up to `rounds` times if the server
    changed them once more. Returns a `Result`; nothing is raised."""
    timeout = TIMEOUT_S if timeout is None else timeout
    settle = SETTLE_S if settle is None else settle
    poll = POLL_S if poll is None else poll
    result = Result(saved.card)
    if not saved.nodes:
        return result
    began = clock()
    try:
        found = {}
        while True:
            found = match(saved.nodes, nodes_of_card(backend.nodes(), saved.card))
            if len(found) == len(saved.nodes) or clock() - began >= timeout:
                break
            sleep(poll)
        result.waited = clock() - began
        statuses = {i: MISSING for i in range(len(saved.nodes))}
        first = {}
        now = dict(found)
        if found:
            sleep(settle)
        for turn in range(rounds):
            current = nodes_of_card(backend.nodes(), saved.card)
            now = match(saved.nodes, current)
            wrote = False
            for i, node in enumerate(saved.nodes):
                if i not in now:
                    continue
                if same(node, now[i]):
                    statuses[i] = statuses[i] if statuses[i] == RESTORED else UNCHANGED
                    continue
                first.setdefault(i, now[i].volume_text())
                _put(backend, node, now[i])
                statuses[i] = RESTORED
                wrote = True
            if not wrote:
                break
            sleep(settle)            # the server may answer with its own change
        else:
            current = nodes_of_card(backend.nodes(), saved.card)
            now = match(saved.nodes, current)
        for i, node in enumerate(saved.nodes):
            if i in now and not same(node, now[i]):
                statuses[i] = DIFFERS
            entry = Entry(node, statuses[i], now.get(i))
            entry.first_seen = first.get(i, "")
            result.entries.append(entry)
        result.default_changes = _default_notes(saved, backend)
    except DesktopError as error:
        result.error = str(error)
        if not result.entries:
            result.entries = [Entry(n, MISSING) for n in saved.nodes]
    return result


def _put(backend, wanted, current):
    volumes = list(wanted.volumes)
    if len(volumes) != len(current.volumes) and volumes:
        volumes = [sum(volumes) / len(volumes)] * len(current.volumes)
    if volumes != list(current.volumes):
        backend.set_volume(current, volumes)
    if bool(wanted.mute) != bool(current.mute):
        backend.set_mute(current, wanted.mute)


def _default_notes(saved, backend):
    """Lines saying the server's default sink or source is not what it was.
    Not changed here: choosing the default is the user's."""
    notes = []
    try:
        sink, source = backend.defaults()
    except DesktopError:
        return notes
    for kind, before, after in ((SINK, saved.default_sink, sink),
                                (SOURCE, saved.default_source, source)):
        if before and after and before != after:
            notes.append(f"The default {kind} is now {after}; it was {before}. "
                         f"To change it back: pactl set-default-{kind} {before}")
    return notes
