# -*- coding: utf-8 -*-
"""Stage 2 — Analyze mesh.

Runs the geometry analysis in a worker thread (dense scans take minutes —
the GUI stays responsive, Cancel works). Shows bbox, planar/cylindrical
fractions, symmetry, and the track decision + confidence. The aligned STL
goes into the 3D view for a visual sanity check. Track override dropdown
for the medium-confidence cases — the machine takes a stand, the human
overrides only when the machine is unsure.
"""

import json
from pathlib import Path

from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
)

from .. import project
from ..engine import analyze as analyze_mod
from ..ui.panels import StagePanel, track_lines
from ._common import active_manifest, icon, require_project


def _analyze_worker(input_copy: str, analysis_dir: str) -> dict:
    """Pure worker: analyze + write measurements JSON + aligned STL.

    No FreeCAD. Returns {"error", "result", "json_path", "aligned_path"}.
    """
    try:
        result, aligned = analyze_mod().analyze(Path(input_copy))
    except Exception as e:
        return {"error": f"analysis failed: {e}"}
    adir = Path(analysis_dir)
    adir.mkdir(parents=True, exist_ok=True)
    stem = Path(input_copy).stem
    json_path = adir / f"{stem}_measurements.json"
    aligned_path = adir / f"{stem}_aligned.stl"
    try:
        json_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
        aligned.export(str(aligned_path))
    except Exception as e:
        return {"error": f"couldn't write analysis outputs: {e}"}
    return {"error": None, "result": result,
            "json_path": str(json_path), "aligned_path": str(aligned_path)}


def _show_aligned_in_doc(aligned_path: str, name: str):
    """MAIN THREAD ONLY — visual sanity check of the aligned mesh."""
    import FreeCAD
    import Mesh

    doc = FreeCAD.ActiveDocument
    if doc is None:
        doc = FreeCAD.newDocument(name)
    Mesh.insert(str(aligned_path), doc.Name)


class AnalyzePanel(StagePanel):
    title = "Analyze mesh"
    one_liner = ("Measure everything before any CAD is built. These numbers "
                 "are what the rebuild gets judged against.")
    next_label = "Continue \u2192 Deviation check"
    next_command = "MTC_Deviation"

    def build_inputs(self):
        row = QHBoxLayout()
        row.addWidget(QLabel("Tolerance (mm):"))
        self.tol_spin = QDoubleSpinBox()
        self.tol_spin.setRange(0.01, 10.0)
        self.tol_spin.setValue(0.3)
        self.tol_spin.setSingleStep(0.05)
        row.addWidget(self.tol_spin)
        row.addWidget(QLabel("Mating (mm):"))
        self.mating_spin = QDoubleSpinBox()
        self.mating_spin.setRange(0.01, 10.0)
        self.mating_spin.setValue(0.1)
        self.mating_spin.setSingleStep(0.05)
        row.addWidget(self.mating_spin)
        self.inputs_layout.addLayout(row)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel("Track override:"))
        self.track_combo = QComboBox()
        self.track_combo.addItems(["auto (trust the analysis)",
                                   "prismatic", "organic", "mixed"])
        row2.addWidget(self.track_combo)
        self.inputs_layout.addLayout(row2)

        self.info = QLabel("")
        self.info.setWordWrap(True)
        self.inputs_layout.addWidget(self.info)
        manifest = active_manifest()
        if manifest:
            self.info.setText(
                f"Project: {manifest['project']}\n"
                "Runs in the background — the GUI stays responsive. "
                "Cancel any time."
            )

    def run_work(self):
        manifest = require_project(self.set_results)
        if manifest is None:
            return None
        self._manifest = manifest
        self._tolerance = self.tol_spin.value()
        self._mating = self.mating_spin.value()
        override = self.track_combo.currentText()
        self._override = None if override.startswith("auto") else override
        self.set_results(["Analyzing\u2026 (this can take minutes on dense scans)"])
        return (_analyze_worker,
                (manifest["source"]["original_file"],
                 str(Path(manifest["project_dir"]) / "analysis")),
                {})

    def on_result(self, result):
        # MAIN THREAD — FreeCAD calls are safe here.
        if result["error"]:
            self.set_results([result["error"]])
            return
        r = result["result"]
        manifest = self._manifest
        ai = manifest["source"].get("source_type") == "ai-generated"

        track = self._override or r["track_decision"]
        manifest["track"] = track
        manifest["track_confidence"] = r["track_confidence"]
        manifest["track_reason"] = r["track_reason"]
        if self._override:
            manifest["track_override"] = self._override
        manifest["tolerance_mm"] = self._tolerance
        manifest["mating_tolerance_mm"] = self._mating
        project.mark_stage(manifest, "analyze", True)
        project.save_manifest(manifest["project_dir"], manifest)

        _show_aligned_in_doc(result["aligned_path"],
                             manifest["project"] + "_aligned")

        bb = r.get("bounding_box_mm", {})
        ext = bb.get("extents", ["?", "?", "?"])
        sym = r.get("symmetry", {})
        sym_line = ", ".join(
            f"{k}: {'symmetric' if v.get('symmetric') else 'no'}"
            for k, v in sym.items() if isinstance(v, dict)
        )
        lines = [
            f"Bounding box: {ext[0]} \u00d7 {ext[1]} \u00d7 {ext[2]} mm",
            f"Faces: {r.get('faces', '?')}  "
            f"Watertight: {'yes' if r.get('is_watertight') else 'no'}",
            f"Prismatic faces: {r.get('effective_prismatic_fraction', '?')}",
            f"Symmetry — {sym_line}",
            "",
        ]
        lines += track_lines(track, r["track_confidence"])
        if r["track_confidence"] == "medium":
            lines += ["",
                      "Medium confidence — this is the case the track "
                      "override is for. Pick a track above if you disagree."]
        if ai:
            lines += ["",
                      "AI meshes carry no real dimensions. This gives you "
                      "editable geometry; YOU set the dimensions to spec "
                      "afterward."]
        lines += ["",
                  f"Measurements: {Path(result['json_path']).name}",
                  "Aligned mesh shown in the 3D view — sanity-check the "
                  "orientation before you model."]
        self.set_results(lines)
        self.enable_next()


class Command:
    NAME = "MTC_Analyze"

    def GetResources(self):
        return {
            "MenuText": "Analyze mesh",
            "ToolTip": "Measure the mesh: bbox, features, track decision (Stage 2)",
            "Pixmap": icon("analyze"),
        }

    def Activated(self):
        import FreeCADGui

        FreeCADGui.Control.showDialog(AnalyzePanel())

    def IsActive(self):
        manifest = active_manifest()
        return (bool(manifest)
                and project.stage_done(manifest, "quality")
                and manifest.get("quality") != "needs-rescan")
