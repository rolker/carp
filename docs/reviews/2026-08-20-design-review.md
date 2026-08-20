# CARP Design Review — 2026-08-20

Independent review by a fresh agent with no conversation context; read the
full repo and re-derived the math. Findings ranked BLOCKER / MAJOR / MINOR.

---

## BLOCKER

### B1. No overcurrent protection anywhere in the electrical system
`wiring.md` power tree, `power-budget.md`, and `bom.md` contain no fuse,
breaker, or current limit of any kind. The system is a 6 Ah pack the docs
themselves credit with **>=120 A** delivery, feeding 10 AWG through a sealed
tube that explicitly "cannot be inspected mid-dive." A chafed 14 AWG ESC drop
or a swollen pouch shorting against the frame is an unfused dead short in a
closed PVC vessel next to a LiPo. The XT90-S anti-spark is inrush management,
not protection.

**Fix (~$15):** one MIDI/ANL 80 A fuse on the pack lead at the star point,
plus optionally 15 A blade fuses per ESC drop. Add "main fuse installed and
verified" to Phase 3.

### B2. Solo free-diving to clear tether snags is the plan of record
ADR-001 and ADR-009 both treat "at 5 m you can free-dive to clear a snag" as
the tether-fouling answer. This is solo breath-hold diving, from a kayak,
into your own entanglement hazard — the line that is snagged is the line that
snags *you*. This is how experienced watermen die.

**Fix ($0):** rewrite as haul-test -> slack-and-reposition -> abandon and
return with a buddy or a grapple. Free-diving on a fouled line is a
two-person operation, full stop. The vehicle is ~$1,600; write that down.

---

## MAJOR

### M1. The all-in cost projection contradicts its own ledger
The BOM concludes "$1,550–1,700 all-in" but records $1,583.58 already paid
plus $325–445 of pending estimates. Floor: ~$1,909; with the file's own ~25%
overrun pattern on pending items: ~$1,990–2,100. The summary mixes ordered
*estimates* with pending estimates even though Paid is known and $438 higher.
The "$500 build?" answer is ~4x, not ~3x.

### M2. Battery-swap-per-dive is unreconciled with a sealed housing
ADR-013's rationale is swap between dives, but the housing doctrine demands a
vacuum re-test after every reopening — a field procedure written nowhere. The
housing open question never mentions the swap requirement, which is arguably
the strongest driver of closure design (tool-free field-serviceable face
seal) or of a separate battery tube (the OpenROV pattern prior-art already
endorses — which also solves relief venting and flood isolation in one move).

### M3. No workable heading source, and the mission depends on heading
The spiral search is dead reckoning on heading, but the only magnetometer is
inside the Pixhawk, inside a tube with six ESCs, the star point, and up-to-
56 A conductors. There is nowhere "away from ESC wiring" inside that tube. No
external compass exists in the BOM. Expect tens of degrees of throttle-
correlated heading error — a spiral that isn't a spiral.

**Fix (~$15–30):** external I2C compass on a mast/far frame corner in its own
potted blob; add "compass interference check under full thrust (MagFit)" to
Phase 3/5.

### M4. What runs on the Pi is undecided, and two docs assume different answers
README/ADR-010 assume ROS 2 + Project11; prior-art plans in detail around
BlueOS + Cockpit. No doc states whether the Pi runs BlueOS, vanilla OS +
mavlink-router + self-hosted Cockpit + ROS 2, or both containerized. This
decides the video pipeline, the control path, and half of Phase 3.
**Fix:** write ADR-017, one page, before Phase 3.

### M5. The dual-CSI purchase reintroduces the CPU problem ADR-015 was
written to avoid — and the pod idea has an unexamined wet-CSI problem
Two software-encoded streams are back on the Pi, plus recording, plus ROS.
Separately, the BOM says the 4" dome was "retired by camera pods," but pods
are only a *candidate* in open-questions, and CSI ribbons are not wet-rated,
can't pass a gland with connectors on, and are EMI-sensitive at ~20–50 cm.

**Fix ($0):** promote "prototype the CSI/encode pipeline at intended
resolution and ribbon length, measure CPU and watts" to a named checklist
item *before pipe purchase*.

### M6. Endurance numbers were never propagated after the lights were deleted
Per-pack runtime rows are still 150 W numbers (35/28 min); at the doc's own
post-ADR-004 ~110 W they are ~48/39 min. Phase 5 still says "against the
150 W estimate." One propagation pass needed.

### M7. Offload plan assumes gigabit; tether doctrine says 100 Mbps
ADR-016's "100 GB in under 20 minutes" needs 1000BASE-T, which prior-art
forbids counting on — and the ordered tether is CCA Cat6, the worst case. At
100 Mbps, 100 GB is ~2.2 h. Fix: offload overnight or via a short dockside
patch cable; test 1000BASE-T on the actual wet tether once and record it.

### M8. No leak detection failsafe — only passive logging
Internal-baro logging is post-dive forensics, not a response. ArduSub
natively supports leak probes (LEAK1_PIN, FS_LEAK=surface) on an AUX pin; a
probe is $5. Auto-surface-on-leak is the cheapest insurance in the project.
Expect condensate false alarms (mount and test accordingly).

---

## MINOR (abridged — see review conversation for full list)

1. Vacuum gate 10 inHg = 3.5 m < 5 m site depth. Pull 15 inHg (~5.2 m).
2. Tether identity drift: wiring says 20 m Cat5e; BOM ordered Cat6 cut ~15 m.
3. Tether attachment: navigation says clip to downline; BOM says to the boat.
   Probably compatible — draw the rigging.
4. BOM subtotal arithmetic drift between section headers and totals table.
5. README still advertises "~$500 core."
6. params/README lists FRAME_CONFIG=SimpleROV-4 but ADR-012 is now Open.
7. BOM asserts pods/dome-retirement that no ADR decided.
8. IMX462 IR-cut variant unconfirmed — add to arrival checks.
9. Phase 2 thruster runs: specify *in water*; 20 min dry is a warranty claim.
10. No sealed thermal soak: add 45-min sealed, everything encoding, SoC temp
    logged, before first water.
11. Desiccant on no BOM line.
12. No field-day ops checklist (pre-dive vacuum, cell voltages, disarm-
    before-hands-near-props — relevant since ADR-007 removed the switch).
13. Pololu ceiling: 25 W Pi-side peak = 5.0 A on a 5.5 A part in a warm
    tube; USB audio + NVMe land on this rail later.
14. Unsynced rolling-shutter stereo is not measurement-grade on a moving
    vehicle; lasers are the real instrument. Don't let the photogrammetry
    claim harden.
15. Acoustic ranging: the topside receive chain needs the same sub-100 us
    timebase — laptop wired to the Opal's LAN port, not WiFi. (The rest of
    the acoustics math checks out.)

## Sequencing

Phase order fundamentally sound. Three re-orderings: (1) the ADR-004 jar
test and bottom-texture check belong in Phase 0/1, the week the cameras
arrive — the whole no-lights architecture hangs on them; (2) CSI/encode
prototype before pipe purchase; (3) Phase 5 needs failsafe drills: kill
topside link mid-dive, pull power at depth, trip the leak probe.

Un-hedged SPOF: the Pixhawk itself — no spare, no fallback. The CCOM
"spare Pixhawks in a drawer" question is the free mitigation; ask early.

## Numbers checked and correct

Buoyancy math, pitch statics, sidescan error table, motor matrices vs
AP_Motors6DOF.cpp, raw-Image data rates, wire gauges vs currents, paid-total
addition, acoustics arithmetic. frame-and-mixing.md, sidescan-datum.md, and
prior-art.md are sound as written.

## What this plan gets right

Relocation correctly identified as the mission; genuine de-rating culture;
honest ADR commitment-grading with recorded reversals; vacuum-as-gate with
positive pressure demoted to debug; rejecting the custom-frame fork on a
flash-limited board.

## Top 5 priorities

1. Main fuse + leak failsafe (~$20 total) — closes both in-tube hazards.
2. Rewrite snag recovery to eliminate solo free-diving — a paragraph, today.
3. Prototype dual-CSI encode + decide the Pi software stack (ADR-017)
   before buying pipe.
4. Re-scope the housing question: field battery swap + external compass.
5. One numbers-propagation pass (cost, endurance, vacuum, tether, subtotals).
