# Prior Art — Cheap ROV Builds, Distilled for CARP

Compiled 2026-08-20 from a survey of established open-source ROV projects and
recent (2020–2026) DIY builds. Organized by what transfers, not by project.
Sources linked throughout; archives worth mining are listed at the end.

**Headline:** every element of CARP's architecture is independently validated
by recent builds — cheap thrusters + Pi 5 + direct Ethernet + Cockpit
([AL3X's mini BlueROV2, Apr 2026](https://discuss.bluerobotics.com/t/a-more-affordable-6-dof-mini-bluerov2-build/22815)),
Pixhawk + ArduSub + Pi + Cat5e + 6 thrusters + ROS 2
([Halo AUV](https://oubrejames.github.io/halo_auv/)). But nobody has published
the *whole* combination, and several specific gaps (ApisQueen teardowns,
dual-CSI stereo behind mini-domes, kayak deployment logs) mean a CARP build
log would be novel content.

---

## Housing and penetrators

**The single most-repeated lesson across every source: wire cores are water
pipes.** Water wicks *between the strands inside insulated wire*, straight
through a perfect epoxy pot — [CPS 5 burned 14 prototypes learning
this](https://hackaday.com/2022/11/02/3d-printed-rov-is-the-result-of-many-lessons-learned/).
Fix: strip and solder-blob every conductor mid-pot so epoxy bonds bare
copper. Acetone-etch cable jackets first — adhesion to the jacket is the seal
([BR potting guide](https://bluerobotics.com/learn/potting-a-cable-penetrator/)).

**Seal geometry:** PVC pipe is out-of-round with extrusion lumps. Radial
O-rings against pipe ID/OD fail; threaded caps are not pressure seals
(OpenROV's chronic endcap leaks were a tolerance-stackup radial-seal problem).
The proven pattern: one solvent-glued end + one **face seal** — flat lid
clamped over a face O-ring on an 800-grit wet-sanded seat. Face seals
self-energize with depth. The [Cave Pearl
recipe](https://thecavepearlproject.org/2020/04/08/diy-data-logger-housing-from-pvc-parts-2020-update/)
(Formufit threaded table cap, #332 O-ring, Loctite E-30CL potting, indicating
desiccant) is proven multi-year to 50 m —
[cross-validated](https://www.homebuiltrovs.com/rovforum/viewtopic.php?f=13&t=1594)
4–12 months submerged with zero floods.

**Potting shoot-out** ([tested to 5.5 bar](https://www.techmonkeybusiness.com/articles/ROV_Wire_Sealing_Methods.html)):
slow-cure two-part epoxy wins; polyester resin, silicone, and hot glue all
empirically fail. PG7 gland + epoxy back-fill ≈ $3/penetration.

**Vacuum testing is universal practice.** BR's kit is a rebadged Mityvac
brake bleeder (~$30 at auto parts). Epoxy a brass barb into a spare
penetrator hole as a permanent nipple; pull ~10 inHg, watch for a steady
needle, before every wet day and after every reopening
([BR guide](https://bluerobotics.com/learn/using-the-vacuum-test-plug/)).
Real-world floods at shallow depth come from the seal you touched last:
mis-seated or contaminated O-rings, and enlarged penetrator holes
([BR flood threads](https://discuss.bluerobotics.com/t/4-enclosure-leaking/23131)).

**Thermal:** PVC insulates; a Pi 5 encoding video in a sealed tube will
throttle. MATE teams moved to aluminum hulls partly for this. Strap the Pi to
an internal aluminum plate against a wet-backed endcap; log SoC temp every
dive. Expect condensation on cold-lake walls — oversize the desiccant, and
expect a leak probe at the low point to false-alarm on condensate.

**Other:** free-flood everything that isn't the pressure vessel (drill the
frame — the SeaPerch rule); separate battery tube(s) mean a leak in one
doesn't kill everything (OpenROV pattern); LiPo relief path is non-negotiable
(vent plug doubles as the vacuum port); slide the housing fore/aft on its
mounts for pitch trim (BlueROV1 pattern) rather than fixing it.

## Tether

- **20 m of direct 100BASE-TX is a non-issue** — no failure report exists
  anywhere at that length; documented trouble starts near 100 m. Don't chase
  gigabit: submersion raises insertion loss and 1000BASE-T dies at length
  while 100 Mbps holds ([BR cat-6 thread](https://discuss.bluerobotics.com/t/cat-6-tether-options/14538)).
- **Water ingress is the real risk**: nicked jackets wick water along pairs
  and slowly detune the link. Upgrade path: gel-filled **direct-burial Cat5e**
  (~$0.15/m) threaded through **hollow-braid polypropylene rope** as strength
  member ([SV Seeker method](https://hackaday.com/2020/01/27/the-options-for-low-cost-rov-tethers/)).
  Seal cut ends; treat the tether as a ~$10 consumable and carry a spare.
- Strain-relieve to the frame (loop or kellems grip), never the penetrator.
  Sleeve in braided loom against kayak-edge abrasion (MATE rule). Pass the
  intact jacket through a WetLink-JPT-style gland so pair twist survives to
  an RJ45 crimped on the dry side.
- Buoyancy at 5 m is easy: closed-cell foam bits zip-tied every 1–2 m near
  the ROV. (All documented float failures — crushed noodles, compressed rope
  air — happened at 20–30 m.)

## Thrusters (ApisQueen U2)

- **"U2" is a family** (Mini / 150 W / 300 W / Pro) and listings mix the
  numbers freely — confirm which variant arrived before sizing fuses (9 A vs
  ~20 A per unit). De-rate marketing thrust ~50%: plan 1.3–1.7 kgf/unit.
- PWM contract is ArduSub-native: 1500 µs neutral, 1100–1900 range, no
  calibration, expects neutral at boot (ArduSub provides it). Plain PWM from
  the Pixhawk; skip DShot.
- **Bench-match all six before anything is potted.** The one detailed field
  report ([ArduRover + 2× U2](https://discuss.ardupilot.org/t/thruster-stops-instantly-with-a-click-instead-of-spinning-down/116439))
  found one faulty unit (throttle ceiling 1640 µs vs 1900 on its twin) and
  asymmetric ESC braking. Log PWM→current per unit; exercise returns early.
- A cheap USB tuning board + Windows app adjusts ESC start/stop sensitivity —
  the fix if depth hold gets jerky.
- Freshwater at 5 m is the easy case: **bearings, not flooding, are the wear
  item**. Rinse after every session, CorrosionX the shafts, carry 1–2 spares.
- Budget for brownout: 6 thrusters slamming reverse sags the bus. Bulk
  capacitance at distribution, Pi on its own regulator, output slew limiting
  ([BorgCube's ESC-reset saga](https://hackaday.io/project/8343)).
- No independent ApisQueen teardown or longevity data exists anywhere; no
  6-thruster ApisQueen vectored build is published. CARP is first.

## Flight controller and firmware

- **`Pixhawk1-1M` is the correct ArduSub build target** for genuine FMUv2;
  Sub/stable (4.7) still ships it. Compiled out on 1 MB boards: **AP_DDS (no
  native ROS 2), Lua, camera/gimbal MAVLink** — ROS 2 lives on the Pi over
  MAVLink, full stop.
- **BlueOS explicitly warns against RadioLink boards** (proprietary
  bootloader), and BlueOS auto-detects Pixhawks **over USB only** (GPIO-UART
  unsupported). Plan: Pixhawk→Pi over USB; flash via QGC custom firmware;
  **pin the working .apj locally**.
- Key params from the field: `SERIAL2_PROTOCOL=2`, `SERIAL2_BAUD=921` (if
  UART), **`SYSID_MYGCS=255`** (else no joystick authority), and in any
  custom control code MANUAL_CONTROL **z-neutral is 500, not 0** — the #1
  "thruster runs away on arm" cause
  ([BR thread](https://discuss.bluerobotics.com/t/pixhawk-running-ardusub-outputs-max-throttle-pwm-signal-upon-arming/23270)).
- In sub-$1,500 builds the **clone FC fails you before the cheap thrusters
  do** (compass grief, EKF weirdness, dropouts). Mount the compass away from
  ESC wiring; calibrate carefully; Bar30 + clean compass matter more than
  thrust quality at 5 m.

## Control and video

- **Plan phone control around Cockpit, not QGC mobile.** QGC Android joystick
  calibration is broken (closed-stale 2025), ArduSub has no virtual
  on-screen sticks, and QGC is gone from the iOS App Store.
  [Cockpit](https://github.com/bluerobotics/cockpit) (BR's browser GCS,
  served from the vehicle) + Chrome full-screen + **Bluetooth gamepad via the
  browser Gamepad API** is the actively developed path. Pin the tab (input
  stops when it loses focus — enable Cockpit's input-hold), disable mobile
  data (Android flees to 4G when the ROV WiFi "has no internet"), disable
  battery saver (a documented cause of 1 s video lag). Keep a laptop with
  desktop QGC for setup/calibration regardless.
- **The CSI video pipeline is CARP's biggest software risk — prototype it
  before sealing hardware decisions.** BlueOS's camera manager does not
  enumerate libcamera CSI cameras
  ([issue #991](https://github.com/bluerobotics/BlueOS/issues/991)); the
  pipeline is hand-built: `libcamerasrc/rpicam-vid → x264enc
  tune=zerolatency speed-preset=ultrafast → RTP udp:5600` for QGC, or WebRTC
  via mavlink-camera-manager for Cockpit. Expect 150–250 ms glass-to-glass.
- Network plan, verbatim from
  [ardusub.com wireless-topside](https://www.ardusub.com/developers/wireless-topside.html):
  192.168.2.0/24 — control device .1, vehicle Pi .2, router .3 as AP.
  **Router mounted on the tether reel = no slip ring** (unplug the RJ45 to
  unspool). The WiFi hop, not the Cat5, is the flaky link — prefer 5 GHz AP
  so the Bluetooth gamepad keeps 2.4 GHz to itself.
- Most common field failures ([Spot X top-5](https://www.spotx.com.au/blogs/news/2019-8-15-top-5-ardusubqgc-mini-rov-fails)):
  wrong topside IP, QGC/ArduSub version mismatch, power-saving topside
  device, loose connections, counterfeit SD cards. All pre-emptable.

## Cameras and domes

- Dome focus: a 2" dome puts the virtual image ~3–4 dome-radii ahead; BR's
  own recipe for M12 lenses is ~½–¾ turn CCW from air focus, then iterate
  wet. Entrance pupil at the dome's center of curvature or astigmatism and
  radially varying blur appear
  ([BR dome-focus thread](https://discuss.bluerobotics.com/t/seeking-input-dome-port-calibration-to-focus-raspberry-pi-camera-for-high-quality-underwater-video/21213)).
  Design fore-aft adjustability into the camera mounts.
- Flat ports have **distortion that varies with subject distance** — breaks
  the single-viewpoint model, poison for stereo measurement. Domes keep the
  pinhole model valid. (Confirms the twin-dome choice.)
- **Calibrate stereo underwater, through the final domes**, laminated
  checkerboard, fisheye model, at working distance; air calibration does not
  transfer. 60–120 mm baseline for 0.5–2 m work. Re-calibrate after any
  reassembly. GEOMAR centering trick: image a checkerboard half-in/half-out
  of water; adjust until no refraction discontinuity
  ([dome calibration paper](https://www.geomar.de/fileadmin/personal/fb2/mg/kkoeser/domecalibration_preprint.pdf)).
- CSI ribbons: reliable ~20 cm stock, ~50 cm with good cables. **EMI from six
  ESCs is the documented failure mode** (camera not detected, corrupted
  frames) — route ribbons away from ESC leads; ferrite/foil if needed.
- Community consensus validates no-lights in turbid shallow daylight
  ("high beams in fog"); STARVIS-class sensors in murky water get strongly
  positive reports. Get the IR-cut version. Aim cameras horizontal or
  slightly up — not down into the silt.
- Cheap flanged CCTV domes work if you buy several and select the best by
  star test; the flange seal is the entire engineering problem. BR's 2" dome
  (~$40) is the known-good fallback if cheap domes ruin the stereo cal.

## Kayak operations

- **Anchor or beach before flying** — solo live-boating is a 3-person task
  scaled to one. Clump weight 1–2 m down the tether decouples surface
  bobbing and kayak drift. Deploy up-current.
- Hand-spool / figure-8 coil beats a drum reel at 20 m; a slip ring is a
  100BASE-TX liability and unnecessary (router-on-reel, Trident pattern).
- Kayak anglers routinely fly ~$1,000 tethered ROVs solo from sit-on-tops:
  spool in lap, phone clamped to a rail mount. A glare hood and phone mount
  matter more than any network spec.
- OpenROV Trident productized CARP's exact topside: neutral tether → WiFi
  buoy/box → phone. Its discontinuation (app support died 4 years after
  launch) is the standing argument for the open ArduSub/ROS 2 stack.

## Reference builds

| Build | Why it matters | Link |
|---|---|---|
| AL3X mini BlueROV2 (2026) | Cheap thrusters + Pi 5 + direct Ethernet + Cockpit — closest architecture match | [BR forum](https://discuss.bluerobotics.com/t/a-more-affordable-6-dof-mini-bluerov2-build/22815) |
| Halo AUV (2023) | Pixhawk + ArduSub + Pi + Cat5e + 6 thrusters + ROS 2; thin pymavlink bridge nodes instead of mavros — study before writing CARP ROS code | [project page](https://oubrejames.github.io/halo_auv/) |
| Orca4 | ROS 2 + ArduSub reference plumbing (GUIDED, vision position); note its author is moving *off* mavros | [GitHub](https://github.com/clydemcqueen/orca4) |
| Cave Pearl Project | The PVC housing recipe, plus DIY pressure/leak testing science | [site](https://thecavepearlproject.org/category/diy-underwater-housings/) |
| CPS 5 | 85 m on 3D-printed + acrylic; source of the solder-blob-in-pot rule | [Hackaday](https://hackaday.com/2022/11/02/3d-printed-rov-is-the-result-of-many-lessons-learned/) |
| Wurzburg SimpleROV (2025) | ArduPilot dev's 3-thruster PVC build; test-plug closure datapoint; "don't build in 2-inch pipe" | [ArduPilot blog](https://discuss.ardupilot.org/t/simple-low-cost-diy-ardusub/135827) |
| BlueROV1 (2015) | The original: 6 thrusters, Pixhawk FMUv2 + Pi, potted-bolt penetrators — CARP is this, rebuilt cheaper | [docs](https://docs.bluerobotics.com/bluerov/) |
| OpenROV 2.x | Endcap tolerance-stackup failures, thin-tether findings, servo camera tilt win | [forum archive](https://forum.openrov.com) |

## Archives to mine

- [discuss.bluerobotics.com](https://discuss.bluerobotics.com) — ArduSub integration, active
- [homebuiltrovs.com forum](https://www.homebuiltrovs.com/rovforum/) — PVC-specific technique
- [forum.openrov.com](https://forum.openrov.com) — sealing/tether archive
- [MATE tech reports](https://materovcompetition.org/archives) — brutally honest failure write-ups
- [Cave Pearl Project](https://thecavepearlproject.org/category/diy-underwater-housings/) — housing/testing science
