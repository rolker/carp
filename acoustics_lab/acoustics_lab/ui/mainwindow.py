"""The main window: pages down the left, a toolbar for what applies
everywhere (backend, scene, run), undo and redo, and a status bar."""
from pathlib import Path

from .. import importers
from ..backends.simulation import sound_speed
from ..pages.placeholder import PlaceholderPage
from ..pages.ranging import RangingPage
from ..pages.room import RoomSonarPage
from ..qtcompat import Qt, QAction, QtCore, QtGui, QtWidgets, Signal
from .detection_dialog import DetectionDesignDialog
from .rig_editor import RigEditor
from .session import HARDWARE, REPLAY, SIMULATION, Session

GROUPS = [
    ("Foundations", ["Signals", "Transducers", "Beam patterns", "Sound speed",
                     "Propagation", "Echo sounding & backscatter", "Doppler", "Noise",
                     "Receiver chain"]),
    ("Systems", ["Room sonar", "Ranging & positioning", "Comms", "Multibeam design",
                 "Sonar equation"]),
]
FIRST_PAGE = "Ranging & positioning"
PAGES = {"Ranging & positioning": RangingPage, "Room sonar": RoomSonarPage}
MAX_RECENT = 8


class MainWindow(QtWidgets.QMainWindow):
    """Signal: workspace_requested(path) when the user opens another
    workspace; the application replaces this window."""

    workspace_requested = Signal(str)

    def __init__(self, workspace, settings, replay=None, environment=None):
        super().__init__()
        self.ws = workspace
        self.settings = settings
        self.session = Session(workspace, self, environment)
        self.pages = {}
        self.dialogs = {}
        self.closer = None
        self.setWindowTitle(f"acoustics_lab - {workspace.name}  ({workspace.path})")
        self.resize(1500, 880)

        self._build_pages()
        self._build_menus()
        self._build_toolbar()
        self._build_status()
        self.session.backend_changed.connect(self._backend_changed)
        self.session.interval_changed.connect(self._interval_changed)
        self.session.hardware_message.connect(self._hardware_message)
        self.ws.changed.connect(self._workspace_changed)
        self.ws.reloaded.connect(self._reloaded)
        self.ws.start_watching()
        self._sync_toolbar()
        self.page_list.setCurrentRow(self._row_of(FIRST_PAGE))
        if workspace.problems:
            self.statusBar().showMessage("Unreadable files: " + "; ".join(workspace.problems))
        elif workspace.notices:
            self.statusBar().showMessage("; ".join(workspace.notices))
        if replay is not None:
            self.open_replay(replay)
        geometry = settings.value("geometry")
        if geometry is not None:
            self.restoreGeometry(geometry)

    # ---- pages ---------------------------------------------------------

    def _build_pages(self):
        split = QtWidgets.QSplitter(Qt.Orientation.Horizontal)
        self.page_list = QtWidgets.QListWidget()
        self.page_list.setMaximumWidth(210)
        self.page_list.setMinimumWidth(150)
        self.stack = QtWidgets.QStackedWidget()
        self._rows = {}
        for group, titles in GROUPS:
            header = QtWidgets.QListWidgetItem(group.upper())
            header.setFlags(Qt.ItemFlag.NoItemFlags)
            font = header.font()
            font.setBold(True)
            font.setPointSizeF(font.pointSizeF() * 0.85)
            header.setFont(font)
            self.page_list.addItem(header)
            for title in titles:
                self.page_list.addItem("  " + title)
                self._rows[title] = self.page_list.count() - 1
        self.page_list.currentRowChanged.connect(self._page_chosen)
        split.addWidget(self.page_list)
        split.addWidget(self.stack)
        split.setStretchFactor(1, 1)
        self.setCentralWidget(split)

    def _row_of(self, title):
        return self._rows[title]

    def _title_at(self, row):
        return next((t for t, r in self._rows.items() if r == row), None)

    def page(self, title):
        """The page with this title, built the first time it is wanted."""
        if title not in self.pages:
            if title in PAGES:
                page = PAGES[title](self.session)
                page.status.connect(self.statusBar().showMessage)
                page.progress.connect(self._progress)
                page.running_changed.connect(lambda _: self._sync_run())
                page.stopped.connect(lambda: self.continuous_action.setChecked(False))
            else:
                page = PlaceholderPage(title)
            self.pages[title] = page
            self.stack.addWidget(page)
        return self.pages[title]

    def current_page(self):
        return self.stack.currentWidget()

    def _page_chosen(self, row):
        title = self._title_at(row)
        if title is None:
            return
        self.stack.setCurrentWidget(self.page(title))
        self._sync_run()
        self.notes_action.setEnabled(hasattr(self.current_page(), "notes"))

    # ---- menus ---------------------------------------------------------

    def _build_menus(self):
        bar = self.menuBar()
        file = bar.addMenu("&File")
        file.addAction(self._action("Open workspace...", self.choose_workspace, "Ctrl+O"))
        file.addAction(self._action("Rigs...", self.edit_rigs,
                                    tip="Which device and channel each transducer is on"))
        file.addAction(self._action("Detection designs...", self.edit_detection,
                                    tip="How returns are found and measured"))
        self.recent_menu = file.addMenu("Recent workspaces")
        self._fill_recent()
        file.addSeparator()
        file.addAction(self._action("Import carp/acoustic designs...", self.import_designs,
                                    tip="Old ping designs become signals and ping designs"))
        file.addAction(self._action("Open recordings folder for replay...",
                                    lambda: self.choose_replay(folder=True)))
        file.addAction(self._action("Open one recording (WAV) for replay...",
                                    lambda: self.choose_replay(folder=False)))
        file.addSeparator()
        file.addAction(self._action("Quit", self.close, "Ctrl+Q"))

        edit = bar.addMenu("&Edit")
        stack = self.ws.undo_stack
        self.undo_action = stack.createUndoAction(self, "Undo")
        self.undo_action.setShortcut(QtGui.QKeySequence.StandardKey.Undo)
        self.redo_action = stack.createRedoAction(self, "Redo")
        self.redo_action.setShortcuts([QtGui.QKeySequence("Ctrl+Shift+Z"),
                                       QtGui.QKeySequence("Ctrl+Y")])
        edit.addAction(self.undo_action)
        edit.addAction(self.redo_action)

        view = bar.addMenu("&View")
        self.history = QtWidgets.QDockWidget("History", self)
        self.history.setWidget(QtWidgets.QUndoView(stack))
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.history)
        self.history.hide()
        view.addAction(self.history.toggleViewAction())
        self.hardware_dock = QtWidgets.QDockWidget("Hardware messages", self)
        self.hardware_log = QtWidgets.QPlainTextEdit()
        self.hardware_log.setReadOnly(True)
        self.hardware_dock.setWidget(self.hardware_log)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self.hardware_dock)
        self.hardware_dock.hide()
        view.addAction(self.hardware_dock.toggleViewAction())
        self.notes_action = self._action("Notes", self._toggle_notes, tip="Show or hide the notes")
        self.notes_action.setCheckable(True)
        self.notes_action.setChecked(True)
        view.addAction(self.notes_action)

    def _action(self, text, slot, shortcut=None, tip=""):
        action = QAction(text, self)
        action.triggered.connect(lambda _=False: slot())
        if shortcut:
            action.setShortcut(QtGui.QKeySequence(shortcut))
        if tip:
            action.setToolTip(tip)
            action.setStatusTip(tip)
        return action

    def _toggle_notes(self):
        page = self.current_page()
        if hasattr(page, "notes"):
            page.notes.setVisible(self.notes_action.isChecked())

    def _fill_recent(self):
        self.recent_menu.clear()
        for path in self.settings.value("recent", [], type=list):
            self.recent_menu.addAction(self._action(
                path, lambda p=path: self.workspace_requested.emit(p)))
        self.recent_menu.setEnabled(not self.recent_menu.isEmpty())

    # ---- toolbar -------------------------------------------------------

    def _build_toolbar(self):
        tb = self.addToolBar("Run")
        tb.setObjectName("run")
        tb.setMovable(False)
        tb.addWidget(QtWidgets.QLabel(" Backend "))
        self.backend_box = QtWidgets.QComboBox()
        for label, mode in (("Simulation", SIMULATION), ("Replay", REPLAY),
                            ("Hardware", HARDWARE)):
            self.backend_box.addItem(label, mode)
        self.backend_box.currentIndexChanged.connect(self._backend_picked)
        tb.addWidget(self.backend_box)

        self.rig_label = QtWidgets.QLabel("  Rig ")
        self.rig_box = QtWidgets.QComboBox()
        self.rig_box.setMinimumWidth(150)
        self.rig_box.currentIndexChanged.connect(self._rig_picked)
        self.rigs_button = QtWidgets.QPushButton("Rigs...")
        self.rigs_button.setToolTip("Edit rigs: devices, channels, loopbacks, Identify")
        self.rigs_button.clicked.connect(lambda: self.edit_rigs())
        self.scene_label = QtWidgets.QLabel("  Scene ")
        self.scene_box = QtWidgets.QComboBox()
        self.scene_box.setMinimumWidth(170)
        self.scene_box.currentIndexChanged.connect(self._scene_picked)
        self.as_built_button = QtWidgets.QPushButton("As built")
        self.as_built_button.setToolTip(
            "Make the rig's as-built scene the active one: the bench as it is")
        self.as_built_button.clicked.connect(lambda: self.session.use_as_built())
        self.built_label = QtWidgets.QLabel()
        self.temp_label = QtWidgets.QLabel("  Air ")
        self.temp = QtWidgets.QDoubleSpinBox()
        self.temp.setRange(-40.0, 60.0)
        self.temp.setSingleStep(0.5)
        self.temp.setDecimals(1)
        self.temp.setSuffix(" °C")
        self.temp.setKeyboardTracking(False)
        self.temp.valueChanged.connect(self._temperature_edited)
        self.speed_label = QtWidgets.QLabel()
        self.replay_label = QtWidgets.QLabel()
        self.replay_button = QtWidgets.QPushButton("Open recordings...")
        self.replay_button.clicked.connect(lambda: self.choose_replay(folder=True))
        self.rig_widgets = [tb.addWidget(w) for w in (self.rig_label, self.rig_box,
                                                       self.rigs_button)]
        self.sim_widgets = [tb.addWidget(w) for w in (self.scene_label, self.scene_box)]
        self.scene_widgets = [tb.addWidget(w) for w in (self.temp_label, self.temp,
                                                         self.speed_label)]
        self.built_widgets = [tb.addWidget(w) for w in (self.as_built_button, self.built_label)]
        self.replay_widgets = [tb.addWidget(w) for w in (self.replay_button, self.replay_label)]
        tb.addSeparator()

        self.ping_action = self._action("Ping", self._ping, "Space",
                                        "Send one ping (Space)")
        self.continuous_action = self._action("Continuous", lambda: None)
        self.continuous_action.setCheckable(True)
        self.continuous_action.toggled.connect(self._continuous)
        tb.addAction(self.ping_action)
        tb.addAction(self.continuous_action)
        tb.addWidget(QtWidgets.QLabel(" every "))
        self.interval = QtWidgets.QDoubleSpinBox()
        self.interval.setRange(0.0, 60.0)
        self.interval.setDecimals(3)
        self.interval.setValue(self.session.interval)
        self.interval.setSuffix(" s")
        self.interval.valueChanged.connect(self.session.set_interval)
        tb.addWidget(self.interval)
        for action in (self.ping_action, self.continuous_action):
            widget = tb.widgetForAction(action)
            if widget is not None:
                widget.setMinimumWidth(80)

    def _backend_picked(self, _):
        self.session.set_mode(self.backend_box.currentData())

    def _scene_picked(self, _):
        if self.scene_box.currentData():
            self.session.set_scene(self.scene_box.currentData())

    def _rig_picked(self, _):
        self.session.set_rig(self.rig_box.currentData())

    def _interval_changed(self, seconds):
        if self.interval.value() != seconds:
            self.interval.blockSignals(True)
            self.interval.setValue(seconds)
            self.interval.blockSignals(False)

    def _temperature_edited(self, value):
        scene = self.ws.get("scenes", self.session.scene_id or "")
        if scene and scene["medium"]["temperature_c"] != value:
            medium = dict(scene["medium"], temperature_c=value)
            self.ws.update("scenes", self.session.scene_id,
                           f"set temperature of {scene['name']} to {value:g} C",
                           medium=medium)

    def _sync_toolbar(self):
        """Bring the toolbar in line with the session and the workspace."""
        s = self.session
        boxes = (self.backend_box, self.scene_box, self.temp, self.rig_box)
        for box in boxes:
            box.blockSignals(True)
        self.backend_box.setCurrentIndex(self.backend_box.findData(s.mode))
        self.scene_box.clear()
        for sid in self.ws.ids("scenes"):
            self.scene_box.addItem(self.ws.name_of("scenes", sid), sid)
        self.scene_box.setCurrentIndex(self.scene_box.findData(s.scene_id))
        self.rig_box.clear()
        for rid in self.ws.ids("rigs"):
            self.rig_box.addItem(self.ws.name_of("rigs", rid), rid)
        if not self.rig_box.count():
            self.rig_box.addItem("(none)", None)
        self.rig_box.setCurrentIndex(max(self.rig_box.findData(s.rig_id), 0))
        scene = self.ws.get("scenes", s.scene_id or "")
        if scene:
            self.temp.setValue(scene["medium"]["temperature_c"])
            self.speed_label.setText(f"  {sound_speed(scene['medium']):.1f} m/s")
        for box in boxes:
            box.blockSignals(False)
        replaying = s.mode == REPLAY
        for action in self.sim_widgets:
            action.setVisible(s.mode == SIMULATION)
        for action in self.scene_widgets:
            action.setVisible(not replaying)
        for action in self.rig_widgets:
            action.setVisible(not replaying)
        for action in self.replay_widgets:
            action.setVisible(replaying)
        text, warning = s.built_text()
        for action in self.built_widgets:
            action.setVisible(not replaying and bool(self.ws.ids("rigs")))
        self.as_built_button.setEnabled(s.mode == SIMULATION and not s.is_as_built())
        self.built_label.setText("  " + text if text else "")
        self.built_label.setStyleSheet("color: #d35400; font-weight: bold" if warning else "")
        self.replay_label.setText("  " + s.describe() if replaying else "")
        self.backend_label.setText(s.describe())
        self._sync_run()

    def _backend_changed(self):
        self._sync_toolbar()

    def _workspace_changed(self, kind, object_id):
        if kind in ("scenes", "layouts", "rigs"):
            self._sync_toolbar()
        elif kind == "ping_designs":
            self._sync_run()

    def _reloaded(self, message):
        self._sync_toolbar()
        self.statusBar().showMessage(message)

    def _sync_run(self):
        """Grey out the run controls, with the reason, where the page or
        backend cannot run an experiment."""
        self.backend_label.setText(self.session.describe())
        page = self.current_page()
        if page is None:
            return
        reason = page.run_blocker()
        busy = getattr(page, "busy", False)
        for action in (self.ping_action, self.continuous_action):
            action.setEnabled(reason is None)
            action.setToolTip(reason and f"Cannot run: {reason}" or action.statusTip()
                              or "Send one ping (Space)")
        if reason is None and self.session.mode == REPLAY:
            self.ping_action.setText("Next")
        else:
            self.ping_action.setText("Ping")
        self.ping_action.setEnabled(reason is None and not busy)

    def _ping(self):
        page = self.current_page()
        if getattr(page, "supports_run", False):
            page.ping()

    def _continuous(self, on):
        page = self.current_page()
        if getattr(page, "supports_run", False):
            page.set_continuous(on)
        elif on:
            self.continuous_action.setChecked(False)

    # ---- editors and the hardware's messages -----------------------------

    def _hardware_message(self, level, text):
        self.hardware_log.appendPlainText(("WARNING: " if level == "warning" else "") + text)
        if level == "warning":
            self.hardware_dock.show()
            self.statusBar().showMessage("Hardware: " + text.splitlines()[0])

    def edit_rigs(self):
        dialog = RigEditor(self.session, self)
        dialog.setModal(False)
        dialog.show()
        self.dialogs["rigs"] = dialog
        return dialog

    def edit_detection(self):
        dialog = DetectionDesignDialog(self.ws, self)
        dialog.setModal(False)
        dialog.show()
        self.dialogs["detection"] = dialog
        return dialog

    # ---- status bar ----------------------------------------------------

    def _build_status(self):
        self.backend_label = QtWidgets.QLabel()
        self.progress_bar = QtWidgets.QProgressBar()
        self.progress_bar.setMaximumWidth(140)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.hide()
        self.statusBar().addPermanentWidget(self.progress_bar)
        self.statusBar().addPermanentWidget(self.backend_label)

    def _progress(self, fraction):
        if fraction < 0:
            self.progress_bar.hide()
        else:
            self.progress_bar.show()
            self.progress_bar.setValue(int(fraction * 100))

    # ---- workspace and files -------------------------------------------

    def choose_workspace(self):
        path = QtWidgets.QFileDialog.getExistingDirectory(
            self, "Open or create a workspace folder", str(self.ws.path.parent))
        if path:
            self.workspace_requested.emit(path)

    def import_designs(self):
        guess = Path(__file__).resolve().parents[3] / "acoustic" / "designs"
        start = str(guess) if guess.is_dir() else str(Path.home())
        folder = QtWidgets.QFileDialog.getExistingDirectory(
            self, "Folder of carp/acoustic ping designs (*.json)", start)
        if folder:
            self.run_import(folder)

    def run_import(self, folder):
        messages = importers.import_designs(self.ws, folder)
        self.statusBar().showMessage("; ".join(messages))

    def choose_replay(self, folder=True):
        guess = Path(__file__).resolve().parents[3] / "acoustic" / "runs"
        start = str(guess) if guess.is_dir() else str(Path.home())
        if folder:
            path = QtWidgets.QFileDialog.getExistingDirectory(
                self, "Folder of recordings (WAV files with .json beside them)", start)
        else:
            path, _ = QtWidgets.QFileDialog.getOpenFileName(
                self, "Recording", start, "WAV files (*.wav)")
        if path:
            self.open_replay(path)

    def open_replay(self, path):
        try:
            self.session.open_replay(path)
            self.statusBar().showMessage(f"Replay: {self.session.describe()}. "
                                         "Press Space for the next recording.")
        except (ValueError, OSError) as error:
            self.statusBar().showMessage(f"Cannot open recordings: {error}")

    def closeEvent(self, event):
        for page in self.pages.values():
            page.shutdown()
        for dialog in self.dialogs.values():
            dialog.close()
        if self.session.mode == HARDWARE or self.session._hardware is not None:
            self.statusBar().showMessage("Putting the sound card, its mixer and the "
                                         "desktop's volumes back ...")
            QtWidgets.QApplication.processEvents()
        self.session.close_hardware()
        self.ws.stop_watching()
        self.settings.setValue("geometry", self.saveGeometry())
        super().closeEvent(event)
