# Open Questions

## Sled, endcaps and CAD — decided vs proposed (2026-09-27)

Much of `sled.md`, the endcap proposal in `housing-layout.md` and
`cad/README.md` was written by an agent in design discussion. **Only the
first list below has Roland's approval.** Everything else is a proposal —
agents must not treat it as decided, build on it silently, or describe it
as settled. Visual: the "CARP Front-End Layout" artifact (side and front
views, cables up/down).

**Decided (Roland):**

- Domes stay on the front plate; cameras go on the sled so their cables
  connect outside the ROV.
- Rear end vacuum-held as well, with a mechanical backup, hardly ever
  opened.
- Aluminium lids are not v1 (cost); revisit later.
- CAD/ROS frame X forward, Y port, Z up; origin at the front pipe end on the
  tube axis.
- Onshape variable names: snake_case, whole words (`cad/README.md`).
- Camera board seats are print-only: slide-in rails (2026-10-02, after the
  tolerance coupons, `cad/README.md` §4).
- The bench rig should mirror the vehicle layout.

**Proposed, not approved:**

- Front lid vacuum-held on the pipe end with an O-ring, printed pilot ring,
  M6 tie rods on a 184 mm circle; 3/4" cast acrylic, 8" square.
- Bay order cameras → electronics → packs → ESCs; packs ride on the sled;
  the disconnect list; Bar30 on the front lid.
- Tray top at Z −55; `tube_length` 400.
- Stepped lid hole (Ø17 through, Ø52 × 8 counterbore) and the camera
  position chain (pupil 3 mm behind the lens front, board inside the lid).
- Stereo baseline stays 74 (could go to ~95). The first bench bracket was
  printed and fitted at 95 (2026-10-10, `cad/README.md`) — **tested, not
  decided**.
- Pi closer to the cameras on the bench rig: one ribbon is tighter than
  Roland likes at the current spacing — **leaning yes** (Roland,
  2026-10-11), not yet done.
- Cables up or down — **open, leaning up** (Roland).
- What holds the board at the rails' open end: printed detent, or a
  nut-held retainer (Roland's suggestion, 2026-10-02).
- Internal fan, Active Cooler, thermal soak before any aluminium.

**To test (Roland, 2026-10-11): a 3D-printed cover.** Roland wants to try a
printed cover before going to something else. This revisits the "never the
pressure boundary" rule in `bom.md` — the rule stands until the test says
otherwise. Nothing printed yet. Proposed test, not approved in detail:

- Seal the cover against a flat smooth plate (glass or an acrylic offcut)
  with the O-ring, Schrader stem in the cover — no pipe needed, and it
  separates the cover's porosity and stiffness from the pipe-end problem.
- Pull 15 inHg (the Phase 4 gate), watch the needle for a minute, then
  leave it overnight for slow weeping and creep.
- Measure the bow with a straightedge. Rough estimate for a flat solid PETG
  disc on the Ø161 seal at 1 bar, assuming 2 GPa: ~1.3 mm at 10 thick,
  ~0.4 mm at 15 thick. Ribs or a shallow dome do the same with less plastic.
- Print for tightness: 5–6 walls, 5+ top and bottom layers, high infill,
  seal face on the bed. Test bare first, then epoxy-coated.
- Pump connection for this test (proposed): a plain hose barb in the cover
  and the bleeder kit's hose — the kit has no Schrader adapter (`bom.md`).
  The gauge is on the pump, so leave the pump connected for the hold and
  do the dead-head check first; an overnight hold needs the pump to stay
  tight or a second gauge teed in. The kit's reservoir jar can stand in as
  a small test vessel to try the pump and hose before printing.

**Vacuum valve — open (raised by Roland, 2026-10-11).** The docs say to
pull the vacuum with the Schrader core out, but the plan is to dive under
vacuum, and with the core out the vacuum is lost when the pump comes off.
A Schrader core is also built to hold pressure in: against vacuum only its
spring keeps it shut. Options discussed, none chosen:

- Core in, pump through a coupler that depresses the pin, then a gasketed
  metal cap as the real seal.
- An A/C access valve (1/4" SAE flare, gasketed cap; core removal tools
  exist) instead of a tyre stem. Its tapered pipe thread cannot go
  straight into acrylic. Parts and prices not looked up.
- A bolt-in tyre stem, which clamps through a flat lid, with an open-flow
  chuck on a barb.
- Until one is chosen, the "core out" wording in `bom.md`,
  `bringup-checklist.md` and `decisions.md` stays as written.

**Under discussion, not decided (Roland's ideas, 2026-10-11):**

- Cameras mounted in the front end-cap with the Pi bracket attached to it,
  Pixhawk possibly beside the Pi, so some or all of the electronics come
  out with the cap. That cap is opened rarely.
- The rear is the regular battery door. This would change the decided
  "rear hardly ever opened" above — not changed yet.
- A printed adapter epoxied to the tube end to take up the pipe's loose
  tolerances. At the rear the adapter carries the cable glands, so the
  cover comes off with no cables in it.
- Two shorter tubes that separate in the middle for battery access — costs
  a third seal.
- Agent's lean, not approved: keep the front lid acrylic (it is the stereo
  datum); glands in the rear adapter rather than the mid-body split; check
  that the packs still pass through the adapter ring.

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

**Sub-question closed at 74 mm (2026-09-26).** The flange measured 71.9, not ~70, which broke 75; the bolt pattern (Ø64.5 circle, inside the flange) retired the old ≥ 5 mm gap rule, and 74 meets the rest (`housing-layout.md`, "Measured flange"). Original reasoning, assuming ~Ø70: **the stereo baseline is 75 mm.** Two ~Ø70 flanges
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
