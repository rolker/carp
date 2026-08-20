# Architecture Decision Records

These records came out of an early brainstorming session and were originally
all stamped "Decided." Most were not. Status now reflects actual commitment:

- **Committed** — hardware ordered or otherwise costly to reverse.
- **Leaning** — reasoned position, nothing bought, cheap to change.
- **Open** — actively contested; see `open-questions.md`.

Format: decision, rationale, consequences, status.

---

## ADR-001 — Design depth 5 m (v1, first site)

**Leaning.** 5 m is the depth of the particular section of Massabesic slated
for the first investigations — a v1 scope choice, not the vehicle's ceiling.
Deeper sites are expected later.

At 0.5 bar gauge the housing is not crush-limited; failures will be seal
workmanship, not structural. 4" sched-40 PVC is overbuilt by an order of
magnitude and can be leak-tested with a bike pump and a Schrader valve in one
endcap.

**Consequence:** Flotation can be sealed air voids (~1 g/cm³ lift) rather than
syntactic foam (~0.4). Budget freed for optics.

**Shallow assumptions to re-check before a deeper site** — several records
lean on "it's only 5 m":

- ADR-002 — surface-on-power-loss as the entire recovery plan
- ADR-009 — "free-dive to clear a snag" as the tether-fouling answer
- Tether length (15 m working radius) and the buoy's ~8 m vertical hang
- Shallow-water multipath handling in acoustic ranging (`navigation.md`)

The Bar30 (ADR-006) already covers 300 m and the housing has margin to several
tens of metres, so depth growth is mostly a seals, tether, and recovery-plan
question — not a rebuild.

---

## ADR-002 — Vehicle is set slightly positive

**Leaning.** Power loss results in surfacing. At 5 m this is the entire
recovery plan.

---

## ADR-003 — Dome port over flat port

**Leaning.** All imagery will be at 0.5–2 m range. Flat-port edge chromatic
aberration and FOV loss are worst at close focus, which is the entire operating
regime. Also preserves future photogrammetry options.

---

## ADR-004 — Lights on offset arms, not hull-mounted

**Leaning.** At 3 m visibility, backscatter from suspended particulate is the
limiting factor, not lumens. More light next to the lens makes the image worse.

**Implementation:** arms 30–40 cm off-axis, toed in so beams cross the camera
cone ~1 m out. Near field stays dark.

**Exception:** the down-looking nav camera wants flat, near-coaxial, diffuse
light — moving off-axis sources cast shadows that sweep across the bottom and
read as platform motion to the optical flow. Separate light, not shared.

---

## ADR-005 — Battery onboard, tether is Ethernet-only

**Leaning.** Topside power means fat conductors, voltage drop, and a tether
that can't be managed one-handed from a cockpit. Ethernet-only tether is thin,
near-neutral with floats, low drag.

**Open sub-decision:** pushing 48 V down a spare pair to carry hotel load only
(thruster transients stay on the onboard pack). Not yet evaluated.

---

## ADR-006 — Bar30 depth sensor, not Bar02

**Committed** — sensor ordered. Reversed from an earlier preference for the
MS5837-02BA.

Original reasoning was resolution. That reasoning was wrong: the 30BA gives
~0.2 mbar ≈ **2 mm** of water, and the 02BA ~0.16 mm. Both are far below the
real noise floor from surface chop and thruster wash.

The 30BA is what every ArduSub build uses, avoids any question about which
stable release picked up 02BA auto-detection, and gives 300 m of range if the
vehicle ever ends up deeper than planned.

**Note:** ArduPilot master *does* support the 02BA — the MS5837 driver reads
pressure sensitivity from PROM and dispatches to separate `_calculate_5837_02ba()`
or `_calculate_5837_30ba()` paths, with distinct device types (0x18 vs 0x12).
Verify the reported device type after connecting; misidentification fails
*silently* with plausible-looking wrong depth.

**Config:** `BARO_EXT_BUS` defaults to −1 (disabled) and must be set to the
external bus index. This is the most likely cause of "depth sensor not
detected" reports.

---

## ADR-007 — No safety switch

**Leaning.** Cannot press a physical button inside a sealed tube. Set
`BRD_SAFETYENABLE = 0`. Alternative was an external switch with its own
penetrator; not worth the hull penetration.

---

## ADR-008 — Pixhawk (FMUv2) + separate Pi, not Pi+Navigator

**Committed.** Radiolink Pixhawk Advanced, ordered from RobotShop.

Rejected the Blue Robotics Navigator ($220 + $65 Pi) on two grounds:

1. **Cost** — $285 of a $500 budget for the FC alone.
2. **Architecture** — Navigator runs ArduSub on the Pi under Linux with PWM
   from a PCA9685 over I2C. That's a soft-real-time control loop sharing cores
   with the payload. This build plans LK optical flow at 30 Hz *and* chirp
   cross-correlation on 96–192 kHz audio. Those are exactly the loads that
   contend with the flight loop.

**Why Radiolink over a 2.4.8 clone:** real manufacturer with automated SMT
assembly rather than an anonymous factory, sold through a real distributor.
Still FMUv2 — the architecture ArduSub actually tests.

**Why not Holybro 6C:** FMUv6C is less-tested for Sub. ArduPilot docs state
only the Pixhawk 1 is fully tested. Issue #23310 ("Sub: Pixhawk 6c full
support") remains open since March 2023, last touched Feb 2024.

**Known consequence:** FMUv2 flash ceiling. ArduPilot has been trimming
features from these boards for years. Fine for ArduSub today; this is a board
near the end of its life.

**Expected quirk:** power module voltage reads low on some units. Calibrate
`BATT_VOLT_MULT` against a meter rather than trusting defaults.

---

## ADR-009 — Stay tethered; reject HROV/AUV hybrid

**Leaning.** The buoy variant below is still just an idea — see
`open-questions.md`.

The mechanical cost of tetherless is near zero (battery is already onboard,
ArduSub already runs missions). The real costs:

- **Loses one-way acoustic ranging.** Sub-meter positioning was plausible
  *because* Ethernet time sync removes transponder turnaround jitter.
  Untethered means two-way ranging with tens of ms of USB audio slop — tens of
  metres of range error.
- **Nothing bounds nav drift.** VO is a random walk, and over featureless mud
  it doesn't drift so much as stop working.
- **The usual HROV justification doesn't apply.** Tether fouling on wreck
  structure is real, but at 5 m you can free-dive to clear a snag.

**Adopted alternative:** tether to a surface buoy carrying GNSS, battery, and
a WiFi/LoRa link, with ~8 m hanging vertically. Untethered *from the kayak*,
which is the part that's actually unpleasant, while preserving Ethernet,
absolute position, and a visible recovery marker.

**Software consequence:** build the vehicle to own its own mission with the
topside as a view, not a dependency. Tether dropout becomes a degraded link
rather than a lost vehicle.

---

## ADR-010 — Project11 interfaces, not Project11 autonomy

**Leaning.** CARP is a personal project first; CCOM use is an option to keep
open if a fit emerges, not a dependency.

**Transfers cleanly:**
- `udp_bridge` — built for exactly this failure mode (unreliable vehicle↔operator link)
- Project11 message types and the helm abstraction, so CARP appears in the same
  operator station as the EchoBoats
- rosbag and diagnostics conventions — what makes an inspection tie back to a
  sidescan contact later

**Does not transfer:** `mission_manager`, `path_follower`, Nav2 overlay. All
assume track lines in a 2D world frame with a GNSS position solution. CARP has
depth, heading, and dead-reckoned velocity — no global fix. Feeding those
planners a random-walk position produces confidently wrong behaviour.

**Rationale beyond the technical:** bare mavros plus a few nodes would be
simpler in isolation. But a vehicle speaking EchoBoat interfaces keeps the
option of CCOM/student use open at little extra cost. That's a side benefit,
not the goal — if the conventions ever fight the build, the build wins.

---

## ADR-011 — Thruster selection: ApisQueen U2

**Leaning** — not yet ordered. ApisQueen U2, 1.7 kgf, 150 W, 12–16 V (3–4S), 500 KV, rated
freshwater **and** seawater.

**Correction on record:** the widely-quoted "3.4 kg" figure is the **U2 Set**
(a pair). A single U2 is 1.7 kgf. Earlier power and pitch-authority
calculations in this project used the doubled figure and were wrong.

**Rejected:**
- **U01** — freshwater only. Also 390 W for 2 kgf, roughly 3× worse
  thrust-per-watt than a T200. For a vehicle that hovers all dive,
  thrust-per-watt sets endurance.
- **U2 Mini** — 1.3 kgf / 130 W. 30% less thrust for 15% less power. Listings
  for both are titled "U2"; check the ASIN.
- **U5** — 12–24 V range would have kept the DeWalt tool-pack option alive, but
  it's freshwater-rated.

**Why not bilge pump conversions:** salt tolerance was *not* the issue (bilge
pumps live submerged in salty bilge water by design — earlier claim retracted).
The real problems are (a) cutting off the impeller housing removes the internal
flow that cools the motor can, (b) prop thrust loads the shaft axially against
a seal designed for radial centrifugal loads, (c) many are rated intermittent
duty, (d) brush timing is advanced for one direction, so reverse is weak and
arcs.

**Why not DIY flooded outrunners:** ~2–3 kgf at ~$25 plus a weekend per motor,
versus $50–70 for a commercially-made unit using the same construction. DIY
wins if you want a specific KV or the knowledge, not on thrust per dollar.
Build time is better spent on the parts nobody sells.

**ESC:** ApisQueen units are bundled and purpose-built bidirectional, 1–2 ms
pulse width plus DShot. This removes the BLHeli 3D-mode setup and desync tuning
that would otherwise be a weekend.

---

## ADR-012 — Start SimpleROV-4, upgrade path to 5

**Leaning.** Thruster count (4 vs 6) is still open — see `open-questions.md`.

`SUB_FRAME_SIMPLEROV_4` and `_5` share one matrix in `AP_Motors6DOF.cpp`
defining **five** motors. Building 4 thrusters uses outputs 1–4 and leaves 5
unpopulated. Adding a lateral thruster later is pure bolt-on — no parameter
change, no reflash.

**Consequence:** the stock 4-thruster verticals are athwartships and give
**roll**, not pitch. The camera-aiming-by-pitching idea requires fore/aft
verticals.

**Custom frames are worse than expected:** `SUB_FRAME_CUSTOM` is an *empty
case* in the source. The only runtime motor parameters are `MOT_n_DIRECTION`
and `MOT_FV_CPLNG_K`. A custom matrix means forking ArduPilot, editing
`AP_Motors6DOF.cpp`, and maintaining a build — on a flash-limited FMUv2 board.

**Deferred:** BlueROV1 frame (6 thrusters, full 6-DoF, includes pitch). See
`frame-and-mixing.md`. Note it does *not* improve surge — still 2 horizontal
thrusters.

---

## ADR-013 — Battery chemistry: 4S LiPo for thrusters

**Leaning** — not yet ordered. 2× 4S 6000 mAh LiPo with XT90-S anti-spark.

**Reversed from an earlier Li-ion preference.** Li-ion is better on density
(~250 vs ~150–180 Wh/kg), protection, and storage tolerance, and C-rate was
supposed to be irrelevant at these currents. But high-current **4S** Li-ion is a
niche product — the market is 3S, 6S for drones, and 13S+ for ebikes. 60+ A at
4S is exactly what LiPo owns.

**Accepted costs:** balance charger required, storage at 3.8 V/cell between
field days, no BMS. Pouch cells swell when they fail — inside a sealed tube
that's pressure with nowhere to go. **Put a relief path in the endcap.**

**Rejected:** 12 V LiFePO4 "fishfinder" packs. The BMS is the blocker — typical
20 A rating caps output at ~256 W, less than two U2s at full throttle, and it
will trip mid-dive. Also ~95 Wh/kg and 12.8 V nominal costs ~30% thrust
(thrust scales roughly with V²). Still a good **hotel** battery.

**Why two packs, not one:** swap between dives. Endurance per *day* is what
actually limits kayak operations, not endurance per dive.

---

## ADR-014 — Two-battery split: propulsion vs hotel

**Open** — conditional on going to 6 thrusters, itself an open question. At 4
thrusters a single pack may be simpler.

Split by **propulsion / hotel**, not by thruster count. A 4/2 thruster split
leaves a partially-controllable vehicle on pack failure — worse than a clean
failure. Propulsion/hotel gives benign failure modes both ways: lose
propulsion and you still have video, telemetry, and a tether to haul on; lose
hotel and you've lost the mission but not the vehicle. Also matches discharge
profiles — thrusters bursty, hotel steady.

**Electrical rule:** tie pack negatives together at a single heavy star point.
ESC signal grounds return to the Pixhawk; floating packs mean a floating PWM
reference and phantom thruster twitches. Take Pi and Pixhawk grounds from the
star point directly, not daisy-chained off the ESC return.

**Monitoring:** wire `BATT2_MONITOR`. Hotel is the pack that drains quietly
while parked on the bottom.

---

## ADR-015 — Video: IP cameras + one direct global-shutter camera

**Leaning.**

**Pi 5 has no hardware H.264 encoder.** VideoCore VII dropped it; encoding is
software x264 on the CPU. Two 1080p30 streams would consume most of the cores
before optical flow or DSP.

**IP cameras solve this** — the camera SoC encodes, the Pi writes bytes it
never compressed. One Ethernet penetrator, internal switch, arbitrary views.

**Costs accepted:** RTSP latency 200 ms–1 s (fine for inspection, unpleasant
near structure); rolling shutter; auto-exposure/AWB that often can't be
disabled and will hunt badly in turbid green water; baked-in sharpening that
fabricates texture feature trackers will latch onto.

**Therefore the nav camera stays direct.** OV9281 global shutter, mono, manual
exposure, MIPI/USB. Rolling shutter plus vehicle roll produces flow skew that
biases systematically, not just noisily.

**Recording format:** `foxglove_msgs/CompressedVideo` or
`ffmpeg_image_transport` `FFMPEGPacket`. **Never raw `Image`** — 1080p30
uncompressed is ~180 MB/s and fills 1 TB in 90 minutes.

**Keyframe interval 1–2 s.** rosbag2 stores opaque bytes with no notion of
frame dependency; seeking lands mid-GOP and decodes garbage until the next
keyframe. Costs ~15% bitrate, makes bags scrubbable. rviz won't render these —
plan on Foxglove.

**H.265 caveat:** marine snow is temporally random high-frequency detail.
Motion prediction can't model it, so it burns bitrate on residuals every frame
and the codec advantage narrows exactly where we're shooting. Inter-frame
prediction also smears the fine bottom texture SfM depends on. **Record
full-res JPEG stills on a trigger** alongside video if measurement is ever the
goal.

---

## ADR-016 — Storage: NVMe on Pi 5, sized for a day

**Leaning.** 1 TB NVMe via M.2 HAT+. Pi 5 PCIe is Gen2 x1 (~450 MB/s).

Capacity is not the constraint; **cooling is**. An NVMe drawing 3–5 W inside a
sealed PVC tube needs a thermal path to the hull wall, not a heatsink into dead
air.

**Sized for a day, not a season.** Can't swap drives in a sealed housing, but
gigabit tether offloads at ~100 MB/s — 100 GB moves in under 20 minutes over
lunch.
