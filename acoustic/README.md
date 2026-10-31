# Acoustic ranging — bench code

Standalone Python for the acoustic ranging tests in `docs/navigation.md`
(Method 4 and its proposed two-way variant). No ROS: a ROS node can wrap
this later. Dependencies come from apt only, the same system Python that
ROS uses:

```bash
sudo apt install python3-numpy python3-scipy python3-pyaudio python3-matplotlib
```

| File | What it does |
|---|---|
| `ranging_dsp.py` | Chirp, matched filter, arrival times. Arrays in, numbers out — no audio hardware |
| `wav_io.py` | 16-bit WAV read and write |
| `audio_io.py` | PyAudio: list devices, play while recording |
| `chirp_data.py` | Sending a few bytes as LoRa-style chirps: modulate and demodulate |
| `pinger.py` | Signals, ping designs, and one ping start to finish: output, recording, arrivals per event |
| `ping_gui.py` | Window to edit signals and ping designs, ping, and see the result |
| `loopback_test.py` | Stage 1: time of flight on one sound device |
| `plot_runs.py` | Plots of saved recordings: one ping in detail, or many side by side |
| `test_ranging_dsp.py` | Checks on simulated recordings: `python3 test_ranging_dsp.py` |
| `array_patterns.py` | Beam patterns of candidate topside arrays for `docs/topside-head.md`: `python3 array_patterns.py` |

## Stage 1: one dongle, loopback plus a disc pair

Wiring: the output channel drives the transmit disc, and a small copy of it
goes through a resistor into the mic input alongside the receive disc. The
recording then holds the chirp twice — when it was sent and when it arrived
— and the gap is the time of flight.

```bash
./loopback_test.py --list                       # devices and sample rates
./loopback_test.py --input-device N --output-device N --save runs/run1.wav
./loopback_test.py --wav runs/run1.wav          # re-analyse a saved run
./loopback_test.py --simulate 1.5               # no hardware: made-up echo at 1.5 m
./loopback_test.py --input-device N --output-device N --count 50 --save runs/series1/p.wav
./plot_runs.py runs/run1.wav                    # waveform, matched filter, spectrum
./plot_runs.py runs/series1/                    # the pings side by side
```

**Recordings go in `acoustic/runs/`**, which is git-ignored: it survives a
reboot (unlike `/tmp`) and stays out of the repo. Folders are created as
needed.

Each saved recording gets a `.json` beside it with the chirp settings, so
re-analysis and plots use the chirp that was actually sent.

The default chirp is 2–20 kHz over 20 ms. Bandwidth sets how close two
arrivals can be before they merge (the script prints the figure): a disc
that only passes a few kHz in air cannot separate short paths.

## Ping window

```bash
./ping_gui.py                 # default sound devices
./ping_gui.py --simulate      # no sound card: made-up echoes
```

**Signals** (left, top) is a list of chirps: name, start and end frequency,
length and level. A lower end frequency makes a down-chirp; equal
frequencies make a tone. Select one to load it into the boxes, then
Update, or change the name and Add to make a new one.

**Ping design** (left, below) is a list of events: an output channel, a
signal, and when it fires in ms after the start of the ping. Repeat a
signal on a channel or chain several by adding rows. All events go out in
one buffer, so their spacing is exact to the sample. Load and Save keep
designs as JSON, by default in `designs/`.

**Ping** sends the design once; **Continuous** keeps going. The table and
the top plot show one row and one trace per event: when its first arrival
came, the path difference, its level, and how far it stands above the
noise. Time zero is the loudest event's first arrival. Two more views can
be ticked on: **Recording** (waveform and spectrum) and **Echogram** (one
column per ping, time running down, for the first four events).

Events are told apart by signal and by timing. Give events that share a
signal at least ~60 ms between them, and more in a reverberant room.
Signals in separate bands can fire at the same instant. An up-chirp and a
down-chirp over the same band cannot: they did not separate on TV speakers
and a laptop mic (2026-10-11: 10 dB apart at best).

`designs/` has starting points:

| Design | What it sends |
|---|---|
| `left-then-right.json` | The same 2-20 kHz chirp on the left, then the right 150 ms later |
| `split-bands.json` | 2-9 kHz on the left and 11-20 kHz on the right, at the same instant |
| `split-bands-swapped.json` | The same with the bands swapped between the channels |
| `timing-check.json` | One chirp three times on the right, 150 ms apart. The second and third should arrive at exactly 0.000 ms; anything else means the sound path is not keeping time |

The bottom-left tabs hold three more tools. Each has a tick box in the
top bar that shows or hides its chart, and each saves its recording and
numbers under `runs/`.

**Noise** records with nothing playing, for the time you set. The left
chart is the typical background level against frequency, per Hz and per
1 kHz band; it uses the median over time, so a single bang does not raise
it. The right chart shows the same recording over time, where bangs,
whines and anything intermittent show up. Use it to choose a quiet band,
and to compare one place or one mic with another.

**Data** sends the text as chirp spread spectrum (the scheme LoRa uses) on
one channel and decodes what the microphone heard. Every symbol is one
chirp across the band, and the data is in where the sweep starts.
`spread` sets the steps across the band per symbol (2 to the power
`spread`), and `bits` how many bits each symbol carries; leaving `bits`
two below `spread` keeps the start points four steps apart, which absorbs
small shifts from echoes. A message is six plain chirps, two reversed ones
to mark the start, then a length byte, the text and a 16-bit checksum. The
status line gives the decoded text, whether the checksum passed and how
many bits differ from what was sent. The charts show the tone of each
symbol (echoes appear as fainter second tones) and how far each stood
above the rest. It detects errors but does not correct them. In
simulation it decoded with noise 10 dB above the signal and with an echo
stronger than the direct sound; a 5 ms gap mid-message, as the WSL bridge
makes, breaks it and the checksum catches that.

**Sweep** answers "which band does this speaker,
room and microphone pass best?". It sends a run of short chirps, each one
`step` wide, stepping up through the range on the left, the right, or each
in turn (about 1.2 s per channel for 2-21 kHz in 1 kHz steps). The chart
shows each band's level and its noise floor; hollow markers were not heard.
The shaded **suggested band** is the widest unbroken run of bands that
every swept channel passes within 10 dB of its best. "Add suggested band to
signals" makes a chirp covering it. Each band is found by its own filter,
not by its place in the sequence, so the sweep also works on WSL. Every
sweep is saved to `runs/sweep-<date>-<time>/`. A sweep only describes the
arrangement it was run on: move the microphone and it changes.

The second row picks the input device, the output device and the sample
rate (only rates both devices accept are offered). Press **Refresh
devices** after plugging a sound device in. On WSL the list only ever
holds `pulse` and `default`: both follow whichever input and output are
the defaults in Windows, so switch devices there. One output device and
one input device per ping for now.

"Save pings" writes each recording to `runs/gui-<date>-<time>/`, with the
design and the results in the `.json` beside it.

The dividers between the panels drag: side panel against the plots, signals
against the ping design, and the results table against the plots. The
toolbar under the plots zooms (magnifier, then drag a box), pans, steps
back and saves an image. A zoom on the top plot is kept from ping to ping;
**Reset zoom** returns to the full view.

## Bench hardware (2026-10-11)

Built so far: the 20 mm transducer holder (below). Drawings:
[twelve-pocket ring](https://claude.ai/artifact/99bWLWpf5B9tmFNcdqrJaM),
[flat cross with 45° receivers](https://claude.ai/artifact/PXHUPA8RArRitkF7W4AGMo)
(private pages on Roland's account).

**Measured, 20 mm disc (Roland, 2026-10-11):**

| | mm |
|---|---|
| Brass diameter | 20 |
| Ceramic diameter | 15 |
| Brass thickness | 0.22 |
| Thickness at the ceramic (brass + ceramic) | 0.46 |
| Thickness at the solder on the ceramic (the thicker joint) | 1.14 |
| Outer edge to the far end of the solder | 9.1 |
| Solder width, across the radius | 5 |
| Wire diameter | 0.8 |

So the ceramic is about 0.24 thick and the bare brass rim is 2.5 wide.
The joint on the ceramic stands 0.68 above it; the joint on the brass is
lower. 9.1 in from the edge is 0.9 short of the centre, so the solder runs
nearly a full radius. The wire leaves at one edge of the 5 mm width, not
from its middle. Not measured yet: capacitance.

**Built: 20 mm transducer holder (Roland, 2026-10-11):**

Roland's Onshape part (Transducer Holder, document `carp`), printed three
times on the Centauri Carbon 2 in Elegoo PLA+, 0.16 mm layers, flat with
the clips up, no supports, about 6 minutes and 1.5 g each. The third print
**fits the disc "pretty good"**. Dimensions read from the STL exports:

| | mm |
|---|---|
| Outer diameter | 26 |
| Thickness | 4 (3 body + 1 clips) |
| Pocket diameter | 20.04 |
| Recess depth | 0.32 |
| Through hole | 17 |
| Retention clips | three, 4 wide, 1 thick, overhanging the pocket by 1; one at the wire side and one 90° either side of it |
| Solder relief | 1 deep below the pocket floor; 6 wide as test-fitted, **8 wide from here on** |
| Wire hole through the wall | 2 wide, 1 tall, rounded, under the wire-side clip |
| Access groove into the wire hole | 1.4 |

- The disc goes in past the clips and the pocket is not too tight at
  20.04: 0.02 a side was enough on this printer and filament. The earlier
  agent proposal of Ø20.4 with glue dots was not needed.
- Print 1 had a 0.56 recess and a 1.0 access groove; the disc fitted but
  the wires would not go into the groove. Print 2 (0.32 recess, 1.4
  groove) is the one that fits.
- The 8 mm solder relief is in the model and in
  `cad/prints/transducer_holder_20mm.stl`, but has **not been printed
  yet**; the tested print had 6.
- Ø17 clears the 15 ceramic by 1 all round and leaves 1.5 of brass rim on
  the ledge. The ceramic (0.46 total) is thicker than the recess but sits
  inside the clips' reach.

**Decided (Roland):**

- Air-scale the mounts: sound is ~4.3 times faster in water, so divide the
  water size by 4.3. Start with the equivalent of 1 m topside and 0.5 m on
  the ROV: **230 mm and 115 mm** between opposite discs.
- First mounts for the **20 mm discs**, with a **printed foot**; separate
  pieces to assemble are fine.
- Onshape: one transducer-holder part, configured per piezo size.

**Proposed, not approved:**

- Layout: four transmitters and two receivers per end, flat. Each transmit
  pair on one dongle (left and right out), so its timing is exact; one
  receiver per dongle. The twelve-pocket ring (a pocket every 30°) takes
  transmit pairs at 90° or 60° on one print — Roland: "looks good".
- The topside ring at **220 mm**, not 230: a 230 ring is 256 across and
  cannot fit the 256 bed. Alternative: print 230 in two halves. Open.
- Stand: cross or ring on a post and base, centre about 300 mm above the
  table so the table reflection separates from the direct sound.
- A short boom for a third axis was discussed and left out for now.

**Circuit, per dongle (proposed):**

```
 Left out  --[100 ohm]--+---- transmit disc ---- GND
                        |
                     [1 Mohm]  loopback
                        |
 Mic in    --[1 uF]-----+---- receive disc ----- GND
```

100 ohm isolates the output from the disc's capacitance. 1 Mohm feeds a
small copy of the output to the mic side (go down to 470 k or 100 k if it
is too faint). 1 uF keeps the mic pin's DC bias off the disc and the
output. Right out gets the same branch, with its own 1 Mohm to the same
mic junction.

**On arrival:** TRRS pinout by multimeter; mic bias voltage; sample rates
(`./loopback_test.py --list`); disc capacitance, lead diameter and solder
blob height; turn off any automatic gain; then `designs/timing-check.json`
through the loopback alone, before any disc is connected.

**Arrived (2026-10-12), first look with two dongles plugged in, nothing
connected to them:** "Generic iStore Audio", USB `001f:0b21`, full-speed USB,
48 kHz only, 16-bit, stereo out and mono in. The mixer has only playback
switch and volume and mic capture switch and volume: no automatic gain to
turn off, no mic monitoring. All of them report the same USB serial
number, so a dongle is known only by the USB port it is in: label them and
keep each in its socket (`../acoustics_lab/tools/duplex_check.py --list`
shows the port of each). The desktop's sound server picks them up as extra
outputs and inputs without making them the default. The USB descriptors
list the output as adaptive (clocked from the computer's USB frames) and
the input as asynchronous (the dongle's own crystal); whether the two stay
locked on one dongle, which the fixed turnaround idea needs, is the first
thing the loopback offset test should show. The checks above still apply;
the hardware tools now live in `../acoustics_lab/` (`tools/duplex_check.py`,
`docs/hardware-layer.md`).

**TRRS screw-terminal cable, buzzed out (Roland, 2026-10-25), one cable:**

| Terminal label | Plug contact |
|---|---|
| L | tip |
| R | ring 1 (next to the tip) |
| V | ring 2 |
| Grd | sleeve |

So the labels follow the plug, but they assume the older OMTP layout (mic
on ring 2, ground on the sleeve). Most current gear is CTIA, with **ground on
ring 2 and the mic on the sleeve**: on a CTIA dongle the terminal marked
"V" would be ground and "Grd" would be the mic. **Measured the same day: the dongle is CTIA.** With the cable in a dongle
plugged into the computer, the meter read **+3.72 V on "Grd" relative to
"V"** (black on V, red on Grd, no load): the mic bias is on the sleeve.
Wire the bench by this, **not by the printed labels**:

| Terminal label | Plug contact | Dongle signal |
|---|---|---|
| L | tip | left out |
| R | ring 1 | right out |
| V | ring 2 | **ground** |
| Grd | sleeve | **mic in** (+3.72 V bias, open circuit) |

Relabel the "V" and "Grd" terminals (tape) on every cable before wiring.
The 1 µF in the circuit below keeps the 3.72 V off the discs and the
outputs. One cable and one dongle measured; the other three cables not yet
buzzed out, and the other dongles assumed the same until checked.

### First loopback offset test (2026-10-25) — no signal recorded yet

**Setup.** Pi 5 (`carp`), dongle on USB port `4-2` (card 0, "iStore
Audio"), no desktop sound server on it. Loopback on the breadboard, no
discs:

```
 L ──[100 Ω]──●A──[100 kΩ]──●B──[1 µF]──●── Grd terminal (mic in, sleeve)
 V terminal (ground, ring 2) ── ground rail      R ── not connected
```

100 kΩ instead of the 1 MΩ in the proposed circuit above: with no disc on
node B, 1 MΩ into the mic input's low resistance would be very faint. The
1 µF is a ceramic marked 105 that measures 0.83 µF.

**Mixer** (`duplex_check.py --device 4-2 --mixer`): PCM Playback Switch on,
PCM Playback Volume 11370 (of 0..11520), Mic Capture Switch on, Mic Capture
Volume 8191 (of 0..8191, the maximum). No AGC or mic monitor controls.

**Runs** (`duplex_check.py --device 4-2 --offset-test --minutes 1 --channel
left`, −20 dBFS), raw input kept on the Pi under
`acoustics_lab/runs/hardware/`:

- `20261025_184636_Audio_offset`: 93 of 120 pings not found; arrival
  **−94 dBFS**, below one 16-bit step, so effectively silence. The figures it
  printed (offset 3990 samples = 83 ms, spread ±4.2 samples, clock −65 ppm
  against the system clock, no dropouts) are not meaningful with no signal.
- `20261025_190415_Audio_offset`: only 2 of 120 usable.

**Fault-finding with the DS1052E** (ground clip on the ground rail):

- Bias on the Grd terminal: present (+3.72 V measured earlier with the
  meter), so the cable reaches the dongle's mic contact.
- Chirp bursts seen at node A. The 20 ms chirp every 0.5 s is awkward to
  trigger on; a continuous tone is easier:
  `speaker-test -D plughw:0 -c 2 -t sine -f 1000`.
- With that tone: **node A about 2.5 V peak-to-peak** (playback volume
  11370). Node B barely above the scope's noise (×10 probe, ~15–20 mV).
  With the capacitor lifted, **node B rises to 2.36 V**: the 100 kΩ is
  fine, and the mic input is a low-resistance load (likely 1–2 kΩ),
  which divides the 2.5 V down to roughly 25–50 mV at the mic. **The signal
  reaches the mic input**, and that much should record loudly at maximum
  capture gain.

**Answered below:** the dongle records its mic, but mutes it while its
left output plays. The plan that followed at the time:

1. With the tone playing, record from the same dongle and print the level:
   `arecord -D plughw:0 -f S16_LE -r 48000 -c 1 -d 5 /tmp/tone.wav`, then
   peak and RMS in dBFS (numpy, `wave`).
2. Loud (around −30 to 0 dBFS): the dongle hears, and the problem is in how
   `duplex_check` plays or finds the chirp: compare the two raw `input.wav`
   files above.
3. Near −90 dBFS: the dongle is ignoring its mic, likely mic detection (a
   headset jack that stays muted until the mic line is loaded). Add **4.7 kΩ
   from the Grd terminal to the ground rail** (bias should drop to about
   1–2 V) and record again; if the level then lands below −40 dBFS in the
   offset test, lower the 100 kΩ to 47 k or 22 k.
4. Once a ping arrives between about −40 and −6 dBFS, rerun the 1-minute
   offset test, then `--minutes 5`, then the other dongles.

To see the small signal at Grd on the scope: Acquire → Average (16–32), BW
Limit on, AC coupling.

### Found (2026-10-25, evening): the dongle mutes its mic while L plays

Tests by recording a tone played on the same dongle and then from a
second dongle (card 3, port `2-2`, its playback volume raised from 6400 to
11370 to match). Raw recordings were in the session scratchpad, not kept.

- **Step 1 (tone on L, record):** the 1 kHz came back at −106 dBFS, with
  only low-frequency junk (18–130 Hz) and a floor so low a quarter of the
  samples were exactly zero. **Step 3 (4.7 kΩ from Grd to ground):** no
  change, and not the cause; to be removed for the tests below.
- 300 ms bursts on L came through at −56 to −59 dBFS for their first
  ~100 ms, then vanished.
- **Second dongle's L into this dongle's mic** (same 100 Ω / 100 kΩ /
  1 µF network, grounds joined): steady 1 kHz at −27 dBFS, settling to
  −42 dBFS within a second (a ~15 dB slow gain change on steady tones) and
  staying there. 300 ms bursts at −25 dBFS throughout. 20 ms chirps 42–52 dB
  above the matched-filter noise.
- With the second dongle still feeding the mic: **this dongle playing
  1.5 kHz on L muted it** (about −94); playing 1.5 kHz on R, or silence,
  left it open.

So the mic is shut while there is sound on the left output, whatever the
sound: speakerphone-style ducking, not noise suppression and not a canceller
matched to the signal. The right output does not trigger it. There is no
mixer control for it. **On these dongles, only R can transmit while the
same dongle listens**, which rules out two transmitters per dongle (L and
R) in the proposed layout.

**Loopback moved to R** (`R ──[100 Ω]──[100 kΩ]──[1 µF]── Grd`, L not
connected). Dongle 1's own R tone arrives at −27 dBFS, the same as from
the other dongle; R bursts come through whole.

Offset test, `duplex_check.py --device 4-2 --offset-test --minutes 1
--channel right` (`runs/hardware/20261025_201557_Audio_offset`):

- **120 of 120 pings found**, none missed, no dropouts.
- Offset 3994.87 samples (83.23 ms), spread **0.86 sample (18 µs, ~6 mm
  of air)**, worst ±3.2 samples. Drift 0.1 ppm over the minute: input and
  output stay locked on one dongle. Device clock −37.6 ppm against the Pi.
- It printed "ping arrives weak (−83 dBFS)", but that figure is on the
  matched-filter scale. Measured in the recording: ping peak about
  −63 dBFS above 1.5 kHz against −100 dBFS between pings, ~35 dB SNR.
- **The mic path cuts off above about 8 kHz.** Spectrum of the averaged
  ping (the test's 10 ms 2–20 kHz chirp), relative to its best band: 1–3
  kHz −31 dB, 3–5 −14, 5–7 0, 7–9 −27, above 9 kHz about −43. The chirp
  has a full Hann taper, so it was sent strongest near 11 kHz and weak at
  both ends: the fall above 8 kHz is the dongle, the weak low end is
  partly the taper. The chip probably samples the mic at 16 kHz
  internally.

**Chirp kept to 3–8 kHz** (`duplex_check.py` gained `--f0`/`--f1`; the
band is saved with each run and used again by `--reanalyse`). Same
loopback, level and settings, `--f0 3000 --f1 8000`:

| Run | Chirp | Found | Offset mean | Spread | Worst | SNR |
|---|---|---|---|---|---|---|
| `20261025_201557` | 2–20 kHz | 120/120 | 3994.87 | 0.86 | ±3.2 | ~35 dB |
| `20261025_202321` | 3–8 kHz | 120/120 | 3972.81 | **0.033** | ±0.17 | 54–60 dB |
| `20261025_202444` | 3–8 kHz | 120/120 | 4041.09 | **0.028** | ±0.11 | |

Offsets in samples. With the energy where the dongle passes it, the spread
is 0.6 µs (0.2 mm of air) and drift 0.003 ppm. **But the offset changes
each time the stream opens** (by 68 samples between the two 3–8 kHz
runs), while it holds to a few hundredths of a sample within a stream. A
fixed turnaround therefore has to be measured on each stream open, which
the loopback copy in every recording already gives.

Next: `--minutes 5`, then the other dongles (each one's R, ducking and
band assumed the same until checked).

## UCA222 bench results (2026-10-30)

Two boxes on the Pi 5: box 1 on USB port `4-2`, box 2 on `2-2`. Electrical
only, no discs. Each link is a direct wire with grounds joined, through the
RCA screw plugs; the unused input left open. Mixer at PCM 108 (−20 dB), the
only control ALSA shows: no capture gain or AGC. Offset runs are in
`acoustics_lab/runs/hardware/` (`*CODEC*_offset`), sweeps in `runs/sweep-*`;
the ducking and cross-box recordings were in the session scratchpad, not
kept; their scripts are here.

**Loopback, 2–20 kHz chirp, −20 dBFS, `--rate 48000`.** Every run with the
wire on the input being recorded found all its pings, with no dropouts or
clipping. Each path had three 1-minute runs and one of 5 minutes, except
box 1 L, which had four 1-minute runs and one of 5 minutes in the default
one-channel mode:

| Path | Offset (samples) | Worst deviation (samples) | Level |
|---|---|---|---|
| Box 1 L → L | 3199.76–3328.75 | 0.0024 | −29.7 dBFS |
| Box 1 R → R | 3199.51–3200.52 | 0.0031 | −29.65 to −29.76 dBFS |
| Box 2 R → R | 3199.42–3200.82 | 0.0021 | −29.82 to −29.91 dBFS |
| Box 2 L → L | 3199.57–3201.17 | 0.0018 | −29.78 to −29.87 dBFS |

- **Within a stream the offset holds to about 0.003 sample** (60 ns), against
  0.03 on the dongle, with no drift: input and output stay locked.
- **The offset changes on each stream open**, so the loopback copy is still
  needed on every open. The 12 stereo runs all fell between 3199.4 and 3201.2,
  moving up to about 1.8 samples. A jump of about 128 samples, to near 3328,
  appeared only with the one-channel input (3 of 6 runs). Too few runs to
  call that a rule.
- Noise floor about −88.5 dBFS on both boxes, about 1 LSB. About 30 dB of
  headroom was left at these levels.

**Bandwidth.** Sweep on box 1 L → L: all 19 bands 2–21 kHz heard, within
**0.4 dB**. In `sweep-20261030-185742` the 16–17 kHz band shows about 5 dB
less SNR at a normal level; not checked whether it repeats. The other three
paths have no sweep: their chirp spectra are symmetric about 11 kHz to within
0.5 dB where looked at (box 2 both channels), which is indirect.

**No ducking on any input.** A steady 1 kHz from the other box, recorded in
stereo while this box played 5 kHz at −6 dBFS on L, R, both, and nothing:

| Input | Tone level | Variation, 100 ms blocks | Separation from the other input, 1 kHz |
|---|---|---|---|
| Box 1 L | −29.70 dBFS | under 0.01 dB | ≥ 92 dB |
| Box 1 R | −29.67 dBFS | 0.01 dB | ≥ 92 dB |
| Box 2 L | −29.73 dBFS | under 0.01 dB | ≥ 94 dB |
| Box 2 R | −29.83 dBFS | under 0.01 dB | ≥ 93 dB |

So **two transmitters and two receivers can share one box**, which the
dongles ruled out. Separation is limited by the noise floor, at 1 kHz only,
with the other input open. The box's own 5 kHz reaches its inputs at −86 to
−95 dBFS with its outputs unloaded, about 60–65 dB below what the output
sends; a disc load may change that. Closing the playback stream leaves a
click on both inputs: −55 dBFS on box 1, −49 dBFS on box 2.

**The two boxes share a clock on one computer.** Cross-wired (box 2 L out →
box 1 L in, box 1 R out → box 2 R in), both playing and recording at once
for 5 minutes with `aplay` and `arecord`, a 1 kHz tone each way:

- Clock difference **0.002 ppm**, equal and opposite in the two directions
  (+0.002 and −0.002), and in each half of the run.
- Timing wander 0.45 µs rms, worst 1.02 µs; biggest 1 s step 0.116 µs.
- No overruns reported, level steady to two decimals.

Two free-running crystals would not agree that closely, so both are
presumably locked to the host's USB frames. From memory the PCM2902 clocks
itself that way; not confirmed, and the input's "asynchronous" descriptor
does not fit it. **This will not carry over to boxes on two computers**, so
ROV and topside need that difference measured.

**The "device clock against the system clock" figure in `duplex_check.py` is
not reliable.** It reads about +130 ppm at 1 minute, −5 to −13 ppm at
5 minutes and +540 to +600 ppm at 15 s, on either box. That fits a fixed
start-up error of about 9 ms (inferred); the tool is not fixed.

**Added:** `duplex_check.py --input left|right` opens the input as stereo
and records that channel. Without it, the one-channel mode hears L in only
(0 of 30 pings on either box with the wire on R in).

**Not done:** noise and crosstalk across the chirp band with an input
shorted; `duplex_check` on both boxes at once (the cross-box run used `aplay`
and `arecord`); one box each on two computers; the chip marking; any disc,
including through the JFET buffer. The 12–13 LSB peak on the unwired input in
the cross-box run was not looked into.

**Next (proposed 2026-10-30, not started): first disc-to-disc test in air.**
Start without the JFET buffer: L out through 100 Ω to the transmit disc, L out
also to R in as time zero, receive disc straight into L in. Disc capacitance
and the line input's resistance set a high-pass corner (rough guess 2–8 kHz,
neither measured), so measure the capacitance first. Build the buffer only if
that band or level falls short. Mount the discs face to face and parallel,
230 mm apart (0.67 ms, 32 samples), about 300 mm above the table, held by
the rim on separate supports, with drive and receive wires apart. Prove it is
sound: the arrival moves with spacing and drops behind foam or folded cloth.
Start at −20 dB mixer and −20 dBFS and raise in steps. `loopback_test.py`
expects the copy mixed into one input, so it needs a small stereo change. Scripts for
the ducking and cross-box runs: `uca222_ducking.py`, `uca222_cross_clock.py`.

## Ideas for later (Roland, 2026-10-11) — not built

- Top-level tabs for the tools: Noise and Data as their own tabs, not
  squeezed under the ping design.
- An Advanced tab for the values now fixed in the code (lead-in, settle,
  search window, detection threshold, speed of sound, chirp fade, sweep
  chirp length, data preamble and fades).
- Several devices at once. For data: decode the same message on several
  selected inputs and compare how they do.

## On WSL

Works for trying the code, with ALSA pointed at the Windows sound bridge
(`libasound2-plugins` and a `~/.asoundrc` that makes `pulse` the default
device). `--list` then shows `pulse` and `default`. Tested 2026-10-11:
chirps played through a TV on HDMI and heard by the laptop mic, with
arrival times repeating to a few microseconds from ping to ping.

Not for measurements across time: the bridge does not keep the spacing
between events. `timing-check.json` came back 5 to 25 ms late, in steps of
about 5 ms, whatever the block size (2026-10-11). Events sent at the same
instant are not affected, and neither are the reflections of one chirp, so
`split-bands.json` gives steady left-right differences. The bridge also
converts sample rates, and there is no loopback, so time zero is the first
sound heard. Real tests belong on the Pi or the netbook.

**Status (2026-10-11):** processing and plots are tested on simulated
recordings, and pings on the live path through the WSL sound bridge. The
noise and data tools have only been run simulated. Nothing has
been run on the USB dongles or with the loopback wired in yet.
