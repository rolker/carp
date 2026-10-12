# Step 2 notes

What was built for step 2 of "Getting there from carp/acoustic" in
[design.md](design.md), what was simplified or left out, and where the code
differs from the design and why. `design.md` itself is unchanged. Nothing
here has been run on a real device: every path that would touch hardware is
tested against a faked machine (`tests/fake_hardware.py`: fake cards, mixer,
desktop, reservation, streams), and the real hardware is to be tried by hand,
a few seconds of pings at a time (see "Trying it on the laptop").

## Built

- **Detection designs** (`models/detection_design.py`, `objects/detections.py`,
  `detection_designs/<id>.json`). Every choice that was a constant in the code
  is a named setting with a unit, limits, a sentence and a default, listed once
  in `SETTINGS`: how a return is found (matched filter or envelope), the event
  threshold, the search window, the first-arrival fraction, the listed-arrival
  fraction, peak separation, most arrivals listed, the leak warning, the live
  hit threshold, the same-arrival window and wait-before-final (in signal
  lengths), the margin, the grouping tolerance, interpolation and its window,
  settle time, input-check length and the clipping, DC and noise limits. The
  dataclass `DetectionDesign`, the workspace validation, the editor and the
  notes all read that list. A default design is created in new workspaces, and
  by the application in a workspace that had none; ping designs gain an
  optional `detection_design` ID (refused if it does not exist; the design is
  refused deletion while a ping design names it).
- **Threaded through.** `models/detection.py` takes a design in
  `analyse_events`, `inseparable`, `leaking`, `correlation`, `refine`,
  `leading`, `input_check`, `locate`; `hardware/checks.py` re-exports them under
  their old names (`checks.FIRST_FRACTION`, `GROUP_SAMPLES`, `SETTLE_S`,
  `leading`, `input_check`, ... are the defaults' values) and `ArrivalDetector`,
  `settle_and_check`, `run_offset_test`, `run_schedule_test` and `_offset_result`
  take a `design`. `experiments/ranging.analyse_capture` takes one and the
  result keeps it and its ID. Each capture's meta gets `detection_design` (the
  ID and a full copy), saved in the sidecar; test summaries record it too.
- **Ping designs name a default detection design; pages and replay choose
  another.** The Ranging page has a "Detection" chooser, the ping design's
  default, an *Edit...* button and *Analyse again*, which reads the latest
  ping (or replayed recording) with the design now chosen. File > Detection
  designs... is the editor: a table of every setting beside what it does and its
  default, undoable per cell.
- **Folders.** `designs/` is `ping_designs/`; opening a step-1 workspace moves
  the files and says so (`Workspace.notices`, shown in the status bar). A file
  whose name is taken in the new folder stays and is mentioned. The importers write
  `ping_designs`.
- **Raw input from hardware checks.** `run_offset_test` and `run_schedule_test`
  keep the device's input exactly (an `InputRecorder`, not limited to the ring);
  `checks.save` writes `input.wav` and `input.wav.json` beside the CSV and
  summary. `checks.load_run` and `checks.reanalyse_offset(raw, design)` read an
  offset test again with another design; `duplex_check.py --reanalyse FOLDER
  [--detection FILE] [--detect KEY=VALUE ...]` does it from the command line and
  saves the result in a folder inside the run. `--detection` and `--detect` also
  apply to live tests.
- **`hardware/hold.py`.** The save / apply / watch / borrow / restore sequence
  that `duplex_check.py` did, as reusable pieces and as `CardHold`. The tool
  now calls them (its output is unchanged; its tests pass as they were).
- **Hardware backend** (`backends/hardware.py`) and **rigs** (`rigs/<id>.json`,
  `objects/rigs.py`): see `docs/hardware-layer.md`, "The hardware backend and
  rigs". Exclusive (reserve, mixer, desktop volumes) and shared (the server's
  PortAudio device, volumes read and recorded, warnings) access; streams kept open
  between pings; recordings per clock domain; `started`, `emitted`, `loopback_of`;
  meta with the rig, layout, per-device mixer and desktop information and the
  input check; warnings for loud pings, clipping, dropouts and a card that will not
  be given up; `identify`.
- **As-built scene** per rig, kept in step by `rigs.update_rig` (one undo step
  for the rig and the scene) and brought up to date when Hardware or *As built* is
  chosen. Medium, planes, noise and reflectors of that scene are the bench's own
  and survive rig edits.
- **Toolbar and editors.** Hardware is enabled. The rig and an *As built* button
  sit next to the scene; choosing Hardware makes the as-built scene active; in
  simulation the toolbar says "simulating X, not built" in orange when the scene is
  not the rig's. `ui/rig_editor.py`: devices, transducers against devices, loopbacks,
  *Identify*, *New laptop rig*. View > Hardware messages collects what taking hold
  of a card says (a warning opens it).
- **Simulation**: scenes gain `reflectors` (fixed point targets) and `movers`
  (a point target walking between two points at a set speed, its place set by the
  ping's `period_s`, which the Room sonar page sets from the ping rate), and truth
  records them.
- **Room sonar** (`experiments/room.py`, `pages/room.py`, `notes/room.md`): see
  below.
- **Laptop template** (`rigs.laptop_template`): layout (speaker and microphone
  0.2 m apart), a rig on the built-in card with the mixer settings that worked on
  2026-10-12, its as-built scene, a demo scene "Laptop in a room" (four surfaces, a
  cabinet, a chair, a person walking 0.5 m/s between 1.3 m and 2.8 m), a 10 ms
  2-20 kHz room chirp at amplitude 0.3 (-10.5 dBFS) and a ping design for it.

## The room sonar

- Each ping's time zero is its own direct sound: the strongest peak of the
  matched-filter output, moved back to the first peak at least the detection
  design's first-arrival fraction of it (so a stronger echo off the screen does not
  become time zero), located to a fraction of a sample. Output and input need not
  share a clock; the output-to-input delay of the device does not matter.
- Range = (c t + d) / 2 for an echo `t` after the direct sound, d the
  speaker-to-microphone distance from the layout (0 if unknown: c t / 2). The grid
  is one sample of travel (3.6 mm at 48 kHz) per bin, so every ping has the same
  bins; values between samples are interpolated.
- Listening time follows from the maximum range: (2R - d) / c + 2 ms. The page
  overrides the ping design's own `listen` for this (it is shown in the numbers);
  the hardware recording additionally keeps going for the device's latency allowance.
- Views: the current return (dB re the direct sound, with the background in grey
  and, in simulation, dotted lines at the true ranges: red for the mover), an
  echogram of the last 150 pings, and the changes: |return - mean of the last N
  returns|. Subtraction is of the matched-filter *envelope*, not the complex signal:
  the carrier phase is not reproducible to the sub-sample precision it would need.
  A mover therefore leaves a faint ghost along its past positions while it is in the
  average.
- Numbers shown: range resolution (3 / bandwidth, the detection model's rule), the
  range bin, the maximum range and listening time, the ping rate asked for and
  achieved, the unambiguous range at that rate, the speaker-to-microphone distance,
  and the direct sound's level and signal-to-noise ratio.
- Declared need: one output near one input (within 0.5 m; `rigs.near_pairs`). If the
  active scene or rig has none the page says so, the run controls are greyed with the
  reason, and it offers the scenes that fit and the laptop template.
- It sends the ping design's *first* signal from the chosen output (a room sonar
  ping has one signal).

## Simplified or left out

- **Instruments and bench measurements** (pinout, DC offset, mic bias, output level
  and impedance procedures; the `instruments/` objects) are not built. A rig has an
  empty `measured` field and nothing reads it. This is the part of step 2 of the
  design that is left.
- **Detection page.** Only its first pieces exist: the design editor, "Analyse
  again" on two pages, and the offset-test re-analysis in the library and the tool. No
  matched-filter trace views, peak-choice explanations, offset histograms, or false
  alarm / miss estimates. Detection kinds `bottom`, `decoding` and `level` are
  accepted by the workspace (they carry the same settings) but nothing uses them
  yet; only arrival detection exists.
- **Choices still in the code.** The noise estimate (the median of the filter
  output) and the floor under it (1.18 x the rounding noise of int16), the use of
  the Hilbert envelope, and `scipy.signal.find_peaks` for finding peaks are not
  settings. The envelope method is deliberately simple: the analytic signal's
  power averaged over the template length, as a root.
- **Re-analysis is close, not bit-identical.** The live detector was fed in device
  blocks; the re-analysis feeds it in 2048-sample steps. With the design the test was
  made with the offsets agree to a few hundredths of a sample (tested to 0.05).
- **Hardware backend.** One input channel per device is recorded (the stream's ring
  holds one); receivers of a device must share it. Two devices are not started
  together and their windows are not aligned (each says its own `started`; the room
  sonar does not need them to be). No sending at a requested time on a device clock
  (a later addition in the design). Closing (leaving Hardware, changing the rig, closing
  the window) is synchronous: the window waits the few seconds the desktop takes to
  recreate its sinks. If the program is killed the reservation lapses but the mixer
  and the desktop's volumes are not put back. Identify's tone is fixed (1 kHz,
  -20 dBFS, 0.5 s). The ping duration includes the latency allowance (0.15 s by
  default), so the laptop pings at about 4 Hz at most; lower the allowance in the rig
  once the offset is known.
- **Rig editor.** A text cell for mixer settings (`Name=value; Name=value`), not a
  list read from the card; the card is chosen from the cards on this machine; cards
  are named by id (built-in) or USB port path, not by number.
- **As-built scene** is brought in step when the rig is edited through the editor
  or `rigs.update_rig`, and when Hardware or *As built* is chosen. Editing the layout
  by hand (no layout editor yet) is picked up then, not at once.
- **Scenes UX.** A page declares its need by a `need_problem()` method and offers
  fitting scenes and a template; there is no shared registry of needs yet (only the
  room sonar has one). Switching the scene in hardware mode is not offered, as the
  design says.
- **The room sonar** uses one input channel and one output, no beamforming, no
  Doppler, no time-varying gain; the "ping rate" is the toolbar's shared "every"
  setting (set to 0.2 s the first time the page is made). Replay uses the output and
  input the recording names and its layout for the baseline.
- **Air only**: no water conversion until the sound speed page.

## Deviations from the design

- **Backend sketch.** `HardwareBackend.close()` and `identify()` are added to the
  interface by this backend only; `open_stream` returns a stream whose `close` does
  not close the devices (a page reopens its stream whenever anything it depends on
  changes), so the devices belong to the backend. `Ping.meta["detection_settings"]`
  carries the detection design in force so that the hardware backend can use its
  settle time and input-check limits when a device opens, and `Ping.meta["period_s"]`
  carries the time between pings for a moving simulated target.
- **Rig devices** carry `card` as a reference (empty: the built-in card, found from
  `/proc/asound` without PortAudio probing the card the desktop holds), not a PortAudio
  device.
- **Kinds and names.** The workspace kind is `ping_designs` (and the kind's singular
  is "ping design"); `detection_designs` and `rigs` are new kinds. `references` treat
  a rig's `as_built` as a reference; a scene's `as_built_of` is not, so there is no
  cycle.
- **Layering.** The matched filter, peak refinement, first-arrival rule and input
  check moved from `hardware/checks.py` into `models/detection.py` (pure functions the
  room sonar also needs); `checks` re-exports them.
- **Defaults.** The new workspace's default detection design is named "Default
  arrival detection"; old workspaces get it from the application on opening, not from
  `Workspace` itself.
- **The worktree.** The branch was created from a commit that did not yet hold
  `acoustics_lab/`; it was fast-forwarded to `main` before starting.

## Trying it on the laptop (a few seconds at a time)

1. `python3 -m acoustics_lab` (from `acoustics_lab/`), choose a workspace; in a new
   one the default detection design exists. Open **Room sonar**. It says the dongle
   bench has no output near an input; press **Make the laptop speaker and microphone**.
2. *Simulation* is now on the scene "Laptop in a room": press Space or **Continuous**
   (every 0.2 s). The return shows the direct sound at 0 dB (0.1 m, half the 0.2 m
   baseline) and echoes from the cabinet, chair and walls; the Changes view shows the
   person's zig-zag between 1.4 and 2.8 m.
3. Check the rig (**Rigs...**): *Laptop speaker and mic* has one exclusive device on
   "the built-in card" with Master -15 dB, Capture Volume 5 dB and Internal Mic Boost
   0 dB. Select *Speaker* and press **Identify**: a 0.5 s quiet tone from the laptop
   speakers (the card is borrowed and given back).
4. Choose **Hardware** in the toolbar. The as-built scene becomes active. Press Space
   once: it borrows the card, applies the mixer, lets the input settle (2 s), pings.
   Read View > Hardware messages (it opens on the first warning). Expect: the direct
   sound about 3195 samples after the output was scheduled (the ranging analysis shows
   it), a screen or table echo about 60 samples later that may be stronger, and echoes
   from the room. Walk towards the laptop with Continuous on and watch the Changes view.
5. Leave Hardware (or close the window): the mixer and the desktop's volumes are put
   back, which takes a few seconds; the message list says "as before the test".
6. The **Ranging & positioning** page runs on hardware too: pick the ping design "room
   chirp from the laptop" (one event from *speaker*, receiver *mic*) and press Space;
   the table shows the direct sound's arrival and the echo after it.
7. For shared mode (no borrowing), set the device's *Access* to shared in the rig
   editor and its *Server device* to pulse or pipewire; the sound server's volume is
   recorded and warned about when not 100 %.
