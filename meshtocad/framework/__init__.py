# -*- coding: utf-8 -*-
"""Host-integration framework — the reusable template layer.

Everything in this package is GENERIC: it knows about stages, manifests,
worker threads, reference panels, verification reports, and export jobs,
but nothing about meshes, tracks, or tolerances. A future host integration
(Blender, another FOSS tool, another pipeline entirely) reuses this layer
unchanged and writes only:

  1. an app layer (specs, wording, stage definitions — e.g. the top-level
     ``meshtocad`` modules outside this package), and
  2. a host adapter (the equivalent of ``freecad_io`` for that host's
     document/geometry APIs).

Layer rules:
  - ``guidance``, ``verification``, ``exporting``: pure Python, plain data
    in/out, no host imports — headless-testable anywhere.
  - ``freecad_io``: the ONLY framework module that imports the host
    (FreeCAD). It exposes plain-data summaries and file writers so the
    pure layers never see a host object.
"""
