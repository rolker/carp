# CAD

> **Decided vs proposed:** most of this file is agent proposals from design
> discussion, not approved decisions. `docs/open-questions.md` lists which
> is which — check it before treating anything here as settled.

Onshape is the CAD tool; the Centauri Carbon 2 prints the parts. This file
is the working plan for turning `docs/sled.md` and `docs/housing-layout.md`
into a printable stereo camera carrier. Trim it as the steps get done.

- `vendor/` — manufacturer STEP files (git-ignored) and where to get them
- `reference/` — vendor drawings (Pi 5 mechanical)
- `prints/` — STLs of parts actually printed, so a print traces back to a design
  (`pi_bracket.stl`: the 2026-08-30 Pi 5 bench holder, Onshape practice part,
  in daily bench use. Its two pins beside the corner pins, at (3.5, 9.5) and
  (61.5, 46.5), sit in the Pi 5's **Active Cooler mounting holes** — cut them
  off or reprint without them before fitting the cooler, and keep the space
  under those holes clear for the cooler's push-pin tips;
  `coupon_a_c1.stl` and `coupon_b1.stl`: the 2026-09-28 tolerance
  coupons, §4)
- `onshape-notes.md` — Onshape plans, API limits, AI/MCP options and 2026
  changes, for agents (researched 2026-09-27)

**Onshape document:** `carp` (folder `carp`) —
<https://cad.onshape.com/documents/ec758b3ca6b65519093ac0d1>

## Next bench print: Pi holder + stereo bar in one piece

The Pi holder has to be reprinted without the cooler-hole pins anyway, so
the next iteration combines it with a stereo camera bar (both cameras at
`stereo_baseline` on standoffs, stock 150 mm cables to the Pi) as one bench
print — the stage-1 air test rig.

- **Use an Assembly to check fit, a Part Studio to make the print.** An
  assembly exported to STL is several overlapping solids again. For one
  printed piece, bring the holder into the camera bar's Part Studio with a
  *Derived* feature (or rebuild it there) and join them with *Boolean →
  Union*, so the export is a single solid.
- Drop the two cooler-hole pins; keep the four corner pins.
- **Print-only camera seats: slide-in rails** (`docs/sled.md`, "Holding each
  board"), chosen 2026-10-02 from the coupons (§4). Groove height from
  coupon A.

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
| B0444 front-face edge clearance | ≥ 1 clear | 2026-10-02: nothing within 1 mm of the slid edges on the lens side — the rail lips (1.0 overlap) clear |
| B0444 connector height | 2.3 proud of the back face | 2026-10-02. On the back (opposite the lens); the tallest back-side part, so it sets the 2.2 → 2.3 clearance. Ribbon leaves parallel to the board, straight out past the edge |
| Stock camera cable reach | ~100 | 2026-10-02: usable distance from Pi 5 camera connector to board connector on the ~150 mm stock cables, allowing for the bends. Sets where the stereo bar sits relative to the Pi holder |
| Active Cooler push-pin tips below the Pi board | 3.5 | 2026-10-02, measured before fitting. The holder must leave this clear under the two cooler holes |

**Dome centre (from the rows above):** sagitta from the OD point (3.0 above
the flange back face): h = 26.7 − 3.0 = 23.7, r = 26.2, so
R = (h² + r²) / 2h = **26.3** — a hemisphere, to measuring accuracy. The
centre of curvature sits **H − R ≈ 0.4 in front of the flange back face**,
i.e. on the lid's outer face (plus any gasket under the flange). The 2 mm
flange cannot clip the 141° cone: the edge ray (70.5°) leaves the glass
~8.8 above the centre, well clear of the flange top at ~1.6.

- [x] **Sensor row direction:** photograph a horizontal edge with the
      connector down. Do the pixel rows run along the 25 mm side? Result:
      **yes** — rows run parallel to the connector edge (a 25 mm edge; the
      24.4 direction runs connector → far edge). Inferred, not photographed:
      cables-up boards gave upright 1920-wide landscape frames with no
      rotation or flips anywhere in the chain (orientation checks below).
      Connector-down is the same axes rotated 180°.

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

- [x] Rotation property: **0** (both; `orientation` 2 = external) — Flip
      bits while streaming: **H 0, V 0** (both; camera_ros `orientation` 0)
      — Bag frame upright?: **yes** (2026-09-26 frames decoded with plain
      ffmpeg, and raw-Bayer previews written in sensor row order, both
      upright with the boards cables-up). **Result 1: cables-up is the
      sensor's natural upright.** A "TOP ↑" sheet shot would confirm
      directly.

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
layout sketch, so changing `stereo_baseline` moves everything together, and the
drilling jig comes later from the same sketch.

**Coordinates:** origin at the **front pipe end, on the tube axis** (= the front
lid's inner face; `housing-layout.md`, "Coordinate frame"), +X
forward along the optical axes (vehicle X), **Y to port**, Z up —
right-handed, ROS REP-103, same as `housing-layout.md`, so this drops into a
vehicle assembly (and a URDF export) later.

### Variable naming conventions

Settled 2026-09-27, before the Variable Studio existed — renaming later does
not update expressions that already use a name.

1. **snake_case, whole words, subject first:** `dome_flange_diameter`, not
   `flangeOD`. Names group by part (`camera_*`, `dome_*`, `lid_*`, `tube_*`)
   and match the ROS side of the repo.
2. **Property words:** `diameter`, `radius`, `thickness`, `width`, `height`,
   `length`, `depth`, `spacing` (centre to centre), `offset`, `gap`,
   `clearance`. The only abbreviations are `min` and `max` (and `cg`).
   Say what is meant: `camera_hole_spacing_x`, not `camera_hole_x`.
3. **Axes as a final `_x` / `_y` / `_z`** — vehicle frame (X forward, Y port, Z up)
   unless it is plainly a board's own axes.
4. **Derived values are expressions,** not typed numbers:
   `tube_inner_diameter = tube_outer_diameter - 2 * tube_wall_thickness`.
5. **Units always** (`74 mm`), and the **source in the description field**
   ("measured 2026-09-27", "design choice, sled.md", "from coupon").
6. **Shared vs local:** anything used by more than one Part Studio, or named
   in the docs, lives in the `Housing` Variable Studio. One-part dimensions
   (a rib thickness) are local Variable features. A local variable never
   reuses a shared name.
7. **Print fits get their own variables** so coupon results feed straight
   in (e.g. a rail groove width, a pin diameter), separate from the
   measured dimension they fit (`camera_board_thickness`).
8. **This table mirrors the Variable Studio.** Change a value in Onshape →
   update the table in the same commit as the print or measurement.

### Variable Studio contents

| Variable | Value | Source |
|---|---|---|
| `tube_outer_diameter` | 168.3 mm | 6" sched-40 |
| `tube_wall_thickness` | 7.11 mm | 6" sched-40 |
| `tube_inner_diameter` | `tube_outer_diameter - 2 * tube_wall_thickness` → 154.1 mm | Derived |
| `seal_diameter` | `(tube_outer_diameter + tube_inner_diameter) / 2` → 161.2 mm | Derived; O-ring centreline |
| `stereo_baseline` | 74 mm | Minimum; 74–~95 allowed (`sled.md`) — **decision open** |
| `dome_flange_diameter` | 71.9 mm | Measured 2026-09-26 |
| `dome_bolt_circle_diameter` | 64.5 mm | Measured 2026-09-26, 6 holes ~Ø2.0 |
| `dome_flange_gap_min` | 2 mm | Rule: flanges don't touch |
| `lid_thickness` | 19.05 mm | 3/4" acrylic; 9.53 for the aluminium option |
| `lid_width` | 203.2 mm | 8" |
| `tie_rod_circle_diameter` | 184 mm | M6 tie rods at 45° |
| `camera_hole_spacing_x` | 21 mm | B0444 hole pattern, along the board width (measured 21.05) |
| `camera_hole_spacing_y` | 12.5 mm | B0444 hole pattern, along the board height (measured 12.55) |
| `camera_axis_offset` | 1.3 mm | Hole-pattern centre to optical axis, toward the connector |
| `camera_board_width` | 25.1 mm | Measured |
| `camera_board_height` | 24.4 mm | Measured |
| `camera_lens_height` | 17 mm | Board front face to lens front, measured at current focus |
| `camera_hole_diameter` | 2.0 mm | Measured (STEP 2.2) |
| `camera_board_thickness` | 1.7 mm | Measured 2026-09-27 |
| `camera_lens_barrel_diameter` | 14 mm | Measured; retainer holes clear it |
| `camera_back_component_height` | 2.2 mm | Measured; standoffs clear it |
| `camera_connector_reach` | 8 mm | Connector + tightly bent ribbon past the board edge |
| `dome_height` | 26.7 mm | Flange back face → apex, measured 2026-09-27 |
| `dome_radius` | 26.2 mm | Glass OD 52.4 / 2; sagitta gives 26.3 — hemisphere |
| `dome_flange_thickness` | 2.0 mm | Measured |
| `lid_hole_diameter` | 17 mm | Through-hole for the Ø14 barrel; 16–18 |
| `lid_counterbore_diameter` | 52 mm | Counterbore from the inside for board + connector |
| `lid_counterbore_depth` | 8 mm | Board needs 4.5–7.5; rest is tune margin |
| `tube_length` | 400 mm | **Provisional** — bay stack total, `housing-layout.md` |
| `camera_pupil_depth` | 3 mm | Lens front → entrance pupil. **Estimate**; the wet tune corrects it |
| `dome_center_x` | `lid_thickness + dome_height - dome_radius` → ~19.5 mm | Derived: dome centre (and the camera pupils) in front of the origin |
| `sled_tray_top_z` | −55 mm | Tray top below the axis; ≥ −58.6 so the 100-wide pack pair fits the bore |
| `camera_spacer_thickness` | 3 mm | Starting guess; set per camera by the wet tune |
| `camera_standoff_height` | 3 mm | Board standoffs; clear the 2.2 back-side parts |
| `camera_pin_diameter` | 1.8 mm (placeholder) | *If* printed pins win: pin diameter for the Ø2.0 board holes — set from the coupon (1.8 / 1.85 / 1.9) |
| `print_fit_clearance` | 0.2 mm (placeholder) | General sliding-fit allowance per side — set from the coupon |

## 3. Build order inside `Front`

1. **Layout sketch** on the lid's outer-face plane:
   - the two optical axes at ±`stereo_baseline`/2
   - the dome flange circles and their six-hole patterns
   - the pipe bore and pilot-ring circle
   - the tie-rod circle

   Add a constraint that makes the model fail when the flanges collide
   (`dome_flange_gap ≥ 2`).
2. **Lid** at `lid_thickness`, modelled but not printed — the reference the carrier
   mounts to, and later the drawing for the acrylic.
3. **Camera carrier:**
   - two board seats, each hole pattern 1.3 off its axis toward the
     connector
   - **both boards the same way up** — never mirrored (rolling-shutter
     readout has to match for the sync, `sled.md`)
   - ribs across the span between them
   - board seats per the chosen print-only method (`docs/sled.md`)
   - dowel + screw interface on its front face (to the lid)
   - a slot for each ribbon to exit rearward
4. **Spacer** — one part with an Onshape **configuration** table for
   thickness, 2.5 to 6 in 0.5 steps. Export the set as STLs.
5. **Stand-in plate** — just the lid's inner-face interface (dowel and screw
   holes) plus feet to stand on the bench. It doesn't need to be 19 thick
   or 8" square; only the region the carrier bolts to.

## 4. Printing

- **PLA+ for stage 1** — it is bench only (`docs/bom.md` material rule).
  Reprint in PETG before it goes in the vehicle.
- **Print a tolerance coupon first** — cheaper than reprinting the
  carrier; it picks the board-seat method. Modelled 2026-09-28 in two Part
  Studios (layout proposed by an agent, sizes are starting guesses):
  - **`Coupon A`** (PLA+, one part, 110 × 60 × 8.5, plate down, no
    supports; label "C1"):
    - three **rail pairs**: walls 3 wide × 6.5 tall, lips 23.1 apart
      (`camera_board_width - 2 * coupon_lip_width`), grooves 25.4 wide
      (`camera_board_width + 0.3`) with the floor at
      `camera_standoff_height`, groove height 1.7 + 0.1 / 0.2 / 0.3; end
      stop at the back, board slides in connector end last
    - three **pin pads**: Ø4 bosses × 3 on one diagonal of the 21 × 12.5
      hole pattern, pins Ø1.80 / 1.85 / 1.90 × 2.2 (0.5 above a seated
      board)
    - embossed labels 0.4 high
  - **`Coupon B`** (PETG, nine parts, 112 × 35 × 15, no supports,
    0.12 layers for the threads):
    - two **latches**, printed flat so the arm flexes in the bed plane:
      arm 1.0 / 1.4 × 12, hook 0.8 over a 3 ramp, channel 8.2, rigid wall
      2.5; one **catch** block 8 × 8.8 fits both (0.6 arm deflection)
    - three **M6 × 1.0 stud + nut pairs** (Plastic Thread, ISO profile,
      presets Close / Normal / Loose, labelled C / N / L): studs Ø6 × 12
      on 12 × 12 × 3 bases, nuts 10 A/F × 5
  - **Results** (fill in after printing):

    | Test | Result |
    |---|---|
    | Rails +0.1 / +0.2 / +0.3 | 2026-09-28: +0.1 a bit too tight, +0.2 a bit loose. 2026-10-02: +0.1 works well after a few insertions — **use +0.1** |
    | Pins 1.80 / 1.85 / 1.90 | 2026-09-28: all too small, board moves around. 2026-10-02: pins measure ~0.05 under design (1.90 → ~1.85) |
    | Latch 1.0 / 1.4 (20 cycles) | 2026-10-02: both snap in and work, but hold weakly; 1.0 is weaker |
    | Nut C / N / L | 2026-10-02: all thread smoothly, all wobble a little (L most, C least); all hold when snug |
- **Carrier printed seat-side up** (rails stand up from the seat face, as on
  coupon A). Both seats finish on the same top layer, so they come out flat
  and coplanar. 4+ walls, ≥ 40% infill.
- **Hardware not yet bought** (not in `docs/bom.md`):
  - Nothing for the board seats — print-only (M2 × 6–8 screws + inserts
    only as a fallback)
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

- the calibrated baseline matches `stereo_baseline`;
- rectified images line up row for row.

Both hold → the carrier is rigid and correctly oriented. A baseline that
drifts between calibration runs means the print is flexing.
