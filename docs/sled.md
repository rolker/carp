# Sled and Camera Mount

What rides on the slide-out sled, how the stereo cameras are held relative to
the domes, and how to test stereo before there is a housing to put it in.

**Status: proposal (2026-09-27).** Nothing drawn yet. The endcaps it hangs
from are in `housing-layout.md`, "Endcaps".

> **Decided vs proposed:** most of this file is agent proposals from design
> discussion, not approved decisions. `docs/open-questions.md` lists which
> is which — check it before treating anything here as settled.

## The idea in one paragraph

The front lid carries the domes on its outside face and the whole sled on its
inside face. Pulling the front lid pulls the sled: cameras, Pi 5, Pixhawk and
both packs come out as one assembly, and every camera cable stays connected on
the bench. The domes and cameras are both fixed to the lid and are never
separated by servicing, so the camera-to-dome geometry — the thing stereo
calibration depends on — is set once and does not move. Repeatability is a
property of the design rather than of how carefully it was put back.

## Datum chain

The optics care about camera-to-dome, nothing else. Keep that chain short and
keep the tube out of it:

```
dome ── dome bolt pattern (blind M2, lid outer face) ── LID ── dowels + screws (lid inner face) ── camera carrier ── camera boards
```

- The **lid** is the only reference. The pipe bore is out-of-round
  (prior-art.md) and never touches the optics.
- The **pilot ring** centres the lid in the pipe. That places the whole
  optical assembly in the vehicle, which matters for camera-to-vehicle roll and
  aim (clocking pin), not for calibration.
- The **tray** behind the carrier rides loose in the bore on skids, a few mm
  of clearance all round. If it fits tightly it fights the lid for location.

## Camera carrier

One printed part holding both cameras — the "one rigid plate" in `bom.md`.
Two separate brackets would let the cameras toe in or out relative to each
other, and a 0.1° change in relative aim costs more depth accuracy at range
than any baseline error does.

**Requirements**

| | Target | Why |
|---|---|---|
| Baseline | `stereo_baseline` (74 today — see "The baseline is no longer pinned") | Optical-axis to optical-axis, not board to board |
| Lateral: axis to dome centre | ≤ 0.2 mm, each camera | Decentring breaks the pinhole model the dome is meant to keep (prior-art.md). Sub-mm is what matters; 0.2 is a print-achievable aim, not a researched limit |
| Fore-aft: entrance pupil at dome centre | Adjustable ±3 mm per camera | prior-art.md: "Design fore-aft adjustability into the camera mounts." Domes and lenses vary |
| Relative aim | Parallel within ~0.5° | Calibration absorbs the rest; this keeps the overlap maximal |
| Board orientation | **Both identical, never mirrored** | The rolling shutter reads rows in the same direction on both, which is what makes the 23 µs sync (ADR-017) mean the same instant top to bottom. A board rotated 180° reads bottom-up and the sync falls apart. Identical orientation also puts both 1.3 mm axis offsets on the same side, so hole-pattern spacing equals `stereo_baseline` |
| Sensor rows | Parallel to the baseline | Rectification assumes it; mechanical roll within ~1°. Check which board edge the rows run along — the STEP does not say |

**Holding each board**

- **Print-only: slide-in rails** (chosen 2026-10-02 from the tolerance
  coupons, `cad/README.md` §4; print-only decided 2026-09-27). The mount has to hold each board
  *located and clamped* — no shift, rock or lift when the lens is turned for
  focus or a ribbon is tugged — or the calibration walks. For the bench rig
  stability is what matters (calibration measures where the boards are); the
  ≤ 0.2 lateral target only bites on the vehicle carrier, lens to dome.
  Candidates, all printed, none bought:
  - **Slide-in rails:** each board slides edgewise into two grooves
    (board 1.7 + 0.1, coupon A) against an end stop. Located by edges and
    groove. Open end: a small printed detent, or a retainer held by a
    printed nut (Close preset, coupon B) that could also clamp behind the
    connector against ribbon pull — **open** (retainer suggested by Roland
    2026-10-02). Needs ~1 mm of component-free board edge on the front — check in
    the STEP.
  - **Locate + snap-on retainer:** printed pins (two diagonal holes,
    Ø~1.8–1.9 in the Ø2.0 holes) or a shallow pocket locate; one PETG plate
    with lens-barrel holes snaps over **both** boards, presses them onto the
    standoffs and bears on the connector end against ribbon pull.
  - **Retainer + printed thumb-nut:** the same retainer plate held by one
    printed nut on a printed stud (≥ M6-class threads print reliably; M2
    does not). Adjustable clamp force, no snap to tune, reusable.
  - **Split snap pins** through the board holes, tapered with a lip that
    snaps over the board: the usual print-only PCB mount, but examples use
    ~3 mm holes and resin; at Ø2.0 in FDM each half-pin is ~0.7 wide —
    probably too fragile.
  - **Filament pins** (1.75 mm filament pressed into the carrier) or
    heat-staking — stronger than printed Ø1.8 pins; set aside for now.
  - Fallback: M2 screws into heat-set inserts.

  The tolerance coupon should decide it: rail grooves at 1.7 + 0.1 / 0.2 /
  0.3, printed pins at Ø1.8 / 1.85 / 1.9, one cantilever latch in PETG, and a
  printed nut on a stud.
- The hole pattern sits 1.3 mm off the dome axis, toward the connector
  (`cad/vendor/README.md`: the optical axis is off-centre, away from the
  connector).
- **Fore-aft = spacers, focus = the lens thread.** Two separate adjustments:
  the spacer stack under the board puts the entrance pupil at the dome centre;
  the M12 thread then sets focus (Blue Robotics' recipe: ½–¾ turn CCW from air
  focus, then iterate wet). Print spacer sets in 0.5 mm steps; the board's
  back-side parts stand ~2 proud, so the thinnest spacer is ≥ 2.5.
- Once tuned, lock the lens thread (a dab of nail varnish or a printed
  clamp — **no threadlocker near the acrylic lid**, uncured Loctite crazes it)
  and don't touch the spacers again. Re-calibrate if either changes.

**Carrier to lid**: two steel dowels in reamed blind holes in the lid's inner
face, plus 3–4 screws into blind tapped holes. Nothing through the lid (see
the lid rules below). The dowels make the carrier removable without losing
calibration, though in normal servicing it never comes off.

**Material**: PETG, or better a CF-filled nylon or PETG (the Centauri Carbon 2
has the hardened nozzle). **Not PLA** — it creeps when warm, and this part
lives next to a Pi that ran at 64–85 °C on the open bench (ADR-015). Rib it
across the baseline; stiffness across that span is what holds relative aim.

## The board sits inside the lid

Measured 2026-09-27 (`cad/README.md` §1 has the readings and the arithmetic):

- **The dome is a hemisphere, R 26.3** (glass OD 52.4, ID 47.25, wall ~2.6).
  Height from the flange's back face to the apex is 26.7, so the **centre of
  curvature sits ~0.4 in front of the flange's back face** — on the lid's
  outer face, plus any gasket under the flange.
- **The flange is 2.0 thick.** The "3/8" flange" in the listing is its
  radial width, (71.9 − 52.4) / 2 ≈ 9.75, not its thickness. The flange cannot
  clip the 141° cone: the 70.5° edge ray leaves the glass ~8.8 above the
  centre, the flange top is at ~1.6.
- **The lens front stands 17.0 in front of the board** at the current focus
  (the STEP said ~16), and the entrance pupil is a few mm behind the front
  element.

So with the pupil at the dome centre, the board's front face lands **~12–15
behind the lid's outer face**, and its back-side parts reach ~15.5–18.5. With
the 3/4" (19 mm) acrylic lid the whole board sits **inside the lid's
thickness**. With the 3/8" (9.5 mm) aluminium upgrade it sits behind the inner
face.

Two consequences:

1. **The camera hole is stepped, not straight.** The pupil sits at the outer
   face and the whole field opens forward into the dome, so the outer part of
   the lid only has to pass the **Ø14 lens barrel**: a **Ø16–18 through-hole**,
   with a light chamfer on the outer edge in case the pupil turns out to sit
   behind the face. The board, connector and ribbon go in a **Ø52 counterbore
   from the inside, ~8 deep** (the board needs 4.5–7.5 of it; the rest is
   margin for the fore-aft tune). From the optical axis the board reaches 7.3
   away from the connector, 16.7 + 8 of connector and ribbon on the connector
   side, ±12.5 across — Ø52 clears that and leaves ~5 of acrylic to the
   dome's bolt holes. The **whole flange face stays intact** for the dome
   seal, which a straight Ø52 hole would have cut down to a ~5 mm land.
   - The 8 needs the ribbon **bent back tightly at the connector** — a 1–2 mm
     radius, not a crease, a few mm clear of the latch, bent once. A loose
     bend measured 12.5 and would push the counterbore to ~Ø58, 2 mm from the
     bolt holes. The carrier clamps the ribbon behind the bend so a tug in
     assembly can't unlatch or re-bend it.
2. **Lid thickness is in the chain.** Swapping acrylic for aluminium moves
   the camera ~9.5 mm relative to the inner face, and the counterbore goes
   away. Make `lid_thickness` a driving variable, and put the difference in one printed
   spacer between carrier and lid, so the swap is a new spacer plus a re-tune,
   not a new carrier. The carrier's board seats reach forward into the
   counterbore on the acrylic lid.

## The baseline is no longer pinned

`housing-layout.md` fixed the baseline at 74 because the dome flanges had to
fit **inside the bore**. With a flat lid on the pipe end they don't — the
flanges sit on the lid's outside face, and only the camera holes and the
carrier have to be inside the pipe. The new limits:

| Constraint | Limit on `stereo_baseline` |
|---|---|
| Flanges don't touch (`dome_flange_gap >= 2`) | ≥ 74 |
| Camera counterbores (Ø52) inside the pilot ring (~Ø147 ID) | ≤ ~95 |
| Flanges inside an 8" lid (tie rods at 45° never interfere) | ≤ ~130 |
| Carrier inside the pilot ring | ≤ ~112 |

So the baseline can be anything from **74 to ~95**. Depth precision at range
scales with baseline: 95 over 74 is ~28% finer at 2 m, with some loss of
overlap at 0.5 m — little, with 141° lenses. It is also more room between the
flanges to get a screwdriver in.

**This is a decision, not a free parameter — make it before cutting the
lid.** Everything that currently says "74" (`bom.md`, `housing-layout.md`,
`open-questions.md`) says it because of the bore, and that reason has gone.

## Lid rules

The lid is pressure boundary. Inside the pipe seal it is dry on the inside
and wet on the outside, so:

1. **Nothing passes through the lid inside the seal** except the two dome
   holes and any glands. Every other fastener goes into a **blind** hole:
   - dome screws (M2) from the outside face — they only locate the dome,
     vacuum and depth hold it;
   - carrier screws and dowels from the inside face.
2. In 19 mm acrylic, blind taps up to ~10 deep: M4 or M5 coarse is fine for
   the carrier, M2 is weak but only has to locate a dome. Zero-rake drill,
   slow, cooled.
3. Tie-rod holes (Ø184 circle, 45°) are **outside** the seal, so they can go
   through.

## What rides on the sled

**Order changes: cameras → electronics → packs → ESCs.** `housing-layout.md`
had packs forward of the electronics. With the Pi on the sled right behind
the cameras, the stock 150 mm FFCs that came with the cameras may reach
without any extension, and the ribbons end up as far from the ESCs as the
tube allows — prior-art.md's documented EMI failure mode.

| On the sled | Notes |
|---|---|
| Camera carrier + both B0444s | Bolted to the lid |
| Pi 5 (+ M.2 HAT, NVMe) | Directly behind the carrier. If the Pi needs the aluminium lid as a heatsink, a short thermal strap to the lid is the path |
| Pixhawk | Beside the Pi (the 106-of-154 side-by-side in `housing-layout.md`) |
| Pololu 5 V regulator | Hotel pack → Pi |
| Hotel + propulsion packs | Side by side, low. Charged **outside** the tube, which a sled makes easy — a lithium pack is never charged inside a sealed tube |
| SOS leak sensor + probes | Probes on the tray's underside, one forward and one aft — the tube's low point moves with the sled's weight |

**Stays in the tube (rear):** the six ESCs, their phase wires to the rear-lid
penetrators, the tether penetrator, the Schrader stem. Phase wiring — 18
conductors — never crosses a disconnect.

**Disconnects the sled crosses** — all made through the front opening with
the sled pulled partway out, so each needs ~150 mm of service loop:

| Line | Connector | Notes |
|---|---|---|
| Propulsion pack → ESC bus | XT90-S (already stocked) | Anti-spark; it is also the arming connection |
| Pixhawk MAIN OUT 1–6 → ESCs | One multi-pin signal connector | Signal + ground only (`wiring.md` rule 3) |
| Tether Ethernet → Pi | RJ45 into the Pi, or an inline coupler | |
| Bar30 → Pixhawk I2C | JST-GH ↔ GH (the Blue Robotics adapter set) | **Or move the Bar30 to the front lid** and drop this one — it is a potted penetrator either way, and on the front lid it comes out with the sled |

**Tray**: flat, under the centreline so the packs sit low (ballast low, as
the BG target wants). A 100-wide pack pair fits the 154 bore at up to ~58 below
the axis. Printed PETG skids on the bore. It is cantilevered from the lid only
when out of the tube; on the bench it rests on its skids.

**CG moves aft** a little with the packs behind the electronics. `thruster_6_z ==
cg_z` in `housing-layout.md` already says to re-check after the float test;
this is one more reason.

## Testing stereo before the housing exists

Three stages. Each one uses the same carrier, so later stages test the
vehicle hardware rather than a stand-in.

1. **Air, now.** Print the carrier and a flat stand-in plate with the lid's
   hole pattern. Cameras on the stock 150 mm cables to the bench Pi. Checks
   the rig is rigid, calibration converges, the calibrated baseline matches
   `stereo_baseline`, sync holds (ADR-017), and depth on a known target is right.
   Air calibration does **not** carry over to water — this validates the rig
   and the pipeline, not the numbers.
2. **Domes in water, no housing — the "glass-bottom" rig.** Drill the real
   acrylic front lid, mount the domes, bolt on the carrier, and lay the lid
   **horizontally across a tote of water, domes down**. The cameras stay dry
   on top; only the domes and the lid's outer face are wet, under a few cm
   of water, so no pipe seal is needed. This is where to:
   - set fore-aft per camera, using the GEOMAR trick: checkerboard
     half in, half out of the water, adjust until there is no refraction
     discontinuity at the waterline (prior-art.md);
   - focus wet;
   - calibrate underwater with the laminated checkerboard, at 0.5–2 m.
3. **Sealed, in the vehicle.** Close up and re-calibrate. It should match
   stage 2 — the lid, domes and carrier never came apart. If it doesn't,
   something in the chain moved, and that is worth knowing before a dive.

## Modelling order (Onshape)

1. Lid: outline, pilot ring, tie-rod circle, stepped camera holes
   (`lid_hole_diameter` through, `lid_counterbore_diameter` counterbore from inside) and blind M2
   patterns — driven by `stereo_baseline`, `dome_bolt_circle_diameter`, `lid_thickness`, `tie_rod_circle_diameter`.
   Model the drilling jig from the same sketch: one jig for acrylic and
   aluminium (`housing-layout.md`, "Endcaps").
2. Domes (measured) and B0444 STEPs (`cad/vendor/`) placed, dome centre
   marked on the lid's outer face.
3. Carrier: camera pockets, 1.3 mm axis offset, spacer stack, dowels to lid.
4. Stand-in plate for stage 1 (same hole pattern, printable).
5. Tray, skids, disconnect positions — after the carrier works.

## Measure / decide before cutting the lid

- [x] **Dome height `H` and glass OD** — 26.7 and 52.4, measured 2026-09-27:
      hemisphere, centre on the lid's outer face, board inside the lid
- [x] **Dome glass inner opening at the flange** — 47.25; moot now the lid
      hole is stepped (Ø16–18 through, Ø52 counterbore from inside)
- [x] **B0444 board, holes, lens height, connector** — measured 2026-09-27,
      `cad/README.md` §1
- [x] **B0444 sensor row direction** relative to the connector edge — rows
      run parallel to it (along the 25 mm side); cables-up is upright.
      Inferred from bench frames, `cad/README.md` §1
- [x] **Lens entrance pupil** — **left to the stage-2 wet tune** (decided
      2026-09-27). Start with the pupil assumed ~3 mm behind the front
      element and set the first spacer from that; the ±3 mm spacer range and
      the counterbore margin absorb the error. Keep the chamfer on the
      Ø16–18 through-hole in case the pupil lands behind the outer face
- [ ] **`stereo_baseline`: stay at 74 or go wider (≤ ~95)?**
- [ ] Bar30 on the front lid or the rear?

## Related

- `housing-layout.md` — tube, endcaps, frame geometry
- `cad/vendor/README.md` — B0444 dimensions
- `prior-art.md` — dome focus, calibration, ribbon EMI
- ADR-003 (domes), ADR-015 (camera measurements), ADR-017 (stereo sync)
