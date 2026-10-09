# Changelog

## 0.1.0 — 2026-10-09

First build (MVP). Green-lit by Dennis after red-pen review of the plan.

- Stage 0 Import: mesh picker, four source types (incl. AI-generated as
  first-class), project folder + manifest, units check with user confirmation.
  Mesh shown in the 3D view.
- Stage 1 Quality gate: four metrics + verdict in CLI vocabulary.
  needs-rescan is an honest stop; AI meshes get "regenerate or clean up" copy.
- Stage 2 Analyze: worker-thread analysis with progress/cancel, bbox,
  planar/cylindrical fractions, symmetry, track decision + confidence,
  track override dropdown, measurements JSON + aligned STL (shown in 3D view).
- Deviation check: CloudCompare cloud-to-mesh as a soft dependency with loud
  degradation. Max/mean/p95 + pass/fail vs tolerance.
- Engine single-sourced from mesh-to-cad via `sync_engine.sh` (+ `--check`).
- No hardcoded paths; no third-party workbench dependencies; MIT.
