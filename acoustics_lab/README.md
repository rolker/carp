# acoustics_lab

A desktop workbench for underwater and in-air acoustics: work out how
something should behave from a model, then try it on simulated or real
hardware. The design is in [docs/design.md](docs/design.md).

**Steps 1 and 2, which is what exists now.** Two working pages. *Ranging &
positioning*: edit signals and a ping design, ping a simulated scene, real
hardware or replay saved recordings, and see when each signal came back.
*Room sonar*: ping a room from a speaker near a microphone (a laptop's own,
or any output and input) and watch the returns against range, with the steady
background taken away so that what moves stands out. Every choice about how a
return is found is a *detection design* in the workspace, recorded with each
result. The other pages are placeholders. What was simplified or left out is
in [docs/step1-notes.md](docs/step1-notes.md) and
[docs/step2-notes.md](docs/step2-notes.md); the hardware layer is in
[docs/hardware-layer.md](docs/hardware-layer.md).

## Install

Ubuntu 24.04, apt packages only, the system Python (3.12):

```bash
sudo apt install python3-numpy python3-scipy python3-pyqtgraph python3-pyqt6 \
    pyqt6-dev-tools python3-opengl python3-pytest
```

`pyqt6-dev-tools` is required even though nothing here uses Designer:
pyqtgraph imports `PyQt6.uic`, which only that package provides.
`python3-opengl` is for the 3D pages later; the app sets `PYOPENGL_PLATFORM`
to match Qt's platform (EGL on Wayland, GLX on X11) so it works from an
XWayland session too.

## Run

```bash
cd acoustics_lab && python3 -m acoustics_lab      # from this folder, or
python3 acoustics_lab/run.py                      # from anywhere
```

Options: `--workspace FOLDER` opens (or creates) a workspace, `--import-designs
FOLDER` imports `carp/acoustic` ping designs first, `--replay PATH` opens a
WAV file or a folder of recordings in replay. Without `--workspace` it opens
the last workspace used (kept in Qt settings, `~/.config/acoustics_lab/`), or
creates `~/acoustics_lab_workspace` on the first start.

Force a Qt platform if needed: `QT_QPA_PLATFORM=xcb` or `wayland`.

## Using it

**Toolbar.** Backend (*Simulation*, *Hardware*, *Replay*), the rig, the active
scene with its air temperature and the resulting sound speed, an **As built**
button, then **Ping** (Space), **Continuous** and the pause between pings.
Choosing *Hardware* makes the rig's as-built scene the active one; in
simulation the toolbar says in orange when the scene is not the bench as built
("simulating Laptop in a room, not built") and *As built* gets you back.
Edit > Undo and Redo (Ctrl+Z, Ctrl+Shift+Z) cover everything you edit; View >
History lists the steps, and View > Hardware messages shows what taking hold of
a sound card said (a warning opens it).

**Rigs** (*File > Rigs...* or the toolbar): which device and channel each
transducer is on, how each device is taken hold of (*exclusive*: borrowed from
the desktop and opened directly, with mixer values applied and put back;
*shared*: through the sound server, whose volume is recorded and warned about),
loopbacks, and an **Identify** button that plays a short quiet tone on the
selected transducer. *New laptop rig* makes the rig for this computer's own
speaker and microphone, its as-built scene, a demo room with a person walking
about, and a ping design for the room sonar.

**Room sonar.** Pick an output and an input, a ping design (its first signal
is sent) and a detection design, the maximum range and the ping rate. The page
shows the current return against range, an echogram of recent pings and the
same with the average of the last N pings taken away. It needs one output near
one input; if the active scene has none it says so and offers the scenes that
fit and the laptop template.

**Detection designs** (*File > Detection designs...*): a table of every
setting (matched filter or envelope, thresholds, the first-arrival fraction,
windows, grouping, settle time, input-check limits) with what each does and
its default; one edit is one undo step. A ping design names its default; the
Ranging and Room sonar pages can choose another and *Analyse again* reads the
latest ping, or a replayed recording, with it.

**Signals** (left, top) is an editable table: change a cell, press Enter,
done. One committed cell is one undo step. *Add reversed copy* makes a
signal derived from the selected one (played backwards); it follows its
source when that is edited, and a loop of derived signals is refused. The
read-only columns say what each signal is worth: processing gain against
white noise and the spacing below which two arrivals merge. Deleting a
signal that a design or another signal uses is refused, with the list of
what uses it.

**Ping design** (left, below): which signal goes out of which transducer, at
what time after the start of the ping; which transducers listen; how long to
keep recording. Problems (a transducer that cannot send, two events that
cannot be told apart) are shown under the table as soon as they appear.

**Results.** The table has a row per event: when it came back, the path
length, level and signal-to-noise ratio. Without a loopback times are against
the loudest event's first arrival, so you get path *differences*. In the
scene *Dongle bench loopback* an electrical copy of each output is mixed into
the input; it marks the instant of sending, the next arrival is the time of
flight, and the path is a distance. For simulations the table also shows the
true path and the error in mm, and the trace shows the true arrivals as
dotted lines. The **echogram** is one column per ping, time running down.
*Save recordings* writes each ping to `runs/<date>/` in the workspace.

**Replay.** *File > Open recordings folder for replay...* (or `--replay`)
reads WAV files with their `.json` beside them, the format `carp/acoustic`
writes (`acoustic/runs/`); Space shows the next one. The design stored with
a recording is what is analysed.

## Workspace

A workspace is a folder of JSON files you can read, diff and keep in git:

```
my_workspace/
  workspace.json
  signals/<id>.json  ping_designs/<id>.json  detection_designs/<id>.json
  layouts/<id>.json  scenes/<id>.json        rigs/<id>.json
  runs/               saved recordings (git-ignored)
```

A workspace from step 1 kept its ping designs in `designs/`; opening it moves
them to `ping_designs/` and the status bar says so.

IDs are short and readable (`chirp_up`), made from the first name and never
changed; the display name is inside the file. Edits are written at once and
atomically. If files change underneath the program (a `git checkout`, another
editor) they are reloaded, the undo history is cleared and the status bar
says so. Layouts and scenes have no editor yet: edit their JSON by hand (move
a transducer, add a wall) and watch the window follow.

*File > Import carp/acoustic designs...* turns `acoustic/designs/*.json` into
signals and ping designs; the old channels `left` and `right` become
transducers of the "stereo dongle" layout, with simulated scenes of it.

## Tests

```bash
python3 -m pytest acoustics_lab/tests            # from the repository root
```

The model tests are ported from `carp/acoustic/test_ranging_dsp.py`; the
simulation tests check arrival times against the truth to a small fraction of
a sample, near the end of the buffer and with clock drift; the window is
driven headlessly (Qt's `offscreen` platform).

## Layout

```
acoustics_lab/        the package (python3 -m acoustics_lab)
  models/             pure functions: media, signals, channel, detection,
                      detection_design (every detection setting)
  objects/            what the workspace objects look like; starter content;
                      rigs and the laptop template; detection design lookup
  backends/           base interface, simulation, replay, hardware
  hardware/           sound cards, mixer, desktop volumes, reservation, duplex
                      streams, the hold sequence, shared access, hardware checks
  experiments/        ranging: a ping from a design, arrivals from a capture;
                      room: a return against range
  pages/  ui/         the window, the rig editor, the detection design editor
  workspace.py  importers.py  capture_io.py  qtcompat.py
tests/  docs/  spike/
```
