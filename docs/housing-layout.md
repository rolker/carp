# Housing Layout and Frame Geometry

Resolves the coupled question `open-questions.md` calls "housing diameter and
camera mounting — one layout problem." Three unknowns (tube diameter, dome
spacing, endcap strategy) that only move together.

**Status: proposal.** Nothing bought, no pipe cut. ADR-012 stays open until
the measurements at the bottom of this file are taken.

## The options

| | Tube | Tube length | Envelope L×W×H | Verdict |
|---|---|---|---|---|
| **A** | 4" sched-40 | ~600–700 | ~750 × 350 × 250 | Cheap pipe, 2 extra penetrators, pods drift out of stereo cal |
| **B** | 6" sched-40 | ~400 | ~600 × 338 × 295 | **Leaning.** Domes on the front plate, one dry volume |
| **C** | 4" + oversized front plate | ~600–700 | ~750 × 350 × 250 | The seal is the hardest part on the vehicle and it is pressure boundary |
| **D** | 4" + mono camera | ~550–650 | ~700 × 350 × 250 | Cheapest path to water; drops stereo |

**Why B.** It resolves housing diameter, camera mounting, and whether pitch is
real, in one decision. Two secondary wins that have nothing to do with cameras:
the LiPos sit **side by side** in a 154 mm bore instead of stacked, and the six
ESCs **ring the tube wall** instead of eating axial length, so every one of them
gets a thermal path to the outside.

**What B costs.** ~$40–60 more in pipe and caps, more displacement so more lead,
more frontal area so more drag, and more dry weight over the gunwale — the
tradeoff `power-budget.md` names as "fine in water and awful at the launch."

## The fit — this is the whole argument

6" sched-40 is Ø168.3 OD, 7.11 wall, **154.1 bore**. Two 2" domes on ~Ø70
flanges:

| Centres | Flange span | Bore clearance | Gap between flanges |
|---|---|---|---|
| **75** | **145.0** | **+4.5** | **5** |
| 80 | 150.0 | +2.0 | 10 |
| 85 | 155.0 | −0.5 — does not fit | 15 |
| 100 | 170.0 | −8.0 — exceeds even the OD | 30 |

**The stereo baseline is not a free choice. The bore pins it at 75 mm** (74 once the flange was measured — see below). The
"~75–100 mm centres" carried in `open-questions.md` and the bring-up checklist
is really just 75. Anything wider forces an overhanging plate (option C) or 8"
pipe.

This costs nothing optically: 75 mm sits inside the 60–120 mm band
`prior-art.md` recommends for 0.5–2 m work.

At 75 mm the flanges land **inside the bore**, not merely inside the tube OD.
So the front plate is a plain disc sealing in the pipe — option C's
oversized-flange fabrication risk never appears.

> **Superseded by the endcap proposal below (2026-09-27).** A disc sealing
> *in* the pipe is a radial seal against the bore — the one prior-art.md says
> fails on out-of-round PVC. The proposal puts a flat lid *on* the pipe end
> instead, with the domes on its outside face, and that removes the reason the
> bore pinned the baseline: see `sled.md`, "The baseline is no longer
> pinned". The table and the 74 below still hold as the minimum.

### Measured flange: 71.9 — baseline moves to 74 mm

The table above assumed a ~Ø70 flange. Measured (2026-09-26) it is **71.9**:

| Centres | Flange span | Bore clearance | Gap between flanges |
|---|---|---|---|
| 73 | 144.9 | +4.6 | 1.1 |
| **74** | **145.9** | **+4.1** | **2.1** |
| 75 | 146.9 | +3.6 | 3.1 |
| 77 | 148.9 | +2.6 | 5.1 |

`bore_clearance >= 4` needs centres ≤ 74.2; the original `dome_flange_gap >= 5` needed
centres ≥ 76.9. No baseline satisfied both — until the bolt pattern was
measured.

**The bolt pattern retires the ≥ 5 gap rule.** Six holes, opposing pairs
spanning 66.5 outside / 62.5 inside: **Ø64.5 bolt circle, ~Ø2.0 holes** (M2
class — confirm with a screw). The bolts sit 3.7 mm in from the flange edge,
so they never reach the gap between flanges. Worst case, a hole on each flange
pointing straight at the other, the facing bolt centres are `stereo_baseline −
64.5` apart — 9.5 mm at 74, room for M2 heads and nuts. Clocked with holes at
±30° off the line between centres (free to do), that grows to ~18 mm. The gap
only needs to keep the flanges from touching, with print/placement tolerance:
**≥ 2**.

**Baseline: 74 mm.** It meets both rules (4.1 bore clearance, 2.1 gap) and
sits in the 60–120 band optically. 73 buys more bore clearance but leaves
~1 mm between flanges, too tight to place by hand.

## Frame — BlueROV1

Thruster numbering is ArduSub motor outputs, matching the matrix in
`frame-and-mixing.md`.

**Coordinate frame (CAD and ROS): X forward, Y to port, Z up** — right-handed,
ROS REP-103 body frame, and what Onshape builds in. Fixed 2026-09-27: earlier
revisions had port at −Y with Z up, a left-handed frame that would have
modelled mirrored.

**Origin: the front pipe end, on the tube axis** (= the front lid's inner
face). Moved 2026-09-27 from the tube's mid-length. Like a ship's aft
perpendicular and baseline, it is a physical datum fixed early that
everything mates to: the lid seats on it, the sled hangs from it, the tube
starts there. A lid-material change then moves only the lid's outer face and
the domes and cameras with it (optics unchanged); a tube-length change moves
only the rear. The tube runs from X = 0 to X = −`tube_length`. Z = 0 stays on
the tube axis, where `cg_z` and the BG target are already quoted from. The
dynamics frame — ArduPilot's, at the CG — is a fixed offset from this, set
after the float test. ArduPilot's own body frame (forward-right-down) is a
separate thing; the matrix factors in `frame-and-mixing.md` are in that
frame and are unaffected.

| Out | Role | Position |
|---|---|---|
| 1 | Horizontal port | Y +134, low, amidships-aft |
| 2 | Horizontal stbd | Y −134, low, amidships-aft |
| 3 | Vertical fwd-port | X −50, Y +134 |
| 4 | Vertical fwd-stbd | X −50, Y −134 |
| 5 | Vertical aft-centre | X −539, centreline |
| 6 | Lateral | X −459, **Z −30 — the CG datum**, aft of the rear cap |

Outputs 5 and 6 moved aft 19 mm when the rear cap became a 19 mm lid on the
pipe end — see "Endcaps". All X values are from the front pipe end (they
read +150 / −339 / −259 from the old mid-tube origin).

Verticals 3/4/5 form the triangle at **489 mm fore-aft separation** — better
than the 400 mm the pitch-authority calculation in `frame-and-mixing.md`
assumes, so that calc is conservative here. Outputs 3 and 1 share a side rail, as do 4 and 2, so each side is one
fabricated part carrying two thrusters.

## Notes

1. **Clock the flange bolt patterns.** Not strictly needed — the Ø64.5 bolt
   circle sits inside the flange, so facing bolts clear even when aligned —
   but rotating each flange so holes sit ±30° off the centre line doubles the
   spacing for free.
2. **All six thruster penetrators on the rear cap.** 18 phase conductors and
   two dome flanges cannot share one endcap. Front plate is domes only.
3. **Output 6 goes on the CG datum — hull-axis height, aft of the rear cap.**
   Not under the hull, and emphatically not above it. The BlueROV1 matrix
   carries a fixed −0.25 roll term for the couple a single off-CG strafe
   thruster induces, so the vertical offset is what makes that number right or
   wrong:

   | Position | Offset from CG | Couple at 1.7 kgf | vs righting moment @20° |
   |---|---|---|---|
   | Under the hull | −90 mm | 1.50 N·m | 1.9× |
   | Above the hull | +150 mm | 2.50 N·m | 3.1×, **and sign reversed** |
   | **CG datum** | **0 mm** | **~0** | **—** |

   Ballast is low, so CG sits ~30 mm below the hull axis: "up and over the top"
   is *further* from CG than under the hull, not nearer, and it flips the sign
   of the couple against a compensation term we cannot edit without forking
   ArduPilot. On the datum the couple vanishes and the sign question is moot.

   Two operational wins come free: no prop is the lowest thing on the vehicle,
   so hovering on a contact does not kick up silt into the shot, and there is
   less hanging down to snag.

4. **Route the tether over the top.** Output 6 now sits directly aft of the
   rear cap, where a tether led straight astern could be ingested. Exit high,
   strain-relieve to the frame, carry it up over the foam.
5. Foam high, ballast low, for the 2–3 cm BG the pitch-stability target wants.
6. **A long 4" tube is the wrong hull for BlueROV1.** Pitch inertia scales with
   length squared: a ~700 mm hull carries roughly 2–3× the pitch inertia of a
   ~400 mm one even after the fatter tube's extra mass. Choosing the six-
   thruster frame for camera aiming and then building option A means building
   the hull that makes aiming sluggish.

## Endcaps — proposal

**Status: proposal (2026-09-27).** Nothing bought. Replaces the "plain disc
sealing in the pipe" above.

**Both ends: a flat, square lid on the faced pipe end, held on by vacuum,
with tie rods as backup.**

- **Seal:** one O-ring lying on the pipe's end face (7.1 wide, centreline
  Ø161). Both pipe ends faced flat and square — wet-sand on 800 grit over
  glass, the Cave Pearl prep (prior-art.md). The lid face needs no prep;
  cast acrylic is cast between glass.
- **Clamp:** vacuum through the Schrader stem. 15 inHg on the Ø161 seal is
  **~1,040 N** at the surface; 5 m of water adds about as much again. The
  vacuum test that ADR-001 makes the gate is also the closure: pull 15 inHg,
  watch it hold, done.
- **Pilot ring**, printed, fixed to the lid's inner face (blind holes): drops
  into the bore to centre the lid, carries a clocking pin, and has a thin
  shoulder that backs the O-ring's inside edge (outside pressure pushes the
  O-ring inward, onto it) and acts as the compression stop. It is not
  pressure boundary, so FDM is fine. **Bench check:** does 15 inHg pull the
  lid down to the stop?
- **Tie rods:** four M6 on a **Ø184 circle at 45°**, outside the pipe (~5
  clear of the OD). That circle fits both an 8" square and an 8" disc (~7 of
  metal outside each hole), so the lid outline is free and one drilling jig
  serves acrylic squares and aluminium discs alike. Nuts set on fixed
  spacers ~1 mm off the lid — they keep a lid from leaving if the vacuum
  bleeds away in the kayak; they must never clamp, or they override the
  O-ring squeeze. Opening the front is: crack the Schrader, undo the four
  front nuts. The rear nuts stay put.
- **Relief for free:** a swelling pack or a hot Pi lifts the lid before the
  tube becomes a pressure vessel — the relief path ADR-013 and
  `power-budget.md` ask for. Crack the Schrader before opening, as ADR-013
  already says.
- **Leak monitor for free, probably:** the Pixhawk's onboard barometer reads
  hull pressure. Rising internal pressure during a dive is a leak, well
  before the SOS probes get wet. Unverified: confirm the Radiolink board has
  one and that ArduSub logs it.

**Front** is the service end: domes on its outside face, the sled on its
inside face (`sled.md`). **Rear** is hardly ever opened: penetrators, the
Schrader stem, and perhaps the ESCs as a heat path if the lid is aluminium.
A flat lid is a better penetrator face than a PVC cap's slight dome, and it
comes straight off without twisting cables — which rules out the threaded
cleanout plug, where every penetrator turns with the plug.

**Material: 3/4" cast acrylic, 8 × 8", both ends (~$40 each).** Clear, so the
O-ring contact, condensation and leak probes are visible. Aluminium only if
the sealed thermal soak says the Pi needs a heatsink — then **the front lid
only**, same outline and holes.

| Lid | Centre flex, 1 bar | Peak stress | Weight (air / net in water) | Cost |
|---|---|---|---|---|
| **3/4" cast acrylic** | ~0.13 mm | ~2.2 MPa (~7 at a hole; acrylic crazes ~10 sustained) | 0.93 / 0.15 kg | ~$40 per 8 × 8 |
| 1/4" 6061-T6 | ~0.16 mm | ~20 MPa (yield 276) | 0.71 / 0.45 kg | — |
| **3/8" 6061-T6** (front upgrade) | ~0.05 mm | ~9 MPa | 1.06 / 0.67 kg | SendCutSend, 2 × 8.5", 4 holes, anodised: ~$200 (quoted 2026-09-27, with 2-off discount) |

1 bar = surface vacuum plus 5 m. Simply-supported plate on the Ø161 seal —
rough; the two dome holes add maybe 1.5–2× to the front lid's flex.

- **Rejected on cost for v1:** the Blue Robotics 6" O-ring flange ($90 per
  end, plus a cap) epoxied into the bore — its radial O-rings are sized for
  BR's 151.9 ± 1.5 bore, not sched-40's 154.1. Revisit for v2.
- **Rejected:** HDPE (epoxy won't bond, so penetrator pots fail; creeps);
  single-layer 0.22" extruded acrylic (~13 MPa at the surface, cracks at
  holes); 6 × 6 sheet (smaller than the 154.1 bore).
- **Cheaper aluminium route:** Online Metals 8" discs (~$60 each; confirm
  it is 3/8" 6061), or a custom-cut 8 × 8 of 3/8" 6061-T651, drilled with the
  same jig as the acrylic. The jig locates from its own first hole (drill,
  pin, drill the rest), not the outline; steel or brass bushings in the
  printed body; flips on plugs in the Ø52 camera counterbores for the inner-face holes.
- **If 3/8" aluminium:** 6061-T6 (5052 only if salt water becomes routine),
  check flatness with a straightedge (< 0.1 across the seal; MIC-6 if not),
  anodise and use Tef-Gel on stainless threads. The re-quote should carry
  the whole front hole layout — the dome centres at `stereo_baseline` are the
  holes worth paying for, not the corners.

**Before ordering:** pick the O-ring (AS568 2-series, 0.139" cord, ID about
6.2" to sit mid-face) and check the corner rods and nuts against thrusters 1,
2 and 6.

## Onshape driving variables

Build the sketch on these, not on typed-in numbers. Assumed values are flagged
— every dimension in this document follows from the five of them.

| Variable | mm | Source |
|---|---|---|
| `tube_outer_diameter` | 168.3 | 6" sched-40 |
| `tube_wall_thickness` | 7.11 | 6" sched-40 |
| `tube_inner_diameter` | 154.1 | `tube_outer_diameter - 2*tube_wall_thickness` |
| `tube_length` | 400 | derived, see bay stack |
| `dome_flange_diameter` | 71.9 | **Measured 2026-09-26** (calipers) — over the 70 assumed, see below |
| `dome_glass_diameter` | 52.4 | **Measured 2026-09-27** — hemisphere R 26.3, flange 2.0 thick (`sled.md`) |
| `stereo_baseline` | 74 | set by bore + measured flange, see "Measured flange" — **74 is now the minimum, ~95 the maximum** (`sled.md`) |
| `lid_thickness` | 19.05 | 3/4" cast acrylic; 9.53 if the front goes to 3/8" aluminium |
| `lid_width` | 203.2 | 8" square (acrylic) or 8" disc (aluminium) — outline is free |
| `tie_rod_circle_diameter` | 184 | tie rods at 45°; fits both outlines |
| `seal_diameter` | 161.2 | O-ring centreline, mid pipe-end face: `(tube_outer_diameter + tube_inner_diameter)/2` |
| `dome_bolt_circle_diameter` | 64.5 | **Measured 2026-09-26** — 6 holes, ~Ø2.0 |
| `thruster_diameter` | 70 | **Measured 2026-10-02** — matches the assumption, nothing moves |
| `thruster_length` | 96 | **Measured 2026-10-02** (was 130 assumed) |
| `esc_length/width/height` | 75/30/15 | **ASSUMED — measure.** The U2 cable carries a sealed Ø20 × 72 cylinder 150 mm from the thruster, then > 1 m to a blue waterproof circular plug (2026-10-02 photo). The plug has **3 pins** (~5 mm spacing, ~10 long; shell OD 15, ID 11.5) — no separate ESC came in the box, so the cylinder is most likely a potted ESC outside the hull, and the 3 pins are V+, GND and signal. **Unconfirmed** — check with an ohmmeter across the pins (~0.1–1 Ω on all pairs would mean motor phases instead) |
| `pack_length/width/height` | 155/50/37 | `power-budget.md` |
| `rail_clearance` | 15 | chosen |
| `vertical_thruster_spacing` | 489 | driven by the tail arrangement |
| `cg_z` | −30 | ≈ BG below hull axis; **verify by float test** |

**Driven, not typed:**

```
rail_y                    = tube_outer_diameter/2 + thruster_diameter/2 + rail_clearance    -> 134
frame_width               = 2*(rail_y + thruster_diameter/2)                                 -> 338
thruster_6_z              = cg_z                                                             -> -30
thruster_3_x              = -50  (chosen: front verticals, 50 behind the front pipe end)      -> -50
thruster_6_x              = -(tube_length + lid_thickness + thruster_diameter/2 + 5)         -> -459
thruster_5_x              = thruster_6_x - thruster_diameter - 10                            -> -539
vertical_thruster_spacing = thruster_3_x - thruster_5_x                                      -> 489
dome_half_span            = stereo_baseline/2 + dome_flange_diameter/2                       -> 72.95
bore_clearance            = tube_inner_diameter/2 - dome_half_span                           -> 4.1
dome_flange_gap           = stereo_baseline - dome_flange_diameter                           -> 2.1
```

**Two inequalities are the design rules.** Make them sketch constraints so the
model breaks loudly rather than quietly:

```
bore_clearance  >= 4       (front plate seals inside the pipe)
dome_flange_gap >= 2       (flanges do not touch, with tolerance; bolts are inside the flange)
thruster_6_z    == cg_z    (strafe roll couple stays at zero)
```

With the endcap proposal, `bore_clearance` gives way to "the camera holes fit
inside the pilot ring" (`sled.md`); keep `dome_flange_gap`.

`thruster_6_z == cg_z` is the one that will drift: CG moves every time ballast or a
component moves. Re-check it after the float test rather than trusting the
sketch.

**Bay stack drives tube length:**

```
tube_length = dome_intrusion + pack_bay_length + electronics_bay_length + esc_bay_length + cap_allowance
            = 30 + 155 + 120 + 80 + 15    -> 400
```

- `pack_bay_length` 155 — two packs side by side, 100 of the 154 bore
- `electronics_bay_length` 120 — Pi 5 and Pixhawk side by side, 106 of the 154 bore
- `esc_bay_length` 80 — six ESCs ringed against the wall, not stacked in line

`sled.md` reorders the bays front to back as cameras → electronics → packs →
ESCs (was packs ahead of electronics), so the camera ribbons stay short and
far from the ESCs. The sum is unchanged. The dome centre is now measured
(on the lid's outer face, `sled.md`): on the acrylic lid the boards sit inside
the lid's thickness, so `dome_intrusion` is just the carrier and ribbon bends
behind the inner face — 30 is a comfortable allowance until the carrier is
drawn.

## Measure before cutting

Four of these five are sitting in boxes waiting on the inventory pass.

- [x] **ApisQueen U2 body OD and length** — **Ø70 × 96**, measured 2026-10-02.
      Mounting pad: four threaded brass inserts on a rectangle ~15.7 × 29.7
      centre to centre (caliper spans 13.5 / 17.8 and 27.3 / 32.1; holes
      Ø~2.2–2.4, thread size not yet identified)
- [ ] **One U2 ESC brick, L×W×H** — the swing factor in tube length, ×6
- [x] **Dome flange OD** — **71.9**, measured 2026-09-26. Over 70, so note 1
      stops holding and the baseline moves to 74 mm — see "Measured flange"
      above
- [ ] **YOWOO pack**, confirm against 155 × 50 × 37 in `power-budget.md`
- [ ] **Thruster mass, each** — for the buoyancy budget
- [ ] **Actual CG height**, from the float test — `thruster_6_z` follows it

## Related

- `sled.md` — camera mount, sled contents, stereo test plan
- `frame-and-mixing.md` — the BlueROV1 matrix these positions come from
- `open-questions.md` — the question this file answers
- `power-budget.md` — pack dimensions, buoyancy accounting
- ADR-012 — frame selection, still open
- ADR-003 / ADR-015 — dome port, camera architecture
