# -*- coding: utf-8 -*-
"""Worker-thread helper — the #1 crash-risk area. Read this before touching.

THE RULE (FreeCAD is absolute about it): document objects may ONLY be touched
from the main GUI thread. A worker thread that calls doc.addObject, touches
obj.Shape, or even reads a property that triggers a recompute can crash or
hard-freeze FreeCAD. There is no warning — it just dies.

THE PATTERN:
  1. The panel builds a Worker around a PURE function — trimesh/numpy math,
     subprocess calls, file I/O. The function receives plain data (paths,
     numbers, strings) and returns plain data (dicts, lists). It NEVER
     receives a FreeCAD object and NEVER imports FreeCAD.
  2. Worker runs in a QThread. Signals (finished/error/progress) cross the
     thread boundary via Qt's queued connections.
  3. The panel's slots run ON THE MAIN THREAD — that is the ONLY place that
     touches the document (inserting the aligned mesh, updating the manifest
     display, etc.).

CRITICAL: the finished/error slots MUST be bound methods of a QObject that
lives in the main thread (e.g. the panel QWidget itself). A plain function
has no thread affinity, so Qt delivers the signal via direct connection —
the "slot" then runs IN THE WORKER THREAD, silently. Touching the document
there crashes FreeCAD. This was verified by test_gui.py on 2026-10-09:
plain-function slots failed; bound-method slots passed.

If you're adding a new long operation: put the math in the worker function,
put the FreeCAD calls in the slot. When in doubt, the slot is where FreeCAD
lives.
"""

from PySide6.QtCore import QObject, QThread, Signal

# Live workers. WHY A REGISTRY: if the last Python reference to a QThread
# (or its Worker) is dropped while the OS thread is still shutting down, Qt
# aborts the whole process ("QThread: Destroyed while thread is still
# running") — and worse, a GC'd Worker silently drops the started->run
# slot, so the thread idles forever with no error. The registry holds BOTH
# until the thread's destroyed() signal fires. Bounded: entries are removed
# on destroyed, so this can't grow without limit.
_LIVE_WORKERS: dict[QThread, "Worker"] = {}


def _forget(thread: QThread):
    _LIVE_WORKERS.pop(thread, None)


def wait_for_all(timeout_ms: int = 10000) -> bool:
    """Block until all worker threads finish. For tests and shutdown."""
    ok = True
    for thread in list(_LIVE_WORKERS):
        if not thread.wait(timeout_ms):
            ok = False
    return ok


class Worker(QObject):
    """Runs fn(*args, **kwargs) off the GUI thread. Emits plain-data results."""

    finished = Signal(object)  # result payload — must be plain data
    error = Signal(str)        # human-readable error, never a traceback dump
    progress = Signal(int)     # 0-100, optional

    def __init__(self, fn, *args, **kwargs):
        super().__init__()
        self._fn = fn
        self._args = args
        self._kwargs = kwargs
        self._cancelled = False

    def cancel(self):
        """Cooperative cancel — the worker fn should check worker.cancelled()."""
        self._cancelled = True

    def cancelled(self) -> bool:
        return self._cancelled

    def run(self):
        # THIS RUNS IN THE WORKER THREAD. No FreeCAD here. Ever.
        try:
            result = self._fn(*self._args, **self._kwargs)
            if not self._cancelled:
                self.finished.emit(result)
        except Exception as e:
            if not self._cancelled:
                self.error.emit(str(e))


def run_in_thread(fn, on_finished, on_error, *args, on_progress=None,
                  **kwargs) -> tuple[QThread, Worker]:
    """Start fn in a worker thread. Slots run on the main thread.

    on_progress is keyword-only (positional args after on_error belong to
    fn — binding one to on_progress by accident is a silent, confusing bug).

    Returns (thread, worker) — the caller owns them; call worker.cancel()
    then thread.quit()/wait() to stop. Typical use lives in ui/panels.py's
    run helpers, not inline in commands.
    """
    thread = QThread()
    worker = Worker(fn, *args, **kwargs)
    worker.moveToThread(thread)
    thread.started.connect(worker.run)
    worker.finished.connect(on_finished)
    worker.error.connect(on_error)
    if on_progress is not None:
        worker.progress.connect(on_progress)
    # Cleanup: stop the thread when the work is done, one way or another.
    # The registry keeps the Python wrappers alive until destroyed() fires —
    # dropping them earlier aborts the process (see _LIVE_WORKERS).
    worker.finished.connect(thread.quit)
    worker.error.connect(thread.quit)
    thread.finished.connect(worker.deleteLater)
    thread.finished.connect(thread.deleteLater)
    thread.destroyed.connect(lambda: _forget(thread))
    _LIVE_WORKERS[thread] = worker
    thread.start()
    return thread, worker
