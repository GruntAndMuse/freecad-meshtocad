# -*- coding: utf-8 -*-
"""Stage 1 — Quality gate.

Runs the four metrics, shows the verdict. needs-rescan is an honest stop,
not a failure — the panel says so, in plain words. For AI meshes the stop
copy reads "regenerate or clean up" (you can't rescan what was never scanned).
"""

from pathlib import Path

from PySide6.QtWidgets import QLabel

from .. import project
from ..engine import quality_gate
from ..ui.panels import StagePanel, quality_lines
from ._common import active_manifest, icon, require_project


def _gate_worker(input_copy: str) -> dict:
    """Pure worker: quality gate on the input copy. No FreeCAD."""
    try:
        return {"error": None,
                "gate": quality_gate().quality_gate(Path(input_copy))}
    except Exception as e:
        return {"error": f"couldn't run the quality gate: {e}", "gate": None}


class QualityPanel(StagePanel):
    title = "Quality gate"
    one_liner = ("Check the mesh is worth rebuilding from. A bad scan here "
                 "means stop — no pipeline fixes missing data.")
    next_label = "Continue \u2192 Analyze"
    next_command = "MTC_Analyze"

    def build_inputs(self):
        self.info = QLabel("")
        self.info.setWordWrap(True)
        self.inputs_layout.addWidget(self.info)
        manifest = active_manifest()
        if manifest:
            self.info.setText(
                f"Project: {manifest['project']}\n"
                f"Mesh: {Path(manifest['source']['original_file']).name}"
            )

    def run_work(self):
        manifest = require_project(self.set_results)
        if manifest is None:
            return None
        self._manifest = manifest
        self.set_results(["Working\u2026"])
        return (_gate_worker, (manifest["source"]["original_file"],), {})

    def on_result(self, result):
        # MAIN THREAD — FreeCAD calls are safe here.
        if result["error"]:
            self.set_results([result["error"]])
            return
        gate = result["gate"]
        manifest = self._manifest
        ai = manifest["source"].get("source_type") == "ai-generated"

        manifest["quality"] = gate["verdict"]
        manifest["quality_reasons"] = gate.get("reasons", [])
        project.mark_stage(manifest, "quality", True)
        project.save_manifest(manifest["project_dir"], manifest)

        hole_frac = (gate.get("hole_fill") or {}).get("fraction")
        noise = gate.get("noise") or {}
        lines = [
            f"Watertight: {'yes' if gate.get('is_watertight') else 'no'}",
            f"Hole fill: {hole_frac:.1%} of surface" if hole_frac is not None
            else "Hole fill: unavailable",
            f"Noise: {noise.get('mean_mm')} mm mean"
            if noise.get("mean_mm") is not None else "Noise: not measured",
            f"Components: {gate.get('component_count', '?')}",
            "",
        ]
        lines += quality_lines(gate["verdict"], gate.get("reasons", []),
                               ai_mesh=ai)
        self.set_results(lines)

        if gate["verdict"] != "needs-rescan":
            self.enable_next()
        # needs-rescan: no next step. The stop IS the result.


class Command:
    NAME = "MTC_Quality"

    def GetResources(self):
        return {
            "MenuText": "Quality gate",
            "ToolTip": "Check the mesh is worth rebuilding from (Stage 1)",
            "Pixmap": icon("quality"),
        }

    def Activated(self):
        import FreeCADGui

        FreeCADGui.Control.showDialog(QualityPanel())

    def IsActive(self):
        manifest = active_manifest()
        return bool(manifest) and project.stage_done(manifest, "import")
