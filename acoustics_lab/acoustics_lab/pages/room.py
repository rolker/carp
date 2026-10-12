"""The room sonar page: an in-air sonar from a speaker and a microphone.

Left: what to send and listen with (output and input, ping design, detection
design, maximum range, ping rate, how long the background is remembered) and
the numbers that follow from them. Centre: the current return against range,
an echogram of recent pings, and the same with the steady background taken
away so that what moves stands out. Right: notes with live numbers.

Works on the simulation (a demo room with a person walking about), on
hardware (a rig) and on replay (saved recordings). Each ping's time zero is
its own direct sound from speaker to microphone (experiments/room.py).
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
from ..ui.widgets import PingWorker

NOTES = Path(__file__).resolve().parent.parent / "notes" / "room.md"
HISTORY = 150                   # pings kept for the echograms
DEFAULT_RATE_HZ = 5.0
DEFAULT_MEMORY = 20             # pings in the background average
DEFAULT_FLOOR_DB = -70.0
CHANGES_TOP_DB = -10.0          # the top of the colour scale of the changes view


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
    needs = "one output near one input"

    def __init__(self, session, parent=None):
        super().__init__(parent)
        self.session = session
        self.ws = session.workspace
        self.design_id = None
        self.detection_id = None        # None: the ping design's own
        self.capture = None             # the latest capture, to analyse again
        self.last = None                # the latest RoomPing
        self.levels = []                # per ping: level array, or None if not heard
        self.diffs = []                 # per ping: |level - background|
        self.numbers_of = []            # ping number of each entry
        self.count = 0
        self.stamps = []                # time.monotonic() of the last pings, for the rate
        self.continuous = False
        self.worker = None
        self.folder = None
        self._filling = False
        self._started = 0.0
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
        self.output_box = QtWidgets.QComboBox()
        self.input_box = QtWidgets.QComboBox()
        self.design_box = QtWidgets.QComboBox()
        self.design_box.setToolTip("The room sonar sends the first signal of the ping "
                                   "design, from the output chosen here")
        self.detection_box = QtWidgets.QComboBox()
        self.detection_box.setToolTip("How returns are found: thresholds, windows, the "
                                      "first-arrival rule. Recorded with every result.")
        for w in (self.output_box, self.input_box, self.design_box, self.detection_box):
            w.currentIndexChanged.connect(self._picked)
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
        self.memory_spin = QtWidgets.QSpinBox()
        self.memory_spin.setRange(2, 500)
        self.memory_spin.setValue(DEFAULT_MEMORY)
        self.memory_spin.setSuffix(" pings")
        self.memory_spin.setToolTip("The background is the average of this many recent pings")
        self.floor_spin = self._spin(DEFAULT_FLOOR_DB, -120.0, -20.0, 0, " dB",
                                     "The bottom of the colour scale, re the direct sound")
        for w in (self.range_spin, self.rate_spin, self.memory_spin, self.floor_spin):
            w.valueChanged.connect(self._setting_changed)
        form.addRow("Output", self.output_box)
        form.addRow("Input", self.input_box)
        form.addRow("Ping design", self.design_box)
        form.addRow("Detection", detection_row)
        form.addRow("Maximum range", self.range_spin)
        form.addRow("Ping rate", self.rate_spin)
        form.addRow("Background memory", self.memory_spin)
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
        self.ascan = pg.PlotWidget()
        self.ascan.setLabel("bottom", "range (m)")
        self.ascan.setLabel("left", "dB re the direct sound")
        self.ascan.showGrid(x=True, y=True, alpha=0.3)
        self.legend = self.ascan.addLegend(offset=(-10, 10))
        self.echogram = self._image_plot("Echogram: the last pings, newest at the bottom")
        self.changes = self._image_plot("Changes: the echogram with the steady background taken away")
        for w in (self.ascan, self.echogram, self.changes):
            plots.addWidget(w)
        plots.setSizes([260, 260, 260])
        cbox.addWidget(plots, 1)

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
        self._update_needs()
        self._update_notes()

    def _backend_changed(self):
        if self._source() != self._last_source:
            self._last_source = self._source()
            self.clear()
        self.fill_transducers()
        self._update_needs()
        self._update_notes()

    def _interval_changed(self, seconds):
        if seconds > 0 and abs(self.rate_spin.value() - 1.0 / seconds) > 1e-6:
            self.rate_spin.blockSignals(True)
            self.rate_spin.setValue(1.0 / seconds)
            self.rate_spin.blockSignals(False)
        self._update_notes()

    def refresh(self):
        self.fill_designs()
        self.fill_transducers()
        self._update_needs()
        self._update_notes()

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
        keep_out, keep_in = self.output_box.currentData(), self.input_box.currentData()
        self.output_box.clear()
        self.input_box.clear()
        for t in infos:
            if t.can_send:
                self.output_box.addItem(t.name or t.id, t.id)
            if t.can_receive:
                self.input_box.addItem(t.name or t.id, t.id)
        out_at, in_at = self.output_box.findData(keep_out), self.input_box.findData(keep_in)
        if out_at < 0 or in_at < 0:
            if near:
                out_at, in_at = (self.output_box.findData(near[0][0]),
                                 self.input_box.findData(near[0][1]))
        self.output_box.setCurrentIndex(max(out_at, 0))
        self.input_box.setCurrentIndex(max(in_at, 0))
        replay = self.session.mode == REPLAY
        self.output_box.setEnabled(not replay)
        self.input_box.setEnabled(not replay)
        self.design_box.setEnabled(not replay)
        self._filling = False

    def _picked(self, _):
        if self._filling:
            return
        self.detection_id = self.detection_box.currentData()
        self.design_id = self.design_box.currentData()
        self._update_needs()
        self._update_notes()
        self._redraw_numbers_only()

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
        self._update_notes()

    def _redraw_numbers_only(self):
        self._update_numbers()

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
        self._need_button("Make the laptop speaker and microphone (rig and scenes)",
                          self.make_laptop)

    def _need_button(self, text, slot):
        b = QtWidgets.QPushButton(text)
        b.clicked.connect(lambda _=False: slot())
        self.needs_buttons.addWidget(b)

    def make_laptop(self):
        """The laptop template: layout, rig, as-built scene, a demo room, a
        room chirp and a ping design. Then use it."""
        ids = rigs.laptop_template(self.ws)
        s = self.session
        s.set_rig(ids["rig"])
        if s.mode == HARDWARE:
            s.use_as_built()
        elif s.mode == "simulation":
            s.set_scene(ids["demo"])
        self.design_id = ids["design"]
        self.fill_designs()
        self.fill_transducers()
        self._update_needs()
        self.status.emit("The laptop rig and its scenes are in the workspace: "
                         "'Laptop in a room' for simulation, the rig's as-built scene "
                         "for hardware.")

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
        if self.session.mode != REPLAY and not (self.output_box.currentData()
                                                and self.input_box.currentData()):
            return "choose an output and an input"
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
                out, inp = self.output_box.currentData(), self.input_box.currentData()
                ping = room.build_ping(
                    self.ws, self.design_id, out, inp, backend.transducers(),
                    self.range_spin.value(), self.session.sound_speed(),
                    room.separation(layout, out, inp))
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
        out, inp = self.output_box.currentData(), self.input_box.currentData()
        max_range = self.range_spin.value()

        def analyse(capture):
            return self._analyse(capture, out, inp, max_range, replay)
        return analyse

    def _analyse(self, capture, out, inp, max_range, replay=False):
        did, design = self.detection(capture)
        if replay or inp not in capture.recordings:
            inp = next(iter(capture.recordings))
            out = capture.ping.emissions[0].transducer
        capture.meta["detection_design"] = detections.record(did, design)
        return room.analyse(capture, out, inp, design, did, max_range)

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

    def _headline(self, capture, result):
        if capture.meta.get("backend") == "replay":
            head = (f"Recording {capture.meta['index'] + 1} of {capture.meta['count']} "
                    f"({Path(capture.meta['source']).name})")
        else:
            head = f"Ping {self.count}"
        if not result.heard:
            return head + ": " + "; ".join(result.warnings or ["nothing heard"])
        text = (f"{head}: direct sound {result.direct_dbfs:.0f} dBFS, "
                f"{20 * np.log10(result.direct_snr):.0f} dB above the noise")
        warnings = list(result.warnings) + list(capture.meta.get("warnings", []))
        return text + ("; " + "; ".join(warnings) if warnings else "")

    # ---- history -------------------------------------------------------

    def _keep(self, result, number):
        level = result.level if result.heard else None
        if self.levels and level is not None:
            width = next((l.size for l in self.levels if l is not None), level.size)
            if level.size != width:
                self.levels, self.diffs, self.numbers_of = [], [], []
        known = [l for l in self.levels if l is not None]
        mean = room.background(known, self.memory_spin.value())
        diff = None if level is None else room.difference(level, mean)
        self.levels = (self.levels + [level])[-HISTORY:]
        self.diffs = (self.diffs + [diff])[-HISTORY:]
        self.numbers_of = (self.numbers_of + [number])[-HISTORY:]

    def _rebuild_diffs(self):
        diffs = []
        for i, level in enumerate(self.levels):
            if level is None:
                diffs.append(None)
                continue
            before = [l for l in self.levels[:i] if l is not None]
            diffs.append(room.difference(level, room.background(before, self.memory_spin.value())))
        self.diffs = diffs

    def clear(self):
        self.levels, self.diffs, self.numbers_of = [], [], []
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
        out, inp = self.output_box.currentData(), self.input_box.currentData()
        replay = self.capture.meta.get("backend") == "replay"
        result = self._analyse(self.capture, out, inp, self.range_spin.value(), replay)
        self.last = result
        if self.levels:
            number = self.numbers_of[-1]
            self.levels, self.diffs, self.numbers_of = (
                self.levels[:-1], self.diffs[:-1], self.numbers_of[:-1])
            self._keep(result, number)
        self.headline.setText(f"Analysed again with {result.design.summary()}: "
                              + self._headline(self.capture, result).split(": ", 1)[-1])
        self._redraw()
        self._update_notes()

    # ---- drawing ---------------------------------------------------------

    def _redraw(self):
        self._draw_ascan()
        self._draw_images()
        self._update_numbers()

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
        known = [l for l in self.levels[:-1] if l is not None]
        mean = room.background(known, self.memory_spin.value())
        if mean is not None and mean.size == result.level.size:
            plot.plot(result.range_m, room.to_db(mean, floor), pen=pg.mkPen("#9a9a9a", width=1),
                      name=f"background ({min(len(known), self.memory_spin.value())} pings)")
        plot.plot(result.range_m, room.to_db(result.level, floor),
                  pen=pg.mkPen("#4e79a7", width=1.3), name="this ping")
        plot.addItem(pg.InfiniteLine(pos=result.noise_db, angle=0, pen=pg.mkPen(
            "#888", width=1, style=Qt.PenStyle.DashLine),
            label="typical noise", labelOpts=dict(position=0.97, color="#888")))
        for route, at in result.truth:
            colour = QtGui.QColor("#e15759" if route.startswith("mover") else "#59a14f")
            colour.setAlpha(150)
            plot.addItem(pg.InfiniteLine(pos=at, angle=90, pen=pg.mkPen(
                colour, width=1, style=Qt.PenStyle.DotLine)))
        plot.addItem(pg.InfiniteLine(pos=result.baseline_m / 2.0, angle=90, pen=pg.mkPen(
            "#4e79a7", width=1, style=Qt.PenStyle.DashLine)))

    def _stack(self, columns, bins, floor):
        rows = [room.to_db(c, floor) if c is not None else np.full(bins, floor)
                for c in columns]
        return np.vstack(rows) if rows else np.zeros((0, bins))

    def _draw_images(self):
        floor = self.floor_spin.value()
        result = self.last
        width = next((l.size for l in self.levels if l is not None), 0)
        for plot, columns, top in ((self.echogram, self.levels, 0.0),
                                   (self.changes, self.diffs, CHANGES_TOP_DB)):
            item = plot.image
            if not columns or not width:
                item.clear()
                continue
            image = self._stack(columns, width, floor)
            first, count = self.numbers_of[0], len(columns)
            max_range = result.range_m[-1] if result is not None and result.range_m.size \
                else self.range_spin.value()
            item.setImage(image.T, levels=(floor, top), autoLevels=False)
            item.setRect(QtCore.QRectF(0, first - 0.5, max_range, count))
            plot.setXRange(0, max_range, padding=0)
            plot.setYRange(first - 0.5, first - 0.5 + max(count, 10), padding=0)

    def _update_numbers(self):
        capture_rate = None
        if len(self.stamps) >= 3:
            capture_rate = (len(self.stamps) - 1) / (self.stamps[-1] - self.stamps[0])
        text = self._numbers_text(capture_rate)
        self.numbers.setText(text)

    def _signal_spec(self):
        design = self.ws.get("ping_designs", self.design_id or "")
        if not design or not design["events"]:
            return None
        from ..objects import signals as signal_objects
        try:
            f0, f1, duration = signal_objects.band(self.ws.get_signal,
                                                   design["events"][0]["signal"])
        except Exception:                       # noqa: a broken signal: say nothing
            return None
        return dict(f0=f0, f1=f1, duration=duration)

    def _numbers_text(self, achieved=None):
        spec = self._signal_spec()
        if self.last is not None and self.last.heard and self.session.mode == REPLAY:
            speed, baseline = self.last.sound_speed, self.last.baseline_m
        else:
            speed = self.session.sound_speed()
            layout = self.session.active_layout()
            baseline = room.separation(layout, self.output_box.currentData() or "",
                                       self.input_box.currentData() or "")
        if spec is None:
            return "Choose a ping design."
        rate = next((i.rate for i in self._infos() if i.rate), 48000.0)
        n = room.numbers(spec, speed, rate, baseline, self.range_spin.value(),
                         self.session.interval)
        lines = [
            f"<b>Range resolution</b>: {100 * n['resolution_m']:.1f} cm "
            f"({1e3 * n['resolution_s']:.2f} ms; chirp {spec['f0']:g}-{spec['f1']:g} Hz, "
            f"bandwidth {n['bandwidth_hz']:g} Hz)",
            f"<b>Range bin</b>: {1e3 * n['bin_m']:.1f} mm (one sample of travel at {rate:g} Hz)",
            f"<b>Maximum range</b>: {n['max_range_m']:g} m, listening {1e3 * n['listen_s']:.1f} ms "
            f"after the sound",
            f"<b>Ping rate</b>: {1.0 / self.session.interval:.2g} Hz asked for"
            if self.session.interval > 0 else "<b>Ping rate</b>: as fast as it goes"]
        if achieved:
            lines[-1] += f", {achieved:.2g} Hz achieved"
        if n["ambiguity_m"]:
            lines.append(f"<b>Unambiguous range</b> at that rate: {n['ambiguity_m']:.0f} m "
                         "(an echo later than the next ping is taken for its echo)")
        lines.append(f"<b>Speaker to microphone</b>: {1e3 * baseline:.0f} mm"
                     + ("" if baseline else " (unknown: ranges are c t / 2)")
                     + f"; sound speed {speed:.1f} m/s")
        out, inp = self.output_box.currentData(), self.input_box.currentData()
        if baseline > rigs.NEAR_M:
            lines.append(f"<font color='#c0392b'><b>These two are {baseline:.2f} m apart</b>: "
                         "ranges assume one place, so near echoes are off by up to half that.</font>")
        result = self.last
        if result is not None and result.heard:
            lines.append(f"<b>Direct sound</b>: {result.direct_dbfs:.1f} dBFS, "
                         f"{20 * np.log10(result.direct_snr):.0f} dB above the noise; typical "
                         f"noise {result.noise_db:.0f} dB re the direct sound")
        return "<br>".join(lines)

    # ---- notes -----------------------------------------------------------

    def _update_notes(self):
        spec = self._signal_spec()
        speed = self.session.sound_speed()
        out, inp = self.output_box.currentData() or "", self.input_box.currentData() or ""
        baseline = room.separation(self.session.active_layout(), out, inp)
        rate = next((i.rate for i in self._infos() if i.rate), 48000.0)
        max_range = self.range_spin.value()
        did, design = self.detection()
        n = (room.numbers(spec, speed, rate, baseline, max_range, self.session.interval)
             if spec else None)
        direct = ("No ping yet." if self.last is None else
                  ("The last direct sound was not found." if not self.last.heard else
                   f"The last one arrived {self.last.direct_dbfs:.0f} dBFS, "
                   f"{20 * np.log10(self.last.direct_snr):.0f} dB above the noise."))
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
            first_fraction=f"{design.first_fraction:g}")
        bar = self.notes.verticalScrollBar().value()
        self.notes.setMarkdown(text)
        self.notes.verticalScrollBar().setValue(bar)

    def shutdown(self):
        self.timer.stop()
        self.continuous = False
        if self.worker is not None:
            self.worker.cancel()
            self.worker.wait()
