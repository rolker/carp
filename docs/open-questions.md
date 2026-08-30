# Open Questions

## Blocking the build

**~~Thruster count: 4 or 6?~~ Resolved by purchase — six ordered 2026-08-19.**
The successor question is the frame: **SimpleROV-4/5 or BlueROV1?**
SimpleROV-5 uses five of the six (one spare) and keeps the simplest possible
bring-up. BlueROV1 uses all six for full 6-DoF — including pitch for camera
aiming with a stock matrix, no ArduPilot fork. Wiring must now budget ~56 A
peak either way, and the propulsion/hotel battery split (ADR-014) is live.

**Housing diameter and camera mounting — see `housing-layout.md`
(Leaning: 6" single housing, option B).** Four options drawn and dimensioned;
6" resolves tube diameter, camera mounting, and whether pitch is real in one
decision. Two findings from the drawing: the LiPos sit side by side in a
154 mm bore rather than stacked, and the six ESCs ring the tube wall instead
of eating axial length. Still no pipe bought — the proposal is gated on five
measurements listed in that file, four of which are in unopened boxes.

**Sub-question now closed: the stereo baseline is 75 mm.** Two ~Ø70 flanges
span 145 mm against a 154.1 mm bore, leaving 4.5 mm each side. At 85 mm
centers they do not fit the bore at all; at 100 mm they exceed even the tube
OD. The "~75–100 mm" carried in this file and the bring-up checklist was
never a range. 75 mm sits inside the 60–120 mm band `prior-art.md`
recommends for 0.5–2 m work, so the constraint costs nothing optically.

**Pi software stack — see ADR-017 (Leaning: vanilla OS, not BlueOS).**
Both design reviews flagged this as untracked. The live sub-question is the
base image: Ubuntu 24.04 (native apt ROS 2, but the Arducam Pivariety camera
stack is packaged for RPi OS only) vs Raspberry Pi OS (cameras turnkey,
ROS 2 in Docker). The CSI/encode bench prototype decides — Ubuntu first,
timeboxed; it must land before Phase 3 software integration.

**Rigging geometry — needs a drawing, not a debate.**
Boat → downline clip → ROV means effective horizontal radius ≈ tether length
minus depth (~15 m − 5 m ≈ 10 m at the first site), and navigation.md
("clip to downline") vs bom.md ("to the boat") is still unreconciled. One
sketch resolves the working radius, the attachment point, and the tether
length to actually buy (reviews 1 minor 3 / 2 minor 1 & 6).

**Is this still a $500 build?**
It is not. Worth deciding explicitly whether the target is "cheapest thing that
works" or "capable inspection platform," because they diverge from here.

## Deferred, revisit after first water

**Pitch control for camera aiming.**
No longer requires an ArduPilot fork — with six thrusters on hand, the stock
BlueROV1 frame provides pitch (see the frame question above). Value is real:
no tilt servo, no dynamic seal, no extra penetrator.

**Hotel/propulsion battery split.**
Live now that six thrusters are ordered. See ADR-014.

**48 V hotel power down a spare tether pair.**
Would give near-unlimited endurance for the load that actually drains the pack.
Not yet evaluated against penetrator count and isolation complexity.

**VESC on the vertical axis.**
FOC gives smooth thrust through zero, which is the axis whose jitter shows up
in imagery. ~$60–100. Only worth it if depth-hold jitter proves visible in
footage.

**Surface buoy instead of kayak tether.**
ADR-009's preferred architecture. Needs a float, GNSS, battery, and a WiFi/LoRa
link. Big usability win — paddle away and leave it working.

## Needs measurement, not decision

- **Actual thrust** per U2 in both directions, on a scale. Specs are optimistic.
- **Actual hover power draw.** The entire endurance model rests on a 10–15%
  duty estimate that hasn't been verified.
- **Ambient light at the site.** Camera in a jar at 5 m, midday and overcast.
  Validates the no-lights posture (ADR-004) before it's built around.
- **Whether the bottom has texture.** Optical flow lives or dies on this, and
  it's site-specific. Test at Massabesic before building around it.
- **Where sidescan contact error actually lives** — layback and GPS-to-transducer
  offset are usually the bigger terms than the receiver.

## Questions for CCOM

This is a personal project first; none of these are dependencies. Worth asking
opportunistically.

- Are there spare Pixhawks, penetrators, or housings in a drawer somewhere?
  Labs accumulate these.
- Is there a project fit — e.g. as a student platform? Would strengthen the
  case for Project11 conventions, but doesn't gate anything.
- Access to a pool or tank for the acoustic calibration (known-distance
  measurement to zero out fixed DAC/ADC buffer offsets).
