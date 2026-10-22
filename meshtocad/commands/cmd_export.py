# -*- coding: utf-8 -*-
"""Stage 5 — Export project (STEP / STL / FCStd / TechDraw PDF).

Writes the project's deliverables into output/ and records them in the
manifest. Planning is framework/exporting.py (pure); writing is
framework/freecad_io.py (the host adapter).

WHY NO WORKER THREAD HERE: every writer needs live document objects
(Part.export, Mesh.export, TechDraw), and document objects may only be
touched from the main thread (see meshtocad/threads.py — that rule is
the #1 crash risk in this codebase). Exports are writes of already-
computed geometry — normally seconds — so this panel runs them
synchronously on the main thread and says so. A format that can't be
produced (no solid for STEP, no GUI for the drawing PDF) is reported as
skipped/failed WITH ITS REASON, never silently dropped.
"""

from pathlib import Path

from PySide6.QtWidgets import QCheckBox, QLabel, QVBoxLayout

from .. import exporting, project
from ..framework import freecad_io
from ..framework.exporting import plan_exports, summarize_results
from ..ui.panels import StagePanel
from ._common import active_manifest, icon, require_project


class ExportPanel(StagePanel):
    title = "Export project"
    one_liner = ("Write the deliverables into output/: STEP for CAD "
                 "exchange, STL, a copy of the document, and a TechDraw "
                 "drawing PDF.")
    # Last stage — no next step.

    def build_inputs(self):
        self.checks = {}
        box = QVBoxLayout()
        for fmt in exporting.SPEC.formats:
            cb = QCheckBox(fmt.label)
            cb.setChecked(fmt.key in exporting.SPEC.default_keys)
            self.checks[fmt.key] = cb
            box.addWidget(cb)
        self.inputs_layout.addLayout(box)
        self.info = QLabel("")
        self.info.setWordWrap(True)
        self.inputs_layout.addWidget(self.info)
        manifest = active_manifest()
        if manifest:
            v = (manifest.get("verification") or {}).get("verdict")
            note = f"Project: {manifest['project']}\n"
            if v == "fail":
                note += ("Verification verdict is FAIL — exporting is "
                         "allowed, but you'd be shipping a model that "
                         "failed its checks.")
            elif v != "pass":
                note += ("No passing verification on record — run "
                         "Verify build first if this export matters.")
            self.info.setText(note)

    # Synchronous main-thread run (see module docstring). Overrides the
    # StagePanel worker machinery for this panel only.
    def _on_run_clicked(self):
        manifest = require_project(self.set_results)
        if manifest is None:
            return
        import FreeCAD

        doc = FreeCAD.ActiveDocument
        if doc is None:
            self.set_results([
                "No document open — open the model you built, then export."
            ])
            return
        selected = [k for k, cb in self.checks.items() if cb.isChecked()]
        if not selected:
            self.set_results(["Pick at least one format to export."])
            return

        descriptors = freecad_io.object_descriptors(doc)
        plan = plan_exports(exporting.SPEC.formats, descriptors, selected,
                            exporting.output_stem(manifest))
        out_dir = Path(manifest["project_dir"]) / "output"
        outcomes = []
        for job in plan["jobs"]:
            try:
                written = freecad_io.export_job(doc, job, out_dir)
                outcomes.append({"ok": True, "path": str(written),
                                 "detail": ""})
            except Exception as e:
                outcomes.append({"ok": False, "path": job["filename"],
                                 "detail": str(e)})
        summary = summarize_results(plan["jobs"], outcomes)

        manifest["export"] = {
            "files": [Path(p).name for p in summary["written"]],
            "skipped": plan["skipped"],
            "failed": summary["failed"],
        }
        if summary["written"]:
            project.mark_stage(manifest, "export", True)
        project.save_manifest(manifest["project_dir"], manifest)

        lines = []
        for p in summary["written"]:
            lines.append(f"Wrote output/{Path(p).name}")
        for f in summary["failed"]:
            lines.append(f"FAILED {f['path']}: {f['detail']}")
        for s in plan["skipped"]:
            lines.append(f"Skipped {s['format']}: {s['reason']}")
        if not summary["written"] and not summary["failed"]:
            lines.append("Nothing was exported — see the skips above.")
        self.set_results(lines)


class Command:
    NAME = "MTC_Export"

    def GetResources(self):
        return {
            "MenuText": "Export project",
            "ToolTip": "STEP / STL / FCStd / TechDraw drawing PDF into output/ (Stage 5)",
            "Pixmap": icon("export"),
        }

    def Activated(self):
        import FreeCADGui

        FreeCADGui.Control.showDialog(ExportPanel())

    def IsActive(self):
        manifest = active_manifest()
        return bool(manifest) and project.stage_done(manifest, "verify")
