# -*- coding: utf-8 -*-
"""Shared task-panel machinery: base class + plain-language result renderers.

The renderers mirror the CLI's wording exactly (see mesh-to-cad's
_friendly_result). If the CLI changes its vocabulary, these change with it —
one vocabulary, three surfaces.
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .. import threads


def units_lines(units_check: dict) -> list[str]:
    """Plain-language units result. Mirrors the CLI."""
    sugg = units_check.get("suggestion", "?")
    conf = units_check.get("confidence", "?")
    if sugg == "millimeters":
        return [f"Units: looks like millimeters ({conf} confidence) — good."]
    return [
        f"Units: looks like {sugg} (confidence: {conf}).",
        "You confirmed this before continuing — the pipeline never guesses here.",
    ]


def quality_lines(verdict: str, reasons: list, ai_mesh: bool = False) -> list[str]:
    """Plain-language quality-gate result. Mirrors the CLI.

    ai_mesh: the stop copy reads "regenerate or clean up" instead of "rescan"
    — you can't rescan something that was never scanned.
    """
    first = reasons[0] if reasons else "see manifest.json for details"
    stop_word = "regenerate or clean up" if ai_mesh else "rescan"
    if verdict == "clean":
        return ["Quality: Clean — the mesh is solid, good to rebuild from."]
    if verdict == "noisy":
        return [
            "Quality: Noisy — usable, but expect cleanup first.",
            f"Why: {first}",
        ]
    if verdict == "needs-rescan":
        return [
            f"Quality: Needs {stop_word} — the mesh is missing too much data.",
            f"Why: {first}",
            f"No pipeline fixes missing data. {stop_word.capitalize()} "
            "and try again.",
        ]
    return [f"Quality: {verdict}"]


def track_lines(track: str, confidence: str) -> list[str]:
    """Plain-language track-decision result. Mirrors the CLI."""
    if track == "prismatic":
        return [
            "Shape: Prismatic — flat faces and cylinders.",
            "Good candidate for parametric CAD rebuild.",
        ]
    if track == "organic":
        return [
            "Shape: Organic — curvy/freeform.",
            "Needs the surface-rebuild path.",
        ]
    if track == "mixed":
        return [
            "Shape: Mixed — prismatic base with organic details.",
            "Rebuild the base first, details after.",
        ]
    return [f"Shape: {track} (confidence: {confidence})"]


class StagePanel(QWidget):
    """Base task panel: header, inputs area, run/cancel, results, next step.

    Subclasses fill in: title/one_liner (header), build_inputs() (part 2),
    run_work() (part 3's worker function — PURE, no FreeCAD), on_result()
    (part 4, runs on the main thread), next_label/next_command (part 5).
    """

    title = "Stage"
    one_liner = "What this stage does, in one plain sentence."
    next_label = ""
    next_command = ""

    def __init__(self):
        super().__init__()
        self._thread = None
        self._worker = None
        self._build()

    # -- layout ---------------------------------------------------------
    def _build(self):
        layout = QVBoxLayout(self)

        header = QLabel(f"<b>{self.title}</b><br>{self.one_liner}")
        header.setWordWrap(True)
        layout.addWidget(header)
        layout.addWidget(self._hrule())

        self.inputs_box = QWidget()
        self.inputs_layout = QVBoxLayout(self.inputs_box)
        self.inputs_layout.setContentsMargins(0, 0, 0, 0)
        self.build_inputs()
        layout.addWidget(self.inputs_box)

        row = QHBoxLayout()
        self.run_button = QPushButton("Run")
        self.run_button.clicked.connect(self._on_run_clicked)
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self._on_cancel_clicked)
        self.cancel_button.setEnabled(False)
        row.addWidget(self.run_button)
        row.addWidget(self.cancel_button)
        layout.addLayout(row)

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)  # indeterminate until stages report %
        self.progress.hide()
        layout.addWidget(self.progress)

        self.results = QLabel("")
        self.results.setWordWrap(True)
        self.results.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self.results)
        layout.addWidget(self._hrule())

        self.next_button = QPushButton(self.next_label or "Continue")
        self.next_button.setEnabled(False)
        self.next_button.clicked.connect(self._on_next_clicked)
        layout.addWidget(self.next_button)
        if not self.next_label:
            self.next_button.hide()

        layout.addStretch(1)

    @staticmethod
    def _hrule():
        line = QWidget()
        line.setFixedHeight(1)
        line.setStyleSheet("background-color: #888;")
        return line

    # -- subclass hooks ---------------------------------------------------
    def build_inputs(self):
        """Part 2: add input widgets to self.inputs_layout."""

    def run_work(self):
        """Part 3: return (fn, args, kwargs) for the worker thread.

        fn MUST be pure: plain data in, plain data out, no FreeCAD.
        """

    def on_result(self, result):
        """Part 4: runs on the MAIN thread. Update the doc + results label."""

    def on_error(self, message: str):
        self._work_done()
        self.set_results([f"Something went wrong: {message}",
                          "Nothing was modified."])

    # -- machinery (do not override) --------------------------------------
    def _on_run_clicked(self):
        spec = self.run_work()
        if spec is None:
            return
        fn, args, kwargs = spec
        self.run_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.progress.show()
        self._thread, self._worker = threads.run_in_thread(
            fn, self._on_worker_finished, self._on_worker_error,
            *args, **kwargs,
        )

    def _on_worker_finished(self, result):
        # Slot: runs on the main thread — FreeCAD calls are safe here.
        self._work_done()
        try:
            self.on_result(result)
        except Exception as e:
            self.set_results([f"Couldn't show the results: {e}",
                              "The work itself finished; only the display failed."])

    def _on_worker_error(self, message):
        self._work_done()
        self.on_error(message)

    def _on_cancel_clicked(self):
        if self._worker is not None:
            self._worker.cancel()
        self._work_done()
        self.set_results(["Cancelled — nothing was modified."])

    def _work_done(self):
        self.run_button.setEnabled(True)
        self.cancel_button.setEnabled(False)
        self.progress.hide()
        self._thread = None
        self._worker = None

    def set_results(self, lines: list[str]):
        self.results.setText("\n".join(lines))

    def enable_next(self):
        if self.next_label:
            self.next_button.setEnabled(True)

    def _on_next_clicked(self):
        if not self.next_command:
            return
        try:
            import FreeCADGui

            FreeCADGui.Control.closeDialog()
            FreeCADGui.runCommand(self.next_command, 0)
        except Exception:
            pass

    # -- FreeCAD task-panel dialog protocol --------------------------------
    def getStandardButtons(self):
        from PySide6.QtWidgets import QDialogButtonBox

        return int(QDialogButtonBox.Close)

    def accept(self):
        return True

    def reject(self):
        if self._worker is not None:
            self._worker.cancel()
        return True
