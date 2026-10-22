# -*- coding: utf-8 -*-
"""Export planning — which formats, which objects, which files.

GENERIC framework module: the app layer declares the formats it supports
(ExportFormat records) and what the document offers (object descriptors:
name + kind); this module plans the jobs — one output file per (format,
object) the format applies to — and records skips WITH REASONS instead of
silently dropping them. Execution (actually writing files) is the host
adapter's job (see freecad_io); planning is pure and headless-testable.

Object kinds are host vocabulary mapped by the adapter: "solid" (a shape
with volume), "mesh", "other". A format declares the kinds it can write;
anything else is a skip with a plain-language reason.
"""

import re
from dataclasses import dataclass, field


@dataclass(frozen=True)
class ExportFormat:
    """One output format an app can produce.

    key:       stable id used in manifests ("step", "stl", ...).
    kinds:     object kinds this format can write.
    per_object: True -> one file per object; False -> one file total
               (e.g. a drawing page or a whole-document save).
    needs_gui: True when writing requires the host's GUI layer (the panel
               warns instead of pretending a headless write happened).
    """

    key: str
    label: str
    extension: str
    kinds: tuple = ("solid",)
    per_object: bool = True
    needs_gui: bool = False


def sanitize_stem(name: str) -> str:
    """A filesystem-safe file stem from any display name."""
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", (name or "").strip())
    return stem.strip("._") or "export"


def plan_exports(formats: list, objects: list, selected_keys,
                 stem: str) -> dict:
    """Plan export jobs. Returns {"jobs": [...], "skipped": [...]}.

    objects: [{"name", "kind"}]. selected_keys: format keys the user chose.
    Job: {"format", "label", "extension", "object" (name or None),
          "filename"}. Skip: {"format", "reason"} — every selected format
    that produces no job appears here exactly once, with why.
    """
    jobs, skipped = [], []
    by_key = {f.key: f for f in formats}
    safe_stem = sanitize_stem(stem)
    for key in selected_keys:
        fmt = by_key.get(key)
        if fmt is None:
            skipped.append({"format": key, "reason": "unknown format"})
            continue
        targets = [o for o in objects if o.get("kind") in fmt.kinds]
        if not targets:
            kinds = "/".join(fmt.kinds)
            skipped.append({
                "format": key,
                "reason": f"no {kinds} object to export — {fmt.label} "
                          "needs one; skipped, not faked.",
            })
            continue
        if fmt.per_object:
            multi = len(targets) > 1
            for o in targets:
                suffix = f"_{sanitize_stem(o['name'])}" if multi else ""
                jobs.append({
                    "format": key, "label": fmt.label,
                    "extension": fmt.extension, "object": o["name"],
                    "filename": f"{safe_stem}{suffix}.{fmt.extension}",
                    "needs_gui": fmt.needs_gui,
                })
        else:
            jobs.append({
                "format": key, "label": fmt.label,
                "extension": fmt.extension,
                "object": targets[0]["name"],
                "filename": f"{safe_stem}.{fmt.extension}",
                "needs_gui": fmt.needs_gui,
            })
    return {"jobs": jobs, "skipped": skipped}


def summarize_results(jobs: list, outcomes: list) -> dict:
    """Fold per-job outcomes into counts the manifest/panel can show.

    outcomes: parallel to jobs, each {"ok": bool, "path", "detail"}.
    """
    done = [o for o in outcomes if o.get("ok")]
    failed = [o for o in outcomes if not o.get("ok")]
    return {
        "written": [o["path"] for o in done],
        "failed": [{"path": o.get("path", ""), "detail": o.get("detail", "")}
                   for o in failed],
        "ok": len(failed) == 0 and len(done) > 0,
        "partial": len(done) > 0 and len(failed) > 0,
    }


@dataclass
class ExportSpec:
    """Everything an app needs to describe its export panel."""

    formats: list = field(default_factory=list)
    default_keys: tuple = ()
