# -*- coding: utf-8 -*-
"""Stage 0 — Import mesh for reverse engineering.

File picker -> project folder -> original copied to input/ (never modified)
-> units check -> the pipeline refuses to guess here, so the user confirms.

AI-generated source type: the mesh is unitless, so the units check becomes
"tell me how big this should be" — raw extents shown, user enters the
intended longest dimension, scale factor computed from that.
"""

from pathlib import Path

from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QWidget,
)

from .. import project
from ..engine import check_units
from ..ui.panels import StagePanel, units_lines
from ._common import icon


def _show_mesh_in_doc(mesh_path: str, doc_name: str):
    """Insert the mesh into the FreeCAD document for visual reference.

    MAIN THREAD ONLY — called from the panel slot, never from a worker.
    """
    import FreeCAD
    import Mesh

    doc = FreeCAD.ActiveDocument
    if doc is None:
        doc = FreeCAD.newDocument(doc_name)
    Mesh.insert(str(mesh_path), doc.Name)


def _units_worker(mesh_path: str) -> dict:
    """Pure worker: run the units suggestion. No FreeCAD."""
    return check_units().suggest_units(Path(mesh_path))


class ImportPanel(StagePanel):
    title = "Import mesh"
    one_liner = ("Bring a mesh in and set up its project folder. "
                 "The original file is copied, never modified.")
    next_label = "Continue \u2192 Quality gate"
    next_command = "MTC_Quality"

    def build_inputs(self):
        # Mesh file picker
        row = QHBoxLayout()
        row.addWidget(QLabel("Mesh file:"))
        self.file_edit = QLineEdit()
        self.file_edit.setPlaceholderText("pick an STL file\u2026")
        browse = QPushButton("Browse\u2026")
        browse.clicked.connect(self._browse_mesh)
        row.addWidget(self.file_edit)
        row.addWidget(browse)
        self.inputs_layout.addLayout(row)

        # Source type — AI-generated is first-class (red-pen decision #6)
        row2 = QHBoxLayout()
        row2.addWidget(QLabel("Source:"))
        self.source_combo = QComboBox()
        self.source_combo.addItems([
            "scanner \u2014 from a 3D scanner",
            "download \u2014 from a model site",
            "photogrammetry \u2014 from phone/camera reconstruction",
            "ai-generated \u2014 made by an AI image/3D tool (unitless!)",
        ])
        self.source_combo.currentIndexChanged.connect(self._source_changed)
        row2.addWidget(self.source_combo)
        self.inputs_layout.addLayout(row2)

        # Project location
        row3 = QHBoxLayout()
        row3.addWidget(QLabel("Projects folder:"))
        self.proj_edit = QLineEdit(str(project.default_projects_dir()))
        proj_browse = QPushButton("Browse\u2026")
        proj_browse.clicked.connect(self._browse_projects)
        row3.addWidget(self.proj_edit)
        row3.addWidget(proj_browse)
        self.inputs_layout.addLayout(row3)

        # AI size entry (hidden unless ai-generated)
        self.ai_row = QWidget()
        ai_layout = QHBoxLayout(self.ai_row)
        ai_layout.setContentsMargins(0, 0, 0, 0)
        ai_layout.addWidget(QLabel("Intended longest side (mm):"))
        self.ai_size_edit = QLineEdit()
        self.ai_size_edit.setPlaceholderText("e.g. 120")
        ai_layout.addWidget(self.ai_size_edit)
        self.ai_row.hide()
        self.inputs_layout.addWidget(self.ai_row)

        self.ai_note = QLabel(
            "AI meshes are unitless — the numbers in the file mean nothing "
            "until you say how big the part should be. Tell me the intended "
            "size and I'll work out the scale."
        )
        self.ai_note.setWordWrap(True)
        self.ai_note.hide()
        self.inputs_layout.addWidget(self.ai_note)

        # Units confirmation (appears after Run when the pipeline won't guess)
        self.confirm_row = QWidget()
        confirm_layout = QHBoxLayout(self.confirm_row)
        confirm_layout.setContentsMargins(0, 0, 0, 0)
        self.confirm_button = QPushButton("Confirm units — continue")
        self.confirm_button.clicked.connect(self._confirm_units)
        confirm_layout.addWidget(self.confirm_button)
        self.confirm_row.hide()
        self.inputs_layout.addWidget(self.confirm_row)

        self._pending_units = None
        self._pending_manifest = None
        self._pending_project_dir = None

    # -- input helpers ----------------------------------------------------
    def _browse_mesh(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Pick a mesh file", str(Path.home()),
            "Mesh files (*.stl *.STL *.ply *.PLY *.obj *.OBJ *.3mf *.3MF)",
        )
        if path:
            self.file_edit.setText(path)

    def _browse_projects(self):
        path = QFileDialog.getExistingDirectory(
            self, "Projects folder", self.proj_edit.text()
        )
        if path:
            self.proj_edit.setText(path)

    def _source_changed(self, index):
        is_ai = index == 3
        self.ai_row.setVisible(is_ai)
        self.ai_note.setVisible(is_ai)

    def _source_type(self) -> str:
        return project.SOURCE_TYPES[self.source_combo.currentIndex()]

    # -- run --------------------------------------------------------------
    def run_work(self):
        mesh = self.file_edit.text().strip()
        if not mesh:
            self.set_results(["Pick a mesh file first."])
            return None
        if self._source_type() == "ai-generated":
            try:
                intended = float(self.ai_size_edit.text().strip())
                if intended <= 0:
                    raise ValueError()
            except ValueError:
                self.set_results([
                    "For an AI-generated mesh, enter the intended longest "
                    "side in millimeters first — the file's own numbers "
                    "mean nothing until you do."
                ])
                return None
        self.set_results(["Working\u2026"])
        return (_import_worker, (mesh, self.proj_edit.text().strip(),
                                self._source_type()), {})

    def on_result(self, result):
        # MAIN THREAD — FreeCAD calls are safe here.
        if result["error"]:
            self.set_results([result["error"]])
            return
        manifest = result["manifest"]
        self._pending_manifest = manifest
        self._pending_units = result["units"]
        self._pending_project_dir = manifest["project_dir"]

        project.set_active_project_dir(manifest["project_dir"])
        _show_mesh_in_doc(manifest["source"]["original_file"],
                          manifest["project"])

        lines = [
            f"Project folder: {manifest['project_dir']}",
            f"Original copied to input/ — your file was not modified.",
            f"Source: {manifest['source']['source_type']}",
            "",
        ]
        units = result["units"]
        if manifest["source"]["source_type"] == "ai-generated":
            raw = units["diagonal_file_units"]
            intended = float(self.ai_size_edit.text().strip())
            scale = intended / raw if raw else 0
            lines += [
                f"The file measures {raw:.3f} units across (meaningless — "
                "AI meshes are unitless).",
                f"You said the longest side should be {intended:g} mm, "
                f"so the scale is \u00d7{scale:.4f}.",
                "",
                "AI meshes carry no real dimensions. This pipeline gives you "
                "editable geometry; YOU set the dimensions to spec afterward.",
            ]
            self._confirm_units()  # user already told us the size — confirmed
            return
        lines += units_lines(units)
        self.set_results(lines)

        if units["suggestion"] == "millimeters":
            # CLI behavior: millimeters -> proceed without asking.
            self._confirm_units()
        else:
            lines += ["", units.get("why", "")]
            lines += ["",
                      "The pipeline won't guess here — a wrong scale corrupts "
                      "everything downstream. Confirm to continue, or convert "
                      "the file first and re-import."]
            self.set_results(lines)
            self.confirm_row.show()

    def _confirm_units(self):
        manifest = self._pending_manifest
        units = self._pending_units
        if manifest is None:
            return
        if manifest["source"]["source_type"] == "ai-generated":
            manifest["source"]["units"] = "mm (user-set size for AI mesh)"
            manifest["source"]["units_check"] = {
                "suggestion": "ai-generated (unitless)",
                "scale_factor": None,
                "confidence": "user-set",
            }
        else:
            manifest["source"]["units_check"] = {
                "suggestion": units["suggestion"],
                "scale_factor": units["scale_factor"],
                "confidence": units["confidence"],
            }
            if units["suggestion"] == "millimeters":
                manifest["source"]["units"] = "mm (looks like millimeters)"
            else:
                manifest["source"]["units"] = (
                    f"mm (confirmed by user, scale \u00d7{units['scale_factor']})"
                )
        project.record_tool_versions(manifest)
        project.save_manifest(self._pending_project_dir, manifest)
        self.confirm_row.hide()
        self.set_results(self.results.text().split("\n") + [
            "", "Units confirmed — project ready."
        ])
        self.enable_next()


def _import_worker(mesh: str, projects_dir: str, source_type: str) -> dict:
    """Pure worker: project setup + units suggestion. No FreeCAD.

    Returns {"manifest", "units", "error"}. The panel slot does the
    FreeCAD-side work (showing the mesh, saving confirmation).
    """
    try:
        manifest = project.create_project(mesh, projects_dir, source_type)
    except ValueError as e:
        return {"error": str(e), "manifest": None, "units": None}
    input_copy = manifest["source"]["original_file"]
    try:
        units = check_units().suggest_units(Path(input_copy))
    except Exception as e:
        return {"error": f"couldn't read the mesh: {e}",
                "manifest": None, "units": None}
    return {"error": None, "manifest": manifest, "units": units}


class Command:
    NAME = "MTC_Import"

    def GetResources(self):
        return {
            "MenuText": "Import mesh",
            "ToolTip": "Bring a mesh in and set up its project (Stage 0)",
            "Pixmap": icon("import"),
        }

    def Activated(self):
        import FreeCADGui

        FreeCADGui.Control.showDialog(ImportPanel())

    def IsActive(self):
        return True
