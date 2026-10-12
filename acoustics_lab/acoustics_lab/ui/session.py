"""What every page shares: the workspace, which backend is chosen, which rig
and which scene is active.

The backend (simulation, hardware, replay) and the active scene are chosen
once, in the toolbar, not per page. Hardware can only ever be the bench as
built, so choosing it makes the rig's as-built scene the active one; the
scene can be changed again (to simulate something not built) only in
simulation, and the toolbar says plainly when it is not the bench.
"""
from ..backends.hardware import HardwareBackend
from ..backends.replay import ReplayBackend
from ..backends.simulation import SimulationBackend, sound_speed
from ..objects import rigs
from ..qtcompat import QtCore, Signal

SIMULATION, REPLAY, HARDWARE = "simulation", "replay", "hardware"


class Session(QtCore.QObject):
    """Signals: backend_changed() when the mode, rig, scene or replay source
    changes, or the active scene's contents do; interval_changed(float) when
    the time between continuous pings changes; hardware_message(level, text)
    for what taking hold of the hardware says (from any thread)."""

    backend_changed = Signal()
    interval_changed = Signal(float)
    hardware_message = Signal(str, str)

    def __init__(self, workspace, parent=None, environment=None):
        super().__init__(parent)
        self.workspace = workspace
        self.environment = environment      # None: the real machine
        self.mode = SIMULATION
        self.scene_id = self._first_scene()
        self.rig_id = self._first_rig()
        self.replay = None              # a ReplayBackend, once one is opened
        self._simulation = None
        self._hardware = None
        self._pings = 0                 # kept across rebuilds, so noise keeps changing
        self.interval = 1.0             # s between pings in continuous mode
        self.messages = []              # (level, text) from the hardware, newest last
        workspace.changed.connect(self._workspace_changed)
        workspace.reloaded.connect(lambda _: self._workspace_changed("scenes", ""))

    # ---- choosing --------------------------------------------------------

    def _first_scene(self):
        ids = self.workspace.ids("scenes")
        return "dongle_bench" if "dongle_bench" in ids else (ids[0] if ids else None)

    def _first_rig(self):
        """The rig to start with: one made on this machine if there is one (a
        workspace shared between machines holds the others' rigs, whose
        devices are not here), else the first."""
        ids = self.workspace.ids("rigs")
        mine = [i for i in ids if self.workspace.get("rigs", i).get("machine") == rigs.machine_name()]
        return (mine or ids)[0] if ids else None

    def machine_note(self):
        """A sentence about whose machine the active rig is for, or ''."""
        rig = self.workspace.get("rigs", self.rig_id or "")
        if not rig or not rig.get("machine"):
            return ""
        here = rigs.machine_name()
        if rig["machine"] == here:
            return f"Rig '{rig['name']}' was made on this machine ({here})."
        return (f"Rig '{rig['name']}' was made on {rig['machine']}, not on this machine "
                f"({here}): the devices it names may not be here. Make this machine's own "
                "rig (the laptop template).")

    def _workspace_changed(self, kind, object_id):
        if kind in ("scenes", "layouts", "rigs"):
            if not self.workspace.exists("scenes", self.scene_id or ""):
                self.scene_id = self._first_scene()
            if not self.workspace.exists("rigs", self.rig_id or ""):
                self.rig_id = self._first_rig()
            self._drop_simulation()
            if kind in ("layouts", "rigs"):
                self.close_hardware()
            elif self._hardware is not None:
                self._hardware.sound_speed_ms = self.sound_speed()
            self.backend_changed.emit()

    def _drop_simulation(self):
        if self._simulation is not None:
            self._pings = self._simulation.count
        self._simulation = None

    def set_mode(self, mode):
        if mode == self.mode:
            return
        if self.mode == HARDWARE:
            self.close_hardware()
        self.mode = mode
        if mode == HARDWARE:
            self.use_as_built()
            return              # which emits
        self.backend_changed.emit()

    def set_scene(self, scene_id):
        if scene_id != self.scene_id:
            self.scene_id = scene_id
            self._drop_simulation()
            self.backend_changed.emit()

    def set_rig(self, rig_id):
        if rig_id != self.rig_id:
            self.close_hardware()
            self.rig_id = rig_id
            if self.mode == HARDWARE:
                self.use_as_built()
                return
            self.backend_changed.emit()

    def use_as_built(self):
        """Make the rig's as-built scene the active one (the bench as it is).
        Creates or brings it in step first, if the rig has none or it is out
        of date. Does nothing if there is no rig."""
        if self.rig_id and self.workspace.exists("rigs", self.rig_id):
            if not rigs.as_built_is_current(self.workspace, self.rig_id):
                with self.workspace.macro("bring the as-built scene in step"):
                    rigs.sync_as_built(self.workspace, self.rig_id)
            self.scene_id = self.workspace.get("rigs", self.rig_id)["as_built"]
            self._drop_simulation()
        self.backend_changed.emit()

    def is_as_built(self):
        """True if the active scene is the active rig's as-built one."""
        rig = self.workspace.get("rigs", self.rig_id or "")
        return bool(rig and rig.get("as_built") and rig["as_built"] == self.scene_id)

    def built_text(self):
        """(text, is_warning) for the toolbar: whether what is simulated is the
        bench. Empty text when there is no rig to compare with."""
        if self.mode == REPLAY:
            return "", False
        rig = self.workspace.get("rigs", self.rig_id or "")
        if rig is None:
            return "", False
        if self.mode == HARDWARE:
            return "the bench as built", False
        scene = self.workspace.get("scenes", self.scene_id or "")
        if self.is_as_built():
            return "as built", False
        return (f"simulating {scene['name'] if scene else 'nothing'}, not built", True)

    def set_interval(self, seconds):
        if seconds != self.interval:
            self.interval = float(seconds)
            self.interval_changed.emit(self.interval)

    def open_replay(self, path):
        """Use saved recordings (a WAV file or a folder) as the backend.
        Raises ValueError if they cannot be used."""
        self.replay = ReplayBackend(path)
        self.close_hardware()
        self.mode = REPLAY
        self.backend_changed.emit()

    # ---- the backends ------------------------------------------------------

    def sound_speed(self):
        scene = self.workspace.get("scenes", self.scene_id or "")
        return sound_speed(scene["medium"]) if scene else 343.2

    def backend(self):
        """The backend in use. Raises ValueError saying what is missing."""
        if self.mode == REPLAY:
            if self.replay is None:
                raise ValueError("no recordings are open; use File > Open "
                                 "recordings for replay")
            return self.replay
        if self.mode == SIMULATION:
            if self.scene_id is None:
                raise ValueError("the workspace has no scene to simulate")
            if self._simulation is None:
                self._simulation = SimulationBackend.from_workspace(
                    self.workspace, self.scene_id)
                self._simulation.count = self._pings
            return self._simulation
        return self.hardware()

    def hardware(self, rig_id=None):
        """The hardware backend for the active rig (made when first wanted;
        nothing is opened until a ping, an identify or a warm-up). Raises
        ValueError saying what is missing."""
        rig_id = rig_id or self.rig_id
        if not rig_id:
            raise ValueError("there is no rig; make one with Rigs... (the laptop's "
                             "speaker and microphone is offered as a template)")
        if self._hardware is None or self._hardware.rig_id != rig_id:
            self.close_hardware()
            self._hardware = HardwareBackend.from_workspace(
                self.workspace, rig_id, self.sound_speed(), self.environment,
                self._hardware_said)
        return self._hardware

    def _hardware_said(self, level, text):
        self.messages.append((level, text))
        self.hardware_message.emit(level, text)

    def close_hardware(self):
        """Stop the hardware streams and put the cards, mixers and the
        desktop's volumes back (this takes a few seconds when something was
        borrowed). Safe to call at any time."""
        if self._hardware is not None:
            backend, self._hardware = self._hardware, None
            backend.close()

    def identify(self, transducer_id, rig_id=None):
        """Play a short tone on one transducer of a rig (see
        HardwareBackend.identify) and return the sentence for the person.
        Called from a worker thread. Raises ValueError or DeviceError."""
        rig_id = rig_id or self.rig_id
        backend = self._hardware if (self._hardware and self._hardware.rig_id == rig_id) \
            else HardwareBackend.from_workspace(
                self.workspace, rig_id, self.sound_speed(), self.environment,
                self._hardware_said)
        return backend.identify(transducer_id)

    # ---- what a page needs -------------------------------------------------

    def active_layout(self):
        """The layout of what is active: the scene's in simulation, the rig's
        in hardware (the same as its as-built scene's), None in replay or
        when hardware has no rig."""
        if self.mode == REPLAY:
            return None
        if self.mode == HARDWARE:
            rig = self.workspace.get("rigs", self.rig_id or "")
            return self.workspace.get("layouts", rig["layout"]) if rig else None
        scene = self.workspace.get("scenes", self.scene_id or "")
        return self.workspace.get("layouts", scene["layout"]) if scene else None

    def active_layout_id(self):
        """The ID of the layout `active_layout` gives, or None."""
        if self.mode == REPLAY:
            return None
        if self.mode == HARDWARE:
            rig = self.workspace.get("rigs", self.rig_id or "")
            return rig["layout"] if rig else None
        scene = self.workspace.get("scenes", self.scene_id or "")
        return scene["layout"] if scene else None

    def scenes_that_fit(self, fits):
        """IDs of the scenes whose layout satisfies `fits(layout)`."""
        out = []
        for sid in self.workspace.ids("scenes"):
            layout = self.workspace.get("layouts", self.workspace.get("scenes", sid)["layout"])
            if layout is not None and fits(layout):
                out.append(sid)
        return out

    def describe(self):
        """A phrase for the toolbar and status bar."""
        if self.mode == REPLAY:
            if self.replay is None:
                return "replay: nothing open"
            return f"replay of {self.replay.path.name} ({len(self.replay)} recordings)"
        if self.mode == HARDWARE:
            rig = self.workspace.get("rigs", self.rig_id or "")
            if rig is None:
                return "hardware: no rig"
            state = "open" if self._hardware and self._hardware.is_open() else "not opened yet"
            return f"hardware: {rig['name']} ({state})"
        scene = self.workspace.get("scenes", self.scene_id or "")
        return f"simulation of {scene['name']}" if scene else "simulation: no scene"
