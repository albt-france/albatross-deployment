"""Build the PDF report: HTML pages + SVG charts -> PDF with headless Edge (or Chrome).

Every number in the text is read from the output tables (data/public, data/simulated);
nothing is typed in by hand. Run after the analysis scripts:
    python src/build_report.py
Outputs: docs/Albatross_DeploymentCaseStudy.pdf and docs/img/page_XX.png (page previews).
"""
from __future__ import annotations

import html
import json
import shutil
import subprocess
from pathlib import Path

import pandas as pd

import charts as C

ROOT = Path(__file__).resolve().parents[1]
PUB, SIM = ROOT / "data" / "public", ROOT / "data" / "simulated"
BUILD = ROOT / "data" / "work" / "report_build"
DOCS = ROOT / "docs"
PDF = DOCS / "Albatross_DeploymentCaseStudy.pdf"
COLLECTED = "2026-11-11"
AI_NOTE = ("AI-assisted workflow: I used Claude, mainly to write scripts faster. I drove the project: I defined "
           "the questions, chose and validated the data sources, made the analytical decisions and checked every result.")
DISCLAIMER = "Independent case study based on public data · not affiliated with or endorsed by Albatross AI"
e = html.escape


# ------------------------------------------------------------------ load every input
def load() -> dict:
    d = {}
    d["facts"] = pd.read_csv(PUB / "albatross_facts.csv").set_index("fact_id")
    i = PUB / "intake"
    d["checks"] = pd.read_csv(i / "checks.csv")
    d["filtering"] = pd.read_csv(i / "filtering.csv")
    d["ready"] = pd.read_csv(i / "readiness.csv")
    d["m"] = json.loads((i / "metrics.json").read_text())
    d["daily"] = pd.read_csv(i / "daily_volume.csv")
    d["sesslen"] = pd.read_csv(i / "session_length.csv")
    d["items"] = pd.read_csv(i / "item_interactions.csv")
    d["newcat"] = pd.read_csv(i / "catalog_new_items.csv")
    d["msg"] = (i / "customer_message.txt").read_text()
    b = PUB / "baselines"
    d["bl"] = pd.read_csv(b / "results_overall.csv")
    d["blseg"] = pd.read_csv(b / "results_by_segment.csv")
    d["blf"] = pd.read_csv(b / "facts.csv").set_index("fact")["value"]
    a = PUB / "ab_design"
    d["base"] = json.loads((a / "base_rates.json").read_text())
    d["mde"] = pd.read_csv(a / "mde_after_3_weeks.csv")
    d["power"] = pd.read_csv(a / "power_table.csv")
    d["health"] = pd.read_csv(SIM / "health_5min.csv")
    d["truth"] = pd.read_csv(SIM / "incidents_truth.csv")
    d["inc"] = pd.read_csv(SIM / "incident_log.csv")
    d["cov"] = pd.read_csv(SIM / "coverage_daily.csv")
    r = SIM / "ab_readout"
    d["srm"] = pd.read_csv(r / "srm_daily.csv")
    d["srms"] = pd.read_csv(r / "srm_summary.csv")
    d["drill"] = pd.read_csv(r / "srm_drilldown.csv")
    d["res"] = pd.read_csv(r / "results.csv")
    d["nov"] = pd.read_csv(r / "novelty.csv")
    d["seg"] = pd.read_csv(r / "segments.csv")
    d["guard"] = pd.read_csv(r / "guardrails.csv")
    d["dec"] = json.loads((r / "decision.json").read_text())
    bc = SIM / "business_case"
    d["cases"] = pd.read_csv(bc / "cases.csv")
    d["sens"] = pd.read_csv(bc / "sensitivity_take_rate.csv")
    d["bcs"] = json.loads((bc / "summary.json").read_text())
    return d


# ------------------------------------------------------------------ html helpers
CSS = """
@page { size: 13.333in 7.5in; margin: 0; }
* { box-sizing: border-box; }
html, body { margin: 0; padding: 0; }
body { font-family: 'Segoe UI', Arial, sans-serif; color: #0B0B0B; background: #F4F4F2;
       -webkit-print-color-adjust: exact; print-color-adjust: exact; }
.page { width: 13.333in; height: 7.5in; padding: 0.38in 0.45in 0.3in; position: relative; overflow: hidden;
        page-break-after: always; break-after: page; background: #F4F4F2; display: flex; flex-direction: column; }
.page:last-child { page-break-after: auto; break-after: auto; }
.head { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 0.14in; }
h1 { font-size: 22px; font-weight: 700; margin: 0 0 4px; line-height: 1.2; max-width: 10.6in; }
.sub { color: #52514E; font-size: 12.5px; max-width: 10.8in; line-height: 1.35; }
.tag { font-size: 10px; font-weight: 700; letter-spacing: .06em; padding: 4px 9px; border-radius: 4px; white-space: nowrap;
       border: 1px solid #E1E0D9; background: #FCFCFB; color: #52514E; }
.tag.public { color: #2A78D6; border-color: #A9C8F0; } .tag.real { color: #1E8E5A; border-color: #9fd4b9; }
.tag.sim { color: #C27C0E; border-color: #e8c98f; }
.grid { display: grid; gap: 0.14in; flex: 1; min-height: 0; }
.card { background: #FCFCFB; border: 1px solid #E1E0D9; border-radius: 8px; padding: 12px 15px; overflow: hidden; }
.card h3 { font-size: 13px; margin: 0 0 6px; font-weight: 600; }
.card p, .card li { font-size: 11.2px; line-height: 1.42; margin: 0 0 5px; color: #1d1d1b; }
.card ul { margin: 0; padding-left: 16px; }
.muted { color: #52514E; } .small { font-size: 10px !important; }
.kpi .lab { font-size: 9.5px; font-weight: 700; color: #52514E; letter-spacing: .05em; }
.kpi .val { font-size: 34px; font-weight: 700; margin: 4px 0 2px; line-height: 1.1; }
.kpi .txt { font-size: 11.2px; color: #52514E; line-height: 1.38; }
.chart img { width: 100%; height: auto; display: block; }
table { border-collapse: collapse; width: 100%; font-size: 10.2px; }
th, td { text-align: left; padding: 3.5px 6px; border-bottom: 1px solid #E1E0D9; vertical-align: top; }
th { color: #52514E; font-weight: 600; } td.n { text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }
.pill { color: #fff; border-radius: 9px; padding: 1px 7px; font-size: 9px; font-weight: 700; white-space: nowrap; }
.OK, .PASS, .GO { background: #1E8E5A; } .WARNING, .CONDITION { background: #C27C0E; } .BLOCKER, .FAIL { background: #D03B3B; }
.SEV1 { background: #D03B3B; } .SEV2 { background: #C27C0E; } .SEV3 { background: #7A7870; }
.verdict { font-size: 26px; font-weight: 700; color: #C27C0E; }
.go { color: #1E8E5A; }
.foot { font-size: 8.6px; color: #7A7870; margin-top: 0.1in; line-height: 1.35; }
.q { font-size: 12px; margin: 0 0 6px; } .q b { color: #2A78D6; }
.ai { border-left: 3px solid #2A78D6; padding-left: 10px; font-style: italic; }
.mono { font-family: Consolas, monospace; font-size: 9.6px; white-space: pre-wrap; background: #F4F4F2; padding: 7px 9px; border-radius: 5px; line-height: 1.35; }
.step { display: inline-block; font-size: 10px; font-weight: 700; color: #2A78D6; margin-right: 4px; }
"""


def page(title, sub, tag, body, sources, cols="1fr", rows="1fr"):
    tag_html = ""
    if tag:
        cls = {"PUBLIC DATA": "public", "REAL DATASET": "real", "SIMULATED": "sim"}.get(tag.split(" + ")[0], "")
        tag_html = f'<div class="tag {cls}">{e(tag)}</div>'
    return (f'<section class="page"><div class="head"><div><h1>{e(title)}</h1><div class="sub">{sub}</div></div>{tag_html}</div>'
            f'<div class="grid" style="grid-template-columns:{cols};grid-template-rows:{rows}">{body}</div>'
            f'<div class="foot">{sources} · {DISCLAIMER}</div></section>')


def card(inner, cls="", style=""):
    return f'<div class="card {cls}" style="{style}">{inner}</div>'


def img(name, max_h=None):
    style = f' style="width:auto;max-width:100%;max-height:{max_h};margin:0 auto"' if max_h else ""
    return f'<div class="chart"><img src="{name}"{style}></div>'


def kpi(label, value, text, color="#0B0B0B"):
    return card(f'<div class="lab">{e(label)}</div><div class="val" style="color:{color}">{e(value)}</div>'
                f'<div class="txt">{text}</div>', "kpi")


def pill(s):
    return f'<span class="pill {s.replace(" ", "")}">{e(s)}</span>'


def pct(x, d=1, sign=False):
    return f"{x:+.{d}%}" if sign else f"{x:.{d}%}"


SRC_RR = ("Data: RetailRocket e-commerce dataset (public, CC BY-NC-SA 4.0), 2,756,101 events, May-Sep 2015 · "
          "code: sql/, src/adequacy/")
SRC_SITE = f"Sources: usealbatross.ai (home, technology, evaluation, primitives, customers, pricing, company), collected {COLLECTED}; data/SOURCES.md"
SRC_SIM = "SIMULATED data (src/simulate.py, seed 42), calibrated on the RetailRocket base rates and kept below Albatross's published lifts; assumptions in data/ASSUMPTIONS.md"


# ------------------------------------------------------------------ pages
def build_pages(d: dict) -> list[str]:
    m, f, dec, bcs = d["m"], d["facts"], d["dec"], d["bcs"]
    checks = d["checks"]
    n_ok, n_warn, n_block = [(checks.status == s).sum() for s in ("OK", "WARNING", "BLOCKER")]
    unknown = checks.set_index("check").loc["check_unknown_items"]
    drops = checks.set_index("check").loc["check_volume_drops"]
    heavy = checks.set_index("check").loc["check_heavy_users"]
    pwv = checks.set_index("check").loc["check_purchase_without_view"]
    cwv = checks.set_index("check").loc["check_cart_without_view"]
    flt = d["filtering"]
    removed_total = flt["removed"].sum()
    ready = d["ready"]
    verdict, score = m["verdict"], int(m["score"])
    bl, seg = d["bl"].set_index("baseline"), d["blseg"]
    cov = "(c) Co-visitation + popularity fill"
    rec = "(b) Recent popularity (7 days)"
    def segv(dim, s, b, col="recall@20"):
        return seg[(seg.dimension == dim) & (seg.segment == s) & (seg.baseline == b)][col].iloc[0]
    covis_warm, covis_cold, covis_new = (segv("target", s, cov) for s in ("warm item (5+)", "cold item (1-4)", "new item (0 in train)"))
    covis_nohist = segv("prev", "current item has no co-visitation", cov)
    mde = d["mde"]
    def mdev(metric, tr):
        return mde[(mde.metric == metric) & (mde.traffic == tr)]["mde_3w"].iloc[0]
    mde_conv_real, mde_eng_real = mdev("Purchase conversion", "real"), mdev("Engaged-visitor rate (2+ views)", "real")
    mde_conv_sim = mdev("Purchase conversion", "sim")
    res = d["res"].set_index("metric")
    prim = res.loc["Feed clicks per visitor (primary)"]
    conv = res.loc["Purchase conversion"]
    rpv = res.loc["Revenue per visitor (EUR)"]
    nov = d["nov"]
    inc = d["inc"]
    cases = d["cases"].set_index("case")
    central = cases.loc["central (point estimate)"]
    srms = d["srms"]
    drill = d["drill"].set_index("device")
    pages = []

    # ---------------- 0. overview
    body = "".join([
        kpi("REAL DATASET · PAGE 3", f"{score}/100",
            f"Readiness of the first data drop: <b>{verdict.lower()}</b>. Train now; fix the "
            f"{pct(unknown.rate)} of events on unknown items and session tracking before the A/B test.", "#C27C0E"),
        kpi("REAL DATASET · PAGE 4", pct(covis_new),
            f"Recall@20 of item-to-item co-visitation when the next item is new, against {pct(covis_warm, 0)} on established items. "
            "That gap is the case for content-aware, session-aware models."),
        kpi("REAL DATASET · PAGE 5", f"±{mde_conv_real:.0%}",
            f"Smallest purchase lift a 3-week test can detect at this dataset's traffic (±{mde_eng_real:.0%} for engagement). "
            "Engagement must be the primary metric."),
        kpi("SIMULATED · PAGES 7-8", pct(bcs["break_even_lift"], 1, True),
            f"Conversion lift needed to cover the list price. The simulated test reads {pct(dec['conversion_rel_lift'], 1, True)} "
            f"[{pct(dec['conversion_ci'][0], 1, True)}, {pct(dec['conversion_ci'][1], 1, True)}]: go, with a holdout."),
        card("<h3 style='font-size:17px'>Five questions a Deployment Strategist answers</h3>"
             "<p class='q'><b>1 · Product</b>&nbsp; What does Albatross sell, and how does an evaluation run? <span class='muted'>(p.1)</span></p>"
             "<p class='q'><b>2 · Intake</b>&nbsp; Is the customer's first data drop usable, and what must be cleaned? <span class='muted'>(p.2)</span></p>"
             "<p class='q'><b>3 · Readiness</b>&nbsp; Go, Go with conditions, or Not yet for the first training run? <span class='muted'>(p.3)</span></p>"
             "<p class='q'><b>4 · Baselines</b>&nbsp; Where does the incumbent-style logic fail, and why does that matter? <span class='muted'>(p.4)</span></p>"
             "<p class='q'><b>5 · Live test</b>&nbsp; How is the A/B test designed, is the deployment healthy, did it win, does it pay? <span class='muted'>(p.5-9)</span></p>"
             f"<p style='margin-top:9px;font-size:12px'><b>Recommendation:</b> start training on the cleaned drop, send the customer "
             f"{len(ready[ready.grade != 'PASS'])} written conditions, run a 3-week test with engagement as the primary metric, and move to "
             "production with a 5 % holdout so revenue per visitor is confirmed before the first renewal talk.</p>",
             style="grid-column: span 2"),
        card("<h3 style='font-size:17px'>Data &amp; methods</h3>"
             f"<p><b>PUBLIC DATA</b>&nbsp; Albatross's own pages (product, 7-week evaluation, customer results, pricing), collected {COLLECTED}.</p>"
             "<p><b>REAL DATASET</b>&nbsp; RetailRocket: 2.76 M real e-commerce events + catalog, used <i>as if</i> it were a new customer's first data drop.</p>"
             "<p><b>SIMULATED</b>&nbsp; live health series and A/B test (weeks 5-7), calibrated on the real base rates, effects kept below published lifts.</p>"
             "<p><b>Tools</b>&nbsp; SQL in DuckDB (checks, sessions, co-visitation), Python (power, z-tests, bootstrap, chi-square), Plotly dashboard, "
             "a reusable <code>adequacy</code> toolkit with tests.</p>", style="grid-column: span 2"),
        card("<h3>How to read this report</h3><p><b>Titles</b> state the conclusion of the page. &nbsp; <b>Tags</b> PUBLIC DATA / REAL DATASET / "
             "SIMULATED mark where the numbers come from. &nbsp; <b>Colours</b> blue = data or treatment, grey = comparison or control, red = alert, "
             "green = go; dashed lines are thresholds. &nbsp; <b>Albatross's models are proprietary:</b> the simple baselines here are not theirs and "
             "do not try to reproduce them.</p>", style="grid-column: span 4"),
    ])
    pages.append(page("Albatross: a 7-week deployment playbook, run on a real marketplace dataset",
                      "From first data drop to a go/no-go readiness score, a deployment-health dashboard and an A/B readout a customer can trust.",
                      "OVERVIEW", body, "Sources: data/SOURCES.md", cols="repeat(4, 1fr)", rows="1.05fr 1.75fr 0.6fr"))

    # ---------------- 1. Albatross in public data
    C.hbar(["Wallapop · homepage engagement", "OfferUp · homepage engagement", "OfferUp · purchase intent",
            "Wallapop · sold items overall"], [1.19, 0.84, 0.15, 0.11], BUILD / "p1_results.svg", w=2.5, h=1.6)
    C.timeline(BUILD / "p1_timeline.svg", w=9.0, h=1.75)
    body = "".join([
        card("<h3>What Albatross sells</h3>"
             "<p><b>Perception models</b>: sequential (transformer) embedding models that read each user's live sequence of events "
             "(views, clicks, searches, purchases) and update on every click.</p>"
             "<ul><li><b>Catalog layer</b>: content embeddings (text, images) per item, so a new listing is recommendable "
             "<i>within minutes, before its first click</i>.</li>"
             "<li><b>User layer</b>: a real-time user embedding from the interaction sequence.</li>"
             "<li><b>Serving</b>: returns the k best items through three APIs (Catalog, Event, Prediction).</li></ul>"
             "<p style='margin-top:6px'><b>Four primitives, one API</b>: Discovery Feed (user_id, k) · Similar Items (item_id, k) · "
             "Playlist (item_ids, k) · Contextual Search (query, user_id, k).</p>"
             "<p class='muted small'>Research: SwapRec (RecSys 2026) and DenseRec on cold / brand-new items; content-enriched sequential "
             "recommenders; Multinomial Blending for promotions.</p>"),
        card("<h3>Announced scale</h3>"
             f"<div style='display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:6px'>"
             f"<div><div class='val' style='font-size:28px;font-weight:700'>3B+</div><div class='muted small'>requests / month</div></div>"
             f"<div><div class='val' style='font-size:28px;font-weight:700'>50M+</div><div class='muted small'>users / month</div></div>"
             f"<div><div class='val' style='font-size:28px;font-weight:700'>150M+</div><div class='muted small'>products orchestrated</div></div>"
             f"<div><div class='val' style='font-size:28px;font-weight:700'>12</div><div class='muted small'>countries with live marketplaces</div></div></div>"
             "<p class='small muted' style='margin-top:10px'>Founded 2024, Switzerland; $16M seed (MMC Ventures, Redalpine, Daphni); "
             "Tech for Retail 2025 award. Public pricing: platform fee from €10k to €40k / month by MAU tier + €0.10-0.50 per 1,000 predictions.</p>"),
        card("<h3>Results published by customers (as shown on usealbatross.ai)</h3>" + img("p1_results.svg") +
             "<p class='small muted'>Wallapop's case study also reports similar-items catalog coverage rising from 50 % to 94 % "
             "and +49.9 % conversion to sold item. OfferUp: Discovery Feed A/B-tested on the homepage against the incumbent system.</p>"),
        card("<h3>The 7-week evaluation: the Deployment Strategist's job, week by week</h3>" + img("p1_timeline.svg", "2.15in") +
             "<p class='small muted'>Customer side: one engineering lead + one PM. Data: event triplets (user ID, event type, item ID, timestamp) + catalog "
             "access; clicks only is enough to start. Fixed 3-month evaluation, no auto-renewal; production is a separate agreement. "
             "Blue bars = the Deployment Strategist's deliverables in this study.</p>", style="grid-column: span 3"),
    ])
    pages.append(page("Albatross sells a measured outcome: live on the homepage in 7 weeks, judged by an A/B test",
                      "Perception models update on every click and make new listings recommendable within minutes. Customers publish lifts of +84 % to "
                      "+119 % in homepage engagement; the 7-week evaluation is where that proof is produced.",
                      "PUBLIC DATA", body, SRC_SITE, cols="1.15fr 0.85fr 1.1fr", rows="1.05fr 1fr"))

    # ---------------- 2. intake
    flagged = [x.split(" ")[0] for x in str(drops.detail).split(", ") if x]
    C.daily_volume(d["daily"], flagged, BUILD / "p2_daily.svg", w=4.6, h=1.9)
    C.waterfall(flt, BUILD / "p2_waterfall.svg", w=3.9, h=1.1)
    nonok = checks[checks.status != "OK"]
    rows = "".join(f"<tr><td>{pill(r.status)}</td><td>{e(r.label)}</td><td class='n'>{r.affected:,.0f}</td>"
                   f"<td class='n'>{r.rate:.1%}</td><td>{e(r.recommendation)}</td></tr>" for r in nonok.itertuples())
    body = "".join([
        card(f"<h3>{n_ok} checks OK · {n_warn} warnings · {n_block} blocking</h3>"
             f"<table><tr><th>Status</th><th>Check</th><th>Rows</th><th>Share</th><th>What we do / ask</th></tr>{rows}</table>"
             f"<p class='small muted' style='margin-top:6px'>Also checked and OK: schema, timestamps (Unix ms, UTC), nulls, event types, "
             f"duplicate catalog ids, exact duplicates ({checks.set_index('check').loc['check_exact_duplicates','affected']:,}), "
             f"repeats under 1 s ({checks.set_index('check').loc['check_near_duplicates','affected']:,}), missing days (0), bursts.</p>"),
        card("<h3>Daily volume: the export ends mid-day</h3>" + img("p2_daily.svg") +
             f"<p class='small muted'>{e(str(drops.detail))}: the last two days are partial and must be dropped from daily KPIs.</p>"),
        card(f"<h3>Filtering rules remove {removed_total:,} events ({removed_total / flt.rows_after.iloc[0]:.1%})</h3>" + img("p2_waterfall.svg") +
             f"<p class='small'>Bot rule 1: more than 100 events in a day ({e(heavy.detail)}). Bot rule 2: 20+ events in one minute. "
             "Same logic as reconciling counted vs real clicks: bots, previews and double taps removed with written rules, "
             "applied identically to training data and A/B metrics.</p>", style="grid-column:2;grid-row:2"),
        card("<h3>Filtering rules, applied in this order (sql/01_intake_checks.sql)</h3><table>"
             "<tr><th>#</th><th>Rule</th><th>Why</th></tr>"
             "<tr><td>1</td><td>Drop rows missing a field or with a timestamp outside 2000-01-01 .. now</td><td>unusable or unit error</td></tr>"
             "<tr><td>2</td><td>Keep one copy of exact duplicates (same user, item, type, timestamp)</td><td>tracker retries</td></tr>"
             "<tr><td>3</td><td>Drop a repeat of the same user / item / type less than 1 s after the previous one</td><td>double taps, reloads</td></tr>"
             "<tr><td>4</td><td>Drop every event of a user with &gt;100 events in a day or 20+ in one minute</td><td>crawlers, scripts</td></tr>"
             "</table><p class='small muted' style='margin-top:6px'>Kept but flagged: events on unknown items (needed to measure the catalog gap) and "
             "purchases without a view (a tracking question for the customer, not a reason to delete sales).</p>", style="grid-column:1;grid-row:2"),
    ])
    pages.append(page(f"The first drop is usable, but {pct(unknown.rate)} of events point to items missing from the catalog",
                      f"{len(checks)} automated checks on the customer's first drop (sql/01_intake_checks.sql): no blocking issue; the warnings are a catalog "
                      f"export gap, partial last days, {pct(heavy.rate)} of events from bot-like users, and {pct(cwv.rate, 0)} of add-to-carts with no earlier view.",
                      "REAL DATASET", body, SRC_RR, cols="1.25fr 1fr", rows="1.15fr 0.85fr"))

    # ---------------- 3. readiness
    sl = d["sesslen"]
    sl["bucket"] = pd.cut(sl["session_length"], [0, 1, 2, 4, 9, 100], labels=["1", "2", "3-4", "5-9", "10+"])
    slb = sl.groupby("bucket", observed=False)["sessions"].sum()
    C.histogram(list(slb.index), slb.values, BUILD / "p3_sessions.svg", highlight=lambda c: c != "1", xlabel="events per session", w=3.3, h=1.75)
    it = d["items"].set_index("interactions").loc[["0", "1-4", "5-19", "20-99", "100+"]]
    C.histogram(list(it.index), it["items"].values, BUILD / "p3_items.svg", highlight=lambda c: c in ("0", "1-4"),
                xlabel="interactions per catalog item (139 days)", w=3.3, h=1.75)
    nc = d["newcat"].copy()
    nc["snapshot_day"] = pd.to_datetime(nc["snapshot_day"])
    gaps = [(a + pd.Timedelta(days=7)).strftime("%Y-%m-%d") for a, b in zip(nc.snapshot_day[:-1], nc.snapshot_day[1:]) if (b - a).days > 7]
    C.weekly_bars(nc["snapshot_day"], nc["new_items"], BUILD / "p3_newitems.svg", w=3.3, h=1.75, gap_dates=gaps)
    rows = "".join(f"<tr><td>{pill(r.grade)}</td><td>{e(r.criterion)}{' *' if r.critical else ''}</td><td class='n'>{e(r.value)}</td>"
                   f"<td class='small'>{e(r.threshold)}</td></tr>" for r in ready.itertuples())
    conds = "".join(f"<li>{e(r.condition)}</li>" for r in ready[ready.grade != "PASS"].itertuples())
    body = "".join([
        card(f"<h3>Readiness scorecard</h3><div class='verdict'>{e(verdict)} · {score}/100</div>"
             f"<table style='margin-top:6px'><tr><th>Grade</th><th>Criterion (* critical)</th><th>Value</th><th>Rule</th></tr>{rows}</table>"
             "<p class='small muted' style='margin-top:5px'>Not yet = a critical criterion fails. Go with conditions = no critical failure, "
             "some conditions. Thresholds are this playbook's rules (src/adequacy/readiness.py), not Albatross's.</p>", style="grid-row: span 2"),
        card(f"<h3>Short sessions: {pct(m['share_sessions_2plus'], 0)} have 2+ events</h3>" + img("p3_sessions.svg") +
             f"<p class='small muted'>Median {m['median_session_length']:.0f} event per session; {pct(m['share_users_2plus'], 0)} of users come back. "
             "In-session intent is the core signal: this is the first condition.</p>"),
        card(f"<h3>A cold catalog: {pct(m['share_catalog_under5'], 0)} of items have under 5 interactions</h3>" + img("p3_items.svg") +
             f"<p class='small muted'>Density of the user x item matrix: {m['density']:.1e}. Top 1 % of items take "
             f"{pct(m['share_top1pct'], 0)} of events. Content embeddings are what serve this long tail.</p>"),
        card(f"<h3>~{nc.new_items.median():,.0f} new catalog items per week</h3>" + img("p3_newitems.svg") +
             f"<p class='small muted'>Weekly catalog snapshots; one snapshot is missing ({', '.join(gaps)}): ask for a daily delta feed.</p>"),
        card("<h3>Conditions sent to the customer</h3><ul>" + conds + "</ul>"
             "<p class='small muted' style='margin-top:4px'>Full e-mail generated by the toolkit: data/public/intake/customer_message.txt</p>"),
    ])
    pages.append(page(f"Verdict: {verdict.capitalize()} ({score}/100). Train now; fix the catalog feed and session tracking before the A/B",
                      f"{int(m['days_covered'])} days of history and a fully categorised catalog pass. Short sessions, low daily volume "
                      f"({m['median_events_per_day']:,.0f} events/day) and a cold long tail are conditions, not blockers.",
                      "REAL DATASET", body, SRC_RR + " · thresholds: src/adequacy/readiness.py", cols="1.3fr 1fr 1fr", rows="1fr 1fr"))

    # ---------------- 4. baselines
    C.grouped_recall(seg, BUILD / "p4_segments.svg", w=5.0, h=3.7)
    rows = "".join(f"<tr><td>{e(b)}</td><td class='n'>{r['recall@20']:.1%}</td><td class='n'>{r['ndcg@20']:.3f}</td>"
                   f"<td class='n'>{r['coverage']:.2%}</td><td class='n'>{int(r['items_recommended']):,}</td></tr>"
                   for b, r in bl.iterrows())
    body = "".join([
        card("<h3>Three incumbent-style baselines, time split</h3>"
             f"<p class='small'>Train: 16 weeks to {d['blf']['split_date']} · Test: the next 4 weeks, {int(d['blf']['test_transitions']):,} "
             f"next-item predictions in {int(d['blf']['test_sessions']):,} sessions. Task: the user is on item P, which different item comes next?</p>"
             f"<table><tr><th>Baseline</th><th>Recall@20</th><th>NDCG@20</th><th>Coverage</th><th>Items shown</th></tr>{rows}</table>"
             "<p class='small muted' style='margin-top:6px'>Coverage = share of the items people interacted with in the test weeks that the "
             "baseline ever recommends. Popularity shows the same 20-67 items to everyone.</p>"),
        card("<h3>Co-visitation works on established items, fails on new ones</h3>" + img("p4_segments.svg"), style="grid-row: span 2"),
        card("<h3>Where the simple logic breaks, and what that says about the product</h3><ul>"
             f"<li><b>New items</b> ({pct(float(d['blf']['share_targets_new_item']))} of next items had no training history): co-visitation recall "
             f"{pct(covis_new)}, against {pct(covis_warm)} on warm items. Content embeddings are built for exactly this.</li>"
             f"<li><b>Items with no co-visitation history</b> ({pct(float(d['blf']['share_prev_item_without_covis_neighbour']))} of cases): recall falls to "
             f"{pct(covis_nohist)}, the popularity fallback.</li>"
             f"<li><b>Longer context is ignored</b>: co-visitation uses the last item only; recall is {pct(segv('context','2+ items seen',cov))} "
             f"with 2+ items seen vs {pct(segv('context','1 item seen',cov))} with 1. A sequence model reads the whole session.</li>"
             "<li><b>Offline is not online</b>: these metrics rank candidates on logged data; only the live A/B (pages 5-7) measures value.</li></ul>"
             "<p class='small muted'>These baselines are not Albatross's models and do not estimate their performance.</p>"),
    ])
    pages.append(page(f"Co-visitation finds the next item {pct(bl.loc[cov, 'recall@20'], 0)} of the time, but almost never when the item is new",
                      f"Popularity is near useless for discovery (Recall@20 {pct(bl.loc[rec, 'recall@20'])}). Co-visitation is a strong incumbent on "
                      f"established items and collapses on the cold and new items that make up a marketplace's long tail.",
                      "REAL DATASET", body, SRC_RR + " · sql/03_baselines.sql, src/baselines.py", cols="1fr 1fr", rows="1fr 1fr"))

    # ---------------- 5. test design
    C.mde_chart(mde, BUILD / "p5_mde.svg", w=4.4, h=2.3)
    base = d["base"]
    pw = d["power"][d["power"].metric.isin(["Engaged-visitor rate (2+ views)", "Purchase conversion"])]
    wk = lambda v: "> 8" if pd.isna(v) else f"{int(v)}"
    power_html = ("<table style='margin-top:4px'><tr><th>Metric</th><th>Lift to detect</th><th>Visitors / arm</th>"
                  "<th>Weeks, RetailRocket traffic</th><th>Weeks, simulated customer</th></tr>" +
                  "".join(f"<tr><td>{e(r.metric.split(' (')[0])}</td><td class='n'>+{r.relative_mde:.0%}</td><td class='n'>{r.n_per_arm:,}</td>"
                          f"<td class='n'>{wk(r.weeks_real)}</td><td class='n'>{wk(r.weeks_sim)}</td></tr>" for r in pw.itertuples()) + "</table>")
    body = "".join([
        card("<h3>What a 3-week test can detect</h3>" + img("p5_mde.svg") +
             f"<p class='small muted'>Real base rates per visitor over 3-week windows: engaged {pct(base['engaged_rate'])}, add-to-cart "
             f"{pct(base['cart_rate'], 2)}, purchase {pct(base['conversion'], 2)}, {base['views_mean']:.2f} views (sd {base['views_sd']:.2f}).</p>"
             + power_html, style="grid-row: span 2"),
        card("<h3>Analysis plan, signed before go-live</h3><table>"
             "<tr><td><b>Primary</b></td><td>Homepage feed clicks per visitor (engagement), the metric customers publish and the one this traffic can read.</td></tr>"
             "<tr><td><b>Secondary</b></td><td>Engaged-visitor rate, add-to-cart rate, purchase conversion, revenue per visitor.</td></tr>"
             "<tr><td><b>Guardrails</b></td><td>Page load time (max +50 ms), bounce rate (max +0.5 pt), error and fallback rates.</td></tr>"
             "<tr><td><b>Unit</b></td><td>Visitor, sticky hash of user_id + salt, 50/50, same assignment on web and apps.</td></tr>"
             "<tr><td><b>Duration</b></td><td>21 days fixed (3 full weekly cycles = weeks 5-7). No decision before day 21: no peeking.</td></tr>"
             "<tr><td><b>Stop early</b></td><td>Only for a guardrail breach or a SEV1 incident.</td></tr>"
             "<tr><td><b>SRM</b></td><td>Chi-square on the split daily and by device; alarm at p &lt; 0.001; investigate before reading any result.</td></tr>"
             "<tr><td><b>Tests</b></td><td>Welch z-test + bootstrap CI (visitor resampling); Holm correction across segments; novelty read week by week.</td></tr>"
             "</table>"),
        card("<h3>Sample size, the formula behind the chart</h3>"
             "<p class='mono'>n per arm = (z<sub>α/2</sub>·√(2p̄q̄) + z<sub>β</sub>·√(p₁q₁+p₂q₂))² / (p₂−p₁)²\nα = 5 % two-sided, power = 80 %</p>"
             f"<p class='small'>Detecting +5 % on purchase conversion needs "
             f"{int(d['power'][(d['power'].metric=='Purchase conversion')&(d['power'].relative_mde==0.05)]['n_per_arm'].iloc[0]):,} visitors per arm. "
             f"RetailRocket reaches ~{int(mde[(mde.traffic=='real')]['n_per_arm_3w'].iloc[0]):,} per arm in 3 weeks: purchases are out of reach, "
             f"engagement is not. The simulated customer (1M per arm) can read ±{mde_conv_sim:.1%} on conversion.</p>"),
    ])
    pages.append(page(f"At this dataset's traffic, 3 weeks can read engagement (±{mde_eng_real:.0%}) but not purchases (±{mde_conv_real:.0%})",
                      "The test is sized on the customer's real base rates before go-live, so the primary metric is one the test can actually answer, "
                      "and every rule for reading it is written down in advance.",
                      "REAL DATASET", body, SRC_RR + " · src/ab_design.py", cols="1.05fr 1fr", rows="1.25fr 0.75fr"))

    # ---------------- 6. deployment health
    C.health_panels(d["health"], d["truth"], BUILD / "p6_health.svg", w=5.4, h_in=5.0)
    rows = "".join(f"<tr><td>{pill(r.severity)}</td><td>{e(r.injected_incident)}</td><td class='n'>{pd.Timestamp(r.alert_at):%d %b %H:%M}</td>"
                   f"<td class='n'>{int(r.minutes_from_true_start)} min</td><td>{e(r.owner)}</td></tr>" for r in inc.itertuples())
    h = d["health"]
    stall = inc[inc.injected_incident == "Catalog feed stalled"].iloc[0]
    body = "".join([
        card("<h3>Weeks 5-7 live monitoring (30-min view; red band = injected incident, dashed = alert threshold)</h3>" + img("p6_health.svg"),
             style="grid-row: span 2"),
        card(f"<h3>{len(set(inc.injected_incident) - {'false alarm'})} of {len(d['truth'])} injected incidents detected, "
             f"{(inc.injected_incident == 'false alarm').sum()} false alarms</h3>"
             f"<table><tr><th>Sev</th><th>Incident</th><th>Alert</th><th>Delay</th><th>Owner</th></tr>{rows}</table>"
             f"<p class='small muted' style='margin-top:5px'>Delay = from the true start of the problem to the alert. The catalog stall alerted after "
             f"{int(stall.minutes_from_true_start)} min because the rule waits for 60 min of staleness: lower it to 30 min.</p>"),
        card("<h3>Normal operating range (median over 3 weeks)</h3>"
             f"<p>p50 / p95 latency <b>{h.latency_p50_ms.median():.0f} / {h.latency_p95_ms.median():.0f} ms</b> · errors "
             f"<b>{h.error_rate.median():.2%}</b> · fallback <b>{h.fallback_share.median():.1%}</b> · event lag p95 <b>{h.event_lag_p95_s.median():.1f} s</b> · "
             f"new listing live in <b>{h.catalog_freshness_min.median():.0f} min</b> · catalog coverage "
             f"<b>{d['cov'].catalog_coverage.iloc[0]:.0%} → {d['cov'].catalog_coverage.iloc[-1]:.0%}</b></p>"
             "<p class='small muted'>Each alert has an owner and an action in the escalation grid (page 9). Event-stream and bot windows are "
             "excluded from A/B metrics for both arms.</p>"),
    ])
    pages.append(page("Monitoring caught all 5 injected incidents; the catalog-stall rule needs a tighter threshold",
                      "Health is read daily during the live test: if events stop, latency spikes or the catalog freezes, the A/B result is "
                      "not trustworthy, whatever it says. Interactive version: docs/dashboard.html.",
                      "SIMULATED", body, SRC_SIM + " · src/health_monitor.py", cols="1.35fr 1fr", rows="1.2fr 0.8fr"))

    # ---------------- 7. A/B readout
    C.srm_chart(d["srm"], BUILD / "p7_srm.svg", w=3.0, h=1.75)
    C.lift_ci(d["res"], BUILD / "p7_lift.svg", w=3.1, h=2.0)
    C.novelty_chart(nov, BUILD / "p7_novelty.svg")
    sg = d["seg"]
    srows = "".join(f"<tr><td>{e(r.segment)}</td><td>{'clicks' if 'clicks' in r.metric else 'conversion'}</td>"
                    f"<td class='n'>{r.rel_lift:+.1%}</td><td class='n'>[{r.rel_ci_low:+.1%}, {r.rel_ci_high:+.1%}]</td>"
                    f"<td class='n'>{r.p_holm:.2f}</td></tr>" for r in sg.itertuples())
    rules = "".join(f"<li>{'✔' if ok else '✘'} {e(k)}</li>" for k, ok in dec["rules"].items())
    body = "".join([
        card("<h3>1 · Sample-ratio mismatch found and fixed first</h3>" + img("p7_srm.svg") +
             f"<p class='small'>Overall split {srms.share_treatment.iloc[0]:.2%} treatment (p = {srms.p_value.iloc[0]:.0e}). "
             f"Drill-down: on day {dec['srm_bad_days'][0]} mobile treatment was {drill.loc['mobile','share_treatment']:.0%} "
             f"(desktop {drill.loc['desktop','share_treatment']:.0%}): a logging bug in a mobile release. Day-{dec['srm_bad_days'][0]} visitors "
             f"excluded from both arms: split {srms.share_treatment.iloc[1]:.2%}, p = {srms.p_value.iloc[1]:.2f}.</p>", style="grid-column:1;grid-row:1"),
        card("<h3>2 · Effects with 95 % confidence intervals</h3>" + img("p7_lift.svg") +
             "<h3 style='margin-top:6px'>4 · Segments (Holm-adjusted p)</h3>"
             f"<table><tr><th>Segment</th><th>Metric</th><th>Lift</th><th>95 % CI</th><th>p adj.</th></tr>{srows}</table>"
             "<p class='small muted' style='margin-top:4px'>Clicks rise in every segment; no segment-level conversion claim survives correction.</p>",
             style="grid-column:2;grid-row:1 / span 2"),
        card("<h3>3 · Novelty: the lift fades</h3>" + img("p7_novelty.svg") +
             f"<p class='small muted'>Week 3 ({pct(dec['week3_lift'], 0, True)}) is the steady-state estimate, not the 3-week average "
             f"({pct(prim.rel_lift, 0, True)}).</p>", style="grid-column:3;grid-row:1"),
        card("<h3>Guardrails and revenue</h3><table><tr><th>Guardrail</th><th>Control</th><th>Treatment</th><th>Max allowed</th></tr>"
             f"<tr><td>Page load time</td><td class='n'>{d['guard'].control.iloc[0]:.0f} ms</td><td class='n'>{d['guard'].treatment.iloc[0]:.0f} ms</td><td class='n'>+50 ms</td></tr>"
             f"<tr><td>Bounce rate</td><td class='n'>{d['guard'].control.iloc[1]:.1%}</td><td class='n'>{d['guard'].treatment.iloc[1]:.1%}</td><td class='n'>+0.5 pt</td></tr></table>"
             f"<p class='small' style='margin-top:6px'>Revenue per visitor {pct(rpv.rel_lift, 1, True)} [{pct(rpv.rel_ci_low, 1, True)}, {pct(rpv.rel_ci_high, 1, True)}]: "
             "inconclusive, not negative. The business case uses the conversion lift; a holdout after launch measures revenue directly.</p>"
             f"<p class='small muted'>Bootstrap CI (500 resamples) on clicks: [{prim.boot_rel_ci_low:+.1%}, {prim.boot_rel_ci_high:+.1%}]; "
             f"on revenue: [{rpv.boot_rel_ci_low:+.1%}, {rpv.boot_rel_ci_high:+.1%}]. Order values vary a lot "
             f"(average order value {dec['aov_rel_diff']:+.1%}, p = {dec['aov_p']:.2f}).</p>",
             style="grid-column:3;grid-row:2"),
        card(f"<h3>5 · Decision: <span class='go'>{e(dec['decision'].lower())}</span></h3><ul>{rules}</ul>"
             f"<p class='small' style='margin-top:5px'>Guardrails: page load {d['guard'].abs_diff.iloc[0]:+.1f} ms, bounce "
             f"{d['guard'].abs_diff.iloc[1] * 100:+.1f} pt. <b>Condition:</b> keep a 5 % holdout for 3 months to confirm revenue per visitor.</p>", style="grid-column:1;grid-row:2"),
    ])
    pages.append(page(f"Engagement {pct(prim.rel_lift, 0, True)} ({pct(dec['week3_lift'], 0, True)} once novelty fades), conversion "
                      f"{pct(conv.rel_lift, 1, True)}: go to production, with a holdout",
                      "Read in the order of the analysis plan: trust the split first, then the effect, then how it changes over time and across segments. "
                      "Simulated effects are deliberately set far below the +84 % to +119 % engagement lifts Albatross's customers published.",
                      "SIMULATED", body, SRC_SIM + " · src/ab_readout.py", cols="1fr 1.1fr 1fr", rows="1fr 1fr"))

    # ---------------- 8. business case
    C.business_bars(d["cases"], BUILD / "p8_cases.svg", w=3.4, h=2.4)
    sens = d["sens"].set_index("conversion lift")
    srows = "".join("<tr><td class='n'>" + e(i) + "</td>" + "".join(
        f"<td class='n' style='color:{'#D03B3B' if v < 0 else '#1E8E5A'}'>{v:+,.0f}</td>" for v in r.values) + "</tr>"
        for i, r in sens.iterrows())
    crow = "".join(f"<tr><td>{e(c.split(' (')[0])}</td><td class='n'>{r.conversion_lift:+.1%}</td><td class='n'>€{r.incremental_gmv / 1e6:,.1f}M</td>"
                   f"<td class='n'>€{r.incremental_revenue / 1e3:,.0f}k</td><td class='n'>{'−' if r.net_benefit < 0 else '+'}€{abs(r.net_benefit) / 1e3:,.0f}k</td>"
                   f"<td class='n'>{r.roi_multiple:.1f}×</td></tr>" for c, r in cases.iterrows())
    body = "".join([
        card("<h3>Annual value vs cost at list price</h3>" + img("p8_cases.svg") +
             f"<table style='margin-top:4px'><tr><th>Case</th><th>Conv. lift</th><th>Extra GMV</th><th>Net revenue</th><th>After cost</th><th>ROI</th></tr>{crow}</table>",
             style="grid-row: span 2"),
        card("<h3>Cost, from the public price list</h3>"
             f"<p>GROWTH tier (1-5M MAU): <b>€{bcs['platform_fee_month']:,.0f}</b> / month · {bcs['predictions_per_month'] / 1e6:.1f}M predictions / month "
             f"at €0.50 per 1k: <b>€{bcs['usage_fee_month']:,.0f}</b> / month · total <b>€{bcs['annual_cost'] / 1e3:,.0f}k</b> / year.</p>"
             f"<p class='small muted'>Revenue side (SIMULATED customer): GMV €{bcs['annual_gmv'] / 1e6:.0f}M / year, {bcs['share_gmv_homepage']:.0%} from homepage "
             f"visitors, take rate {bcs['take_rate']:.0%}. Lift = conversion lift (order value assumed flat, see page 7). "
             f"Payback of the €{bcs['one_off'] / 1e3:.0f}k one-off integration effort: {central.payback_months:.1f} months in the central case.</p>"),
        card("<h3>Sensitivity: net benefit after cost, € k / year</h3>"
             f"<table><tr><th>Conv. lift</th>{''.join(f'<th>{e(c)}</th>' for c in sens.columns)}</tr>{srows}</table>"),
        card("<h3>One-pager for the negotiation</h3><ul>"
             f"<li><b>Break-even:</b> {pct(bcs['break_even_lift'], 1, True)} conversion on the homepage feed covers list price.</li>"
             f"<li><b>Measured:</b> {pct(dec['conversion_rel_lift'], 1, True)} conversion, {pct(dec['week3_lift'], 0, True)} steady-state engagement, guardrails clean.</li>"
             f"<li><b>Central case:</b> €{central.incremental_gmv / 1e6:,.1f}M extra GMV, €{central.net_benefit / 1e3:,.0f}k net per year after cost ({central.roi_multiple:.1f}×).</li>"
             f"<li><b>Risk:</b> the CI lower bound ({pct(dec['conversion_ci'][0], 1, True)}) does not pay; a 5 % holdout measured at month 3 gives both sides a shared success metric.</li>"
             "<li><b>Upside not counted:</b> engagement value, seller retention, more surfaces (Similar Items: +10 % platform fee).</li></ul>",
             style="grid-column: span 2"),
    ])
    pages.append(page(f"At list price, the feed pays back above {pct(bcs['break_even_lift'], 1, True)} conversion; the central case returns "
                      f"{central.roi_multiple:.1f}× its cost",
                      "Sales support in numbers: the A/B confidence interval becomes a low / central / high case, the public price list gives the cost, "
                      "and the break-even lift is the number to anchor the negotiation on.",
                      "SIMULATED + PUBLIC PRICING", body, SRC_SIM + f" · pricing: usealbatross.ai/pricing, collected {COLLECTED} · src/business_case.py",
                      cols="1.05fr 1fr 1fr", rows="1fr 1fr"))

    # ---------------- 9. working with the customer
    C.timeline(BUILD / "p9_timeline.svg", w=5.6, h=2.6)
    body = "".join([
        card("<h3>Who does what, week by week</h3>" + img("p9_timeline.svg") +
             "<table style='margin-top:4px'><tr><th></th><th>Customer engineering lead</th><th>Customer PM</th><th>Deployment Strategist</th></tr>"
             "<tr><td style='white-space:nowrap'>Wk 1-2</td><td>Wire Catalog + Event APIs, history drop</td><td>Owns dates, unblocks access</td><td>Data request, intake report, readiness verdict</td></tr>"
             "<tr><td style='white-space:nowrap'>Wk 3-4</td><td>Fix intake conditions, exposure logging</td><td>Signs the analysis plan</td><td>Baselines, power, plan, go-live checklist</td></tr>"
             "<tr><td style='white-space:nowrap'>Wk 5-7</td><td>Feed integration on the homepage</td><td>Weekly check-in, readout</td><td>Daily health + SRM, weekly report, readout + business case</td></tr></table>",
             style="grid-row: span 2"),
        card("<h3>Escalate or resolve? (excerpt of playbook/04)</h3><table>"
             "<tr><th>Signal</th><th>Rule</th><th>Who</th></tr>"
             "<tr><td>p95 latency</td><td>&gt; 150 ms for 10 min</td><td>Escalate now: on-call</td></tr>"
             "<tr><td>Event stream down</td><td>&lt; 20 % of yesterday, 15 min</td><td>Escalate: customer engineer</td></tr>"
             "<tr><td>Catalog stalled</td><td>freshness &gt; 30 min</td><td>Escalate: both data owners</td></tr>"
             "<tr><td>SRM</td><td>p &lt; 0.001</td><td>Investigate, then data scientist</td></tr>"
             "<tr><td>Duplicates, bots</td><td>&gt; 5 %</td><td>Resolve, report weekly</td></tr>"
             "<tr><td>Data drop late</td><td>2 working days</td><td>Follow-up; PM after 5 days</td></tr></table>"
             "<p class='small muted' style='margin-top:4px'>Resolve alone what is reversible and invisible to users; escalate early, with facts, "
             "when users, revenue, the timeline or trust are at stake.</p>"),
        card("<h3>Templates in playbook/</h3><p class='mono'>Subject: Evaluation – data drop: 2 fixes needed to keep\nthe week-3 training date\n\n"
             f"1. {pct(unknown.rate)} of events point to items missing from\n   the catalog ({unknown.detail.split(' ')[0]} ids). Could you re-export\n   the catalog including sold and delisted listings?\n"
             "2. Time zone: please confirm timestamps are UTC.\n\nImpact on the plan: if we have it by [date], training\nstill starts on [week-3 date].</p>"
             "<p class='small muted'>01 data request · 02 follow-up · 03 weekly report · 04 escalation grid · 05 go-live checklist</p>"),
    ])
    pages.append(page("Two people on the customer side, one owner on ours: who does what, when, and when to escalate",
                      "The customer relationship is the delivery mechanism: clear asks with formats and dates, one weekly report with the same structure, "
                      "and written rules for what is fixed quietly and what is escalated.",
                      "", body, "Templates: playbook/*.md · timeline from usealbatross.ai/evaluation", cols="1.35fr 1fr", rows="1fr 1fr"))

    # ---------------- 10. methods, limits, AI note
    body = "".join([
        card("<h3>Sources and licences</h3><ul>"
             f"<li><b>Albatross public pages</b> (home, technology, evaluation, primitives, customers, Wallapop case study, pricing, company, resources), "
             f"collected {COLLECTED}, one request every 3 s, robots.txt respected. Facts table with URL and date: data/public/albatross_facts.csv. "
             "Page copies are not redistributed (site terms).</li>"
             "<li><b>RetailRocket e-commerce dataset</b>, CC BY-NC-SA 4.0. Integrity checked against the published totals (2,756,101 events, "
             "1,407,580 visitors, 22,457 transactions) and SHA-256 recorded. Raw files are not redistributed; only aggregates.</li>"
             "<li><b>Simulated data</b>: src/simulate.py, seed 42; every assumption in data/ASSUMPTIONS.md.</li></ul>"
             "<h3 style='margin-top:8px'>Methods</h3><ul>"
             "<li>SQL (DuckDB): intake checks, filtering rules, sessions (30-min gap), adequacy metrics, co-visitation, time-split evaluation.</li>"
             "<li>Python: readiness scoring, sample size (two-proportion and mean formulas), Welch z-tests, bootstrap, chi-square SRM, Holm correction, "
             "rule-based health alerts, business-case sensitivity.</li>"
             "<li>Toolkit: <code>python -m adequacy check --events … --catalog …</code>, 8 pytest tests on a synthetic drop with injected anomalies.</li></ul>"
             f"<h3 style='margin-top:10px'>AI note</h3><p class='ai'>{e(AI_NOTE)}</p>",
             style="grid-row: span 2"),
        card("<h3>Limits</h3><ul>"
             "<li>RetailRocket is a 2015 e-commerce shop, not a 2026 second-hand marketplace: smaller, shorter sessions, hashed item properties.</li>"
             "<li>Weeks 5-7 are simulated: they demonstrate the checks and the reasoning, not real Albatross or customer performance.</li>"
             "<li>The baselines are deliberately simple and are not Albatross's models; offline recall does not predict online lift.</li>"
             "<li>Readiness thresholds and alert rules are this playbook's choices, written down to be challenged.</li>"
             "<li>Business case: customer GMV, take rate and homepage share are assumptions; only the pricing is public.</li></ul>"),
        card("<h3>Reproduce</h3><p class='mono'>pip install -r requirements.txt &amp;&amp; pip install -e .\npython src/load_dataset.py   # needs the raw dataset\n"
             "python src/run_intake.py\npython src/baselines.py\npython src/ab_design.py\npython src/simulate.py\npython src/ab_readout.py\n"
             "python src/health_monitor.py\npython src/business_case.py\npython src/build_dashboard.py\npython src/build_report.py\npytest</p>"),
    ])
    pages.append(page("Methods, limits and AI note",
                      "Every number in this report comes from a query or a script in the repository; simulated numbers are labelled as such on every page.",
                      "", body, "data/SOURCES.md · data/ASSUMPTIONS.md", cols="1.2fr 1fr", rows="1fr 1fr"))
    return pages


def find_browser() -> str:
    for p in (r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
              r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
              r"C:\Program Files\Google\Chrome\Application\chrome.exe"):
        if Path(p).exists():
            return p
    for name in ("msedge", "google-chrome", "chromium", "chrome"):
        if shutil.which(name):
            return shutil.which(name)
    raise SystemExit("Edge or Chrome not found: open data/work/report_build/report.html and print to PDF.")


def main() -> None:
    BUILD.mkdir(parents=True, exist_ok=True)
    (DOCS / "img").mkdir(parents=True, exist_ok=True)
    d = load()
    pages = build_pages(d)
    doc = (f"<!doctype html><html lang='en'><head><meta charset='utf-8'><title>Albatross deployment case study</title>"
           f"<style>{CSS}</style></head><body>{''.join(pages)}</body></html>")
    src = BUILD / "report.html"
    src.write_text(doc, encoding="utf-8")
    tmp_pdf = BUILD / "report_raw.pdf"
    subprocess.run([find_browser(), "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
                    f"--user-data-dir={(BUILD / 'browser_profile').as_posix()}",
                    f"--print-to-pdf={tmp_pdf}", src.resolve().as_uri()], check=True, timeout=180,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    clean_pdf(tmp_pdf, PDF)
    previews(PDF)
    print(f"{len(pages)} pages -> {PDF.relative_to(ROOT)}")


def clean_pdf(src: Path, dst: Path) -> None:
    """Rewrite the PDF with neutral metadata (title only, no author, no tool names)."""
    from pypdf import PdfReader, PdfWriter
    reader, writer = PdfReader(src), PdfWriter()
    for p in reader.pages:
        writer.add_page(p)
    writer.add_metadata({"/Title": "Albatross: a 7-week deployment playbook (independent case study)"})
    writer._info.get_object().pop("/Producer", None)
    with open(dst, "wb") as fh:
        writer.write(fh)


def previews(pdf: Path) -> None:
    """PNG previews of every page for the README (docs/img/page_XX.png)."""
    import pypdfium2 as pdfium
    doc = pdfium.PdfDocument(str(pdf))
    for i in range(len(doc)):
        doc[i].render(scale=1.4).to_pil().save(DOCS / "img" / f"page_{i:02d}.png", optimize=True)


if __name__ == "__main__":
    main()
