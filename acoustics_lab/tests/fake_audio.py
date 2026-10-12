"""Fakes for the mixer and the desktop's sound server: no real card is read
or written, no real sound server is asked, no sound is made."""
import copy
import time

from acoustics_lab.hardware import desktop, mixer


class FakeAlsaBackend:
    """Stands in for `mixer.AlsaBackend`: holds controls and their values,
    applies writes and queues a change event for every change, whoever makes
    it (`touch` is another program)."""
    name = "fake-alsa"

    def __init__(self, text, events=True):
        self.controls = {c.numid: c for c in mixer.parse_contents(text)}
        self.writes = []                  # (numid, values) we were asked for
        self.refuse = set()               # numids that raise on write
        self.ignore = set()               # numids that accept and do nothing
        self.queues = []
        self.has_events = events
        self.log = None                   # optional list for call ordering

    def read_controls(self, card):
        return copy.deepcopy(list(self.controls.values()))

    def write(self, card, control, values):
        self.writes.append((control.numid, list(values)))
        if self.log is not None:
            self.log.append(f"mixer write {control.name}")
        if control.numid in self.refuse:
            raise mixer.MixerError("Control busy")
        if control.numid not in self.ignore:
            self._set(control.numid, values)

    def touch(self, name, values):
        """Another program sets a control."""
        control = mixer.find_control(list(self.controls.values()), name)
        self._set(control.numid, values)

    def _set(self, numid, values):
        control = self.controls[numid]
        if list(values) != control.values:
            control.values = list(values)
            for queue in self.queues:
                queue.append(numid)

    def open_events(self, card):
        if not self.has_events:
            raise mixer.MixerError("no events")
        queue = []
        self.queues.append(queue)
        return FakeEvents(self, queue)


class FakeEvents:
    def __init__(self, backend, queue):
        self.backend = backend
        self.queue = queue
        self.closed = False

    def wait(self, timeout):
        if not self.queue:
            time.sleep(min(timeout, 0.01))
        found, self.queue[:] = sorted(set(self.queue)), []
        return found

    def close(self):
        self.closed = True
        self.backend.queues.remove(self.queue)


class FakeClock:
    """Time that only moves when something sleeps."""

    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


class FakeDesktop:
    """Stands in for a desktop backend. `nodes()` is what the server has
    now; `script` maps the number of the `nodes()` call to something to do
    on that call (a card going away, coming back)."""
    name = "fake-desktop"

    def __init__(self, nodes, default_sink="", default_source=""):
        self.current = list(nodes)
        self.sink_default = default_sink
        self.source_default = default_source
        self.calls = 0
        self.script = {}
        self.sets = []                    # ("volume"|"mute", name, value)
        self.meddle = None                # function(node) after each set
        self.fail = None                  # DesktopError text for nodes()
        self.log = None

    def nodes(self):
        self.calls += 1
        if self.log is not None:
            self.log.append("desktop read")
        action = self.script.get(self.calls)
        if action:
            action()
        if self.fail:
            raise desktop.DesktopError(self.fail)
        return copy.deepcopy(self.current)

    def _node(self, node):
        for n in self.current:
            if n.name == node.name:
                return n
        raise desktop.DesktopError(f"{node.label()} is gone")

    def set_volume(self, node, volumes):
        self.sets.append(("volume", node.name, list(volumes)))
        if self.log is not None:
            self.log.append(f"desktop set {node.name}")
        target = self._node(node)
        target.volumes = list(volumes)
        if self.meddle:
            self.meddle(target)

    def set_mute(self, node, mute):
        self.sets.append(("mute", node.name, mute))
        self._node(node).mute = bool(mute)

    def defaults(self):
        return self.sink_default, self.source_default


def node(kind, name, card, volumes, mute=False, description=""):
    return desktop.Node(kind, name, 1, card, description or name, list(volumes), mute)
