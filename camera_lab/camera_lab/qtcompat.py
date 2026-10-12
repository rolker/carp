"""The one place Qt is imported from.

Everything else uses `from .qtcompat import QtCore, QtGui, QtWidgets, ...`.
Importing this module also settles two environment questions that must be
answered before Qt or OpenGL are used (the same two as acoustics_lab):

* the Qt binding is PyQt6 (apt `python3-pyqt6`);
* PyOpenGL picks EGL when WAYLAND_DISPLAY is set, but Qt on xcb (also
  XWayland) uses GLX, and the mismatch breaks every 3D item with "Attempt to
  retrieve context when no valid context". PyOpenGL is made to follow Qt's
  platform plugin: egl for Wayland, glx for xcb. Must happen before OpenGL
  is imported.
"""
import os

os.environ.setdefault("PYQTGRAPH_QT_LIB", "PyQt6")

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
