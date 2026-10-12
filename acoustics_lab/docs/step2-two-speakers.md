# Room sonar with two speakers: decisions and limits

Follows [step2-notes.md](step2-notes.md); `design.md` is unchanged. Nothing here
has been run on a real device: simulation, the faked machine
(`tests/fake_hardware.py`) and hand calculations only. Roland tries hardware.

## Built

- **Every event of the ping design is sent** (`room.build_ping`): own transducer,
  signal and time per event, on simulation, hardware (exclusive and shared; the
  backend already scheduled each transducer on its own channel) and replay (the
  sidecar already lists every event and the layout).
- **Sounds.** Events of one signal that start within the detection design's
  *same-sound window* (2 ms) are one combined sound; every other signal, or the
  same signal further apart ("left then right"), is a sound of its own, with its
  own matched filter, time zero (its own direct arrival), return, echogram and
  changes view. `room.read` gives a `RoomResult` (a `RoomPing` per sound);
  `room.analyse(capture, output, input)` stays as the one-sound reading.
- **Time zero per sound.** The strongest peak of the clearest signal anchors the
  ping (the candidate that best explains the other sounds, for a repeated
  signal); the other sounds' direct sounds are looked for where the ping design
  and the layout put them, within the *direct-sound window* (4 ms); then the
  usual first-arrival rule and sub-sample refinement.
- **Leakage** between signals that share the room's time is measured
  (`detection.isolation_db`) and shown in the numbers, the notes and a warning
  (the existing *leak warning* setting). On the lab's 10 ms chirps: up against down
  of one band -17 dB, split bands 2-10 / 11-20 kHz -102 dB.
- **Placing.** `find_echoes` (peaks above the echo threshold, beyond the nearest
  range, to a fraction of a bin), `pair_echoes` (path difference within spacing
  plus tolerance, levels within a limit, one-to-one by alike level) and
  `solve_position`: closed form when the microphone is in the speakers' plane, a
  few Newton steps from that seed with it above (a laptop's is in the screen).
  3D geometry, targets taken to be at the speakers' height; the solution in front
  (larger y) is reported, the one behind is not (stated on the page).
- **Position view**: plan (x across, y forward) or bearing-and-range, fading
  trail, speakers and microphone drawn from the layout, "not measured" marker, the
  steered zone, and in simulation green rings where the targets really are.
  Targets from every echo, or from what changed since the background.
- **Steering** for the same-signal case: the speaker nearest the target in that
  direction starts last by d sin(angle)/c; the zone where the copies merge is
  drawn and given in numbers (half-width asin(c resolution / 2 / spacing); for 0.3
  m and a 2.9 cm range resolution about 5.5 degrees, as in the brief; the brief's
  "2.9 cm of path" is half of c x resolution, which is what the code uses).
  Whole samples on hardware (7 mm).
- **Geometry on the page**: editable x, y, z of every transducer in cm (one undo
  step, the history is cleared), a "measured" tick, and a "not measured" marker
  everywhere until it is ticked or a position is edited. Starter layouts: *17-inch
  Alienware* (speakers 34 cm apart, microphone top centre, 25 cm up, 5 cm behind)
  and *15-inch Alienware* (30 cm, 22 cm up), both marked not measured; a laptop
  made before two speakers is brought up to date by `laptop_template`.
- **Starter ping designs** (new workspaces, the template, and the page's button):
  "both speakers, same chirp", "both speakers, up and down chirps", "both speakers,
  split bands", "left then right". The transducers are `left`, `right`, `mic`, as
  the dongle bench has, so the same designs run on both. The page starts on split
  bands; the ranging page still starts on "left then right".
- **Simulation**: "Laptop in a room" has two speakers, the person and a trolley.
- **Machines and WSL**: a rig records `machine` (hostname); a session starts on
  this machine's rig and says whose the active rig is (status line, numbers);
  under WSL the laptop rig is made shared with no mixer; the room sonar warns on
  WSL (hardware mode) when a ping design staggers events, or steers, because the
  Windows sound bridge slips 5-25 ms between events sent at different times, and
  recommends the simultaneous coded designs.
- **Microphone across**: the difference of the two direct arrival times (latency
  cancels) gives the microphone's x for the y and z entered; shown as "about x cm
  towards the left/right speaker of where the layout puts it", averaged over recent
  pings.
- New detection settings (principle 7), all with units, limits and a sentence:
  `echo_snr` 8, `nearest_m` 0.3, `echo_separation_s` 0.0002, `max_echoes` 20,
  `pair_tolerance_m` 0.03, `pair_level_db` 12, `direct_window_s` 0.004,
  `combine_s` 0.002.

## Accuracy (simulation, noise on, 48 kHz)

Static point targets, split bands: placed within 1.5-2.5 cm in plane (`post` and
`cabinet` of the tests), up to 3.7 cm for a chair 20 cm below the speakers'
height. Movers over many pings: median error 1.6 cm; one in five placed worse than
about 5 cm, when its echo merges with another's. Target height 30 cm above the
speakers' plane: 1-2.4 cm at 0.5-2 m; leaving the microphone's height out would
cost 0.7-2.7 cm (table with live numbers in the page's notes).

## Limits and decisions

- Same signal on both speakers: range and the beam, no place across (the side is
  not known from two copies). Steering is not searched for a bearing.
- Walls are placed where an equivalent point reflector would be; merged peaks give
  one target or a ghost; up and down chirps show a spray of ghosts near the laptop
  (the -17 dB leak) as the notes say; that is the demonstration, not hidden.
- Pairing is for the first two single-speaker sounds; more speakers are not paired.
- Echo peak finding works on the level grid (one sample of travel per bin) with a
  parabola, and uses its own `echo_separation_s`, not the arrival `min_separation_s`.
- The history is cleared when the geometry changes or the design changes shape.
- A rig from another machine is not hidden: it is only not chosen first, and the
  page says whose it is. Not built: switching machines' rigs by hostname when the
  rig list is edited, or marking a rig's devices as missing.
- Finding the microphone by tapping the lid (watch the input level) and measuring
  the geometry with a reflector at a known spot are described in the notes, not built.

## Left to do

Machine-aware rig *editing* (rigs per machine in the editor); measuring the
geometry from pings of a reflector; a bearing search for the same-signal case;
placing from more than two speakers; trying everything on real hardware.
