"""Small pieces shared by pages: colours, a combo box for table cells, and a
worker thread that fires a ping off the GUI thread."""
from ..backends.base import Cancelled
from ..experiments import ranging
from ..qtcompat import Qt, QtCore, QtGui, QtWidgets, Signal

# Tableau 10: readable on dark and light backgrounds, same order everywhere.
PALETTE = ["#4e79a7", "#f28e2b", "#e15759", "#76b7b2", "#59a14f",
           "#edc948", "#b07aa1", "#ff9da7", "#9c755f", "#bab0ac"]


def colour(index):
    return QtGui.QColor(PALETTE[index % len(PALETTE)])


class ComboDelegate(QtWidgets.QStyledItemDelegate):
    """A drop-down for a table cell. `choices()` returns (label, value)
    pairs; the cell shows the label and keeps the value in UserRole."""

    def __init__(self, choices, parent=None):
        super().__init__(parent)
        self.choices = choices

    def createEditor(self, parent, option, index):
        box = QtWidgets.QComboBox(parent)
        for label, value in self.choices():
            box.addItem(label, value)
        return box

    def setEditorData(self, editor, index):
        current = index.data(Qt.ItemDataRole.UserRole)
        at = editor.findData(current)
        if at >= 0:
            editor.setCurrentIndex(at)
        editor.showPopup()

    def setModelData(self, editor, model, index):
        model.setData(index, editor.currentText(), Qt.ItemDataRole.DisplayRole)
        model.setData(index, editor.currentData(), Qt.ItemDataRole.UserRole)


def read_only(item):
    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
    return item


class PingWorker(QtCore.QThread):
    """Fires one ping and analyses it, off the GUI thread. `analyse(capture)`
    returns the page's results (default: ranging's, one per receiver)."""

    progressed = Signal(float, str)
    succeeded = Signal(object, object)      # capture, whatever `analyse` made
    failed = Signal(str)

    def __init__(self, stream, analyse=None, parent=None):
        super().__init__(parent)
        self.stream = stream
        self.analyse = analyse or (lambda capture: {
            rid: ranging.analyse_capture(capture, rid) for rid in capture.recordings})
        self._cancel = False

    def cancel(self):
        self._cancel = True

    def run(self):
        try:
            capture = self.stream.fire(
                progress=lambda fraction, text="": self.progressed.emit(fraction, text),
                cancel=lambda: self._cancel)
            self.succeeded.emit(capture, self.analyse(capture))
        except Cancelled:
            self.failed.emit("")
        except (ValueError, OSError) as error:
            self.failed.emit(str(error))
        except Exception as error:                  # noqa: show it, do not die
            self.failed.emit(f"{type(error).__name__}: {error}")
