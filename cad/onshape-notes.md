# Onshape — notes for agents

Researched **2026-09-27** so later sessions don't have to redo it. Onshape
ships every ~3 weeks; before relying on anything version-specific, check the
newest "Improvements to Onshape — <date>" post on forum.onshape.com and the
API changelog (links at the bottom). Update this file when you do.

## What an agent can and can't do here

**No agent in this repo can drive the Onshape GUI.** The user models; the
agent plans, sets dimensions, reviews, and analyses exports. Four ways to go
further, in order of cost:

1. **Guide the user.** Give numbered steps with named Onshape features
   (Sketch, Extrude New/Add/Remove, Hole, Linear pattern, Variable,
   configurations) and the exact dimension expressions (`#stereo_baseline/2`). The
   user has "dabbled" — explain concepts once, briefly.
2. **Analyse exported geometry locally.** The user exports STL/STEP to
   Windows `Downloads` (`/mnt/c/Users/roland/Downloads` from WSL). Recipe that
   works, in the session scratchpad (the system Python has no numpy):

   ```bash
   python3 -m venv venv && ./venv/bin/pip install -q numpy scipy networkx shapely rtree trimesh matplotlib
   ```

   `trimesh.load()` for bounds/volume/`split()` into bodies; `m.section()` for
   cross-sections; matplotlib `Poly3DCollection` to render PNG views you can
   then Read. `split()` needs scipy or networkx installed.
3. **FeatureScript MCP Server (Onshape Labs, early access, July 2026).**
   Official. Lets Claude write, test and refine **custom features**
   (FeatureScript in a Feature Studio) from natural language — a
   text → code → CAD route. It is not documented as a general "edit my Part
   Studio" tool. Setup, per Onshape's tech tip:
   - subscribe to **FeatureScript MCP Server** in the Onshape App Store;
   - `claude mcp add --transport http onshape https://fs-mcp.labs.onshape.app/mcp`;
   - authorise in the browser when Claude Code prompts; `/mcp` to
     re-authenticate if its tools vanish.

   It writes into the user's documents — **ask before setting it up.** Cost
   was not stated. App Store app calls do not count against the API quota.
4. **REST API with the user's keys.** Keys now live in the user's Onshape
   preferences (moved from the dev portal, rel-1.204). **The quota is tiny on
   Free/Standard: 2,500 calls per user per year** (~7/day), counted for API
   keys and private OAuth apps, including API Explorer calls; exceeding a rate
   limit returns HTTP 429. Never poll; batch; prefer one export over many
   reads. Third-party MCP servers (e.g. `altendky/onshape-mcp`,
   `Casys-AI/mcp-onshape`, `onshape-claude-bridge`) exist but are unvetted and
   spend this same quota.

## Plans (as of 2026-09)

| Plan | Price | Relevant terms |
|---|---|---|
| Free | $0 | **Non-commercial, documents are public.** API 2,500 calls/user/yr. A third-party page claims a 10-document / 100 MB private cap — unverified against Onshape's own terms |
| Standard | $1,500/user/yr | Private storage, support. API 2,500/user/yr |
| Professional | $2,500/user/yr | PDM, simulation, rendering, CAM. API 5,000/user/yr |
| Enterprise | custom | API 10,000/full user/yr |

The user's plan isn't recorded. CARP's GitHub repo is public, so public
Onshape documents don't expose anything new.

## API

- Current version **V17** (rel-1.220, 2026-08-28). V13–V16 landed Jan–May
  2026 (V16: assembly suppression states).
- **Direct export** endpoints for Part Studios and Assemblies to STEP, glTF,
  OBJ, SolidWorks (rel-1.199); STL has a `mode` parameter (rel-1.195); async
  STEP export for Part Studios (rel-1.198).
- 19 new webhook event types (rel-1.221), mass properties with named
  positions, material library endpoints.

## 2026 product changes worth knowing for this project

| When | Change | Why it matters here |
|---|---|---|
| Jan 9 | Revolve gains Up to Next / Part / Vertex / Face | Dome and pilot-ring modelling |
| Mar | Named assembly positions link to in-context features | Sled in/out positions |
| Jun 5 | Routing curves with a target length | FFC / cable length from the CAD path (`bom.md` pending cable row) |
| Jun 26 | Asynchronous simulation | Lid flex check if ever wanted |
| Aug 28 | **Variable Studio parameters readable from FeatureScript** | Custom features can use `stereo_baseline` etc. directly |
| Aug 28 | Orient normal to sketch (auto camera); resize planes to bounding box | Beginner friendliness |
| Aug 28 | New Learning Center course: **Introduction to Configurations** | Spacer-thickness configurations (`cad/README.md`) |
| Sep 18 | Reset configurations to defaults; view-only document mode; filter by warnings; configurable section-view interference colour | Safer review of the user's documents |
| Sep 18 | **URDF export can emit GLB meshes** | ROS 2 robot description for the vehicle, later |
| Sep 18 | Dynamic suppression in assemblies (suppress parts/patterns/mates from values) | Acrylic vs aluminium lid variants in one assembly |
| 2026 | AI Advisor in-app (help, best practice, troubleshooting); roadmap: LLM-assisted FeatureScript, AI search, AI quick render, AI agents as project members | Point the user at AI Advisor for "how do I…" questions |

## Gotchas seen in this project

- **Extrude "New" vs "Add".** The user's practice Pi 5 holder
  (`prints/pi_bracket.stl`) exported as ~11 overlapping solids (plate,
  standoffs, pins) that were never merged, so the STL is not watertight.
  The slicer coped and it printed, but tell the user to use *Add* (or a
  Boolean union) so each printed part is one solid.
- **Never Mirror a camera seat** — use Linear pattern or a transform copy.
  Mirroring flips the 1.3 mm optical-axis offset and the connector side
  (`docs/sled.md`: both boards must be identical, not mirrored).
- Units: everything in this repo is mm; say so in every dimension you hand
  the user.
- **Printed threads: the Plastic Thread custom feature** (william_knoblauch,
  [doc](https://cad.onshape.com/documents/7a5d17f7ab4323f51774364f/v/40e5786c17172c1c23f38138/e/31ca9e4b737302343e72270b)).
  Onshape's Hole threads are cosmetic only. Add it by pasting that link in
  *Add custom features → Other documents*; searching "plastic threads"
  mostly finds greyed-out documents that only use it. Select the stud's
  cylinder and the nut's hole together so the threads match; presets
  Close / Normal / Loose.
  - **Draw the hole at the nominal size (Ø6 for M6), not the minor
    diameter.** The feature builds the internal thread around the selected
    hole; a Ø4.9 hole gave an "M4.9" nut that interfered with the M6 stud
    by ~0.5 on diameter (coupon B, 2026-09-28).
  - Its *View* panel (pitch, TPI, min layer) is read-only and did not
    reflect the Advanced-tab inputs (showed 3.175 pitch for a 1 mm thread,
    min layer blank). Measure the geometry instead.
  - Measured clearance on M6 × 1.0 (radial, per side): Close 0.22, Normal
    0.28, Loose 0.33.
- **Copy-pasted sketch text keeps the original string** — edit every
  pasted label (coupon A shipped three "1.85" pin labels at first).
- **A sketch hides itself once a feature consumes it.** To reference its
  geometry from a later sketch (e.g. a pattern centreline), show it with
  the eye icon in the feature list.
- **Check exported STLs locally.** The user's Windows Downloads is
  `/mnt/c/Users/roland/Downloads/`; parse the binary STL in Python
  (bounding box, Z levels, per-part split by shared vertices, thread radii)
  — it caught a 5 mm-for-0.5 mm pin height and the undersized nut threads.

## Sources

- Release posts: [Sep 18](https://forum.onshape.com/discussion/31763/improvements-to-onshape-september-18-2026),
  [Aug 28](https://forum.onshape.com/discussion/31629/improvements-to-onshape-august-28-2026),
  [Jun 26](https://forum.onshape.com/discussion/31232/improvements-to-onshape-june-26-2026),
  [Jun 5](https://forum.onshape.com/discussion/31101/improvements-to-onshape-june-5-2026),
  [Jan 9](https://forum.onshape.com/discussion/29760/improvements-to-onshape-january-9th-2026),
  [March highlights](https://www.onshape.com/en/blog/cloud-native-cad-software-automatic-updates-new-features)
- [API changelog](https://onshape-public.github.io/docs/changelog/) ·
  [API limits](https://onshape-public.github.io/docs/auth/limits/)
- [FeatureScript MCP + Claude Code tech tip](https://www.onshape.com/en/resource-center/tech-tips/connect-featurescript-mcp-server-claude-code) ·
  [Getting started with the FeatureScript MCP Server](https://www.onshape.com/en/blog/get-started-featurescript-mcp-server)
- [AI in Onshape](https://www.onshape.com/en/blog/ai-artificial-intelligence-cloud-native-cad-pdm-platform) ·
  [Pricing](https://www.onshape.com/en/pricing)
