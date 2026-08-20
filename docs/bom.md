# Bill of Materials & Procurement Tracker

One row per part: quantity, source, estimated cost, what was actually paid,
and status. **Est** is a planning number; **Paid** is filled in when the order
is placed. Statuses: `ordered` → `received` → installed; `pending` = not yet
bought; `later` = deliberate deferral.

## Ordered

| Item | Qty | Source | Est $ | Paid $ | Status | Notes |
|---|---|---|---|---|---|---|
| Radiolink Pixhawk Advanced | 1 | RobotShop | 60 | 159.82 | shipped | FMUv2 / STM32F427. **Not** the Radiolink Pixhawk 4 — that one is ArduPilot-incompatible (proprietary binaries, wrong connectors). Shipped separately, +8.92 shipping |
| Pololu D36V50F5 | 1 | RobotShop | 25 | 39.95 | shipped | 5 V @ 5.5 A. Honest ratings, real thermal path |
| Digital RC servo tester | 1 | RobotShop | 20 | 10.74 | shipped | Manual mode holds settable pulse width, 2 µs resolution, PPM passthrough display |
| Bar30 pressure sensor (Blue Robotics R2) | 1 | RobotShop | 85 | 90.00 | shipped | MS5837-30BA, potted in penetrator. See ADR-006 |
| 4S 6000 mAh LiPo (YOWOO, 100C, XT90-S) | 2 | Amazon | 84 | 131.98 | ordered | 65.99 ea. Anti-spark XT90-S as specified in ADR-013 |
| Dual LiPo balance charger/discharger, 10 A | 1 | Amazon | 60 | 67.19 | ordered | |
| XT90-S pairs w/ 150 mm 10 AWG pigtails (Amass) | 3 pr | Amazon | 12 | 14.99 | ordered | Pigtails help but bulk 10 AWG still needed |
| XT90 male → XT60 female adapters (OliRC) | 3 | Amazon | 8 | 8.99 | ordered | Charging only (6 A, nowhere near limit) |
| ApisQueen U2 + ESC, 3.75 lbf | 6 | Amazon (ApisQueen) | 390 | 389.88 | ordered | 64.98 ea, two line items of 3. **Verify handedness on arrival** — counter-rotating pairs needed and the two listings carried identical titles |
| Raspberry Pi 5 8 GB | 1 | Amazon (MemoryWhiz, 3rd party) | 110 | 200.00 | ordered | $175 at PiShop — ~$25 premium for fast arrival. Third-party seller: **verify genuine on arrival** (board markings, boots official OS). 8 GB doubles the 4 GB minimum — welcome DSP headroom |
| Arducam IMX462 color 141° (stereo pair) | 2 | Amazon (UCTRONICS) | 96 | 95.98 | ordered | 47.99 ea. Parallel mount, ~75–100 mm baseline, one rigid plate, software sync. **On arrival: verify Pivariety driver works on Pi 5 inside the return window** |
| SupremeTech 2" acrylic dome, 3/8" flange | 2 | Amazon (Supreme Tech) | 21 | 21.38 | ordered | 10.69 ea, pre-drilled flanges. No spares ordered — handle gently; check apex optical uniformity on arrival |

**Ordered subtotal: est ~$970 · paid $1,239.82 (Amazon $613.03 + $200.00 +
$117.36 + RobotShop $140.69 + $168.74 incl. shipping).**

## Core, pending

| Item | Qty | Source | Est $ | Paid $ | Status | Notes |
|---|---|---|---|---|---|---|
| M.2 HAT+ | 1 | | 20 | | pending | |
| NVMe 512 GB–1 TB | 1 | | 70–160 | | pending | Thermal path to hull wall required. NAND-crisis pricing: ~$105/TB best case as of Aug 2026, relief not expected before 2027. 512 GB (~$70) still holds a week of dive days — capacity was never the constraint (ADR-016). Not needed until thermal soak / sealed integration; bench bring-up runs on microSD |
| GL.iNet GL-SFT1200 "Opal" router | 1 | | 40 | | pending | Topside AP on the kayak, USB-C powered from a power bank. Gigabit ports matter for lunch-break rosbag offload (ADR-016). Configure LAN as 192.168.2.0/24 — ArduSub/QGC convention |
| 4" PVC, caps, o-rings | — | | 60 | | pending | |
| Penetrators + potting epoxy | — | | 30 | | pending | Count them: tether, thrusters ×4–6, lights ×2–3, Bar30, lasers |
| 20 m gel-filled direct-burial Cat5e + hollow polypro rope + foam floats | 1 | | 25 | | pending | Burial cable resists water wicking; rope is the strength member (SV Seeker method); foam bits zip-tied every 1–2 m near the ROV. Seal cut ends. Treat as a consumable — buy enough for a spare |
| HDPE frame stock, ballast | — | | 30 | | pending | |

**Core pending subtotal (est): ~$250–370** depending on NVMe capacity

## Small parts and consumables, pending

Previously mentioned in notes but never costed as line items.

| Item | Qty | Source | Est $ | Paid $ | Status | Notes |
|---|---|---|---|---|---|---|
| 10 AWG silicone wire | few m | | 15 | | pending | Pack → distribution |
| 14 AWG silicone wire | few m | | 10 | | pending | Distribution → ESCs |
| XT60 connector pairs | 8 | | 10 | | pending | Distribution to individual ESCs, ~10 A each |
| JST-GH pigtails, pre-crimped | set | | 15 | | pending | Hand-crimping GH is miserable |
| Small UBEC, sensor rail | 1 | | 10 | | pending | Derate to 2–3 A (see power-budget.md) |
| Schrader valve + fitting | 1 | | 10 | | pending | Leak-test port in endcap (ADR-001) |
| Thermal pads / gap filler | — | | 12 | | pending | NVMe, converters, ESCs to hull wall |
| MicroSD cards | 2 | | 12 | | pending | Pi 5 first boot / flashing; Pixhawk spare |
| Spare o-rings, every size | kit | | 15 | | pending | **Before first assembly.** A nicked o-ring on a Sunday ends the day |
| Silicone grease | 1 | | 12 | | pending | **Molykote 111 or Super Lube only.** Petroleum products attack Buna-N |
| Cell-voltage checker with alarm | 1 | | 8 | | pending | |
| LiPo-safe bag or ammo can | 1 | | 12 | | pending | |
| Mityvac-style hand vacuum pump | 1 | | 35 | | pending | Auto-parts brake bleeder. Pull ~10 inHg via the vent nipple before every wet day — the universal pre-dive ritual (prior-art.md) |
| Vent plug / brass barb for vacuum nipple | 1 | | 8 | | pending | Triple duty: vacuum test port, LiPo relief path (ADR-013), equalize-before-opening |
| Bulk capacitor for power distribution | 1–2 | | 8 | | pending | 6 thrusters slamming reverse sags the bus — brownout is the classic cheap-ESC field failure |
| ApisQueen USB ESC tuning board | 1 | | 12 | | pending | Adjusts start/stop sensitivity if depth hold gets jerky |

**Small parts subtotal (est): ~$200**

## Field / mission gear, pending

| Item | Qty | Source | Est $ | Paid $ | Status | Notes |
|---|---|---|---|---|---|---|
| Downline: weighted marker, line, small surface float | 1 | | 25 | | pending | The primary navigation datum (navigation.md Method 1) |
| Quick-releases / carabiners | 2 | | 10 | | pending | Tether and rode, **both to the boat, neither to the body** |
| Milk crate for tether flake | 1 | | 0 | | pending | Probably free |
| Drift sock | 1 | | 20 | | pending | Station-keeping at anchor; optional |

**Field gear subtotal (est): ~$55**

## Likely already owned — confirm

| Item | Have? | Notes |
|---|---|---|
| Multimeter with DC current clamp | ? | Verify actual thruster draw against the 150 W spec without breaking the circuit |
| Joystick / gamepad | ? | Needed for Phase 0 SITL |
| Bike pump | ? | Leak testing |
| Kitchen scale + bucket | ? | Thrust measurement, Phase 2 |
| Topside laptop | ? | QGC + Foxglove |
| USB power bank | ? | Powers the Opal (~3 W → 10k mAh ≈ 10 h). Must not auto-shutoff at ~0.5 A load — check for trickle/always-on mode and bench-test an hour. Use A-to-C cable for guaranteed plain 5 V |
| Bluetooth gamepad | ? | Pairs to phone/tablet for QGC — virtual on-screen sticks are a poor way to fly an ROV |
| Kayak, anchor, rode | ? | The surface platform |

## Options / later

| Item | Est $ | Notes |
|---|---|---|
| Parallel green line lasers | 20 | Scaling **and** altitude for optical flow. Green penetrates turbid water far better than red |
| USB audio interface, 96–192 kHz multichannel | 100–200 | Acoustic ranging. CM6206-class does 96k stereo |
| 27 mm piezo discs + polyurethane | 20 | Transducers. Work far better underwater than they should |
| 12 V LiFePO4 pack | 50 | Hotel only — BMS current limit rules out propulsion |
| Single small diffuse light, potted | 20 | Shadowed-structure inspection; required for deeper sites (ADR-004) |
| Down/nav camera + optical flow | 100 | Deferred past v1. For ambient ops prefer mono IMX296 + fast CS lens over OV9281 |
| Ethernet switch, small internal | 15 | Only needed if IP/multiple Ethernet cameras return |
| 4" dome port for main housing | 40 | Retired by the twin mini-dome camera pods (ADR-003/015); revisit if a high-res camera goes in the main tube |
| VESC (single) | 60–100 | Vertical axis only. FOC gives smooth control through zero |
| Surface buoy: float, GNSS, WiFi/LoRa | ? | ADR-009's preferred architecture; not yet scoped |

## Deliberately not buying

| Item | Why |
|---|---|
| Blue Robotics Navigator | ADR-008 |
| Fathom-X tether interface | Unnecessary under ~50 m; saves ~$100 |
| Echosounder for altitude hold | Blows budget; lasers + optical flow substitute |
| XT60 on the main power path | 60 A rated vs ~61 A peak. Thermal bottleneck in a sealed tube |

## Running totals

| | Est $ | Paid $ |
|---|---|---|
| Ordered | ~970 | 1,239.82 |
| Core pending | ~250–370 | |
| Small parts pending | ~200 | |
| Field gear pending | ~55 | |
| **Committed + planned (6 thrusters, no options)** | **~$1,550–1,700** | |

Confirms `open-questions.md`: this is not a $500 build. Ordered items ran ~24%
over estimate (Pixhawk 159.82 vs 60 est, batteries 131.98 vs 84; thrusters on
the nose). If the pending items overrun similarly, expect **$1,600–1,700
all-in** before options.
