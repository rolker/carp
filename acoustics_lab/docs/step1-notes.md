# Step 1 notes

What was built for step 1 of "Getting there from carp/acoustic" in
[design.md](design.md), what was simplified or left out, and where the code
differs from the design and why. `design.md` itself is unchanged.

## Built

- **Models** (`models/`): `media` (sound speed in air, wavelength), `signals`
  (chirp and tone, time reverse, invert, processing gain), `channel`
  (image sources, spreading, absorption, the frequency-domain path renderer),
  `detection` (matched filter, arrivals, finding the events of a ping,
  noise spectrum). Ported from `ranging_dsp.py` and `pinger.py`; their tests
  are in `tests/test_models.py`.
- **Workspace** (`workspace.py`, `objects/`): signals, ping designs, layouts
  and scenes as JSON files; readable fixed IDs; atomic writes; refusal to
  delete what is used; a cycle check for derived signals (time reverse and
  invert exist); one `QUndoStack`; macros for imports; file watching with
  reload.
- **Backends** (`backends/`): the interface, simulation, replay.
- **Imports** (`importers.py`, `capture_io.py`): old designs, and old runs in
  replay.
- **Ranging page** and the window around it.

## Simplified or left out

- **Signals:** only parametric chirps (tones are chirps with equal ends) and
  two derived operations. No file signals, no data symbols, no shift, join or
  fade operations. A derived signal cannot be detached yet.
- **Ported, not moved:** `chirp_data.py` (comms), the sweep functions of
  `pinger.py` and `simulate_noise` were not ported; they belong to steps 5
  and 6. `noise_spectrum` and `band_levels` were, with their test.
- **Scene:** point transducers only. No directivity and no resonance
  filters, but the renderer multiplies per-path spectra, so both slot in
  there. Flat planes are handled by image sources (one reflection each;
  no multiple reflections, no plane-to-plane paths). One uniform air medium;
  travel time is length over sound speed. Absorption is a stand-in: a
  frequency-squared law with a coefficient in the scene (0.0015 dB per metre
  per kHz squared, about 0.5 dB/m at 18 kHz), until the propagation page
  brings ISO 9613-1. Water is refused with a message.
- **Noise:** white or tilted (`slope_db_per_octave`) Gaussian, one level per
  scene. Not a recorded noise file, not per device.
- **Clocks:** offset, drift and start delay per device are implemented, as
  described in the design: a device's local time is
  `(true time - start_delay) * (1 + drift)`. Parametric signals are not
  generated at device-clock times. The stretch that drift puts on a signal
  within its own duration is therefore not modelled; `truth` states it per
  emission (`unmodelled_stretch_s`). Sender and receiver on one device share
  a clock, so it is zero there.
- **Layouts and scenes have no editors** (step 3). They are edited as JSON
  files; the watcher picks the change up (and clears the undo history, as
  the design says for outside changes). Positions of transducers are the
  thing to try.
- **Rigs** are not a separate object yet. The simulated rig (which
  transducers share a device, device rates and clocks, which input carries
  which loopback) lives in the scene as `devices` and `loopbacks`; it moves
  to `rigs/` when hardware needs real ones (step 2). No as-built scene, no
  As built button.
- **Ranging page:** no recording waveform/spectrum view, no sweep, noise or
  data tabs (steps 5 and 6), and only the first four events get an echogram.
  The echogram's time axis has no distance axis beside it. Panels are in
  splitters, not rearrangeable docks. The notes panel is one Markdown file
  with `$name` placeholders filled from the page's numbers.
- **Replay:** a recording is rebuilt from the signal's band, length and level
  (what the old sidecars hold), so a signal that was derived by time reversal
  comes back as the down-chirp of the same band: the same sound up to a
  constant phase, which the matched filter's envelope ignores. Recordings made
  by this tool carry the scene and layout in their sidecar, as the design
  asks, but not yet git's commit. A WAV with no sidecar is refused with a
  message.
- **Saved runs** go to `runs/<date and time>/p_0001.wav` (+ `.json`), one
  file per receiver, not under a date-only folder.
- **Hardware** is listed in the toolbar, disabled, as step 2.

## Deviations from the design

- **Backend sketch.** Added `Emission.rate` (the sender's device rate; the
  sketch had samples with no rate), `Emission.signal` (signal ID, so analysis
  can tell which events share a filter), `Ping.meta` (design and signal
  settings, copied into the capture), `Capture.ping` (what was asked for;
  replay needs it because the ping comes from the recording, not the page).
  `TransducerInfo` exists as a dataclass. `fire` and `open_stream` are as
  sketched; `open_stream` returns a `PingStream` with `fire` and `close`.
  `cancel` is a function returning True to stop; `Cancelled` is raised.
- **Chirps are float64** (the old code gave float32), so the simulation does
  not lose precision before rendering. WAVs are still 16-bit.
- **Analysis works from the ping, not from a design.** It reads the emissions
  of the capture's `Ping`, so replay, simulation and later hardware share one
  path, and an edit to a design after a ping does not change how that ping is
  read.
- **Time zero.** Old `pinger.py` took the loudest event's first arrival as
  time zero. That stays, but where a recording holds a loopback of an event's
  emitter, that copy is time zero for the event and the time of flight is the
  gap to the next arrival after it (arrivals above 5% of the strongest peak
  are kept; the first-arrival threshold stays at 30%).
- **No modal dialogs** for errors (a bad replay path, a refused edit): they go
  to the status bar, so nothing blocks the window or a test.
- **Start-up.** The package has the same name as its folder, so
  `python3 -m acoustics_lab` works from inside `acoustics_lab/` (or with it
  on `PYTHONPATH`); `acoustics_lab/run.py` works from anywhere.
- **Layer order.** `capture_io` and `importers` sit beside `workspace` rather
  than in `objects/`; `backends/replay` imports `capture_io`.

## Known problems

- Editing a layout in a text editor while a ping is in flight is fine (the
  backend holds a copy), but the undo history is cleared by the reload.
- The window was checked on Qt's offscreen platform and on a virtual X
  display (xvfb, xcb, software GL); not yet on a real Wayland session or
  WSL.
- A cell edit made while typing in the "Receivers" or "Listen after" fields
  commits on Enter or when the field loses focus, not per keystroke.
- A continuous run reuses its stream until anything it depends on changes
  (any workspace change counts), then reopens it; harmless for simulation,
  and the right behaviour once hardware streams stay open.
