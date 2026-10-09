# -*- coding: utf-8 -*-
"""Task panels — one per pipeline stage.

Every panel follows the same five-part shape (the directions ARE the
automation, for now):
  1. Header: stage name + what it does in one plain sentence.
  2. Inputs: whatever the stage needs, pre-filled where possible.
  3. Run button -> progress bar + Cancel. Long work runs in a worker thread;
     the GUI stays responsive.
  4. Results: the numbers, in the SAME wording as the CLI. No new vocabulary —
     the docs, the CLI, and the workbench all say the same things.
  5. Next-step button ("Continue -> ...") that closes this panel and opens
     the next stage's panel.

Panels are QWidgets shown via FreeCADGui.Control.showDialog(). The dialog
object implements accept()/reject()/getStandardButtons() per FreeCAD's
task-panel convention.
"""
