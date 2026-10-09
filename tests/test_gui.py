# -*- coding: utf-8 -*-
"""GUI integration test — run inside the FreeCAD GUI under xvfb.

Run:  MTC_WB_ROOT=/home/hatch/workspace/freecad-workbench \
      xvfb-run -a <freecad-bin> /home/hatch/workspace/freecad-workbench/tests/test_gui.py

Exercises what freecadcmd can't: InitGui registration, workbench
activation, the four commands, task-panel construction, and the QThread
worker pattern end-to-end (signals -> main-thread slots).

Lessons baked in (2026-10-09):
- FreeCAD's event loop is ALREADY running during startup scripts: a nested
  QApplication.exec() returns immediately. Signal slots run after the script
  returns; the script must not block waiting for them.
- Never call wb.Initialize() manually: the C++ delegate (__Workbench__)
  only exists after activation. Use activateWorkbench().
- Flush every print: FreeCAD's script-exception handler can discard
  buffered stdout.
"""

import os
import sys
import traceback

WB_ROOT = os.environ.get("MTC_WB_ROOT")
assert WB_ROOT and os.path.isdir(WB_ROOT), "set MTC_WB_ROOT"
if WB_ROOT not in sys.path:
    sys.path.insert(0, WB_ROOT)

RESULTS = []


def check(name, cond, detail=""):
    RESULTS.append((name, bool(cond), detail))
    print(("ok - " if cond else "FAIL - ") + name
          + (f" ({detail})" if detail and not cond else ""), flush=True)


def finish():
    failed = [r for r in RESULTS if not r[1]]
    print(f"\n{len(RESULTS) - len(failed)}/{len(RESULTS)} GUI checks passed",
          flush=True)
    if failed:
        open("/tmp/guitest_failed.txt", "w").write("\n".join(
            r[0] for r in failed))
    print("GUI TEST DONE", flush=True)


try:
    import FreeCADGui
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication

    # 1. InitGui registers the workbench (pass class; FreeCAD instantiates)
    import InitGui  # noqa: F401
    wb = FreeCADGui.getWorkbench("MeshToCADWorkbench")
    check("workbench registered", wb is not None)

    # 2. Full activation lifecycle, then the four commands exist
    FreeCADGui.activateWorkbench("MeshToCADWorkbench")
    for cmd in ("MTC_Import", "MTC_Quality", "MTC_Analyze", "MTC_Deviation"):
        check(f"command {cmd} registered",
              cmd in FreeCADGui.listCommands())

    # 3. Task panels construct without errors
    from meshtocad.commands.cmd_analyze import AnalyzePanel
    from meshtocad.commands.cmd_deviation import DeviationPanel
    from meshtocad.commands.cmd_import import ImportPanel
    from meshtocad.commands.cmd_quality import QualityPanel

    for cls in (ImportPanel, QualityPanel, AnalyzePanel, DeviationPanel):
        try:
            panel = cls()
            check(f"{cls.__name__} constructs", True)
            check(f"{cls.__name__} has run/next buttons",
                  panel.run_button is not None and panel.next_button is not None)
        except Exception as e:
            check(f"{cls.__name__} constructs", False, str(e))

    # 4. Deviation panel degrades loudly without CloudCompare
    from meshtocad import deps, threads

    if deps.find_cloudcompare() is None:
        panel = DeviationPanel()
        check("deviation panel loud without CC",
              "CloudCompare not found" in panel.cc_label.text())
    else:
        print("(cloudcompare found — skipping loud-degradation check)",
              flush=True)

    # 5. Worker thread pattern. Slots MUST be bound methods of a QObject
    # living in the main thread (like the panels' QWidget slots): a plain
    # function has no thread affinity, so Qt uses a direct connection and
    # it runs IN THE WORKER THREAD — silently wrong. (Verified 2026-10-09:
    # plain-function slots failed exactly this way.)
    from PySide6.QtCore import QObject

    state = {}

    def pure_fn(a, b):
        import threading
        state["worker_thread"] = threading.current_thread().name
        return a + b

    class SlotHolder(QObject):
        def on_done(self, result):
            import threading
            state["slot_thread"] = threading.current_thread().name
            state["result"] = result
            worker_checks()

        def on_err(self, msg):
            state["error"] = msg
            worker_checks()

    holder = SlotHolder()  # main-thread affinity

    def worker_checks():
        check("worker ran off the main thread",
              state.get("worker_thread") != state.get("slot_thread"),
              str(state))
        check("slot ran on main thread",
              state.get("slot_thread") == "MainThread", str(state))
        check("worker result marshalled", state.get("result") == 42,
              str(state))
        check("worker no error", "error" not in state,
              str(state.get("error")))
        finish()
        threads.wait_for_all(10000)
        QApplication.instance().quit()

    # (SlotHolder methods above are the slots; no plain-function versions.)

    # Keep the references (the registry is a backstop, not the primary owner).
    _t, _w = threads.run_in_thread(pure_fn, holder.on_done, holder.on_err,
                                   20, 22)

    def on_timeout():
        check("worker completed within 30s", False, "timeout")
        finish()
        QApplication.instance().quit()

    QTimer.singleShot(30000, on_timeout)
    # Return to FreeCAD's running event loop — the slots do the rest.

except Exception:
    open("/tmp/guitrace.txt", "w").write(traceback.format_exc())
    print("FAIL - test script crashed; see /tmp/guitrace.txt", flush=True)
    try:
        from PySide6.QtWidgets import QApplication
        QApplication.instance().quit()
    except Exception:
        pass
