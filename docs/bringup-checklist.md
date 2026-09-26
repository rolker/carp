# Bring-Up Checklist

Order matters. Every item below happens **before** anything is potted, sealed,
or epoxied.

## Phase 0 — Before hardware arrives

- [ ] ArduSub in SITL
- [ ] Frame type selected and confirmed in simulation
- [ ] Joystick/gamepad mapping worked out
- [ ] Verify axis signs in sim — sign errors are cheap here and expensive in a pond
- [ ] **Camera geometry + housing layout on paper — before any pipe is bought**
      (review 2 MA2). Drawn: see `housing-layout.md` — 6" single housing,
      74 mm stereo baseline (set by the bore and the 71.9 flange, not chosen). Confirm the
      five assumed dimensions in that file before any pipe is cut
- [ ] ADR-017 stack confirmed by the CSI/encode bench prototype (dual capture
      → encode → phone stream → rosbag) before Phase 3 integration
- [x] **Print toolchain validated** (2026-08-30) — Onshape → slice → Centauri
      Carbon 2, first part a bench holder for the Pi 5 in PLA+. Bracket and
      mount design is unblocked; carry designs forward but reprint in PETG
      (inside the hull) or ASA (outside) per the material rule in `bom.md`

## Phase 1 — Autopilot acceptance (within the return window)

Run the day it arrives. A bad board goes back inside the window.

- [ ] Flash ArduSub, confirm boot, QGC connects
- [ ] IMU noise on a still bench — obvious spikes or drift means return it
- [ ] Power module holds 5 V under a couple of amps
- [ ] Calibrate `BATT_VOLT_MULT` against a meter (Radiolink units are known to read low)
- [ ] MS5837 on I2C, set `BARO_EXT_BUS`, confirm depth reads
- [ ] Confirm reported baro device type — 0x12 for 30BA, 0x18 for 02BA. Misidentification fails *silently* with plausible wrong depth
- [ ] SD card write and read
- [ ] Exercise all PWM outputs against servo or scope
- [ ] Set `BRD_SAFETYENABLE = 0` (ADR-007)

## Phase 2 — Thruster acceptance

Per unit, on the servo tester, no autopilot involved.

- [ ] **Set the tester pot to centre before applying power.** It boots into
      manual mode following knob position, *not* 1500 µs
- [ ] **Clamp the thruster down.** Bidirectional units jump on connect
- [ ] Check which U2 variant arrived and whether its ESC has a BEC (the
      150 W variant ships one, 5 V/1 A). If yes it can feed the tester; if
      not, any USB charger or bench supply works
- [ ] If ESCs have BECs: plan the servo-rail wiring so at most one BEC's 5 V
      line lands on the rail — six paralleled BECs fight
- [ ] Confirm rotation direction, sort CW/CCW pairs before mounting
- [ ] Find true neutral and map deadband width (tester resolves 2 µs)
- [ ] Verify bidirectional behaviour across 1000–2000 µs
- [ ] Bucket + kitchen scale: measure **actual** thrust both directions at known
      pulse widths. Specs are consistently optimistic
- [ ] 20 min continuous run, hand on the can, note temperature
- [ ] Clamp-meter the current draw against the 150 W spec
- [ ] All four/six simultaneously — combined draw against the pack

## Phase 3 — Integration, still dry

- [ ] Pixhawk → ESCs, wired to the frame diagram's output numbering
- [ ] Common ground between ESC power and signal — floating grounds produce
      phantom twitches
- [ ] Star-point grounding verified with a meter under load
- [ ] `MOT_n_DIRECTION` corrections rather than rewiring
- [ ] Servo tester inline between Pixhawk and one ESC — read what ArduSub is
      actually commanding
- [ ] Pi 5 boots, NVMe mounts, `usb_max_current_enable=1` set
- [ ] Cameras stream, encode, and record to NVMe
- [ ] rosbag records with keyframe interval 1–2 s, plays back in Foxglove
- [ ] Thermal soak — everything running, **45 min** (review 1 minor 10; 30 was
      a transcription drift), check converter and NVMe temps
- [ ] Measure the real tether link: iperf3 through the actual CCA Cat6 + Opal.
      Record the negotiated rate — the ADR-016 offload plan depends on it —
      and sum the operating load (2× video + MAVLink + ROS topics) against it
- [ ] Topside qualification: router in the dry box on bank power, phone at
      operating distance, Cockpit + gamepad running ~30 min under motion —
      confirm no WiFi dropout (review 2 minor 7)

## Phase 4 — Housing

- [ ] Vacuum test via Schrader stem (core out): **15 inHg** (≈5.2 m — the
      site depth; 10 inHg only proves 3.5 m), steady needle for a minute,
      housing **empty**
- [ ] Main fuse installed at the star point and verified (see wiring.md)
- [ ] Leak probe at the low point wired to Pixhawk AUX; `FS_LEAK = surface`
      set and bench-tripped
- [ ] If it fails: 2–3 psi from a bike pump (core in) + soapy water on every
      joint to find the leak, then re-test under vacuum
- [ ] Leak test again with a paper towel inside and nothing valuable
- [ ] Relief/vent path confirmed: Schrader stem, core in for diving; verify
      the core tool cracks it and **always vent before opening the lid**
      (ADR-013)
- [ ] Thermal paths: NVMe, converters, and ESCs padded to the hull wall
- [ ] Internal baro logged as a leak detector — rising internal pressure means
      water displacing air
- [ ] Spare o-rings on hand before first close-up

## Phase 5 — First water

- [ ] Ballast to slightly positive (ADR-002)
- [ ] Tether quick-release to a deck cleat, **never to your body**
- [ ] Confirm it surfaces on power-off
- [ ] Depth hold, shallow
- [ ] All axes on the joystick, confirm signs match expectation
- [ ] Full dive on one pack, log actual endurance against the ~110 W
      no-lights estimate (~39 min to 20% reserve)
- [ ] **Snag drill** (review 2 / ADR-009): with the real rigging, gentle
      haul-test from multiple bearings; practice slack-and-drive; confirm the
      buoy-and-return kit is aboard. A protocol never rehearsed isn't one
- [ ] Run the whole day from `field-checklist.md` — shake it down while the
      stakes are low

## Deferred until it swims

- `udp_bridge` and Project11 operator station
- Optical flow
- Acoustic ranging

Both of the latter are projects in their own right and neither blocks
inspecting a contact.
