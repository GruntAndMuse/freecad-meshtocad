# -*- coding: utf-8 -*-
"""Command registration. MVP: Import -> Quality -> Analyze -> Deviation.

Each command is a FreeCAD command class (GetResources/Activated/IsActive).
IsActive() enforces pipeline order from the manifest: you can't Analyze
before Import, can't run Deviation before Analyze. Same "one command can't
be misordered" idea as the CLI, expressed as button states.
"""

COMMANDS = []


def _register(cmd_cls):
    import FreeCADGui

    cmd = cmd_cls()
    FreeCADGui.addCommand(cmd.NAME, cmd)
    COMMANDS.append(cmd.NAME)


def register_all():
    from . import cmd_analyze, cmd_deviation, cmd_import, cmd_quality

    for mod in (cmd_import, cmd_quality, cmd_analyze, cmd_deviation):
        _register(mod.Command)


def toolbar_commands():
    return [
        "MTC_Import",
        "MTC_Quality",
        "MTC_Analyze",
        "MTC_Deviation",
    ]
