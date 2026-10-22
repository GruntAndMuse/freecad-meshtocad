# -*- coding: utf-8 -*-
"""Rebuild guidance — the mesh-to-cad app layer over framework.guidance.

Stage 3A (prismatic) / 3B (organic) rebuild is MANUAL in this pipeline —
the workbench does not reimplement anyone's fitter, and there is no magic
rebuild button. What it can do is put the measurements beside the modeler:
every number the rebuild will be verified against, what each number means
for the modeling, and a checklist in build order. The directions ARE the
automation until automation exists.

This module holds the mesh-to-cad specifics (which analyze.py measurements
matter, the track-dependent advice, the wording). The rendering/plumbing
lives in framework/guidance.py and stays pipeline-agnostic.
"""

import json
from pathlib import Path

from .framework.guidance import GuidanceField, GuidanceSpec

FIELDS = [
    GuidanceField("bounding_box_mm.extents[0]", "Overall width (X)", "mm",
                  hint="Set the base sketch to this width in the aligned "
                       "frame (longest axis on X)."),
    GuidanceField("bounding_box_mm.extents[1]", "Overall depth (Y)", "mm",
                  hint="Second axis on Y."),
    GuidanceField("bounding_box_mm.extents[2]", "Overall height (Z)", "mm",
                  hint="Shortest axis on Z — most parts model bottom-up "
                       "from the XY plane."),
    GuidanceField("volume_mm3", "Volume", "mm³", decimals=2,
                  hint="Sanity target for the finished solid (watertight "
                       "meshes only). A big miss means a feature is "
                       "missing or doubled."),
    GuidanceField("faces", "Mesh faces", kind="text",
                  hint="Source mesh density — context, not a target."),
    GuidanceField("is_watertight", "Mesh watertight", kind="bool",
                  hint="If no, expect gaps the mesh hides; measure twice "
                       "before trusting a surface."),
    GuidanceField("planar_fraction", "Planar fraction", kind="percent",
                  hint="Share of faces on dominant planes. High = model "
                       "with sketches and pads."),
    GuidanceField("effective_prismatic_fraction", "Prismatic fraction",
                  kind="percent",
                  hint="Planar + cylindrical-wall faces. This is the "
                       "number the track decision used."),
    GuidanceField("cylindrical_fraction", "Cylindrical fraction",
                  kind="percent",
                  hint="Bores and turned walls — model these as holes / "
                       "revolves, not as organic detail."),
    GuidanceField("track_decision", "Track", kind="text",
                  hint="The recorded track decision (override shown in "
                       "the manifest if you changed it)."),
    GuidanceField("track_confidence", "Track confidence", kind="text",
                  hint="Medium confidence is the case for a second look "
                       "before you commit to a modeling strategy."),
]

CHECKLIST_PRISMATIC = [
    "Open the aligned mesh (shown after Analyze) beside PartDesign — "
    "model in the aligned frame: longest axis on X, shortest on Z.",
    "Build the base solid from the overall extents above.",
    "Add the dominant planes' features as sketches/pads — largest faces "
    "first.",
    "Cut bores and cylindrical walls as holes/revolves (see the "
    "cylindrical fraction).",
    "Compare the solid's volume against the target volume above.",
    "Run Deviation check, then Verify build.",
]

CHECKLIST_ORGANIC = [
    "Open the aligned mesh beside your surface tools — model in the "
    "aligned frame: longest axis on X, shortest on Z.",
    "Section the mesh at the symmetry planes and sketch the profiles.",
    "Loft/sweep the main body to the overall extents above.",
    "Check the solid's volume against the target volume above.",
    "Run Deviation check early and often — organic fitting is a loop, "
    "not a single pass.",
    "Run Verify build when the deviation is inside tolerance.",
]

CHECKLIST_MIXED = [
    "Rebuild the prismatic base first (overall extents, dominant planes, "
    "bores) — organic details last.",
    "Model in the aligned frame: longest axis on X, shortest on Z.",
    "Add the organic details on top of the finished base.",
    "Compare the solid's volume against the target volume above.",
    "Run Deviation check, then Verify build.",
]

_CHECKLISTS = {
    "prismatic": CHECKLIST_PRISMATIC,
    "organic": CHECKLIST_ORGANIC,
    "mixed": CHECKLIST_MIXED,
}


def spec_for_track(track: str) -> GuidanceSpec:
    return GuidanceSpec(fields=list(FIELDS),
                        checklist=list(_CHECKLISTS.get(
                            track, CHECKLIST_PRISMATIC)))


def measurements_path(manifest: dict) -> Path:
    """Where Analyze wrote this project's measurements JSON."""
    stem = Path(manifest["source"]["original_file"]).stem
    return Path(manifest["project_dir"]) / "analysis" / f"{stem}_measurements.json"


def load_measurements(manifest: dict) -> dict | None:
    """The measurements dict, or None if Analyze hasn't written it."""
    p = measurements_path(manifest)
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def planes_section(measurements: dict) -> tuple:
    """(heading, lines) for the dominant-planes block of the reference."""
    planes = measurements.get("dominant_planes") or []
    lines = []
    for i, p in enumerate(planes[:6], 1):
        n = p.get("normal", ["?", "?", "?"])
        lines.append(
            f"- Plane {i}: normal ({n[0]}, {n[1]}, {n[2]}) — "
            f"{p.get('face_fraction', '?')} of faces "
            f"({p.get('face_count', '?')} faces). Sketch on this plane "
            "early; it carries the part's main faces.")
    if not lines:
        lines.append("- No dominant planes recorded — this mesh has no "
                     "strong flat faces (organic territory).")
    return ("Dominant planes", lines)


def symmetry_lines(measurements: dict) -> list:
    sym = measurements.get("symmetry") or {}
    lines = []
    for name in ("xy", "xz", "yz"):
        entry = sym.get(name)
        if isinstance(entry, dict) and "symmetric" in entry:
            state = "symmetric" if entry["symmetric"] else "not symmetric"
            lines.append(f"- {name.upper()} plane: {state} "
                         f"(mean deviation {entry.get('mean_dev_mm', '?')} mm)"
                         + (" — model half and mirror."
                            if entry["symmetric"] else ""))
    return lines


def intro_lines(manifest: dict, measurements: dict) -> list:
    ai = manifest["source"].get("source_type") == "ai-generated"
    track = manifest.get("track") or measurements.get("track_decision", "?")
    lines = [
        f"Project: {manifest['project']}  ",
        f"Track: {track} — rebuild by measuring and remodeling. There is "
        "no automatic rebuild; this reference is the guide.",
        "Model in the aligned frame (the aligned mesh Analyze showed): "
        "longest axis on X, second on Y, shortest on Z. Verification "
        "compares against these same numbers, in this frame.",
    ]
    if ai:
        lines.append(
            "**AI-generated mesh:** it carries no real dimensions. These "
            "numbers describe the AI mesh, not reality — set the part's "
            "dimensions to spec yourself as you model.")
    return lines


def reference_filename(manifest: dict) -> str:
    stem = Path(manifest["source"]["original_file"]).stem
    return f"{stem}_reference.md"


def cad_dir_listing(manifest: dict) -> list:
    """Files already in cad/ — what's been built so far."""
    cad = Path(manifest["project_dir"]) / "cad"
    if not cad.is_dir():
        return []
    return sorted(p.name for p in cad.iterdir() if p.is_file())


def build_reference(project_dir: str) -> dict:
    """Build the rebuild reference for a project. PURE — worker-safe.

    Loads the manifest + measurements from disk, renders the reference,
    writes analysis/<name>_reference.md. Returns {"error", "rows",
    "reference_path", "track", "cad_files"}.
    """
    from . import project as _project
    from .framework.guidance import build_reference_rows, render_reference_markdown

    manifest = _project.load_manifest(project_dir)
    if manifest is None:
        return {"error": "project manifest missing — re-run Import."}
    measurements = load_measurements(manifest)
    if measurements is None:
        return {"error": "no measurements found — run Analyze first; "
                         "guidance is built from its measurements JSON."}
    track = manifest.get("track") or measurements.get("track_decision",
                                                      "prismatic")
    spec = spec_for_track(track)
    rows = build_reference_rows(measurements, spec.fields)
    extra = [planes_section(measurements)]
    sym = symmetry_lines(measurements)
    if sym:
        extra.append(("Symmetry", sym))
    markdown = render_reference_markdown(
        f"Rebuild reference — {manifest['project']}",
        intro_lines(manifest, measurements),
        rows, spec.checklist, extra)
    out = Path(project_dir) / "analysis" / reference_filename(manifest)
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(markdown, encoding="utf-8")
    except OSError as e:
        return {"error": f"couldn't write the reference file: {e}"}
    return {"error": None, "rows": rows, "track": track,
            "reference_path": str(out),
            "cad_files": cad_dir_listing(manifest)}
