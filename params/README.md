# ArduSub Parameters

Parameter files for CARP, one per configuration stage.

## Conventions

- Export from QGroundControl after each verified change
- Commit the *whole* file, not diffs — ArduSub params are order-independent and
  the full snapshot is what gets reflashed
- Name files `carp-<stage>-<date>.params`

## Known non-default values

| Parameter | Value | Why |
|---|---|---|
| `BRD_SAFETYENABLE` | 0 | No physical switch reachable in a sealed housing (ADR-007) |
| `BARO_EXT_BUS` | *(set to external bus index)* | Defaults to −1 (disabled). Most common cause of "depth sensor not detected" |
| `FRAME_CONFIG` | *(pending frame decision)* | ADR-012 is Open — six thrusters make BlueROV1 a live alternative to SimpleROV-4/5 |
| `LEAK1_PIN` / `FS_LEAK` | *(AUX pin)* / surface | Leak probe auto-surface failsafe (design review M8) |
| `BATT_VOLT_MULT` | *(calibrate)* | Radiolink power modules are known to read low |
| `MOT_n_DIRECTION` | *(as needed)* | Correct thruster rotation here rather than rewiring inside the housing |
| `SYSID_MYGCS` | 255 | Required for QGC/Cockpit joystick authority; the #1 "no control" cause |
| `SERIAL2_PROTOCOL` / `SERIAL2_BAUD` | 2 / 921 | Only if Pi connects via TELEM2 UART instead of USB |
| `FS_PILOT_INPUT` | *(verify)* | Pilot-input failsafe timing — matters with browser-based control (Cockpit tab focus) |

**Firmware target:** `Pixhawk1-1M` from Sub/stable (genuine FMUv2 is 1 MB;
plain `Pixhawk1` assumes 2 MB and fails to flash). Pin the working `.apj`.
Custom control code note: MAVLink MANUAL_CONTROL z-axis neutral is **500**
(0–1000 scale), unlike x/y/r at ±1000 — z=0 means full descent on arm.

## Not available

`SUB_FRAME_CUSTOM` is an empty case in `AP_Motors6DOF.cpp`. There is no
parameter-driven custom motor matrix — a custom frame requires a firmware fork.
