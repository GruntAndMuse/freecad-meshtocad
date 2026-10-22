# -*- coding: utf-8 -*-
"""Stage 3 — Rebuild guidance (measure-and-remodel reference panel).

The rebuild itself is manual: the workbench does not reimplement a
fitter, and there is no magic rebuild button. This panel is the
measure-and-remodel mode from the plan — it docks every measurement the
rebuild will be verified against, what each number means while modeling,
and a checklist in build order, and writes the same reference to
analysis/<name>_reference.md so it survives outside FreeCAD.

Track-specific checklists (prismatic / organic / mixed) come from the
app layer (meshtocad/guidance.py); rendering is framework/guidance.py.
"""

from pathlib import Path

from PySide6.QtWidgets import QLabel

from .. import guidance, project
from ..ui.panels import StagePanel
from ._common import active_manifest, icon, require_project

# The worker function lives in the app layer (meshtocad/guidance.py) so it
# stays headless-testable without Qt. It is pure: plain data in/out.
_guidance_worker = guidance.build_reference


class RebuildPanel(StagePanel):
    title = "Rebuild guidance"
    one_liner = ("The rebuild is manual — this panel puts every measured "
                 "number beside you while you model, in build order.")
    next_label = "Continue \u2192 Deviation check"
    next_command = "MTC_Deviation"

    def build_inputs(self):
        self.info = QLabel("")
        self.info.setWordWrap(True)
        self.inputs_layout.addWidget(self.info)
        manifest = active_manifest()
        if manifest:
            track = manifest.get("track", "?")
            self.info.setText(
                f"Project: {manifest['project']}\n"
                f"Track: {track} — model in PartDesign (prismatic) or "
                "with surface tools (organic), in the aligned frame "
                "Analyze showed. Save your document into the project's "
                "cad/ folder so the project stays self-contained."
            )

    def run_work(self):
        manifest = require_project(self.set_results)
        if manifest is None:
            return None
        self._manifest = manifest
        self.set_results(["Building the reference\u2026"])
        return (_guidance_worker, (manifest["project_dir"],), {})

    def on_result(self, result):
        # MAIN THREAD — FreeCAD calls are safe here.
        if result["error"]:
            self.set_results([result["error"]])
            return
        manifest = self._manifest
        project.mark_stage(manifest, "rebuild", True)
        manifest["rebuild_reference"] = Path(
            result["reference_path"]).name
        project.save_manifest(manifest["project_dir"], manifest)

        lines = [f"Track: {result['track']}", ""]
        for r in result["rows"]:
            value = r["value_text"] + (f" {r['unit']}" if r["unit"] else "")
            lines.append(f"{r['label']}: {value}")
        lines += ["",
                  f"Full reference (with the build checklist): "
                  f"analysis/{Path(result['reference_path']).name}"]
        if result["cad_files"]:
            lines.append("Already in cad/: " + ", ".join(result["cad_files"]))
        else:
            lines.append("cad/ is empty — nothing built yet. The "
                         "checklist in the reference is the order to "
                         "build in.")
        self.set_results(lines)
        self.enable_next()


class Command:
    NAME = "MTC_Rebuild"

    def GetResources(self):
        return {
            "MenuText": "Rebuild guidance",
            "ToolTip": "Measurements + checklist for the manual rebuild (Stage 3)",
            "Pixmap": icon("rebuild"),
        }

    def Activated(self):
        import FreeCADGui

        FreeCADGui.Control.showDialog(RebuildPanel())

    def IsActive(self):
        manifest = active_manifest()
        return bool(manifest) and project.stage_done(manifest, "analyze")
