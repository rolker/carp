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
magnitude. Leak testing via a Schrader stem in one endcap: **vacuum test is
the gate** (15 inHg with the hand pump, core removed — loads seals the same
direction depth does; 15 inHg ≈ 5.2 m of water — matches the site depth,
where 10 inHg would only prove 3.5 m), gentle bike-pump pressure + soapy
water only to *localize* a leak after a failed vacuum test (positive
pressure unseats face seals, so it's a debug tool, not a pass/fail check).

**Consequence:** Flotation can be sealed air voids (~1 g/cm³ lift) rather than
syntactic foam (~0.4). Budget freed for optics.

**Shallow assumptions to re-check before a deeper site** — several records
lean on "it's only 5 m":

- ADR-002 — surface-on-power-loss as the entire recovery plan
- ADR-009 — snag recovery workable from the surface
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

## ADR-004 — Ambient light first; no lights on v1

**Leaning.** Reversed 2026-08-20 from "lights on offset arms."

The v1 site is 5 m deep, worked in daylight. At Kd ≈ 0.7–1.0 (consistent with
3 m visibility), 5 m keeps ~1–3% of surface light — hundreds to thousands of
lux on the bottom. A fast lens and a sensitive sensor can use that; adding our
own light next to the camera re-lights the particulate column that ambient
leaves dark.

**Wins:** the backscatter problem vanishes (ambient arrives from above,
already diffuse); hotel load drops 20–40 W — the power budget's dominant
term — extending endurance per pack ~30–40%; two or three penetrators and the
light arms disappear from the build.

**Costs:** the shadowed side of structure is invisible — the one strong
argument for carrying a single small diffuse light, off by default. Ambient
dies exponentially with depth, so deeper sites (ADR-001) will need lights,
full stop. In direct sun the vehicle's own shadow moves with the down
camera's frame; features on its edge report zero motion and must be masked
out of optical flow.

**Hardware consequence:** camera selection prioritises sensitivity and true
manual gain (large/BSI pixels, fast glass) over convenience.

**Superseded reasoning, kept for the day lights return:** backscatter, not
lumens, is the limiting factor — arms 30–40 cm off-axis, toed in so beams
cross the camera cone ~1 m out; the down-looking nav camera is the exception
and wants flat, near-coaxial, diffuse light, since moving off-axis shadows
read as platform motion to optical flow.

**Verify before first water:** camera in a jar at the site, midday and
overcast. This is a measurement, not a debate.

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

**Field intel (2026-08-20, see `prior-art.md`):** BlueOS explicitly warns
against RadioLink boards (proprietary bootloader), and community experience
says the clone FC — not the cheap thrusters — is what fails first in budget
builds (compass grief, EKF weirdness). Mitigations: flash `Pixhawk1-1M`
Sub/stable via QGC custom firmware, **keep the working .apj pinned locally**,
mount the compass away from ESC wiring, and connect Pixhawk→Pi over USB
(BlueOS only auto-detects over USB, not UART). Note AP_DDS and Lua are
compiled out of 1 MB builds — ROS 2 lives on the Pi over MAVLink.

**Cost note, on record:** actual price paid was $159.82 + shipping, not the
~$60 street price assumed when this was argued. Against the Navigator's $285
the cost gap (ground 1) was much thinner in practice; the architecture
argument (ground 2 — hard-real-time FC separate from the DSP-loaded Pi) is
what carries this decision.

**Bench evidence (2026-09-26): this board has 2 MB of flash.** Running the
`Pixhawk1-1M` build, ArduSub 4.7.1 logs `2M flash - use Pixhawk1 firmware`
on every boot (board ID `002A0032 35335103 33303831`). The 1 MB ceiling above
does not apply to this unit. **Reflashed to the full `Pixhawk1` build the
same evening** — it boots clean, no warning, calibration and parameters
carried over. It adds 91 parameters: Lua scripting (`SCR_ENABLE`),
mount/gimbal (`MNT1_*`), IMU temperature calibration, a third harmonic
notch, more filters, proximity. It does **not** include AP_DDS (no `DDS_*`
parameters), so ROS 2 over MAVLink on the Pi stays the plan. QGC's
`Unsupported FTP: 16` persists on the full build, so that is a QGC/ArduSub
FTP mismatch, not a 1 MB cut. Still one IMU on the full build (MPU6000,
`INS_ACC2_ID = 0`): this board has no second IMU, or it is dead — no backup
IMU either way.

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
  structure is real, but at 5 m a fouled tether is recoverable without
  abandoning the vehicle. **Snag protocol (2026-08-20, replaces an earlier
  "free-dive to clear it" line):** gentle haul-test from multiple bearings →
  slack the tether and drive the vehicle to unwind it → if still fouled,
  buoy the tether end and come back with a second person or a grapple.
  **Never solo breath-hold dive on a fouled line** — the line that snagged
  the vehicle is the line that snags the diver. The vehicle costs ~$1,600;
  it is not worth a solo entanglement dive, ever.

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

**Committed.** Six units ordered 2026-08-19. ApisQueen U2, 1.7 kgf, 150 W, 12–16 V (3–4S), 500 KV, rated
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

**Open — changed circumstances.** Written when 4 thrusters was the plan; six
have since been ordered, making BlueROV1 (all six, full 6-DoF including the
pitch-for-camera-aiming this ADR rules out, stock matrix, no fork) a live
alternative to starting at SimpleROV-4. See `open-questions.md`.

BlueROV1 has since been laid out and dimensioned against a 6" housing in
`housing-layout.md`. Note 5 there is the argument this ADR now has to answer:
pitch inertia scales with length squared, so adopting BlueROV1 for camera
aiming and then building it on a long 4" tube produces the hull that makes
aiming sluggish. The frame and the housing are one decision, not two.

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

**Committed.** Ordered 2026-08-19 (YOWOO 100C). 2× 4S 6000 mAh LiPo with
XT90-S anti-spark.

**Reversed from an earlier Li-ion preference.** Li-ion is better on density
(~250 vs ~150–180 Wh/kg), protection, and storage tolerance, and C-rate was
supposed to be irrelevant at these currents. But high-current **4S** Li-ion is a
niche product — the market is 3S, 6S for drones, and 13S+ for ebikes. 60+ A at
4S is exactly what LiPo owns.

**Accepted costs:** balance charger required, storage at 3.8 V/cell between
field days, no BMS. Pouch cells swell when they fail — inside a sealed tube
that's pressure with nowhere to go. **The relief path is the Schrader stem in
the endcap** (BOM small parts; same fitting as the vacuum/pressure test port).
Core in while diving — it seals against water and holds internal pressure, so
this is a *manual* vent, not an automatic pop-off: **always crack the core
(core tool) to equalize before opening the lid**, and treat a hiss as a
warning, not a nuisance. Mid-dive swelling is mitigated upstream — per-cell
check before every charge, pack inspection before every dive — not by the
vent. (Review 2 MA1: the part and procedure are now named, closing the
"relief path: confirmed" checkbox loop.)

**Rejected:** 12 V LiFePO4 "fishfinder" packs. The BMS is the blocker — typical
20 A rating caps output at ~256 W, less than two U2s at full throttle, and it
will trip mid-dive. Also ~95 Wh/kg and 12.8 V nominal costs ~30% thrust
(thrust scales roughly with V²). Still a good **hotel** battery.

**Why two packs, not one:** swap between dives. Endurance per *day* is what
actually limits kayak operations, not endurance per dive.

---

## ADR-014 — Two-battery split: propulsion vs hotel

**Open — now live.** Six thrusters have been ordered, so this split is on the
table. The two 4S packs on hand could serve as propulsion + hotel, or
propulsion + swap spare with a LiFePO4 hotel pack later.

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

**Open — under revision 2026-08-20.** Ambient-only operation (ADR-004) puts a
premium on sensor sensitivity and true manual gain, which is exactly where
cheap IP cameras are worst (tiny sensors, undefeatable noise reduction).
Forward-camera selection is in progress; the down/nav camera and optical flow
are deferred past v1. The analysis below predates that shift.

**Pi 5 has no hardware H.264 encoder.** VideoCore VII dropped it; encoding is
software x264 on the CPU. Two 1080p30 streams would consume most of the cores
before optical flow or DSP.

**Measured 2026-09-26** (bench Pi 5, **no cooler**, two B0444s through our
libcamera → `camera_ros` → `image_transport` republisher → libx264
`ultrafast`/`zerolatency` → `FFMPEGPacket` → MCAP, one component container):

| Setting (per camera) | Encoded | CPU | SoC temp |
|---|---|---|---|
| 1920×1080, cameras at 30 fps | **~10 fps**, ⅔ of frames dropped | saturated (0–2% idle) | 75 → **85 °C, throttling** |
| 1280×720 at 10 fps | **10.00 fps**, every frame | ~20% (80% idle) | flat 64–66 °C |
| 1280×720 at 20 fps | 20.00 fps, every frame | ~45% | ~72 °C, level |
| **1920×1080 at 10 fps** (default) | 10.00 fps, every frame | ~38–48% (two runs) | 69–71 °C, level |
| 1920×1080 at 12 fps | 12.00 fps, every frame | ~52% | 72 → 78 °C, **still rising** at 60 s |

So the prediction above holds and is worse than stated: 1080p30 stereo does
not fit on the CPU at all, and without a cooler it overheats trying.
**Default is 1920×1080 at 10 fps** (`ros/carp_camera` launch file): sensor
native, so no ISP scaling, and resolution buys more than frame rate here —
stereo depth precision scales with pixels across (~1.5× finer than 720p at
the 74 mm baseline), while at ROV speeds 10 fps already overlaps
consecutive frames by >90% at 0.5–2 m. Frame rate matters for piloting
feel, which argues for a separate low-res live view rather than a faster
recording. 12 fps is the edge uncooled; everything was measured on an open
bench, so the sealed housing needs its own thermal soak. Bench-scene
bitrates were ~155 kbit/s (720p10) and ~330 kbit/s (1080p10) per camera,
well under the caps. Shutdown sometimes hangs (container SIGKILLed after
15 s at 720p20 and 1080p12; bags intact) — not yet investigated.

**IP cameras solve this** — the camera SoC encodes, the Pi writes bytes it
never compressed. One Ethernet penetrator, internal switch, arbitrary views.

**Costs accepted:** RTSP latency 200 ms–1 s (fine for inspection, unpleasant
near structure); rolling shutter; auto-exposure/AWB that often can't be
disabled and will hunt badly in turbid green water; baked-in sharpening that
fabricates texture feature trackers will latch onto.

**Therefore the nav camera stays direct.** OV9281 global shutter, mono, manual
exposure, MIPI/USB. Rolling shutter plus vehicle roll produces flow skew that
biases systematically, not just noisily.

**Recording format:** `ffmpeg_image_transport` `FFMPEGPacket` (chosen
2026-09-26 to match `unh_marine_perception`, so the same decode and rqt
tooling works on CARP bags). **Never raw `Image`** — 1080p30
uncompressed is ~180 MB/s and fills 1 TB in 90 minutes.

**Keyframe interval 1–2 s.** rosbag2 stores opaque bytes with no notion of
frame dependency; seeking lands mid-GOP and decodes garbage until the next
keyframe. Costs ~15% bitrate, makes bags scrubbable. rviz won't render these;
view through `ffmpeg_image_transport` decode (republish or rqt tools).

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

**Caveat (reviews 1 M7 / 2 minor 3):** the field tether is CCA Cat6 and the
doctrine is 100BASE-TX; at 100 Mbps that same 100 GB is ~2.2 h. Measure what
the real tether + Opal actually negotiate (iperf3, Phase 3) before this
offload story hardens. Fallback: offload dockside over a short known-good
gigabit cable, or overnight.

---

## ADR-017 — Pi software stack: vanilla Raspberry Pi OS, not BlueOS

**Leaning.** Decide before any Phase 3 software integration (both reviews
flagged this as untracked; it gates nothing mechanical but everything on the
Pi).

**Options considered:**

- **A — BlueOS** (Blue Robotics' companion image): polished web UI, extension
  ecosystem, autopilot management. But it warns against RadioLink boards
  (prior-art), its camera manager can't enumerate libcamera CSI cameras
  ([BlueOS #991](https://github.com/bluerobotics/BlueOS/issues/991)) — so the
  dual-IMX462 pipeline gets hand-built *anyway* — and ROS 2 would live beside
  it in a container it knows nothing about.
- **B — vanilla OS + hand-assembled services:** mavlink-router (Pixhawk USB
  → tether UDP + local apps), the hand-built CSI → encode → RTP/WebRTC
  pipeline, ROS 2, Cockpit self-hosted. Every piece is a standalone open
  project; nothing fights the Pivariety camera driver or the RadioLink
  board. Splits on the base image:
  - **B1 — Ubuntu 24.04 for Pi:** the Tier-1 ROS 2 platform — Jazzy from
    apt, no containers, no source builds. But Arducam's Pivariety stack
    (kernel driver + dtoverlay + libcamera fork + tuning files) is packaged
    **for Raspberry Pi OS only**; on Ubuntu's different Pi kernel that chain
    is a rebuild-it-yourself project with a history of forum grief.
  - **B2 — Raspberry Pi OS 64-bit:** cameras turnkey per Arducam's own docs;
    ROS 2 has no official Debian-arm64 binaries, so it lives in a Docker
    container (or a source build). Containerized ROS 2 is well-trodden;
    CSI/GPU access stays on the host side of the boundary (cameras → encoder
    feeds ROS via local UDP/shared memory, so the container never needs
    /dev/video access).
- **C — hybrid:** BlueOS as base plus ROS 2 container. Maximum moving parts,
  both ecosystems' failure modes.

**Leaning B** (not BlueOS) because the two things BlueOS is best at (camera
plumbing, board support) are exactly where this build deviates from BlueROV
hardware, and ROS 2 as a first-class citizen is a project goal (ADR-010).
Cost: we own service wiring (systemd units) that BlueOS would have given for
free. **B1 vs B2 is genuinely open** — preference is B1 (Ubuntu) if the
cameras cooperate, because native ROS 2 removes a whole layer.

**Decision gate:** the CSI/encode bench prototype (review 1 sequencing item)
decides. Order of attack: flash **Ubuntu 24.04 first** and timebox the
Pivariety driver bring-up to one evening — if both cameras enumerate and
stream, B1 wins and everything else is easy. If the driver fights, flash
RPi OS (B2), confirm the cameras per Arducam's happy path, and accept
Docker'd ROS 2. **Revisit trigger:** if MAVLink routing or telemetry
plumbing burns more than a weekend of fiddling on either base, try BlueOS
(A) on a spare SD card before writing more glue.

**Evidence, 2026-09-26.** The cameras are SKU **B0444 — Pivariety**, not
Arducam's native IMX462 (B0423, which is a plain `dtoverlay=imx462` on the
stock Pi kernel). Pivariety needs Arducam's own libcamera build via
`install_pivariety_pkgs.sh`; Arducam's docs list Raspberry Pi OS only
(Bullseye/Bookworm/Trixie), and the Ubuntu reports on their forum are
source builds with mixed results. Ubuntu 24.04's own libcamera (0.2) also
predates Pi 5 support. This is the "driver fights" branch arriving before
the timebox starts — it weighs toward B2.

**Evidence, 2026-09-26 (bench, later).** The kernel half works on Ubuntu
24.04 with nothing from Arducam installed: the stock `6.8.0-raspi` kernel
ships `arducam-pivariety.ko`, and `dtoverlay=arducam-pivariety,cam0` /
`,cam1` (with `camera_auto_detect=0`, `scripts/enable-pivariety-cameras.sh`)
binds both B0444s (firmware 0x10003). Both stream raw 1920×1080 RGGB10 at
the same time through plain V4L2 (`scripts/capture-raw-pair.sh`), with
recognisable images and no throttling on a 4.9 V supply. What is still
missing on Ubuntu is everything above the kernel: no Pivariety-aware
libcamera, so no ISP debayer, AWB or AE — the frames are raw Bayer. B1 is
back in play; the open question narrows to "debayer + exposure control on
Ubuntu" (Arducam's libcamera fork from source, the Pi ISP another way, or
GStreamer/CPU debayer at the frame rates we need). Bring-up notes: the
first failures were a cable seated contacts-away at one end (each end of a
Type B cable must match its own connector), and `/dev/mediaN` / `/dev/videoN`
numbering moves between boots, so find cameras by I2C bus (10 = CAM0,
11 = CAM1).

**Evidence, 2026-09-26 (libcamera on Ubuntu).** The "debayer + exposure
control on Ubuntu" question is answered: yes, with a small patch of our own.
Arducam's Pivariety userspace turned out to be Raspberry Pi's libcamera plus
a closed cam helper shipped only as RPi OS binaries, so there is no source to
port. Instead, `patches/libcamera/` teaches Raspberry Pi's open libcamera
(pinned at `6c1dd9d`) the `arducam-pivariety` sensor: a ~60-line cam helper
(linear gain code in hundredths, read from Arducam's binary; IMX290-family
timing), an IMX462 entry in the sensor property table, and the upstream
`imx462.json` tuning installed under the Pivariety name.
`scripts/build-libcamera.sh` builds it and rpicam-apps into
`~/opt/libcamera`; `rpicam-hello` lists both cameras (1080p60) and
`rpicam-still` gives colour, auto-exposed, white-balanced frames from each.
**B1 now has a full camera path**, and the cost that comes with it:
- the patch is ours to carry, re-applied on each libcamera bump (small and
  self-contained, so low risk; it breaks only if the cam helper API moves);
- the ROS camera node (`camera_ros`) must be built against this libcamera,
  not taken from apt with ROS's own copy;
- `imx462.json` was tuned for another vendor's module (Innomaker), so colour
  is approximate until we calibrate; the board shows no IR-cut control;
- control delays are IMX462 defaults, not Arducam's board-stored values —
  check for exposure flicker under AE before trusting them;
- rpicam-apps' libav encoder needs ffmpeg 7 (Ubuntu 24.04 has 6.1), so
  encoding goes through the ROS video transport or GStreamer instead.
Still open for the gate: dual encode → rosbag on the Pi, measured on a
stable supply with cooling (the build alone hit undervoltage on a 4.9 V
supply and the 77 °C soft limit without a fan).

**Evidence, 2026-09-26 (gate met at 720p10).** The bench prototype runs end
to end on Ubuntu: both cameras → `camera_ros` (from source, against our
libcamera) → H.264 via `ffmpeg_image_transport` → MCAP rosbag on the Pi,
10.00 fps per camera with every frame kept, keyframes every 1.5 s, and both
streams decode cleanly offline. Setup is `scripts/setup-ros-workspace.sh`
(rosdep, skipping the `libcamera` key) and `scripts/build-ros-workspace.sh`.
**B1 holds**; the costs listed above stand. Resolution/frame-rate limits are
in ADR-015. **Stereo sync is the open problem:** the cameras free-run, and
this run's pairs sat a constant 49 ms apart (half a frame at 10 fps; the
phase is random per start). Arducam documents external trigger only for its
global-shutter Pivariety models, not the IMX462, and the driver exposes no
trigger control on ours. Raspberry Pi's libcamera has software sync
(`rpi.sync`: one camera serves timing, the other adjusts its frame length to
match), which our driver's VBLANK control should support; it needs
`"rpi.sync": {}` in the tuning file and `SyncMode` set per camera. Untested.

**Evidence, 2026-09-26 (software stereo sync works).** With `rpi.sync`
enabled in our tuning file (`build-libcamera.sh` adds it) and `SyncMode`
server on cam0 / client on cam1 (launch default `sync:=true`), cam1 locked
~3.4 s after start and then held its sensor timestamps a median **23 µs**
from cam0's (p99 50 µs, max 137 µs over 790 pairs at 1080p10; max 0.2 ms at
1080p12), against 2–49 ms free-running. That is ~1.5 sensor lines (line
time 14.8 µs), negligible next to the ~16 ms rolling-shutter readout both
cameras share, so no hardware trigger is needed for stereo at ROV speeds. Frames from the first few seconds, before lock, are not
paired; `camera_ros` does not surface libcamera's `SyncReady`, so drop
them downstream by timestamp offset. Sync traffic is UDP multicast
239.255.255.250:10000 on the default route (Wi-Fi on the bench) — confirm
it still flows with only the tether up.
