# -*- coding: utf-8 -*-
"""Deviation check — how far is YOUR model from the input mesh?

Tessellates the selected solid (or a picked STL), runs CloudCompare
cloud-to-mesh against the project's input mesh, reports max/mean/p95 and
pass/fail vs the tolerance.

CloudCompare is a SOFT dependency: if it's missing, this panel says so
loudly — what it needs, where to get it, per-OS — and the Run button stays
disabled. Everything else in the workbench keeps working. Never a
traceback, never a silent skip.

Honest limit, stated in the panel: this checks your model against the input
mesh. For an AI mesh that means "your CAD matches the AI mesh" — not "your
CAD matches reality."
"""

import tempfile
from pathlib import Path

from PySide6.QtWidgets import (
    QDoubleSpinBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
)

from .. import deps, project
from ..engine import deviation as deviation_mod
from ..ui.panels import StagePanel
from ._common import active_manifest, icon, require_project

# Same distance cap the CLI uses: deviations beyond this are "way off",
# not "slightly over tolerance".
MAX_DIST_CAP_MM = 5.0


def _deviation_worker(model_stl: str, ref_stl: str, cc_bin: str) -> dict:
    """Pure worker: CloudCompare c2m. No FreeCAD."""
    try:
        stats = deviation_mod().measure_clean(
            Path(model_stl), Path(ref_stl), MAX_DIST_CAP_MM, cc_bin
        )
        return {"error": None, "stats": stats}
    except FileNotFoundError as e:
        return {"error": str(e)}
    except RuntimeError as e:
        return {"error": f"CloudCompare ran but failed: {e}"}
    except Exception as e:
        return {"error": f"couldn't parse CloudCompare output: {e}"}


def _tessellate_selection_to_stl() -> str:
    """Tessellate the selected solid to a temp STL. MAIN THREAD ONLY."""
    import FreeCADGui
    import Mesh

    sel = FreeCADGui.Selection.getSelection()
    if not sel:
        raise ValueError("nothing selected — select the solid to check first.")
    obj = sel[0]
    shape = getattr(obj, "Shape", None)
    if shape is None or shape.isNull():
        raise ValueError(
            f"'{obj.Label}' has no shape to measure — select a solid, not a mesh."
        )
    tmp = Path(tempfile.mkdtemp(prefix="mtc_model_")) / "model.stl"
    mesh = Mesh.Mesh(shape.tessellate(0.1))
    mesh.write(str(tmp))
    return str(tmp)


class DeviationPanel(StagePanel):
    title = "Deviation check"
    one_liner = ("How far is your model from the input mesh? "
                 "Needs CloudCompare (free) — see below if it's missing.")
    # No next step in the MVP: deviation is the last stage.

    def build_inputs(self):
        self.cc_bin = deps.find_cloudcompare()
        if not self.cc_bin:
            # LOUD degradation: the whole panel becomes the install guide.
            self.cc_label = QLabel(
                "<b>CloudCompare not found.</b><br><br>"
                + deps.cloudcompare_guidance().replace("\n", "<br>")
                + "<br><br>Install it, restart FreeCAD, and this panel will "
                  "light up. Everything else in the workbench works meanwhile."
            )
            self.cc_label.setWordWrap(True)
            self.inputs_layout.addWidget(self.cc_label)
            return

        self.sel_radio = QRadioButton("Selected solid in the document")
        self.sel_radio.setChecked(True)
        self.file_radio = QRadioButton("STL file:")
        self.file_edit = QLineEdit()
        self.file_edit.setPlaceholderText("pick a model STL\u2026")
        browse = QPushButton("Browse\u2026")
        browse.clicked.connect(self._browse_model)
        self.inputs_layout.addWidget(self.sel_radio)
        row = QHBoxLayout()
        row.addWidget(self.file_radio)
        row.addWidget(self.file_edit)
        row.addWidget(browse)
        self.inputs_layout.addLayout(row)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel("Tolerance (mm):"))
        self.tol_spin = QDoubleSpinBox()
        self.tol_spin.setRange(0.01, 10.0)
        self.tol_spin.setValue(0.3)
        self.tol_spin.setSingleStep(0.05)
        row2.addWidget(self.tol_spin)
        self.inputs_layout.addLayout(row2)

        self.info = QLabel(
            "Checks YOUR model against the project's input mesh — the "
            "original, never a cleaned copy."
        )
        self.info.setWordWrap(True)
        self.inputs_layout.addWidget(self.info)

    def _browse_model(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Pick the model STL", str(Path.home()),
            "STL files (*.stl *.STL)",
        )
        if path:
            self.file_edit.setText(path)
            self.file_radio.setChecked(True)

    def _on_run_clicked(self):
        if not self.cc_bin:
            self.set_results([
                "Can't run without CloudCompare — see above for install steps."
            ])
            return
        super()._on_run_clicked()

    def run_work(self):
        manifest = require_project(self.set_results)
        if manifest is None:
            return None
        self._manifest = manifest
        self._tolerance = self.tol_spin.value()

        # Tessellation touches the document -> happens here (main thread),
        # NOT in the worker. run_work() is called from the panel, which is
        # main-thread context.
        try:
            if self.file_radio.isChecked():
                model_stl = self.file_edit.text().strip()
                if not model_stl or not Path(model_stl).is_file():
                    self.set_results(["Pick a model STL file first."])
                    return None
            else:
                model_stl = _tessellate_selection_to_stl()
        except ValueError as e:
            self.set_results([str(e)])
            return None

        self.set_results(["Running CloudCompare\u2026"])
        return (_deviation_worker,
                (model_stl, manifest["source"]["original_file"], self.cc_bin),
                {})

    def on_result(self, result):
        # MAIN THREAD — FreeCAD calls are safe here.
        if result["error"]:
            self.set_results([result["error"],
                              "Nothing was modified."])
            return
        s = result["stats"]
        manifest = self._manifest
        ai = manifest["source"].get("source_type") == "ai-generated"
        tol = self._tolerance
        passed = s["max_mm"] <= tol

        manifest["deviation"] = {
            "max_mm": s["max_mm"],
            "mean_mm": s["mean_mm"],
            "p95_mm": s["p95_mm"],
            "tolerance_mm": tol,
            "passed": bool(passed),
        }
        project.mark_stage(manifest, "deviation", True)
        project.save_manifest(manifest["project_dir"], manifest)

        lines = [
            f"Max deviation:  {s['max_mm']} mm",
            f"Mean deviation: {s['mean_mm']} mm",
            f"P95 deviation:  {s['p95_mm']} mm",
            "",
        ]
        if passed:
            lines.append(f"PASS \u2713 \u2014 max {s['max_mm']} mm \u2264 "
                         f"{tol} mm tolerance")
        else:
            lines.append(f"FAIL \u2717 \u2014 max {s['max_mm']} mm > "
                         f"{tol} mm tolerance")
            lines.append("The model needs more work before it's within tolerance.")
        if ai:
            lines += ["",
                      "Remember: this checks your CAD against the AI mesh — "
                      "\"matches the AI mesh,\" not \"matches reality.\""]
        self.set_results(lines)


class Command:
    NAME = "MTC_Deviation"

    def GetResources(self):
        return {
            "MenuText": "Deviation check",
            "ToolTip": "CloudCompare cloud-to-mesh: model vs input mesh",
            "Pixmap": icon("deviation"),
        }

    def Activated(self):
        import FreeCADGui

        FreeCADGui.Control.showDialog(DeviationPanel())

    def IsActive(self):
        manifest = active_manifest()
        return bool(manifest) and project.stage_done(manifest, "analyze")
