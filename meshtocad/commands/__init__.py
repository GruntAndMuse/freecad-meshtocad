# -*- coding: utf-8 -*-
"""Command registration.

Pipeline order: Import -> Quality -> Analyze -> Rebuild -> Deviation ->
Verify -> Export. Each command is a FreeCAD command class
(GetResources/Activated/IsActive). IsActive() enforces pipeline order
from the manifest: you can't Analyze before Import, can't Export before
Verify. Same "one command can't be misordered" idea as the CLI,
expressed as button states.
"""

COMMANDS = []


def _register(cmd_cls):
    import FreeCADGui

    cmd = cmd_cls()
    FreeCADGui.addCommand(cmd.NAME, cmd)
    COMMANDS.append(cmd.NAME)


def register_all():
    from . import (cmd_analyze, cmd_deviation, cmd_export, cmd_import,
                   cmd_quality, cmd_rebuild, cmd_verify)

    for mod in (cmd_import, cmd_quality, cmd_analyze, cmd_rebuild,
                cmd_deviation, cmd_verify, cmd_export):
        _register(mod.Command)


def toolbar_commands():
    return [
        "MTC_Import",
        "MTC_Quality",
        "MTC_Analyze",
        "MTC_Rebuild",
        "MTC_Deviation",
        "MTC_Verify",
        "MTC_Export",
    ]
