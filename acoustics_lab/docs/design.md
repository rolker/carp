# acoustics_lab — design

Status: **draft, 2026-10-12.** The tables under Decisions are settled. Items
marked *open*, and the user-experience section, are still to be decided.

## What it is

A desktop workbench for underwater (and in-air, scaled) acoustics: work out
how something should behave from a model, then try it, on simulated or real
hardware, and see both on the same plot.

It grows out of the bench tools in `carp/acoustic/` (ping designer, sweep,
noise, chirp data link: Tk and matplotlib programs), which were written for
one job: testing two-way acoustic ranging for CARP. Most of that code is not
CARP-specific, and the topics around it (beam patterns, transducers, sound
speed, propagation, comms, positioning, multibeam design) belong together in
one tool.

**Provenance.** The ideas and much of the starting material are older than
CARP, from my graduate acoustics coursework and later work at the Center for
Coastal and Ocean Mapping (CCOM), University of New Hampshire:

- **2007:** transducer impedance and equivalent-circuit fits (a loudspeaker
  and an underwater transducer); a laptop sound card as a measuring
  instrument; in-air 40 kHz piezo beam patterns, single elements, baffled,
  in and out of phase pairs and a 3 × 3 array, measured on a rotating mount
  and compared with theory.
- **2007–08:** beam-pattern models (elements, uniform arrays, steering) in
  C++ in [GeoZui4D](https://github.com/rolker/geozui4d), the lab's 3D
  visualization framework, of which I was a major contributor, rendered as
  3D surfaces with the measured slices drawn over them. GeoZui4D is Apache
  2.0, and that code is the starting point for the beam patterns page.
- **2008:** reciprocity calibration of a sidescan transducer in a tank;
  near field of a rectangular piston.
- **2012–13:** a phase-shift beamformer for element-level multibeam data;
  a simulated sonar receive chain (transducer model, preamplifier noise,
  ADC, quadrature demodulation, coherent and incoherent summing).
- **2012–14:** a multibeam performance prediction tool (Python, with a web
  front end), built with Xavier Lurton of Ifremer: sonar-equation coverage,
  maximum range at a required signal-to-noise ratio, and bathymetric
  accuracy for real sonar configurations, meant partly for teaching. It is
  the model for the multibeam design page; the physics is implemented from
  Lurton's book, *An Introduction to Underwater Acoustics* (2nd ed., 2010).

**Audience.** A personal tool first. It should stay open to becoming
something students use, which mostly means two habits from the start: every
page explains itself, and nothing depends on CARP or on one machine's setup.
The explanations are also reminders for the author, so they are worth
writing either way.

**Home.** It lives in the CARP repository for now, as a self-contained
top-level `acoustics_lab/` with no imports from the rest of CARP, so it can
be split out later with its history (`git subtree split` or
`git filter-repo`). It needs its own license before that happens; Apache 2.0
is the likely choice.

## Words used here

- **Signal:** a waveform to send: a chirp, a tone, data symbols, a file, or
  one derived from another signal.
- **Ping design:** a stored recipe for one transmission: which signals go
  out of which transducers, at what times, and what the ping is for (its
  roles, below).
- **Ping:** one transmission and the reception that follows, made from a
  ping design on a backend, as echosounder users mean it ("ping 12").
  A ping produces a capture.
- **Capture:** what came back from a ping: recordings, timing, and for
  simulations the truth.
- **Roles:** what a ping design is for: listening to its own echoes
  (soundings, seafloor or water-column backscatter, and more), talking to
  another node (interrogation, reply, beacon, data), or bench work. A
  design can have several. See *Ping roles* under Signals and ping
  designs.
- **Responder:** something that listens for an interrogation and answers
  with a reply, as a transponder does.
- **Sequence:** an ordered, repeating set of ping designs; positioning's
  interrogation cycle.
- **Transducer:** a named sender or receiver ("TX north", "RX 1"), whether
  real or simulated.
- **Layout:** where each transducer is, which way it faces, and what it is.
- **Rig:** which real device and channel each transducer is wired to, and
  what has been measured about it.
- **Scene:** what the simulator simulates: a layout plus the medium,
  reflecting surfaces and noise.
- **Profile:** sound speed (or temperature and salinity) against depth.
- **Clock domain:** a set of samples timed by one clock. Two recordings in
  the same clock domain can be timed against each other exactly; across
  domains only by measurement.
- **Backend:** where pings are made: hardware, simulation or replay.
- **Instrument:** a bench meter (a multimeter, later perhaps an
  oscilloscope) described by what it can measure and how well.

## Decisions

| Decision | Choice | Why |
|---|---|---|
| Language | Python 3, numpy and scipy | The hardware side is already Python; the models are array maths; fast to change |
| Physics | Written here, independent of any other engine | Keeps the tool self-contained; its tests can serve as reference values for a faster implementation elsewhere later |
| User interface | Qt with pyqtgraph; 3D through `pyqtgraph.opengl` and `python3-opengl` | Fast live plots, 3D surfaces for beam patterns, dockable panels |
| Dependencies | Ubuntu 24.04 apt packages only | Same rule as `carp/acoustic`: the system Python that ROS uses, nothing from pip at run time |
| Seawater properties | TEOS-10 through `python3-gsw` (in apt) as the reference; classic formulas written here alongside it | TEOS-10 is the current standard and covers fresh to salt water; the classic formulas are what textbooks and older software use, and comparing them is part of the lesson |
| Audio | PortAudio through PyAudio, as now | Works; `audio_io.py` already handles its quirks |

**Open: which Qt binding.** pyqtgraph supports PyQt5, PyQt6 and PySide2, and
all are in apt. Prefer Qt 6 (`python3-pyqt6`) if pyqtgraph's 3D view works
with it from apt, under Wayland as well as X11; fall back to PyQt5. Qt is
imported through `pyqtgraph.Qt` plus a small shim of our own for classes
that moved between Qt 5 and 6 (`QUndoStack` and `QAction` are in `QtWidgets`
in Qt 5 and `QtGui` in Qt 6), so the binding can change without touching
pages. A short spike settles this before anything else is built.

## Principles

1. **One experiment, any backend.** A page that runs an experiment asks for
   "send these signals from these transducers, give me what the receivers
   heard". Whether that is a sound card, a simulated scene or a saved run is
   chosen once, in the toolbar, not per page.
2. **Models are plain functions.** No Qt, no audio, no global state: arrays
   and numbers in, arrays and numbers out, with units in the names or
   docstrings. Each one has tests against a textbook case or a hand
   calculation, to tight tolerances. Each states its source (paper or
   standard) and its range of validity. Outside that range it still
   answers, but marks the result as extrapolated, and pages show the mark.
   No hidden defaults: the medium (air or water, temperature, salinity,
   depth) is always passed in, never assumed.
3. **Theory and measurement on the same axes.** Model curves as lines,
   measurements as points, in consistent colours, so the comparison is the
   default view rather than an extra step.
4. **Every number explains itself.** Derived quantities are shown next to
   the inputs that produce them (wavelength, ka, near-field distance,
   processing gain), and each page has notes with the equations and rules of
   thumb, filled in with the current values.
5. **Simulation knows the truth.** A simulated capture carries the real path
   delays and levels, so processing can be checked against them, not just
   eyeballed.

## Architecture

```
 pages        signals · transducers · beam patterns · sound speed · propagation
              echo sounding & backscatter · doppler · noise · receiver chain
              ranging & positioning · comms · multibeam design · sonar equation
 ─────────────────────────────────────────────────────────────────────────────
 experiments  ping · sweep · rotate-and-measure · record noise · send data
              distance series · stepped-level loopback · measure sound speed
 backends     hardware (audio devices) │ simulation (scene) │ replay (saved runs)
 workspace    signals · ping designs · layouts · scenes · rigs · profiles · runs
 models       media (sound speed, absorption) · ray tracing · elements & arrays
              signals · detection · transducer resonance · channel
              receiver & ADC · sonar equation · positioning · comms · multibeam
```

Lower layers never import upper ones. Models know nothing of scenes or the
workspace; backends know nothing of pages.

### Package layout

```
acoustics_lab/
  README.md
  docs/design.md
  acoustics_lab/
    __main__.py            # python3 -m acoustics_lab
    models/                # pure functions, no Qt, no audio
      media.py             # sound speed and absorption, air and water; air/water scaling
      raytrace.py          # rays through a layered sound-speed profile
      elements.py          # point, line, rectangular, circular piston responses
      arrays.py            # uniform and arbitrary arrays, steering, shading
      signals.py           # tones, chirps, chirp-spread-spectrum symbols
      detection.py         # matched filter, envelopes, first arrival
      transducer.py        # resonance (equivalent circuit) model
      channel.py           # spreading, absorption, image-source paths
      receiver.py          # gain, clipping, automatic gain, ADC quantisation, TVG
      sonar_equation.py
      positioning.py       # geometry to position error; clock sync from exchanges
      comms.py             # modem theory: error rates, detection, link budget
      multibeam.py         # beam widths, footprints, coverage, sounding accuracy
      doppler.py           # shifts, Doppler-tolerant signals, velocity estimation
    qtcompat.py            # the Qt 5 / Qt 6 shim
    workspace.py           # folder, files, IDs, undo stack, file watching
    objects/               # signals, ping designs, layouts, scenes, rigs, profiles, instruments
    procedures/            # guided bench measurements, one module each
    backends/
      base.py              # the interface below
      hardware.py          # from carp/acoustic/audio_io.py
      simulation.py
      replay.py
    experiments/           # one module per experiment in the diagram
    pages/                 # one module per page
    ui/                    # main window, editors, shared widgets, plot helpers
    notes/                 # one Markdown file of explanations per page
  tests/
```

### Backend interface (sketch)

```python
@dataclass
class Emission:
    transducer: str          # transducer ID
    samples: np.ndarray      # float, full-scale units, at the sending device's rate
    start: float             # s after the ping starts, on the sending device's clock

@dataclass
class Ping:
    emissions: list[Emission]
    receivers: list[str]     # transducer IDs
    listen: float            # s to keep recording after the last emission

@dataclass
class Recording:
    samples: np.ndarray      # float, full-scale units (hardware gives int16, mono)
    rate: float              # this device's sample rate
    clock: str               # clock domain
    started: float           # start time on that clock, s
    loopback_of: list[str]   # emitter IDs whose electrical copy is mixed into this input

@dataclass
class Capture:
    recordings: dict[str, Recording]   # receiver transducer ID -> recording
    emitted: dict[str, float]          # emitter ID -> send time, where the backend knows it
    truth: dict | None                 # simulation only: every path's delay, level, history
    meta: dict                         # devices, gains, wall time, scene or rig, versions

class Backend(Protocol):
    name: str
    realtime: bool           # False: a simulation may run faster than real time
    def transducers(self) -> list[TransducerInfo]   # ID, name, can send / receive, rate
    def fire(self, ping: Ping, progress, cancel) -> Capture   # called from a worker thread
    def open_stream(self, ping: Ping) -> PingStream   # repeated pings, streams kept open
```

**Timing is measured, not assumed.** Times are always on a named device
clock. Even on one USB dongle, output and input are separate PortAudio
streams with an unknown offset between them, so the send time is not known
from software. The reference is the **loopback**: an electrical copy of an
output mixed into an input through a resistor, as in the bench circuit. The
rig records which input carries the loopback of which output
(`loopback_of`), and processing finds time zero there, as `ping_gui.py`
does now. Without a loopback, time zero is the first arrival, as on the WSL
bridge. Between devices, clocks are compared by measurement (a shared
loopback or a two-way exchange). Starting two dongles from Python is never
simultaneous; each recording's `started` time says how far apart they were.

- **Hardware** maps transducer IDs to device and channel through a rig.
  Hardware recordings are int16 and mono; they are converted to float on
  arrival, with the original format kept in `meta`.
- **Simulation** builds each recording from the scene (below), including a
  loopback copy wherever the simulated rig has one, so processing sees the
  same structure as on hardware.
- **Replay** reads saved captures. Reprocessing old data with new settings
  is the main use.

**Threads.** `fire` runs on a worker thread with progress and cancel, never
on the GUI thread. Live modes (continuous pinging, the echogram) use
`open_stream` and keep PortAudio streams open between pings instead of
opening them per ping as `audio_io.play_and_record` does now. Plot redraws
must not starve the audio callbacks; if threads are not enough, audio moves
to its own process.

**Later additions, when a page needs them:** sending at a requested time on
a device clock (for a fixed reply delay in two-way ranging), and captures
pushed by a detector rather than requested. Together these make
**responders** possible: a simulated or real transponder that hears an
interrogation and sends its reply design after a fixed delay. A simulated
responder lives in the scene; a real one is a second rig (another dongle,
another computer, or the vehicle).

Experiments that move something (turning a disc for a beam pattern) go
through a `Positioner`: *manual* asks the user to set the angle and press a
button; *simulated* changes the scene; a motorised stage could be added
later.

### Rigs and layouts

Ping designs and pages refer to transducers by ID, never to devices. Two
workspace objects connect transducers to something real:

- **Layout:** each transducer's ID and display name, where it is, which way
  it faces, and what it is (element model such as a 20 mm circular piston,
  resonance model). The twelve-pocket ring and the flat cross are layouts.
- **Rig:** which device and channel each transducer is on, which inputs
  carry which loopbacks, and what has been measured about each path: gain,
  latency, calibration, band.

**Finding the right dongle.** Identical USB dongles report the same name to
PortAudio. A rig identifies each by its USB port path, read from
`/proc/asound` and sysfs (PyAudio does not expose it). That is fragile
across kernels and hubs, so the fallback is to ask: play a short tone on
each candidate in turn and let the user say which transducer made it. The
rig says clearly when a device has moved or is missing.

The hardware backend needs a rig; the simulation backend needs a scene and
plays the part of a rig, so the same ping design runs on either.

### Scene (simulation)

- **Transducers:** a layout, as above, plus a simulated rig (which
  transducers share a device, and loopbacks).
- **Medium:** air (temperature, humidity, pressure) or water (a profile).
  It gives sound speed and absorption along each path. To start, paths are
  straight and travel time uses the mean slowness along the path; bending
  comes with ray tracing (open question).
- **Boundaries:** flat reflecting planes (table, floor, wall, water surface,
  bottom) with a reflection coefficient, handled as image sources. Enough
  for bench and shallow-water multipath without ray tracing.
- **Noise:** a level and spectrum shape, or a recorded noise file played
  underneath, separately per device.
- **Clocks:** offset and drift per simulated device, and its sample rate.
- **Motion (later, for the Doppler page):** transducers and reflectors that
  move along a path. A moving path changes its delay during the signal, so
  the signal is stretched or compressed, not only delayed: 1 m/s in water
  stretches a 40 ms chirp by about 27 µs, more than a sample at 48 kHz.
  Parametric signals are then generated at the warped times directly;
  file signals are resampled per path with a band-limited method whose
  accuracy is stated in `truth`.

**How a recording is built.**

- Each path (direct, or an image source per reflection) is rendered in the
  frequency domain: the sent signal's spectrum times `exp(-j2πfτ)` for the
  delay, times spreading, absorption `α(f)` over the path, reflection
  coefficients, and both transducers' directivity and resonance. Delays are
  then exact to any fraction of a sample, with no truncated interpolation
  kernel. That matters most near the top of the band: several current ping
  designs use 16–20 kHz with 48 kHz sampling.
- **Padding.** A delay in the frequency domain is circular, so each path is
  rendered into a buffer at least as long as the signal, plus the longest
  path delay, plus room for the ringing of the resonance and directivity
  filters (which can also ring slightly before the arrival), rounded up to
  a fast FFT length, then trimmed. Real FFTs (`rfft`) keep the result real;
  the Nyquist bin is handled explicitly. A test delays an impulse by a
  fraction of a sample near the end of the buffer and checks nothing wraps.
- **Clocks are part of the delay, not a resampling afterwards.** Each
  path's arrival time is mapped through the receiving device's clock
  (offset plus drift), and the sender's emission time through the sending
  device's clock, before rendering. Parametric signals are generated
  directly at the device-clock times. What this leaves out is the stretch
  of a signal by drift during its own duration: 50 ppm over a 40 ms chirp is
  2 µs, a tenth of a sample at 48 kHz. That residual is stated in `truth`
  rather than hidden.
- Source directivity is taken in the direction from the (image) source to
  the receiver; receiver directivity in the direction it arrives from.
- Times are float64 throughout. No global delay is added and no high-pass
  is applied: the truth must match the recording.
- `truth` holds every path's exact delay (on each clock), level and
  reflection history.

### Air and water

Bench tests run in air at a reduced size. The scale factor is the ratio of
the two sound speeds, computed from both media rather than fixed: about 4.3
(4.31 to 4.37 over ordinary temperatures).

**What carries over.** Dividing a water geometry by that factor and keeping
the same frequency keeps travel times the same, and also keeps every size
in wavelengths the same, because the wavelength shrinks by the same factor.
So beam patterns, ka, near-field distances, grating-lobe angles and timing
all carry over. A 20 mm disc at 18 kHz in air behaves, in pattern and
timing, like an 86 mm disc at 18 kHz in water. Doppler carries over too if
speeds are scaled by the same factor, since it goes with speed over sound
speed: a vehicle moving at 1 m/s in water is a 0.23 m/s motion on the
bench.

**What does not.**

- Absorption: air absorbs far more per wavelength than water at these
  frequencies.
- Impedance, and so reflection and transmission at boundaries: ρc is about
  413 for air and 1.5 million for water.
- The transducer itself: loading, resonance frequency and sharpness, and
  efficiency all change with the medium it pushes against.
- Noise sources, bubbles and boundaries: a table is not a seafloor.

The medium setting converts geometry both ways, and pages show results in
water terms as well ("this 115 mm bench spacing stands for 0.5 m on the
vehicle"). Where a page's result depends on something in the second list,
its notes say so.

## Pages

Lower-level topics first, then systems built from them. Each page has a
model part; those with an experiment also run on a backend. "Starts from"
names the existing `carp/acoustic` code (Tk and matplotlib) or older work
the page grows from.

| Page | Model | Experiment | Starts from |
|---|---|---|---|
| Signals | Chirps and tones; spectrum; processing gain against white noise (duration × bandwidth, less for tapered signals); peak width (first nulls of the matched-filter envelope at ±1/bandwidth, about 0.89/bandwidth wide at −3 dB without tapering); how strongly each signal correlates with each other one (which can share a ping) | Ping a signal, compare received and sent spectrum | `pinger.py`, `ranging_dsp.py` |
| Transducers | Resonance from an equivalent circuit; bandwidth; ringing | Frequency sweep through a transducer | sweep tab of `ping_gui.py` |
| Beam patterns | Elements and arrays, steering, grating lobes; polar slices and 3D surface | Rotate and measure, plotted over the model | GeoZui4D beam-pattern code and the 2007 lab |
| Sound speed | Water: TEOS-10, with Mackenzie (salinity 25–40, 2–30 °C, to 8000 m), Chen–Millero (UNESCO; salinity 0–40, so fresh water too), Del Grosso, and pure-water formulas (Marczak; Bilaniuk–Wong) to compare; air: temperature and humidity. Profiles: from a CTD (temperature and salinity probe) cast, typed in, or built (mixed layer, thermocline, a lake through the seasons). Derived: gradients, mean speed to a depth. Refraction: ray fans through a layered profile, shadow zones, ducts. Consequences: range error from a wrong sound speed; multibeam "smile" and "frown" from a wrong profile; how fast sounding uncertainty grows as profiles age (after Beaudoin's uncertainty wedge) | Measure sound speed in air over a known distance and compare with a thermometer reading (about 0.6 m/s per °C, 0.4 mm of range per °C at 230 mm) | new |
| Propagation | Spreading; absorption (water: Francois–Garrison, Thorp for a quick estimate; fresh water: Francois–Garrison with salinity 0, which leaves only its pure-water term, flagged as an estimate since the model was not fitted to fresh water; air: ISO 9613-1, specified to 10 kHz and marked extrapolated above it); reflections; travel time | Distance series | new |
| Echo sounding & backscatter | Single-beam echo sounding: bottom detection, seafloor backscatter against angle, water-column echograms and volume backscatter strength, target strength and calibration with a standard sphere; the echo roles above on one transducer before an array | On the bench, in air: sound a board, tilt it for angle, hang a small ball as a target and a cloud of small objects as a "water column" | echogram view of `ping_gui.py` |
| Noise | Background spectrum and over time | Record noise | noise tab of `ping_gui.py` |
| Receiver chain | Gain staging, clipping, automatic gain, ADC bits and dynamic range; time-varying gain (TVG): 40 log R for a point target, 30 log R for seafloor reverberation, 20 log R for volume reverberation, each plus 2αR for absorption | Stepped-level loopback test | new |
| Ranging & positioning | Ping designs and event timing; layout geometry to position error; one-way with sync vs two-way (timestamps at both ends, fixed reply delay, clock offset and drift estimated from the exchange); how long a sync stays good for a given clock drift | Ping, continuous, echogram | `ping_gui.py`, `docs/navigation.md` |
| Comms | Chirp spread spectrum link; theory for it as non-coherent near-orthogonal M-ary signalling, with coherent BPSK as a familiar baseline; later frequency-hopping FSK as a slower, more robust alternative; simulated link as sonar-equation SNR, then detection against a false-alarm rate, then a measured error-rate curve, with optional fading; a known-data test mode for counting bit errors | Send and decode a message | `chirp_data.py`, data tab of `ping_gui.py` |
| Doppler | Shift for one-way and two-way paths (about 2v/c for an echo); what motion does to each kind of signal: a CW pulse shifts in frequency, a linear chirp shifts in apparent time (range–Doppler coupling), a hyperbolic chirp hardly changes (Doppler-tolerant); the ambiguity function of each signal design; Doppler in comms (time compression, why modems estimate and resample); range error from a moving vehicle; velocity measurement: DVL bottom track and water track with four slanted beams, ADCP current profiles, pulse-pair and broadband estimation and their ambiguity velocity | A reflector or transducer moving on the bench (a pendulum, or a board on a slide), with speeds scaled as above | new |
| Multibeam design | Transmit and receive arrays to beam widths, footprints, swath, sounding spacing, grating lobes, range limit, ping rate; bottom detection by amplitude and by phase, and the sounding accuracy of each; seafloor and water-column backscatter from the same ping; optional coherence-factor beamforming | None (model only) | beam patterns, sonar equation, the 2012–13 beamformer and 2012–14 performance tool |
| Sonar equation | Source level, transmission loss, target strength, noise, directivity, detection threshold | None | used by other pages |

## Workspace

Everything the user makes lives in a workspace folder. The tool remembers
the last one (Qt settings, `~/.config/acoustics_lab/`) and opens it at
start; File → Open and a recent-workspaces list switch between them, and
`--workspace` overrides. A workspace is also the natural unit to hand out as
a lab exercise later.

```
my_workspace/
  workspace.json         # name, settings shared by its pages
  signals/<id>.json
  designs/<id>.json      # ping designs
  layouts/<id>.json
  scenes/<id>.json
  rigs/<id>.json
  profiles/<id>.json     # sound-speed profiles: casts, typed in, or built
  instruments/<id>.json  # bench meters and their limits
  runs/<date>/...        # captures: WAV per recording + JSON sidecar
  .gitignore             # runs/ by default
```

**IDs.** Every object, and every transducer inside a layout, has a short,
readable ID made from its first name (`up_16_20k`, `tx_north`), fixed when
it is created and never changed. The display name lives inside the file and
can change freely, so renaming breaks nothing and git diffs stay readable.
References between objects always use IDs.

- **Deleting** something that other objects use is refused, with a list of
  what uses it; delete or repoint those first.
- **Derived signals** cannot form a loop (a signal derived, through any
  chain, from itself); the editor refuses the edit that would close one.

**Files and edits.**

- **No Save button.** Each edit is written as it is made, atomically (write
  a temporary file, then rename), so a crash never leaves half a file.
- **Undo and redo** (one Qt `QUndoStack` per workspace) cover signals,
  ping designs, layouts, scenes, rigs, profiles and instruments: Ctrl+Z,
  Ctrl+Shift+Z, and an
  optional history panel. Undo rewrites the file too. One committed cell
  edit is one undo step; typing within a cell is not.
- **Runs are records, not edits,** and are not undone.
- **Outside changes.** The tool watches the workspace folder. If files
  change underneath it (a `git checkout`, a pull, another editor), it
  reloads them, clears the undo history, and says so.

**Version control.** Files are laid out for it whether or not it is used:
one object per file, pretty-printed JSON with a stable key order, no
timestamps that change on every write.

- **Git is optional.** Creating a workspace offers "initialise as a git
  repository". The tool does not commit on every edit (that would bury the
  history); at most a "commit snapshot" action with a message. Anything
  beyond that is left to git itself, not rebuilt as a git interface.
- **Every run records what made it.** A capture's sidecar holds copies of
  the ping design, signals, layout or scene and rig used, so a recording can
  always be traced to the exact versions that produced it, with or without
  git. If the workspace is a git repository, the sidecar also holds the
  commit; since edits are written immediately, there will usually be
  uncommitted changes as well, which is why the copies are the record and
  the commit is a convenience.

**Imports** from `carp/acoustic`:

- `designs/*.json`: each signal becomes a signal object (its name becomes
  its ID), each design a ping design. The old channels `left` and `right` become
  transducers `left` and `right` in a "stereo dongle" layout and rig,
  which the user can then rename.
- `runs/` recordings open in replay.

## Signals and ping designs

Two lists, managed alike, shared by every page.

**Signals.** Kinds:

- *parametric:* chirp, tone, data symbols, noise burst; defined by a few
  numbers, generated at whatever sample rate is in use.
- *from file:* a WAV, for recorded or externally made signals.
- *derived:* a recipe applied to another signal: time reverse, invert,
  shift in band, change fade or amplitude, join. A derived signal follows
  its source when the source is edited; *detach* freezes it as a copy. The
  reverse of an up-chirp is a down-chirp, and the two correlate poorly,
  which is useful when several transmitters share a ping.

**Editing with few clicks.** The signal list is an editable table: change a
value in place, Enter or leaving the cell commits it. No separate form and
Update button. The selected signal shows a live preview (waveform, spectrum,
spectrogram), and read-only columns show what it is worth: duration, band,
processing gain, peak width. Checks run as values change: above what the
sample rate can carry, outside a rig's measured band, too close to another
signal in the same ping.

**Ping designs.** A ping design says which signal goes out of which
transducer at what time, as the current ping designer does, and lists its
roles. Every page that sends anything picks a ping design from the same
list with the same control: ranging, beam-pattern measurement, sweep,
comms. The roles tell a page what to do with what comes back: time the
arrivals of interrogations, replies and beacons; decode data pings; measure
levels from measurement pings. A responder is told which designs are
interrogations it answers and which design is its reply.

**Ping roles.** Grouped by who listens.

*Echo roles: the sender listens to its own echoes.* What is kept differs,
which is why they are separate roles even when one ping serves several, as
a multibeam ping does.

| Role | What comes back is used for | What is kept |
|---|---|---|
| Sounding | Range (and angle) to the bottom: bathymetry; a single-beam echosounder or altimeter is the simplest case | Detections: range, angle, quality |
| Seafloor backscatter | How strongly the bottom returns sound, against angle, to tell rock from mud; sidescan imagery is this | Calibrated intensity around each detection, or along track |
| Water-column backscatter | Echo intensity through the water column, not a sounding: fish, plankton layers, bubble plumes and seeps, suspended sediment, wrecks standing off the bottom | Full intensity against range for every beam (an echogram), volume backscatter strength Sv |
| Target strength | How strongly a single target returns sound (a fish, a calibration sphere) | Peak level of isolated echoes, and their angle if the transducer is split-beam |
| Sub-bottom | Layers below the seafloor, with low frequencies that penetrate it | Intensity against depth below the bottom |
| Velocity | Doppler shift of echoes: speed over the bottom (bottom track, as a DVL does) or water current with depth (as an ADCP does) | Doppler shift or phase change per range bin |

*Link roles: another node listens.*

| Role | Meaning |
|---|---|
| Interrogation | Asks a responder to reply |
| Reply | Sent by a responder after a fixed delay |
| Beacon | Sent unprompted, for one-way ranging against a synchronised clock |
| Data | Carries a message: telemetry, commands, acknowledgements |

*Bench roles.*

| Role | Meaning |
|---|---|
| Measurement | Sweeps, beam patterns, distance series, level steps |
| Calibration | Pings whose result corrects others: loopback level, a standard target, reciprocity |

A ping design can combine roles across groups: a data ping whose preamble
is timed is also a beacon; a multibeam ping is sounding, seafloor
backscatter and water-column backscatter at once.

**Later: sequences.** Positioning runs in cycles (interrogate A, then B,
then C, repeat; an echosounder calls this sequencing). A third list of
sequences can come when that page needs it.

## Bench measurements

Hardware numbers the rest of the tool relies on (volts per full scale,
output impedance, input sensitivity, mic bias, disc capacitance) are
measured on the bench with ordinary meters. The tool guides those
measurements, does the playing and the arithmetic, and keeps the results in
the rig with where they came from.

**Instruments.** A workspace object per meter: model, what it measures,
whether its AC reading is true RMS, its AC bandwidth (cheap multimeters are
often specified only to 400 Hz or 1 kHz and read low above that), its
ranges and resolution. Procedures choose test frequencies and levels the
meter can handle, and flag a reading outside its specification.

**Procedures.** Each is a short guided sequence: what to connect (with a
diagram), which meter mode and range, what the tool will play, the range of
readings to expect, and a field for the reading. The tool computes the
result and stores it in the rig with the date, instrument and raw readings.

| Procedure | Meter mode | How | Gives |
|---|---|---|---|
| Plug pinout | Continuity | Plug inserted, probe each contact against the leads | Which contact is left, right, mic, ground |
| Output DC offset | DC volts | Output idle | Offset, should be near 0 V |
| Mic bias | DC volts | Mic contact to ground, nothing connected | Bias voltage, which the coupling capacitor must block |
| Output level and linearity | AC volts | Sine at a frequency inside the meter's bandwidth (typically 1 kHz), at −20, −10, −6 and −3 dBFS, never at 0 dBFS where outputs can clip; the device's own mixer at a known setting and system volume bypassed | Volts RMS at full scale, and whether each 10 dB step reads ×3.16 |
| Output impedance | AC volts | The same tone, open circuit, then across a known resistor (about 100 Ω): Z = R·(V_open/V_loaded − 1) | Output impedance, used by the simulator and the receiver chain page |
| Input sensitivity | AC volts | The calibrated output into the mic input through a resistor divider (for example 100 kΩ over 1 kΩ); meter on the divided voltage if it resolves millivolts, otherwise computed from the divider | Volts at the input per full scale |
| Disc capacitance | Capacitance | Disc disconnected | Capacitance, for the transducer model |
| Resistors | Resistance | Out of circuit | Actual values of the bench circuit's resistors |

Responses at higher frequencies (16–20 kHz and up) are not taken from the
meter; they are measured relative to the 1 kHz point through the loopback,
by the sweep.

**Where results show.** Pages that use a measured value (levels in volts,
output impedance in the simulator, capacitance in the transducer model)
say which measurement it came from and when; a value that was never
measured is shown as assumed.

Later, an oscilloscope as an instrument would add phase and timing
procedures, such as the series-resistor impedance sweep from the 2007 lab.

## User experience (proposal, to discuss)

- **Window.** A list of pages down the left, grouped into foundations and
  systems. A toolbar across the top holds what applies everywhere: backend
  (simulation, hardware, replay) with its rig or scene, sample rate, and a
  run button.
- **Medium.** The scene owns the medium; the toolbar shows the current
  scene's medium and edits it there. Pages pass it to the models
  explicitly. Replay uses the medium recorded with the capture, which can
  be overridden for reprocessing.
- **A page.** Parameters on the left with units, each with its derived
  values beside it. Plots in the centre, in docks that can be rearranged.
  Notes on the right, collapsible, with the equations and current numbers.
- **Running.** One ping, continuous, or a sequence (sweep, rotation), with
  progress and stop at the bottom. Space bar pings.
- **Bench measurements.** Run from the rig editor (and offered when a
  page needs a value that has not been measured); the Receiver chain
  page's notes explain what each measurement means.
- **Editors.** Layouts, scenes and rigs each have one editor, shared by
  every page: a layout shown top-down and side-on; a rig as a table of
  transducers against devices, with an "identify" button that plays a tone.
- **Export.** Any plot as PNG or SVG, its data as CSV.
- **Scripting.** The workspace objects and models usable from a Python
  script or notebook, for batch runs, without the window.

Questions to settle (current leaning in brackets):

1. Page list on the left, tabs, or a free workbench where views from
   different pages can sit side by side? (List; docks within a page.)
2. Is the scene global, or does each page carry its own? (Global: the bench
   is one bench.)
3. Notes always visible, collapsible, or as hover tips? Static text, or
   filled in with live values? (Collapsible, with live values.)
4. Model and experiment on one page, or as separate modes? (One page.)
5. For air-scaled bench work, show air numbers, water numbers, or both?
   (Air, with water equivalents beside them.)

## Testing

- **Models** against hand calculations and textbook values, to tight
  tolerances. Examples, each recomputed by hand:
  - Mackenzie sound speed at 27 °C, salinity 35, 10 m: 1539.09 m/s.
  - Normal-incidence reflection from ρ = 1200 kg/m³, c = 1600 m/s under
    seawater (1023, 1540): (Z₂ − Z₁)/(Z₂ + Z₁) = 0.0986.
  - Non-coherent binary FSK bit error rate at Eb/N₀ = 10 dB:
    ½·exp(−Eb/2N₀) = 3.4 × 10⁻³ (the family the chirp modem belongs to).
    Coherent BPSK at 7 dB: Q(√(2·Eb/N₀)) = 7.7 × 10⁻⁴.
  - Uniform array of N elements spaced d, steered to θ₀: first nulls either
    side of the main lobe at sin θ = sin θ₀ ± λ/(N·d); grating lobes at
    sin θ = sin θ₀ ± m·λ/d.
  - ISO 9613-1 air absorption against values computed from the standard's
    formulas and checked against a published table (source cited in the
    test).
- **Simulation** against its own truth: arrival times recovered from a
  simulated recording to a small fraction of a sample, including near the
  end of the buffer and with clock drift; levels to the expected spreading,
  absorption and reflection losses.
- **Cross-checks against other open-source tools**, for development only,
  installed with pip outside the system Python and skipped when absent:
  pyroomacoustics for image-source delays and levels in air (with its
  default high-pass filter and fixed added delay turned off), arlpy for
  water absorption and sound speed. TEOS-10 (`gsw`, from apt) checks the
  classic sound-speed formulas inside their valid ranges.

## Related work

### At CCOM

- **[Sound Speed Manager](https://www.hydroffice.org/soundspeed/main)**
  (HydrOffice; CCOM and NOAA; Python; LGPL 2.1): sound-speed profile
  management for survey work. It reads about 25 profiler and CTD file
  formats and can pull profiles from ocean climatologies (World Ocean Atlas,
  RTOFS). The sound speed page could import casts and typical profiles
  through it as an optional extra. Its code is LGPL, so it is called, not
  copied in.
- **Uncertainty wedge** (Beaudoin, Hiebert, Calder and Imahori, 2009;
  [Beaudoin's 2010 dissertation](https://gge.ext.unb.ca/Pubs/TR271.pdf)):
  ray tracing through successive profiles to show how much sounding
  uncertainty comes from the water column changing. A model for the sound
  speed page's "consequences".
- **[Multibeam Advisory Committee assessment
  tools](https://mac.unols.org/resources/assessment-tools/)**: swath
  coverage and accuracy plotters from ships' acceptance tests. Measured
  coverage against depth in that form is what the multibeam design page's
  predictions should be compared with.
- **[OpenBST](https://scholars.unh.edu/ccom/1713/)** (Open Backscatter
  Toolchain): community-reviewed seafloor backscatter processing, for a
  seafloor-scattering page later.

### Elsewhere

What exists, as read in October 2026. None of it combines models,
simulation and real sound-card hardware for these topics in one tool, and
none is usable as a run-time dependency under the apt-only rule. Statements
are about the versions named and may not hold for later ones.

| Project | Version read | What it is | License | Useful here | Different here |
|---|---|---|---|---|---|
| [arlpy](https://github.com/org-arl/arlpy) | 1.9.3 (last commit 2026-09-04) | Python underwater acoustics, signals, beamforming and comms functions; a wrapper for the Bellhop propagation model. Its README says it is in maintenance mode | BSD | Reference values for sound speed (Mackenzie), absorption (Francois–Garrison), reflection, Doppler; plain functions with units and a runnable example in each docstring; steering delays as their own array | Its functions default to 27 °C seawater, and some defaults are computed when the module loads; this tool needs the medium passed every time. It does not cover air, the sonar equation, spreading loss or chirp modems, which are this tool's to write |
| [pyroomacoustics](https://github.com/LCAV/pyroomacoustics) | 0.10.1 (last commit 2026-07-17) | Room simulation in air by image sources; array processing; direction finding | MIT | Image-source paths for flat planes; where to evaluate source and receiver directivity; a directivity interface taking azimuth and colatitude | Built for room acoustics: its air-absorption table covers octave bands up to 8 kHz, and by default it adds a fixed delay and a 10 Hz high-pass to responses. This tool needs higher frequencies and exact truth, so it renders paths in the frequency domain |
| [EchoVerse Sonar Lab](https://github.com/Qiuming-Ai/echoverse_sonar_lab) | commit of 2026-09-04 | C++/Qt application rendering a 3D scene into forward-looking, multibeam and sidescan sonar images, with a separate stage that simulates waveforms and beamforms them | Apache 2.0 | Time-varying gain with a selectable spreading law; coherence-factor beamforming variants; staging of the receive chain; a small summary file per recording session | Its images come from rendering the scene's geometry; this tool works from the sonar equation and calibrated levels, so it can compare with measurements |
| [UnetStack](https://unetstack.net) | 7.0.0 | Underwater network stack whose simulator and real modems run the same code; includes a software modem that uses a computer's sound card | Community edition: academic teaching and research only, distributed as a binary package; some components are open source | Device clocks never assumed in sync; start times on captures; sending at a requested time; two-way ranging with a fixed reply delay; how long a clock sync stays valid; a channel model built as SNR, then detection against a false-alarm rate, then error rate with fading; frequency-hopping FSK | Built as many communicating agents, which a single-process tool does not need |

Also noted, not studied in depth: Acoular (microphone-array beamforming in
air, BSD); MATLAB's Sensor Array Analyzer (beam patterns, commercial); REW
and ARTA (sound-card measurement of frequency response, impedance and, in
ARTA, directivity).

## Getting there from carp/acoustic

The move is a rebuild of the user interface, not a port: `ping_gui.py` is
about 1200 lines of Tk and matplotlib, and every widget is rewritten in Qt.
The processing in `pinger.py`, `ranging_dsp.py`, `chirp_data.py` and
`audio_io.py` moves across with its tests. `carp/acoustic` keeps working
until the new tool does everything it does; then its programs retire, and
`carp/acoustic` keeps the bench hardware notes and ping designs.

0. **Spike:** a pyqtgraph window with a live plot and a 3D surface, on
   PyQt6 and on PyQt5, on the dev machine (X11 and Wayland) and under WSL.
   Settles the Qt binding.
1. **First working tool, simulation and replay only:** models moved from
   `ranging_dsp.py` and `pinger.py` with their tests; workspace with
   signals, ping designs and undo; imports of old designs and runs; simulation
   backend with a minimal scene (point transducers, one medium, noise,
   loopback); replay; the ranging page with one ping, continuous and the
   echogram. No hardware yet.
2. **Hardware:** the hardware backend from `audio_io.py`, with streams kept
   open; rigs and the rig editor with "identify"; loopback timing;
   instruments and the first bench measurements (pinout, DC offset, mic
   bias, output level, output impedance). At this point the ranging page
   matches `ping_gui.py` on the ping itself.
3. **Beam patterns:** the page, the layout and scene editors, and
   rotate-and-measure.
4. **Sound speed and propagation:** profiles, ray tracing for the page,
   reflections in the scene, the distance-series and sound-speed
   experiments.
5. **Signals, noise, receiver chain, transducers:** the remaining tabs of
   `ping_gui.py` (sweep, noise, data) find their homes here and in comms,
   and `ping_gui.py` can retire.
6. **Comms and positioning design.**
7. **Echo sounding and backscatter, multibeam design, and the sonar
   equation.**
8. **Doppler**, with motion in the scene. Long term.

## Open questions

- Qt binding (settled by the spike).
- Ray tracing is planned for the sound speed page (layered profile,
  constant gradient per layer, so rays are circular arcs with exact travel
  times). Open: whether the simulation also uses it to bend paths and find
  eigenrays, or keeps straight paths with mean slowness.
- TEOS-10 converts practical salinity to absolute salinity using location,
  so profiles carry a position; for bench and lake use without one, a
  standard approximation is used and noted.
- How much of a page is usable from scripts: the models and workspace
  objects certainly; whether experiments too.
- License and repository name when it is split out.
