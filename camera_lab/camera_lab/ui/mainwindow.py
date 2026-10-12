"""The window: pages on the left with the rig list below, a toolbar for the
scene and medium, undo and redo in the Edit menu."""
from ..pages.fov import FovPage
from ..pages.objects import ObjectsPage
from ..pages.placeholder import PlaceholderPage
from ..pages.resolution import ResolutionPage
from ..pages.stereo import StereoPage
from ..qtcompat import QAction, Qt, QtCore, QtWidgets
from .session import Session
from .widgets import colour

PLACEHOLDERS = [
    ("Ports & domes", "Ray trace through a dome with the pupil off centre, virtual image against object "
                      "distance, flat-port caustic and colour fringes (the models exist in "
                      "<code>models/ports.py</code>; the page does not)."),
    ("Visibility & attenuation", "Contrast and light against range and depth for the water: attenuation, "
                                "veiling light, and what lights add. See the design document."),
    ("Measurements", "Put bench and water measurements (a checkerboard through the domes, a ruler at known "
                     "ranges) on the same axes as the models."),
]


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self, ws, settings=None):
        super().__init__()
        self.ws, self.settings = ws, settings
        self.session = Session(ws)
        self.setWindowTitle(f"camera_lab - {ws.path.name}")
        self.resize(1500, 920)
        self.pages = [FovPage(ws, self.session), StereoPage(ws, self.session),
                      ResolutionPage(ws, self.session), ObjectsPage(ws, self.session)]
        self.pages += [PlaceholderPage(ws, self.session, t, x) for t, x in PLACEHOLDERS]

        left = QtWidgets.QWidget()
        ll = QtWidgets.QVBoxLayout(left)
        ll.setContentsMargins(4, 4, 4, 4)
        self.page_list = QtWidgets.QListWidget()
        for p in self.pages:
            self.page_list.addItem(p.title)
        self.page_list.setMaximumHeight(26 * len(self.pages) + 10)
        ll.addWidget(QtWidgets.QLabel("Pages"))
        ll.addWidget(self.page_list)
        ll.addWidget(QtWidgets.QLabel("Rigs: tick to show, select one as primary"))
        self.rig_list = QtWidgets.QListWidget()
        ll.addWidget(self.rig_list, 1)
        dock = QtWidgets.QDockWidget("Navigation", self)
        dock.setWidget(left)
        dock.setFeatures(QtWidgets.QDockWidget.DockWidgetFeature.DockWidgetMovable)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, dock)
        left.setMinimumWidth(210)

        self.stack = QtWidgets.QStackedWidget()
        for p in self.pages:
            self.stack.addWidget(p)
        self.setCentralWidget(self.stack)

        tb = self.addToolBar("Selection")
        tb.setMovable(False)
        tb.addWidget(QtWidgets.QLabel(" Scene: "))
        self.scene_box = QtWidgets.QComboBox()
        tb.addWidget(self.scene_box)
        tb.addWidget(QtWidgets.QLabel("   Medium: "))
        self.medium_box = QtWidgets.QComboBox()
        self.medium_box.setToolTip("Look into this medium instead of the scene's own, to compare air, "
                                   "fresh and salt water.")
        tb.addWidget(self.medium_box)

        edit = self.menuBar().addMenu("&Edit")
        self.undo_action = ws.undo_stack.createUndoAction(self, "&Undo")
        self.undo_action.setShortcut("Ctrl+Z")
        self.redo_action = ws.undo_stack.createRedoAction(self, "&Redo")
        self.redo_action.setShortcut("Ctrl+Shift+Z")
        edit.addAction(self.undo_action)
        edit.addAction(self.redo_action)
        self.statusBar().showMessage(f"Workspace: {ws.path}")
        ws.reloaded.connect(self.statusBar().showMessage)

        self.page_list.currentRowChanged.connect(self._page_changed)
        self.scene_box.activated.connect(self._scene_picked)
        self.medium_box.activated.connect(self._medium_picked)
        self.rig_list.itemChanged.connect(self._rig_checked)
        self.rig_list.currentItemChanged.connect(self._rig_primary)
        ws.changed.connect(lambda *_: self._refill_lists())
        self._filling = False
        self._refill_lists()
        self.page_list.setCurrentRow(0)
        ws.start_watching()

    # ---- helpers for tests and screenshots ----------------------------

    def page(self, title):
        return next(p for p in self.pages if p.title == title)

    def show_page(self, title):
        self.page_list.setCurrentRow(next(i for i, p in enumerate(self.pages) if p.title == title))

    def current_page(self):
        return self.pages[self.page_list.currentRow()]

    def _page_changed(self, row):
        if row >= 0:
            self.stack.setCurrentIndex(row)

    # ---- lists -----------------------------------------------------------

    def _refill_lists(self):
        s, ws = self.session, self.ws
        self._filling = True
        try:
            self.scene_box.clear()
            for i in ws.ids("scenes"):
                self.scene_box.addItem(ws.name_of("scenes", i), i)
            if s.scene_id not in ws.ids("scenes"):
                s.scene_id = self.scene_box.itemData(0)
            self.scene_box.setCurrentIndex(max(0, self.scene_box.findData(s.scene_id)))
            self.medium_box.clear()
            self.medium_box.addItem("(the scene's own)", None)
            for i in ws.ids("media"):
                self.medium_box.addItem(ws.name_of("media", i), i)
            self.medium_box.setCurrentIndex(max(0, self.medium_box.findData(s.medium_override)))
            self.rig_list.clear()
            ids = ws.ids("rigs")
            s.shown &= set(ids)
            if s.primary_id not in ids:
                s.primary_id = ids[0] if ids else None
            for i in ids:
                item = QtWidgets.QListWidgetItem(ws.name_of("rigs", i))
                item.setData(Qt.ItemDataRole.UserRole, i)
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(Qt.CheckState.Checked if i in s.shown else Qt.CheckState.Unchecked)
                item.setForeground(colour(ids.index(i)))
                f = item.font()
                f.setBold(i == s.primary_id)
                item.setFont(f)
                self.rig_list.addItem(item)
                if i == s.primary_id:
                    self.rig_list.setCurrentItem(item)
        finally:
            self._filling = False

    def _scene_picked(self, _):
        self.session.set(scene_id=self.scene_box.currentData())

    def _medium_picked(self, _):
        self.session.set(medium_override=self.medium_box.currentData())

    def _rig_checked(self, item):
        if self._filling:
            return
        rid = item.data(Qt.ItemDataRole.UserRole)
        shown = set(self.session.shown)
        (shown.add if item.checkState() == Qt.CheckState.Checked else shown.discard)(rid)
        self.session.set(shown=shown)

    def _rig_primary(self, item, _previous=None):
        if self._filling or item is None:
            return
        rid = item.data(Qt.ItemDataRole.UserRole)
        if rid != self.session.primary_id:
            self.session.primary_id = rid
            self._refill_lists()
            self.session.changed.emit()

    def closeEvent(self, event):
        self.ws.stop_watching()
        super().closeEvent(event)
