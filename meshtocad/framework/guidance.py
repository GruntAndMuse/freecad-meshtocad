# -*- coding: utf-8 -*-
"""Rebuild guidance — turn a measurements dict into a modeling reference.

GENERIC framework module: no pipeline vocabulary lives here. The app layer
supplies a *field spec* (which measurements matter, how to label and format
them, and what the modeler should do with each number); this module walks
the spec, formats the values, and renders a reference document.

The rendered reference is the "directions ARE the automation" artifact for
the manual rebuild stage: a checklist + every measurement the rebuild will
later be verified against, in one file the modeler keeps beside the CAD.

Pure Python — plain data in/out, headless-testable, worker-thread safe.
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class GuidanceField:
    """One measurement the modeler needs, and how to present it.

    key:  dotted path into the measurements dict ("bounding_box.extents").
          A trailing "[i]" indexes a list ("bounding_box.extents[0]").
    kind: "value" | "percent" | "bool" | "text" — formatting only.
    hint: what to DO with this number while modeling (the guidance).
    """

    key: str
    label: str
    unit: str = ""
    kind: str = "value"
    decimals: int = 3
    hint: str = ""


def dig(data, dotted_key: str):
    """Resolve a dotted key (with optional [i] list indexes). None if absent."""
    import re

    cur = data
    for token in re.findall(r"[^.\[\]]+|\[\d+\]", dotted_key):
        if token.startswith("["):
            try:
                cur = cur[int(token[1:-1])]
            except (ValueError, IndexError, KeyError, TypeError):
                return None
        else:
            if not isinstance(cur, dict) or token not in cur:
                return None
            cur = cur[token]
    return cur


def format_value(value, kind: str = "value", decimals: int = 3) -> str:
    """Format one measurement value for display. Never raises."""
    if value is None:
        return "— not measured —"
    if kind == "bool":
        return "yes" if value else "no"
    if kind == "percent":
        try:
            return f"{float(value):.0%}"
        except (TypeError, ValueError):
            return str(value)
    if kind == "text":
        return str(value)
    try:
        return f"{float(value):.{decimals}f}"
    except (TypeError, ValueError):
        return str(value)


def build_reference_rows(measurements: dict, fields: list) -> list:
    """Walk the spec over the measurements. One row per field.

    Row: {"label", "value_text", "unit", "hint", "present"}.
    Missing measurements stay visible as rows (present=False) — a guidance
    panel that silently drops the number it couldn't find teaches the
    modeler to trust a partial reference.
    """
    rows = []
    for f in fields:
        raw = dig(measurements, f.key)
        rows.append({
            "label": f.label,
            "value_text": format_value(raw, f.kind, f.decimals),
            "unit": f.unit,
            "hint": f.hint,
            "present": raw is not None,
        })
    return rows


def missing_labels(rows: list) -> list:
    return [r["label"] for r in rows if not r["present"]]


def render_reference_markdown(title: str, intro_lines: list, rows: list,
                              checklist: list,
                              extra_sections: list = ()) -> str:
    """Render the reference document (Markdown).

    extra_sections: [(heading, [lines])] — app-specific additions (e.g. a
    dominant-planes table) rendered after the measurement table.
    """
    out = [f"# {title}", ""]
    out += list(intro_lines) + [""]
    out += ["## Measurements to build to", "",
            "| Measurement | Value | How to use it |",
            "|---|---|---|"]
    for r in rows:
        value = r["value_text"] + (f" {r['unit']}" if r["unit"] else "")
        out.append(f"| {r['label']} | {value} | {r['hint']} |")
    missing = missing_labels(rows)
    if missing:
        out += ["", "**Not measured** (do not guess these — re-run the "
                "measurement stage if you need them): "
                + ", ".join(missing) + "."]
    for heading, lines in extra_sections:
        out += ["", f"## {heading}", ""] + list(lines)
    if checklist:
        out += ["", "## Rebuild checklist", ""]
        out += [f"- [ ] {step}" for step in checklist]
    out.append("")
    return "\n".join(out)


@dataclass
class GuidanceSpec:
    """Everything an app needs to describe its guidance panel."""

    fields: list = field(default_factory=list)
    checklist: list = field(default_factory=list)
