"""Render the intake report + Readiness scorecard as Markdown or a self-contained HTML page."""
from __future__ import annotations

import html
from datetime import datetime, timezone

import pandas as pd

STATUS_COLOR = {"OK": "#1E8E5A", "WARNING": "#C27C0E", "BLOCKER": "#D03B3B",
                "PASS": "#1E8E5A", "CONDITION": "#C27C0E", "FAIL": "#D03B3B"}
VERDICT_COLOR = {"GO": "#1E8E5A", "GO WITH CONDITIONS": "#C27C0E", "NOT YET": "#D03B3B"}


def _fmt_int(x) -> str:
    return f"{int(x):,}"


def to_markdown(name: str, checks: pd.DataFrame, waterfall: pd.DataFrame | None, result: dict | None) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    out = [f"# Data intake report: {name}", "", f"_Generated {now} by the adequacy toolkit._", ""]
    counts = checks["status"].value_counts()
    out += [f"**Checks:** {counts.get('OK', 0)} OK · {counts.get('WARNING', 0)} warning · "
            f"{counts.get('BLOCKER', 0)} blocking", ""]
    if result:
        out += [f"## Readiness: **{result['verdict']}** (score {result['score']}/100)", ""]
    out += ["## 1. Intake checks", "", "| Status | Check | Rows affected | Share | Detail | Recommendation |",
            "|---|---|---:|---:|---|---|"]
    for _, r in checks.iterrows():
        detail = str(r["detail"])[:160].replace("|", "/")
        out.append(f"| {r['status']} | {r['label']} | {_fmt_int(r['affected'])} | {r['rate']:.2%} | {detail} | {r['recommendation']} |")
    if waterfall is not None:
        out += ["", "## 2. Filtering rules and their effect", "", "| Step | Rows removed | Share removed | Rows after |",
                "|---|---:|---:|---:|"]
        for _, r in waterfall.iterrows():
            out.append(f"| {r['step']} | {_fmt_int(r['removed'])} | {r['share_removed']:.2%} | {_fmt_int(r['rows_after'])} |")
    if result:
        out += ["", "## 3. Readiness scorecard", "", "| Grade | Criterion | Value | Threshold | Critical | Why it matters |",
                "|---|---|---:|---|---|---|"]
        for _, r in result["scorecard"].iterrows():
            out.append(f"| {r['grade']} | {r['criterion']} | {r['value']} | {r['threshold']} | "
                       f"{'yes' if r['critical'] else 'no'} | {r['why_it_matters']} |")
        out += ["", "## 4. Message to the customer", "", "```text", result["message"].replace("**", ""), "```"]
    return "\n".join(out) + "\n"


def to_html(name: str, checks: pd.DataFrame, waterfall: pd.DataFrame | None, result: dict | None) -> str:
    e = html.escape
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    pill = lambda s: f'<span class="pill" style="background:{STATUS_COLOR.get(s, "#888")}">{e(s)}</span>'
    parts = [f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Intake report</title>
<style>
body{{font-family:'Segoe UI',Arial,sans-serif;background:#F4F4F2;color:#0B0B0B;margin:0;padding:24px}}
.card{{background:#FCFCFB;border:1px solid #E1E0D9;border-radius:8px;padding:18px 22px;margin:0 auto 16px;max-width:1100px}}
h1{{font-size:24px;margin:0 0 4px}} h2{{font-size:17px;margin:0 0 10px}} .sub{{color:#52514E;font-size:13px}}
table{{border-collapse:collapse;width:100%;font-size:13px}} th,td{{text-align:left;padding:6px 8px;border-bottom:1px solid #E1E0D9;vertical-align:top}}
th{{color:#52514E;font-weight:600}} td.n{{text-align:right;font-variant-numeric:tabular-nums}}
.pill{{color:#fff;border-radius:10px;padding:1px 8px;font-size:11px;font-weight:600;white-space:nowrap}}
.verdict{{font-size:28px;font-weight:700}} pre{{white-space:pre-wrap;font-family:inherit;font-size:13px;background:#F4F4F2;padding:12px;border-radius:6px}}
</style></head><body>
<div class="card"><h1>Data intake report: {e(name)}</h1><div class="sub">Generated {now} by the adequacy toolkit.</div></div>"""]
    if result:
        c = VERDICT_COLOR[result["verdict"]]
        parts.append(f'<div class="card"><h2>Readiness</h2><div class="verdict" style="color:{c}">{e(result["verdict"])}</div>'
                     f'<div class="sub">Score {result["score"]}/100 · thresholds listed in the scorecard below</div></div>')
    rows = "".join(
        f"<tr><td>{pill(r['status'])}</td><td>{e(r['label'])}</td><td class='n'>{_fmt_int(r['affected'])}</td>"
        f"<td class='n'>{r['rate']:.2%}</td><td>{e(str(r['detail'])[:200])}</td><td>{e(r['recommendation'])}</td></tr>"
        for _, r in checks.iterrows())
    parts.append(f'<div class="card"><h2>1. Intake checks</h2><table><tr><th>Status</th><th>Check</th><th>Rows</th>'
                 f'<th>Share</th><th>Detail</th><th>Recommendation</th></tr>{rows}</table></div>')
    if waterfall is not None:
        rows = "".join(f"<tr><td>{e(r['step'])}</td><td class='n'>{_fmt_int(r['removed'])}</td>"
                       f"<td class='n'>{r['share_removed']:.2%}</td><td class='n'>{_fmt_int(r['rows_after'])}</td></tr>"
                       for _, r in waterfall.iterrows())
        parts.append(f'<div class="card"><h2>2. Filtering rules and their effect</h2><table><tr><th>Step</th>'
                     f'<th>Removed</th><th>Share</th><th>Rows after</th></tr>{rows}</table></div>')
    if result:
        rows = "".join(f"<tr><td>{pill(r['grade'])}</td><td>{e(r['criterion'])}</td><td class='n'>{e(r['value'])}</td>"
                       f"<td>{e(r['threshold'])}</td><td>{'yes' if r['critical'] else 'no'}</td><td>{e(r['why_it_matters'])}</td></tr>"
                       for _, r in result["scorecard"].iterrows())
        parts.append(f'<div class="card"><h2>3. Readiness scorecard</h2><table><tr><th>Grade</th><th>Criterion</th>'
                     f'<th>Value</th><th>Threshold</th><th>Critical</th><th>Why it matters</th></tr>{rows}</table></div>')
        parts.append(f'<div class="card"><h2>4. Message to the customer</h2><pre>{e(result["message"].replace("**", ""))}</pre></div>')
    parts.append("</body></html>")
    return "\n".join(parts)
