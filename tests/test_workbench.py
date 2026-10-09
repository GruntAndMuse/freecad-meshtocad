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
        _WB_ROOT / "meshtocad" / "commands" / "cmd_import.py",
        _WB_ROOT / "meshtocad" / "commands" / "cmd_quality.py",
        _WB_ROOT / "meshtocad" / "commands" / "cmd_analyze.py",
        _WB_ROOT / "meshtocad" / "commands" / "cmd_deviation.py",
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
