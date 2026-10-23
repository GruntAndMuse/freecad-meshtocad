# -*- coding: utf-8 -*-
"""Workbench integration tests - run inside freecadcmd (console mode).

Run:  ~/workspace/freecad/freecadcmd /path/to/test_workbench.py

Exercises the same code paths the task panels use (project creation,
manifest read/write, engine calls, stage gating) without needing the GUI.
GUI-only modules (panels, workbench class) are compile-checked, not executed.

Exits 0 on success, 1 on failure. Prints TAP-ish lines for the log.
"""

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path


def _wb_root() -> Path:
    """freecadcmd exec's scripts without setting __file__ — resolve robustly."""
    candidates = []
    # 1. __file__ when the interpreter provides it (pytest, plain python)
    try:
        candidates.append(Path(__file__).parents[1])
    except NameError:
        pass
    # 2. the script path freecadcmd was given (argv[0])
    if sys.argv and sys.argv[0].endswith(".py"):
        candidates.append(Path(sys.argv[0]).resolve().parents[1])
    # 3. explicit env override
    if os.environ.get("MTC_WB_ROOT"):
        candidates.append(Path(os.environ["MTC_WB_ROOT"]))
    for c in candidates:
        if (c / "meshtocad" / "__init__.py").is_file():
            return c
    raise RuntimeError(
        "can't locate the freecad-workbench tree — set MTC_WB_ROOT")


_WB_ROOT = _wb_root()
if str(_WB_ROOT) not in sys.path:
    sys.path.insert(0, str(_WB_ROOT))

SAMPLES = Path.home() / "workspace" / "pipelines" / "mesh-to-cad" / "test-samples"

import FreeCAD  # noqa: E402  (must exist - we're inside freecadcmd)

from meshtocad import deps, engine, project  # noqa: E402

PASS = 0
FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"ok - {name}")
    else:
        FAIL += 1
        print(f"FAIL - {name} {detail}")


def main():
    print("FreeCAD:", FreeCAD.Version())

    # 1. deps layer (no GUI needed)
    ok, ver = deps.check_trimesh()
    check("trimesh detectable", ok, f"got {ver}")
    cc = deps.find_cloudcompare()
    cc_note = "found at " + cc if cc else ("not found - deviation will "
                                           "degrade loudly, as designed")
    print(f"  (cloudcompare: {cc_note})")
    idir = deps.additional_packages_dir()
    check("additional-packages dir derived", str(idir).endswith(
        "AdditionalPythonPackages"), str(idir))

    # 2. project creation (temp dir - never touches the real projects folder)
    tmp = Path(tempfile.mkdtemp(prefix="mtc_wb_test_"))
    sample = SAMPLES / "bracket_prismatic.stl"
    check("test sample exists", sample.is_file(), str(sample))
    try:
        manifest = project.create_project(sample, tmp, "scanner")
    except Exception as e:
        check("create_project", False, str(e))
        manifest = None
    check("create_project ok", manifest is not None)
    if manifest:
        check("input copy exists",
              Path(manifest["source"]["original_file"]).is_file())
        check("manifest saved",
              (Path(manifest["project_dir"]) / "manifest.json").is_file())
        check("stage import marked",
              project.stage_done(manifest, "import"))
        check("source type recorded",
              manifest["source"]["source_type"] == "scanner")

        # 3. engine through the panel's code path
        units = engine.check_units().suggest_units(
            Path(manifest["source"]["original_file"]))
        check("units suggestion", units["suggestion"] in (
            "millimeters", "meters", "micrometers-or-inches"), str(units))
        gate = engine.quality_gate().quality_gate(
            Path(manifest["source"]["original_file"]))
        check("quality verdict sane",
              gate["verdict"] in ("clean", "noisy", "needs-rescan"),
              str(gate["verdict"]))
        result, aligned = engine.analyze().analyze(
            Path(manifest["source"]["original_file"]))
        check("analyze track == prismatic",
              result["track_decision"] == "prismatic",
              str(result["track_decision"]))

        # 4. manifest round-trip with stage data (what the panels persist)
        manifest["source"]["units_check"] = {
            "suggestion": units["suggestion"],
            "scale_factor": units["scale_factor"],
            "confidence": units["confidence"],
        }
        manifest["quality"] = gate["verdict"]
        manifest["quality_reasons"] = gate["reasons"]
        project.mark_stage(manifest, "quality", True)
        manifest["track"] = result["track_decision"]
        manifest["track_confidence"] = result["track_confidence"]
        project.mark_stage(manifest, "analyze", True)
        project.record_tool_versions(manifest)
        project.save_manifest(manifest["project_dir"], manifest)
        reloaded = project.load_manifest(manifest["project_dir"])
        check("manifest round-trip",
              reloaded and reloaded["track"] == "prismatic"
              and project.stage_done(reloaded, "analyze"))

        # 4b. Post-MVP stages: guidance -> verify -> export (the same
        # functions the panels call; panels themselves are GUI-tested).
        from meshtocad import exporting, guidance, verification
        from meshtocad.framework import freecad_io
        from meshtocad.framework.exporting import plan_exports

        check("stage list is the full pipeline",
              project.STAGES == ("import", "quality", "analyze", "rebuild",
                                 "deviation", "verify", "export"))
        old = {"stages": {"import": True}}  # a 0.1.0-era manifest
        check("old manifest: new stages read as not-done",
              not project.stage_done(old, "verify"))
        project.mark_stage(old, "verify", True)
        check("old manifest: mark_stage accepts new stages",
              project.stage_done(old, "verify"))

        # The panel's Analyze stage writes the measurements JSON — mirror
        # that here so guidance/verify read the real file layout.
        import json as _json
        meas_path = (Path(manifest["project_dir"]) / "analysis"
                     / f"{sample.stem}_measurements.json")
        meas_path.write_text(_json.dumps(result, indent=2),
                             encoding="utf-8")

        ref = guidance.build_reference(manifest["project_dir"])
        check("guidance reference built", ref["error"] is None,
              str(ref["error"]))
        if ref["error"] is None:
            ref_text = Path(ref["reference_path"]).read_text(
                encoding="utf-8")
            check("guidance reference has checklist + numbers",
                  "## Rebuild checklist" in ref_text
                  and "Overall width (X)" in ref_text)
            # Analyze's full record reaches the reference: the hole
            # assessment status always renders; the box's planes carry
            # cylindrical detail entries.
            check("guidance reference has hole-assessment section",
                  "## Holes and openings" in ref_text)
            check("guidance reference has cylindrical section",
                  "## Cylindrical walls and bores" in ref_text)
            check("guidance: no deviation on record yet",
                  ref.get("deviation") is None
                  and "## Last deviation check" not in ref_text)
            # With a deviation check on record, guidance surfaces it —
            # the iteration-pass case.
            manifest["deviation"] = {"max_mm": 0.2, "mean_mm": 0.05,
                                      "p95_mm": 0.15, "tolerance_mm": 0.3,
                                      "passed": True}
            project.save_manifest(manifest["project_dir"], manifest)
            ref2 = guidance.build_reference(manifest["project_dir"])
            check("guidance rebuilt with deviation on record",
                  ref2["error"] is None, str(ref2["error"]))
            if ref2["error"] is None:
                ref2_text = Path(ref2["reference_path"]).read_text(
                    encoding="utf-8")
                check("guidance reference shows deviation summary",
                      "## Last deviation check" in ref2_text
                      and "max 0.2 mm" in ref2_text
                      and "PASS" in ref2_text)
                check("guidance result carries the deviation record",
                      ref2["deviation"]["passed"] is True)
            project.mark_stage(manifest, "rebuild", True)

        # A real CAD solid with exactly the measured extents.
        doc = FreeCAD.newDocument("verify_test")
        box = doc.addObject("Part::Box", "Model")
        ext = result["bounding_box_mm"]["extents"]
        box.Length, box.Width, box.Height = ext[0], ext[1], ext[2]
        doc.recompute()
        summary = freecad_io.shape_summary(box)
        check("shape_summary extents match the box",
              summary and summary["extents_mm"] == [round(float(v), 4)
                                                    for v in ext])
        geom = freecad_io.geometry_check(box.Shape)
        check("geometry check: box valid + closed, no problems",
              geom["ran"] and geom["valid"] and geom["closed"]
              and not geom["problems"], str(geom))

        vres = verification.run_verification(manifest, summary, geom,
                                             0.3, 0.1)
        check("verification report written", vres["error"] is None,
              str(vres["error"]))
        if vres["error"] is None:
            rows = {r["name"]: r["status"]
                    for r in vres["report"]["dimension_rows"]}
            check("verification: XYZ dimensions pass on exact box",
                  all(rows.get(f"Overall size {a}") == "pass"
                      for a in "XYZ"), str(rows))
            check("verification report file exists",
                  Path(vres["path"]).is_file())
            # With deviation on record + matching volume -> PASS verdict.
            manifest["deviation"] = {"max_mm": 0.2, "mean_mm": 0.05,
                                      "p95_mm": 0.15, "tolerance_mm": 0.3,
                                      "passed": True}
            exact = dict(summary)
            exact["volume_mm3"] = result["volume_mm3"]
            vres2 = verification.run_verification(manifest, exact, geom,
                                                  0.3, 0.1)
            check("verification: full pass when every check passes",
                  vres2["error"] is None
                  and vres2["report"]["verdict"] == "pass",
                  str(vres2.get("report", {}).get("summary")))
            if vres2["error"] is None:
                manifest["verification"] = vres2["report"]["summary"]
            project.mark_stage(manifest, "verify", True)

        # Export: plan from real document descriptors, write real files.
        descriptors = freecad_io.object_descriptors(doc)
        plan = plan_exports(exporting.SPEC.formats, descriptors,
                            ["step", "stl", "fcstd"], manifest["project"])
        check("export plan: 3 jobs, no skips",
              len(plan["jobs"]) == 3 and plan["skipped"] == [],
              str(plan))
        out_dir = Path(manifest["project_dir"]) / "output"
        written = []
        export_err = ""
        for job in plan["jobs"]:
            try:
                written.append(freecad_io.export_job(doc, job, out_dir))
            except Exception as e:
                export_err = f"{job['format']}: {e}"
        check("export writes STEP/STL/FCStd files",
              len(written) == 3
              and all(p.is_file() and p.stat().st_size > 0
                      for p in written), export_err)
        # Drawing PDF in console mode must degrade LOUDLY (TechDrawGui is
        # GUI-only) — a clear RuntimeError, never a silent success.
        plan_pdf = plan_exports(exporting.SPEC.formats, descriptors,
                                ["drawing-pdf"], manifest["project"])
        if plan_pdf["jobs"]:
            try:
                p = freecad_io.export_job(doc, plan_pdf["jobs"][0], out_dir)
                check("drawing export (GUI path available)", p.is_file())
            except RuntimeError as e:
                check("drawing export degrades loudly headless",
                      "GUI" in str(e), str(e))
        project.mark_stage(manifest, "export", True)
        project.save_manifest(manifest["project_dir"], manifest)
        reloaded2 = project.load_manifest(manifest["project_dir"])
        check("post-MVP stages round-trip",
              all(project.stage_done(reloaded2, s)
                  for s in ("rebuild", "verify", "export")))

    # 5. AI source type accepted (red-pen decision #6)
    try:
        m2 = project.create_project(sample, tmp, "ai-generated")
        check("ai-generated source type",
              m2["source"]["source_type"] == "ai-generated")
    except Exception as e:
        check("ai-generated source type", False, str(e))

    # 6. GUI modules at least compile (can't execute without a display here)
    import py_compile
    gui_files = [
        _WB_ROOT / "InitGui.py",
        _WB_ROOT / "meshtocad" / "workbench.py",
        _WB_ROOT / "meshtocad" / "threads.py",
        _WB_ROOT / "meshtocad" / "ui" / "panels.py",
        _WB_ROOT / "meshtocad" / "guidance.py",
        _WB_ROOT / "meshtocad" / "verification.py",
        _WB_ROOT / "meshtocad" / "exporting.py",
        _WB_ROOT / "meshtocad" / "framework" / "guidance.py",
        _WB_ROOT / "meshtocad" / "framework" / "verification.py",
        _WB_ROOT / "meshtocad" / "framework" / "exporting.py",
        _WB_ROOT / "meshtocad" / "framework" / "freecad_io.py",
        _WB_ROOT / "meshtocad" / "commands" / "cmd_import.py",
        _WB_ROOT / "meshtocad" / "commands" / "cmd_quality.py",
        _WB_ROOT / "meshtocad" / "commands" / "cmd_analyze.py",
        _WB_ROOT / "meshtocad" / "commands" / "cmd_rebuild.py",
        _WB_ROOT / "meshtocad" / "commands" / "cmd_deviation.py",
        _WB_ROOT / "meshtocad" / "commands" / "cmd_verify.py",
        _WB_ROOT / "meshtocad" / "commands" / "cmd_export.py",
    ]
    compile_ok = True
    for f in gui_files:
        try:
            py_compile.compile(str(f), doraise=True)
        except Exception as e:
            compile_ok = False
            print(f"  compile fail {f.name}: {e}")
    check("GUI modules compile", compile_ok)

    shutil.rmtree(tmp, ignore_errors=True)
    print(f"\n{PASS} passed, {FAIL} failed")
    return FAIL


# NOTE: do NOT call sys.exit() here — freecadcmd discards buffered stdout
# when a script raises SystemExit, swallowing the whole report. Raising a
# real exception on failure gives freecadcmd something to report AND a
# non-zero exit.
_failures = main()
if _failures:
    raise RuntimeError(f"{_failures} workbench test(s) failed")
