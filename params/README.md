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
| `FRAME_CONFIG` | SimpleROV-4 | ADR-012 |
| `BATT_VOLT_MULT` | *(calibrate)* | Radiolink power modules are known to read low |
| `MOT_n_DIRECTION` | *(as needed)* | Correct thruster rotation here rather than rewiring inside the housing |

## Not available

`SUB_FRAME_CUSTOM` is an empty case in `AP_Motors6DOF.cpp`. There is no
parameter-driven custom motor matrix — a custom frame requires a firmware fork.
