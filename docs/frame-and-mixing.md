# Frame Geometry and ArduSub Mixing

Matrices below were read directly from `libraries/AP_Motors/AP_Motors6DOF.cpp`
in ArduPilot master. Factor columns follow
`add_motor_raw_6dof(motor, roll, pitch, yaw, throttle, forward, lateral, order)`.

---

## SimpleROV-4 / SimpleROV-5 — selected for v1

Both frame types share one matrix defining **five** motors. Building four
thrusters populates outputs 1–4 and leaves 5 empty.

| Out | Role | Roll | Pitch | Yaw | Heave | Surge | Sway |
|---|---|---|---|---|---|---|---|
| 1 | Horizontal port | | | −1.0 | | 1.0 | |
| 2 | Horizontal stbd | | | +1.0 | | 1.0 | |
| 3 | Vertical port | +1.0 | | | −1.0 | | |
| 4 | Vertical stbd | −1.0 | | | −1.0 | | |
| 5 | Lateral | | | | | | 1.0 |

**DoF available with 4 thrusters:** surge, yaw, heave, roll.
**With 5:** adds sway.

**Geometry:** verticals are **athwartships** (port/starboard), not fore/aft.
This gives roll authority, not pitch. Horizontal pair fore-aft, offset from
centreline for yaw.

**Note the negative throttle factors** on outputs 3 and 4 — a sign convention.
Use `MOT_n_DIRECTION` to correct any thruster spinning the wrong way rather
than rewiring inside the housing.

**Upgrade path:** output 5 is already defined. Adding a lateral thruster is
bolt-on — no parameter change, no reflash.

---

## BlueROV1 — deferred 6-thruster option

| Out | Role | Roll | Pitch | Yaw | Heave | Surge | Sway |
|---|---|---|---|---|---|---|---|
| 1 | Horizontal port | | | −1.0 | | 1.0 | |
| 2 | Horizontal stbd | | | +1.0 | | 1.0 | |
| 3 | Vertical fwd-port | −0.5 | +0.5 | | 0.45 | | |
| 4 | Vertical fwd-stbd | +0.5 | +0.5 | | 0.45 | | |
| 5 | Vertical aft-centre | | −1.0 | | 1.0 | | |
| 6 | Lateral | −0.25 | | | | | 1.0 |

**Geometry:** verticals form a **triangle** — two forward (port/starboard), one
aft on centreline. Full 6-DoF: surge, sway, heave, roll, pitch, yaw.

**The lateral thruster carries a −0.25 roll term** compensating for the roll
couple a single off-CG strafe thruster induces. Its vertical placement relative
to CG therefore matters.

**Surge does not improve.** Still two horizontal thrusters, still ~3.4 kgf. The
two extra thrusters buy sway and roll, not speed. If current becomes the
limiting problem, the **Vectored** frame (four horizontals at 45°) is the
answer instead.

---

## Vectored — not selected

BlueROV2 layout: four horizontal at 45°, two vertical side-by-side. More surge
and sway authority; no pitch. Most heavily tested frame in ArduSub by a wide
margin. `MOT_FV_CPLNG_K` exists to limit hydrodynamic coupling between vertical
and rear horizontal thrusters on this frame.

---

## Custom frames

`SUB_FRAME_CUSTOM` is an **empty case** in `AP_Motors6DOF.cpp`. The only
runtime motor parameters are `MOT_n_DIRECTION` and `MOT_FV_CPLNG_K`.

A custom matrix therefore requires forking ArduPilot, editing the source, and
maintaining a build — on a flash-limited FMUv2 board. Not a parameter change.

**If pitch-for-camera-aiming is wanted later**, the minimal change is taking
the SimpleROV-4 matrix and moving the roll factors into the pitch column, with
the verticals mounted fore/aft on centreline instead of athwartships.

---

## Propeller handedness

Thrusters sharing an axis should **counter-rotate** to minimise incidental
torque. Order CW/CCW pairs deliberately — many cheap thrusters ship one hand
only. Same-hand horizontal pairs make the vehicle roll under thrust, and the
attitude estimate pays for it.

## Pitch stability target

If pitch control is ever implemented: BG separation of 2–3 cm keeps pitch
commandable while resisting tether tug and surface chop. Righting moment at 20°
for an 8 kg vehicle with 3 cm BG is ~0.8 N·m; with verticals 40 cm apart that
needs only ~0.2 kgf differential — a rounding error against 1.7 kgf per
thruster. Pitch authority is never the constraint.
