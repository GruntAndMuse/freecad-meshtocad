# -*- coding: utf-8 -*-
"""Stage 4 — Verify build (verification report).

Judges the built model three ways (see meshtocad/verification.py):
dimension re-check against the Analyze measurements, the kernel geometry
check, and the deviation result recorded by the Deviation stage. Writes
verification/<name>_report.md and stamps the manifest with the verdict:
pass / fail / incomplete. INCOMPLETE is a first-class outcome — if a
check didn't run, the report says so and never calls it a pass.

Threading: the shape summary + geometry check touch the document, so they
are gathered HERE (main thread, in run_work — same pattern as the
Deviation panel's tessellation). The judging + report writing is pure
and runs in the worker.
"""

from pathlib import Path

from PySide6.QtWidgets import QComboBox, QDoubleSpinBox, QHBoxLayout, QLabel

from .. import project, verification
from ..framework import freecad_io
from ..ui.panels import StagePanel
from ._common import active_manifest, icon, require_project


def _shape_objects():
    """Document objects that carry a shape. MAIN THREAD ONLY."""
    import FreeCAD

    doc = FreeCAD.ActiveDocument
    if doc is None:
        return doc, []
    return doc, [o for o in doc.Objects
                 if freecad_io.shape_summary(o) is not None]


# The worker function lives in the app layer (meshtocad/verification.py)
# so it stays headless-testable without Qt. Pure: plain data in/out.
_verify_worker = verification.run_verification


class VerifyPanel(StagePanel):
    title = "Verify build"
    one_liner = ("Judge the finished model: dimensions re-checked against "
                 "the measurements, geometry checked, deviation on record. "
                 "Writes the verification report.")
    next_label = "Continue \u2192 Export"
    next_command = "MTC_Export"

    def build_inputs(self):
        row = QHBoxLayout()
        row.addWidget(QLabel("Model to verify:"))
        self.obj_combo = QComboBox()
        _, objs = _shape_objects()
        self._objects = objs
        for o in objs:
            self.obj_combo.addItem(o.Label)
        row.addWidget(self.obj_combo)
        self.inputs_layout.addLayout(row)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel("Tolerance (mm):"))
        self.tol_spin = QDoubleSpinBox()
        self.tol_spin.setRange(0.01, 10.0)
        self.tol_spin.setSingleStep(0.05)
        row2.addWidget(self.tol_spin)
        row2.addWidget(QLabel("Mating (mm):"))
        self.mating_spin = QDoubleSpinBox()
        self.mating_spin.setRange(0.01, 10.0)
        self.mating_spin.setSingleStep(0.05)
        row2.addWidget(self.mating_spin)
        self.inputs_layout.addLayout(row2)

        manifest = active_manifest()
        if manifest:
            self.tol_spin.setValue(float(manifest.get("tolerance_mm", 0.3)))
            self.mating_spin.setValue(
                float(manifest.get("mating_tolerance_mm", 0.1)))
        else:
            self.tol_spin.setValue(0.3)
            self.mating_spin.setValue(0.1)

        self.info = QLabel(
            "Compares against the ORIGINAL input mesh's measurements — "
            "never a cleaned copy. If the deviation check hasn't run, the "
            "verdict will be INCOMPLETE, not pass."
        )
        self.info.setWordWrap(True)
        self.inputs_layout.addWidget(self.info)

    def run_work(self):
        manifest = require_project(self.set_results)
        if manifest is None:
            return None
        idx = self.obj_combo.currentIndex()
        if idx < 0 or idx >= len(self._objects):
            self.set_results([
                "No model with a shape in the document — build the "
                "model (or open its document) first, then verify."
            ])
            return None
        obj = self._objects[idx]
        # Main thread: gather the FreeCAD-side facts as plain data.
        summary = freecad_io.shape_summary(obj)
        shape = getattr(obj, "Shape", None)
        geometry = freecad_io.geometry_check(shape) if shape else None
        self._manifest = manifest
        self.set_results(["Verifying\u2026"])
        return (_verify_worker,
                (manifest, summary, geometry, self.tol_spin.value(),
                 self.mating_spin.value()),
                {})

    def on_result(self, result):
        # MAIN THREAD — FreeCAD calls are safe here.
        if result["error"]:
            self.set_results([result["error"]])
            return
        report = result["report"]
        manifest = self._manifest
        manifest["verification"] = report["summary"]
        project.mark_stage(manifest, "verify", True)
        project.save_manifest(manifest["project_dir"], manifest)

        s = report["summary"]
        lines = [
            f"Verdict: {report['verdict'].upper()}",
            f"Dimensions: {s['dimensions_passed']} passed, "
            f"{s['dimensions_failed']} failed, "
            f"{s['dimensions_not_run']} not run",
        ]
        if "worst_dimension" in s:
            lines.append(f"Worst dimension: {s['worst_dimension']} — "
                         f"off by {s['worst_delta_mm']} mm")
        lines += ["", f"Report: verification/{Path(result['path']).name}"]
        if report["verdict"] == "incomplete":
            lines.append("Incomplete is not a pass — the report lists "
                         "which check didn't run and why.")
        self.set_results(lines)
        self.enable_next()


class Command:
    NAME = "MTC_Verify"

    def GetResources(self):
        return {
            "MenuText": "Verify build",
            "ToolTip": "Verification report: dimensions + geometry + deviation (Stage 4)",
            "Pixmap": icon("verify"),
        }

    def Activated(self):
        import FreeCADGui

        FreeCADGui.Control.showDialog(VerifyPanel())

    def IsActive(self):
        manifest = active_manifest()
        return bool(manifest) and project.stage_done(manifest, "analyze")
