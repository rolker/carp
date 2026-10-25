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
"V" would be ground and "Grd" would be the mic. Which one the dongle uses
is the next measurement: plug the cable into a dongle and measure DC
between V and Grd. The mic bias (a few volts) is positive on the mic
contact. The other three cables not yet checked.

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
