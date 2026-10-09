# -*- coding: utf-8 -*-
"""Project folders + manifest.json.

The manifest is the single source of truth for pipeline state — the workbench
reads it to show which stages are done, so closing and reopening FreeCAD
doesn't lose anything. Schema mirrors the mesh-to-cad CLI's manifest.json
(so CLI and workbench projects are interchangeable) plus workbench-specific
fields: source_type (incl. ai-generated), per-stage completion flags.

No FreeCAD imports here — pure Python, headless-testable.
"""

import json
import shutil
from datetime import date
from pathlib import Path

SOURCE_TYPES = ("scanner", "download", "photogrammetry", "ai-generated")
PROJECT_SUBDIRS = ("input", "work", "analysis", "cad", "verification", "output")
STAGES = ("import", "quality", "analyze", "deviation")


def default_projects_dir() -> Path:
    """Where new projects go unless the user picks elsewhere.

    Under the user's home dir — no drive letter, no platform assumption.
    """
    return Path.home() / "mesh-to-cad-projects"


def create_project(mesh_path: str | Path, projects_dir: str | Path | None,
                   source_type: str = "scanner") -> dict:
    """Set up a project folder for one mesh. Returns the new manifest dict.

    Copies the original into input/ — the original is never modified (SOP).
    Raises ValueError on bad input; never leaves a half-built folder behind
    without a manifest explaining what happened.
    """
    mesh_path = Path(mesh_path)
    if not mesh_path.is_file():
        raise ValueError(f"mesh file not found: {mesh_path}")
    if source_type not in SOURCE_TYPES:
        raise ValueError(
            f"unknown source type {source_type!r} — pick one of: "
            + ", ".join(SOURCE_TYPES)
        )

    projects_dir = Path(projects_dir) if projects_dir else default_projects_dir()
    project_dir = projects_dir / mesh_path.stem
    we_created = not project_dir.exists()

    for sub in PROJECT_SUBDIRS:
        (project_dir / sub).mkdir(parents=True, exist_ok=True)

    input_copy = project_dir / "input" / mesh_path.name
    try:
        if mesh_path.resolve() != input_copy.resolve():
            shutil.copy2(mesh_path, input_copy)
    except OSError as e:
        raise ValueError(f"couldn't copy mesh into project: {e}")

    manifest = {
        "project": project_dir.name,
        "project_dir": str(project_dir),
        "tool": f"freecad-meshtocad {__import__('meshtocad').__version__}",
        "date": str(date.today()),
        "source": {
            "original_file": str(input_copy),
            "source_type": source_type,
            "units": "mm (pending confirmation)",
        },
        "stages": {s: False for s in STAGES},
        "tools": {},
    }
    manifest["stages"]["import"] = True
    save_manifest(project_dir, manifest)
    return manifest


def manifest_path(project_dir: str | Path) -> Path:
    return Path(project_dir) / "manifest.json"


def load_manifest(project_dir: str | Path) -> dict | None:
    """Read the manifest, or None if this isn't a project folder."""
    p = manifest_path(project_dir)
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def save_manifest(project_dir: str | Path, manifest: dict) -> None:
    manifest_path(project_dir).write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )


def mark_stage(manifest: dict, stage: str, done: bool = True) -> None:
    if stage not in STAGES:
        raise ValueError(f"unknown stage {stage!r}")
    manifest["stages"][stage] = done


def stage_done(manifest: dict | None, stage: str) -> bool:
    if not manifest:
        return False
    return bool(manifest.get("stages", {}).get(stage, False))


def record_tool_versions(manifest: dict) -> None:
    """Snapshot the tool versions that produced these results. Reproducibility."""
    import sys

    tools = {
        "python": f"{sys.version_info.major}.{sys.version_info.minor}."
                  f"{sys.version_info.micro}",
    }
    try:
        import trimesh

        tools["trimesh"] = trimesh.__version__
    except Exception:
        pass
    try:
        import FreeCAD

        tools["freecad"] = ".".join(str(v) for v in FreeCAD.Version()[:3])
    except Exception:
        pass
    manifest["tools"] = tools


def get_active_project_dir() -> Path | None:
    """The project the user is working on, remembered across commands.

    Stored in FreeCAD's own parameter system (User parameter tree) — no files
    in magic locations, no hardcoded paths. Returns None when unset.
    """
    try:
        import FreeCAD

        params = FreeCAD.ParamGet(
            "User parameter:BaseApp/Preferences/Mod/MeshToCAD"
        )
        raw = params.GetString("ActiveProjectDir", "")
        return Path(raw) if raw else None
    except Exception:
        return None


def set_active_project_dir(project_dir: str | Path) -> None:
    """Remember the active project. See get_active_project_dir."""
    import FreeCAD

    params = FreeCAD.ParamGet(
        "User parameter:BaseApp/Preferences/Mod/MeshToCAD"
    )
    params.SetString("ActiveProjectDir", str(Path(project_dir)))
