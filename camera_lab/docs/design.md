# camera_lab: design

Status: **draft, 2026-10-12.** Written in the style of `acoustics_lab/docs/design.md`
(a sibling tool in this repository; nothing here imports from it). Items marked
*open* are still to be decided. What exists today is listed under *Getting there*.

## What it is

A desktop workbench for understanding camera choices for an underwater vehicle:
how much a camera or a stereo pair sees (field of view and coverage), how finely
(resolution on target), how sharply while moving (frame rate, exposure and
motion blur), and how well it measures depth (stereo), in air or through a
flat or dome port into fresh or salt water.

It exists because the camera decisions for CARP (`README.md`, `docs/`) are
coupled and made on paper: the lens, the dome, the stereo baseline, the frame
rate the Pi can encode. The tool puts the numbers behind those choices next to
each other, so that a change (a 95 mm baseline instead of 74, a narrower lens,
a flat port) shows its consequences everywhere at once.

**The case it was built for.** CARP relocates and images sidescan contacts in
shallow (about 5 m), turbid (about 3 m visibility) water, from a kayak. Current
choice: two Arducam IMX462 colour 141 degree modules (SKU B0444) as a parallel
stereo pair on one rigid plate, behind two 2 inch acrylic domes, on a Pi 5, at
1080p10 with software stereo sync. **Baseline: 95 mm as printed on the bench
bracket, 74 to 95 mm allowed, decision open** (`docs/sled.md`, "The baseline is
no longer pinned"). Helping make that decision is the first job of the stereo
page.

**Audience.** A personal tool first, possibly students later. Two habits from
the start: every page explains itself, and nothing depends on CARP or one
machine's setup.

**Home.** A self-contained top-level `camera_lab/` with no imports from the rest
of the repository, so it can be split out with its history later.

## Principles

1. **Models are plain functions.** No Qt, no files, no global state: numbers and
   arrays in, numbers and arrays out, units in names or docstrings. Each has
   tests against a hand calculation, a statement of its source and its range of
   validity. Outside that range it still answers and the page shows a warning.
   The medium and the port are always passed in, never assumed.
2. **Theory and measurement on the same axes.** Model curves as lines,
   measurements as points, in consistent colours (the *Measurements* page, not
   built yet: checkerboard through the domes, a ruler at known ranges, a
   stereo calibration's reprojection error against the model).
3. **Every number explains itself.** Derived quantities are shown beside the
   inputs that produce them, and each page has notes with the formulas filled in
   with the current values.
4. **No hidden choices.** Assumptions are visible settings with defaults, saved in
   the workspace: the stereo matcher's disparity accuracy (0.25 px), the acceptable
   depth error (5 % of range), the matcher's search range (256 px), what counts
   as full overlap (90 %), the pixels needed across a target (24), the acceptable
   motion blur (1 px), the visibility (3 m), the vehicle speed (0.5 m/s), the
   encoded bits per pixel. They are defaults to start from, not measurements,
   and the pages say so.
5. **Demonstrate, don't block.** A setting outside a model's range (a flat port
   asked for more than the water allows, a dome pupil 3 mm off centre) is
   drawn, with a visible warning; nothing is refused except values that make no
   sense (a negative baseline).

## Decisions

| Decision | Choice | Why |
|---|---|---|
| Language | Python 3.12, numpy | Same stack as `acoustics_lab`; the models are array maths |
| Interface | PyQt6 with pyqtgraph; 3D through `pyqtgraph.opengl` | Live plots, dockable pages, frusta in 3D |
| Dependencies | Ubuntu 24.04 apt packages only | `python3-numpy python3-scipy python3-pyqtgraph python3-pyqt6 pyqt6-dev-tools python3-opengl python3-pytest`; nothing from pip |
| Platform setting | `PYOPENGL_PLATFORM` follows Qt's platform (egl for Wayland, glx for xcb) before OpenGL is imported | Mismatch breaks every 3D item (see `qtcompat.py`) |
| Storage | JSON objects in a workspace folder, IDs, undo | Same pattern as `acoustics_lab`, written again here |

## Words used here

- **Camera:** a sensor behind a lens. **Sensor:** the pixel array (size, pixel
  pitch, bit depth, shutter). **Lens:** focal length, projection model, aperture.
- **Projection model:** how an angle from the optical axis maps to a distance
  from the image centre (rectilinear, equidistant, equisolid, stereographic,
  orthographic).
- **Port:** the window between camera and water: *flat* or *dome*. Not the same
  as the **medium** (air, fresh, salt water: refractive index, visibility).
- **Rig:** a sensor, lens and port, as one camera or a **stereo pair** with a
  **baseline** (distance between the two entrance pupils), toe-in, frame rate,
  exposure, sync error.
- **Scene:** the medium and the assumptions listed under principle 4, plus the
  targets (small and large object sizes and the range they are drawn at).
- **Target:** a flat object square to the cameras.

## Workspace

A workspace is a folder, remembered between runs (default
`~/camera_lab_workspace`, created with CARP's cameras on first start):

```
sensors/<id>.json  lenses/<id>.json  ports/<id>.json
media/<id>.json    rigs/<id>.json    scenes/<id>.json
```

One object per file, indented JSON with sorted keys (friendly to git). Every
object has a short readable ID (`carp_95`) fixed when created; display names live
inside the file; references (a rig's sensor, lens, port; a scene's medium) use
IDs. All edits go through one undo stack (Edit > Undo, Ctrl+Z), one committed
edit being one step, and undo rewrites the files. Files edited outside are
picked up and the undo history is cleared, saying so. Objects in use cannot be
deleted; *Copy* makes a variation to compare. The fields of each kind are in
one table (`objects/schema.py`) from which the forms, validation and tooltips are
built.

Preloaded: the IMX462 sensor; the B0444 141 degree lens and a hypothetical 4 mm
rectilinear lens; the 2 inch dome (pupil centred, and 3 mm off), a flat window
and "no port"; air, fresh and salt water; rigs *CARP 95 mm (printed bracket)*,
*CARP 74 mm (minimum allowed)*, and for comparison a 4 mm lens, a 150 mm baseline
and a flat port; one scene, the shallow turbid site.

## Pages

| Page | Question | Status |
|---|---|---|
| Field of view & coverage | What do the cameras see, at which footprint and pixel size? | **built** |
| Stereo performance | Depth error, near and far limits, baseline decision, lens trade-off, sync error | **built** |
| Resolution & motion | Pixels on target, motion blur against exposure and speed, frame rate against data rate and overlap | **built** |
| Objects | Edit sensors, lenses, ports, media, rigs, scenes | **built** |
| Ports & domes | Ray trace through a dome with the pupil off centre; virtual image against range; flat-port caustic and colour fringes | models exist, page not built |
| Visibility & attenuation | Contrast and light against range and depth; what lights add | models sketched, page not built |
| Measurements | Measured points over the model curves | not built |

The window has the page list at the left with the **rig list** below (tick rigs to
show them, select one as the *primary*, shown in bold and used for single-rig
plots) and a toolbar for the scene and for a medium override (compare air, fresh
and salt water without editing the scene).

## The physics to get right

### Projection models

For a ray at angle theta from the axis and focal length f, the distance from the
image centre is

| Model | r |
|---|---|
| rectilinear (pinhole) | f tan(theta) |
| equidistant | f theta |
| equisolid angle | 2 f sin(theta / 2) |
| stereographic | 2 f tan(theta / 2) |
| orthographic | f sin(theta) |

All have r = f theta near the axis, so f is the on-axis scale. The field of view
across a sensor extent e is 2 theta(e / 2). A rectilinear lens cannot reach
180 degrees; fisheye projections can. Sources: Kannala and Brandt (2006), IEEE
PAMI 28(8); Ray, *Applied Photographic Optics*. Tests: pinhole 6.4 mm sensor and
4 mm lens gives 77.32 degrees (hand calculation); the other models likewise.

### Flat port

Snell's law at the window (its own index cancels for parallel faces):
n_air sin(theta_a) = n_water sin(theta_w). The field of view narrows by about 1/n
(tan of the half angle, near the axis), and cannot exceed 2 asin(1 / n) =
97.2 degrees in fresh water however wide the lens. Rays at different angles do
not appear to come from one point (the axial caustic: pupil 10 mm behind the
window appears 13.3 mm behind it on axis and 15.2 mm at 40 degrees), so the
pinhole model holds only near the axis. Water disperses (n = 1.340 blue, 1.332
red): blue and red rays at 60 degrees differ by about 0.3 degrees at the water
side (colour fringes). On axis, angles shrink by n, so there are n times more
pixels per radian: a flat port "zooms in". Source: Treibitz, Schechner, Kunz and
Singh (2012), "Flat refractive geometry", IEEE PAMI 34(1).

### Dome port

Pupil at the centre of curvature: every ray crosses both surfaces along the
normal, goes straight, and the field of view is unchanged; one viewpoint, so the
pinhole model survives (the reason for ADR-003). Two consequences:

- The dome is a negative lens for the scene. Paraxially, for an object at
  distance s (water side, from the outer surface), each surface obeys
  n1/s + n2/s' = (n2 - n1)/R with R positive (centre ahead of the light). For a
  far object the virtual image is about 3 dome radii out (95 mm from the pupil
  for R 26.3, acrylic 2.0 mm, fresh water): the lens must focus there. Hecht,
  *Optics*, 5th ed., 5.2.
- With the pupil off centre by d, a ray at theta meets the surface at an
  incidence angle asin(d sin(theta) / R) and is refracted off its path: there is
  no single viewpoint, field of view and focal scale change. The model traces
  rays through both surfaces with vector Snell's law (`ports.dome_trace`). Test:
  a hand calculation of a 5 mm offset, 25 mm sphere, 30 degree ray (31.43
  degrees out). Kunz and Singh (2008), OCEANS; Menna et al. (2016).

Dome wall thickness: 2.0 mm (`docs/bom.md`); `docs/sled.md` measured ~2.6 mm.
The object holds 2.0; the effect on the numbers is small and it is a setting.
*Open:* acrylic's refractive index (1.49 is a textbook value, unmeasured).

### Stereo

Two parallel, rectified cameras, baseline B, focal length f_px in pixels (in the
medium), disparity d, range z:

- d = f_px B / z, z = f_px B / d
- Depth error from a disparity error dd: dz = z^2 dd / (f_px B) (differentiate
  z = f B / d). Test: f_px 800, B 74 mm, z 2000 mm, dd 0.25 px gives 16.89 mm.
- Nearest range the matcher can handle: z_min = f_px B / d_max.
- Range at which the error reaches a fraction e of the range: z = e f_px B / dd.
- Overlap of two parallel cameras: footprint W = 2 z tan(FOV / 2); the share of one
  footprint the other also sees is 1 - B / W; they first touch at
  B / (2 tan(FOV / 2)). The coverage page also draws the overlap polygon for
  toed-in cameras.
- Sync: two frames t apart while moving sideways at v shift the target by v t,
  a disparity error f_px v t / z and a depth error z v t / B, independent of the
  lens. Forward motion costs v t of position along the axes.
- A fisheye is rectified to a pinhole image before matching, so only its central
  part is usable for stereo; the formulas use f_px on axis and an angular form
  (`range_error_off_axis_mm`) off axis.

Rectification and toe-in: toe-in changes where the footprints overlap (drawn on
the coverage page) but a rectified pair behaves like a parallel one with a
rotated image plane; the stereo numbers assume rectification.

Sources: Hartley and Zisserman, *Multiple View Geometry*, ch. 9-10; Szeliski,
*Computer Vision*, 12.1. Underwater: calibrate through the final domes (docs/prior-art.md).

### Resolution, blur, data

- Ground sample (mm per pixel) on a flat target: z / (cos^2(theta) p), with p the
  local pixels per radian (on axis z / f_px). Pixels across a target of size s:
  s / GSD.
- Motion blur in pixels = v t_exp / GSD; the longest exposure for a blur limit
  b is b GSD / v.
- Frame overlap along travel: 1 - v / (fps W).
- Raw rate = width x height x bits x fps; encoded rate from a bits-per-pixel
  setting (ADR-015: 1080p10 measured about 0.016 bit/px, cap 3 Mbit/s a camera).
- Pixels are counted, not detail: lens sharpness, demosaicing, compression and
  turbid water cost resolution. Rolling shutter shear is not modelled.

### Water

Refractive index from the Quan and Fry (1995) formula (400-700 nm, 0-30 C,
0-35 PSU): 1.3330 at 589 nm and 20 C fresh, 1.3399 at 15 C and 35 PSU. The
coefficients were written from memory and the tests reproduce those textbook
values. Visibility as c = 4.6 / V (1 % contrast) is a rule of thumb only.
The later *Visibility & attenuation* page will cover absorption and scattering
against wavelength, veiling light and what lights add (ADR-004 chose ambient
light); the 3 m visibility is a hard marker on every view until then.

## Camera facts (verified 2026-10-12, with what is not)

Sources: (1) switch-science.com/products/9985 (a retailer reproducing the
Arducam B0444 specification); (2) docs.arducam.com/Raspberry-Pi-Camera/Pivariety-Camera/IMX462/
(lists B0444 beside B0333); (3) framos.com IMX462LQR-C sensor page; (4) the
Arducam product page for B0444 (not fetchable; a search snippet agrees with 1).

| Fact | Value | Source |
|---|---|---|
| Sensor | Sony IMX462 STARVIS, 1/2.8 type (6.46 mm diagonal), 2.9 x 2.9 um pixels | 1, 2, 3 |
| Resolution and rate | 1920 x 1080, RAW10, 1080p up to 60 fps on the module (the bare sensor is quoted at 120 fps) | 1, 2, 3 |
| Lens | M12, manual focus, f = 2.1 mm +-5 %, F2.1 +-10 %, built-in IR-cut | 1, 2 |
| Field of view | **141.4 degrees horizontal** x 81.7 vertical x 161 diagonal (so "141" is the horizontal field) | 1, 2 |
| Dome | 2 inch acrylic, R 26.3 mm outer, wall 2.0 mm (bom) or ~2.6 mm (sled) | docs/bom.md, docs/sled.md |

**Unverified or inconsistent:**

- **The projection is not published.** A rectilinear 2.1 mm lens on this sensor would
  see 106 degrees, so the lens is a fisheye. An equidistant projection with
  f = 2.1 mm gives 151.9 degrees, not 141.4. The model uses equidistant with
  f = 2.256 mm (7 % above nominal, outside the stated +-5 %), which reproduces the
  listed horizontal (141.4) and lands within 2.3 degrees on the vertical (79.4
  against 81.7) and diagonal (162.0 against 161). Treat it as a fitted model until
  a calibration (checkerboard) measures the real mapping and distortion.
- Lens distortion figures are not published.
- Arducam's B0333 (4 mm, "92 degree") listing is inconsistent with its stated focal
  length and sensor (a 4 mm pinhole lens would see 70 degrees), so published
  field-of-view figures from this vendor are not independent of the projection used.
- Effective pixel counts differ between sources (1945 x 1097 effective on a reseller
  page); the 1920 x 1080 mode is taken as the whole active array.
- Rolling shutter (assumed from the sensor family), the exposure and gain limits, and
  the dome pupil position (tuned wet per `docs/sled.md`) are not verified.
- The full Sony datasheet was not found; unit cell size is from distributors (2.9 um).

## Numbers for CARP's rig (fresh water 15 C, dome, pupil centred)

From the preloaded workspace, to be reproduced by `tests/test_models.py`:

| | 95 mm | 74 mm |
|---|---|---|
| Horizontal FOV in water | 141.4 deg (unchanged by the dome) | same |
| Footprint width at 1, 2, 3 m | 5.7, 11.4, 17.1 m | same |
| Pixel size on target at 1, 2, 3 m | 1.29, 2.57, 3.86 mm | same |
| Depth error at 1, 2, 3 m (0.25 px) | 3.4, 13.5, 30.4 mm | 4.3, 17.4, 39.1 mm |
| Nearest range, matcher searching 256 px | 0.29 m | 0.22 m |
| Nearest range, 90 % overlap | 0.17 m | 0.13 m |

The matcher's search range, not the overlap, sets the near limit: the wider
baseline buys 22 % less error and costs 7 cm of minimum range at 256 px. That is the
trade the decision turns on (and a reason the search range is a visible setting).

## Getting there

1. **Done:** models (media, projection, ports, stereo, imaging, geometry, system) with tests;
   workspace with undo; Field of view & coverage; Stereo performance; Resolution & motion; Objects.
2. **Next:** the *Ports & domes* page (off-centre pupil traced, virtual image, close focus
   against lens minimum focus distance); a lens-database import (sensor and lens from datasheet
   values) with the source recorded per number.
3. **Then:** *Measurements*: load a checkerboard calibration (OpenCV in the vehicle's workspace, not
   a dependency here) and compare mapping and distortion with the model; measured disparity
   noise from a flat target to replace the 0.25 px default.
4. **Later:** *Visibility & attenuation*; rolling-shutter shear; a rectified-FOV crop for
   fisheye stereo; lighting; the stereo matcher's own error against texture.

*Open questions:* the real projection and distortion of the B0444 lens through the domes;
the dome's pupil offset in the built carrier; whether the matcher will really search 256 px
at 1080p10 on the Pi; whether 95 mm's longer minimum range matters for 0.5 m work.
