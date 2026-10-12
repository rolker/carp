# Step 0 spike: Qt binding for acoustics_lab

`spike.py` opens one window with a live 2D trace (30 Hz timer, scrolling
chirp plus noise), a 3D `GLSurfacePlotItem` (beam pattern of an 8 x 8 square
array, steerable), and a `QUndoStack`-backed "Steer +15 deg" action with
Undo/Redo. With `--seconds N` it exercises undo/redo, prints the achieved
frame rate and GL renderer, optionally saves a screenshot, and exits.

Choose the binding with `PYQTGRAPH_QT_LIB` (`PyQt5` or `PyQt6`) and the Qt
platform plugin with `QT_QPA_PLATFORM`.

## Install (Ubuntu 24.04, apt only)

    sudo apt install python3-pyqtgraph python3-pyqt6 pyqt6-dev-tools \
        python3-opengl python3-pyqt5 python3-pyqt5.qtopengl

`pyqt6-dev-tools` is required: pyqtgraph does `from PyQt6 import uic` and
that module ships only in that package. (Drop the `python3-pyqt5*` entries
once PyQt6 is chosen.)

## Real display

Wayland (native):

    PYQTGRAPH_QT_LIB=PyQt6 QT_QPA_PLATFORM=wayland python3 spike.py
    PYQTGRAPH_QT_LIB=PyQt5 QT_QPA_PLATFORM=wayland python3 spike.py

X11 / XWayland:

    PYQTGRAPH_QT_LIB=PyQt6 QT_QPA_PLATFORM=xcb python3 spike.py
    PYQTGRAPH_QT_LIB=PyQt5 QT_QPA_PLATFORM=xcb python3 spike.py

Add `--seconds 8 --screenshot /tmp/spike.png` for a timed, reporting run.
On the NVIDIA/Intel laptop, to try the discrete GPU:
`__NV_PRIME_RENDER_OFFLOAD=1 __GLX_VENDOR_LIBRARY_NAME=nvidia` (xcb only).

`spike.py` sets `PYOPENGL_PLATFORM` itself (egl for wayland, glx for xcb)
unless you set it. Without that, PyOpenGL picks EGL whenever
`WAYLAND_DISPLAY` is set, even if Qt runs on xcb, and the 3D view fails
with "Attempt to retrieve context when no valid context".

## Headless (xvfb, software GL)

    QT_QPA_PLATFORM=xcb PYQTGRAPH_QT_LIB=PyQt6 \
      xvfb-run -a -s "-screen 0 1280x900x24 +extension GLX" \
      python3 spike.py --seconds 6 --screenshot /tmp/spike6.png

Unset `WAYLAND_DISPLAY` for xvfb runs if you force `QT_QPA_PLATFORM=wayland`,
otherwise Qt connects to your real compositor.

## WSL (WSL2 with WSLg)

    sudo apt install mesa-utils   # for glxinfo
    PYQTGRAPH_QT_LIB=PyQt6 QT_QPA_PLATFORM=wayland python3 spike.py
    PYQTGRAPH_QT_LIB=PyQt6 QT_QPA_PLATFORM=xcb python3 spike.py

Try both; WSLg offers Wayland and X11. GL goes through Mesa `d3d12` or
`llvmpipe`; check the `GL_RENDERER` line printed at the end. If the 3D view
is blank, try `LIBGL_ALWAYS_SOFTWARE=1`.
