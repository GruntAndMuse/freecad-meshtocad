# -*- coding: utf-8 -*-
"""Export — the mesh-to-cad app layer over framework.exporting.

Stage 5: "Export project". Produces the project's deliverables into
output/:

  - STEP (.step)      — the parametric-exchange file, per solid.
  - STL (.stl)        — tessellated, per solid or mesh (0.1 mm deflection,
                        the same tessellation the deviation stage checks).
  - FCStd (.fcstd)    — a copy of the whole FreeCAD document.
  - Drawing PDF (.pdf)— TechDraw page (Front/Top/Right/Isometric) built
                        from the first solid, exported via the GUI layer.

Format declarations live here; planning lives in framework/exporting.py;
writing lives in framework/freecad_io.py (the host adapter).
"""

from .framework.exporting import ExportFormat, ExportSpec

FORMATS = [
    ExportFormat("step", "STEP — CAD exchange (.step)", "step",
                 kinds=("solid",)),
    ExportFormat("stl", "STL — mesh (.stl)", "stl",
                 kinds=("solid", "mesh")),
    ExportFormat("fcstd", "FreeCAD document copy (.fcstd)", "fcstd",
                 kinds=("solid", "mesh", "other"), per_object=False),
    ExportFormat("drawing-pdf", "TechDraw drawing (.pdf)", "pdf",
                 kinds=("solid",), per_object=False, needs_gui=True),
]

SPEC = ExportSpec(formats=list(FORMATS),
                  default_keys=("step", "stl", "fcstd", "drawing-pdf"))


def output_stem(manifest: dict) -> str:
    return manifest["project"]
