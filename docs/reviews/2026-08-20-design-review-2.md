# CARP Design Review — 2026-08-20 (second pass)

Independent review by a second agent. The first review (`2026-08-20-design-review.md`)
is excellent and most of its findings have already been incorporated into the source docs.
This pass checks whether anything was missed or left unacted-on, and adds new observations.

Findings ranked BLOCKER / MAJOR / MINOR.

---

## What the first review got right that remains solid

The core architecture (ArduSub + Pi over USB/MAVLink), buoyancy math, wiring gauge
analysis, vacuum gate corrected to 15 inHg, acoustic ranging math and
tether-as-sync-path argument, snag protocol rewrite, and the decision to stay tethered
are all sound. `frame-and-mixing.md`, `sidescan-datum.md`, and `prior-art.md` remain
correct as written.

---

## First-review findings that are still open (not yet acted on)

### B2 carry-forward — snag protocol not in the checklist
ADR-009 now has the correct rewrite. `bringup-checklist.md` Phase 5 has no snag drill
or "haul-test from multiple bearings" step. A written procedure that is never practiced
is not a procedure.

### M3 carry-forward — external compass not on any BOM line
The first review calls for a ~$15–30 external I2C compass and MagFit in Phase 3/5.
Neither the BOM pending section nor the bringup checklist has been updated. It will
surface on first water, not in a drawer.

### M4 carry-forward — ADR-017 not written
The first review calls for ADR-017 (Pi software stack decision) before Phase 3. It is
not in `open-questions.md`, not in `decisions.md`, and not in any checklist. It will
get skipped unless explicitly tracked.

### Minor 10 carry-forward — thermal soak duration discrepancy
The first review recommended 45 min sealed soak; `bringup-checklist.md` Phase 3 says
30 min. One of them is wrong.

### Minor 12 carry-forward — no field-day ops checklist
`bringup-checklist.md` covers bench phases only. First dive needs its own card: cell
voltages, vacuum hold check, tether flaked, quick-release confirmed, downline dropped
and clipped, disarm before hands near props. This was flagged and not created.

---

## MAJOR

### MA1. Relief path in the endcap is called for but never specified

ADR-013, `power-budget.md`, and the bringup checklist all say "relief path in
endcap — confirmed." No doc says what it is: a Schrader valve? A burst disk? A
pop-off rated to what pressure? Without a specific part and a test procedure, this is
a checkbox with no method. A swollen 4S pouch in a sealed PVC tube with a vague
"relief path" is still an unresolved hazard.

**Fix (~$5):** one Schrader valve stem in an endcap hole, core in during diving (seals
against water), core removable for bench venting. Same part already called for by the
vacuum test (it is already in the BOM pending section as "Schrader valve stem + core
tool" — confirm it serves both roles and cross-reference in ADR-013).

### MA2. Camera pod / housing layout is the most blocking unresolved mechanical question

The 2" dome cameras are ordered. Camera pods are "a candidate" in `open-questions.md`.
CSI ribbons are not wet-rated and cannot pass a gland — correctly flagged in the first
review (M5) — but no fallback is specified. The main housing endcap cannot carry two
~70 mm flanges on a 4" cap. There is no pod design, no housing diameter decision, and
no frame layout. These three questions are the same problem and must be resolved before
pipe is purchased.

**Fix ($0):** add "lay out camera geometry and housing diameter on paper before buying
any pipe" as a Phase 0 item, immediately after the battery dimensions are measured on
arrival.

### MA3. XT90-S anti-spark resistor is a consumable — not mentioned anywhere

The pre-charge resistor in the XT90-S male pin is rated for a finite number of
insertions (typically 30–50) before it degrades and the connector becomes a plain XT90.
Field operations mean connecting and disconnecting every dive. There is no mention of
inspecting or replacing the anti-spark element, and the XT90-S is currently the only
inrush protection. When it fails silently, every subsequent connect is a hard spark
into a 6 Ah pack through a 10 AWG lead inside a sealed tube.

**Fix (~$8):** add "inspect XT90-S male pin for contact pitting every N dives; carry
a spare male XT90-S in the field box" to the field ops checklist. Document the wear
limit.

---

## MINOR

1. **Tether working-radius math is never closed.** `navigation.md` assumes "15 m from
   downline." If the tether routes boat → downline clip → ROV, the effective horizontal
   radius is tether length minus downline vertical depth (~5 m), leaving ~10 m. Draw
   the rigging geometry explicitly.

2. **Pololu D36V50F5 margin is thin and not documented as accepted risk.** 25 W peak
   Pi load = 91% of the 27.5 W converter rating, in a sealed tube with no active
   cooling. USB audio + NVMe tighten this further. Either document the accepted risk or
   replace with a 6–8 A part.

3. **Actual tether link speed on CCA Cat6 is never verified.** The offload plan
   (ADR-016, "100 GB in 20 min") needs 1000BASE-T. CCA Cat6 at this length may or may
   not negotiate gigabit — some runs degrade to 100 Mbps or worse. Test once on the
   actual tether/Opal combination and record it before the storage architecture hardens.

4. **No bandwidth budget for two RTSP streams + MAVLink + ROS topics on one 100 Mbps
   link.** Two 1080p streams at moderate bitrate are 8–16 Mbps; `udp_bridge` topic
   volume is unknown. This probably fits, but nobody has added it up.

5. **2" acrylic domes have no spares.** $10.69 each, "handle gently." A cracked dome
   mid-season ends the mission. One spare is cheap insurance — especially since they
   are described as having already been ordered through a single third-party seller.

6. **Tether attachment: navigation.md says clip to downline; bom.md says to the
   boat.** The first review flagged this (Minor 3) as "probably compatible — draw the
   rigging." It has not been drawn. The rigging diagram resolves this and the working-
   radius question simultaneously.

7. **8BitDo + Cockpit over WiFi: no range/link-reliability test planned.** The Opal's
   5 GHz AP has ~20–30 m open-air range. Water spray and a metal kayak hull can
   degrade this. The backup control path if WiFi drops is the tether; acceptable, but
   worth a bench qualification (router in the dry box, phone at operating distance,
   confirm no dropout under motion).

---

## Sequencing additions

Two Phase 0 items deserve promotion from "before Phase 3":

1. **Camera geometry + housing layout** — before pipe purchase, which is earlier than
   Phase 3.
2. **ADR-017 (Pi software stack)** — before *any* software integration work in Phase 3.

And one Phase 5 addition: **snag drill** — gentle haul-test from multiple bearings,
confirm the protocol works with the actual rigging before the first unsupervised dive.

---

## Top 5 priorities from this pass

1. Specify the LiPo relief path (name the part, cross-reference the Schrader stem
   already in the BOM) — closes MA1 in one sentence in ADR-013.
2. Add camera geometry / housing layout session as Phase 0 item — closes MA2.
3. Add XT90-S wear note and inspection step to field ops checklist — closes MA3.
4. Write ADR-017 and add the external compass to BOM pending — closes M3 and M4
   carry-forwards from the first review.
5. Write the field-day ops checklist — closes the Minor 12 carry-forward.
