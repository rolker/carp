# Topside acoustic head — multibeam, tracker and acoustic comms (idea)

**Status: idea (2026-10-30), Roland's, for after ROV 1.0 and Tracking 1.0.**
Nothing bought, nothing decided, no ADR. The beam-pattern and cost numbers
below are an agent's computations and estimates, not measurements; the
patterns come from `acoustic/array_patterns.py`, which anyone can rerun.
The one part of this document that matters now is §2, the compatibility
contract with the ROV end being built for Tracking 1.0.

## 1. The idea

The topside tracking layout in `navigation.md` Method 4 is two transmitters
on one axis and two receivers on the other: a two-element Mills cross. A
multibeam echosounder is the same cross with both arms filled. So the
tracking head and a multibeam are one device at different element
densities, and a single head on the kayak could:

- **image** the bottom and structure around the downline in a 2D grid of
  beams every ping, with the ROV visible in the water column;
- **track** the ROV by direction (receive beamforming on its reply chirp)
  and range (two-way timing against the ROV's 2 × 2), with a transmit beam
  steered at the ROV;
- **carry telemetry** (acoustic comms) in the reply chirps, using the
  LoRa-style modulation already in `acoustic/chirp_data.py`.

Reference point: the Simrad ME70 fisheries multibeam does all of this with
800 elements in a fully populated planar array, each element transmitting
and receiving, forming up to 45 steerable split beams per ping. This
document is about what a 32-channel, piezo-disc version of that trade can
do, and what it cannot.

One head, one microcontroller, one PoE cable. The digitizer lives at the
array, so analog leads are centimetres long, and only Ethernet comes back
to the laptop or Pi.

## 2. Compatibility contract with Tracking 1.0

The ROV end for Tracking 1.0 is a 2 × 2: two transmit discs and two
receive discs on one UCA222 (stereo out, stereo in, 48 kHz), with the
loopback and the measured or scheduled turnaround time (TAT) from
`navigation.md`. For a future topside head to interact with that ROV
unchanged, Tracking 1.0 should fix and record:

| Item | Why the head cares |
|---|---|
| **Chirp band, below ~20 kHz** | The UCA222 samples at 48 kHz. The head's element pitch is set by the top of the band (37 mm at 20 kHz in water) |
| **Which chirp means "reply to this"** | The head will also send wide imaging pings the ROV must ignore. Up-sweep vs down-sweep, or distinct bands, decided once |
| **The ROV's reply chirps, one per transmitter, distinguishable** | The head beamforms each reply separately; two distinguishable chirps from the ROV's two transmitters is what the two-way layout already proposes |
| **Fixed TAT and the reply window it creates** | A TAT of ~200 ms puts the reply well after the imaging echo window (13 ms round trip at 10 m), so replies never collide with bottom returns |
| **Loopback on both ends** | The head gives its loopback a dedicated channel; the ROV mixes it into its inputs as now |
| **ROV 2 × 2 geometry** | Transmitter and receiver baselines on the ROV, in the vehicle frame, so the head can interpret the two replies |
| **Telemetry payload format**, if any | Whatever `chirp_data.py` settles on for the ROV's reply becomes the head's comms format |

None of these constrain Tracking 1.0 beyond writing them down. Anything
not fixed here can be changed later on both ends together.

## 3. Candidate geometries

All at half-wavelength pitch (37 mm at 20 kHz in water, 34 mm at 5 kHz in
air: nearly the same plate serves both). Ideal array factors, broadside,
uniform weights. "Leak beyond N°" is the strongest response to a target more
than N° off the beam axis. `python3 acoustic/array_patterns.py` reproduces
the table; see its docstring for what is left out.

| Geometry and processing | Channels | Pings per 2D frame | Beamwidth | Leak beyond 20° | Leak beyond 30° |
|---|---|---|---|---|---|
| 8 × 8 Mills cross, arms multiplied, wide transmit | 15 | 1 | 12.6° | −13 dB | −16 dB |
| 4 × 4 filled, transmit and receive | 16 | steered | 18.7° | −14 dB | −23 dB |
| Hybrid: 8 × 8 cross with a filled 4 × 4 core, core transmits, thick arms multiplied | 24 | steered | 13.2° | −30 dB | −39 dB |
| **Cored cross: 5 × 5 core, 11-wide × 5-tall arms, core transmits, thick arms multiplied** | **31** | steered | **10.0° × 12.6°** | **−37 dB** | **−37 dB** |
| Cored cross: 5 × 5 core, 9 × 7 arms, same processing | 31 | steered | 10.9° × 11.8° | −41 dB | −41 dB |
| Square ring, 9 per side, all transmit, sides multiplied | 32 | steered | 4.9° | −24 dB | −24 dB |
| Filled 8 × 8, transmit and receive (for comparison) | 64 | steered | 9.2° | −26 dB | −33 dB |

What the table says:

- **Processing matters as much as geometry.** Simply adding all elements of
  a cross or ring gives a poor pattern (−6 dB sidelobes for the ring). The
  Mills cross multiplication is what makes sparse layouts work, and giving
  each arm the core ("thick arms") is what removes the cross's ghost arms.
- **The qualitative jump is 16 → 24 channels**, where the core turns ghost
  arms at −13 dB into a clean image at −30 dB. 24 → 32 is incremental.
- **The ring is the resolution option** (5° beams from 32 channels) at the
  cost of near-in lobes about 15 dB down that never fall away, and of
  sensitivity to element gain and phase errors, which cheap discs have.
- **The cored cross is the dynamic-range option** and the forgiving one, and
  it is the recommendation. The 11-wide axis goes across the kayak.
- **The 32nd channel is the transmit loopback**, which the timing scheme
  needs anyway.

## 4. Why tracking does not drive the design

Bearing precision from a cooperative chirp scales with aperture and SNR. A
0.3 m cored cross gives about 0.5° at 30 dB SNR, about 9 cm at 10 m; the
original 1 m tracking baseline would give about 0.1°. A hobby-grade IMU on
a rigid pole holds roll and pitch to about 0.5° and heading to 1–2°, and
every degree of unsensed kayak motion is a degree of bearing error. So the
array is not the limit on tracking, the IMU is, and the channels can go to
imaging. Shallow-water bounces are also separable in time: the bottom-bounce
path to a mid-water ROV is metres longer than the direct path, milliseconds
at a chirp whose resolution is a tenth of a millisecond.

The steered transmit beam still earns its keep: the ROV's receivers are
bare discs on a line input, and the 14 dB of directivity from a 5 × 5 core
is spent on that downlink.

## 5. Hardware sketch

- **Digitizer:** Teensy 4.1 (two TDM audio inputs, 32 slots at 48 kHz,
  native 100 Mbps Ethernet). Four 8-channel ADCs: AD7606 modules (16-bit,
  200 ksps, bipolar inputs, shared convert-start) avoid a chip-level design;
  audio ADCs on a custom board are cheaper per channel.
- **Front end:** one buffer per channel (op-amp or JFET source follower),
  AC coupling, protection diodes, on a small 4-layer board.
- **Transmit:** the 25 core elements, each a logic-level MOSFET from a
  Teensy pin with back-to-back 1N4148 pairs as a passive transmit/receive
  switch. Steering is eight to twenty-five delayed digital bursts; a
  frequency-swept square wave is the chirp and the disc's resonance rounds
  it. Arm-tip elements are receive-only.
- **Link:** UDP frames with a sequence number and sample counter over PoE.
  Beamforming on the Pi or laptop, not on the Teensy.
- **Timing:** loopback channel for time zero. Optional later: a 1 PPS on a
  spare tether pair, or IEEE 1588 on the Teensy's MAC, which would turn
  two-way ranging into one-way.
- **Transducers:** 27 mm potted discs at 37 mm pitch; 31 needed, 20 in hand.
- **Plate:** about 0.4 × 0.25 m with a 19 cm filled centre, printed in two
  pieces, IMU mounted on the plate.

## 6. Modes and ping schedule

1. **Imaging ping.** Wide chirp from one core element; all beams from one
   recording by thick-arm multiplication. A few hertz.
2. **Tracking ping.** The core steered at the last ROV fix, with the "reply
   to this" chirp. The ROV replies after its fixed TAT; the reply lands
   after the imaging echo window and is beamformed, so the ROV appears in
   the water-column display at its range and bearing.
3. **Comms.** Telemetry rides in the reply chirps. Rate is a few bytes per
   reply; the head's receive gain is what makes it reliable.

## 7. Channel count, cost and the first step

| Channels | Hardware | Parts, air bench |
|---|---|---|
| 8 | No PCB; Teensy + four PCM1808 boards, or a UMC1820 off the shelf | $120–180 or $229 |
| 16 | PCB and TDM already needed; coarse beams or ghosts | $200–300 |
| 24 | Three ADC boards; the performance knee | $280–450 |
| 32 | Four boards; the Teensy's limit; the cost-per-channel knee | $310–600 |
| 64 | Two digitizers with a shared clock, or an FPGA | $650–1,100 |

Fixed costs dominate (Teensy, board, housing, firmware, hours); marginal
channels are $8–12 each, so within one Teensy build to 32. Past 32 is a
second digitizer and a sync problem. Water adds potting and a housing for
the digitizer at the array, roughly $100.

**First step, before anything is ordered:** the 8-channel multiplexed
prototype. A CD4051 in front of each of 8 channels covers 32 element
positions in 4 pings on a static bench scene, coherent through the
loopback, for about $8 of switch chips. It produces the patterns in §3 on
a wall and a pipe with real discs, or shows that they do not survive disc
variation. It cannot track a moving ROV; that needs all channels in one
ping.

## 8. What must be measured first

- A bare disc hearing a chirp from another disc across a room. The 42–52 dB
  figures from 2026-10-25 were electrical loopback. Electret capsules are the
  fallback receiver for the air bench if discs are too deaf in air.
- Disc-to-disc sensitivity and phase spread, which sets how much sidelobe
  performance survives without calibration.
- Ring-down time of a potted disc, which sets the minimum range.
- Whatever the UCA222 bench shows (arriving 2026-10-31): bandwidth, offset
  stability, crosstalk between its two inputs.
- Whether a line input with a JFET buffer is sensitive enough, or the
  mic-preamp class of input is needed.

## 9. Not in scope here

Dates, a parts order, the ROV-side 4 × 4 that was considered and set aside
in favour of the 2 × 2 on a UCA222, and any change to Tracking 1.0 beyond
recording the items in §2.
