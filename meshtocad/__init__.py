# -*- coding: utf-8 -*-
"""MeshToCAD — mesh-to-cad pipeline inside FreeCAD.

MVP: intake (units check) + quality gate + analysis + deviation check.
No third-party workbench dependencies. MIT.

This package must import cleanly WITHOUT FreeCADGui (console mode,
headless tests). GUI-only imports live in commands/ and ui/, loaded lazily.
"""

__version__ = "0.1.0"
