#!/usr/bin/env bash
# run_tests.sh — engine tests (plain python) + workbench tests (freecadcmd).
# freecadcmd location: $FREECADCMD, or ~/workspace/freecad/freecadcmd.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
FREECADCMD="${FREECADCMD:-$HOME/workspace/freecad/freecadcmd}"

echo "=== engine tests (no FreeCAD) ==="
python3 "$HERE/test_engine.py"

echo ""
echo "=== workbench tests (freecadcmd) ==="
# Absolute path: freecadcmd exec's scripts without setting __file__,
# so the test resolves its tree from argv[0].
"$FREECADCMD" "$HERE/test_workbench.py"
