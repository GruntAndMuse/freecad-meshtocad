# -*- coding: utf-8 -*-
"""FreeCAD host adapter — document/geometry I/O for the framework.

This is the one framework module that imports FreeCAD. A different host
(Blender, ...) replaces this file with its own adapter exposing the same
plain-data surface; the pure framework layers never see host objects.

MAIN-THREAD RULE (see meshtocad/threads.py): everything here touches the
document or geometry, so call it from panel code / command code on the
main GUI thread — never from a worker function.

Surfaces:
  - object_descriptors(doc): [{"name", "label", "kind"}] for export planning
    (kind in "solid" | "mesh" | "other").
  - shape_summary(obj): plain-data measurements of one shape, for the
    verification dimension re-check.
  - geometry_check(shape): validity/closedness verdict, plain data.
  - export_job(doc, job, out_dir): write one planned export file.
  - build_drawing_page / export_page_pdf: TechDraw drawing + PDF.
"""

from pathlib import Path


def _shape_of(obj):
    shape = getattr(obj, "Shape", None)
    if shape is None or shape.isNull():
        return None
    return shape


def object_kind(obj) -> str:
    """Classify a document object for export planning."""
    if obj is None:
        return "other"
    type_id = getattr(obj, "TypeId", "")
    if type_id.startswith("Mesh::"):
        return "mesh"
    shape = _shape_of(obj)
    if shape is not None:
        try:
            if shape.Solids:
                return "solid"
        except Exception:
            pass
        return "other"
    return "other"


def object_descriptors(doc) -> list:
    """Plain-data view of a document's objects, for framework planning."""
    if doc is None:
        return []
    return [{"name": obj.Name, "label": obj.Label, "kind": object_kind(obj)}
            for obj in doc.Objects]


def shape_summary(obj) -> dict | None:
    """Measurements of one object's shape. None when it has no shape."""
    shape = _shape_of(obj)
    if shape is None:
        return None
    bb = shape.BoundBox
    summary = {
        "object": obj.Name,
        "label": obj.Label,
        "extents_mm": [round(bb.XLength, 4), round(bb.YLength, 4),
                       round(bb.ZLength, 4)],
        "bbox_min": [round(bb.XMin, 4), round(bb.YMin, 4), round(bb.ZMin, 4)],
        "bbox_max": [round(bb.XMax, 4), round(bb.YMax, 4), round(bb.ZMax, 4)],
        "solids": len(shape.Solids),
        "faces": len(shape.Faces),
        "is_valid": bool(shape.isValid()),
        "is_closed": bool(shape.isClosed()),
    }
    try:
        summary["volume_mm3"] = round(float(shape.Volume), 4)
    except Exception:
        summary["volume_mm3"] = None
    try:
        summary["area_mm2"] = round(float(shape.Area), 4)
    except Exception:
        summary["area_mm2"] = None
    return summary


def geometry_check(shape) -> dict:
    """Run the kernel geometry check. Plain-data verdict.

    Uses Shape.check(True) (BRepCheck with BOP arguments check): valid
    shapes return quietly; invalid ones raise with the kernel's findings,
    which we keep as the problem list. isValid()/isClosed() are reported
    separately — a shape can be closed yet invalid, and the report should
    say which.
    """
    result = {
        "ran": False,
        "valid": bool(shape.isValid()),
        "closed": bool(shape.isClosed()),
        "problems": [],
    }
    try:
        shape.check(True)
        result["ran"] = True
    except Exception as e:
        result["ran"] = True
        result["problems"] = [str(e)]
    if not result["valid"] and not result["problems"]:
        result["problems"] = ["kernel reports the shape is not valid "
                               "(isValid() is False)"]
    return result


# ---------------------------------------------------------------------------
# Export writers. One function per format key the app layer declares; each
# returns the written path. All raise on failure — the caller records the
# failure per job instead of aborting the whole export.
# ---------------------------------------------------------------------------

def _write_step(doc, obj, path: Path) -> Path:
    import Part

    Part.export([obj], str(path))
    return path


def _write_stl(doc, obj, path: Path) -> Path:
    import Mesh

    if object_kind(obj) == "mesh":
        Mesh.export([obj], str(path))
        return path
    # Solid -> tessellate. 0.1 mm deflection matches the deviation stage's
    # tessellation, so the exported STL and the checked STL agree.
    shape = _shape_of(obj)
    mesh = Mesh.Mesh(shape.tessellate(0.1))
    mesh.write(str(path))
    return path


def _write_fcstd(doc, obj, path: Path) -> Path:
    # saveCopy writes the whole document without retitling the live one.
    doc.saveCopy(str(path))
    return path


# TechDraw view directions: (label, direction, x-direction or None).
# XDirection must be perpendicular to Direction or TechDraw cannot build
# the projection coordinate system — the Right view fails exactly that
# way ("failed to create projection CS", seen on 1.1.4) when it is left
# to the default. (0,1,0) keeps world +Z as drawing-up for the Right view.
_DRAWING_VIEWS = (
    ("Front", (0, 0, 1), None),
    ("Top", (0, 1, 0), None),
    ("Right", (1, 0, 0), (0, 1, 0)),
    ("Isometric", (1, 1, 1), (0, 1, 0)),
)


def default_template_path():
    """The stock A4 landscape TechDraw template, resolved via FreeCAD's
    resource dir — never a hardcoded install path. None if absent."""
    import FreeCAD

    templates = (Path(FreeCAD.getResourceDir()) / "Mod" / "TechDraw"
                 / "Templates")
    preferred = templates / "Default_Template_A4_Landscape.svg"
    if preferred.is_file():
        return preferred
    if templates.is_dir():
        svgs = sorted(templates.glob("*.svg"))
        if svgs:
            return svgs[0]
    return None


def build_drawing_page(doc, source_obj, page_name: str = "Drawing"):
    """Create (or reuse) a TechDraw page with Front/Top/Right/Iso views.

    Returns the page object. Raises RuntimeError with a plain-language
    reason when TechDraw or a template is unavailable — loud, not silent.
    """
    import FreeCAD  # noqa: F401  (host adapter: FreeCAD is the point)

    page = None
    for obj in doc.Objects:
        if obj.TypeId == "TechDraw::DrawPage" and obj.Name == page_name:
            page = obj
            break
    if page is None:
        page = doc.addObject("TechDraw::DrawPage", page_name)
        template_path = default_template_path()
        if template_path is None:
            raise RuntimeError(
                "no TechDraw template found in FreeCAD's resources — "
                "the drawing page can't be built. STEP/STL export still "
                "works; install FreeCAD's TechDraw resources for drawings."
            )
        tmpl = doc.addObject("TechDraw::DrawSVGTemplate", "Template")
        tmpl.Template = str(template_path)
        page.Template = tmpl
    # Page membership is the Views property (there is no Group on a
    # DrawPage in FreeCAD 1.1 — verified against 1.1.4).
    existing = {v.Label for v in (getattr(page, "Views", None) or [])}
    for label, direction, xdir in _DRAWING_VIEWS:
        if label in existing:
            continue
        view = doc.addObject("TechDraw::DrawViewPart", f"View{label}")
        view.Source = [source_obj]
        view.Direction = direction
        if xdir is not None:
            try:
                view.XDirection = xdir
            except Exception:
                pass
        page.addView(view)
    doc.recompute()
    return page


def export_page_pdf(page, path: Path) -> Path:
    """Write a TechDraw page as PDF. Needs the GUI layer (TechDrawGui) —
    raises RuntimeError saying so when run headless."""
    try:
        import TechDrawGui
    except Exception:
        raise RuntimeError(
            "drawing PDF export needs FreeCAD's GUI (TechDrawGui is not "
            "loaded in console mode). The drawing page was still created "
            "in the document — open it in FreeCAD and export the PDF, or "
            "re-run Export from the GUI."
        )
    TechDrawGui.exportPageAsPdf(page, str(path))
    return path


def _write_drawing_pdf(doc, obj, path: Path) -> Path:
    page = build_drawing_page(doc, obj)
    return export_page_pdf(page, path)


_WRITERS = {
    "step": _write_step,
    "stl": _write_stl,
    "fcstd": _write_fcstd,
    "drawing-pdf": _write_drawing_pdf,
}


def export_job(doc, job: dict, out_dir) -> Path:
    """Execute one planned export job. Returns the written path.

    MAIN THREAD ONLY (document access). Raises on failure with the reason.
    """
    writer = _WRITERS.get(job["format"])
    if writer is None:
        raise RuntimeError(f"no FreeCAD writer for format {job['format']!r}")
    obj = doc.getObject(job["object"]) if job.get("object") else None
    if job["format"] != "fcstd" and obj is None:
        raise RuntimeError(f"object {job.get('object')!r} not in document")
    out = Path(out_dir) / job["filename"]
    out.parent.mkdir(parents=True, exist_ok=True)
    written = writer(doc, obj, out)
    if not Path(written).is_file() or Path(written).stat().st_size == 0:
        raise RuntimeError(f"writer produced no file at {written}")
    return Path(written)
