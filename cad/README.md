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
| Dome height `H`, flange back face → apex | | |
| Dome glass OD `2R` | | Dome centre sits `H − R` in front of the flange back face, if it is a true hemisphere |
| Dome glass ID at the flange | | Upper limit on the lid hole before it vignettes |
| Dome flange thickness | | Listed as 3/8" (9.5) |
| B0444 board width × height | | STEP says 25 × ~24 |
| B0444 hole pattern | | STEP says 21 × 12.5, Ø2.2 |
| B0444 lens front above board front face | | STEP says ~16; changes with focus |
| B0444 lens barrel OD | | STEP says ~14 |
| B0444 back-side component height | | STEP says ~2 |
| B0444 connector + ribbon stub past board edge | | STEP says ~8 |

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
| **Part Studio** `Dome` | Simple model from the measurements: flange disc + hemisphere, dome centre marked as a mate connector |
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
| `camBoardW` | 25 mm | |
| `camBoardH` | 24 mm | |
| `camLensFront` | 16 mm | Board front face to lens front |
| `domeH` | _measure_ | |
| `domeR` | _measure_ | |
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
