# -*- coding: utf-8 -*-
"""MeshToCAD workbench — console-mode entry point.

Runs at FreeCAD startup even in console (freecadcmd) mode. MVP registers no
console-mode importers; this file exists so the Addon Manager and FreeCAD's
module loader recognize the workbench in every mode.

All paths are resolved from this file's location — nothing is hardcoded.
"""

import os

# Workbench root: the directory containing this file. Everything else hangs
# off it. This is the one path rule for the whole project: derive, don't
# assume. (Dennis installs to D: — hardcoded C: paths are a bug.)
WORKBENCH_ROOT = os.path.dirname(os.path.abspath(__file__))
