# -*- coding: utf-8 -*-
"""Dependency detection: trimesh (required) and CloudCompare (soft).

Rules:
- Detect, never assume. Every path is resolved from the environment.
- Missing trimesh -> guided install into FreeCAD's AdditionalPythonPackages,
  with pinned versions (numpy-2.x breakage is a documented forum graveyard).
- Missing CloudCompare -> LOUD degradation. The deviation command explains
  itself and stays disabled; everything else keeps working. Never a
  traceback, never a silent skip.
- No FreeCAD imports at module level (headless-testable). FreeCAD-specific
  helpers guard their imports.
"""

import os
import shutil
import sys
from pathlib import Path

# Loose floors — last resort when the synced lock file is missing.
DEP_FLOORS = {
    "trimesh": "4.0",
    "numpy": "1.24",
    "scipy": "1.10",
    "networkx": "3.0",
}


# Pinned versions, synced from the pipeline's requirements-locked.txt (the
# versions the pipeline was actually tested against). Falls back to loose
# floors when the sync hasn't run. Read at call time, not import time, so
# tests can point at a fixture.
def _pinned_versions() -> dict:
    pins: dict[str, str] = {}
    locked = Path(__file__).parent / "engine" / "requirements-locked.txt"
    try:
        for line in locked.read_text(encoding="utf-8").splitlines():
            line = line.split("#", 1)[0].strip()
            if "==" in line:
                name, ver = (p.strip() for p in line.split("==", 1))
                pins[name.lower()] = ver
    except OSError:
        pass
    for name, floor in DEP_FLOORS.items():
        pins.setdefault(name, floor)
    return pins

CC_ENV_VAR = "MESHTOCAD_CC_BIN"


def check_trimesh() -> tuple[bool, str | None]:
    """(ok, version_or_None). Pure import check — no side effects."""
    try:
        import trimesh

        return True, trimesh.__version__
    except Exception:
        return False, None


def additional_packages_dir() -> Path:
    """Where FreeCAD looks for user-installed Python packages.

    Derived from FreeCAD's own app-data dir — never hardcoded, works on any
    drive and any OS.
    """
    try:
        import FreeCAD

        base = Path(FreeCAD.getUserAppDataDir())
    except Exception:
        # Outside FreeCAD (headless tests): mirror the platform convention.
        if os.name == "nt":
            base = Path(os.environ.get("APPDATA", "~")) / "FreeCAD"
        elif sys.platform == "darwin":
            base = Path.home() / "Library" / "Application Support" / "FreeCAD"
        else:
            base = Path.home() / ".local" / "share" / "FreeCAD"
    return base / "AdditionalPythonPackages"


def python_exe() -> str:
    """The Python interpreter whose packages FreeCAD actually uses."""
    try:
        import freecad.utils  # noqa

        return __import__("freecad.utils", fromlist=["get_python_exe"]).get_python_exe()
    except Exception:
        return sys.executable


def trimesh_install_command() -> str:
    """The exact pip command the user should run. Shown in the guided dialog."""
    target = additional_packages_dir()
    pins = " ".join(f"{name}=={ver}" for name, ver in _pinned_versions().items())
    return f'"{python_exe()}" -m pip install --target="{target}" {pins}'


def find_cloudcompare(explicit: str | None = None) -> str | None:
    """Locate the CloudCompare binary. Returns path or None (not an exception).

    Order: explicit arg/env var -> PATH (both casings) -> platform-typical
    locations derived from environment variables (ProgramFiles etc. — never
    a hardcoded drive letter).
    """
    candidates: list[str] = []
    env_bin = os.environ.get(CC_ENV_VAR)
    for cand in (explicit, env_bin):
        if cand:
            candidates.append(cand)
    for name in ("CloudCompare", "cloudcompare"):
        found = shutil.which(name)
        if found:
            candidates.append(found)
    # Platform-typical spots, all derived from env — no hardcoded drives.
    if os.name == "nt":
        for var in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA"):
            root = os.environ.get(var)
            if root:
                candidates.append(
                    str(Path(root) / "CloudCompare" / "CloudCompare.exe")
                )
    elif sys.platform == "darwin":
        candidates.append("/Applications/CloudCompare.app/Contents/MacOS/CloudCompare")
    for c in candidates:
        if c and Path(c).exists():
            return c
    return None


def cloudcompare_guidance() -> str:
    """Plain-language install help, per OS. Shown when CC is missing."""
    lines = [
        "Deviation check needs CloudCompare (it does the cloud-to-mesh math).",
        "Everything else in this workbench works without it.",
        "",
    ]
    if os.name == "nt":
        lines.append("Windows: download the installer from cloudcompare.org "
                     "— install anywhere you like (D: drive is fine).")
    elif sys.platform == "darwin":
        lines.append("macOS: download CloudCompare.app from cloudcompare.org "
                     "and drop it in Applications.")
    else:
        lines.append("Linux: `sudo apt install cloudcompare`, or download "
                     "from cloudcompare.org.")
    lines += [
        "",
        "If it's installed but not found, set the environment variable",
        f"{CC_ENV_VAR} to its full path and restart FreeCAD.",
    ]
    return "\n".join(lines)
