# Bill of Materials & Procurement Tracker

One row per part: quantity, source, estimated cost, what was actually paid,
and status. **Est** is a planning number; **Paid** is filled in when the order
is placed. Statuses: `ordered` → `received` → installed; `pending` = not yet
bought; `later` = deliberate deferral.

## Ordered

| Item | Qty | Source | Est $ | Paid $ | Status | Notes |
|---|---|---|---|---|---|---|
| Radiolink Pixhawk Advanced | 1 | RobotShop | 60 | 159.82 | received | FMUv2 / STM32F427. **Not** the Radiolink Pixhawk 4 — that one is ArduPilot-incompatible (proprietary binaries, wrong connectors). Shipped separately, +8.92 shipping |
| Pololu D36V50F5 | 1 | RobotShop | 25 | 39.95 | received | 5 V @ 5.5 A. Honest ratings, real thermal path |
| Digital RC servo tester | 1 | RobotShop | 20 | 10.74 | received | Manual mode holds settable pulse width, 2 µs resolution, PPM passthrough display |
| Bar30 pressure sensor (Blue Robotics R2) | 1 | RobotShop | 85 | 90.00 | received | MS5837-30BA, potted in penetrator. See ADR-006 |
| 4S 6000 mAh LiPo (YOWOO, 100C, XT90-S) | 2 | Amazon | 84 | 131.98 | received | 65.99 ea. Anti-spark XT90-S as specified in ADR-013 |
| Dual LiPo balance charger/discharger, 10 A | 1 | Amazon | 60 | 67.19 | received | |
| XT90-S pairs w/ 150 mm 10 AWG pigtails (Amass) | 3 pr | Amazon | 12 | 14.99 | received | Pigtails help but bulk 10 AWG still needed |
| XT90 male → XT60 female adapters (OliRC) | 3 | Amazon | 8 | 8.99 | received | Charging only (6 A, nowhere near limit) |
| ApisQueen U2 + ESC, 3.75 lbf | 6 | Amazon (ApisQueen) | 390 | 389.88 | received | 64.98 ea, two line items of 3. **Verify handedness on arrival** — counter-rotating pairs needed and the two listings carried identical titles |
| Raspberry Pi 5 8 GB | 1 | Amazon (MemoryWhiz, 3rd party) | 110 | 200.00 | received | $175 at PiShop — ~$25 premium for fast arrival. Third-party seller: **verified genuine 2026-09-26** — revision `d04171` (8 GB, Sony UK, Pi 5 Rev 1.1), 7.8 GiB reported, boots Ubuntu 24.04 (kernel 6.8.0-1064-raspi). 8 GB doubles the 4 GB minimum — welcome DSP headroom |
| Arducam IMX462 color 141° (stereo pair), **SKU B0444 — Pivariety** | 2 | Amazon (UCTRONICS) | 96 | 95.98 | received | 47.99 ea. Parallel mount, one rigid plate, software sync. Camera connector is **22-pin 0.5 mm**; ships with 22↔22 Type B cables — plugs into the Pi 5 directly. **Baseline is 74 mm** — set by the 6" bore and the measured 71.9 dome flange, not chosen (`housing-layout.md`). **Both verified on the Pi 5 (2026-09-26):** Pivariety driver binds on stock Ubuntu 24.04 and both stream raw 1080p (ADR-017 evidence) |
| SupremeTech 2" acrylic dome, 3/8" flange (radial width; 2.0 thick) | 2 | Amazon (Supreme Tech) | 21 | 21.38 | received | 10.69 ea, pre-drilled flanges. No spares ordered — handle gently; check apex optical uniformity on arrival |
| 8BitDo Ultimate Mobile controller | 1 | Amazon (8BitDo) | — | 49.99 | received | Hall sticks. Telescopic phone-grip, Bluetooth/Android only — the field controller for Cockpit. **No wired USB / PC mode**: bench SITL needs a separate pad or keyboard |
| Gebildet PG7 ×30 + PG9 ×20 cable glands | 1 | Amazon (Gebildet) | 10 | 9.99 | received | Package marked E271 — PG7/PG9 count not yet checked. Penetrators: gland + epoxy back-fill, solder-blob every conductor mid-pot (prior-art.md) |
| Anker 10,000 mAh PowerIQ USB-C power bank | 2 | Amazon (AnkerDirect) | — | 45.99 | received | Two arrived (2-pack at $45.99). Topside: runs the Opal ~10 h. Bench-qualify: router on it one hour, no blinks |
| GL.iNet GL-SFT1200 Opal router | 1 | Amazon (GL Tech) | 40 | 39.99 | received | Topside AP. Configure LAN 192.168.2.0/24; 5 GHz AP so the BT gamepad keeps 2.4 GHz |
| Loctite Marine Epoxy 0.85 oz syringe | 2 | Amazon | 15 | 15.00 | received | Arriving Sunday. ~50 ml total — enough for ~8–12 gland back-fills; buy more before doing all penetrators in one session |
| Amass XT60 pairs w/ 14 AWG 100 mm pigtails | 2 pk | Amazon (Hiteuoms) | 10 | 17.98 | received | **3 pairs per pack** ("6PCS" = pieces) — 6 pairs total, exactly one per ESC drop, **zero spares**. See spare XT60 row below. Female on the source side |
| SanDisk 256 GB Ultra microSDXC + adapter | 1 | Amazon (First Choice Online) | 12 | 56.00 | received | NAND-crisis pricing. Pi boot/rescue + interim bench recording. Third-party seller — **verified genuine 2026-09-26** (`f3probe --destructive` on the EeePC reader: "the device is the real thing") |
| Marine-grade adhesive heat-shrink kit, 4:1 | 1 | Amazon (LONGBIN) | 8 | 8.99 | received | Adhesive-lined = the right kind for wet-adjacent joints |
| 10 AWG silicone wire, 5 ft red + 5 ft black | 1 | Amazon (Kenhihi) | 15 | 8.98 | received | Pack → star point runs |
| Cordless USB-C soldering iron | 1 | Amazon (AutoFittings) | — | 28.99 | received | Fine for signal wiring; 10 AWG + XT90 cups need more heat — have a ≥60 W mains iron for the big joints |
| Cat6 outdoor direct-burial, 100 ft, **CCA** | 1 | Amazon (FYRIKTB) | 25 | 21.99 | received | Tether stock: two ~50 ft tethers incl. spare. CCA fatigues under flex — gentle bends, hard strain relief, treat as consumable. Data-only at this length: fine |
| 14 AWG silicone wire, 2-core, 25 ft | 1 | Amazon (Haerkn) | 10 | 19.98 | received | Distribution → ESC runs; 2-core = paired +/− pulls |
| FEICHAO 35 V 1000 µF XT60 cap filters ×4 | 1 | Amazon (FEICHAO) | 15 | 39.96 | received | **Arrives Sept 8–16** (China lead time). 4,000 µF total at the star point. Bench Phases 1–3 can run without them — short bench leads = low inductance — but install before sealed integration; Castle CapPack is the local fallback if the housing outpaces the mail |
| LiPo safe pouches, 185×75×60 mm ×2 | 1 | Amazon (CNDHDOK) | 12 | 9.99 | received | One pouch per pack — isolation during storage and charging. Arrives with the batteries |
| BX100 cell checkers w/ LV buzzer ×2 | 1 | Amazon (SpeedyFPV) | 8 | 9.49 | received | Arrives Saturday — Friday's first charge relies on the charger's own per-cell display. Plug-read-unplug; standby drain unbalances packs left connected |
| BOJACK MIDI 80 A fuses ×3 + holders ×2 | 1 | Amazon (BOJACK) | 15 | 21.98 | received | **4 fuses arrived** (listing said ×3), 2 holders. Main fuse at the star point (review B1) + two spare elements and a spare holder — field-box spares covered |
| IP68 RJ45 panel-mount coupler, F-F ×2 | 1 | Amazon | — | 15.99 | received | Topside dry box wall only — splash-rated, **never submerged** (prior-art: IP67/68 couplers are not pressure-rated). Second is the spare |
| Tomotato transparent waterproof dry box | 1 | Amazon | 20 | 17.99 | received | **Too small** for the Opal + power bank — needs a bigger box (return or repurpose this one). Topside station: Opal + power bank; tether enters via PG9 gland or the panel coupler. Confirm it floats loaded; leash to kayak |
| Hand vacuum pump / brake bleeder kit w/ gauge | 1 | Amazon (Pathfinder Auto) | 35 | 19.89 | received | The pre-dive leak-test tool: **15 inHg** via the Schrader stem (core out), watch for a steady needle. **Kit checked 2026-10-11: no Schrader adapter** — push-on vinyl hose and barbed adapters only (T, straight, tapered, bleeder-nipple, cup), plus a reservoir jar with two-port lids. The gauge is built into the pump body, so it reads the hull only while the pump stays connected. Still to do: verify the pump holds vacuum dead-headed, and measure the hose inside diameter (sets the barb size) |
| JST-GH ↔ DF13 adapter board, 4-pin | 1 | Blue Robotics | 10 | 13.44 | received | 2026-09-26. Incl. $1.44 tariff surcharge. Board plus 100 mm DF13↔DF13 and GH↔GH cables — Bar30 → Pixhawk I2C with the pinout guaranteed. Unblocks the Phase 1 depth check |
| SOS Leak Sensor | 1 | Blue Robotics | 5 | 35.00 | received | 2026-09-26, same order ($6.50 shipping). Replaces the bare-wire probe: four sponge-tipped probes (2×6", 2×12") + 4 spare tips — needs liquid, not condensate. 3-pin 0.1" out straight to a Pixhawk AUX pin, ArduSub-native, `FS_LEAK = surface`. **Needs 3.3–5 V on the servo rail** — one ESC BEC (U2 BEC still unconfirmed) or a separate 5 V feed |
| uxcell FFC 22-pin 0.5 mm **Type B**, 500 mm, 5 pcs | 1 | Amazon (uxcell) | 7 | 6.47 | received | 2026-09-26, arriving Tue 2026-09-29. Bench, mock-up and fixture cables plus spares — generous enough to connect cameras without fighting for slack. Plain unshielded FFC: the vehicle gets the shortest length that reaches once the sled/bay order is drawn (pending row below) |
| Raspberry Pi 5 Active Cooler (official) | 1 | Amazon (UeeKKoo, 3rd party) | — | 10.95 | received | 2026-09-27, arriving 2026-09-28. ~$5 list — third-party premium, so check it is genuine on arrival. **Fitted 2026-10-10.** ADR-015 re-run with it: 1080p10 holds 50–51 °C (was 64–66 uncooled), 1080p20 holds under 60 °C. Moves SoC heat into the hull air, not out of the hull — pairs with an air-stirring fan or a conduction path (`sled.md`). Clears the M.2 HAT+ (its standoffs are sized for it). Push-pins and pad are one-use-ish: fit it once. Fan speed control works under stock Ubuntu 24.04 (`pwm-fan`, starts at 50 °C, steps up at 60) |
| iRasptek 27 W 5.1 V / 5 A USB-C PD supply | 1 | Amazon (iRasptek) | — | 10.99 | received | 2026-09-27, arriving 2026-09-28. **Bench only** — the vehicle Pi runs from the Pololu off the hotel pack. Fixes the undervoltage the Pi hit on a 4.9 V supply during the build (ADR-017); 5 A lets the Pi 5 run USB peripherals at full current |
| QimKero USB-A → 3.5 mm TRRS sound card dongle, 2-pack | 2 pk | Amazon (QimKero) | — | 13.88 | received | 2026-10-10, received 2026-10-12. 6.94 per pack — **4 dongles**. Cheap-parts bench test of the acoustic ranging idea (`navigation.md` Method 4) before spending on the 96–192 kHz interface in Options. Female TRRS jack: stereo out + mono mic in per dongle. **Seen on arrival (two plugged in, read-only):** USB `001f:0b21` "Generic iStore Audio", full-speed USB; **48 kHz only**, 16-bit, 2 out / 1 in; mixer is just PCM playback switch + volume and Mic capture switch + volume (no auto gain, no mic monitor). **Every unit reports the same serial number**, so only the USB port tells them apart — label them and keep each in its socket. USB descriptors: output endpoint *adaptive* (follows the host's USB clock), input *asynchronous* (the dongle's own clock) — whether output and input on one dongle stay locked is for the loopback offset test. **Still to check:** TRRS pinout and mic bias with a multimeter; loopback offset test; the other two dongles |
| XMSJSIY 3.5 mm TRRS male → 4-pin screw-terminal cable, 32 cm, 2-pack | 2 pk | Amazon (Sissel's Store) | — | 17.20 | received | 2026-10-10 (two orders, 8.60 each), received; confirmed by Roland 2026-10-25 as 2 × 2-packs, so 4 cables in hand (arrival date not recorded). Was arriving 2026-10-11. **4 cables**, 4-pole male plug per the listing ("trrs male" variant) — matches the dongles' female jack. Solderless hookup from the dongles to the breadboard for the acoustic bench test. **Check on arrival:** which terminal is tip / ring 1 / ring 2 / sleeve — buzz it out, don't trust the labels |
| EDGELEC Dupont jumper wire kit, 120 pcs, 20 cm | 1 | Amazon (EDGELEC) | — | 6.98 | received | 2026-10-10, received; confirmed by Roland 2026-10-25 (arrival date not recorded). Was arriving 2026-10-11. Breadboard hookup for the acoustic bench test. Assorted kit — presumably M-M / M-F / F-F, confirm on arrival. 20 cm loose leads pick up noise on the small receive signals: keep the mic-input side short and away from the transmit wiring |
| Chanzon MB-102 solderless breadboard, 830 tie points, 3 pcs | 1 | Amazon (Chanzon) | — | 7.99 | received | 2026-10-10, received; confirmed by Roland 2026-10-25 (arrival date not recorded). Was arriving 2026-10-11. **3 boards** — one per end of the acoustic bench test plus a spare. Generic MB-102 contacts are loose-ish: stranded piezo leads need tinning or header pins to stay put. Power rails on some MB-102 boards are split at mid-length — buzz them out before relying on a rail end to end |
| ALLECIN monolithic ceramic capacitor kit, 24 values, 10 pF–10 µF | 1 | Amazon (ALLECIN E.C. US) | — | 9.99 | received | 2026-10-10, received; confirmed by Roland 2026-10-25 (arrival date not recorded). Was arriving 2026-10-11. For the 1 µF per receive disc; non-polarized, so orientation does not matter. Replaces an electrolytic kit ordered and cancelled the same day. Count the 1 µF parts on arrival — one per receive disc plus spares. Loose tolerance at the high values: measure if a value matters |
| Zorfeter 20 mm piezo discs, 20 pcs | 1 | Amazon (YONWUF) | — | 4.99 | received | 2026-10-10, received by 2026-10-11 (a disc was measured that day). Was arriving 2026-10-11. Bench transducers, smaller size to compare against the 27 mm. Resonance differs between the two sizes — find each by sweep rather than assuming |
| Zorfeter 27 mm piezo discs, 20 pcs, 100 mm leads | 1 | Amazon (YONWUF) | — | 5.99 | received | 2026-10-10, received; confirmed by Roland 2026-10-25 (arrival date not recorded). Was **arriving Mon 2026-10-12** — a day after the rest. The size `navigation.md` names. 20 pcs leaves room to sort by capacitance and pick matched ones |
| AYWFEY 30 AWG stranded hookup wire, 6 colors × 32.8 ft | 1 | Amazon (AYWFEY) | — | 9.99 | received | 2026-10-10, received; confirmed by Roland 2026-10-25 (arrival date not recorded). Was arriving 2026-10-11. Extending the piezo disc leads. Single conductors, not twisted pair or shielded — twist the two leads of each receive disc together by hand to cut pickup. Too thin and limp for breadboard holes: tin the ends or land them in the screw terminals |
| BOJACK resistor kit, 1000 pcs, 25 values 1 Ω–1 MΩ, 5 % ¼ W carbon film | 1 | Amazon (BOJACK ELECTRON) | — | 9.99 | received | 2026-10-10, received; confirmed by Roland 2026-10-25 (arrival date not recorded). Was arriving 2026-10-11. Reference and level-setting resistors for the acoustic bench circuit. **Check the kit has 100 kΩ** and what it offers between 47 k and 470 k. 5 % parts: where two resistors need to match, pick a pair with the multimeter |

**Ordered subtotal: est ~$1,237 (+15 unestimated adds) · paid $1,869.33
(Amazon orders through 2026-08-20 + RobotShop $140.69 + $168.74 incl.
shipping + Blue Robotics $54.94 incl. shipping + uxcell cables $6.47,
2026-09-26 + Active Cooler and bench PSU $21.94, 2026-09-27 + acoustic
bench-test parts $87.00 across six orders, net of two cancelled items,
2026-10-10 — per-order
figures in git history).**

## Core, pending

| Item | Qty | Source | Est $ | Paid $ | Status | Notes |
|---|---|---|---|---|---|---|
| M.2 HAT+ | 1 | | 20 | | pending | |
| NVMe 512 GB–1 TB | 1 | | 70–160 | | pending | Thermal path to hull wall required. NAND-crisis pricing: ~$105/TB best case as of Aug 2026, relief not expected before 2027. 512 GB (~$70) still holds a week of dive days — capacity was never the constraint (ADR-016). Not needed until thermal soak / sealed integration; bench bring-up runs on microSD |
| PVC pipe, caps, o-rings | — | | 60–120 | | pending | **Diameter not settled — do not buy.** `housing-layout.md` leans 6" sched-40 over 4"; gated on the caliper measurements. 6" pipe and caps run ~$40–60 over 4". **Caps → lids (proposal 2026-09-27):** two 3/4" cast acrylic 8 × 8 squares (~$40 each, Falken or Source One), four M6 tie rods, pipe-end O-ring (AS568 2-series, ~6.2" ID) + spares — ~$100 for the closure alone, so this line likely needs raising (`housing-layout.md`, "Endcaps") |
| Hollow polypro rope + closed-cell foam floats for tether | 1 | | 10 | | pending | Cable ordered (Cat6 burial). Rope is the strength member (SV Seeker method); foam bits zip-tied every 1–2 m near the ROV. Seal cable cut ends |
| HDPE frame stock, ballast | — | | 30 | | pending | |
| External I2C compass module | 1 | | 15–30 | | pending | Review 1 M3 / review 2 carry-forward: internal compass sits in ESC field; mount external, away from power wiring, MagFit calibrate in Phase 3/5 |

**Core pending subtotal (est): ~$205–310** depending on NVMe capacity

## Small parts and consumables, pending

Previously mentioned in notes but never costed as line items.

| Item | Qty | Source | Est $ | Paid $ | Status | Notes |
|---|---|---|---|---|---|---|
| DF13 pigtails, 4-pin | set | | 0–10 | | pending | The Bar30 mismatch (JST-GH lead vs DF13 I2C port, confirmed 2026-09-26) is solved by the Blue Robotics adapter in Ordered. Buy DF13 pigtails only if another Pixhawk port needs one — check the Radiolink box first |
| Schrader valve stem + core tool | 1 | | 8 | | pending | **NOT yet ordered.** One fitting, three jobs: pressure test (bike pump, core in), vacuum test (bleeder pump, core out — the kit has no Schrader adapter, checked 2026-10-11), LiPo relief/equalization. Auto-parts store. **Open (2026-10-11):** core out cannot keep a vacuum for the dive, and a core is held shut against vacuum only by its spring — valve type and how to pump through it are undecided (`open-questions.md`) |
| Thermal pads / gap filler | — | | 12 | | pending | NVMe, converters, ESCs to hull wall |
| MicroSD 16–32 GB for Pixhawk, FAT32 | 1 | | 7 | | pending | Only if the Radiolink box card is junk — FMUv2 likes small plain cards |
| Spare o-rings, every size | kit | | 15 | | pending | **Before first assembly.** A nicked o-ring on a Sunday ends the day |
| Silicone grease | 1 | | 12 | | pending | **Molykote 111 or Super Lube only.** Petroleum products attack Buna-N |
| Indicating silica desiccant packs | — | | 5 | | pending | Cave Pearl recipe; oversize for a Pi 5 sweating in a cold lake |
| Spare 2" acrylic dome | 1 | | 11 | | pending | Review 2 minor 5: single-seller part, "handle gently" — a cracked dome mid-season ends the mission |
| Spare XT90-S male connector | 1 | | 8 | | pending | Review 2 MA3: anti-spark resistor is a consumable (~30–50 matings); lives in the field box |
| Spare XT60 pigtail pairs | 2–3 pr | | 8 | | pending | The two packs came as 3 pairs each — 6 pairs for 6 ESC drops, none spare. A melted or mis-soldered one otherwise stops a thruster |
| Pi 5 camera cables, 22↔22-pin, 0.5 mm, **Type B**, vehicle length | 2+2 | | 12 | | pending | **Not blocking the bench test** — the Arducams have 22-pin connectors and shipped with 22↔22 Type B cables (~150 mm) that plug straight into the Pi 5. Needed for the vehicle only, **length from the CAD cable path once the sled and bay order are drawn** — with cameras and Pi both on the sled, Pi right behind the cameras (`sled.md`), the stock ~150 mm cables may reach and this row may not be needed at all; the 500 mm uxcell set (Ordered) covers bench work meanwhile. Match Type B — wrong type makes no contact; never flip one to make it fit. Shortest that reaches; route away from ESC leads |
| ApisQueen ESC tuning tool | 1 | | 12–15 | | pending | **Hold — compatibility unconfirmed.** O'Hara card = boat ESC line; Feather USB board = 80–300 A standalone ESCs; unclear which (if either) programs the U2's integrated ESC. Check the manual on arrival or email help@underwaterthruster.com. Only needed if depth hold is jerky and ArduSub deadzone params can't fix it |

**Small parts subtotal (est): ~$115**

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
| Multimeter with DC current clamp | partly | The Extech EX430 came out of storage (Bench instruments, below), but it is not a clamp meter: its 10 A range measures in series, so the circuit has to be broken. A clamp is still wanted to check thruster draw against the 150 W spec |
| Joystick / gamepad | ? | Needed for Phase 0 SITL |
| Bike pump | ? | Leak testing |
| Kitchen scale + bucket | ? | Thrust measurement, Phase 2 |
| Topside laptop | ? | QGC + ROS 2 rqt tools |
| Wired/X-input gamepad for bench SITL | ? | The 8BitDo Ultimate Mobile (ordered) is Android-only — desktop QGC/SITL needs any pad the laptop recognizes |
| RJ45 crimper + plugs | ? | Required: tether ends get cut to pass through glands, then re-terminated. CCA strands are brittle — crimp gently, strain-relieve behind the plug |
| Kayak, anchor, rode | ? | The surface platform |

## Options / later

| Item | Est $ | Notes |
|---|---|---|
| Parallel green line lasers | 20 | Scaling **and** altitude for optical flow. Green penetrates turbid water far better than red |
| USB audio interface, 96–192 kHz multichannel | 100–200 | Acoustic ranging. CM6206-class does 96k stereo. Hold until the cheap dongle test (Ordered) shows the idea is worth it. The Edirol FA-101 found in storage (Bench instruments) may fill this for the bench, if a FireWire computer can be found |
| Polyurethane potting resin for the piezo discs | 20 | Discs themselves are in Ordered (20 mm and 27 mm, 2026-10-10). Potting is for the wet stage only — not needed for the in-air bench test. Est was for discs + resin together |
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
| Elegoo Centauri Carbon 2 Combo | 1 | Amazon (ELEGOO Official US) | 378.61 | received · **validated 2026-08-30** | Enclosed CoreXY, 256 mm³, 350 °C hardened nozzle, HEPA+carbon filter; Combo = CANVAS multi-color unit included. First part: a bench holder for the Pi 5, Onshape → slice → print, no trouble on the machine side |
| ELEGOO PLA+ 1.75 mm, pink & purple 2 kg | 1 | Amazon (ELEGOO Official US) | 28.99 | received | 2 spools. Toys / learning / doll wheelchair |
| ELEGOO PETG 1.75 mm, yellow & orange 2 kg | 1 | Amazon (ELEGOO Official US) | 26.58 | received | 2 spools. Wet-environment parts; high-vis colors are a feature underwater |
| ELEGOO PLA+ 1.75 mm, white 1 kg | 1 | Amazon (ELEGOO Official US) | 13.24 | received | 1 spool. General purpose |
| Spurtar vernier caliper, 150 mm, steel | 1 | Amazon (Wittyware) | 16.97 | received | The one to trust for dimensions that drive the CAD — flange OD, thruster OD, ESC brick |
| Ultrassist plastic vernier calipers, 150 mm ×2 | 1 | Amazon (Ultrassist) | 6.99 | received | One for Isabelle to learn on. The other kept for the shop: plastic is **non-conductive**, which is the right property for measuring around live LiPo terminals |
| YISHU 6 ft surge-protected power strip, 8 outlets + 4 USB | 1 | Amazon (QINGLIANFENG TECH) | 11.99 | received | 2026-09-27, arriving 2026-09-28. Bench power |

**Shop tooling subtotal: $483.37 · out of pocket $407.32** (rewards points −$76.05)

Still pending for the print shop: **ASA 1 kg** (~$20 — exterior ROV brackets,
UV-stable; needs the enclosure + ventilation), desiccant/dry bags for
filament storage (shared line with the housing desiccant).

All 5 spools received (2 PLA+ colored, 2 PETG, 1 PLA+ white) — the filament
order is complete. Only ASA remains unbought, and it is not needed until
exterior brackets.

**Caliper range is 150 mm, and two dimensions that matter exceed it:** the
YOWOO pack at 155 long and the 6" bore at 154.1. Use a steel rule for those
two. Everything else on the `housing-layout.md` measurement list — thruster
OD and length, ESC brick, dome flange OD — falls inside 150.

**CAD is Onshape.** The toolchain is proven end to end as of 2026-08-30;
the only friction was re-learning the tool, not the machine. Design parts
with driving variables (tube ID, flange diameter, stereo baseline) so the
housing layout can be swept rather than argued — see `open-questions.md`.

Printed parts are brackets and mounts only — **never the pressure boundary**
(FDM layer bonds are not watertight; housing stays PVC/acrylic/epoxy).
A printed cover is to be tested against this rule (2026-10-11,
`open-questions.md`); the rule stands until that test says otherwise.

**Material rule for printed parts:**

- **PLA+ — bench and mock-up only.** Fit checks, holders, jigs, anything that
  lives on a table at room temperature. It softens around 55–60 °C, and the
  sealed hull is deliberately a warm place (Pi 5 and NVMe both thermal-padded
  to the hull wall) before the sun gets to a dark tube on a kayak deck.
- **PETG — inside the hull.** Anything structural that ships in the vehicle.
- **ASA — outside the hull.** UV-stable; still pending purchase.

A part proven in PLA+ on the bench is a finished *design*, not a finished
part: reprint it in PETG or ASA before it goes in the build.

## Bench instruments (owned, from storage)

Brought out of storage 2026-10-25 (Roland). They have been in storage, so
**each one has to be checked before it is trusted**. They are owned, so they
are not counted in the build totals. Status: `to check` → `works` /
`needs repair` / `retired`, or `shelved` (kept, not checked, no way to use it yet). Check the multimeter first, because it is used to
check the other two.

| Item | Status | Use on CARP | Notes |
|---|---|---|---|
| Extech EX430 True RMS multimeter | works, mA fuse likely blown, switch intermittent | TRRS pinout, mic bias, piezo disc capacitance, resistor matching, general bench work | Autoranging, with a capacitance range. Not a clamp meter (see "Likely already owned") |
| Extech 382213 DC power supply | to check | Current-limited first power-up of the Pixhawk, Bar30, Pololu 5 V and new boards; a supply for a piezo driver if one is ever added | Digital triple output (Roland, 2026-10-25; specs from extech.com/products/382213): **adjustable 0–30 V / 0–3 A** with constant voltage / constant current and a current-limit LED; **fixed 5 V and fixed 12 V, each 0.5 A continuous, 1 A max**, with no settable limit (the page says only "overload and short circuit protection"). Ripple and noise < 5 mV; line and load regulation < 0.05 % + 10 mV; LCD meters, accuracy not listed. 3 A is too little to run an ESC, but the adjustable output can smoke-test one with the limit set low. The fixed 5 V at 0.5 A is too weak for the Pi 5. Not needed for the dongles, which run off USB |
| Rigol DS1052E oscilloscope, 50 MHz, 2 ch | to check | Drive amplitude on the transmit disc, receive signal, time of flight as a check on the software that doesn't depend on the dongle clocks, disc resonance (FFT or a stepped tone) | Probe ground is mains earth: clip it to circuit ground only. USB port for pulling waveforms to the computer; under WSL that needs `usbipd` |
| Edirol FA-101 audio interface | shelved | Possibly the 96–192 kHz multichannel interface in Options, for the acoustic bench only: many inputs and outputs on **one clock**, which is what the dongles cannot promise | Found 2026-10-25 (Roland), used before for acoustics. **Shelved 2026-10-25 (Roland): no FireWire computer.** USB-C cannot carry FireWire; the only chain is Thunderbolt 3 → Apple Thunderbolt 2 adapter → Apple Thunderbolt-to-FireWire 800 adapter (discontinued, expensive used) → FW800-to-400 cable, on a true Thunderbolt port, with thin driver support. The cheapest way back is an old desktop with a TI-chipset PCIe FireWire card running Linux. **FireWire 400 (IEEE 1394a), not USB**: it needs a computer with a FireWire port or card, and WSL cannot reach one, so it would run on native Linux (ALSA `snd-bebob` or FFADO) or Windows. Not for the vehicle: the Pi 5 has no FireWire. Up to 24-bit / 192 kHz, with fewer channels at the higher rates (check the manual for the counts). The front mic inputs have phantom power: **keep phantom off** with a piezo disc connected |

**Checks:**

- **EX430:** fresh 9 V battery and every display segment lit; leads
  without cracks, tips shorted read under ~0.5 Ω; fuses checked by
  resistance from the V/Ω jack into the mA and A jacks (a low reading means
  the fuse is good; replace a blown one with the rating the manual gives);
  readings against known values: a new AA (1.5–1.6 V), the Pi USB-C
  supply (5.1 V), kit resistors (5 %), kit capacitors (loose at the high
  values); continuity beeper and diode mode.
- **382213:** check the cord and plug and listen for loose parts before
  plugging it in; with no load, turn the adjustable output through its range and
  check it against the EX430, and measure the fixed 12 V and 5 V; on the adjustable output, set ~5 V with a ~100 mA limit, short
  it, and check that it goes to constant current and recovers; check it
  holds under a real load (a 12 V bulb or power resistor, because the
  ¼ W kit resistors are too small); ripple on the scope, AC coupled
  (the spec is < 5 mV; hundreds of mV of hum means tired filter capacitors).
- **DS1052E:** boot and backlight (a dim or flickering screen means an
  ageing CCFL, the usual failure); warm up ~30 min, then Utility →
  Self-Calibration with the inputs disconnected; both probes set to ×10 and
  compensated on the built-in 1 kHz square wave, on both channels; a DC
  voltage read on the scope and on the EX430 should agree within a few
  percent.
- **FA-101:** first find a computer it can plug into (FireWire port or
  card, native Linux or Windows). Then: does it power up and show up as a
  device; play and record at 48 kHz; then at the highest rate it offers and
  how many channels it keeps there; loopback from an output to an input, on
  the scope too; noise floor with the inputs open. Phantom power off for
  all of it.

**Results** (fill in as checked):

| Instrument | Date | Result |
|---|---|---|
| EX430 | 2026-10-25 | Works; DC volts agree with the 382213's adjustable output. **The rotary switch sometimes doesn't engage a mode**: check the display shows the expected mode and unit before trusting a reading, and work the switch through every position a few times to wipe the contacts. Fuse check by resistance from the V/Ω jack: **A (20 A) jack under 1 Ω, fuse good; mA jack about 0.5 MΩ, mA fuse most likely blown** (confirm out of circuit with the case open; replace with the same rating and type printed on it, a ceramic high-breaking-capacity fuse, not glass). Until then the mA/µA ranges don't work; volts, ohms and capacitance don't use that fuse. Capacitance reads a kit capacitor; continuity beeper works. Lead resistance and a resistor reading not yet recorded |
| 382213 | 2026-10-25 | Adjustable output agrees with the EX430 (DC volts). Current-limit short test, fixed 12 V and 5 V, load and ripple still to do |
| DS1052E | | |
| FA-101 | 2026-10-25 | Shelved: no FireWire computer |

### Parts from storage

Owned, found 2026-10-25 (Roland). Not counted in the build totals.

| Item | Status | Notes |
|---|---|---|
| Elenco CK-1000 component kit | in hand, contents not yet checked against the label | Label lists: ¼ W 5 % resistors 10 Ω–1 MΩ (5 each, includes 100 k, 220 k, 470 k, 1 M); trim pots 500 Ω–1 MΩ; ceramic disc 2.2–680 pF; Mylar film 0.001–0.33 µF; 50 V radial electrolytics 1–1000 µF; diodes incl. 1N4148, 1N4001 and Zeners; 2N2222A, 2N2907, 2N3904, 2N3906, 2N3055, 2N5457 (JFET); LM386, NE555, 741, CD4013, 4017, 7805, 7812, 74LS logic; inductors, 5 V relay, condenser microphone, 8 Ω speaker, buzzer, switches, alligator clips, 22 ga solid wire (5 colours). Useful on the acoustic bench: **1 MΩ trim pot** for setting the loopback level instead of swapping 1 M / 470 k / 100 k; **1N4148s** to clamp the mic input; the **condenser mic** to hear what a transmit disc puts into the air; **LM386** as a stronger disc driver or receive gain stage if the dongle is too weak (the 741 is too slow above ~10 kHz); **22 ga solid wire** for the breadboard, where the 30 AWG stranded is too limp |
| Arduino Mega 2560 | to check | 5 V AVR board. On the bench: drives the AD9835 over SPI, fires HC-SR04 pings, generates servo / ESC pulses, and gives a hardware trigger for the scope. Its ADC is too slow and coarse to record the discs |
| HC-SR04 ultrasonic ranger | to check | 40 kHz air ranging module, 5 V. An independent distance check in air to compare with the disc ranging, and a pair of real ultrasonic transducers to look at on the scope. 40 kHz is above what a 48 kHz dongle can record (24 kHz max) |
| Parallax standard servo | to check | Bench load for checking Pixhawk servo outputs (Phase 1) and the RC servo tester before anything drives an ESC |
| SparkFun AD9835 breakout | to check | DDS signal generator, programmed over SPI (from the Mega). A clean sine at any frequency for **sweeping disc resonance**, including above the dongle's 24 kHz limit, and for driving the HC-SR04 transducers at 40 kHz. Output is small: watch it on the scope, and add the LM386 or a transistor stage if a disc needs more drive |
| SparkFun 6DOF IMU v4 | to check | Old Bluetooth IMU board. Not for the vehicle (the Pixhawk's IMUs are better); curiosity or learning only |

## Running totals

| | Est $ | Paid $ |
|---|---|---|
| Ordered | ~1,237 | 1,869.33 |
| Core pending | ~205–310 | |
| Small parts pending | ~115 | |
| Field gear pending | ~55 | |
| **Paid + pending (6 thrusters, no options)** | **~$2,245–2,350** | |
| Shop tooling (excluded from above) | | 407.32 out of pocket (483.37 list) |

Confirms `open-questions.md`: this is not a $500 build — it is a ~$2,000
build (≈4×). The projection is Paid ($1,869.33, a known number) plus pending
estimates ($375–480); ordered items ran ~25% over their estimates, so pending
items may too. (Corrected 2026-08-20 per design review M1 — the earlier
"$1,550–1,700" summary mixed estimates for items whose real prices were
already known. Pending re-totaled after review 2 added the compass, spare
dome, and spare XT90-S.)
