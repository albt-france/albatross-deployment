"""Interactive dashboard "Deployment health & A/B results" -> docs/dashboard.html.

One self-contained HTML file (plotly.js inlined, opens offline, no server).
Sections: data intake (REAL dataset) · live deployment health (SIMULATED) · A/B results (SIMULATED).
Run: python src/build_dashboard.py   (after the analysis scripts)
"""
from __future__ import annotations

import html
import json
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

ROOT = Path(__file__).resolve().parents[1]
PUB, SIM = ROOT / "data" / "public", ROOT / "data" / "simulated"
OUT = ROOT / "docs" / "dashboard.html"
BLUE, GREY, RED, GREEN, AMBER, GRID = "#2A78D6", "#7A7870", "#D03B3B", "#1E8E5A", "#C27C0E", "#E1E0D9"
e = html.escape


def style(fig: go.Figure, height: int) -> go.Figure:
    fig.update_layout(template="plotly_white", height=height, margin=dict(l=60, r=20, t=30, b=40),
                      font=dict(family="Segoe UI, Arial, sans-serif", size=12, color="#0B0B0B"),
                      paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", hovermode="x unified",
                      legend=dict(orientation="h", y=1.08, x=0))
    fig.update_xaxes(gridcolor=GRID, zeroline=False)
    fig.update_yaxes(gridcolor=GRID, zeroline=False)
    return fig


def div(fig: go.Figure, first: bool = False) -> str:
    return fig.to_html(full_html=False, include_plotlyjs=True if first else False, default_width="100%",
                       config={"displaylogo": False, "responsive": True})


def main() -> None:
    m = json.loads((PUB / "intake" / "metrics.json").read_text())
    checks = pd.read_csv(PUB / "intake" / "checks.csv")
    daily = pd.read_csv(PUB / "intake" / "daily_volume.csv")
    h = pd.read_csv(SIM / "health_5min.csv", parse_dates=["ts"])
    truth = pd.read_csv(SIM / "incidents_truth.csv", parse_dates=["start", "end"])
    inc = pd.read_csv(SIM / "incident_log.csv")
    cov = pd.read_csv(SIM / "coverage_daily.csv")
    srm = pd.read_csv(SIM / "ab_readout" / "srm_daily.csv")
    res = pd.read_csv(SIM / "ab_readout" / "results.csv")
    nov = pd.read_csv(SIM / "ab_readout" / "novelty.csv")
    seg = pd.read_csv(SIM / "ab_readout" / "segments.csv")
    guard = pd.read_csv(SIM / "ab_readout" / "guardrails.csv")
    dec = json.loads((SIM / "ab_readout" / "decision.json").read_text())
    bcs = json.loads((SIM / "business_case" / "summary.json").read_text())

    # --- intake: daily volume
    f0 = go.Figure()
    f0.add_scatter(x=daily["day"], y=daily["raw_events"], name="raw events", line=dict(color=GREY, width=1))
    f0.add_scatter(x=daily["day"], y=daily["clean_events"], name="clean events", line=dict(color=BLUE, width=2))
    f0 = style(f0, 300)

    # --- health: 5 panels, shared x, incident bands, thresholds
    panels = [("requests_per_min", "Feed requests / min", None), ("events_per_min", "Events / min", None),
              ("latency_p95_ms", "p95 latency (ms)", 150), ("error_rate", "Error rate", 0.01),
              ("fallback_share", "Fallback share", None), ("duplicate_share", "Duplicate events share", 0.05),
              ("catalog_freshness_min", "Catalog freshness (min)", 60), ("top_client_share", "Top client share", 0.05)]
    f1 = make_subplots(rows=len(panels), cols=1, shared_xaxes=True, vertical_spacing=0.02,
                       subplot_titles=[p[1] for p in panels])
    for i, (col, label, thr) in enumerate(panels, start=1):
        f1.add_scatter(x=h["ts"], y=h[col], name=label, line=dict(color=BLUE, width=1), row=i, col=1, showlegend=False)
        if thr is not None:
            f1.add_hline(y=thr, line=dict(color=RED, dash="dash", width=1), row=i, col=1)
    for r in truth.itertuples():
        f1.add_vrect(x0=r.start, x1=r.end, fillcolor=RED, opacity=0.12, line_width=0)
    f1 = style(f1, 1250)
    f1.update_annotations(font_size=11, x=0, xanchor="left")
    f1.update_xaxes(rangeslider=dict(visible=True, thickness=0.04), row=len(panels), col=1)

    # --- coverage
    f2 = go.Figure()
    f2.add_scatter(x=cov["date"], y=cov["catalog_coverage"], name="catalog coverage", line=dict(color=BLUE, width=2))
    f2.add_scatter(x=cov["date"], y=cov["new_items_live_15min"], name="new listings live within 15 min", line=dict(color=GREY, width=2))
    f2 = style(f2, 280)
    f2.update_yaxes(tickformat=".0%")

    # --- A/B: SRM
    f3 = go.Figure()
    f3.add_bar(x=srm["first_day"] + 1, y=srm["share_treatment"],
               marker_color=[RED if f else BLUE for f in srm["flag"]],
               customdata=srm[["control", "treatment", "p_value"]],
               hovertemplate="day %{x}<br>treatment share %{y:.2%}<br>control %{customdata[0]:,} · treatment %{customdata[1]:,}"
                             "<br>chi-square p %{customdata[2]:.1e}<extra></extra>")
    f3.add_hline(y=0.5, line=dict(color=GREY, dash="dash"))
    f3 = style(f3, 280)
    f3.update_yaxes(range=[0.4, 0.52], tickformat=".0%", title="share in treatment")
    f3.update_xaxes(title="test day")

    # --- A/B: lifts with CI
    r = res.iloc[::-1]
    f4 = go.Figure()
    f4.add_scatter(x=r["rel_lift"], y=r["metric"], mode="markers",
                   marker=dict(size=11, color=[BLUE if lo > 0 else GREY for lo in r["rel_ci_low"]]),
                   error_x=dict(type="data", symmetric=False, array=r["rel_ci_high"] - r["rel_lift"],
                                arrayminus=r["rel_lift"] - r["rel_ci_low"], color="#52514E"),
                   hovertemplate="%{y}<br>lift %{x:+.1%}<extra></extra>", showlegend=False)
    f4.add_vline(x=0, line=dict(color=GREY))
    f4 = style(f4, 300)
    f4.update_layout(hovermode="closest", margin=dict(l=230))
    f4.update_xaxes(tickformat="+.0%", title="relative lift, treatment vs control (95 % CI)")

    # --- A/B: novelty
    f5 = go.Figure()
    f5.add_bar(x=[f"week {w}" for w in nov["week"]], y=nov["rel_lift"], marker_color=["#A9C8F0", "#A9C8F0", BLUE],
               error_y=dict(type="data", symmetric=False, array=nov["rel_ci_high"] - nov["rel_lift"],
                            arrayminus=nov["rel_lift"] - nov["rel_ci_low"]),
               hovertemplate="%{x}: %{y:+.1%}<extra></extra>")
    f5 = style(f5, 280)
    f5.update_yaxes(tickformat="+.0%", title="feed clicks lift")

    # --- tables
    def table(df: pd.DataFrame, fmt: dict) -> str:
        head = "".join(f"<th>{e(c)}</th>" for c in df.columns)
        body = "".join("<tr>" + "".join(f"<td>{e(fmt.get(c, str)(v))}</td>" for c, v in row.items()) + "</tr>"
                       for _, row in df.iterrows())
        return f"<table><tr>{head}</tr>{body}</table>"

    inc_t = table(inc[["alert_at", "severity", "injected_incident", "minutes_from_true_start", "owner", "action"]]
                  .rename(columns={"alert_at": "alert", "injected_incident": "incident", "minutes_from_true_start": "delay (min)"}), {})
    chk_t = table(checks[checks.status != "OK"][["status", "label", "affected", "rate", "recommendation"]],
                  {"affected": lambda v: f"{int(v):,}", "rate": lambda v: f"{v:.1%}"})
    seg_t = table(seg[["dimension", "segment", "metric", "rel_lift", "rel_ci_low", "rel_ci_high", "p_holm"]],
                  {"rel_lift": lambda v: f"{v:+.1%}", "rel_ci_low": lambda v: f"{v:+.1%}", "rel_ci_high": lambda v: f"{v:+.1%}",
                   "p_holm": lambda v: f"{v:.3f}"})
    g_t = table(guard, {"control": lambda v: f"{v:.3f}", "treatment": lambda v: f"{v:.3f}", "abs_diff": lambda v: f"{v:+.3f}",
                        "ci_high": lambda v: f"{v:+.3f}"})

    kpis = [("REAL DATASET", f"{m['verdict'].capitalize()}", f"readiness score {int(m['score'])}/100"),
            ("SIMULATED", f"{len(set(inc.injected_incident) - {'false alarm'})} / {len(truth)}", "injected incidents detected"),
            ("SIMULATED", f"{dec['primary_rel_lift']:+.1%}", f"feed clicks per visitor (week 3: {dec['week3_lift']:+.1%})"),
            ("SIMULATED", f"{dec['conversion_rel_lift']:+.1%}", f"conversion [{dec['conversion_ci'][0]:+.1%}, {dec['conversion_ci'][1]:+.1%}] · break-even {bcs['break_even_lift']:+.1%}")]
    kpi_html = "".join(f"<div class='card kpi'><div class='lab'>{e(t)}</div><div class='val'>{e(v)}</div><div class='txt'>{e(x)}</div></div>"
                       for t, v, x in kpis)

    page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Deployment health and A/B results</title>
<style>
body{{font-family:'Segoe UI',Arial,sans-serif;background:#F4F4F2;color:#0B0B0B;margin:0;padding:20px}}
.wrap{{max-width:1240px;margin:0 auto}} h1{{font-size:24px;margin:0}} h2{{font-size:18px;margin:26px 0 8px}}
.sub{{color:#52514E;font-size:13px;margin:4px 0 14px}} .tag{{font-size:10px;font-weight:700;color:#C27C0E;border:1px solid #e8c98f;border-radius:4px;padding:2px 7px;margin-left:8px;vertical-align:middle}}
.tag.real{{color:#1E8E5A;border-color:#9fd4b9}}
.card{{background:#FCFCFB;border:1px solid #E1E0D9;border-radius:8px;padding:12px 16px;margin-bottom:12px;overflow-x:auto}}
.kpis{{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px}}
.kpi .lab{{font-size:10px;font-weight:700;color:#52514E}} .kpi .val{{font-size:28px;font-weight:700;margin:4px 0}} .kpi .txt{{font-size:12px;color:#52514E}}
.two{{display:grid;grid-template-columns:repeat(auto-fit,minmax(420px,1fr));gap:12px}}
.two>.card,.kpis>.card{{min-width:0}}
table{{border-collapse:collapse;width:100%;font-size:12px}} th,td{{text-align:left;padding:5px 7px;border-bottom:1px solid #E1E0D9;vertical-align:top}}
th{{color:#52514E}} h3{{font-size:14px;margin:0 0 6px}} .foot{{font-size:11px;color:#7A7870;margin-top:20px}}
</style></head><body><div class="wrap">
<h1>Deployment health &amp; A/B results</h1>
<div class="sub">Albatross 7-week evaluation playbook, run on a public dataset. Intake = REAL dataset (RetailRocket). Weeks 5-7 = SIMULATED (seed 42).
Decision: <b>{e(dec['decision'].lower())}</b>, with a 5 % holdout to confirm revenue.</div>
<div class="kpis">{kpi_html}</div>

<h2>Weeks 1-2 · Data intake <span class="tag real">REAL DATASET</span></h2>
<div class="two"><div class="card"><h3>Daily events, raw vs after filtering rules</h3>{div(f0, first=True)}</div>
<div class="card"><h3>Checks that need action</h3>{chk_t}</div></div>

<h2>Weeks 5-7 · Live deployment health <span class="tag">SIMULATED</span></h2>
<div class="card"><h3>5-minute monitoring series · red bands = injected incidents · dashed = alert thresholds · drag the slider to zoom</h3>{div(f1)}</div>
<div class="two"><div class="card"><h3>Incident log (detected by src/health_monitor.py)</h3>{inc_t}</div>
<div class="card"><h3>Catalog coverage and freshness, daily</h3>{div(f2)}</div></div>

<h2>A/B test results <span class="tag">SIMULATED</span></h2>
<div class="two"><div class="card"><h3>Sample-ratio check by day (day {dec['srm_bad_days'][0]} excluded from both arms)</h3>{div(f3)}</div>
<div class="card"><h3>Effects with 95 % confidence intervals</h3>{div(f4)}</div></div>
<div class="two"><div class="card"><h3>Novelty: lift on feed clicks by week</h3>{div(f5)}</div>
<div class="card"><h3>Guardrails</h3>{g_t}<h3 style="margin-top:12px">Segments (Holm-adjusted p)</h3>{seg_t}</div></div>
<div class="foot">Independent case study based on public data · not affiliated with or endorsed by Albatross AI · RetailRocket dataset CC BY-NC-SA 4.0 ·
simulated data and assumptions: data/ASSUMPTIONS.md · Albatross facts collected 2026-11-11: data/SOURCES.md</div>
</div>
<script>window.addEventListener('load',function(){{document.querySelectorAll('.plotly-graph-div').forEach(function(d){{Plotly.Plots.resize(d);}});}});</script>
</body></html>"""
    OUT.write_text(page, encoding="utf-8")
    print(f"dashboard -> {OUT.relative_to(ROOT)} ({OUT.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
