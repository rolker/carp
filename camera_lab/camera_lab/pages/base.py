"""Base class for pages: gets the workspace and the shared selection, and
redraws when either changes (redraws are batched into one per event-loop
turn)."""
from ..qtcompat import QtCore, QtWidgets
from ..ui.widgets import colour


class Page(QtWidgets.QWidget):
    title = "Page"
    blurb = ""

    def __init__(self, ws, session, parent=None):
        super().__init__(parent)
        self.ws, self.session = ws, session
        self._timer = QtCore.QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(0)
        self._timer.timeout.connect(self._redraw)
        ws.changed.connect(lambda *_: self.schedule())
        session.changed.connect(self.schedule)
        self.visible_now = False

    def schedule(self):
        """Ask for a redraw (done once, and only while the page is shown)."""
        self._timer.start()

    def showEvent(self, event):
        super().showEvent(event)
        self.visible_now = True
        self.schedule()

    def hideEvent(self, event):
        super().hideEvent(event)
        self.visible_now = False

    def _redraw(self):
        if self.visible_now and self.session.scene() and self.session.shown_rigs():
            self.redraw()
        elif self.visible_now:
            self.redraw_empty()

    def redraw(self):                     # overridden
        pass

    def redraw_empty(self):
        pass

    def rig_table(self, table, columns, rows):
        """Fill a QTableWidget: one column per rig, one row per (label,
        function of the resolved rig)."""
        table.clear()
        table.setColumnCount(len(columns))
        table.setRowCount(len(rows))
        table.setVerticalHeaderLabels([r[0] for r in rows])
        for c, res in enumerate(columns):
            head = QtWidgets.QTableWidgetItem(res.name)
            head.setToolTip(res.name)
            head.setForeground(colour(res.colour_index))
            table.setHorizontalHeaderItem(c, head)
            for r, (_, fn) in enumerate(rows):
                item = QtWidgets.QTableWidgetItem(fn(res))
                item.setFlags(item.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable)
                item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter)
                table.setItem(r, c, item)
        table.setTextElideMode(QtCore.Qt.TextElideMode.ElideRight)
        table.resizeColumnsToContents()
        for c in range(len(columns)):
            table.setColumnWidth(c, min(table.columnWidth(c), 190))
        table.resizeRowsToContents()
