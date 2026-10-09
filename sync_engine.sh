#!/usr/bin/env bash
# sync_engine.sh — single-source the pipeline engine scripts into the workbench.
#
# The pipeline scripts live in ONE place (the mesh-to-cad repo). This script
# copies them into meshtocad/engine/ at build/release time. NEVER hand-edit
# the copies — fix the pipeline, re-run this script.
#
# Pipeline location: $MESHTOCAD_PIPELINE_DIR, or ~/workspace/pipelines/mesh-to-cad
# by default. Derived from the environment — no hardcoded machine paths.
#
# Usage: ./sync_engine.sh          # copy
#        ./sync_engine.sh --check   # fail if copies are stale (CI gate)
set -euo pipefail

PIPELINE_DIR="${MESHTOCAD_PIPELINE_DIR:-$HOME/workspace/pipelines/mesh-to-cad}"
SRC="$PIPELINE_DIR/scripts"
DST="$(cd "$(dirname "$0")" && pwd)/meshtocad/engine"
FILES="check_units.py quality_gate.py analyze.py deviation.py"

if [ ! -d "$SRC" ]; then
  echo "pipeline scripts not found at $SRC" >&2
  echo "set MESHTOCAD_PIPELINE_DIR to the mesh-to-cad checkout" >&2
  exit 1
fi

if [ "${1:-}" = "--check" ]; then
  stale=0
  for f in $FILES requirements-locked.txt; do
    if ! cmp -s "$SRC/$f" "$DST/$f" 2>/dev/null; then
      echo "STALE: engine/$f differs from pipeline $SRC/$f" >&2
      stale=1
    fi
  done
  [ "$stale" -eq 0 ] && echo "engine/ is in sync with the pipeline"
  exit "$stale"
fi

mkdir -p "$DST"
for f in $FILES requirements-locked.txt; do
  cp "$SRC/$f" "$DST/$f"
  echo "synced $f"
done
echo "done — engine/ matches $SRC"
