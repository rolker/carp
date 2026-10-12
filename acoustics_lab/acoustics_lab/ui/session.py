"""What every page shares: the workspace and which backend is chosen.

The backend (simulation, replay; hardware comes in step 2) and the active
scene are chosen once, in the toolbar, not per page.
"""
from ..backends.replay import ReplayBackend
from ..backends.simulation import SimulationBackend
from ..qtcompat import QtCore, Signal

SIMULATION, REPLAY, HARDWARE = "simulation", "replay", "hardware"


class Session(QtCore.QObject):
    """Signals: backend_changed() when the mode, scene or replay source
    changes, or the active scene's contents do."""

    backend_changed = Signal()

    def __init__(self, workspace, parent=None):
        super().__init__(parent)
        self.workspace = workspace
        self.mode = SIMULATION
        self.scene_id = self._first_scene()
        self.replay = None              # a ReplayBackend, once one is opened
        self._simulation = None
        self._pings = 0                 # kept across rebuilds, so noise keeps changing
        self.interval = 1.0             # s between pings in continuous mode
        workspace.changed.connect(self._workspace_changed)
        workspace.reloaded.connect(lambda _: self._workspace_changed("scenes", ""))

    def _first_scene(self):
        ids = self.workspace.ids("scenes")
        return "dongle_bench" if "dongle_bench" in ids else (ids[0] if ids else None)

    def _workspace_changed(self, kind, object_id):
        if kind in ("scenes", "layouts"):
            if not self.workspace.exists("scenes", self.scene_id or ""):
                self.scene_id = self._first_scene()
            self._drop_simulation()
            self.backend_changed.emit()

    def _drop_simulation(self):
        if self._simulation is not None:
            self._pings = self._simulation.count
        self._simulation = None

    def set_mode(self, mode):
        if mode != self.mode:
            self.mode = mode
            self.backend_changed.emit()

    def set_scene(self, scene_id):
        if scene_id != self.scene_id:
            self.scene_id = scene_id
            self._drop_simulation()
            self.backend_changed.emit()

    def open_replay(self, path):
        """Use saved recordings (a WAV file or a folder) as the backend.
        Raises ValueError if they cannot be used."""
        self.replay = ReplayBackend(path)
        self.mode = REPLAY
        self.backend_changed.emit()

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
        raise ValueError("the hardware backend comes in step 2")

    def describe(self):
        """A phrase for the toolbar and status bar."""
        if self.mode == REPLAY:
            if self.replay is None:
                return "replay: nothing open"
            return f"replay of {self.replay.path.name} ({len(self.replay)} recordings)"
        scene = self.workspace.get("scenes", self.scene_id or "")
        return f"simulation of {scene['name']}" if scene else "simulation: no scene"
