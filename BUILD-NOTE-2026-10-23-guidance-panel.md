# Build note — Rebuild guidance panel (post-MVP unit 1), 2026-10-23

Lane: FreeCAD workbench, local tree only. No push (pushes are gated).

## State on arrival (verified first-hand)

- The panel already exists from the 0.2.0 post-MVP build (commits
  ced9db8..166fffb, local): `commands/cmd_rebuild.py` (RebuildPanel on
  the shared StagePanel base — bound-method slots, pure QThread worker
  per the house threading rules), app logic in `meshtocad/guidance.py`,
  generic rendering in `meshtocad/framework/guidance.py`.
- Full suite run first-hand 2026-10-23: engine 9/9, freecadcmd 29/29,
  GUI (xvfb) 29/29 = **67/67 green** before any edit.

## Gap found vs the unit brief (analysis detail not surfaced)

Analyze records three things the guidance never showed:

1. `cylindrical_detail` — per-dominant-plane cylindrical wall/bore face
   counts + full-wrap flag (only the aggregate fraction was shown).
2. `hole_detection` — a *status* record, NOT detected holes
   (watertight → not-applicable; open mesh → section-segment counts, a
   complexity signal; failed → unavailable). Surfaced verbatim-honest,
   never dressed up as a hole list.
3. `manifest["deviation"]` — the recorded deviation summary (max/mean/
   p95 vs tolerance, pass/fail). Guidance runs before Deviation on a
   first pass, but on iteration passes the modeler should see where
   the current solid stands without leaving the panel.

## Work done this unit

- `meshtocad/guidance.py`: `cylinders_section()`, `holes_section()`,
  `deviation_section()` (app layer, pure); `build_reference` appends
  the sections after Dominant planes / before Symmetry (deviation
  last) and returns the recorded deviation in its result dict.
- `commands/cmd_rebuild.py`: panel result shows a "Last deviation
  check" summary line when one is on record.
- Tests extended in the established style: headless section tests
  (test_engine.py), end-to-end reference-content checks
  (test_workbench.py). GUI tier unchanged — it covers panel
  construction/lifecycle; the new content is logic, covered below it.

## Verification (2026-10-23, first-hand)

- Full suite after the change: engine **10/10** (was 9), freecadcmd
  **35/35** (was 29, +6 guidance checks), GUI **29/29** — **74/74
  green** (baseline on arrival was 67/67).
- Eyeball check: reference rendered from the real bracket sample —
  cylindrical section shows the true wall data (392 faces, full wrap,
  per plane normal), hole section carries Analyze's verbatim status,
  deviation section shows FAIL summary with the re-run caveat.

## Remaining for the program (not this unit)

- Unit 2: verification report — already built in 0.2.0 (see README);
  lane should verify, not rebuild.
- Unit 3: STEP/STL/TechDraw export — already built in 0.2.0; the
  TechDraw PDF path is GUI-tier verified.
- Still manual by design: the rebuild itself; organic surface loop.
