# Agent Guide: carp

> CARP (Cheap-Ass ROV Project): a low-cost, ROS 2–capable inspection ROV for
> relocating and imaging sidescan sonar contacts in shallow water, deployed
> from a kayak.

Most of this repository is design documentation for hardware that is being
bench-tested, not code. The code that exists is bench and desktop tooling.
The current goal is in [`docs/roadmap.md`](../docs/roadmap.md), under
Direction.

## Decided vs proposed: read this first

Much of the design text was written by agents during design discussion, and
**most agent suggestions have not been approved.**

- `docs/open-questions.md` says which parts of the design have the owner's
  approval and which are still proposals. Check it before you treat
  anything in `docs/sled.md`, `docs/housing-layout.md` or `cad/README.md`
  as settled.
- `docs/decisions.md` grades each ADR as **Committed** (hardware ordered,
  costly to reverse), **Leaning** (reasoned, cheap to change) or **Open**
  (contested, see `open-questions.md`). Don't treat a Leaning ADR as
  Committed.
- When you write a new suggestion, label it as proposed and add it to
  `docs/open-questions.md`. Don't write it into a design doc as if it were
  decided.

## Components

| Component | Language | What it is |
|-----------|----------|------------|
| `acoustic/` | Python | Bench code for the acoustic ranging tests in `docs/navigation.md`. No ROS, apt dependencies only. See `acoustic/README.md` |
| `acoustics_lab/` | Python (PyQt6, pyqtgraph) | Desktop workbench for acoustics: simulated, real or replayed pings, and room sonar. Design in `acoustics_lab/docs/design.md` |
| `camera_lab/` | Python (PyQt6, pyqtgraph) | Desktop workbench for choosing cameras: field of view, stereo performance, resolution and motion blur. Design in `camera_lab/docs/design.md` |
| `ros/carp_camera` | ROS 2 (ament_cmake, launch only) | `launch/cameras.launch.py`: both Pivariety cameras through `camera_ros`, encoded to H.264 `FFMPEGPacket`, optionally recorded |
| `scripts/` | bash, Python | Pi 5 setup: patched libcamera build, ROS workspace setup and build, enabling the Pivariety cameras, raw capture checks |
| `patches/` | patch files | Patches applied to `camera_ros`, `ffmpeg_encoder_decoder` and `libcamera` by the scripts in `scripts/` |
| `params/` | ArduSub `.params` | Parameter files, exported whole from QGroundControl after each verified change |
| `cad/` | Onshape exports | The CAD working plan (`cad/README.md`, mostly proposals), STLs of printed parts in `cad/prints/`, vendor drawings in `cad/reference/` |

## Repository layout

```
docs/                 design docs; the root README.md lists what each covers
  decisions.md        ADRs, graded Committed / Leaning / Open
  open-questions.md   unresolved decisions; what is approved vs proposed
  bom.md              bill of materials, ordered vs received
  bringup-checklist.md  bench acceptance phases 0-5, ticked as done
  roadmap.md          current goal (Direction)
  reviews/            design reviews
acoustic/             ranging bench code; designs/ holds ping designs (JSON)
acoustics_lab/        package, tests/, docs/, tools/, spike/, run.py
camera_lab/           package, tests/, docs/, run.py
ros/carp_camera/      ROS 2 launch package
scripts/  patches/    Pi 5 camera stack setup
params/               ArduSub parameters
cad/                  CAD plan, prints/, reference/, vendor/ (git-ignored)
```

## Key files to read first

1. `README.md`: mission, operating envelope, design posture, status.
2. `docs/open-questions.md`: what is decided and what is proposed.
3. `docs/decisions.md`: the ADRs and how committed each one is.
4. `docs/bringup-checklist.md`: what has been tested on the bench and what
   hasn't.
5. `docs/roadmap.md`: the current goal.
6. `docs/power-budget.md` and `docs/wiring.md`: the power system.

## Build & test

There is nothing to build on a desktop. The ROS camera stack is built on
the Pi 5 with the scripts in `scripts/` (`install-libcamera-build-deps.sh`,
`build-libcamera.sh`, `setup-ros-workspace.sh`, `build-ros-workspace.sh`).

Tests, from the repository root:

```bash
python3 -m pytest acoustics_lab/tests camera_lab/tests acoustic/test_ranging_dsp.py
```

Dependencies come from apt only and use the system Python. Install
`python3-pytest` along with the packages listed in `acoustics_lab/README.md`
and `camera_lab/README.md`. The GUI tests use Qt's `offscreen` platform.

## Common pitfalls

- **The owner does hardware tasks themselves to learn them.** For hands-on
  steps such as wiring, explain step by step. Don't produce the finished
  artifact unless asked.
- **Measurements are records.** `bom.md` and `cad/` hold calipered
  dimensions along with the Onshape models that corrected them. Change a
  number only with its source.
- **Vendor CAD is git-ignored** (`cad/vendor/*`) and not redistributed.
  `cad/vendor/README.md` says where to get it.
- **Run data is git-ignored**: `acoustic/runs/`, `acoustics_lab/runs/`,
  bags, `*.mcap`, `*.db3`.
