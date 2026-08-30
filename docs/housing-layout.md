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

**The stereo baseline is not a free choice. The bore pins it at 75 mm.** The
"~75–100 mm centres" carried in `open-questions.md` and the bring-up checklist
is really just 75. Anything wider forces an overhanging plate (option C) or 8"
pipe.

This costs nothing optically: 75 mm sits inside the 60–120 mm band
`prior-art.md` recommends for 0.5–2 m work.

At 75 mm the flanges land **inside the bore**, not merely inside the tube OD.
So the front plate is a plain disc sealing in the pipe — option C's
oversized-flange fabrication risk never appears.

## Frame — BlueROV1

Thruster numbering is ArduSub motor outputs, matching the matrix in
`frame-and-mixing.md`.

| Out | Role | Position |
|---|---|---|
| 1 | Horizontal port | Y −134, low, amidships-aft |
| 2 | Horizontal stbd | Y +134, low, amidships-aft |
| 3 | Vertical fwd-port | X +150, Y −134 |
| 4 | Vertical fwd-stbd | X +150, Y +134 |
| 5 | Vertical aft-centre | X −320, centreline |
| 6 | Lateral | X −240, **Z −30 — the CG datum**, aft of the rear cap |

Verticals 3/4/5 form the triangle at **470 mm fore-aft separation** — better
than the 400 mm the pitch-authority calculation in `frame-and-mixing.md`
assumes, so that calc is conservative here. Outputs 3 and 1 share a side rail, as do 4 and 2, so each side is one
fabricated part carrying two thrusters.

## Notes

1. **Clock the flange bolt patterns.** 5 mm between flanges means fasteners on
   the facing sides interfere. Rotate each flange so no bolt lands inboard.
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

## Onshape driving variables

Build the sketch on these, not on typed-in numbers. Assumed values are flagged
— every dimension in this document follows from the five of them.

| Variable | mm | Source |
|---|---|---|
| `tubeOD` | 168.3 | 6" sched-40 |
| `tubeWall` | 7.11 | 6" sched-40 |
| `tubeID` | 154.1 | `tubeOD - 2*tubeWall` |
| `tubeLen` | 400 | derived, see bay stack |
| `flangeOD` | 70 | **ASSUMED — measure** |
| `domeGlassOD` | 50 | SupremeTech 2" |
| `stereoBase` | 75 | pinned by bore, see above |
| `thrusterOD` | 70 | **ASSUMED — measure** |
| `thrusterLen` | 130 | **ASSUMED — measure** |
| `escL/W/H` | 75/30/15 | **ASSUMED — measure** |
| `packL/W/H` | 155/50/37 | `power-budget.md` |
| `railClear` | 15 | chosen |
| `vertSep` | 470 | driven by the tail arrangement |
| `cgZ` | −30 | ≈ BG below hull axis; **verify by float test** |

**Driven, not typed:**

```
railY        = tubeOD/2 + thrusterOD/2 + railClear      -> 134
frameW       = 2*(railY + thrusterOD/2)                 -> 338
out6Z        = cgZ                                      -> -30
out6X        = -(tubeLen/2 + thrusterOD/2 + 5)          -> -240
out5X        = out6X - thrusterOD - 10                  -> -320
vertSep      = 150 - out5X                              -> 470
domeHalfSpan = stereoBase/2 + flangeOD/2                -> 72.5
boreClear    = tubeID/2 - domeHalfSpan                  -> 4.5
flangeGap    = stereoBase - flangeOD                    -> 5
```

**Two inequalities are the design rules.** Make them sketch constraints so the
model breaks loudly rather than quietly:

```
boreClear >= 4        (front plate seals inside the pipe)
flangeGap >  0        (flanges do not overlap; >= 5 to clock bolts)
out6Z     == cgZ      (strafe roll couple stays at zero)
```

`out6Z == cgZ` is the one that will drift: CG moves every time ballast or a
component moves. Re-check it after the float test rather than trusting the
sketch.

**Bay stack drives tube length:**

```
tubeLen = domeIntrusion + packL + elecL + escL + capAllow
        = 30 + 155 + 120 + 80 + 15               -> 400
```

- `packL` 155 — two packs side by side, 100 of the 154 bore
- `elecL` 120 — Pi 5 and Pixhawk side by side, 106 of the 154 bore
- `escL` 80 — six ESCs ringed against the wall, not stacked in line

## Measure before cutting

Four of these five are sitting in boxes waiting on the inventory pass.

- [ ] **ApisQueen U2 body OD and length** — sets frame width and vertical clearance
- [ ] **One U2 ESC brick, L×W×H** — the swing factor in tube length, ×6
- [ ] **Dome flange OD** — if it is over 70, note 1 stops holding and the
      75 mm baseline needs re-examining
- [ ] **YOWOO pack**, confirm against 155 × 50 × 37 in `power-budget.md`
- [ ] **Thruster mass, each** — for the buoyancy budget
- [ ] **Actual CG height**, from the float test — `out6Z` follows it

## Related

- `frame-and-mixing.md` — the BlueROV1 matrix these positions come from
- `open-questions.md` — the question this file answers
- `power-budget.md` — pack dimensions, buoyancy accounting
- ADR-012 — frame selection, still open
- ADR-003 / ADR-015 — dome port, camera architecture
