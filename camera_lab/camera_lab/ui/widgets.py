"""Small pieces shared by pages: colours, an editor form for any workspace
object, plot helpers, and the notes panel."""
import numpy as np

from ..objects import schema
from ..qtcompat import Qt, QtCore, QtGui, QtWidgets, pg

# Tableau 10: readable on light and dark backgrounds, same order everywhere.
PALETTE = ["#4e79a7", "#f28e2b", "#e15759", "#76b7b2", "#59a14f",
           "#edc948", "#b07aa1", "#ff9da7", "#9c755f", "#bab0ac"]


def colour(index):
    return QtGui.QColor(PALETTE[index % len(PALETTE)])


def pen(index, width=2, style=None, alpha=255):
    c = colour(index)
    c.setAlpha(alpha)
    p = pg.mkPen(c, width=width)
    if style is not None:
        p.setStyle(style)
    return p


def brush(index, alpha=40):
    c = colour(index)
    c.setAlpha(alpha)
    return pg.mkBrush(c)


class FieldsPanel(QtWidgets.QWidget):
    """A form for some fields of one workspace object. Each committed edit is
    one undo step; undo, redo and outside changes update the form. Pass
    `keys` to show only some fields. `set_object(kind, id)` re-targets it."""

    def __init__(self, ws, keys=None, parent=None):
        super().__init__(parent)
        self.ws, self.keys = ws, keys
        self.kind = self.object_id = None
        self.form = QtWidgets.QFormLayout(self)
        self.form.setContentsMargins(0, 0, 0, 0)
        self.form.setVerticalSpacing(2)
        self.widgets = {}
        self._loading = False
        ws.changed.connect(self._ws_changed)

    def set_object(self, kind, object_id):
        if (kind, object_id) == (self.kind, self.object_id) and self.widgets:
            self.reload()
            return
        self.kind, self.object_id = kind, object_id
        while self.form.rowCount():
            self.form.removeRow(0)
        self.widgets = {}
        if kind is None or object_id is None or not self.ws.exists(kind, object_id):
            return
        specs = [f for f in schema.FIELDS[kind] if self.keys is None or f["key"] in self.keys]
        name = QtWidgets.QLineEdit()
        name.editingFinished.connect(lambda: self._commit("name", name.text()))
        self.widgets["name"] = name
        if self.keys is None:
            self.form.addRow("Name", name)
        for spec in specs:
            w = self._make(spec)
            self.widgets[spec["key"]] = w
            label = spec["label"] + (f" ({spec['unit']})" if spec["unit"] else "")
            if spec["help"]:
                w.setToolTip(spec["help"])
            self.form.addRow(label, w)
        self.reload()

    def _make(self, spec):
        key, kind = spec["key"], spec["kind"]
        if kind in ("float", "int"):
            w = QtWidgets.QDoubleSpinBox() if kind == "float" else QtWidgets.QSpinBox()
            if kind == "float":
                w.setDecimals(spec["decimals"])
            w.setRange(spec["lo"], spec["hi"])
            w.setKeyboardTracking(False)
            w.setGroupSeparatorShown(False)
            w.valueChanged.connect(lambda v, k=key: self._commit(k, v))
        elif kind == "choice":
            w = QtWidgets.QComboBox()
            w.addItems(spec["choices"])
            w.activated.connect(lambda _, k=key, w=w: self._commit(k, w.currentText()))
        elif kind == "ref":
            w = QtWidgets.QComboBox()
            w.activated.connect(lambda _, k=key, w=w: self._commit(k, w.currentData()))
        else:
            w = QtWidgets.QLineEdit()
            w.editingFinished.connect(lambda k=key, w=w: self._commit(k, w.text()))
        return w

    def reload(self):
        if self.kind is None or not self.ws.exists(self.kind, self.object_id):
            return
        data = self.ws.get(self.kind, self.object_id)
        self._loading = True
        try:
            for key, w in self.widgets.items():
                v = data.get(key)
                if isinstance(w, (QtWidgets.QDoubleSpinBox, QtWidgets.QSpinBox)):
                    if w.value() != v:
                        w.setValue(v)
                elif isinstance(w, QtWidgets.QLineEdit):
                    if w.text() != v:
                        w.setText(v)
                elif isinstance(w, QtWidgets.QComboBox):
                    spec = schema.field(self.kind, key)
                    if spec["kind"] == "ref":
                        w.clear()
                        for i in self.ws.ids(spec["ref"]):
                            w.addItem(self.ws.name_of(spec["ref"], i), i)
                    w.setCurrentIndex(max(0, w.findData(v) if spec["kind"] == "ref" else w.findText(v)))
        finally:
            self._loading = False

    def _ws_changed(self, kind, object_id):
        if self.kind and (kind == self.kind and object_id == self.object_id
                          or kind in {f.get("ref") for f in schema.FIELDS[self.kind]}):
            self.reload()

    def _commit(self, key, value):
        if self._loading or self.kind is None:
            return
        try:
            self.ws.update(self.kind, self.object_id, **{key: value})
        except schema.WorkspaceError as error:
            QtWidgets.QMessageBox.warning(self, "Not accepted", str(error))
            self.reload()


class Notes(QtWidgets.QTextBrowser):
    """The notes panel: HTML filled in with live values."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setOpenExternalLinks(True)
        self.document().setDefaultStyleSheet(
            "h4 {margin-top:6px; margin-bottom:2px;} td {padding: 1px 6px;} "
            "th {padding: 1px 6px; text-align:right;} .warn {color:#b00020;} .dim {color:#666;}")


def plot(title=None, x=None, y=None, parent=None, log_x=False, log_y=False):
    """A pyqtgraph plot with labelled axes and a grid."""
    w = pg.PlotWidget(parent=parent, background="w")
    p = w.getPlotItem()
    if title:
        p.setTitle(title, color="k", size="10pt")
    if x:
        p.setLabel("bottom", x)
    if y:
        p.setLabel("left", y)
    p.showGrid(x=True, y=True, alpha=0.25)
    p.setLogMode(x=log_x, y=log_y)
    for axis in ("left", "bottom"):
        p.getAxis(axis).setPen("k")
        p.getAxis(axis).setTextPen("k")
    return w


def hline(plot_widget, y, colour_="#555", style=Qt.PenStyle.DashLine, label=None):
    line = pg.InfiniteLine(pos=y, angle=0, pen=pg.mkPen(colour_, width=1, style=style),
                           label=label, labelOpts=dict(color=colour_, position=0.97))
    plot_widget.addItem(line)
    return line


def vline(plot_widget, x, colour_="#555", style=Qt.PenStyle.DashLine, label=None):
    line = pg.InfiniteLine(pos=x, angle=90, pen=pg.mkPen(colour_, width=1, style=style),
                           label=label, labelOpts=dict(color=colour_, position=0.95))
    plot_widget.addItem(line)
    return line


def fmt(v, digits=3):
    """Short number for the notes."""
    if v is None or not np.isfinite(v):
        return "n/a"
    return f"{v:.{digits}g}" if abs(v) < 1e4 else f"{v:,.0f}"
