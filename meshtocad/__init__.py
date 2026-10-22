# -*- coding: utf-8 -*-
"""MeshToCAD — mesh-to-cad pipeline inside FreeCAD.

Pipeline: intake (units check) + quality gate + analysis + rebuild
guidance + deviation check + verification report + export.
No third-party workbench dependencies. MIT.

Structure: meshtocad/framework/ is the generic host-integration layer
(reusable by future host integrations); the top-level modules and
commands/ are the mesh-to-cad app layer on top of it.

This package must import cleanly WITHOUT FreeCADGui (console mode,
headless tests). GUI-only imports live in commands/ and ui/, loaded lazily.
"""

__version__ = "0.2.0"
