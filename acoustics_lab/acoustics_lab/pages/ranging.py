"""The ranging page: edit signals and a ping design, ping, and see when
each signal came back.

Left: the signals table and the ping design (events table), both edited in
place, one committed cell being one undo step. Centre: one row per event
(like ping_gui's table), the matched-filter trace of each event, and the
echogram (one column per ping). Right: notes with live numbers.
"""
import datetime
import string
from pathlib import Path

import numpy as np

from .. import capture_io
from ..experiments import ranging
from ..models import media
from ..objects import detections, schema, signals as signal_objects
from ..objects.schema import InUseError, WorkspaceError
from ..qtcompat import Qt, QtCore, QtGui, QtWidgets, Signal, pg
from ..ui.session import REPLAY
from ..ui.widgets import ComboDelegate, PingWorker, colour, read_only

NOTES = Path(__file__).resolve().parent.parent / "notes" / "ranging.md"
MAX_ECHOGRAMS = 4
FLOOR_DB = -40.0
BEFORE_MS = 2.0
HISTORY = 200

SIGNAL_COLUMNS = ["Name", "Operation", "Source", "From (Hz)", "To (Hz)",
                  "Length (ms)", "Level (0-1)", "Gain (dB)", "Merge below (ms)", "ID"]
NAME, OP, SOURCE, F0, F1, LENGTH, LEVEL, GAIN, RESOLUTION, ID = range(10)
EVENT_COLUMNS = ["#", "Transducer", "Signal", "Time (ms)"]
RESULT_COLUMNS = ["#", "Receiver", "Transducer", "Signal", "Sent (ms)",
                  "Arrival (ms)", "Path (m)", "Level (dB)", "SNR", "True path (m)",
                  "Error (mm)", "Note"]


def number(text, what):
    """float(text), with an error a person can act on."""
    try:
        return float(text)
    except ValueError:
        raise ValueError(f"{what} must be a number, not '{text.strip()}'") from None


class RangingPage(QtWidgets.QWidget):
    """Signals: status(str) for the status bar; progress(float) 0..1, or -1
    when idle; running_changed(bool); stopped() when continuous pinging
    ended by itself (an error)."""

    status = Signal(str)
    progress = Signal(float)
    running_changed = Signal(bool)
    stopped = Signal()

    title = "Ranging & positioning"
    supports_run = True

    def __init__(self, session, parent=None):
        super().__init__(parent)
        self.session = session
        self.ws = session.workspace
        self.design_id = None
        self.detection_id = None        # None: the ping design's own detection design
        self.capture = None             # the latest capture, to analyse again
        self.results = {}               # receiver -> RangingResult, latest ping
        self.count = 0                  # pings since the last Clear
        self.columns = {}               # receiver -> per ping, a trace per event
        self.span_ms = 15.0
        self.continuous = False
        self.worker = None
        self.stream = None
        self.stream_revision = -1
        self.revision = 0               # bumped by any change a ping depends on
        self.folder = None              # where this run's recordings are saved
        self._filling = False
        self._zoomed = False
        self._last_source = self._source()
        self._build()
        self.ws.changed.connect(self._changed)
        self.ws.reloaded.connect(lambda _: self._changed("*", ""))
        session.backend_changed.connect(self._backend_changed)
        self.timer = QtCore.QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.ping)
        self.refresh()

    # ---- layout --------------------------------------------------------

    def _build(self):
        left = QtWidgets.QSplitter(Qt.Orientation.Vertical)
        left.addWidget(self._build_signals())
        left.addWidget(self._build_design())
        centre = self._build_centre()
        self.notes = QtWidgets.QTextBrowser()
        self.notes.setMinimumWidth(220)
        self.notes.setOpenExternalLinks(False)
        self.split = QtWidgets.QSplitter(Qt.Orientation.Horizontal)
        for w in (left, centre, self.notes):
            self.split.addWidget(w)
        self.split.setStretchFactor(0, 3)
        self.split.setStretchFactor(1, 5)
        self.split.setStretchFactor(2, 2)
        self.split.setSizes([560, 700, 260])
        box = QtWidgets.QVBoxLayout(self)
        box.setContentsMargins(0, 0, 0, 0)
        box.addWidget(self.split)

    def _group(self, title, widget, buttons=()):
        group = QtWidgets.QGroupBox(title)
        box = QtWidgets.QVBoxLayout(group)
        box.setContentsMargins(6, 6, 6, 6)
        box.addWidget(widget)
        if buttons:
            row = QtWidgets.QHBoxLayout()
            for b in buttons:
                row.addWidget(b)
            row.addStretch(1)
            box.addLayout(row)
        return group

    def _button(self, text, slot, tip=""):
        b = QtWidgets.QPushButton(text)
        b.setToolTip(tip)
        b.clicked.connect(lambda _=False: slot())
        return b

    def _build_signals(self):
        t = self.signal_table = QtWidgets.QTableWidget(0, len(SIGNAL_COLUMNS))
        t.setHorizontalHeaderLabels(SIGNAL_COLUMNS)
        t.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        t.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        t.verticalHeader().setVisible(False)
        t.horizontalHeader().setStretchLastSection(True)
        t.itemChanged.connect(self._signal_edited)
        t.itemSelectionChanged.connect(self._update_notes)
        t.setItemDelegateForColumn(OP, ComboDelegate(
            lambda: [(op, op) for op in schema.DERIVED_OPS], t))
        t.setItemDelegateForColumn(SOURCE, ComboDelegate(
            lambda: [(self.ws.name_of("signals", i), i) for i in self.ws.ids("signals")], t))
        buttons = [
            self._button("Add chirp", self.add_chirp,
                         "A new 2-20 kHz chirp; equal From and To make a tone"),
            self._button("Add reversed copy", self.add_reversed,
                         "A signal derived from the selected one by playing it backwards; "
                         "it follows the source when that is edited"),
            self._button("Delete", self.delete_signal,
                         "Refused while a design or another signal uses it")]
        return self._group("Signals  (edit a cell, Enter commits)", t, buttons)

    def _build_design(self):
        panel = QtWidgets.QWidget()
        box = QtWidgets.QVBoxLayout(panel)
        box.setContentsMargins(0, 0, 0, 0)
        top = QtWidgets.QHBoxLayout()
        self.design_box = QtWidgets.QComboBox()
        self.design_box.currentIndexChanged.connect(self._design_picked)
        top.addWidget(self.design_box, 1)
        top.addWidget(self._button("New", self.new_design))
        top.addWidget(self._button("Delete", self.delete_design))
        box.addLayout(top)

        form = QtWidgets.QFormLayout()
        self.design_name = QtWidgets.QLineEdit()
        self.design_name.editingFinished.connect(self._design_name_edited)
        self.receivers = QtWidgets.QLineEdit()
        self.receivers.setPlaceholderText("empty: every receiver")
        self.receivers.setToolTip("Transducer IDs that listen, separated by commas")
        self.receivers.editingFinished.connect(self._receivers_edited)
        self.listen = QtWidgets.QLineEdit()
        self.listen.setToolTip("Seconds to keep recording after the last event")
        self.listen.editingFinished.connect(self._listen_edited)
        self.default_detection = QtWidgets.QComboBox()
        self.default_detection.setToolTip(
            "The detection design that reads this ping design's returns unless a "
            "page or a replay chooses another")
        self.default_detection.currentIndexChanged.connect(self._default_detection_picked)
        form.addRow("Name", self.design_name)
        form.addRow("Receivers", self.receivers)
        form.addRow("Listen after (s)", self.listen)
        form.addRow("Detection design", self.default_detection)
        box.addLayout(form)

        t = self.event_table = QtWidgets.QTableWidget(0, len(EVENT_COLUMNS))
        t.setHorizontalHeaderLabels(EVENT_COLUMNS)
        t.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        t.verticalHeader().setVisible(False)
        t.horizontalHeader().setStretchLastSection(True)
        t.itemChanged.connect(self._event_edited)
        t.setItemDelegateForColumn(1, ComboDelegate(self._sender_choices, t))
        t.setItemDelegateForColumn(2, ComboDelegate(
            lambda: [(self.ws.name_of("signals", i), i) for i in self.ws.ids("signals")], t))
        box.addWidget(t)
        row = QtWidgets.QHBoxLayout()
        row.addWidget(self._button("Add event", self.add_event))
        row.addWidget(self._button("Delete event", self.delete_event))
        row.addStretch(1)
        box.addLayout(row)
        self.design_warnings = QtWidgets.QLabel()
        self.design_warnings.setWordWrap(True)
        self.design_warnings.setStyleSheet("color: #c0392b")
        box.addWidget(self.design_warnings)
        self.design_group = self._group("Ping design", panel)
        return self.design_group

    def _update_design_title(self):
        self.design_group.setTitle(
            "Ping design  (not used in replay: each recording carries its own)"
            if self.session.mode == REPLAY else "Ping design")

    def _build_centre(self):
        panel = QtWidgets.QWidget()
        box = QtWidgets.QVBoxLayout(panel)
        box.setContentsMargins(0, 0, 0, 0)
        self.headline = QtWidgets.QLabel("No ping yet. Press Space, or the Ping button.")
        self.headline.setWordWrap(True)
        font = self.headline.font()
        font.setBold(True)
        self.headline.setFont(font)
        box.addWidget(self.headline)
        bar = QtWidgets.QHBoxLayout()
        bar.addWidget(QtWidgets.QLabel("Receiver"))
        self.receiver_box = QtWidgets.QComboBox()
        self.receiver_box.currentIndexChanged.connect(lambda _: self._redraw())
        bar.addWidget(self.receiver_box)
        bar.addWidget(QtWidgets.QLabel("Detection"))
        self.detection_box = QtWidgets.QComboBox()
        self.detection_box.setToolTip(
            "How the returns are read: every threshold and window is in the "
            "detection design, and is recorded with the result")
        self.detection_box.currentIndexChanged.connect(self._detection_picked)
        bar.addWidget(self.detection_box)
        bar.addWidget(self._button(
            "Analyse again", self.reanalyse,
            "Read the latest ping again with the chosen detection design"))
        bar.addWidget(self._button("Edit...", self.edit_detection,
                                   "Edit detection designs"))
        bar.addWidget(QtWidgets.QLabel("Show (ms)"))
        self.span_edit = QtWidgets.QLineEdit(f"{self.span_ms:g}")
        self.span_edit.setMaximumWidth(60)
        self.span_edit.editingFinished.connect(self._span_edited)
        bar.addWidget(self.span_edit)
        self.echogram_check = QtWidgets.QCheckBox("Echogram")
        self.echogram_check.setChecked(True)
        self.echogram_check.toggled.connect(lambda on: self.echogram.setVisible(on))
        bar.addWidget(self.echogram_check)
        self.save_check = QtWidgets.QCheckBox("Save recordings")
        self.save_check.setToolTip("Write each ping to runs/<date>/ in the workspace")
        bar.addWidget(self.save_check)
        bar.addStretch(1)
        bar.addWidget(self._button("Reset zoom", self.reset_zoom))
        bar.addWidget(self._button("Clear", self.clear))
        box.addLayout(bar)

        t = self.result_table = QtWidgets.QTableWidget(0, len(RESULT_COLUMNS))
        t.setHorizontalHeaderLabels(RESULT_COLUMNS)
        t.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        t.verticalHeader().setVisible(False)
        t.horizontalHeader().setStretchLastSection(True)
        t.setMaximumHeight(150)
        box.addWidget(t)

        self.trace = pg.PlotWidget()
        self.trace.setLabel("bottom", "time after the first arrival (ms)")
        self.trace.setLabel("left", "level (dB below the strongest peak)")
        self.trace.showGrid(x=True, y=True, alpha=0.3)
        self.legend = self.trace.addLegend(offset=(-10, 10))
        self.trace.showAxis("top")
        top = self.trace.getAxis("top")
        top.setLabel("path length (m)")
        top.linkToView(self.trace.getViewBox())
        self.trace.getViewBox().sigRangeChangedManually.connect(
            lambda *_: setattr(self, "_zoomed", True))
        self.echogram = pg.GraphicsLayoutWidget()
        for w, stretch in ((self.trace, 3), (self.echogram, 2)):
            box.addWidget(w, stretch)
        return panel

    # ---- keeping the tables in step with the workspace -----------------

    def _changed(self, kind, object_id):
        self.revision += 1
        if kind in ("signals", "*"):
            self.fill_signals()
        if kind in ("ping_designs", "detection_designs", "signals", "*"):
            self.fill_designs()
        if kind in ("layouts", "scenes", "*"):
            self.fill_events()
        self._update_notes()

    def _source(self):
        s = self.session
        return (s.mode, s.scene_id if s.mode != REPLAY else str(s.replay and s.replay.path))

    def _backend_changed(self):
        self.revision += 1
        if self._source() != self._last_source:
            # Another scene, or live to replay: the old pings are not comparable.
            # (Editing the active scene keeps them, so a change shows up in the echogram.)
            self._last_source = self._source()
            self.clear()
        self._update_design_title()
        self.fill_events()
        self._update_notes()
        self._check_design()

    def refresh(self):
        self.fill_signals()
        self.fill_designs()
        self._update_notes()

    def _row_id(self, table, row):
        item = table.item(row, 0)
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def selected_signal_id(self):
        rows = self.signal_table.selectionModel().selectedRows()
        return self._row_id(self.signal_table, rows[0].row()) if rows else None

    def fill_signals(self):
        t, ws = self.signal_table, self.ws
        keep = self.selected_signal_id()
        self._filling = True
        t.setRowCount(0)
        for sid in ws.ids("signals"):
            data = ws.get("signals", sid)
            f0, f1, duration = signal_objects.band(ws.get_signal, sid)
            worth = signal_objects.worth(ws.get_signal, sid)
            derived = data["type"] == "derived"
            row = t.rowCount()
            t.insertRow(row)
            cells = {NAME: data["name"],
                     OP: data["op"] if derived else "chirp",
                     SOURCE: ws.name_of("signals", data["source"]) if derived else "",
                     F0: f"{f0:g}", F1: f"{f1:g}", LENGTH: f"{duration * 1e3:g}",
                     LEVEL: f"{signal_objects.level(ws.get_signal, sid):g}",
                     GAIN: f"{worth['gain_db']:.1f}",
                     RESOLUTION: ("" if worth["resolution_ms"] is None
                                  else f"{worth['resolution_ms']:.2f}"),
                     ID: sid}
            for column, text in cells.items():
                item = QtWidgets.QTableWidgetItem(text)
                editable = column == NAME or (derived and column in (OP, SOURCE)) or (
                    not derived and column in (F0, F1, LENGTH, LEVEL))
                if not editable:
                    read_only(item)
                if column == NAME:
                    item.setData(Qt.ItemDataRole.UserRole, sid)
                if column == OP and derived:
                    item.setData(Qt.ItemDataRole.UserRole, data["op"])
                if column == SOURCE and derived:
                    item.setData(Qt.ItemDataRole.UserRole, data["source"])
                t.setItem(row, column, item)
            if sid == keep:
                t.selectRow(row)
        t.resizeColumnsToContents()
        self._filling = False

    def _signal_edited(self, item):
        if self._filling:
            return
        sid = self._row_id(self.signal_table, item.row())
        column, text = item.column(), item.text().strip()
        try:
            if column == NAME:
                self.ws.update("signals", sid, name=text)
            elif column == OP:
                self.ws.update("signals", sid, op=item.data(Qt.ItemDataRole.UserRole))
            elif column == SOURCE:
                self.ws.update("signals", sid, source=item.data(Qt.ItemDataRole.UserRole))
            else:
                key, scale = {F0: ("f0", 1.0), F1: ("f1", 1.0), LENGTH: ("duration", 1e-3),
                              LEVEL: ("amplitude", 1.0)}[column]
                value = number(text, SIGNAL_COLUMNS[column]) * scale
                self.ws.update("signals", sid, **{key: value})
            self.status.emit("")
        except (WorkspaceError, ValueError) as error:
            self.status.emit(f"Not changed: {error}")
            self.fill_signals()         # put the old value back

    def add_chirp(self):
        sid = self.ws.create("signals", "new chirp", schema.new_chirp("", 2000, 20000, 0.02))
        self._select_signal(sid)

    def add_reversed(self):
        sid = self.selected_signal_id()
        if sid is None:
            self.status.emit("Select a signal to make a reversed copy of.")
            return
        name = self.ws.name_of("signals", sid) + " reversed"
        self._select_signal(self.ws.create(
            "signals", name, schema.new_derived("", "time_reverse", sid)))

    def delete_signal(self):
        sid = self.selected_signal_id()
        if sid is None:
            return
        try:
            self.ws.delete("signals", sid)
            self.status.emit("")
        except InUseError as error:
            self.status.emit(f"Not deleted: {error}")

    def _select_signal(self, sid):
        for row in range(self.signal_table.rowCount()):
            if self._row_id(self.signal_table, row) == sid:
                self.signal_table.selectRow(row)
                self.signal_table.editItem(self.signal_table.item(row, NAME))

    # ---- the ping design -----------------------------------------------

    def fill_designs(self):
        keep = self.design_id
        self._filling = True
        self.design_box.clear()
        for did in self.ws.ids("ping_designs"):
            self.design_box.addItem(self.ws.name_of("ping_designs", did), did)
        at = self.design_box.findData(keep)
        self.design_box.setCurrentIndex(at if at >= 0 else (0 if self.design_box.count() else -1))
        self._filling = False
        self.design_id = self.design_box.currentData()
        self.fill_detection()
        self.fill_events()

    def fill_detection(self):
        """The two detection design drop-downs: the page's choice (first
        entry: the ping design's own) and the ping design's default."""
        self._filling = True
        names = [(self.ws.name_of("detection_designs", i), i)
                 for i in self.ws.ids("detection_designs")]
        own = detections.of_ping_design(self.ws, self.design_id)
        self.detection_box.clear()
        self.detection_box.addItem("the ping design's own" + (
            f" ({self.ws.name_of('detection_designs', own)})" if own else
            " (none named: the first one)"), None)
        for name, i in names:
            self.detection_box.addItem(name, i)
        at = self.detection_box.findData(self.detection_id)
        self.detection_box.setCurrentIndex(max(at, 0))
        if at < 0:
            self.detection_id = None
        self.default_detection.clear()
        self.default_detection.addItem("(none)", None)
        for name, i in names:
            self.default_detection.addItem(name, i)
        self.default_detection.setCurrentIndex(max(self.default_detection.findData(own), 0))
        self._filling = False

    def _detection_picked(self, _):
        if self._filling:
            return
        self.detection_id = self.detection_box.currentData()
        self._update_notes()

    def _default_detection_picked(self, _):
        if self._filling or not self.design_id:
            return
        chosen = self.default_detection.currentData()
        if chosen != detections.of_ping_design(self.ws, self.design_id):
            self._edit_design(detection_design=chosen)

    def detection(self, capture=None):
        """(ID, DetectionDesign) in force: the page's choice, else the ping
        design's own (for a replayed recording, the one it was made with), else
        the first stored design."""
        own = detections.of_ping_design(self.ws, self.design_id)
        if capture is not None and capture.meta.get("backend") == "replay":
            own = (capture.ping.meta.get("detection_design") if capture.ping else None) or own
        return detections.resolve(self.ws, self.detection_id, own)

    def edit_detection(self):
        from ..ui.detection_dialog import DetectionDesignDialog
        dialog = DetectionDesignDialog(self.ws, self, self.detection()[0] or None)
        dialog.setModal(False)
        dialog.show()
        self._detection_dialog = dialog

    def _analyse(self, capture):
        """Read every recording of a capture with the detection design in
        force, and record which one was used with the capture."""
        did, design = self.detection(capture)
        capture.meta["detection_design"] = detections.record(did, design)
        return {rid: ranging.analyse_capture(capture, rid, design, did)
                for rid in capture.recordings}

    def reanalyse(self):
        """Read the latest ping again with the detection design now chosen."""
        if self.capture is None:
            self.status.emit("Nothing to analyse again yet: ping first.")
            return
        self.results = self._analyse(self.capture)
        for rid, result in self.results.items():
            if self.columns.get(rid):
                self.columns[rid] = self.columns[rid][:-1]
            self._add_column(rid, result)
        self._show_headline(f"Analysed again with {self.detection(self.capture)[1].summary()}")
        self._redraw()
        self._update_notes()

    def _show_headline(self, text):
        warnings = sorted({w for r in self.results.values() for w in r.warnings})
        self.headline.setText(text + ": " + ("; ".join(warnings) if warnings
                                              else "all events heard"))

    def _design_picked(self, _):
        if self._filling:
            return
        self.design_id = self.design_box.currentData()
        self.revision += 1
        self.fill_detection()
        self.fill_events()

    def _sender_choices(self):
        try:
            infos = self.session.backend().transducers()
        except ValueError:
            infos = []
        return [(t.name or t.id, t.id) for t in infos if t.can_send]

    def fill_events(self):
        design = self.ws.get("ping_designs", self.design_id) if self.design_id else None
        self._filling = True
        t = self.event_table
        t.setRowCount(0)
        enabled = design is not None
        for w in (self.design_name, self.receivers, self.listen, t,
                  self.default_detection):
            w.setEnabled(enabled)
        if design is None:
            self.design_name.clear(), self.receivers.clear(), self.listen.clear()
        else:
            if not self.design_name.hasFocus():
                self.design_name.setText(design["name"])
            if not self.receivers.hasFocus():
                self.receivers.setText(", ".join(design.get("receivers", [])))
            if not self.listen.hasFocus():
                self.listen.setText(f"{design['listen']:g}")
            names = {i.id: i.name for i in self._infos()}
            for n, event in enumerate(design["events"]):
                t.insertRow(n)
                number_item = read_only(QtWidgets.QTableWidgetItem(str(n + 1)))
                t.setItem(n, 0, number_item)
                tid = event["transducer"]
                cell = QtWidgets.QTableWidgetItem(names.get(tid, tid))
                cell.setData(Qt.ItemDataRole.UserRole, tid)
                t.setItem(n, 1, cell)
                cell = QtWidgets.QTableWidgetItem(self.ws.name_of("signals", event["signal"]))
                cell.setData(Qt.ItemDataRole.UserRole, event["signal"])
                t.setItem(n, 2, cell)
                t.setItem(n, 3, QtWidgets.QTableWidgetItem(f"{event['time'] * 1e3:g}"))
        t.resizeColumnsToContents()
        self._filling = False
        self._check_design()

    def _infos(self):
        try:
            return self.session.backend().transducers()
        except ValueError:
            return []

    def _check_design(self):
        """Tell the user now if the design cannot be played, or its events
        cannot be told apart, rather than at the first ping."""
        if not self.design_id:
            self.design_warnings.setText("")
            return
        try:
            ping = ranging.build_ping(self.ws, self.design_id, self._infos())
            self.design_warnings.setText("\n".join(ranging.ping_warnings(ping, self.detection()[1])))
        except ValueError as error:
            self.design_warnings.setText(str(error))

    def _edit_design(self, **changes):
        try:
            self.ws.update("ping_designs", self.design_id, **changes)
            self.status.emit("")
        except (WorkspaceError, ValueError) as error:
            self.status.emit(f"Not changed: {error}")
            self.fill_events()

    def _event_edited(self, item):
        if self._filling or not self.design_id:
            return
        events = self.ws.get("ping_designs", self.design_id)["events"]
        n, column = item.row(), item.column()
        try:
            if column == 1:
                events[n]["transducer"] = item.data(Qt.ItemDataRole.UserRole)
            elif column == 2:
                events[n]["signal"] = item.data(Qt.ItemDataRole.UserRole)
            elif column == 3:
                events[n]["time"] = number(item.text(), "Time") / 1e3
        except ValueError as error:
            self.status.emit(f"Not changed: {error}")
            self.fill_events()
            return
        self._edit_design(events=events)

    def _design_name_edited(self):
        if self.design_id and self.design_name.text().strip():
            self._edit_design(name=self.design_name.text().strip())

    def _receivers_edited(self):
        if self.design_id:
            ids = [r.strip() for r in self.receivers.text().split(",") if r.strip()]
            self._edit_design(receivers=ids)

    def _listen_edited(self):
        if not self.design_id:
            return
        try:
            self._edit_design(listen=number(self.listen.text(), "The listening time"))
        except ValueError as error:
            self.status.emit(f"Not changed: {error}")
            self.fill_events()

    def new_design(self):
        senders = [i for i in self._infos() if i.can_send]
        signals = self.ws.ids("signals")
        events = ([dict(transducer=senders[0].id, signal=signals[0], time=0.0)]
                  if senders and signals else [])
        self.design_id = self.ws.create("ping_designs", "new ping design", schema.new_design(
            "", events, receivers=[i.id for i in self._infos() if i.can_receive][:1]))

    def delete_design(self):
        if self.design_id:
            try:
                self.ws.delete("ping_designs", self.design_id)
            except InUseError as error:
                self.status.emit(f"Not deleted: {error}")

    def add_event(self):
        if not self.design_id:
            return
        design = self.ws.get("ping_designs", self.design_id)
        senders = [i.id for i in self._infos() if i.can_send]
        signals = self.ws.ids("signals")
        if not senders or not signals:
            self.status.emit("An event needs a signal and a transducer that can send.")
            return
        last = design["events"][-1] if design["events"] else None
        design["events"].append(dict(
            transducer=last["transducer"] if last else senders[0],
            signal=last["signal"] if last else signals[0],
            time=(last["time"] + 0.15) if last else 0.0))
        self._edit_design(events=design["events"])

    def delete_event(self):
        rows = self.event_table.selectionModel().selectedRows()
        if self.design_id and rows:
            events = self.ws.get("ping_designs", self.design_id)["events"]
            del events[rows[0].row()]
            self._edit_design(events=events)

    # ---- running -------------------------------------------------------

    def run_blocker(self):
        """Why the run controls are greyed out, or None."""
        if self.session.mode != REPLAY and not self.design_id:
            return "there is no ping design; add one on the left"
        try:
            self.session.backend()
        except ValueError as error:
            return str(error)
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
        try:
            backend = self.session.backend()
            if self.stream is None or self.stream_revision != self.revision:
                self._close_stream()
                ping = (None if self.session.mode == REPLAY else
                        ranging.build_ping(self.ws, self.design_id, backend.transducers()))
                self.stream = backend.open_stream(ping)
                self.stream_revision = self.revision
        except ValueError as error:
            self.status.emit(f"Check the ping design: {error}")
            self._stop_continuous()
            return
        self.worker = PingWorker(self.stream, self._analyse, self)
        self.worker.progressed.connect(lambda f, _t: self.progress.emit(f))
        self.worker.succeeded.connect(self._ping_done)
        self.worker.failed.connect(self._ping_failed)
        self.running_changed.emit(True)
        self.status.emit("Pinging...")
        self.worker.start()

    def stop(self):
        """End continuous pinging and cancel a ping in progress."""
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

    def _close_stream(self):
        if self.stream is not None:
            self.stream.close()
            self.stream = None

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

    def _ping_done(self, capture, results):
        self._finish_worker()
        self.count += 1
        self.capture = capture
        self.results = results
        current = self.receiver_box.currentData()
        self._filling = True
        self.receiver_box.clear()
        for rid in results:
            self.receiver_box.addItem(rid, rid)
        at = self.receiver_box.findData(current)
        self.receiver_box.setCurrentIndex(max(at, 0))
        self._filling = False
        for rid, result in results.items():
            self._add_column(rid, result)
        text = f"Ping {self.count}"
        if capture.meta.get("backend") == "replay":
            text = (f"Recording {capture.meta['index'] + 1} of {capture.meta['count']}"
                    f" ({Path(capture.meta['source']).name})")
        self._show_headline(text)
        saved = ""
        if self.save_check.isChecked() and capture.meta.get("backend") != "replay":
            if self.folder is None:
                stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
                self.folder = self.ws.path / "runs" / stamp
            for rid in capture.recordings:
                path = capture_io.save_capture(self.folder, self.count, capture, rid)
            saved = f"   [saved in {Path(path).parent.relative_to(self.ws.path)}]"
        self.status.emit(text + saved)
        self._redraw()
        if self.continuous:
            self.timer.start(int(self.session.interval * 1000))
        self._update_notes()

    # ---- display -------------------------------------------------------

    def _span_edited(self):
        try:
            span = number(self.span_edit.text(), "The time shown")
            if not 1 <= span <= 2000:
                raise ValueError("show between 1 and 2000 ms")
        except ValueError as error:
            self.status.emit(str(error))
            self.span_edit.setText(f"{self.span_ms:g}")
            return
        if span != self.span_ms:
            self.span_ms = span
            self.columns = {}
            for rid, result in self.results.items():
                self._add_column(rid, result)
            self._zoomed = False
            self._redraw()

    def reset_zoom(self):
        self._zoomed = False
        self._redraw()

    def clear(self):
        self.results, self.columns, self.count, self.folder = {}, {}, 0, None
        self.capture = None
        self.headline.setText("No ping yet.")
        self._redraw()

    def _add_column(self, rid, result):
        """Keep this ping's traces for the echogram. A ping that found
        nothing leaves a gap."""
        analysis = result.analysis
        n = len(analysis.events)
        if analysis.detected():
            column = [analysis.trace_db(i, BEFORE_MS, self.span_ms, FLOOR_DB)
                      for i in range(n)]
        else:
            column = [None] * n
        history = self.columns.get(rid, [])
        if history and len(history[-1]) != n:
            history = []                # the design changed shape: start again
        self.columns[rid] = (history + [column])[-HISTORY:]

    def _redraw(self):
        if self._filling:
            return
        self._fill_results()
        self._draw_trace()
        self._draw_echogram()

    def _fill_results(self):
        t = self.result_table
        t.setRowCount(0)
        for result in self.results.values():
            for row in result.rows:
                heard = row["delay_ms"] is not None
                shared = "".join(f" (with #{n})" for n in row["combined_with"])
                note = row["note"] or ("time of flight from the loopback"
                                       if row["mode"] == "loopback" and heard else "")
                if not row["heard"]:
                    note = "not heard"
                cells = [
                    str(row["number"]), row["receiver"], row["transducer"] + shared,
                    row["signal"], f"{row['sent_ms']:g}",
                    f"{row['delay_ms']:+.3f}" if heard else "",
                    f"{row['path_m']:+.3f}" if heard else "",
                    f"{row['level_db']:+.1f}" if heard else "",
                    f"{row['snr']:.0f}" if row["snr"] is not None else "",
                    f"{row['true_path_m']:.3f}" if row["true_path_m"] is not None else "",
                    f"{row['error_mm']:+.2f}" if row["error_mm"] is not None else "",
                    note]
                n = t.rowCount()
                t.insertRow(n)
                for column, text in enumerate(cells):
                    t.setItem(n, column, read_only(QtWidgets.QTableWidgetItem(text)))
        t.resizeColumnsToContents()

    def _draw_trace(self):
        plot = self.trace
        plot.clear()
        self.legend.clear()
        result = self.results.get(self.receiver_box.currentData())
        speed = result.sound_speed if result else media.sound_speed_air(20.0)
        plot.getAxis("top").setScale(speed / 1e3)
        if not self._zoomed:
            plot.setXRange(-BEFORE_MS, self.span_ms, padding=0)
            plot.setYRange(FLOOR_DB, 5, padding=0)
            self._zoomed = False
        if result is None:
            return
        analysis = result.analysis
        if not analysis.detected():
            self.headline.setText(f"Ping {self.count}: nothing detected ("
                                  + "; ".join(analysis.warnings) + ")")
            return
        rows = {r["number"] - 1: r for r in result.rows}
        for i, event in enumerate(analysis.events):
            heard = analysis.results[i] is not None
            c = colour(i)
            pen = pg.mkPen(c, width=1.2 if heard else 1)
            trace = analysis.trace_db(i, BEFORE_MS, self.span_ms, FLOOR_DB)
            x = np.linspace(-BEFORE_MS, self.span_ms, trace.size, endpoint=False)
            plot.plot(x, trace, pen=pen,
                      name=event.label + ("" if heard else " (not heard)"))
            if heard:
                at = analysis.delay_ms(i)
                if rows[i]["mode"] == "loopback" and rows[i]["delay_ms"] is not None:
                    at += rows[i]["delay_ms"]
                plot.addItem(pg.InfiniteLine(
                    pos=at, angle=90, pen=pg.mkPen(c, width=1, style=Qt.PenStyle.DashLine)))
            faint = QtGui.QColor(c)
            faint.setAlpha(110)
            for route, ms in ranging.truth_marks_ms(result, i):
                plot.addItem(pg.InfiniteLine(
                    pos=ms, angle=90, pen=pg.mkPen(faint, width=1,
                                                   style=Qt.PenStyle.DotLine)))

    def _draw_echogram(self):
        win = self.echogram
        win.clear()
        history = self.columns.get(self.receiver_box.currentData(), [])
        if not history:
            return
        lut = pg.colormap.get("viridis").getLookupTable(nPts=256)
        count = len(history)
        first = self.count - count + 1
        events = len(history[-1])
        label = {i: e.label for i, e in enumerate(
            self.results[self.receiver_box.currentData()].analysis.events)}
        for i in range(min(events, MAX_ECHOGRAMS)):
            columns = [c[i] for c in history]
            rows = max((c.size for c in columns if c is not None), default=0)
            if not rows:
                continue
            image = np.full((count, rows), FLOOR_DB)
            for n, c in enumerate(columns):
                if c is not None and c.size == rows:
                    image[n] = c
            plot = win.addPlot(col=i)
            plot.setTitle(label.get(i, f"event {i + 1}"), size="9pt")
            item = pg.ImageItem(image, lut=lut, levels=(FLOOR_DB, 0))
            item.setRect(QtCore.QRectF(first - 0.5, -BEFORE_MS, count,
                                       self.span_ms + BEFORE_MS))
            plot.addItem(item)
            plot.invertY(True)
            plot.setLabel("bottom", "ping number")
            if i == 0:
                plot.setLabel("left", "ms")
            plot.setMouseEnabled(x=True, y=True)
            plot.setXRange(first - 0.5, first - 0.5 + max(count, 10), padding=0)
            plot.setYRange(-BEFORE_MS, self.span_ms, padding=0)

    # ---- notes ---------------------------------------------------------

    def _update_notes(self):
        scene = self.ws.get("scenes", self.session.scene_id or "")
        temp = scene["medium"]["temperature_c"] if scene else 20.0
        speed = float(media.sound_speed_air(temp))
        rate = next((i.rate for i in self._infos() if i.rate), 48000)
        sid = self.selected_signal_id()
        details = "Select a signal in the table to see what it is worth."
        resolution_line = gain_line = ""
        if sid:
            f0, f1, duration = signal_objects.band(self.ws.get_signal, sid)
            worth = signal_objects.worth(self.ws.get_signal, sid)
            wavelength = media.wavelength(speed, max((f0 + f1) / 2, 1.0)) * 1e3
            details = (f"{f0:g} to {f1:g} Hz over {duration * 1e3:g} ms: bandwidth "
                       f"{worth['bandwidth_hz']:g} Hz, wavelength at the middle "
                       f"{wavelength:.1f} mm.")
            if worth["resolution_ms"]:
                resolution_line = (f"For this signal: {worth['resolution_ms']:.2f} ms, "
                                   f"or {worth['resolution_ms'] * speed:.0f} mm of path.")
            gain_line = f"{worth['gain_db']:.1f} dB for this signal."
        text = string.Template(NOTES.read_text()).safe_substitute(
            temperature=f"{temp:g}", speed=f"{speed:.1f}", rate=f"{rate:g}",
            mm_per_ms=f"{speed:.0f}", mm_per_sample=f"{speed / rate * 1e3:.2f}",
            signal=self.ws.name_of("signals", sid) if sid else "none",
            details=details, resolution_line=resolution_line, gain_line=gain_line)
        bar = self.notes.verticalScrollBar().value()
        self.notes.setMarkdown(text)
        self.notes.verticalScrollBar().setValue(bar)

    def shutdown(self):
        self.timer.stop()
        self.continuous = False
        if self.worker is not None:
            self.worker.cancel()
            self.worker.wait()
        self._close_stream()
