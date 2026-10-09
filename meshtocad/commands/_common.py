# -*- coding: utf-8 -*-
"""Shared command helpers: icons, active project, gating."""

from pathlib import Path

from .. import project

_ICON_DIR = Path(__file__).parents[2] / "Resources" / "icons"


def icon(name: str) -> str:
    """Icon path resolved from the workbench tree — never hardcoded."""
    return str(_ICON_DIR / f"{name}.svg")


def active_manifest() -> dict | None:
    """The manifest of the project the user is working on, or None."""
    proj_dir = project.get_active_project_dir()
    if proj_dir is None:
        return None
    return project.load_manifest(proj_dir)


def require_project(panel_set_results) -> dict | None:
    """Fetch the active manifest or tell the user to import first."""
    manifest = active_manifest()
    if manifest is None:
        panel_set_results([
            "No project yet — run Import mesh first.",
            "The pipeline runs in order: Import \u2192 Quality \u2192 "
            "Analyze \u2192 Deviation.",
        ])
    return manifest
