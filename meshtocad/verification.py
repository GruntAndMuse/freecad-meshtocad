# -*- coding: utf-8 -*-
"""Verification — the mesh-to-cad app layer over framework.verification.

Stage 4: "Verify build". Three check groups, judged against the ORIGINAL
input mesh's measurements (never a cleaned copy — the pipeline's rule):

  1. Dimension re-check — the CAD shape's bounding box / volume vs the
     measurements JSON from Analyze, each dimension against the project
     tolerance. Assumes the model was built in the aligned frame (the
     guidance panel says to build there); the report states this.
  2. Geometry check — the FreeCAD kernel's verdict on the built shape
     (valid, closed), gathered by the caller via framework.freecad_io.
  3. Deviation — the CloudCompare result the Deviation stage recorded in
     the manifest. Not re-run here; if it never ran (or CloudCompare was
     missing), the check reads NOT RUN and the verdict is INCOMPLETE —
     an unverified build is never dressed up as a pass.

For AI-generated meshes the report says plainly what verification means
there: "your CAD matches the AI mesh," not "matches reality."

Assembly here is pure given (manifest, measurements, shape summary,
geometry result) — the panel gathers the FreeCAD-side facts on the main
thread, this module does the judging and writing in the worker.
"""

from pathlib import Path

from .framework import verification as fw
from .guidance import load_measurements

_AXES = ("X", "Y", "Z")


def report_filename(manifest: dict) -> str:
    stem = Path(manifest["source"]["original_file"]).stem
    return f"{stem}_report.md"


def dimension_pairs(measurements: dict, shape_summary: dict | None,
                    tolerance: float, mating_tolerance: float) -> list:
    """Expected (mesh) vs actual (CAD) pairs, toleranced per dimension.

    Overall extents use the general tolerance; volume uses a relative
    band expressed through the same pair machinery via an absolute
    tolerance of 5% of expected volume (labeled in the name).
    """
    pairs = []
    extents = (measurements.get("bounding_box_mm") or {}).get("extents") or []
    actual_ext = (shape_summary or {}).get("extents_mm") or []
    for i, axis in enumerate(_AXES):
        pairs.append({
            "name": f"Overall size {axis}",
            "expected": extents[i] if i < len(extents) else None,
            "actual": actual_ext[i] if i < len(actual_ext) else None,
            "tolerance": tolerance,
        })
    expected_vol = measurements.get("volume_mm3")
    pairs.append({
        "name": "Volume (5% band)",
        "expected": expected_vol,
        "actual": (shape_summary or {}).get("volume_mm3"),
        "tolerance": (0.05 * expected_vol) if expected_vol else None,
    })
    return pairs


def geometry_section(geometry: dict | None) -> dict:
    """framework section for the kernel geometry check."""
    if not geometry or not geometry.get("ran"):
        return {"heading": "Geometry check", "status": "not-run",
                "lines": ["The geometry check did not run — no shape was "
                          "available to check. Build (or select) the model "
                          "first."]}
    lines = [
        f"- Kernel validity (isValid): {'yes' if geometry['valid'] else 'NO'}",
        f"- Closed shell (isClosed): {'yes' if geometry['closed'] else 'no'}",
    ]
    for p in geometry.get("problems", []):
        lines.append(f"- Problem: {p}")
    ok = geometry["valid"] and not geometry.get("problems")
    return {"heading": "Geometry check",
            "status": "pass" if ok else "fail",
            "lines": lines}


def deviation_section(manifest: dict) -> dict:
    """framework section for the recorded deviation result."""
    dev = manifest.get("deviation")
    if not dev:
        return {"heading": "Deviation vs input mesh", "status": "not-run",
                "lines": ["No deviation result recorded — run Deviation "
                          "check first. Without it, this report cannot "
                          "say how close the model sits to the input mesh."]}
    lines = [
        f"- Max deviation: {dev.get('max_mm', '?')} mm",
        f"- Mean deviation: {dev.get('mean_mm', '?')} mm",
        f"- P95 deviation: {dev.get('p95_mm', '?')} mm",
        f"- Tolerance used: {dev.get('tolerance_mm', '?')} mm",
        "- Compared against the project's input mesh (the original — "
        "never a cleaned copy).",
    ]
    return {"heading": "Deviation vs input mesh",
            "status": "pass" if dev.get("passed") else "fail",
            "lines": lines}


def build_report(manifest: dict, shape_summary: dict | None,
                 geometry: dict | None, tolerance: float,
                 mating_tolerance: float) -> dict:
    """Assemble the full verification. Pure — returns the report dict.

    {"verdict", "markdown", "dimension_rows", "summary"} where summary is
    the compact record the manifest keeps.
    """
    ai = manifest["source"].get("source_type") == "ai-generated"
    measurements = load_measurements(manifest)
    sections = [geometry_section(geometry), deviation_section(manifest)]

    if measurements is None:
        dim_rows = [{"name": "Dimension re-check", "expected": None,
                     "actual": None, "tolerance": None, "delta": None,
                     "status": "not-run",
                     "detail": "measurements JSON missing — re-run Analyze"}]
    else:
        dim_rows = fw.compare_dimensions(
            dimension_pairs(measurements, shape_summary, tolerance,
                            mating_tolerance))

    verdict = fw.overall_verdict(
        [dim_rows] + [[{"status": s["status"]}] for s in sections])

    meta = [
        f"Project: {manifest['project']}  ",
        f"Source mesh: {Path(manifest['source']['original_file']).name}  ",
        f"Model checked: {(shape_summary or {}).get('label', '—')}  ",
        f"Tolerance: {tolerance} mm (mating {mating_tolerance} mm)  ",
        "Dimensions are compared in the aligned frame from Analyze — "
        "the frame the rebuild guidance says to model in.",
    ]
    if ai:
        meta.append(
            "**AI-generated source:** this verifies your CAD against the "
            "AI mesh — \"matches the AI mesh,\" not \"matches reality.\" "
            "The mesh carries no real dimensions.")

    markdown = fw.render_report_markdown(
        f"Verification report — {manifest['project']}",
        verdict, meta, dim_rows, sections)

    summary = {
        "verdict": verdict,
        "report": report_filename(manifest),
        "model": (shape_summary or {}).get("label"),
        "dimensions_passed": sum(1 for r in dim_rows if r["status"] == "pass"),
        "dimensions_failed": sum(1 for r in dim_rows if r["status"] == "fail"),
        "dimensions_not_run": sum(1 for r in dim_rows
                                  if r["status"] == "not-run"),
    }
    worst = fw.worst_instance(dim_rows)
    if worst is not None:
        summary["worst_dimension"] = worst["name"]
        summary["worst_delta_mm"] = worst["delta"]
    return {"verdict": verdict, "markdown": markdown,
            "dimension_rows": dim_rows, "summary": summary}


def write_report(manifest: dict, report: dict) -> Path:
    """Write the report into verification/. Returns the path."""
    out = Path(manifest["project_dir"]) / "verification" / report_filename(manifest)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(report["markdown"], encoding="utf-8")
    return out


def run_verification(manifest: dict, shape_summary: dict | None,
                     geometry: dict | None, tolerance: float,
                     mating: float) -> dict:
    """Judge + write the report. PURE — worker-safe. No FreeCAD.

    The caller gathers shape_summary/geometry on the main thread (via
    framework.freecad_io) and passes plain data in.
    Returns {"error", "report", "path"}.
    """
    try:
        report = build_report(manifest, shape_summary, geometry,
                              tolerance, mating)
        path = write_report(manifest, report)
        return {"error": None, "report": report, "path": str(path)}
    except Exception as e:
        return {"error": f"couldn't build the verification report: {e}"}
