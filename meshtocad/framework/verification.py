# -*- coding: utf-8 -*-
"""Verification reports — compare what was built against what was measured.

GENERIC framework module: no pipeline vocabulary lives here. The app layer
supplies dimension pairs (expected vs actual, each with its tolerance), a
geometry-check summary, and any extra named checks; this module computes
pass/fail per check, finds the WORST instance in each class (acceptance is
judged on worst instances, never averages), combines everything into one
honest verdict, and renders the report.

Verdict vocabulary (the whole framework uses exactly these):
  "pass"       — every check that ran passed.
  "fail"       — at least one check that ran failed. Fail beats incomplete:
                 a known failure is never hidden behind a missing check.
  "incomplete" — nothing failed, but at least one required check did not
                 run (missing input, missing optional tool, ...). The
                 report says which, and why. Never upgraded to "pass".

Pure Python — plain data in/out, headless-testable, worker-thread safe.
"""

VERDICTS = ("pass", "fail", "incomplete")
CHECK_STATUSES = ("pass", "fail", "not-run")


def compare_dimensions(pairs: list) -> list:
    """Judge dimension pairs.

    Each pair: {"name", "expected", "actual", "tolerance"} (floats or None).
    Returns one check row per pair: {"name", "expected", "actual", "delta",
    "tolerance", "status"} — status "not-run" when either side is missing,
    with the reason in "detail".
    """
    rows = []
    for p in pairs:
        row = {"name": p["name"], "expected": p.get("expected"),
               "actual": p.get("actual"), "tolerance": p.get("tolerance"),
               "delta": None, "status": "not-run", "detail": ""}
        if p.get("expected") is None:
            row["detail"] = "no expected value (measurement missing)"
        elif p.get("actual") is None:
            row["detail"] = "no actual value (nothing built yet?)"
        elif p.get("tolerance") is None:
            row["detail"] = "no tolerance configured"
        else:
            row["delta"] = round(abs(float(p["actual"]) - float(p["expected"])), 6)
            row["status"] = "pass" if row["delta"] <= float(p["tolerance"]) else "fail"
        rows.append(row)
    return rows


def worst_instance(rows: list):
    """The row with the largest delta/tolerance ratio among judged rows.

    This is THE acceptance number: a build passes on its worst dimension,
    not its average one. None when no row was judged.
    """
    judged = [r for r in rows if r.get("delta") is not None
              and r.get("tolerance")]
    if not judged:
        return None
    return max(judged, key=lambda r: r["delta"] / float(r["tolerance"]))


def overall_verdict(check_groups: list) -> str:
    """Combine groups of checks into one verdict.

    check_groups: list of lists of rows/dicts each carrying "status".
    Any "fail" anywhere -> "fail". Else any "not-run" -> "incomplete".
    Else "pass". An empty group counts as not-run (it was required and
    produced nothing).
    """
    saw_not_run = False
    for group in check_groups:
        if not group:
            saw_not_run = True
            continue
        for row in group:
            if row.get("status") == "fail":
                return "fail"
            if row.get("status") == "not-run":
                saw_not_run = True
    return "incomplete" if saw_not_run else "pass"


_VERDICT_BANNER = {
    "pass": "PASS — every check that ran is within tolerance.",
    "fail": "FAIL — at least one check is outside tolerance. See the worst "
            "instances below; fix those first.",
    "incomplete": "INCOMPLETE — nothing failed, but at least one required "
                  "check did not run. This is not a pass.",
}


def render_report_markdown(title: str, verdict: str, meta_lines: list,
                           dimension_rows: list, sections: list) -> str:
    """Render the verification report (Markdown).

    sections: [{"heading", "status", "lines": [str]}] for the non-dimension
    checks (geometry, deviation, ...) — the app words them; the framework
    only places them and stamps each with its status.
    """
    out = [f"# {title}", ""]
    out += list(meta_lines) + [""]
    out += [f"**Verdict: {verdict.upper()}** — {_VERDICT_BANNER[verdict]}", ""]

    out += ["## Dimension re-check", ""]
    if dimension_rows:
        out += ["| Dimension | Expected | Actual | Delta | Tolerance | Result |",
                "|---|---|---|---|---|---|"]
        for r in dimension_rows:
            def _f(v):
                return "—" if v is None else f"{float(v):.3f}"
            result = {"pass": "PASS", "fail": "FAIL",
                      "not-run": "NOT RUN"}.get(r["status"], r["status"])
            if r["status"] == "not-run" and r.get("detail"):
                result += f" ({r['detail']})"
            out.append(f"| {r['name']} | {_f(r['expected'])} | "
                       f"{_f(r['actual'])} | {_f(r['delta'])} | "
                       f"{_f(r['tolerance'])} | {result} |")
        worst = worst_instance(dimension_rows)
        if worst is not None:
            ratio = worst["delta"] / float(worst["tolerance"])
            out += ["", f"Worst dimension: **{worst['name']}** — delta "
                    f"{worst['delta']:.3f} against tolerance "
                    f"{float(worst['tolerance']):.3f} ({ratio:.0%} of the "
                    "allowed error). The build is judged on this number, "
                    "not the average."]
    else:
        out.append("No dimensions were compared.")
    out.append("")

    for s in sections:
        out += [f"## {s['heading']}", "",
                f"Status: {s['status']}", ""]
        out += list(s.get("lines", [])) + [""]
    return "\n".join(out)
