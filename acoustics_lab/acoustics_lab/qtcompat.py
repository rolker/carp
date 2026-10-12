"""The one place Qt is imported from.

Everything else uses `from .qtcompat import QtCore, QtGui, QtWidgets, ...`.
pyqtgraph.Qt already hides most of the differences between Qt 5 and Qt 6
(actions, shortcuts and the undo classes are in QtGui under both). What is
left is done by convention: scoped enum names (Qt.AlignmentFlag.AlignLeft),
key sequences as strings ("Ctrl+Z"), and the Qt 6 names for removed calls.

Importing this module also settles two environment questions that must be
answered before Qt or OpenGL are used.
"""
import os

# PyQt6 from apt, as chosen after the step 0 spike. Set before pyqtgraph is
# imported, which picks a binding when it first loads.
os.environ.setdefault("PYQTGRAPH_QT_LIB", "PyQt6")

# PyOpenGL picks EGL when WAYLAND_DISPLAY is set, but Qt on xcb (also
# XWayland) uses GLX; the mismatch gives "Attempt to retrieve context when no
# valid context" in every 3D item. Make PyOpenGL follow Qt's platform plugin.
# Must happen before OpenGL is imported.
if "PYOPENGL_PLATFORM" not in os.environ:
    _qpa = os.environ.get("QT_QPA_PLATFORM", "")
    if _qpa.startswith("xcb") or (not _qpa and not os.environ.get("WAYLAND_DISPLAY")):
        os.environ["PYOPENGL_PLATFORM"] = "glx"
    elif _qpa.startswith("wayland") or os.environ.get("WAYLAND_DISPLAY"):
        os.environ["PYOPENGL_PLATFORM"] = "egl"

import pyqtgraph as pg                                       # noqa: E402
from pyqtgraph.Qt import QtCore, QtGui, QtWidgets, QT_LIB    # noqa: E402

Qt = QtCore.Qt
Signal = QtCore.pyqtSignal if QT_LIB.startswith("PyQt") else QtCore.Signal
QAction = QtGui.QAction
QUndoStack = QtGui.QUndoStack
QUndoCommand = QtGui.QUndoCommand
QShortcut = QtGui.QShortcut

__all__ = ["pg", "QtCore", "QtGui", "QtWidgets", "QT_LIB", "Qt", "Signal",
           "QAction", "QUndoStack", "QUndoCommand", "QShortcut"]
