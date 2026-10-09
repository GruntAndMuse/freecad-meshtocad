# -*- coding: utf-8 -*-
"""Pipeline engine, single-sourced from the mesh-to-cad repo.

DO NOT HAND-EDIT THE .py FILES IN THIS DIRECTORY. They are copies — the
originals live in mesh-to-cad/scripts/. Fix the original, run
../../sync_engine.sh (or `sync_engine.sh --check` in CI to catch drift).

Loaded via importlib from explicit file paths so these copies can never
collide with another mesh-to-cad checkout on sys.path.
"""

import importlib.util
from pathlib import Path

_ENGINE_DIR = Path(__file__).parent


def _load(name: str):
    path = _ENGINE_DIR / f"{name}.py"
    if not path.is_file():
        raise ImportError(
            f"engine script missing: {path.name} — run sync_engine.sh "
            "to copy it from the mesh-to-cad repo."
        )
    spec = importlib.util.spec_from_file_location(f"mtc_engine_{name}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _lazy(name: str):
    cache = {}

    def get():
        if name not in cache:
            cache[name] = _load(name)
        return cache[name]

    return get


check_units = _lazy("check_units")
quality_gate = _lazy("quality_gate")
analyze = _lazy("analyze")
deviation = _lazy("deviation")
