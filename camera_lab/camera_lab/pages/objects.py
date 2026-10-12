"""Objects: edit any workspace object (sensors, lenses, ports, media, rigs,
scenes), copy it to try a variation, delete it."""
from ..objects import schema
from ..qtcompat import Qt, QtWidgets
from ..ui.widgets import FieldsPanel
from .base import Page


class ObjectsPage(Page):
    title = "Objects"

    def __init__(self, ws, session, parent=None):
        super().__init__(ws, session, parent)
        lay = QtWidgets.QHBoxLayout(self)
        left = QtWidgets.QVBoxLayout()
        self.kind_box = QtWidgets.QComboBox()
        for k in schema.KINDS:
            self.kind_box.addItem(schema.TITLES[k], k)
        self.list = QtWidgets.QListWidget()
        self.list.setMinimumWidth(260)
        buttons = QtWidgets.QHBoxLayout()
        self.copy_button = QtWidgets.QPushButton("Copy")
        self.copy_button.setToolTip("Make a copy to change, keeping the original for comparison.")
        self.delete_button = QtWidgets.QPushButton("Delete")
        buttons.addWidget(self.copy_button)
        buttons.addWidget(self.delete_button)
        left.addWidget(self.kind_box)
        left.addWidget(self.list, 1)
        left.addLayout(buttons)
        lay.addLayout(left)
        right = QtWidgets.QVBoxLayout()
        self.title_label = QtWidgets.QLabel()
        self.title_label.setStyleSheet("font-weight: bold;")
        self.form = FieldsPanel(ws)
        self.used = QtWidgets.QLabel()
        self.used.setWordWrap(True)
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.form)
        right.addWidget(self.title_label)
        right.addWidget(scroll, 1)
        right.addWidget(self.used)
        lay.addLayout(right, 1)
        self.kind_box.currentIndexChanged.connect(self.schedule)
        self.list.currentItemChanged.connect(lambda *_: self._select())
        self.copy_button.clicked.connect(self._copy)
        self.delete_button.clicked.connect(self._delete)
        self._building = False

    def kind(self):
        return self.kind_box.currentData()

    def _current_id(self):
        item = self.list.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _redraw(self):
        if self.visible_now:
            self.redraw()

    def redraw(self):
        kind, keep = self.kind(), self._current_id()
        self._building = True
        self.list.clear()
        for i in self.ws.ids(kind):
            item = QtWidgets.QListWidgetItem(self.ws.name_of(kind, i))
            item.setData(Qt.ItemDataRole.UserRole, i)
            self.list.addItem(item)
            if i == keep:
                self.list.setCurrentItem(item)
        if self.list.currentItem() is None and self.list.count():
            self.list.setCurrentRow(0)
        self._building = False
        self._select()

    def _select(self):
        if self._building:
            return
        kind, oid = self.kind(), self._current_id()
        self.form.set_object(kind, oid)
        self.copy_button.setEnabled(oid is not None)
        self.delete_button.setEnabled(oid is not None)
        if oid is None:
            self.title_label.setText("")
            self.used.setText("")
            return
        data = self.ws.get(kind, oid)
        self.title_label.setText(f"{schema.SINGULAR[kind]} '{oid}'")
        users = self.ws.uses(kind, oid)
        self.used.setText("Used by: " + (", ".join(self.ws.name_of(k, i) for k, i in users) or "nothing")
                          + ".   Fields have tooltips that say what they mean.")

    def _copy(self):
        kind, oid = self.kind(), self._current_id()
        if oid:
            new = self.ws.duplicate(kind, oid)
            self._select_id(new)

    def _select_id(self, oid):
        self.redraw()
        for r in range(self.list.count()):
            if self.list.item(r).data(Qt.ItemDataRole.UserRole) == oid:
                self.list.setCurrentRow(r)

    def _delete(self):
        kind, oid = self.kind(), self._current_id()
        if not oid:
            return
        try:
            self.ws.delete(kind, oid)
        except schema.WorkspaceError as error:
            QtWidgets.QMessageBox.information(self, "Cannot delete", str(error))
