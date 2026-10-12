"""The detection design editor: a list of designs and a table of every
setting, edited in place (one committed cell is one undo step), with what each
setting does beside it. Every choice about how a return is found is here
(design.md, principle 7)."""
from ..models import detection_design as dd
from ..objects.schema import InUseError, WorkspaceError
from ..qtcompat import Qt, QtWidgets
from .widgets import read_only

KEY, LABEL, VALUE, UNIT, DEFAULT_COLUMN, TEXT = range(6)
COLUMNS = ["", "Setting", "Value", "Unit", "Default", "What it does"]


class DetectionDesignDialog(QtWidgets.QDialog):
    def __init__(self, workspace, parent=None, select=None):
        super().__init__(parent)
        self.ws = workspace
        self.design_id = select
        self._filling = False
        self.setWindowTitle("Detection designs")
        self.resize(980, 640)
        self._build()
        workspace.changed.connect(self._changed)
        self.fill_list()

    def _build(self):
        outer = QtWidgets.QHBoxLayout(self)
        left = QtWidgets.QVBoxLayout()
        self.list = QtWidgets.QListWidget()
        self.list.setMaximumWidth(230)
        self.list.currentRowChanged.connect(self._picked)
        left.addWidget(self.list)
        for text, slot, tip in (
                ("New (copy)", self.new_copy, "A new design starting from the selected one"),
                ("Delete", self.delete, "Refused while a ping design names it")):
            b = QtWidgets.QPushButton(text)
            b.setToolTip(tip)
            b.clicked.connect(lambda _=False, f=slot: f())
            left.addWidget(b)
        outer.addLayout(left)

        right = QtWidgets.QVBoxLayout()
        form = QtWidgets.QFormLayout()
        self.name = QtWidgets.QLineEdit()
        self.name.editingFinished.connect(self._name_edited)
        self.kind = QtWidgets.QComboBox()
        for kind in dd.KINDS:
            self.kind.addItem(dd.KIND_TEXT[kind], kind)
        self.kind.currentIndexChanged.connect(self._kind_picked)
        self.description = QtWidgets.QLineEdit()
        self.description.editingFinished.connect(self._description_edited)
        form.addRow("Name", self.name)
        form.addRow("Kind", self.kind)
        form.addRow("Notes", self.description)
        right.addLayout(form)
        t = self.table = QtWidgets.QTableWidget(0, len(COLUMNS))
        t.setHorizontalHeaderLabels(COLUMNS)
        t.setColumnHidden(KEY, True)
        t.verticalHeader().setVisible(False)
        t.setWordWrap(True)
        t.itemChanged.connect(self._edited)
        right.addWidget(t)
        self.message = QtWidgets.QLabel()
        self.message.setWordWrap(True)
        right.addWidget(self.message)
        outer.addLayout(right, 1)

    # ---- the list ------------------------------------------------------

    def fill_list(self):
        self._filling = True
        self.list.clear()
        for did in self.ws.ids("detection_designs"):
            item = QtWidgets.QListWidgetItem(self.ws.name_of("detection_designs", did))
            item.setData(Qt.ItemDataRole.UserRole, did)
            self.list.addItem(item)
            if did == self.design_id:
                self.list.setCurrentItem(item)
        if self.list.currentRow() < 0 and self.list.count():
            self.list.setCurrentRow(0)
        self._filling = False
        self.design_id = (self.list.currentItem().data(Qt.ItemDataRole.UserRole)
                          if self.list.currentItem() else None)
        self.fill_table()

    def _picked(self, _):
        if self._filling:
            return
        item = self.list.currentItem()
        self.design_id = item.data(Qt.ItemDataRole.UserRole) if item else None
        self.fill_table()

    def _changed(self, kind, object_id):
        if kind == "detection_designs":
            self.fill_list()

    def new_copy(self):
        data = (self.ws.get("detection_designs", self.design_id)
                if self.design_id else dd.new_default())
        name = f"{data.get('name', 'design')} copy"
        self.design_id = self.ws.create("detection_designs", name, data)

    def delete(self):
        if not self.design_id:
            return
        try:
            self.ws.delete("detection_designs", self.design_id)
            self.message.setText("")
        except InUseError as error:
            self.message.setText(f"Not deleted: {error}")

    # ---- the table -----------------------------------------------------

    def fill_table(self):
        data = self.ws.get("detection_designs", self.design_id) if self.design_id else None
        self._filling = True
        t = self.table
        t.setRowCount(0)
        for w in (self.name, self.kind, self.description, t):
            w.setEnabled(data is not None)
        if data is None:
            self.name.clear()
            self.description.clear()
            self._filling = False
            return
        if not self.name.hasFocus():
            self.name.setText(data["name"])
        if not self.description.hasFocus():
            self.description.setText(data.get("description", ""))
        self.kind.setCurrentIndex(max(self.kind.findData(data.get("kind", "arrival")), 0))
        design = dd.from_dict(data)
        for s in dd.SETTINGS:
            row = t.rowCount()
            t.insertRow(row)
            value = getattr(design, s.key)
            cells = {KEY: s.key, LABEL: s.label,
                     VALUE: value if s.key in dd.CHOICES else f"{value:g}",
                     UNIT: (" / ".join(dd.CHOICES[s.key]) if s.key in dd.CHOICES
                            else s.unit),
                     DEFAULT_COLUMN: s.default if s.key in dd.CHOICES else f"{s.default:g}",
                     TEXT: s.text}
            for column, text in cells.items():
                item = QtWidgets.QTableWidgetItem(str(text))
                if column != VALUE:
                    read_only(item)
                if column == VALUE and value != s.default:
                    font = item.font()
                    font.setBold(True)
                    item.setFont(font)
                t.setItem(row, column, item)
        t.resizeColumnsToContents()
        t.setColumnWidth(TEXT, 480)
        t.resizeRowsToContents()
        self._filling = False

    def _edited(self, item):
        if self._filling or item.column() != VALUE or not self.design_id:
            return
        key = self.table.item(item.row(), KEY).text()
        setting = dd.SETTING[key]
        text = item.text().strip()
        try:
            if key in dd.CHOICES:
                value = text
            else:
                try:
                    value = float(text)
                except ValueError:
                    raise WorkspaceError(f"{setting.label} must be a number, "
                                         f"not '{text}'") from None
            self.ws.update("detection_designs", self.design_id,
                           text=f"set {setting.label} of "
                                f"{self.ws.name_of('detection_designs', self.design_id)}",
                           **{key: value})
            self.message.setText("")
        except (WorkspaceError, ValueError) as error:
            self.message.setText(f"Not changed: {error}")
            self.fill_table()

    def _name_edited(self):
        text = self.name.text().strip()
        if self.design_id and text and text != self.ws.name_of("detection_designs", self.design_id):
            self.ws.update("detection_designs", self.design_id, name=text)

    def _description_edited(self):
        if self.design_id:
            self.ws.update("detection_designs", self.design_id,
                           description=self.description.text())

    def _kind_picked(self, _):
        if self._filling or not self.design_id:
            return
        self.ws.update("detection_designs", self.design_id, kind=self.kind.currentData())
