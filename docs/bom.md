# Bill of Materials

## Ordered

| Item | Source | Notes |
|---|---|---|
| Radiolink Pixhawk Advanced | RobotShop | FMUv2 / STM32F427. **Not** the Radiolink Pixhawk 4 — that one is ArduPilot-incompatible (proprietary binaries, wrong connectors) |
| Pololu D36V50F5 | RobotShop | 5 V @ 5.5 A. Honest ratings, real thermal path |
| Digital RC servo tester | RobotShop | Manual mode holds settable pulse width, 2 µs resolution, PPM passthrough display |
| Bar30 pressure sensor | — | MS5837-30BA, potted in penetrator. See ADR-006 |

## Core, pending

| Item | Qty | ~$ | Notes |
|---|---|---|---|
| ApisQueen U2 + ESC | 4–6 | 60–70 ea | Full U2, **not** U2 Mini. Order CW/CCW pairs |
| Raspberry Pi 5 4 GB | 1 | 55 | 4 GB minimum; DSP will consume headroom |
| M.2 HAT+ | 1 | 20 | |
| NVMe 1 TB | 1 | 60 | Thermal path to hull wall required |
| 4S 6000 mAh LiPo, XT90-S | 2 | 42 ea | Anti-spark matters — 6 ESCs present a large capacitor bank |
| Dual-channel LiPo charger | 1 | ~60 | AC 150 W total across channels; DC 11–18 V for field charging |
| OV9281 global shutter camera | 1 | 50 | Down-looking nav camera |
| IP cameras | 2 | 30 ea | Forward + inspection. Onboard H.264/265 encode |
| Ethernet switch, small | 1 | 15 | Internal |
| GL.iNet travel router | 1 | 30 | Topside |
| 4" PVC, caps, o-rings | — | 60 | |
| Dome port | 1 | 40 | See ADR-003 |
| Penetrators + potting epoxy | — | 30 | |
| 20 m Cat5e + floats | 1 | 25 | |
| HDPE frame stock, ballast | — | 30 | |
| Lights, potted COB | 2 | 30 | On offset arms |

## Options / later

| Item | ~$ | Notes |
|---|---|---|
| Parallel green line lasers | 20 | Scaling **and** altitude for optical flow. Green penetrates turbid water far better than red |
| USB audio interface, 96–192 kHz multichannel | 100–200 | Acoustic ranging. CM6206-class does 96k stereo |
| 27 mm piezo discs + polyurethane | 20 | Transducers. Work far better underwater than they should |
| 12 V LiFePO4 pack | 50 | Hotel only — BMS current limit rules out propulsion |
| VESC (single) | 60–100 | Vertical axis only. FOC gives smooth control through zero |

## Deliberately not buying

| Item | Why |
|---|---|
| Blue Robotics Navigator | ADR-008 |
| Fathom-X tether interface | Unnecessary under ~50 m; saves ~$100 |
| Echosounder for altitude hold | Blows budget; lasers + optical flow substitute |
| XT60 on the main power path | 60 A rated vs ~61 A peak. Thermal bottleneck in a sealed tube |

## Connectors and wire

- **XT90-S** pack to distribution point, 10 AWG silicone. This is the service
  disconnect — the pre-charge resistor is in the male pin, so don't bury it
  behind a permanent adapter and disconnect elsewhere.
- **XT60** distribution to individual ESCs, 14 AWG. Each sees ~10 A.
- **XT90 male → XT60 female adapter** for charging only (6 A, nowhere near
  limit). Check the charger box first — most in this class ship a full adapter
  set.
- **JST-GH pigtails** for Pixhawk ports, pre-crimped. Hand-crimping GH is
  miserable.

## Tools and consumables

- Multimeter with DC current clamp — verify actual thruster draw against the
  150 W spec without breaking the circuit
- Silicone grease for o-rings — **Molykote 111 or Super Lube only**. Petroleum
  products attack Buna-N
- **Spare o-rings in every size, bought before first assembly.** The housing
  will be opened more times than expected; a nicked o-ring on a Sunday ends the
  day
- LiPo-safe bag or ammo can
- Cell-voltage checker with alarm (~$8)
