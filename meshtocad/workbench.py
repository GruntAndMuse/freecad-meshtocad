# -*- coding: utf-8 -*-
"""The MeshToCAD workbench class.

Toolbar order enforces the pipeline: Import -> Quality -> Analyze ->
Deviation. Each command's IsActive() gates on the manifest, so the buttons
themselves teach the order.

On first activation, runs the dependency check: trimesh missing ->
guided-install dialog (never silent, never a traceback); CloudCompare
missing -> one plain-language notice, deviation stays loud-but-disabled.
"""

import os

import FreeCADGui

from . import deps


class MeshToCADWorkbench(FreeCADGui.Workbench):
    MenuText = "MeshToCAD"
    ToolTip = ("Mesh to CAD pipeline: import, quality gate, analyze, "
               "deviation check. No magic scan-to-CAD button.")
    Icon = os.path.normpath(os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "..", "Resources", "icons", "workbench.svg"))

    def __init__(self):
        # Both are required (found 2026-10-09, GUI test):
        # 1. super().__init__() — the C++ base sets up __Workbench__; without
        #    it the object is half-constructed.
        # 2. InitGui passes the CLASS to addWorkbench(), not an instance —
        #    FreeCAD instantiates it internally (Draft workbench pattern).
        super().__init__()
        self._deps_checked = False

    def Initialize(self):
        from .commands import register_all, toolbar_commands

        register_all()
        cmds = toolbar_commands()
        self.appendToolbar("MeshToCAD", cmds)
        self.appendMenu("MeshToCAD", cmds)

    def Activated(self):
        if not self._deps_checked:
            self._deps_checked = True
            self._check_dependencies()

    def Deactivated(self):
        pass

    def GetClassName(self):
        return "Gui::PythonWorkbench"

    # -- first-run dependency check --------------------------------------
    def _check_dependencies(self):
        ok, version = deps.check_trimesh()
        if not ok:
            self._offer_trimesh_install()

    def _offer_trimesh_install(self):
        from PySide6.QtWidgets import QMessageBox

        box = QMessageBox()
        box.setWindowTitle("MeshToCAD — missing piece")
        box.setText(
            "This workbench needs the <b>trimesh</b> Python package to read "
            "meshes, and it isn't installed in FreeCAD's Python.\n\n"
            "Install it now? This runs pip into FreeCAD's own package folder "
            "(no system changes, no admin needed):"
        )
        box.setInformativeText(f"<tt>{deps.trimesh_install_command()}</tt>")
        box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        box.setDefaultButton(QMessageBox.Yes)
        if box.exec() != QMessageBox.Yes:
            return
        self._install_trimesh()

    def _install_trimesh(self):
        import subprocess

        from PySide6.QtCore import QObject
        from PySide6.QtWidgets import QMessageBox, QProgressDialog

        from . import threads

        target = deps.additional_packages_dir()
        target.mkdir(parents=True, exist_ok=True)
        pins = [f"{n}=={v}" for n, v in deps._pinned_versions().items()]
        cmd = [deps.python_exe(), "-m", "pip", "install",
               f"--target={target}"] + pins

        progress = QProgressDialog(
            "Installing trimesh and dependencies into FreeCAD's Python…\n"
            "This takes a few minutes — FreeCAD stays responsive.",
            None, 0, 0)  # no Cancel: pip can't be interrupted cleanly
        progress.setWindowTitle("MeshToCAD")
        progress.setMinimumDuration(0)

        def do_install():
            # WORKER THREAD — no GUI calls here.
            try:
                proc = subprocess.run(cmd, capture_output=True, text=True,
                                      timeout=900)
            except Exception as e:
                return {"ok": False, "detail": f"couldn't run pip: {e}"}
            if proc.returncode != 0:
                return {"ok": False,
                        "detail": proc.stderr[-2000:] or proc.stdout[-2000:]}
            return {"ok": True, "detail": ""}

        class InstallSlots(QObject):
            def on_done(self, result):
                progress.close()
                if result["ok"]:
                    QMessageBox.information(
                        None, "MeshToCAD",
                        "trimesh installed. Restart FreeCAD and the "
                        "workbench is ready.")
                else:
                    MeshToCADWorkbench._install_failed(result["detail"])

            def on_err(self, message):
                progress.close()
                MeshToCADWorkbench._install_failed(message)

        slots = InstallSlots()  # main-thread affinity: slots run on GUI thread
        self._install_slots = slots  # keep alive until done
        threads.run_in_thread(do_install, slots.on_done, slots.on_err)

    @staticmethod
    def _install_failed(detail: str):
        from PySide6.QtWidgets import QMessageBox

        QMessageBox.warning(
            None, "MeshToCAD — install failed",
            "The automatic install didn't work. Nothing was changed.\n\n"
            "Install it by hand with this command, then restart FreeCAD:\n\n"
            f"{deps.trimesh_install_command()}\n\nDetails:\n{detail[-1500:]}")
