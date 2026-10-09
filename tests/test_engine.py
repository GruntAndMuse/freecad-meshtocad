# -*- coding: utf-8 -*-
"""Engine tests — headless, no FreeCAD needed.

Run:  python3 test_engine.py
   or pytest test_engine.py

Uses the pipeline's own test samples (known answers): bracket_prismatic.stl
is prismatic, blob_organic.stl is organic.
"""

import sys
from pathlib import Path

# Workbench root on the path so `meshtocad` imports.
_WB_ROOT = Path(__file__).parents[1]
if str(_WB_ROOT) not in sys.path:
    sys.path.insert(0, str(_WB_ROOT))

from meshtocad import engine  # noqa: E402

SAMPLES = Path.home() / "workspace" / "pipelines" / "mesh-to-cad" / "test-samples"
# Fall back to a relative guess if HOME differs (CI checkouts).
if not SAMPLES.is_dir():
    SAMPLES = _WB_ROOT.parent / "pipelines" / "mesh-to-cad" / "test-samples"


def _sample(name: str) -> Path:
    p = SAMPLES / name
    assert p.is_file(), f"test sample missing: {p}"
    return p


def test_units_bracket():
    units = engine.check_units().suggest_units(_sample("bracket_prismatic.stl"))
    assert units["suggestion"] in ("millimeters", "meters",
                                   "micrometers-or-inches"), units
    assert units["confidence"] in ("high", "medium"), units
    assert units["diagonal_file_units"] > 0
    print(f"  units: {units['suggestion']} ({units['confidence']})")


def test_quality_gate_bracket():
    gate = engine.quality_gate().quality_gate(_sample("bracket_prismatic.stl"))
    assert gate["verdict"] in ("clean", "noisy", "needs-rescan"), gate
    assert isinstance(gate["reasons"], list)
    print(f"  quality: {gate['verdict']}")


def test_analyze_bracket_is_prismatic():
    result, aligned = engine.analyze().analyze(_sample("bracket_prismatic.stl"))
    assert result["track_decision"] == "prismatic", result["track_decision"]
    assert aligned is not None
    assert "bounding_box_mm" in result
    print(f"  bracket track: {result['track_decision']} "
          f"({result['track_confidence']})")


def test_analyze_blob_is_organic():
    result, aligned = engine.analyze().analyze(_sample("blob_organic.stl"))
    assert result["track_decision"] == "organic", result["track_decision"]
    print(f"  blob track: {result['track_decision']} "
          f"({result['track_confidence']})")


def test_deviation_module_loads():
    dev = engine.deviation()
    assert callable(dev.measure_clean)
    assert callable(dev.find_cloudcompare)
    print("  deviation module loads")


TESTS = [
    test_units_bracket,
    test_quality_gate_bracket,
    test_analyze_bracket_is_prismatic,
    test_analyze_blob_is_organic,
    test_deviation_module_loads,
]


def main() -> int:
    failures = 0
    for t in TESTS:
        try:
            print(f"{t.__name__} ...")
            t()
            print("  PASS")
        except Exception as e:
            failures += 1
            print(f"  FAIL: {e}")
    print(f"\n{len(TESTS) - failures}/{len(TESTS)} passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
