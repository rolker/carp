# Open Questions

## Blocking the build

**Thruster count: 4 or 6?**
Four keeps the budget near $500 and uses the stock SimpleROV-4 matrix with a
free upgrade path to 5. Six (BlueROV1) gives full 6-DoF including pitch, but
costs $360–420 in thrusters alone, needs ~56 A of wiring, and **doesn't improve
surge**. Current leaning: start at 4.

**Housing diameter.**
4" sched-40 is the default, but two stacked LiPos plus Pi 5 plus NVMe plus
Pixhawk plus converters is tight. Worth laying out on paper before buying pipe.

**Is this still a $500 build?**
It is not. Worth deciding explicitly whether the target is "cheapest thing that
works" or "capable inspection platform," because they diverge from here.

## Deferred, revisit after first water

**Pitch control for camera aiming.**
Requires an ArduPilot fork (ADR-012). Value is real — no tilt servo, no dynamic
seal, no extra penetrator. Revisit if fixed-camera framing proves limiting.

**Hotel/propulsion battery split.**
Worth it at 6 thrusters. At 4, one pack may be simpler. See ADR-014.

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
