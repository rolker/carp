# Power Budget

## Load analysis

Size on **average** draw, not peak. All thrusters flat out never happens —
hovering in still water at 5 m runs 10–15% of rated.

| Load | Average | Peak |
|---|---|---|
| Thrusters (4) | 60–90 W | 600 W |
| Thrusters (6) | 60–120 W | 900 W |
| Pi 5 + cameras encoding | ~15 W | 25 W |
| Pixhawk + sensors | ~3 W | 5 W |
| Lights | 0 (ambient-first, ADR-004) | — |
| **Total** | **~110 W** (was ~150 W with lights) | |

At 16 V: ~7 A average, 37 A peak (4 thrusters) or 56 A peak (6).

**Hotel load dominates at depth.** At 5 m the thrusters do very little work —
hovering, not transiting. With no lights (ADR-004) hotel is ~18 W — the Pi
and sensors — instead of ~50 W, which is worth ~30–40% more runtime per pack.
If lights ever return, remember: **dimming the lights buys more endurance
than a second battery.**

## Battery sizing

Target **~200 Wh** — about 80 minutes usable stopping at 20% reserve.

Selected: 2× 4S 6000 mAh LiPo = 178 Wh total, ~1.2 kg, ~$85.

| | Value |
|---|---|
| Per pack | 6 Ah × 14.8 V = **89 Wh** |
| Runtime, one pack | ~48 min to empty, ~39 min to 20% reserve (at ~110 W, no lights; was 35/28 min under the old 150 W with-lights model) |
| Pack dimensions | 155 × 50 × 37 mm, 616 g |
| Current available | ≥120 A even discounting the 100C claim by 80% |

**Packing note:** 50 mm wide × 37 mm tall **stacks** inside a 4" tube.
Side-by-side at 100 mm won't clear with a frame.

## Wire gauge

Size for **peak**, not average. Undersized wire is a fire risk in a sealed tube
with no way to inspect mid-dive.

| Run | Current | Gauge |
|---|---|---|
| Pack → distribution | 37–56 A | 10 AWG |
| Distribution → each ESC | ~10 A | 14 AWG |

## Buoyancy accounting

Each LiPo: 616 g in ~287 cm³ → displaces 287 g → **~330 g negative**. Offset
with ~330 cm³ air void per pack.

General rule: a battery costs roughly **2.2× its own volume** in vehicle
envelope once flotation is included.

**Two things buoyancy cannot fix:**

1. **Mass stays.** Neutral buoyancy cancels weight, not inertia. A heavy
   neutral vehicle overshoots, takes longer to stop, and gets pushed further by
   current. With small thrusters, control authority degrades noticeably.
2. **Dry weight.** The vehicle gets carried to the kayak and lifted over the
   gunwale. 20 kg is fine in water and awful at the launch.

## 5 V rails

Split the rails. Thruster-induced noise on the ESC side must not reach the Pi.

| Rail | Supply | Load |
|---|---|---|
| Pi 5 | Pololu D36V50F5 (5.5 A) | Pi, NVMe, cameras |
| Pixhawk | **Its own power module** | Bar30 powers from the Pixhawk I2C port |

(A separate sensor/bench UBEC was planned but its loads evaporated — lights
deleted by ADR-004, Bar30 on the Pixhawk, servo tester is bench-only and can
run from a USB charger or an ESC BEC.)

**Accepted risk — Pololu margin (review 2 minor 2):** a 25 W Pi-side peak is
91% of the D36V50F5's 27.5 W rating, in a sealed tube. Accepted because the
25 W figure is itself a worst-case transient (Pi 5 peak + NVMe write burst +
both cameras), the converter has thermal-path-to-hull treatment like the
NVMe, and the Phase 3 thermal soak will catch it if reality disagrees. If the
soak shows the Pololu derating, the fix is a 6–8 A part, not a redesign.

**If the ESCs have BECs, don't parallel them.** The U2 150 W variant ships
with a 5 V/1 A BEC in the ESC; six BECs tied together on the servo rail will
fight each other. Connect at most one BEC's 5 V wire to the rail (or none —
the Pixhawk doesn't need servo-rail power), signal and ground only on the
rest.

**Pi 5 GPIO power gotcha:** powering through the GPIO header bypasses USB-PD
negotiation, so the Pi assumes a weak supply and caps USB current to 600 mA.
Set `usb_max_current_enable=1` in `/boot/firmware/config.txt`. Relevant when
the acoustics USB audio interface arrives.

**Cheap UBEC ratings are optimistic.** An 8 A part with thin input leads is a
4–5 A part in practice. A 5 A part on a 26 × 12 mm board is a 2–3 A part inside
a sealed tube. Derate everything and give each converter a thermal path to the
hull wall.

## Grounding

All ESC signal grounds return to the Pixhawk. If pack negatives float relative
to each other, the PWM reference floats and produces phantom thruster twitches
— miserable to diagnose once sealed.

**Run both pack negatives to a single heavy star point.** Take Pi and Pixhawk
grounds from that point *directly*, not daisy-chained off the ESC return. 56 A
through a shared return shifts the ground reference under load.

## Safety

- Relief path in the endcap, not just an o-ring. More lithium in a sealed tube
  is a worse failure, and pouch cells swell before they rupture.
- Never parallel two packs unless voltage-matched — mismatched packs dump
  current into each other on connection.
- `BATT2_MONITOR` on the hotel pack. It drains quietly while parked on the
  bottom.
