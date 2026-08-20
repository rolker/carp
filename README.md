# CARP — Cheap-Ass ROV Project

A low-cost, ROS 2–capable inspection ROV for relocating and imaging sidescan
sonar contacts in shallow water, deployed from a kayak.

## Mission

CARP is a long-daydreamed ROV build with a concrete first job. Sidescan and
bathymetry surveys produce contacts faster than anyone can dive them; CARP is
a cheap camera platform for closing that loop: drop on a contact, find it,
image it, and log the result against the sonar record.

That job drives the v1 design but isn't the only goal — the envelope below
describes the first site, not the vehicle's ambitions. Deeper sites are
expected later (see ADR-001).

**Operating envelope**

| Parameter | Value |
|---|---|
| Design depth (v1, first site) | 5 m |
| Expected visibility | ~3 m |
| Working radius | ~15 m from downline |
| Deployment | Kayak, tethered |
| Water | Freshwater primary; saltwater capable |
| Cost | ~$2,000 as built (the "$500 build" did not survive contact with procurement — see `docs/bom.md`) |

## Design posture

Current leanings from an early design brainstorm, not final commitments —
`docs/decisions.md` grades each record by how committed it actually is.

- **Tethered, not autonomous.** The tether is not a limitation to be removed —
  it carries Ethernet, enables one-way acoustic ranging, and is the recovery
  path. See `docs/decisions.md` ADR-009.
- **Relocation is the hard problem, not the vehicle.** With 3 m visibility you
  can sit on top of a target and not see it. The downline is the primary
  navigation aid.
- **ArduSub for control, ROS 2 for payload.** Pixhawk owns the control loop;
  the Pi owns cameras, logging, and future DSP.
- **Project11 interfaces where they transfer**, not the full autonomy stack.
  See ADR-010.

## Repository layout

```
docs/
  decisions.md          Architecture decision records
  bom.md                Bill of materials, ordered vs pending
  power-budget.md       Load analysis, battery sizing, wiring gauge
  wiring.md             Power tree, signal map, grounding rules
  frame-and-mixing.md   ArduSub motor matrices, verified from source
  bringup-checklist.md  Bench acceptance tests before anything is sealed
  navigation.md         Downline method, scaling lasers, acoustic ranging
  open-questions.md     Unresolved decisions
  prior-art.md          Survey of other cheap ROV builds, distilled lessons
params/
  ArduSub parameter files
```

## Status

Pre-build. Electronics ordered, mechanical design open.

## License

TBD
