# -*- coding: utf-8 -*-
"""MeshToCAD workbench — GUI entry point.

Loaded by FreeCAD only in GUI mode. Registers the workbench class; the class
itself lives in meshtocad/workbench.py so it stays importable and testable
without dragging FreeCADGui into every module.
"""

import os
import sys

import FreeCAD
import FreeCADGui

WORKBENCH_ROOT = os.path.dirname(os.path.abspath(__file__))

# Make the meshtocad package importable. Derived from this file's location —
# works wherever the user installed the workbench (Mod dir, D: drive, anywhere).
if WORKBENCH_ROOT not in sys.path:
    sys.path.insert(0, WORKBENCH_ROOT)

try:
    from meshtocad.workbench import MeshToCADWorkbench

    # Pass the CLASS — FreeCAD instantiates it internally. (FreeCAD's own
    # workbenches, e.g. Draft, do exactly this; passing an instance breaks
    # the C++ wrapping with "'...' object has no attribute '__Workbench__'".)
    FreeCADGui.addWorkbench(MeshToCADWorkbench)
except Exception as e:
    # A workbench that kills FreeCAD startup is worse than a workbench that
    # doesn't load. Say what happened, keep going.
    FreeCAD.Console.PrintWarning(
        f"[MeshToCAD] workbench failed to load: {e}\n"
    )
