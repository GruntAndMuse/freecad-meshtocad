#!/usr/bin/env bash
# run_tests.sh — engine tests (plain python) + workbench tests (freecadcmd)
# + GUI tests (FreeCAD under xvfb, when available).
# freecadcmd location: $FREECADCMD, or ~/workspace/freecad/freecadcmd.
# GUI binary location: $FREECAD_GUI, or the extracted AppImage tree.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
FREECADCMD="${FREECADCMD:-$HOME/workspace/freecad/freecadcmd}"
FREECAD_GUI="${FREECAD_GUI:-$HOME/workspace/freecad/app/squashfs-root/usr/bin/freecad}"

echo "=== engine tests (no FreeCAD) ==="
python3 "$HERE/test_engine.py"

echo ""
echo "=== workbench tests (freecadcmd) ==="
# Absolute path: freecadcmd exec's scripts without setting __file__,
# so the test resolves its tree from argv[0].
"$FREECADCMD" "$HERE/test_workbench.py"

echo ""
echo "=== GUI tests (xvfb) ==="
if [ -x "$FREECAD_GUI" ] && command -v xvfb-run >/dev/null 2>&1; then
  rm -f /tmp/guitest_failed.txt /tmp/guitest_results.txt
  MTC_WB_ROOT="$(dirname "$HERE")" timeout 600 xvfb-run -a "$FREECAD_GUI" \
    "$HERE/test_gui.py" > /tmp/mtc_guitest.log 2>&1 || true
  # Verdict comes from the results file the test writes itself (FreeCAD's
  # stdout plumbing + the test's deterministic exit can lose log lines;
  # files don't get lost).
  cat /tmp/guitest_results.txt 2>/dev/null || true
  if [ -f /tmp/guitest_failed.txt ]; then
    echo "GUI TESTS FAILED:"; cat /tmp/guitest_failed.txt; exit 1
  fi
  grep -q "GUI TEST DONE" /tmp/guitest_results.txt || {
    echo "GUI tests did not complete — see /tmp/mtc_guitest.log"; exit 1; }
  echo "GUI tests passed"
else
  echo "skipped — no GUI binary or xvfb-run on this machine"
fi
