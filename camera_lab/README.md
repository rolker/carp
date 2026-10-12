# camera_lab

A desktop workbench for choosing cameras for an underwater vehicle: field of
view and coverage, resolution on target, frame rate and motion blur, and
expected stereo performance, in air or through a flat or dome port into fresh
or salt water. Built first for CARP's stereo pair; the design is in
[docs/design.md](docs/design.md).

**What exists now:** pages *Field of view & coverage* (top, side and 3D views,
footprints, visibility and target markers), *Stereo performance* (depth error
against range, near and far limits, **the 74 to 95 mm baseline decision**, lens
trade-off, sync error) and *Resolution & motion*, plus an *Objects* editor. A new
workspace starts with CARP's rig (95 mm printed bracket, 74 mm minimum) and a few
alternatives to compare. The other pages are placeholders.

## Install

Ubuntu 24.04, apt packages only, the system Python (3.12):

```bash
sudo apt install python3-numpy python3-scipy python3-pyqtgraph python3-pyqt6 \
    pyqt6-dev-tools python3-opengl python3-pytest
```

`pyqt6-dev-tools` is required even though nothing here uses Designer: pyqtgraph
imports `PyQt6.uic`, which only that package provides. `python3-opengl` is for the
3D view; the app sets `PYOPENGL_PLATFORM` to match Qt's platform (EGL on Wayland,
GLX on X11), so it works from an XWayland session too. Without OpenGL the 3D view
is replaced by a note and the rest works.

## Run

```bash
python3 camera_lab/run.py          # from the repository root, or from anywhere
python3 -m camera_lab              # from inside this folder
```

Options: `--workspace FOLDER` opens (or creates, with CARP's cameras) a workspace;
without it the last one used is opened (kept in Qt settings), or
`~/camera_lab_workspace` is created on the first start. `--page "Stereo performance"`
opens on a page; `--screenshot FILE.png` saves the window and exits.
Force a Qt platform if needed: `QT_QPA_PLATFORM=xcb` or `wayland`.

## Using it

- **Left:** the pages, and the rigs. Tick rigs to show them on the plots; click one
  to make it the *primary* (bold): the one whose assumptions appear in the side
  panel and that single-rig plots use.
- **Toolbar:** the scene, and a medium override to compare air, fresh and salt
  water without editing the scene.
- **Side panels** hold the settings the page uses (disparity accuracy, speed,
  baseline...). Every edit is saved to the workspace and is one undo step
  (Edit > Undo, Ctrl+Z). Hover a field for what it means. The *Objects* page edits
  everything, and *Copy* makes a variation to compare.
- Defaults for assumptions (0.25 px disparity accuracy, 5 % depth tolerance, 256 px
  search range, 0.5 m/s, ...) are starting points, not measurements.

## Tests

```bash
python3 -m pytest camera_lab/tests
```

Model tests are against hand calculations (pinhole and fisheye field of view,
Snell's law through a flat port, a dome with the pupil off centre, the stereo
depth-error formula at a known point, overlap, sync, blur). The window tests run
on Qt's offscreen platform; the 3D view is skipped there, because that platform
has no OpenGL.

To look at the real window headlessly (never on the real display):

```bash
QT_QPA_PLATFORM=xcb PYOPENGL_PLATFORM=glx xvfb-run -a -s "-screen 0 1500x950x24 +extension GLX" \
    python3 camera_lab/run.py --workspace /tmp/ws --screenshot /tmp/shot.png
```
