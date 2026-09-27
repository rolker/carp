# CAD

Onshape is the CAD tool; the Centauri Carbon 2 prints the parts. This file
is the working plan for turning `docs/sled.md` and `docs/housing-layout.md`
into a printable stereo camera carrier. Trim it as the steps get done.

- `vendor/` — manufacturer STEP files (git-ignored) and where to get them
- `reference/` — vendor drawings (Pi 5 mechanical)

**Onshape document:** _(link here once created)_

## First target: camera carrier + stand-in plate

Not the sled yet. The first print is **stage 1 of the test plan in
`docs/sled.md`**: the camera carrier and a printed stand-in for the front
lid. Small, needs no housing, and it tests the part that matters most.
Model it so it grows into the real front lid and sled without a restart.

## 1. Measure first

Calipers, ~20 minutes. These decide the geometry. Fill in the values here,
then carry them into the docs (the way the 71.9 flange went into
`housing-layout.md`).

| Measurement | Value (mm) | Notes |
|---|---|---|
| Dome height `H`, flange back face → apex | 26.7 ± 0.2 | Straightedge bridged across both domes (2026-09-27): rule on edge 46.1 − 19.6 = 26.5; rule flat 27.6 − 0.7 = 26.9 |
| Dome glass OD `2R` | 52.4 | Taken 1 mm above the flange front face (2026-09-27); glass narrows right away, no cylindrical skirt |
| Dome glass ID at the flange | 47.25 | Measured 2026-09-27 from the back. Wall (52.4 − 47.25) / 2 ≈ 2.6 |
| Dome flange thickness | 2.0 | Measured 2026-09-27. The listed 3/8" flange is the radial width: (71.9 − 52.4) / 2 = 9.75 |
| B0444 board width × height | 25.1 × 24.4 | Measured 2026-09-27. STEP says 25 × ~24 |
| B0444 hole pattern | 21.05 × 12.55, Ø≈2.0 | 2026-09-27, caliper spans (outer / inner): 21-dir 23.1 / 19.0 → 21.05, Ø 2.05; 12.5-dir 14.5 / 10.6 → 12.55, Ø 1.95. Matches STEP (21 × 12.5). Two earlier 12.5-dir readings (14.7 / 11.55, 14.55 / 11.5) gave ~13.1 but an impossible Ø ~1.55 — bad inner span, discarded. STEP lists Ø2.2 |
| B0444 lens front above board front face | 17.0 | 2026-09-27, at current focus: lens front → PCB back 18.7 − PCB 1.7. STEP says ~16; changes with focus |
| B0444 lens barrel OD | 14.0 | Measured 2026-09-27. STEP says ~14 |
| B0444 back-side component height | 2.2 | Measured 2026-09-27. STEP says ~2 |
| B0444 connector + ribbon stub past board edge | 8 (design) | 2026-09-27: 12.5 with a loose bend; can be bent to the STEP's ~8. Design to 8 and have the carrier hold the bend (clamp behind the connector) so the ribbon cannot pull on the latch |

**Dome centre (from the rows above):** sagitta from the OD point (3.0 above
the flange back face): h = 26.7 − 3.0 = 23.7, r = 26.2, so
R = (h² + r²) / 2h = **26.3** — a hemisphere, to measuring accuracy. The
centre of curvature sits **H − R ≈ 0.4 in front of the flange back face**,
i.e. on the lid's outer face (plus any gasket under the flange). The 2 mm
flange cannot clip the 141° cone: the edge ray (70.5°) leaves the glass
~8.8 above the centre, well clear of the flange top at ~1.6.

- [ ] **Sensor row direction:** photograph a horizontal edge with the
      connector down. Do the pixel rows run along the 25 mm side? Result:

### Image orientation — which way up is upright?

The bench tests ran with the boards' printing upside down and the cables
up, and the images looked upright. Nothing in this repo rotates or flips
(launch file, patches, scripts checked 2026-09-27), so one of:

1. **The sensor is upright that way** — the board's natural orientation is
   connector-up.
2. **libcamera corrected it** — the overlay declares a `rotation`, and
   camera_ros's default orientation makes libcamera compensate using the
   sensor's own flip bits (no CPU cost, but it reverses the row readout
   order).
3. **The viewing step flipped it** — an ffmpeg/Python preview in the test
   session, not the bag itself.

Checks, on the Pi:

```bash
# 1. Does the overlay declare a rotation? (big-endian u32: 0 or 180)
xxd /proc/device-tree/axi/pcie@120000/rp1/i2c@88000/arducam_pivariety@c/rotation

# 2. With cameras.launch.py running: are the sensor flip bits set?
for d in /dev/v4l-subdev*; do echo $d; v4l2-ctl -d $d --list-ctrls | grep -i flip; done

# 3. Ground truth: cables up, camera pointed at a sheet with "TOP ↑" on it,
#    view a frame decoded straight from the bag in a stock viewer.
```

| Result | Meaning |
|---|---|
| No rotation property, flips off | 1 — cables-up is upright |
| Rotation 180, flips on | 2 — libcamera corrects for a connector-down board |
| Bag frame upside down | 3 — the preview was flipped after the fact |

- [ ] Rotation property: — Flip bits: — Bag frame upright?: —

**For the carrier:** any orientation works as long as both boards are
mounted the same way and both cameras run identical settings — that keeps
the readout order matched for the sync. Pick cables-up or cables-down for
ribbon routing to the Pi, then make the software match (camera_ros
`orientation`) rather than bending the mount to suit. **Calibrate with the
final orientation settings** — changing them afterwards invalidates the
intrinsics. Update the "connector down" assumption above, and `sled.md`,
once decided.

## 2. Onshape document structure

One document, `CARP`:

| Tab | Contents |
|---|---|
| **Variable Studio** `Housing` | Driving variables (list below) |
| **Part Studio** `B0444` | Imported STEP from `vendor/` |
| **Part Studio** `Dome` | Simple model from the measurements: 2.0 flange disc + R 26.3 hemisphere, centre ~0.4 in front of the flange back face, marked as a mate connector |
| **Part Studio** `Front` | Multi-part: layout sketch, lid, carrier, spacers, stand-in plate |
| **Assembly** `Front check` | Two cameras + two domes placed on the parts; clearances and axis alignment |

**`Front` is one multi-part Part Studio** — the Onshape idiom for parts
designed around each other. Lid, carrier and stand-in all reference one
layout sketch, so changing `stereoBase` moves everything together, and the
drilling jig comes later from the same sketch.

**Coordinates:** origin at the centre of the lid's **outer** face, +X
forward along the optical axes (vehicle X), Z up. Same convention as
`housing-layout.md`, so this drops into a vehicle assembly later.

### Variable Studio contents

| Variable | Value | Source |
|---|---|---|
| `tubeOD` | 168.3 mm | 6" sched-40 |
| `tubeID` | 154.1 mm | 6" sched-40 |
| `sealDia` | 161.2 mm | `(tubeOD + tubeID)/2` |
| `stereoBase` | 74 mm | Minimum; 74–~95 allowed (`sled.md`) — **decision open** |
| `flangeOD` | 71.9 mm | Measured 2026-09-26 |
| `boltCircle` | 64.5 mm | Measured 2026-09-26, 6 holes ~Ø2.0 |
| `flangeGapMin` | 2 mm | Rule: flanges don't touch |
| `lidT` | 19.05 mm | 3/4" acrylic; 9.53 for the aluminium option |
| `lidSize` | 203.2 mm | 8" |
| `rodCircle` | 184 mm | M6 tie rods at 45° |
| `camHoleX` | 21 mm | B0444 hole pattern |
| `camHoleY` | 12.5 mm | B0444 hole pattern |
| `camAxisOffset` | 1.3 mm | Hole-pattern centre to optical axis, toward the connector |
| `camBoardW` | 25.1 mm | Measured |
| `camBoardH` | 24.4 mm | Measured |
| `camLensFront` | 17 mm | Board front face to lens front, measured at current focus |
| `camHoleD` | 2.0 mm | Measured (STEP 2.2) |
| `camConnReach` | 8 mm | Connector + tightly bent ribbon past the board edge |
| `domeH` | 26.7 mm | Flange back face → apex, measured 2026-09-27 |
| `domeR` | 26.2 mm | Glass OD 52.4 / 2; sagitta gives 26.3 — hemisphere |
| `domeFlangeT` | 2.0 mm | Measured |
| `lidHoleD` | 17 mm | Through-hole for the Ø14 barrel; 16–18 |
| `lidCboreD` | 52 mm | Counterbore from the inside for board + connector |
| `lidCboreDepth` | 8 mm | Board needs 4.5–7.5; rest is tune margin |
| `spacerT` | 3 mm | Starting guess; set per camera by the wet tune |

## 3. Build order inside `Front`

1. **Layout sketch** on the lid's outer-face plane:
   - the two optical axes at ±`stereoBase`/2
   - the dome flange circles and their six-hole patterns
   - the pipe bore and pilot-ring circle
   - the tie-rod circle

   Add a constraint that makes the model fail when the flanges collide
   (`flangeGap ≥ 2`).
2. **Lid** at `lidT`, modelled but not printed — the reference the carrier
   mounts to, and later the drawing for the acrylic.
3. **Camera carrier:**
   - two board seats, each hole pattern 1.3 off its axis toward the
     connector
   - **both boards the same way up** — never mirrored (rolling-shutter
     readout has to match for the sync, `sled.md`)
   - ribs across the span between them
   - dowel + screw interface on its front face
   - a slot for each ribbon to exit rearward
4. **Spacer** — one part with an Onshape **configuration** table for
   thickness, 2.5 to 6 in 0.5 steps. Export the set as STLs.
5. **Stand-in plate** — just the lid's inner-face interface (dowel and screw
   holes) plus feet to stand on the bench. It doesn't need to be 19 thick
   or 8" square; only the region the carrier bolts to.

## 4. Printing

- **PLA+ for stage 1** — it is bench only (`docs/bom.md` material rule).
  Reprint in PETG before it goes in the vehicle.
- **Print a tolerance coupon first:** holes and pins at ±0.1–0.3 around
  nominal for the heat-set inserts, M2 clearance holes and the dowels.
  Printed holes come out undersized; cheaper than reprinting the carrier.
- **Carrier printed board-seat faces down on the bed**, so both seats come
  out flat and coplanar — that is what sets relative aim. 4+ walls, ≥ 40%
  infill.
- **Hardware not yet bought** (not in `docs/bom.md`):
  - M2 heat-set inserts + M2 × 6–8 screws (boards)
  - M3 or M4 inserts + screws (carrier to plate)
  - 3 mm steel dowel pins
  - a heat-set tip for the soldering iron

## 5. Tying it back to the repo

- Put the Onshape document link at the top of this file, and name Onshape
  versions to match git commits (e.g. "carrier v1 — 8b89fd0") when a part
  is printed.
- Export STLs for parts that were actually printed, so a print traces back
  to a design.
- Measurements go into the docs once taken.

## First test

Cameras on the carrier, stock 150 mm cables to the bench Pi, calibrate in
air with ROS `camera_calibration` in stereo mode. Check:

- the calibrated baseline matches `stereoBase`;
- rectified images line up row for row.

Both hold → the carrier is rigid and correctly oriented. A baseline that
drifts between calibration runs means the print is flexing.
