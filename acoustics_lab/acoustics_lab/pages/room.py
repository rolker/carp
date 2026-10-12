"""The room sonar page: an in-air sonar from speakers and a microphone.

Left: what to send and listen with (input, ping design, detection design,
maximum range, ping rate, steering, how long the background is remembered),
where the speakers and the microphone are (editable) and the numbers that
follow from them. Centre: where the echoes put the targets in the plane in
front of the laptop (or as bearing and range), the current return of each
sound against range, and an echogram of recent pings with the same with the
steady background taken away, for each. Right: notes with live values.

Every event of the ping design is sent (experiments/room.py). Works on the
simulation (a demo room with people moving about), on hardware (a rig) and on
replay (saved recordings). Each sound's time zero is its own direct sound from
its speaker to the microphone.
"""
import datetime
import string
import time
from pathlib import Path

import numpy as np

from .. import capture_io
from ..experiments import ranging, room
from ..models import media
from ..objects import detections, rigs
from ..qtcompat import Qt, QtCore, QtGui, QtWidgets, Signal, pg
from ..ui.session import HARDWARE, REPLAY
from ..ui.widgets import PingWorker, colour

NOTES = Path(__file__).resolve().parent.parent / "notes" / "room.md"
HISTORY = 150                   # pings kept for the echograms
DEFAULT_RATE_HZ = 5.0
DEFAULT_MEMORY = 20             # pings in the background average
DEFAULT_FLOOR_DB = -70.0
DEFAULT_TRAIL = 8               # pings of targets kept on the position view
CHANGES_TOP_DB = -10.0          # the top of the colour scale of the changes view
EVERY_ECHO, WHAT_CHANGED = "every", "changed"
PLAN, BEARING = 0, 1
TOLERANCE_NOTE_M = 2.0          # the range the notes quote a cross-range error at


class RoomSonarPage(QtWidgets.QWidget):
    """Signals: status(str); progress(float) 0..1 or -1 when idle;
    running_changed(bool); stopped() when continuous pinging ended by itself
    (an error)."""

    status = Signal(str)
    progress = Signal(float)
    running_changed = Signal(bool)
    stopped = Signal()

    title = "Room sonar"
    supports_run = True
    needs = "one or two outputs near one input"

    def __init__(self, session, parent=None):
        super().__init__(parent)
        self.session = session
        self.ws = session.workspace
        self.design_id = None
        self.detection_id = None        # None: the ping design's own
        self.capture = None             # the latest capture, to analyse again
        self.last = None                # the latest RoomResult
        self.results = []               # per ping: RoomResult
        self.levels = []                # per ping: a level array per sound (None if not heard)
        self.diffs = []                 # per ping: |level - background| per sound
        self.changed = []               # per ping: targets placed from the changes
        self.numbers_of = []            # ping number of each entry
        self.count = 0
        self.stamps = []                # time.monotonic() of the last pings, for the rate
        self.continuous = False
        self.worker = None
        self.folder = None
        self._filling = False
        self._started = 0.0
        self._geometry_ids = None       # transducers the geometry rows are built for
        self._image_plots = []          # per sound: (echogram plot, changes plot)
        self._last_source = self._source()
        if abs(session.interval - 1.0) < 1e-9:
            session.set_interval(1.0 / DEFAULT_RATE_HZ)
        self._build()
        self.ws.changed.connect(self._changed)
        self.ws.reloaded.connect(lambda _: self._changed("*", ""))
        session.backend_changed.connect(self._backend_changed)
        session.interval_changed.connect(self._interval_changed)
        self.timer = QtCore.QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.ping)
        self.refresh()

    # ---- layout --------------------------------------------------------

    def _build(self):
        left = QtWidgets.QWidget()
        box = QtWidgets.QVBoxLayout(left)
        box.setContentsMargins(0, 0, 0, 0)

        self.needs_group = QtWidgets.QGroupBox("This page needs " + self.needs)
        needs = QtWidgets.QVBoxLayout(self.needs_group)
        self.needs_text = QtWidgets.QLabel()
        self.needs_text.setWordWrap(True)
        self.needs_text.setStyleSheet("color: #c0392b")
        needs.addWidget(self.needs_text)
        self.needs_buttons = QtWidgets.QVBoxLayout()
        needs.addLayout(self.needs_buttons)
        box.addWidget(self.needs_group)

        group = QtWidgets.QGroupBox("Sound and listening")
        form = QtWidgets.QFormLayout(group)
        self.input_box = QtWidgets.QComboBox()
        self.design_box = QtWidgets.QComboBox()
        self.design_box.setToolTip(
            "Every event of the ping design is sent, each from its own transducer with "
            "its own signal and time. Two speakers with different signals place targets "
            "in the room; with the same signal they act as one steerable speaker.")
        self.detection_box = QtWidgets.QComboBox()
        self.detection_box.setToolTip("How returns are found: thresholds, windows, the "
                                      "first-arrival rule, how echoes are paired. "
                                      "Recorded with every result.")
        for w in (self.input_box, self.design_box, self.detection_box):
            w.currentIndexChanged.connect(self._picked)
        design_row = QtWidgets.QHBoxLayout()
        design_row.addWidget(self.design_box, 1)
        starters = QtWidgets.QPushButton("Add the two-speaker designs")
        starters.setToolTip("Add, if they are missing, the starter ping designs for two "
                            "speakers and a microphone: both speakers with the same chirp, "
                            "with an up and a down chirp, with split bands; left then right")
        starters.clicked.connect(lambda _=False: self.add_two_speaker_designs())
        self.starters_button = starters
        edit = QtWidgets.QPushButton("Edit...")
        edit.setToolTip("Edit detection designs")
        edit.clicked.connect(lambda: self.edit_detection())
        detection_row = QtWidgets.QHBoxLayout()
        detection_row.addWidget(self.detection_box, 1)
        detection_row.addWidget(edit)
        self.range_spin = self._spin(room.DEFAULT_MAX_RANGE_M, 0.3, 100.0, 1, " m",
                                     "Echoes are listened for out to this range; the "
                                     "listening time follows from it")
        self.rate_spin = self._spin(DEFAULT_RATE_HZ, 0.05, 60.0, 2, " Hz",
                                    "Pings per second (the toolbar's 'every' is the same "
                                    "setting). Hardware cannot ping faster than a ping takes.")
        self.rate_spin.setValue(1.0 / max(self.session.interval, 1e-3))
        self.steer_spin = self._spin(0.0, -80.0, 80.0, 1, " deg",
                                     "Speakers that send the same signal together are delayed "
                                     "against each other so that their sound adds up towards "
                                     "this bearing (0 straight ahead, positive to the right). "
                                     "It does nothing if no two speakers share a signal. The "
                                     "delay is made of whole samples on hardware.")
        self.memory_spin = QtWidgets.QSpinBox()
        self.memory_spin.setRange(2, 500)
        self.memory_spin.setValue(DEFAULT_MEMORY)
        self.memory_spin.setSuffix(" pings")
        self.memory_spin.setToolTip("The background is the average of this many recent pings")
        self.floor_spin = self._spin(DEFAULT_FLOOR_DB, -120.0, -20.0, 0, " dB",
                                     "The bottom of the colour scale, re the direct sound")
        self.source_box = QtWidgets.QComboBox()
        self.source_box.addItem("every echo", EVERY_ECHO)
        self.source_box.addItem("what changed", WHAT_CHANGED)
        self.source_box.setToolTip(
            "Place targets from every echo (walls and furniture too), or only from what "
            "changed since the background: the things that move")
        self.source_box.currentIndexChanged.connect(lambda _: self._draw_positions())
        self.trail_spin = QtWidgets.QSpinBox()
        self.trail_spin.setRange(1, HISTORY)
        self.trail_spin.setValue(DEFAULT_TRAIL)
        self.trail_spin.setSuffix(" pings")
        self.trail_spin.setToolTip("How many recent pings of targets are kept on the position "
                                   "view, fading with age")
        self.trail_spin.valueChanged.connect(lambda _: self._draw_positions())
        for w in (self.range_spin, self.rate_spin, self.memory_spin, self.floor_spin,
                  self.steer_spin):
            w.valueChanged.connect(self._setting_changed)
        form.addRow("Input", self.input_box)
        form.addRow("Ping design", design_row)
        form.addRow("", starters)
        form.addRow("Detection", detection_row)
        form.addRow("Maximum range", self.range_spin)
        form.addRow("Ping rate", self.rate_spin)
        form.addRow("Steer same-signal speakers", self.steer_spin)
        form.addRow("Background memory", self.memory_spin)
        form.addRow("Place targets from", self.source_box)
        form.addRow("Position trail", self.trail_spin)
        form.addRow("Colour floor", self.floor_spin)
        self.save_check = QtWidgets.QCheckBox("Save recordings")
        self.save_check.setToolTip("Write each ping to runs/<date>/ in the workspace, with "
                                   "the detection design used")
        row = QtWidgets.QHBoxLayout()
        row.addWidget(self.save_check)
        row.addStretch(1)
        for text, slot, tip in (("Analyse again", self.reanalyse,
                                 "Read the latest ping again with the detection design now chosen"),
                                ("Clear", self.clear, "Forget the pings so far")):
            b = QtWidgets.QPushButton(text)
            b.setToolTip(tip)
            b.clicked.connect(lambda _=False, f=slot: f())
            row.addWidget(b)
        form.addRow(row)
        box.addWidget(group)

        self.geometry_group = QtWidgets.QGroupBox("Speakers and microphone (cm)")
        geometry_box = QtWidgets.QVBoxLayout(self.geometry_group)
        self.geometry_grid = QtWidgets.QGridLayout()
        geometry_box.addLayout(self.geometry_grid)
        self.measured_check = QtWidgets.QCheckBox("These positions are measured")
        self.measured_check.setToolTip(
            "Where the targets are placed depends on these. They start as a guess; measure "
            "yours (the centre of each speaker grille and of the microphone hole, from one "
            "reference point, x across, y towards the room, z up) and type them in.")
        self.measured_check.toggled.connect(self._measured_toggled)
        self.geometry_note = QtWidgets.QLabel()
        self.geometry_note.setWordWrap(True)
        geometry_box.addWidget(self.measured_check)
        geometry_box.addWidget(self.geometry_note)
        box.addWidget(self.geometry_group)

        self.numbers = QtWidgets.QLabel()
        self.numbers.setWordWrap(True)
        self.numbers.setTextFormat(Qt.TextFormat.RichText)
        numbers_group = QtWidgets.QGroupBox("What the ping design and settings give")
        QtWidgets.QVBoxLayout(numbers_group).addWidget(self.numbers)
        box.addWidget(numbers_group)
        box.addStretch(1)

        centre = QtWidgets.QWidget()
        cbox = QtWidgets.QVBoxLayout(centre)
        cbox.setContentsMargins(0, 0, 0, 0)
        self.headline = QtWidgets.QLabel("No ping yet. Press Space, or the Ping button.")
        self.headline.setWordWrap(True)
        font = self.headline.font()
        font.setBold(True)
        self.headline.setFont(font)
        cbox.addWidget(self.headline)
        plots = QtWidgets.QSplitter(Qt.Orientation.Vertical)

        place = QtWidgets.QWidget()
        place_box = QtWidgets.QVBoxLayout(place)
        place_box.setContentsMargins(0, 0, 0, 0)
        view_row = QtWidgets.QHBoxLayout()
        view_row.addWidget(QtWidgets.QLabel("Targets:"))
        self.view_box = QtWidgets.QComboBox()
        self.view_box.addItem("in the plane (across and forward)", PLAN)
        self.view_box.addItem("by bearing and range", BEARING)
        self.view_box.currentIndexChanged.connect(self._view_picked)
        view_row.addWidget(self.view_box)
        self.place_text = QtWidgets.QLabel()
        view_row.addWidget(self.place_text, 1)
        place_box.addLayout(view_row)
        self.plan = pg.PlotWidget()
        self.plan.setLabel("bottom", "across (m), right is positive")
        self.plan.setLabel("left", "forward (m), into the room")
        self.plan.showGrid(x=True, y=True, alpha=0.25)
        self.plan.setAspectLocked(True)
        self.plan_legend = self.plan.addLegend(offset=(-10, 10))
        self.bearing = pg.PlotWidget()
        self.bearing.setLabel("bottom", "bearing (deg), right is positive")
        self.bearing.setLabel("left", "range from the speakers (m)")
        self.bearing.showGrid(x=True, y=True, alpha=0.25)
        self.stack = QtWidgets.QStackedWidget()
        self.stack.addWidget(self.plan)
        self.stack.addWidget(self.bearing)
        place_box.addWidget(self.stack, 1)

        self.ascan = pg.PlotWidget()
        self.ascan.setLabel("bottom", "range (m)")
        self.ascan.setLabel("left", "dB re the direct sound")
        self.ascan.showGrid(x=True, y=True, alpha=0.3)
        self.legend = self.ascan.addLegend(offset=(-10, 10))
        self.images = QtWidgets.QWidget()
        self.image_grid = QtWidgets.QGridLayout(self.images)
        self.image_grid.setContentsMargins(0, 0, 0, 0)
        for w in (place, self.ascan, self.images):
            plots.addWidget(w)
        plots.setSizes([380, 200, 320])
        cbox.addWidget(plots, 1)
        self._build_images(1)

        self.notes = QtWidgets.QTextBrowser()
        self.notes.setMinimumWidth(220)
        self.notes.setOpenExternalLinks(False)
        self.split = QtWidgets.QSplitter(Qt.Orientation.Horizontal)
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(left)
        scroll.setMinimumWidth(340)
        for w in (scroll, centre, self.notes):
            self.split.addWidget(w)
        self.split.setStretchFactor(0, 2)
        self.split.setStretchFactor(1, 6)
        self.split.setStretchFactor(2, 2)
        self.split.setSizes([380, 760, 300])
        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self.split)

    def _spin(self, value, low, high, decimals, suffix, tip):
        spin = QtWidgets.QDoubleSpinBox()
        spin.setRange(low, high)
        spin.setDecimals(decimals)
        spin.setSuffix(suffix)
        spin.setValue(value)
        spin.setKeyboardTracking(False)
        spin.setToolTip(tip)
        return spin

    def _image_plot(self, title):
        plot = pg.PlotWidget(title=title)
        plot.setLabel("bottom", "range (m)")
        plot.setLabel("left", "ping")
        plot.invertY(True)
        item = pg.ImageItem()
        item.setLookupTable(pg.colormap.get("viridis").getLookupTable(nPts=256))
        plot.addItem(item)
        plot.image = item
        return plot

    def _build_images(self, count, names=None):
        """One echogram and one changes view per sound, side by side."""
        while self.image_grid.count():
            item = self.image_grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._image_plots = []
        names = names or [""] * count
        for k in range(count):
            suffix = f" ({names[k]})" if names[k] else ""
            echo = self._image_plot("Echogram" + suffix + ": the last pings, newest at the bottom")
            changes = self._image_plot("Changes" + suffix + ": the echogram less the steady background")
            self.image_grid.addWidget(echo, 0, k)
            self.image_grid.addWidget(changes, 1, k)
            self._image_plots.append((echo, changes))

    @property
    def echogram(self):
        """The first sound's echogram plot."""
        return self._image_plots[0][0]

    @property
    def changes(self):
        """The first sound's changes plot."""
        return self._image_plots[0][1]

    # ---- keeping in step with the workspace and the session ---------------

    def _source(self):
        s = self.session
        return (s.mode, s.scene_id if s.mode != REPLAY else str(s.replay and s.replay.path),
                s.rig_id if s.mode == HARDWARE else None)

    def _changed(self, kind, object_id):
        if kind in ("ping_designs", "detection_designs", "signals", "*"):
            self.fill_designs()
        if kind in ("layouts", "scenes", "rigs", "*"):
            self.fill_transducers()
            self.fill_geometry()
        self._update_needs()
        self._update_notes()
        self._update_numbers()
        if kind in ("layouts", "scenes", "rigs", "*"):
            self._draw_positions()

    def _backend_changed(self):
        if self._source() != self._last_source:
            self._last_source = self._source()
            self.clear()
        self.fill_transducers()
        self.fill_geometry()
        self._update_needs()
        self._update_notes()
        self._draw_positions()
        if self.session.mode == HARDWARE and self.session.machine_note():
            self.status.emit(self.session.machine_note())

    def _interval_changed(self, seconds):
        if seconds > 0 and abs(self.rate_spin.value() - 1.0 / seconds) > 1e-6:
            self.rate_spin.blockSignals(True)
            self.rate_spin.setValue(1.0 / seconds)
            self.rate_spin.blockSignals(False)
        self._update_notes()

    def refresh(self):
        self.fill_designs()
        self.fill_transducers()
        self.fill_geometry()
        self._update_needs()
        self._update_notes()
        self._draw_positions()
        if self.session.machine_note():
            self.status.emit(self.session.machine_note())

    def _infos(self):
        try:
            return self.session.backend().transducers()
        except ValueError:
            return []

    def fill_designs(self):
        self._filling = True
        keep = self.design_id
        self.design_box.clear()
        for did in self.ws.ids("ping_designs"):
            self.design_box.addItem(self.ws.name_of("ping_designs", did), did)
        at = self.design_box.findData(keep)
        if at < 0:
            at = self.design_box.findData(rigs.LAPTOP_DEFAULT_DESIGN)
        if at < 0:
            at = max(self.design_box.findData(rigs.LAPTOP_DESIGN), 0)
        self.design_box.setCurrentIndex(at if self.design_box.count() else -1)
        self.design_id = self.design_box.currentData()
        own = detections.of_ping_design(self.ws, self.design_id)
        self.detection_box.clear()
        self.detection_box.addItem("the ping design's own" + (
            f" ({self.ws.name_of('detection_designs', own)})" if own else
            " (none named: the first one)"), None)
        for did in self.ws.ids("detection_designs"):
            self.detection_box.addItem(self.ws.name_of("detection_designs", did), did)
        at = self.detection_box.findData(self.detection_id)
        self.detection_box.setCurrentIndex(max(at, 0))
        if at < 0:
            self.detection_id = None
        self._filling = False

    def fill_transducers(self):
        infos = self._infos()
        layout = self.session.active_layout()
        near = rigs.near_pairs(layout) if layout else []
        self._filling = True
        keep_in = self.input_box.currentData()
        self.input_box.clear()
        for t in infos:
            if t.can_receive:
                self.input_box.addItem(t.name or t.id, t.id)
        in_at = self.input_box.findData(keep_in)
        if in_at < 0 and near:
            in_at = self.input_box.findData(near[0][1])
        self.input_box.setCurrentIndex(max(in_at, 0))
        replay = self.session.mode == REPLAY
        self.input_box.setEnabled(not replay)
        self.design_box.setEnabled(not replay)
        self.starters_button.setEnabled(not replay)
        self._filling = False

    def _picked(self, _):
        if self._filling:
            return
        self.detection_id = self.detection_box.currentData()
        self.design_id = self.design_box.currentData()
        self._update_needs()
        self._update_notes()
        self._update_numbers()

    def _setting_changed(self, _):
        if self._filling:
            return
        if self.sender() is self.rate_spin:
            self.session.set_interval(1.0 / self.rate_spin.value())
        elif self.sender() is self.range_spin:
            self.clear()                    # the bins change, so the old pings do not fit
        elif self.sender() is self.memory_spin:
            self._rebuild_diffs()
            self._redraw()
        elif self.sender() is self.floor_spin:
            self._redraw()
        elif self.sender() is self.steer_spin:
            self._draw_positions()
        self._update_notes()
        self._update_numbers()

    def _view_picked(self, _):
        self.stack.setCurrentIndex(self.view_box.currentData())
        self._draw_positions()

    def detection(self, capture=None):
        """(ID, DetectionDesign) in force: the page's choice, else the ping
        design's own (for a replayed recording, the one it was made with)."""
        own = detections.of_ping_design(self.ws, self.design_id)
        if capture is not None and capture.meta.get("backend") == "replay" and capture.ping:
            own = capture.ping.meta.get("detection_design") or own
        return detections.resolve(self.ws, self.detection_id, own)

    def edit_detection(self):
        from ..ui.detection_dialog import DetectionDesignDialog
        dialog = DetectionDesignDialog(self.ws, self, self.detection()[0] or None)
        dialog.setModal(False)
        dialog.show()
        self._detection_dialog = dialog

    def add_two_speaker_designs(self):
        """Make the starter two-speaker ping designs that are missing, for the
        active layout's two outputs near an input (else for 'left' and 'right')."""
        trio = rigs.stereo_outputs(self.session.active_layout())
        left, right = (trio[0], trio[1]) if trio else (rigs.LEFT, rigs.RIGHT)
        made = rigs.ensure_stereo_designs(self.ws, left, right)
        self.fill_designs()
        if made:
            self.status.emit(f"Added {len(made)} ping design(s) for {left} and {right}.")
        else:
            self.status.emit("The two-speaker ping designs are already there.")

    # ---- where the speakers and the microphone are -----------------------

    def _active_layout(self):
        return self.session.active_layout()

    def fill_geometry(self):
        layout = self._active_layout()
        ids = [(t["id"], t.get("name", t["id"])) for t in layout["transducers"]] if layout else []
        self._filling_geometry = True
        if ids != self._geometry_ids:
            self._geometry_ids = ids
            while self.geometry_grid.count():
                item = self.geometry_grid.takeAt(0)
                widget = item.widget()
                if widget:
                    widget.setParent(None)
                    widget.deleteLater()
            self._geometry_spins = {}
            for c, text in enumerate(("", "across x", "forward y", "up z"), 0):
                self.geometry_grid.addWidget(QtWidgets.QLabel(text), 0, c)
            for r, t in enumerate(layout["transducers"] if layout else [], 1):
                self.geometry_grid.addWidget(QtWidgets.QLabel(t.get("name", t["id"])), r, 0)
                spins = []
                for c in range(3):
                    spin = QtWidgets.QDoubleSpinBox()
                    spin.setRange(-1000.0, 1000.0)
                    spin.setDecimals(1)
                    spin.setSingleStep(0.5)
                    spin.setKeyboardTracking(False)
                    spin.setToolTip(f"{t.get('name', t['id'])}: position in cm")
                    spin.valueChanged.connect(self._geometry_edited)
                    self.geometry_grid.addWidget(spin, r, c + 1)
                    spins.append(spin)
                self._geometry_spins[t["id"]] = spins
        for t in (layout["transducers"] if layout else []):
            for spin, value in zip(self._geometry_spins[t["id"]], t["position"]):
                spin.blockSignals(True)
                spin.setValue(100.0 * value)
                spin.blockSignals(False)
        measured = rigs.is_measured(layout)
        self.measured_check.blockSignals(True)
        self.measured_check.setChecked(measured)
        self.measured_check.blockSignals(False)
        editable = layout is not None and self.session.mode != REPLAY
        for spins in self._geometry_spins.values():
            for spin in spins:
                spin.setEnabled(editable)
        self.measured_check.setEnabled(editable)
        self.geometry_group.setVisible(layout is not None)
        self.geometry_note.setText(
            "" if measured else
            "<font color='#d35400'><b>Not measured</b>: these are a guess"
            + (f". {layout.get('note', '')}" if layout and layout.get("note") else "")
            + " Targets are placed where these positions put them.</font>")
        self.geometry_note.setTextFormat(Qt.TextFormat.RichText)
        self._filling_geometry = False

    _filling_geometry = False

    def _geometry_edited(self, _=None):
        if self._filling_geometry:
            return
        lid, layout = self.session.active_layout_id(), self._active_layout()
        if not lid or not layout:
            return
        transducers = []
        for t in layout["transducers"]:
            t = dict(t)
            t["position"] = [spin.value() / 100.0 for spin in self._geometry_spins[t["id"]]]
            transducers.append(t)
        self.ws.update("layouts", lid, text="edit the speaker and microphone positions",
                       transducers=transducers, measured=True, note="")
        self.status.emit("Positions changed: targets are placed with them from the next ping "
                         "(the history is cleared).")
        self.clear()

    def _measured_toggled(self, checked):
        lid = self.session.active_layout_id()
        if lid and not self._filling_geometry:
            self.ws.update("layouts", lid, text="mark the positions as measured or guessed",
                           measured=bool(checked))

    # ---- what the page needs ---------------------------------------------

    @staticmethod
    def fits(layout):
        return bool(rigs.near_pairs(layout))

    def need_problem(self):
        """Why the active scene (or rig) will not do, or None. Replay needs
        nothing: the recording is what it is."""
        if self.session.mode == REPLAY:
            return None
        layout = self.session.active_layout()
        if layout is None:
            return ("there is no scene" if self.session.mode != HARDWARE
                    else "there is no rig: make one with Rigs...")
        if self.fits(layout):
            return None
        return (f"{'the rig' if self.session.mode == HARDWARE else 'the active scene'} "
                f"has no output within {rigs.NEAR_M:g} m of an input. The room sonar "
                "needs a speaker close to a microphone, like a laptop's")

    def _update_needs(self):
        problem = self.need_problem()
        self.needs_group.setVisible(problem is not None)
        while self.needs_buttons.count():
            item = self.needs_buttons.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        if problem is None:
            return
        self.needs_text.setText(problem[0].upper() + problem[1:] + ".")
        s = self.session
        if s.mode != HARDWARE:
            for sid in s.scenes_that_fit(self.fits):
                self._need_button(f"Use scene: {self.ws.name_of('scenes', sid)}",
                                  lambda sid=sid: s.set_scene(sid))
        for size, spec in rigs.LAPTOP_TEMPLATES.items():
            self._need_button(f"Make the laptop speakers and microphone: {spec['name']} "
                              "(layout, rig and scenes, not measured)",
                              lambda size=size: self.make_laptop(size))

    def _need_button(self, text, slot):
        b = QtWidgets.QPushButton(text)
        b.clicked.connect(lambda _=False: slot())
        self.needs_buttons.addWidget(b)

    def make_laptop(self, size="17"):
        """The laptop template of a size ("17" or "15" inch Alienware): layout,
        rig, as-built scene, a demo room, a room chirp and ping designs. Then
        use it."""
        ids = rigs.laptop_template(self.ws, size)
        s = self.session
        s.set_rig(ids["rig"])
        if s.mode == HARDWARE:
            s.use_as_built()
        elif s.mode == "simulation":
            s.set_scene(ids["demo"])
        self.design_id = ids["design"]
        self.fill_designs()
        self.fill_transducers()
        self.fill_geometry()
        self._update_needs()
        self.status.emit("The laptop rig and its scenes are in the workspace: "
                         "'Laptop in a room' for simulation, the rig's as-built scene "
                         "for hardware."
                         + (" The laptop made before it had two speakers was brought up to date."
                            if ids.get("upgraded") else ""))

    # ---- running -------------------------------------------------------

    def run_blocker(self):
        """Why the run controls are greyed out, or None."""
        problem = self.need_problem()
        if problem:
            return problem
        if self.session.mode != REPLAY and not self.design_id:
            return "there is no ping design; make one on the Ranging page"
        try:
            self.session.backend()
        except ValueError as error:
            return str(error)
        if self.session.mode != REPLAY and not self.input_box.currentData():
            return "choose an input"
        return None

    @property
    def busy(self):
        return self.worker is not None

    def ping(self):
        """Send one ping (or, in replay, read the next recording)."""
        self.timer.stop()
        if self.busy:
            return
        reason = self.run_blocker()
        if reason:
            self.status.emit(f"Cannot ping: {reason}")
            self._stop_continuous()
            return
        replay = self.session.mode == REPLAY
        try:
            backend = self.session.backend()
            did, design = self.detection()
            ping = None
            if not replay:
                layout = self.session.active_layout()
                ping = room.build_ping(
                    self.ws, self.design_id, self.input_box.currentData(),
                    backend.transducers(), self.range_spin.value(), self.session.sound_speed(),
                    layout, self.steer_spin.value(), design,
                    wsl=self.session.mode == HARDWARE and rigs.on_wsl())
                ping.meta["period_s"] = self.session.interval
                ping.meta["detection_settings"] = design.to_dict()
            stream = backend.open_stream(ping)
        except ValueError as error:
            self.status.emit(f"Check the ping design: {error}")
            self._stop_continuous()
            return
        self.worker = PingWorker(stream, self._analyser(), self)
        self.worker.progressed.connect(self._progressed)
        self.worker.succeeded.connect(self._ping_done)
        self.worker.failed.connect(self._ping_failed)
        self.running_changed.emit(True)
        self.status.emit("Pinging...")
        self._started = time.monotonic()
        self.worker.start()

    def _analyser(self):
        """The function the worker runs on a capture, with the settings as
        they are now."""
        replay = self.session.mode == REPLAY
        inp = self.input_box.currentData()
        max_range = self.range_spin.value()

        def analyse(capture):
            return self._analyse(capture, inp, max_range, replay)
        return analyse

    def _analyse(self, capture, inp, max_range, replay=False):
        did, design = self.detection(capture)
        if replay or inp not in capture.recordings:
            inp = next(iter(capture.recordings))
        capture.meta["detection_design"] = detections.record(did, design)
        return room.read(capture, inp, design, did, max_range)

    def _progressed(self, fraction, text):
        self.progress.emit(fraction)
        if text:
            self.status.emit(f"Pinging... {text}")

    def stop(self):
        self._stop_continuous()
        if self.worker is not None:
            self.worker.cancel()

    def set_continuous(self, on):
        self.continuous = on
        if on:
            self.ping()
        else:
            self.timer.stop()

    def _stop_continuous(self):
        if self.continuous:
            self.continuous = False
            self.stopped.emit()
        self.timer.stop()

    def _finish_worker(self):
        worker, self.worker = self.worker, None
        worker.wait()
        worker.deleteLater()
        self.progress.emit(-1.0)
        self.running_changed.emit(False)

    def _ping_failed(self, message):
        self._finish_worker()
        self._stop_continuous()
        self.status.emit(f"Ping failed: {message}" if message else "Cancelled.")

    def _ping_done(self, capture, result):
        self._finish_worker()
        self.count += 1
        self.capture, self.last = capture, result
        self._keep(result, self.count)
        now = time.monotonic()
        self.stamps = (self.stamps + [now])[-12:]
        text = self._headline(capture, result)
        saved = ""
        if self.save_check.isChecked() and capture.meta.get("backend") != "replay":
            if self.folder is None:
                stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
                self.folder = self.ws.path / "runs" / stamp
            path = capture_io.save_capture(self.folder, self.count, capture, result.input)
            saved = f"   [saved in {Path(path).parent.relative_to(self.ws.path)}]"
        self.headline.setText(text)
        self.status.emit(text.split(":")[0] + saved)
        self._redraw()
        self._update_notes()
        if self.continuous:
            wait = max(0.0, self.session.interval - (now - self._started))
            self.timer.start(int(wait * 1000))

    def _name(self, result, channel):
        """What to call a sound: its speakers' names."""
        layout = self.session.active_layout() or (self.capture.meta.get("layout")
                                                  if self.capture else None)
        names = {t["id"]: t.get("name", t["id"]) for t in (layout or {}).get("transducers", [])}
        return " + ".join(names.get(o, o) for o in channel.outputs)

    def _headline(self, capture, result):
        if capture.meta.get("backend") == "replay":
            head = (f"Recording {capture.meta['index'] + 1} of {capture.meta['count']} "
                    f"({Path(capture.meta['source']).name})")
        else:
            head = f"Ping {self.count}"
        if not result.heard:
            return head + ": " + "; ".join(result.all_warnings or ["nothing heard"])
        parts = []
        for c in result.channels:
            if c.heard:
                parts.append(f"{self._name(result, c)} {c.direct_dbfs:.0f} dBFS "
                             f"({20 * np.log10(c.direct_snr):.0f} dB above the noise)")
            else:
                parts.append(f"{self._name(result, c)} not heard")
        text = f"{head}: direct sound " + ", ".join(parts)
        if result.geometry is not None:
            text += f"; {len(result.fixes)} target(s) placed"
        warnings = result.all_warnings + list(capture.meta.get("warnings", []))
        return text + ("; " + "; ".join(warnings) if warnings else "")

    # ---- history -------------------------------------------------------

    def _keep(self, result, number):
        levels = [c.level if c.heard else None for c in result.channels]
        if self.levels:
            same = len(self.levels[-1]) == len(levels) and all(
                a is None or b is None or a.size == b.size
                for a, b in zip(self.levels[-1], levels))
            if not same:
                self._forget()
        diffs, known = [], self.levels
        for k, level in enumerate(levels):
            if level is None:
                diffs.append(None)
                continue
            before = [ls[k] for ls in known if ls[k] is not None]
            diffs.append(room.difference(level, room.background(before, self.memory_spin.value())))
        self.results = (self.results + [result])[-HISTORY:]
        self.levels = (self.levels + [levels])[-HISTORY:]
        self.diffs = (self.diffs + [diffs])[-HISTORY:]
        self.changed = (self.changed + [self._changed_fixes(result, diffs)])[-HISTORY:]
        self.numbers_of = (self.numbers_of + [number])[-HISTORY:]
        if len(self._image_plots) != len(result.channels):
            self._build_images(len(result.channels), [self._name(result, c) for c in result.channels])

    def _changed_fixes(self, result, diffs):
        arrays = [d if d is not None else np.zeros(0) for d in diffs]
        return room.place(result.channels, arrays, result.design, result.geometry)

    def _forget(self):
        self.results, self.levels, self.diffs = [], [], []
        self.changed, self.numbers_of = [], []

    def _rebuild_diffs(self):
        diffs, changed = [], []
        for i, levels in enumerate(self.levels):
            row = []
            for k, level in enumerate(levels):
                if level is None:
                    row.append(None)
                    continue
                before = [ls[k] for ls in self.levels[:i] if ls[k] is not None]
                row.append(room.difference(level, room.background(before, self.memory_spin.value())))
            diffs.append(row)
            changed.append(self._changed_fixes(self.results[i], row))
        self.diffs, self.changed = diffs, changed

    def clear(self):
        self._forget()
        self.count, self.last, self.capture, self.folder = 0, None, None, None
        self.stamps = []
        self.headline.setText("No ping yet.")
        self._redraw()
        self._update_notes()

    def reanalyse(self):
        """Read the latest ping again with the detection design now chosen,
        replacing it in the history."""
        if self.capture is None:
            self.status.emit("Nothing to analyse again yet: ping first.")
            return
        inp = self.input_box.currentData()
        replay = self.capture.meta.get("backend") == "replay"
        result = self._analyse(self.capture, inp, self.range_spin.value(), replay)
        self.last = result
        if self.levels:
            number = self.numbers_of[-1]
            self.results, self.levels, self.diffs, self.changed, self.numbers_of = (
                self.results[:-1], self.levels[:-1], self.diffs[:-1], self.changed[:-1],
                self.numbers_of[:-1])
            self._keep(result, number)
        self.headline.setText(f"Analysed again with {result.design.summary()}: "
                              + self._headline(self.capture, result).split(": ", 1)[-1])
        self._redraw()
        self._update_notes()

    # ---- drawing ---------------------------------------------------------

    def _redraw(self):
        self._draw_positions()
        self._draw_ascan()
        self._draw_images()
        self._update_numbers()

    def _channel_colour(self, k):
        return colour(k).name()

    def _draw_ascan(self):
        plot = self.ascan
        plot.clear()
        self.legend.clear()
        floor = self.floor_spin.value()
        plot.setYRange(floor, 6, padding=0)
        plot.setXRange(0, self.range_spin.value(), padding=0)
        result = self.last
        if result is None or not result.heard:
            return
        first = True
        for k, c in enumerate(result.channels):
            if not c.heard:
                continue
            hue = self._channel_colour(k)
            before = [ls[k] for ls in self.levels[:-1] if k < len(ls) and ls[k] is not None]
            mean = room.background(before, self.memory_spin.value())
            if mean is not None and mean.size == c.level.size:
                faint = QtGui.QColor(hue)
                faint.setAlpha(110)
                plot.plot(c.range_m, room.to_db(mean, floor),
                          pen=pg.mkPen(faint, width=1, style=Qt.PenStyle.DashLine),
                          name=f"{self._name(result, c)} background "
                               f"({min(len(before), self.memory_spin.value())} pings)")
            plot.plot(c.range_m, room.to_db(c.level, floor), pen=pg.mkPen(hue, width=1.3),
                      name=f"{self._name(result, c)} ({self._signal_name(c)})")
            if c.echoes:
                plot.addItem(pg.ScatterPlotItem(
                    x=[e.range_m for e in c.echoes], y=[max(e.level_db, floor) for e in c.echoes],
                    symbol="t1", size=8, brush=pg.mkBrush(hue), pen=pg.mkPen("w", width=0.5)))
            if first:
                plot.addItem(pg.InfiniteLine(pos=c.noise_db, angle=0, pen=pg.mkPen(
                    "#888", width=1, style=Qt.PenStyle.DashLine),
                    label="typical noise", labelOpts=dict(position=0.97, color="#888")))
                first = False
            for route, at in c.truth:
                tint = QtGui.QColor("#e15759" if route.startswith("mover") else "#59a14f")
                tint.setAlpha(120)
                plot.addItem(pg.InfiniteLine(pos=at, angle=90, pen=pg.mkPen(
                    tint, width=1, style=Qt.PenStyle.DotLine)))
            plot.addItem(pg.InfiniteLine(pos=c.baseline_m / 2.0, angle=90, pen=pg.mkPen(
                hue, width=1, style=Qt.PenStyle.DashLine)))

    def _signal_name(self, channel):
        spec = (self.capture.ping.meta.get("signals", {}) if self.capture and self.capture.ping
                else {}).get(channel.signal)
        if spec:
            return f"{spec.get('name', channel.signal)}, {spec['f0'] / 1e3:g}-{spec['f1'] / 1e3:g} kHz"
        return channel.signal

    def _stack(self, columns, bins, floor):
        rows = [room.to_db(c, floor) if c is not None else np.full(bins, floor)
                for c in columns]
        return np.vstack(rows) if rows else np.zeros((0, bins))

    def _draw_images(self):
        floor = self.floor_spin.value()
        result = self.last
        for k, (echo, changes) in enumerate(self._image_plots):
            width = next((ls[k].size for ls in self.levels if k < len(ls) and ls[k] is not None), 0)
            for plot, source, top in ((echo, self.levels, 0.0), (changes, self.diffs, CHANGES_TOP_DB)):
                columns = [ls[k] if k < len(ls) else None for ls in source]
                item = plot.image
                if not columns or not width:
                    item.clear()
                    continue
                image = self._stack(columns, width, floor)
                first, count = self.numbers_of[0], len(columns)
                channel = result.channels[k] if result is not None and k < len(result.channels) else None
                max_range = channel.range_m[-1] if channel is not None and channel.range_m.size \
                    else self.range_spin.value()
                item.setImage(image.T, levels=(floor, top), autoLevels=False)
                item.setRect(QtCore.QRectF(0, first - 0.5, max_range, count))
                plot.setXRange(0, max_range, padding=0)
                plot.setYRange(first - 0.5, first - 0.5 + max(count, 10), padding=0)

    # ---- the targets in the room --------------------------------------------

    def _zone(self, result):
        """(low, high, steer) in degrees of the zone where speakers sending
        the same signal together add up, or None if no two do."""
        if result is None:
            return None
        for k, c in enumerate(result.channels):
            if c.combined and c.heard:
                spec = self._spec_of(c)
                resolution = (room.numbers(spec, result.sound_speed, c.rate, c.baseline_m,
                                           self.range_spin.value(), 0.0,
                                           result.design.resolution)["resolution_s"]
                              if spec else 0.0)
                geom = room.geometry(self._layout_of_last(), c.outputs, result.input)
                if geom is None:
                    return None
                xs = [geom.xy(o)[0] for o in c.outputs]
                low, high = room.steered_zone(max(xs) - min(xs), resolution, result.sound_speed,
                                              result.steer_deg)
                return low, high, result.steer_deg
        return None

    def _layout_of_last(self):
        if self.capture is not None and self.capture.meta.get("layout"):
            return self.capture.meta["layout"]
        return self.session.active_layout()

    def _spec_of(self, channel):
        spec = (self.capture.ping.meta.get("signals", {}) if self.capture and self.capture.ping
                else {}).get(channel.signal)
        return dict(spec) if spec else None

    def _fixes_of(self, index):
        return (self.changed if self.source_box.currentData() == WHAT_CHANGED
                else [r.fixes for r in self.results])[index]

    def _draw_positions(self):
        """The targets, the speakers and the microphone, on whichever view is
        showing; both are redrawn."""
        result = self.last
        layout = self._layout_of_last() if result is not None else self.session.active_layout()
        max_range = self.range_spin.value()
        self._draw_plan(result, layout, max_range)
        self._draw_bearing(result, max_range)
        if result is None:
            self.place_text.setText("")
            return
        if result.geometry is None:
            channels = [c for c in result.channels if c.heard]
            self.place_text.setText(
                "One return only: its speakers sent the same signal, so there is range and "
                "the beam, but nothing says where across a target is. Use a design with "
                "different signals for place." if len(channels) <= 1 or any(
                    c.combined for c in channels) else
                "The layout does not say where the speakers are.")
            return
        fixes = self._fixes_of(len(self.results) - 1) if self.results else []
        what = "changes" if self.source_box.currentData() == WHAT_CHANGED else "echoes"
        self.place_text.setText(f"{len(fixes)} target(s) from the {what} of the last ping"
                                + ("; positions not measured" if result.geometry.assumed else ""))

    def _trail_points(self):
        """(x, y, bearing, range, age) of the targets of the recent pings."""
        out = []
        recent = min(self.trail_spin.value(), len(self.results))
        for age in range(recent):
            index = len(self.results) - 1 - age
            for f in self._fixes_of(index):
                out.append((f.x, f.y, f.bearing_deg, f.range_m, age, f.level_db))
        return out

    def _fade(self, age, base):
        """Brush and pen for a point `age` pings old."""
        recent = max(self.trail_spin.value() - 1, 1)
        alpha = int(255 * max(1.0 - 0.85 * age / recent, 0.1)) if age else 255
        fill = QtGui.QColor(base)
        fill.setAlpha(alpha)
        edge = QtGui.QColor("white")
        edge.setAlpha(alpha)
        return pg.mkBrush(fill), pg.mkPen(edge, width=0.5)

    def _draw_plan(self, result, layout, max_range):
        plot = self.plan
        plot.clear()
        self.plan_legend.clear()
        plot.setXRange(-0.75 * max_range, 0.75 * max_range, padding=0)
        plot.setYRange(-0.1 * max_range, max_range, padding=0)
        ring = np.radians(np.linspace(-90, 90, 91))
        for r in range(1, int(max_range) + 1):
            plot.plot(r * np.sin(ring), r * np.cos(ring), pen=pg.mkPen("#999999", width=0.6,
                                                                        style=Qt.PenStyle.DotLine))
            label = pg.TextItem(f"{r} m", color="#888888", anchor=(0.5, 1.0))
            label.setPos(0.0, r)
            plot.addItem(label)
        centre = np.zeros(2)
        if layout:
            pos = room.positions(layout)
            sends = [t for t in layout["transducers"] if t.get("can_send") and t["id"] in pos]
            hears = [t for t in layout["transducers"] if t.get("can_receive") and t["id"] in pos]
            if sends:
                centre = np.mean([pos[t["id"]][:2] for t in sends], axis=0)
            for group, symbol, hue, text in ((sends, "t", "#f28e2b", "speaker"),
                                             (hears, "o", "#76b7b2", "microphone")):
                if not group:
                    continue
                plot.addItem(pg.ScatterPlotItem(
                    x=[pos[t["id"]][0] for t in group], y=[pos[t["id"]][1] for t in group],
                    symbol=symbol, size=12, brush=pg.mkBrush(hue), pen=pg.mkPen("k", width=1),
                    name=text))
                ordered = sorted(group, key=lambda t: pos[t["id"]][0])
                for n, t in enumerate(ordered):
                    if symbol == "o":
                        anchor, dy = (0.5, 0.0), -0.04 * max_range
                    else:                       # speakers: the left one's name to its left
                        anchor, dy = ((1.0, 1.0) if n < len(ordered) / 2 else (0.0, 1.0)), 0.03 * max_range
                    label = pg.TextItem(t.get("name", t["id"]), color=hue, anchor=anchor)
                    label.setPos(pos[t["id"]][0], pos[t["id"]][1] + dy)
                    plot.addItem(label)
            if not rigs.is_measured(layout):
                note = pg.TextItem("speaker and microphone positions: not measured (a guess)",
                                   color="#d35400", anchor=(0.0, 0.0))
                note.setPos(-0.75 * max_range, max_range)
                plot.addItem(note)
        zone = self._zone(result)
        if zone is not None:
            low, high, steer = zone
            edges = np.radians(np.linspace(low, high, 25))
            outline = [QtCore.QPointF(*centre)] + [
                QtCore.QPointF(centre[0] + max_range * np.sin(a), centre[1] + max_range * np.cos(a))
                for a in edges]
            wedge = QtWidgets.QGraphicsPolygonItem(QtGui.QPolygonF(outline))
            wedge.setBrush(pg.mkBrush(QtGui.QColor(118, 183, 178, 60)))
            wedge.setPen(pg.mkPen("#76b7b2", width=1))
            plot.addItem(wedge)
            plot.addItem(pg.PlotDataItem(
                [centre[0], centre[0] + max_range * np.sin(np.radians(steer))],
                [centre[1], centre[1] + max_range * np.cos(np.radians(steer))],
                pen=pg.mkPen("#76b7b2", width=1, style=Qt.PenStyle.DashLine),
                name=f"steered to {steer:+g} deg: copies merge in the zone"))
        if result is not None and result.truth_targets:
            plot.addItem(pg.ScatterPlotItem(
                x=[t[2] for t in result.truth_targets], y=[t[3] for t in result.truth_targets],
                symbol="o", size=16, brush=None, pen=pg.mkPen("#59a14f", width=1.5),
                name="where they really are (simulation)"))
        points = self._trail_points()
        if points:
            base = "#e15759" if self.source_box.currentData() == WHAT_CHANGED else "#4e79a7"
            spots = []
            for x, y, _, _, age, _ in points:
                brush, pen = self._fade(age, base)
                spots.append(dict(pos=(x, y), size=10 if age == 0 else 7, brush=brush, pen=pen))
            plot.addItem(pg.ScatterPlotItem(spots=spots, name="targets placed by the echoes"))

    def _draw_bearing(self, result, max_range):
        plot = self.bearing
        plot.clear()
        plot.setXRange(-90, 90, padding=0)
        plot.setYRange(0, max_range, padding=0)
        zone = self._zone(result)
        if zone is not None:
            low, high, steer = zone
            plot.addItem(pg.LinearRegionItem([low, high], movable=False,
                                             brush=pg.mkBrush(QtGui.QColor(118, 183, 178, 60))))
        points = self._trail_points()
        if points:
            base = "#e15759" if self.source_box.currentData() == WHAT_CHANGED else "#4e79a7"
            spots = []
            for _, _, bearing, rng, age, _ in points:
                brush, pen = self._fade(age, base)
                spots.append(dict(pos=(bearing, rng), size=10 if age == 0 else 7,
                                  brush=brush, pen=pen))
            plot.addItem(pg.ScatterPlotItem(spots=spots))
        if result is not None and result.truth_targets and result.geometry is not None:
            centre = result.geometry.centre
            xs = [(t[2] - centre[0], t[3] - centre[1]) for t in result.truth_targets]
            plot.addItem(pg.ScatterPlotItem(
                x=[np.degrees(np.arctan2(dx, dy)) for dx, dy in xs],
                y=[float(np.hypot(dx, dy)) for dx, dy in xs],
                symbol="o", size=16, brush=None, pen=pg.mkPen("#59a14f", width=1.5)))

    # ---- numbers ---------------------------------------------------------

    def _update_numbers(self):
        capture_rate = None
        if len(self.stamps) >= 3:
            capture_rate = (len(self.stamps) - 1) / (self.stamps[-1] - self.stamps[0])
        self.numbers.setText(self._numbers_text(capture_rate))

    def _rate(self):
        return next((i.rate for i in self._infos() if i.rate), 48000.0)

    def _layout_for_numbers(self):
        if self.session.mode == REPLAY:
            return self._layout_of_last() if self.capture is not None else None
        return self.session.active_layout()

    def _numbers_text(self, achieved=None):
        rate = self._rate()
        specs = room.signal_specs(self.ws, self.design_id, rate)
        if self.session.mode == REPLAY and self.capture is not None and self.last is not None \
                and self.last.heard:
            speed = self.last.sound_speed
            specs = self._replay_specs()
        else:
            speed = self.session.sound_speed()
        if not specs:
            return "Choose a ping design."
        layout = self._layout_for_numbers()
        design = self.detection()[1]
        inp = self.input_box.currentData() or ""
        lines = []
        seen = set()
        for spec in specs:
            if spec["signal"] in seen:
                continue
            seen.add(spec["signal"])
            baseline = room.separation(layout, spec["transducer"], inp)
            n = room.numbers(spec, speed, rate, baseline, self.range_spin.value(),
                             self.session.interval, design.resolution)
            lines.append(
                f"<b>Range resolution</b> ({spec['name']}): {100 * n['resolution_m']:.1f} cm "
                f"({1e3 * n['resolution_s']:.2f} ms; chirp {spec['f0']:g}-{spec['f1']:g} Hz, "
                f"bandwidth {n['bandwidth_hz']:g} Hz)")
        baselines = {s["transducer"]: room.separation(layout, s["transducer"], inp) for s in specs}
        first = next(iter(baselines.values()))
        lines += [
            f"<b>Range bin</b>: {1e3 * n['bin_m']:.1f} mm (one sample of travel at {rate:g} Hz)",
            f"<b>Maximum range</b>: {n['max_range_m']:g} m, listening "
            f"{1e3 * room.listen_for(self.range_spin.value(), speed, min(baselines.values())):.1f} "
            "ms after the sound",
            f"<b>Ping rate</b>: {1.0 / self.session.interval:.2g} Hz asked for"
            if self.session.interval > 0 else "<b>Ping rate</b>: as fast as it goes"]
        if achieved:
            lines[-1] += f", {achieved:.2g} Hz achieved"
        if n["ambiguity_m"]:
            lines.append(f"<b>Unambiguous range</b> at that rate: {n['ambiguity_m']:.0f} m "
                         "(an echo later than the next ping is taken for its echo)")
        lines.append("<b>Speaker to microphone</b>: " + ", ".join(
            f"{t} {1e3 * d:.0f} mm" if d else f"{t} unknown (ranges are c t / 2)"
            for t, d in baselines.items()) + f"; sound speed {speed:.1f} m/s")
        if any(d > rigs.NEAR_M for d in baselines.values()):
            lines.append("<font color='#c0392b'><b>A speaker and the microphone are more than "
                         f"{rigs.NEAR_M:g} m apart</b>: ranges assume one place, so near echoes "
                         "are off by up to half that.</font>")
        lines += self._geometry_lines(specs, layout, inp, speed, design)
        if self.session.mode == HARDWARE:
            note = self.session.machine_note()
            if note:
                lines.append(note)
            if rigs.on_wsl():
                staggered = (max(s["time"] for s in specs) - min(s["time"] for s in specs)
                             >= design.combine_s)
                lines.append("<font color='#c0392b'><b>WSL</b>: " + room.WSL_STAGGER
                             + (". <b>This ping design staggers its events</b>: use both "
                                "speakers with up and down chirps, or with split bands."
                                if staggered else ". This ping design sends at one instant: fine.")
                             + "</font>")
        if self._mic_line():
            lines.append("<b>Microphone across</b>: " + self._mic_line())
        result = self.last
        if result is not None and result.heard:
            for c in result.channels:
                if c.heard:
                    lines.append(f"<b>Direct sound</b> ({self._name(result, c)}): "
                                 f"{c.direct_dbfs:.1f} dBFS, {20 * np.log10(c.direct_snr):.0f} dB "
                                 f"above the noise; typical noise {c.noise_db:.0f} dB re the "
                                 "direct sound")
        return "<br>".join(lines)

    def _replay_specs(self):
        out = []
        for e in self.capture.ping.emissions:
            spec = self.capture.ping.meta.get("signals", {}).get(e.signal)
            if spec is None:
                continue
            out.append(dict(transducer=e.transducer, time=e.start, signal=e.signal,
                            name=spec.get("name", e.signal), f0=spec["f0"], f1=spec["f1"],
                            duration=spec["duration"], template=ranging._template(e, e.rate),
                            template_rate=e.rate))
        return out

    def _geometry_lines(self, specs, layout, inp, speed, design):
        """Numbers about two speakers: their spacing, the leak between their
        signals, the steered zone and the cross-range precision."""
        lines = []
        outs = list(dict.fromkeys(s["transducer"] for s in specs))
        geom = room.geometry(layout, outs, inp)
        if len(outs) < 2:
            return lines
        if geom is None:
            lines.append("<b>Speakers</b>: the layout does not give where they are, so "
                         "targets cannot be placed.")
            return lines
        spacing = geom.spacing(outs[0], outs[1])
        lines.append(f"<b>Speaker spacing</b>: {100 * spacing:.1f} cm"
                     + (" <font color='#d35400'>(a guess: not measured)</font>"
                        if geom.assumed else ""))
        for i, j, db in room.leak_pairs(specs, self.range_spin.value(), speed):
            bad = db > design.leak_db
            text = (f"<b>Leak</b> between {specs[i]['name']} ({specs[i]['transducer']}) and "
                    f"{specs[j]['name']} ({specs[j]['transducer']}): {db:.0f} dB")
            lines.append(f"<font color='#c0392b'>{text}: weak echoes near strong ones can be "
                         "confused</font>" if bad else text)
        groups = room.group_events([(s["signal"], s["time"]) for s in specs], design.combine_s)
        together = [g for g in groups if len(g) > 1]
        if together:
            g = together[0]
            ids = [specs[k]["transducer"] for k in g]
            spec = specs[g[0]]
            resolution = room.numbers(spec, speed, self._rate(), 0.0, self.range_spin.value(),
                                      0.0, design.resolution)["resolution_s"]
            xs = [geom.speakers[o][0] for o in ids if o in geom.speakers]
            dx = (max(xs) - min(xs)) if xs else spacing
            steer = self.steer_spin.value()
            low, high = room.steered_zone(dx, resolution, speed, steer)
            delays = room.steering_delays(geom, ids, steer, speed)
            lines.append(f"<b>Same signal on {' and '.join(ids)}</b>: one combined sound; "
                         f"steered to {steer:+g} deg the copies merge between {low:+.1f} and "
                         f"{high:+.1f} deg (delays: "
                         + ", ".join(f"{o} {1e6 * d:.0f} us" for o, d in delays.items()) + ")")
        elif self.steer_spin.value():
            lines.append("<b>Steering</b> does nothing: no two speakers share a signal in this "
                         "ping design.")
        lines.append(f"<b>Across-range precision</b>: a 1 cm error in a path length moves a "
                     f"target at {TOLERANCE_NOTE_M:g} m sideways by about "
                     f"{100 * TOLERANCE_NOTE_M * 0.01 / max(spacing, 1e-3):.0f} cm "
                     "(range times error over speaker spacing)")
        return lines

    def _mic_estimate(self):
        """The microphone's x from the direct sounds, averaged over the recent
        pings: (estimate m, layout's m, n), or None."""
        found = [r.mic for r in self.results[-20:] if r.mic]
        if not found:
            return None
        return (float(np.mean([m["x_m"] for m in found])), found[-1]["layout_x_m"], len(found))

    def _mic_line(self):
        mic = self._mic_estimate()
        if mic is None:
            return ""
        x, layout_x, n = mic
        off = 100 * (x - layout_x)
        return (f"From the last {n} ping(s) the microphone is about {abs(off):.1f} cm "
                + ("towards the right speaker" if off > 0 else "towards the left speaker")
                + f" of where the layout puts it ({100 * layout_x:.1f} cm across).")

    def _height_errors(self, geom):
        """A sentence with how far off a target is placed at 0.5, 1 and 2 m
        when it is 30 cm or 60 cm above the speakers' height, and if the
        microphone's height had not been entered."""
        if geom is None:
            return ""
        rows = []
        for r in (0.5, 1.0, 2.0):
            target = (0.3 * r, r)
            cells = []
            for dz, ignore in ((0.3, False), (0.6, False), (0.0, True)):
                e = room.placement_error(geom, (*target, dz), ignore)
                cells.append("not placed" if e is None else f"{100 * e:.0f}")
            rows.append(f"{r:g} m: {cells[0]} / {cells[1]} / {cells[2]} cm")
        return "; ".join(rows)

    # ---- notes -----------------------------------------------------------

    def _update_notes(self):
        rate = self._rate()
        speed = self.session.sound_speed()
        layout = self._layout_for_numbers()
        inp = self.input_box.currentData() or ""
        specs = room.signal_specs(self.ws, self.design_id, rate)
        max_range = self.range_spin.value()
        did, design = self.detection()
        outs = list(dict.fromkeys(s["transducer"] for s in specs))
        geom = room.geometry(layout, outs, inp) if len(outs) >= 2 else None
        spacing = geom.spacing(outs[0], outs[1]) if geom else 0.0
        baseline = room.separation(layout, outs[0], inp) if outs else 0.0
        n = (room.numbers(specs[0], speed, rate, baseline, max_range, self.session.interval,
                          design.resolution) if specs else None)
        lo, hi = ((specs[0]["f0"], specs[0]["f1"]) if specs else (2000.0, 20000.0))
        lam_long = 1e3 * media.wavelength(speed, max(min(lo, hi), 1.0))
        lam_short = 1e3 * media.wavelength(speed, max(max(lo, hi), 1.0))
        resolution_path = (100 * speed * n["resolution_s"]) if n else 0.0
        half_zone = (np.degrees(np.arcsin(min(speed * n["resolution_s"] / 2.0 / spacing, 1.0)))
                     if n and spacing else 0.0)
        fringe = room.fringe_step_deg(spacing, (lo + hi) / 2.0, speed) if spacing else None
        direct = ("No ping yet." if self.last is None else
                  ("The last direct sound was not found." if not self.last.heard else
                   "The last ones arrived " + ", ".join(
                       f"{c.direct_dbfs:.0f} dBFS" for c in self.last.channels if c.heard)
                   + f", {20 * np.log10(min(c.direct_snr for c in self.last.channels if c.heard)):.0f} "
                     "dB or more above the noise."))
        leaks = room.leak_pairs(specs, max_range, speed) if specs else []
        leak_line = (f"In this ping design the leak between {specs[leaks[0][0]]['name']} and "
                     f"{specs[leaks[0][1]]['name']} is {leaks[0][2]:.0f} dB." if leaks else
                     "This ping design has no two different signals at the same time, so "
                     "there is no leak to measure.")
        measured = "" if rigs.is_measured(layout) else (
            "**These positions are a guess, not measured** (speakers 34 cm apart, symmetric; "
            "the microphone at the top centre of the screen, 25 cm above them and 5 cm "
            "behind): measure yours and type them in on the left.")
        text = string.Template(NOTES.read_text()).safe_substitute(
            max_range=f"{max_range:g}", listen=f"{1e3 * n['listen_s']:.1f}" if n else "?",
            baseline=f"{1e3 * baseline:.0f}", speed=f"{speed:.1f}", mm_per_ms=f"{speed:.0f}",
            resolution_line=(f"With this chirp, two echoes closer than "
                             f"{100 * n['resolution_m']:.1f} cm of range merge." if n else ""),
            pulse=f"{1e3 * n['duration_s']:g}" if n else "?",
            pulse_m=f"{n['pulse_m']:.2f}" if n else "?",
            bin=f"{1e3 * n['bin_m']:.1f}" if n else "?",
            ambiguity_line=(f"At {1 / self.session.interval:.2g} pings a second an echo from "
                            f"beyond {n['ambiguity_m']:.0f} m would arrive after the next ping."
                            if n and n["ambiguity_m"] and self.session.interval else ""),
            memory=str(self.memory_spin.value()), direct_line=direct,
            detection_line=f"The detection design in force is {design.summary()}.",
            first_fraction=f"{design.first_fraction:g}",
            spacing=f"{100 * spacing:.0f}" if spacing else "?",
            measured_line=measured,
            lambda_long=f"{lam_long:.0f}", lambda_short=f"{lam_short:.0f}",
            path_resolution=f"{resolution_path:.1f}", half_zone=f"{half_zone:.0f}",
            fringe_line=(f"At the middle of this signal's band ({(lo + hi) / 2e3:g} kHz) a steady "
                         f"tone from these two speakers has lobes every {fringe:.0f} degrees "
                         "of bearing." if fringe else
                         "With this spacing a steady tone has a single lobe."),
            leak_line=leak_line, height_errors=self._height_errors(geom),
            mic_line=self._mic_line(), steer=f"{self.steer_spin.value():+g}",
            pair_tolerance=f"{100 * design.pair_tolerance_m:.0f}",
            pair_level=f"{design.pair_level_db:g}", echo_snr=f"{design.echo_snr:g}",
            nearest=f"{design.nearest_m:g}", combine=f"{1e3 * design.combine_s:g}",
            cross_error=f"{100 * TOLERANCE_NOTE_M * 0.01 / max(spacing, 1e-3):.0f}"
            if spacing else "?", cross_range=f"{TOLERANCE_NOTE_M:g}")
        bar = self.notes.verticalScrollBar().value()
        self.notes.setMarkdown(text)
        self.notes.verticalScrollBar().setValue(bar)

    def shutdown(self):
        self.timer.stop()
        self.continuous = False
        if self.worker is not None:
            self.worker.cancel()
            self.worker.wait()
