# MeshToCAD — FreeCAD Workbench

Bring a mesh in (scan, download, or AI-generated) and run the
[mesh-to-cad](https://github.com/GruntAndMuse/mesh-to-cad) pipeline from
inside FreeCAD. MIT licensed.

**What it does:** intake with units check → quality gate → geometry
analysis → rebuild guidance → deviation check → verification report →
STEP/STL/TechDraw export. Seven toolbar buttons, in pipeline order — the
buttons themselves won't let you run stages out of order.

**What it doesn't do:** one-click scan-to-CAD. The pipeline's honest limits
carry over unchanged: no magic buttons, no invented geometry, and a
`needs-rescan` verdict is a feature, not a bug. Until a stage is automated,
the task panels explain themselves — the directions ARE the automation.

## Install

1. In FreeCAD: **Tools → Addon Manager → search "MeshToCAD" → Install**.
   (Manual: copy this folder into FreeCAD's `Mod/` directory —
   find it via `FreeCAD.getUserAppDataDir()` in the Python console. Works
   from any drive; nothing here assumes `C:`.)
2. Restart FreeCAD, switch to the **MeshToCAD** workbench.
3. First activation checks for `trimesh` and offers a guided install if it's
   missing (pinned versions, into FreeCAD's own package folder — no system
   changes).

**CloudCompare** (for the deviation check) is a soft dependency: install it
from [cloudcompare.org](https://www.cloudcompare.org/) if you want that
stage. Everything else works without it, and the panel tells you exactly
what's missing instead of failing silently.

## The pipeline, briefly

| Button | Stage | What happens |
|---|---|---|
| Import mesh | 0 — Intake | File picker, source type (scanner / download / photogrammetry / **AI-generated**), project folder. Original copied to `input/`, never modified. Units check — the pipeline refuses to guess here, you confirm. |
| Quality gate | 1 — Cleanup gate | Four metrics + verdict: clean, noisy, or needs-rescan. Rescan is an honest stop. |
| Analyze mesh | 2 — Analysis | Runs in the background (dense scans take minutes). Bounding box, planar/cylindrical fractions, symmetry, and the **track decision** (prismatic / organic / mixed) with confidence. Aligned mesh shown for a visual sanity check. |
| Rebuild guidance | 3 — Rebuild | The rebuild is manual — no magic button. This panel docks every measurement the rebuild will be verified against, what each number means while modeling, and a track-specific checklist in build order. Also written to `analysis/<name>_reference.md`. |
| Deviation check | 3B — Deviation | Your modeled solid vs the input mesh, via CloudCompare. Max/mean/p95 + pass/fail against your tolerance. |
| Verify build | 4 — Verification | Dimension re-check (CAD vs the Analyze measurements, per-dimension tolerance, judged on the **worst** dimension), kernel geometry check, and the recorded deviation — combined into one verdict: pass / fail / **incomplete** (a check that didn't run is never dressed up as a pass). Report written to `verification/<name>_report.md`. |
| Export project | 5 — Output | STEP (per solid), STL, a copy of the document (FCStd), and a TechDraw drawing PDF (Front/Top/Right/Isometric) into `output/`. Anything that can't be produced is reported skipped/failed **with its reason**. |

Each project lives in a folder (`input/`, `analysis/`, `cad/`, …) with a
`manifest.json` — the same format the `mesh-to-cad` CLI writes, so CLI and
workbench projects are interchangeable. AI-generated meshes are a
first-class source type: the intake treats them as unitless (you set the
intended size), and every result reminds you the mesh carries no real
dimensions.

## For developers

- **Engine single-sourcing:** `meshtocad/engine/` holds copies of the
  pipeline scripts. Never hand-edit them — run `./sync_engine.sh` (or
  `./sync_engine.sh --check` in CI) to sync from the mesh-to-cad repo.
- **Threading rule:** long work runs in `QThread` workers (`meshtocad/
  threads.py`). Worker functions are pure — plain data in/out, no FreeCAD.
  Document objects are touched only in panel slots, which run on the main
  GUI thread. Get this wrong and FreeCAD crashes; the module docstring
  explains the pattern.
- **No hardcoded paths, anywhere.** Resolve from `__file__`, environment
  variables, or FreeCAD's own API.
- **Framework vs app:** `meshtocad/framework/` is the generic
  host-integration layer (guidance/verification/export planning, plus
  `freecad_io.py`, the FreeCAD host adapter) — it knows nothing about
  meshes or tracks and is the reusable template for future host
  integrations. The top-level `meshtocad` modules and `commands/` are
  the mesh-to-cad app layer on top of it.
- **Tests:** `tests/test_engine.py` (headless, no FreeCAD),
  `tests/test_workbench.py` (via `freecadcmd`), `tests/test_gui.py`
  (FreeCAD GUI under xvfb — workbench lifecycle, all seven panels, the
  worker-thread pattern, and the TechDraw PDF export that console mode
  can't do). Run everything with `./tests/run_tests.sh`.

## Roadmap

Post-MVP stages shipped in 0.2.0: rebuild guidance, verification
report, STEP/STL/TechDraw export. Still manual by design: the rebuild
itself (guided, not automated) and the organic surface-fitting loop.
