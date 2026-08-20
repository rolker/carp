# Wiring Plan — v1 Baseline

Single battery per dive (the second pack is the swap spare, ADR-013); the
propulsion/hotel split (ADR-014) stays deferred until there's a reason.

## Power tree

```mermaid
flowchart TD
    B["4S LiPo 6000 mAh<br/>(XT90-S on pack lead)"] -->|XT90-S = service disconnect<br/>10 AWG| D["Distribution star point<br/>+ bulk capacitors"]
    D -->|14 AWG, XT60 ×6<br/>female on source side| E1["U2 ESC/thruster 1–6"]
    D -->|spur| PM["Pixhawk power module<br/>(voltage sense + 5.3 V)"]
    PM --> PX["Pixhawk POWER port"]
    D -->|12–17 V in| POL["Pololu D36V50F5<br/>5 V @ 5.5 A"]
    POL -->|5 V, GPIO header| PI["Pi 5"]
```

## Signal / data

```mermaid
flowchart LR
    PX["Pixhawk"] -->|"PWM signal+GND ×6<br/>MAIN OUT 1–6"| ESC["U2 ESCs"]
    BAR["Bar30"] -->|"I2C (BARO_EXT_BUS)"| PX
    PX <-->|USB| PI["Pi 5"]
    CAM1["IMX462 L"] -->|CSI ribbon| PI
    CAM2["IMX462 R"] -->|CSI ribbon| PI
    PI <-->|"Ethernet, RJ45 crimped dry-side<br/>of the tether gland"| TETHER["~15 m Cat6 tether (CCA)"]
    TETHER <--> OPAL["Opal router (topside)<br/>LAN 192.168.2.0/24"]
    OPAL -.->|WiFi 5 GHz| PHONE["Phone: Cockpit<br/>+ 8BitDo via BT 2.4 GHz"]
    BANK["Anker 10k power bank"] -->|USB-C 5 V| OPAL
```

## The rules (each one bought with someone's misery — see prior-art.md)

0. **Main fuse (MIDI/ANL 80 A) on the pack lead at the star point.** The
   pack delivers ≥120 A into a dead short inside a tube nobody can open
   mid-dive; the XT90-S is inrush management, not protection. Optionally
   15 A blade fuses per ESC drop. (Design review B1.)
1. **XT90-S is the service disconnect.** The pre-charge resistor lives in the
   male pin — never bury it behind a permanent adapter and disconnect
   elsewhere. Charging uses the XT90M→XT60F adapter, outside the vehicle.
2. **Star-point grounding.** Pack negative to one heavy point; Pi and Pixhawk
   grounds taken from that point *directly*, never daisy-chained off an ESC
   return. 56 A through a shared return shifts ground under load → phantom
   thruster twitches.
3. **ESC signal grounds return to the Pixhawk servo rail** alongside their
   signals.
4. **At most one ESC BEC 5 V line lands on the servo rail** (the U2 150 W
   variant has a 5 V/1 A BEC). Six paralleled BECs fight. Snip or tape back
   the rest — signal and ground only.
5. **Never backfeed 5 V into the Pixhawk through the servo rail.** The
   Pixhawk eats from its power module; the Pi eats from the Pololu. Separate
   rails, by design (power-budget.md).
6. **Pi powered via GPIO header** from the Pololu → set
   `usb_max_current_enable=1` or USB devices get capped at 600 mA.
7. **Bulk capacitance at the star point** — six thrusters slamming reverse
   sags the bus; brownout reboots are the classic cheap-build field failure.
8. **CSI ribbons route away from ESC power leads** — documented EMI failure
   mode (camera vanishes, corrupted frames). Ferrite/foil if it appears.
9. **Solder, then heat-shrink, every joint** — bullet connectors corrode;
   inside penetrators every conductor gets a stripped solder blob mid-pot.
10. **Leak probe at the hull low point → Pixhawk AUX pin**, `LEAK1_PIN` set,
    `FS_LEAK = surface`. Auto-surface-on-leak is the cheapest insurance in
    the project; mount above the condensate sweat line and bench-trip it.

## Open decision: power module placement

The Radiolink power module has XT60 connectors, and the main path peaks at
~56 A with 6 thrusters — right at the XT60's limit, which the BOM explicitly
bans on the main path. Two options:

- **A (chosen for v1): power module on a spur** off the star point. Pixhawk
  gets clean 5.3 V and accurate *voltage* telemetry; current telemetry reads
  only the Pixhawk's own draw, so set `BATT_MONITOR` for voltage-only and
  don't trust the mAh counter. Voltage sag under load is still visible —
  which is the number that actually predicts a brownout.
- **B (later, if current telemetry is wanted): re-terminate the module with
  XT90s** or add a standalone hall-effect sensor on the main path.

## Bench-phase deltas

- Phase 1–2 run without the Pololu/Pi: Pixhawk on USB power bank, servo
  tester fed by a USB charger or one ESC BEC.
- Thruster tests always on the LiPo, never a bank or BEC.
- Verify star-point integrity with a meter under load (Phase 3 checklist).
