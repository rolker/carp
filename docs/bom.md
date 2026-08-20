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
| 8BitDo Ultimate Mobile controller | 1 | Amazon (8BitDo) | — | 49.99 | ordered | Hall sticks. Telescopic phone-grip, Bluetooth/Android only — the field controller for Cockpit. **No wired USB / PC mode**: bench SITL needs a separate pad or keyboard |
| Gebildet PG7 ×30 + PG9 ×20 cable glands | 1 | Amazon (Gebildet) | 10 | 9.99 | ordered | Penetrators: gland + epoxy back-fill, solder-blob every conductor mid-pot (prior-art.md) |
| Anker 10,000 mAh PowerIQ USB-C power bank | 1 | Amazon (AnkerDirect) | — | 45.99 | ordered | Topside: runs the Opal ~10 h. Bench-qualify: router on it one hour, no blinks |
| GL.iNet GL-SFT1200 Opal router | 1 | Amazon (GL Tech) | 40 | 39.99 | ordered | Topside AP. Configure LAN 192.168.2.0/24; 5 GHz AP so the BT gamepad keeps 2.4 GHz |
| Loctite Marine Epoxy 0.85 oz syringe | 2 | Amazon | 15 | 15.00 | ordered | Arriving Sunday. ~50 ml total — enough for ~8–12 gland back-fills; buy more before doing all penetrators in one session |
| Amass XT60 pairs w/ 14 AWG 100 mm pigtails | 2 pk | Amazon (Hiteuoms) | 10 | 17.98 | ordered | "6PCS" per pack — **count on arrival**: if that means 3 pairs/pack, the 6 pairs total exactly covers 6 ESC drops with zero spares. Female on the source side |
| SanDisk 256 GB Ultra microSDXC + adapter | 1 | Amazon (First Choice Online) | 12 | 56.00 | ordered | NAND-crisis pricing. Pi boot/rescue + interim bench recording. Third-party seller — **verify genuine** (h2testw/f3) |
| Marine-grade adhesive heat-shrink kit, 4:1 | 1 | Amazon (LONGBIN) | 8 | 8.99 | ordered | Adhesive-lined = the right kind for wet-adjacent joints |
| 10 AWG silicone wire, 5 ft red + 5 ft black | 1 | Amazon (Kenhihi) | 15 | 8.98 | ordered | Pack → star point runs |
| Cordless USB-C soldering iron | 1 | Amazon (AutoFittings) | — | 28.99 | ordered | Fine for signal wiring; 10 AWG + XT90 cups need more heat — have a ≥60 W mains iron for the big joints |
| Cat6 outdoor direct-burial, 100 ft, **CCA** | 1 | Amazon (FYRIKTB) | 25 | 21.99 | ordered | Tether stock: two ~50 ft tethers incl. spare. CCA fatigues under flex — gentle bends, hard strain relief, treat as consumable. Data-only at this length: fine |
| 14 AWG silicone wire, 2-core, 25 ft | 1 | Amazon (Haerkn) | 10 | 19.98 | ordered | Distribution → ESC runs; 2-core = paired +/− pulls |
| FEICHAO 35 V 1000 µF XT60 cap filters ×4 | 1 | Amazon (FEICHAO) | 15 | 39.96 | ordered | **Arrives Sept 8–16** (China lead time). 4,000 µF total at the star point. Bench Phases 1–3 can run without them — short bench leads = low inductance — but install before sealed integration; Castle CapPack is the local fallback if the housing outpaces the mail |
| LiPo safe pouches, 185×75×60 mm ×2 | 1 | Amazon (CNDHDOK) | 12 | 9.99 | ordered | One pouch per pack — isolation during storage and charging. Arrives with the batteries |
| BX100 cell checkers w/ LV buzzer ×2 | 1 | Amazon (SpeedyFPV) | 8 | 9.49 | ordered | Arrives Saturday — Friday's first charge relies on the charger's own per-cell display. Plug-read-unplug; standby drain unbalances packs left connected |
| BOJACK MIDI 80 A fuses ×3 + holders ×2 | 1 | Amazon (BOJACK) | 15 | 21.98 | ordered | Main fuse at the star point (review B1) + two spare elements and a spare holder — field-box spares covered |
| IP68 RJ45 panel-mount coupler, F-F ×2 | 1 | Amazon | — | 15.99 | ordered | Topside dry box wall only — splash-rated, **never submerged** (prior-art: IP67/68 couplers are not pressure-rated). Second is the spare |
| Tomotato transparent waterproof dry box | 1 | Amazon | 20 | 17.99 | ordered | Topside station: Opal + power bank; tether enters via PG9 gland or the panel coupler. Confirm it floats loaded; leash to kayak |
| Hand vacuum pump / brake bleeder kit w/ gauge | 1 | Amazon (Pathfinder Auto) | 35 | 19.89 | ordered | The pre-dive leak-test tool: **15 inHg** via the Schrader stem (core out), watch for a steady needle. Check kit for a Schrader adapter; verify pump holds vacuum dead-headed on arrival |

**Ordered subtotal: est ~$1,215 (+4 unestimated adds) · paid $1,698.98
(Amazon orders through 2026-08-20 + RobotShop $140.69 + $168.74 incl.
shipping — per-order figures in git history).**

## Core, pending

| Item | Qty | Source | Est $ | Paid $ | Status | Notes |
|---|---|---|---|---|---|---|
| M.2 HAT+ | 1 | | 20 | | pending | |
| NVMe 512 GB–1 TB | 1 | | 70–160 | | pending | Thermal path to hull wall required. NAND-crisis pricing: ~$105/TB best case as of Aug 2026, relief not expected before 2027. 512 GB (~$70) still holds a week of dive days — capacity was never the constraint (ADR-016). Not needed until thermal soak / sealed integration; bench bring-up runs on microSD |
| 4" PVC, caps, o-rings | — | | 60 | | pending | |
| Hollow polypro rope + closed-cell foam floats for tether | 1 | | 10 | | pending | Cable ordered (Cat6 burial). Rope is the strength member (SV Seeker method); foam bits zip-tied every 1–2 m near the ROV. Seal cable cut ends |
| HDPE frame stock, ballast | — | | 30 | | pending | |
| External I2C compass module | 1 | | 15–30 | | pending | Review 1 M3 / review 2 carry-forward: internal compass sits in ESC field; mount external, away from power wiring, MagFit calibrate in Phase 3/5 |

**Core pending subtotal (est): ~$205–310** depending on NVMe capacity

## Small parts and consumables, pending

Previously mentioned in notes but never costed as line items.

| Item | Qty | Source | Est $ | Paid $ | Status | Notes |
|---|---|---|---|---|---|---|
| FC pigtails — **verify DF13 vs JST-GH on arrival** | set | | 0–15 | | pending | Classic Pixhawk 1/FMUv2 = DF13, not JST-GH. Radiolink usually includes a cable set and the Bar30 ships with its own I2C lead — inventory Friday, order only the gap |
| Schrader valve stem + core tool | 1 | | 8 | | pending | **NOT yet ordered.** One fitting, three jobs: pressure test (bike pump, core in), vacuum test (bleeder pump, core out — check the kit for a Schrader adapter), LiPo relief/equalization. Auto-parts store |
| Thermal pads / gap filler | — | | 12 | | pending | NVMe, converters, ESCs to hull wall |
| MicroSD 16–32 GB for Pixhawk, FAT32 | 1 | | 7 | | pending | Only if the Radiolink box card is junk — FMUv2 likes small plain cards |
| Spare o-rings, every size | kit | | 15 | | pending | **Before first assembly.** A nicked o-ring on a Sunday ends the day |
| Silicone grease | 1 | | 12 | | pending | **Molykote 111 or Super Lube only.** Petroleum products attack Buna-N |
| **Leak probe** (bare-wire pair or SOS-style) | 1 | | 5 | | pending | Low point of the hull → Pixhawk AUX, `FS_LEAK = surface`. Review M8. Expect condensate false alarms — mount above the sweat line, test the failsafe |
| Indicating silica desiccant packs | — | | 5 | | pending | Cave Pearl recipe; oversize for a Pi 5 sweating in a cold lake |
| Spare 2" acrylic dome | 1 | | 11 | | pending | Review 2 minor 5: single-seller part, "handle gently" — a cracked dome mid-season ends the mission |
| Spare XT90-S male connector | 1 | | 8 | | pending | Review 2 MA3: anti-spark resistor is a consumable (~30–50 matings); lives in the field box |
| ApisQueen ESC tuning tool | 1 | | 12–15 | | pending | **Hold — compatibility unconfirmed.** O'Hara card = boat ESC line; Feather USB board = 80–300 A standalone ESCs; unclear which (if either) programs the U2's integrated ESC. Check the manual on arrival or email help@underwaterthruster.com. Only needed if depth hold is jerky and ArduSub deadzone params can't fix it |

**Small parts subtotal (est): ~$105**

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
| Wired/X-input gamepad for bench SITL | ? | The 8BitDo Ultimate Mobile (ordered) is Android-only — desktop QGC/SITL needs any pad the laptop recognizes |
| RJ45 crimper + plugs | ? | Required: tether ends get cut to pass through glands, then re-terminated. CCA strands are brittle — crimp gently, strain-relieve behind the plug |
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

## Shop tooling (household tools — excluded from build totals)

Bought because CARP needs printed brackets/mounts, but it's a general shop
tool serving other projects too, so it doesn't count against the vehicle cost.

| Item | Qty | Source | Paid $ | Status | Notes |
|---|---|---|---|---|---|
| Elegoo Centauri Carbon 2 Combo | 1 | Amazon (ELEGOO Official US) | 378.61 | Arrives Sat 2026-08-22 | Enclosed CoreXY, 256 mm³, 350 °C hardened nozzle, HEPA+carbon filter; Combo = CANVAS multi-color unit included |
| ELEGOO PLA+ 1.75 mm, pink & purple 2 kg | 1 | Amazon (ELEGOO Official US) | 28.99 | Arrives 2026-08-21 | Toys / learning / doll wheelchair |
| ELEGOO PETG 1.75 mm, yellow & orange 2 kg | 1 | Amazon (ELEGOO Official US) | 26.58 | Arrives 2026-08-21 | Wet-environment parts; high-vis colors are a feature underwater |
| ELEGOO PLA+ 1.75 mm, white 1 kg | 1 | Amazon (ELEGOO Official US) | 13.24 | Arrives 2026-08-21 | General purpose |

**Shop tooling subtotal: $447.42 · out of pocket $371.37** (rewards points −$76.05)

Still pending for the print shop: **ASA 1 kg** (~$20 — exterior ROV brackets,
UV-stable; needs the enclosure + ventilation), desiccant/dry bags for
filament storage (shared line with the housing desiccant).

Printed parts are brackets and mounts only — **never the pressure boundary**
(FDM layer bonds are not watertight; housing stays PVC/acrylic/epoxy).

## Running totals

| | Est $ | Paid $ |
|---|---|---|
| Ordered | ~1,215 | 1,698.98 |
| Core pending | ~205–310 | |
| Small parts pending | ~105 | |
| Field gear pending | ~55 | |
| **Paid + pending (6 thrusters, no options)** | **~$2,065–2,170** | |
| Shop tooling (excluded from above) | | 371.37 out of pocket |

Confirms `open-questions.md`: this is not a $500 build — it is a ~$2,000
build (≈4×). The projection is Paid ($1,698.98, a known number) plus pending
estimates ($365–470); ordered items ran ~25% over their estimates, so pending
items may too. (Corrected 2026-08-20 per design review M1 — the earlier
"$1,550–1,700" summary mixed estimates for items whose real prices were
already known. Pending re-totaled after review 2 added the compass, spare
dome, and spare XT90-S.)
