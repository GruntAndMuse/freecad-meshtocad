# -*- coding: utf-8 -*-
"""Engine tests — headless, no FreeCAD needed.

Run:  python3 test_engine.py
   or pytest test_engine.py

Uses the pipeline's own test samples (known answers): bracket_prismatic.stl
is prismatic, blob_organic.stl is organic.
"""

import sys
from pathlib import Path

# Workbench root on the path so `meshtocad` imports.
_WB_ROOT = Path(__file__).parents[1]
if str(_WB_ROOT) not in sys.path:
    sys.path.insert(0, str(_WB_ROOT))

from meshtocad import engine  # noqa: E402

SAMPLES = Path.home() / "workspace" / "pipelines" / "mesh-to-cad" / "test-samples"
# Fall back to a relative guess if HOME differs (CI checkouts).
if not SAMPLES.is_dir():
    SAMPLES = _WB_ROOT.parent / "pipelines" / "mesh-to-cad" / "test-samples"


def _sample(name: str) -> Path:
    p = SAMPLES / name
    assert p.is_file(), f"test sample missing: {p}"
    return p


def test_units_bracket():
    units = engine.check_units().suggest_units(_sample("bracket_prismatic.stl"))
    assert units["suggestion"] in ("millimeters", "meters",
                                   "micrometers-or-inches"), units
    assert units["confidence"] in ("high", "medium"), units
    assert units["diagonal_file_units"] > 0
    print(f"  units: {units['suggestion']} ({units['confidence']})")


def test_quality_gate_bracket():
    gate = engine.quality_gate().quality_gate(_sample("bracket_prismatic.stl"))
    assert gate["verdict"] in ("clean", "noisy", "needs-rescan"), gate
    assert isinstance(gate["reasons"], list)
    print(f"  quality: {gate['verdict']}")


def test_analyze_bracket_is_prismatic():
    result, aligned = engine.analyze().analyze(_sample("bracket_prismatic.stl"))
    assert result["track_decision"] == "prismatic", result["track_decision"]
    assert aligned is not None
    assert "bounding_box_mm" in result
    print(f"  bracket track: {result['track_decision']} "
          f"({result['track_confidence']})")


def test_analyze_blob_is_organic():
    result, aligned = engine.analyze().analyze(_sample("blob_organic.stl"))
    assert result["track_decision"] == "organic", result["track_decision"]
    print(f"  blob track: {result['track_decision']} "
          f"({result['track_confidence']})")


def test_deviation_module_loads():
    dev = engine.deviation()
    assert callable(dev.measure_clean)
    assert callable(dev.find_cloudcompare)
    print("  deviation module loads")


# --- Post-MVP framework + app-layer tests (pure, no FreeCAD) ---------------

def _bracket_measurements() -> dict:
    import json
    result, _ = engine.analyze().analyze(_sample("bracket_prismatic.stl"))
    return json.loads(json.dumps(result))


def test_framework_guidance_rows():
    from meshtocad import guidance
    from meshtocad.framework.guidance import (
        build_reference_rows, dig, missing_labels, render_reference_markdown)

    m = _bracket_measurements()
    assert dig(m, "bounding_box_mm.extents[0]") == m["bounding_box_mm"]["extents"][0]
    assert dig(m, "nope.missing") is None
    spec = guidance.spec_for_track("prismatic")
    rows = build_reference_rows(m, spec.fields)
    by_label = {r["label"]: r for r in rows}
    assert by_label["Overall width (X)"]["present"]
    assert by_label["Track"]["value_text"] == "prismatic"
    md = render_reference_markdown("T", ["intro"], rows, spec.checklist,
                                   [guidance.planes_section(m)])
    assert "## Rebuild checklist" in md and "Dominant planes" in md
    # Missing measurements stay visible, never silently dropped.
    rows2 = build_reference_rows({}, spec.fields)
    assert missing_labels(rows2), "empty measurements must report missing"
    print("  guidance rows + markdown ok")


def test_app_guidance_sections():
    from meshtocad import guidance

    # Cylindrical detail: where the walls/bores live, per dominant plane.
    m = {"cylindrical_detail": [
        {"plane_normal": [0, 0, 1], "side_faces": 42, "full_coverage": True},
        {"plane_normal": [1, 0, 0], "side_faces": 7, "full_coverage": False},
    ]}
    sec = guidance.cylinders_section(m)
    assert sec is not None and sec[0] == "Cylindrical walls and bores"
    assert "42 faces" in sec[1][0] and "full circumference" in sec[1][0]
    assert "partial wrap" in sec[1][1]
    assert guidance.cylinders_section({}) is None
    assert guidance.cylinders_section({"cylindrical_detail": []}) is None

    # Hole assessment is a STATUS record, never a hole count — the
    # section must carry Analyze's own detail and invent nothing.
    det = {"status": "not-applicable",
           "detail": "watertight — no boundary loops to find."}
    sec = guidance.holes_section({"hole_detection": det})
    assert sec is not None and "not-applicable" in sec[1][0]
    assert "no boundary loops" in sec[1][0]
    det2 = {"status": "ok",
            "detail": "mesh is open; section-segment counts",
            "section_segments_xyz": [12, 4, 30]}
    sec = guidance.holes_section({"hole_detection": det2})
    assert "X: 12" in sec[1][1] and "Z: 30" in sec[1][1]
    det3 = {"status": "failed", "detail": "section analysis raised",
            "error": "boom"}
    sec = guidance.holes_section({"hole_detection": det3})
    assert "Do not assume" in sec[1][1]
    assert guidance.holes_section({}) is None
    assert guidance.holes_section({"hole_detection": "junk"}) is None

    # Deviation summary: only when a check is actually on record.
    assert guidance.deviation_section({}) is None
    assert guidance.deviation_section({"deviation": {"passed": True}}) is None
    mf = {"deviation": {"max_mm": 0.42, "mean_mm": 0.1, "p95_mm": 0.3,
                        "tolerance_mm": 0.3, "passed": False}}
    sec = guidance.deviation_section(mf)
    assert sec is not None and sec[0] == "Last deviation check"
    assert "max 0.42 mm" in sec[1][0] and "FAIL" in sec[1][0]
    print("  guidance sections (cylinders / holes-status / deviation) ok")


def test_framework_verification_verdicts():
    from meshtocad.framework import verification as fw

    pairs = [
        {"name": "X", "expected": 100.0, "actual": 100.1, "tolerance": 0.3},
        {"name": "Y", "expected": 50.0, "actual": 49.0, "tolerance": 0.3},
        {"name": "Z", "expected": None, "actual": 10.0, "tolerance": 0.3},
    ]
    rows = fw.compare_dimensions(pairs)
    assert [r["status"] for r in rows] == ["pass", "fail", "not-run"], rows
    assert fw.worst_instance(rows)["name"] == "Y"
    assert fw.overall_verdict([rows]) == "fail"  # fail beats incomplete
    ok = fw.compare_dimensions(pairs[:1])
    assert fw.overall_verdict([ok]) == "pass"
    assert fw.overall_verdict([ok, [{"status": "not-run"}]]) == "incomplete"
    assert fw.overall_verdict([[]]) == "incomplete"
    print("  verification verdict logic ok")


def test_app_verification_end_to_end_pure():
    from meshtocad import verification

    m = _bracket_measurements()
    manifest = {
        "project": "bracket_prismatic",
        "project_dir": "/nonexistent",
        "source": {"original_file": "/x/bracket_prismatic.stl",
                   "source_type": "scanner"},
    }
    # Patch the measurements lookup at its source (guidance loader).
    import meshtocad.verification as vmod
    orig = vmod.load_measurements
    vmod.load_measurements = lambda _mf: m
    try:
        summary = {"label": "Box", "extents_mm": m["bounding_box_mm"]["extents"],
                   "volume_mm3": m["volume_mm3"]}
        geom_pass = {"ran": True, "valid": True, "closed": True,
                     "problems": []}
        # No deviation on record -> INCOMPLETE even when everything else passes.
        r = verification.build_report(manifest, summary, geom_pass, 0.3, 0.1)
        assert r["verdict"] == "incomplete", r["summary"]
        assert "Status: not-run" in r["markdown"]  # deviation section
        # Deviation passed -> PASS.
        manifest["deviation"] = {"max_mm": 0.2, "mean_mm": 0.05,
                                  "p95_mm": 0.15, "tolerance_mm": 0.3,
                                  "passed": True}
        r = verification.build_report(manifest, summary, geom_pass, 0.3, 0.1)
        assert r["verdict"] == "pass", r["summary"]
        # Dimension off by 5 mm -> FAIL, and it is the worst instance.
        bad = dict(summary)
        bad["extents_mm"] = [summary["extents_mm"][0] + 5.0,
                             summary["extents_mm"][1],
                             summary["extents_mm"][2]]
        r = verification.build_report(manifest, bad, geom_pass, 0.3, 0.1)
        assert r["verdict"] == "fail", r["summary"]
        assert r["summary"]["worst_dimension"] == "Overall size X"
        # AI source: the honest wording must be in the report.
        manifest["source"]["source_type"] = "ai-generated"
        r = verification.build_report(manifest, summary, geom_pass, 0.3, 0.1)
        assert "matches the AI mesh" in r["markdown"]
    finally:
        vmod.load_measurements = orig
    print("  app verification: incomplete/pass/fail + AI wording ok")


def test_framework_export_plan():
    from meshtocad import exporting
    from meshtocad.framework.exporting import plan_exports, sanitize_stem

    objects = [{"name": "Body", "kind": "solid"},
               {"name": "Scan", "kind": "mesh"},
               {"name": "Notes", "kind": "other"}]
    plan = plan_exports(exporting.SPEC.formats, objects,
                        ["step", "stl", "fcstd", "drawing-pdf"], "proj")
    kinds = {(j["format"], j["object"]) for j in plan["jobs"]}
    assert ("step", "Body") in kinds
    assert ("stl", "Body") in kinds and ("stl", "Scan") in kinds
    assert ("fcstd", "Body") in kinds  # per_object=False -> one job
    assert ("drawing-pdf", "Body") in kinds
    assert plan["skipped"] == [], plan["skipped"]
    # No solid -> STEP and drawing skip WITH reasons; STL still plans.
    plan2 = plan_exports(exporting.SPEC.formats, objects[1:],
                         ["step", "stl", "drawing-pdf"], "proj")
    skipped = {s["format"] for s in plan2["skipped"]}
    assert skipped == {"step", "drawing-pdf"}, plan2
    assert all(s["reason"] for s in plan2["skipped"])
    assert sanitize_stem("my part!.stl") == "my_part_.stl"
    print("  export planning + skips ok")


TESTS = [
    test_units_bracket,
    test_quality_gate_bracket,
    test_analyze_bracket_is_prismatic,
    test_analyze_blob_is_organic,
    test_deviation_module_loads,
    test_framework_guidance_rows,
    test_app_guidance_sections,
    test_framework_verification_verdicts,
    test_app_verification_end_to_end_pure,
    test_framework_export_plan,
]


def main() -> int:
    failures = 0
    for t in TESTS:
        try:
            print(f"{t.__name__} ...")
            t()
            print("  PASS")
        except Exception as e:
            failures += 1
            print(f"  FAIL: {e}")
    print(f"\n{len(TESTS) - failures}/{len(TESTS)} passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
