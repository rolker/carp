"""Pages that are designed (docs/design.md) but not built yet."""
from ..qtcompat import QtWidgets
from .base import Page


class PlaceholderPage(Page):
    def __init__(self, ws, session, title, text, parent=None):
        super().__init__(ws, session, parent)
        self.title = title
        lay = QtWidgets.QVBoxLayout(self)
        label = QtWidgets.QLabel(f"<h3>{title}</h3><p>Not built yet.</p><p>{text}</p>")
        label.setWordWrap(True)
        lay.addWidget(label)
        lay.addStretch(1)

    def _redraw(self):
        pass
