#!/usr/bin/env python3
"""Step 0 spike: which Qt binding for acoustics_lab?

Choose the binding with PYQTGRAPH_QT_LIB=PyQt5 or PyQt6.  Shows a live 2D
plot (~30 Hz), a 3D beam-pattern surface and an undoable action.
"""
import argparse
import os
import sys
import time

# PyOpenGL picks EGL when WAYLAND_DISPLAY is set, but Qt on xcb (also XWayland)
# uses GLX; the mismatch gives "Attempt to retrieve context when no valid
# context" while drawing.  Make PyOpenGL follow Qt's platform plugin.
# Must happen before OpenGL is imported.
if "PYOPENGL_PLATFORM" not in os.environ:
    _qpa = os.environ.get("QT_QPA_PLATFORM", "")
    if _qpa.startswith("xcb") or (not _qpa and not os.environ.get("WAYLAND_DISPLAY")):
        os.environ["PYOPENGL_PLATFORM"] = "glx"
    elif _qpa.startswith("wayland") or os.environ.get("WAYLAND_DISPLAY"):
        os.environ["PYOPENGL_PLATFORM"] = "egl"

import numpy as np
import pyqtgraph as pg
import pyqtgraph.opengl as gl
from pyqtgraph.Qt import QtCore, QtGui, QtWidgets, QT_LIB, VERSION_INFO

# Only the small "shim" the real qtcompat.py would need.  pyqtgraph.Qt already
# puts QAction/QShortcut/QUndoStack/QUndoCommand in QtGui under both Qt 5 and 6.
QAction = QtGui.QAction
QUndoStack = QtGui.QUndoStack
QUndoCommand = QtGui.QUndoCommand
QShortcut = QtGui.QShortcut
Qt = QtCore.Qt


def beam_pattern(n_el=8, spacing_wl=0.5, steer_deg=0.0, n=161):
    """Height field: pattern (dB, floor -40) of an n_el x n_el square array
    over direction-cosine space (u, v), steered in u.  z-values are 0..1."""
    u = np.linspace(-1, 1, n)
    v = np.linspace(-1, 1, n)
    U, V = np.meshgrid(u, v, indexing="ij")
    u0 = np.sin(np.radians(steer_deg))

    def af(x):
        psi = np.pi * 2 * spacing_wl * x
        with np.errstate(divide="ignore", invalid="ignore"):
            r = np.sin(n_el * psi / 2) / (n_el * np.sin(psi / 2))
        return np.where(np.isfinite(r), r, 1.0)

    p = af(U - u0) * af(V)
    db = np.clip(20 * np.log10(np.abs(p) + 1e-9), -40, 0)
    db[U**2 + V**2 > 1] = -40                   # outside the visible region
    return u, v, (db + 40) / 40


class SteerCommand(QUndoCommand):
    def __init__(self, win, old, new):
        super().__init__(f"steer {old:g} -> {new:g} deg")
        self.win, self.old, self.new = win, old, new

    def redo(self):
        self.win.set_steer(self.new)

    def undo(self):
        self.win.set_steer(self.old)


class Win(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"acoustics_lab spike - {VERSION_INFO}")
        self.resize(1100, 600)
        self.steer = 0.0
        self.undo = QUndoStack(self)

        split = QtWidgets.QSplitter(Qt.Orientation.Horizontal)
        self.setCentralWidget(split)

        self.plot = pg.PlotWidget(title="live trace (30 Hz)")
        self.plot.setYRange(-1.5, 1.5)
        self.curve = self.plot.plot(pen=pg.mkPen("c", width=1))
        split.addWidget(self.plot)

        self.view = gl.GLViewWidget()
        self.view.setCameraPosition(distance=3.2, elevation=25, azimuth=40)
        split.addWidget(self.view)
        self.surf = None
        self.set_steer(0.0)

        # action + undo/redo + shortcut
        tb = self.addToolBar("edit")
        self.steer_act = QAction("Steer +15 deg", self)
        self.steer_act.setShortcut(QtGui.QKeySequence("Ctrl+T"))
        self.steer_act.triggered.connect(self.do_steer)
        tb.addAction(self.steer_act)
        self.undo_act = self.undo.createUndoAction(self, "Undo")
        self.undo_act.setShortcut(QtGui.QKeySequence.StandardKey.Undo)
        self.redo_act = self.undo.createRedoAction(self, "Redo")
        tb.addAction(self.undo_act)
        tb.addAction(self.redo_act)
        self.sc = QShortcut(QtGui.QKeySequence("Ctrl+Q"), self, activated=self.close)

        self.t0 = time.perf_counter()
        self.frames = 0
        self.times = []
        self.timer = QtCore.QTimer(self)
        self.timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.timer.timeout.connect(self.tick)
        self.timer.start(33)

    def do_steer(self):
        self.undo.push(SteerCommand(self, self.steer, self.steer + 15.0))

    def set_steer(self, deg):
        self.steer = deg
        u, v, z = beam_pattern(steer_deg=deg)
        colors = pg.colormap.get("viridis").map(z, mode="float").reshape(-1, 4)
        if self.surf is None:
            self.surf = gl.GLSurfacePlotItem(x=u, y=v, z=z, colors=colors,
                                             shader="shaded", smooth=False)
            self.surf.scale(1, 1, 0.8)
            self.view.addItem(self.surf)
            g = gl.GLGridItem()
            g.setSize(2, 2)
            g.setSpacing(0.25, 0.25)
            self.view.addItem(g)
        else:
            self.surf.setData(z=z, colors=colors)

    def tick(self):
        now = time.perf_counter()
        self.times.append(now)
        t = now - self.t0
        n = 4096
        ts = np.linspace(t - 0.5, t, n)
        f = 200 + 600 * ((ts * 2) % 1)          # repeating up-chirp
        sig = np.sin(2 * np.pi * f * ts) + 0.1 * np.random.randn(n)
        self.curve.setData(ts, sig)

    def fps(self):
        ts = np.array(self.times)
        if len(ts) < 3:
            return 0.0
        return (len(ts) - 1) / (ts[-1] - ts[0])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seconds", type=float, default=0, help="exit after N s (0 = run until closed)")
    ap.add_argument("--screenshot", help="save a PNG of the window before exiting")
    a = ap.parse_args()

    app = pg.mkQApp("spike")
    print("binding:", VERSION_INFO, "| pyqtgraph", pg.__version__, "| platform:", app.platformName())
    w = Win()
    w.show()

    def finish():
        # exercise undo/redo through the action to prove the stack works
        w.steer_act.trigger()
        w.undo.undo()
        assert w.steer == 0.0, w.steer
        w.undo.redo()
        assert w.steer == 15.0, w.steer
        w.undo.undo()
        ok_undo = w.steer == 0.0
        print(f"live plot: {w.fps():.1f} Hz over {len(w.times)} frames")
        print("undo/redo via QUndoStack action:", "ok" if ok_undo else "FAIL")
        try:
            w.view.makeCurrent()
            from OpenGL import GL
            print("GL_RENDERER:", GL.glGetString(GL.GL_RENDERER).decode())
            print("GL_VERSION:", GL.glGetString(GL.GL_VERSION).decode())
        except Exception as e:                  # noqa
            print("GL query failed:", e)
        if a.screenshot:
            app.processEvents()
            ok = w.grab().save(a.screenshot)
            print("screenshot:", a.screenshot, "saved" if ok else "FAILED")
        app.quit()

    if a.seconds > 0:
        QtCore.QTimer.singleShot(int(a.seconds * 1000), finish)
    rc = app.exec()
    sys.exit(rc)


if __name__ == "__main__":
    main()
