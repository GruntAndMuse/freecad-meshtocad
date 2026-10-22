# Changelog

## 0.2.0 — 2026-10-21

Post-MVP stages, in the deferred build order. The generic
host-integration framework was factored out along the way
(`meshtocad/framework/`) — guidance, verification, and export planning
are pipeline-agnostic; mesh-to-cad specifics live in the app layer.

- Stage 3 Rebuild guidance: measure-and-remodel reference panel —
  every measurement the rebuild will be verified against, what each
  means while modeling, track-specific checklists (prismatic / organic
  / mixed), dominant planes and symmetry notes. Written to
  `analysis/<name>_reference.md`. The rebuild stays manual and the
  panel says so — no magic rebuild button.
- Stage 4 Verification report: dimension re-check against the Analyze
  measurements (judged on the worst dimension, never the average),
  kernel geometry check, and the recorded deviation result, combined
  into pass / fail / incomplete — a check that didn't run (e.g. no
  CloudCompare) yields INCOMPLETE, never a dressed-up pass. Written to
  `verification/<name>_report.md`; verdict recorded in the manifest.
  AI-mesh reports state plainly that verification means "matches the
  AI mesh," not "matches reality."
- Stage 5 Export: STEP (per solid), STL (0.1 mm tessellation, same as
  the deviation stage checks), FCStd document copy, and a TechDraw
  drawing PDF (Front/Top/Right/Isometric, stock A4 template) into
  `output/`. Unproducible formats are skipped/failed with reasons.
  Export runs synchronously on the main thread by design (the writers
  need live document objects; see cmd_export.py). In console mode the
  drawing PDF degrades loudly instead of pretending.
- Toolbar is now the full pipeline: Import → Quality → Analyze →
  Rebuild → Deviation → Verify → Export, gated by the manifest as
  before. Deviation's next-step now chains to Verify.
- Tests: 67 checks (engine 9, freecadcmd 29, GUI 29) — run_tests.sh
  now also runs the GUI class under xvfb when available. Hardened the
  GUI test harness: the 30 s worker timeout could fire after a
  successful finish and record a phantom failure, and
  QApplication.quit() proved unreliable with modified documents open
  (one run hung >6 min after passing) — the test now stops its timer,
  writes its results to a file, and exits deterministically.
- TechDraw: the Right drawing view needs an explicit XDirection or
  its projection fails to build ("failed to create projection CS") —
  caught from the GUI run's console warnings and fixed in the adapter.

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
