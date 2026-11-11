"""Chart helpers for the report (matplotlib -> SVG). One function per figure.

Style: Segoe UI, recessive grid, blue = the data / treatment, grey = comparison / control,
red = alerts and blocking items, green = "Go", dashed lines = thresholds.
Every number drawn here is read from data/public or data/simulated.
"""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

BLUE, BLUE_LIGHT = "#2A78D6", "#A9C8F0"
GREY, GREY_LIGHT = "#7A7870", "#C9C7BF"
RED, GREEN, AMBER = "#D03B3B", "#1E8E5A", "#C27C0E"
INK, MUTED, GRID = "#0B0B0B", "#52514E", "#E1E0D9"

plt.rcParams.update({
    "font.family": "Segoe UI", "font.size": 9, "axes.edgecolor": GRID, "axes.labelcolor": MUTED,
    "xtick.color": MUTED, "ytick.color": MUTED, "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6, "axes.axisbelow": True,
    "svg.fonttype": "none", "figure.dpi": 100, "legend.frameon": False,
})


def _save(fig, path: Path) -> str:
    fig.savefig(path, format="svg", bbox_inches="tight", transparent=True)
    plt.close(fig)
    return path.name


def hbar(labels, values, path, fmt="{:+.0%}", color=BLUE, w=5.6, h=2.2, xlabel=None, colors=None):
    fig, ax = plt.subplots(figsize=(w, h))
    y = np.arange(len(labels))[::-1]
    ax.barh(y, values, color=colors or color, height=0.55)
    for yi, v in zip(y, values):
        ax.text(v + max(values) * 0.015, yi, fmt.format(v), va="center", color=INK, fontsize=9)
    ax.set_yticks(y, labels)
    ax.grid(axis="y", visible=False)
    ax.set_xlim(0, max(values) * 1.18)
    ax.xaxis.set_visible(False)
    ax.spines["bottom"].set_visible(False)
    ax.spines["left"].set_visible(False)
    ax.tick_params(axis="y", length=0)
    if xlabel:
        ax.set_xlabel(xlabel)
    return _save(fig, path)


def daily_volume(df: pd.DataFrame, flagged: list[str], path: Path, w=4.8, h=2.1) -> str:
    d = df.copy()
    d["day"] = pd.to_datetime(d["day"])
    fig, ax = plt.subplots(figsize=(w, h))
    ax.fill_between(d["day"], d["clean_events"], d["raw_events"], color=GREY_LIGHT, lw=0, label="removed by filters")
    ax.plot(d["day"], d["clean_events"], color=BLUE, lw=1.6, label="clean events / day")
    f = d[d["day"].dt.strftime("%Y-%m-%d").isin(flagged)]
    ax.scatter(f["day"], f["raw_events"], color=RED, s=22, zorder=3, label="volume drop flagged")
    ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{v / 1000:.0f}k"))
    ax.xaxis.set_major_locator(mdates.MonthLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    ax.legend(loc="upper left", fontsize=8, ncol=3)
    ax.set_ylim(0, d["raw_events"].max() * 1.25)
    return _save(fig, path)


def waterfall(df: pd.DataFrame, path: Path, w=3.4, h=1.6) -> str:
    steps = df[df["removed"] > 0]
    fig, ax = plt.subplots(figsize=(w, h))
    y = np.arange(len(steps))[::-1]
    ax.barh(y, steps["removed"], color=[GREY, GREY, RED][-len(steps):], height=0.55)
    for yi, (r, s) in zip(y, zip(steps["removed"], steps["share_removed"])):
        ax.text(r + steps["removed"].max() * 0.02, yi, f"{r:,.0f}  ({s:.2%})", va="center", fontsize=9, color=INK)
    ax.set_yticks(y, steps["step"])
    ax.set_xlim(0, steps["removed"].max() * 1.6)
    ax.xaxis.set_visible(False)
    for s in ("bottom", "left"):
        ax.spines[s].set_visible(False)
    ax.grid(False)
    ax.tick_params(axis="y", length=0)
    return _save(fig, path)


def histogram(cats, values, path, highlight=None, xlabel="", w=3.9, h=2.0, pct=True):
    fig, ax = plt.subplots(figsize=(w, h))
    vals = np.asarray(values, float)
    share = vals / vals.sum()
    colors = [BLUE if (highlight is None or highlight(c)) else GREY_LIGHT for c in cats]
    ax.bar(range(len(cats)), share, color=colors, width=0.75)
    ax.set_xticks(range(len(cats)), cats)
    ax.yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1, decimals=0))
    ax.grid(axis="x", visible=False)
    if xlabel:
        ax.set_xlabel(xlabel)
    for i, s in enumerate(share):
        if s > 0.04:
            ax.text(i, s + 0.01, f"{s:.0%}", ha="center", fontsize=8, color=INK)
    ax.set_ylim(0, share.max() * 1.2)
    return _save(fig, path)


def weekly_bars(dates, values, path, w=3.9, h=2.0, gap_dates=None):
    fig, ax = plt.subplots(figsize=(w, h))
    d = pd.to_datetime(pd.Series(dates))
    ax.bar(d, values, width=5, color=BLUE)
    for g in gap_dates or []:
        ax.axvline(pd.Timestamp(g), color=RED, ls="--", lw=1)
        ax.text(pd.Timestamp(g), max(values) * 0.92, " missing\n snapshot", color=RED, fontsize=7.5)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b"))
    ax.grid(axis="x", visible=False)
    ax.set_ylabel("new items / week")
    return _save(fig, path)


def grouped_recall(seg: pd.DataFrame, path: Path, w=5.0, h=3.3) -> str:
    t = seg[seg["dimension"] == "target"].copy()
    order = ["warm item (5+)", "cold item (1-4)", "new item (0 in train)"]
    bl = ["(b) Recent popularity (7 days)", "(c) Co-visitation + popularity fill"]
    fig, ax = plt.subplots(figsize=(w, h))
    x = np.arange(len(order))
    for i, (b, col) in enumerate(zip(bl, [GREY, BLUE])):
        v = [t[(t.segment == o) & (t.baseline == b)]["recall@20"].iloc[0] for o in order]
        bars = ax.bar(x + (i - 0.5) * 0.36, v, width=0.34, color=col, label=b.split(") ")[1])
        for xi, vi in zip(x + (i - 0.5) * 0.36, v):
            ax.text(xi, vi + 0.008, f"{vi:.1%}", ha="center", fontsize=8, color=INK)
    n = [int(t[(t.segment == o)]["n_targets"].iloc[0]) for o in order]
    names = ["warm item\n(5+ training events)", "cold item\n(1-4 training events)", "new item\n(no training event)"]
    ax.set_xticks(x, [f"{nm}\nn = {k:,}" for nm, k in zip(names, n)], fontsize=8)
    ax.yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1, decimals=0))
    ax.set_ylabel("Recall@20")
    ax.grid(axis="x", visible=False)
    ax.legend(fontsize=8, loc="upper right")
    ax.set_ylim(0, 0.45)
    return _save(fig, path)


def mde_chart(mde: pd.DataFrame, path: Path, w=4.3, h=2.6) -> str:
    metrics = mde["metric"].unique().tolist()
    fig, ax = plt.subplots(figsize=(w, h))
    y = np.arange(len(metrics))[::-1]
    for tag, col, off, lab in (("real", GREY, 0.18, "RetailRocket traffic (~112k visitors / arm)"),
                               ("sim", BLUE, -0.18, "mid-size marketplace (1M / arm, simulated)")):
        v = [mde[(mde.metric == m) & (mde.traffic == tag)]["mde_3w"].iloc[0] for m in metrics]
        ax.barh(y + off, v, height=0.34, color=col, label=lab)
        for yi, vi in zip(y + off, v):
            ax.text(vi + 0.002, yi, f"±{vi:.1%}", va="center", fontsize=8, color=INK)
    ax.axvline(0.11, color=RED, ls="--", lw=1)
    ax.text(0.112, y.max() + 0.45, "Wallapop published +11 % sold items", color=RED, fontsize=7.5)
    ax.set_yticks(y, metrics)
    ax.xaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1, decimals=0))
    ax.set_xlabel("smallest lift detectable in 3 weeks (80 % power, alpha 5 %)")
    ax.grid(axis="y", visible=False)
    ax.legend(fontsize=8, loc="upper center", bbox_to_anchor=(0.4, -0.22), ncol=1)
    ax.set_xlim(0, 0.17)
    return _save(fig, path)


def health_panels(h: pd.DataFrame, truth: pd.DataFrame, path: Path, w=5.3, h_in=4.9) -> str:
    h = h.copy()
    h["ts"] = pd.to_datetime(h["ts"])
    panels = [("events_per_min", "Events received / min", None, "Event stream cut"),
              ("latency_p95_ms", "p95 latency (ms)", 150, "Latency spike"),
              ("duplicate_share", "Duplicate events share", 0.05, "Duplicate events"),
              ("catalog_freshness_min", "Catalog freshness (min)", 60, "Catalog feed stalled"),
              ("top_client_share", "Top client share of requests", 0.05, "Bot traffic")]
    fig, axes = plt.subplots(len(panels), 1, figsize=(w, h_in), sharex=True)
    for ax, (col, label, thr, inc) in zip(axes, panels):
        hourly = h.set_index("ts")[col].resample("30min").max() if col != "events_per_min" else \
            h.set_index("ts")[col].resample("30min").min()
        ax.plot(hourly.index, hourly.values, color=BLUE, lw=1)
        r = truth[truth.incident == inc].iloc[0]
        ax.axvspan(pd.Timestamp(r.start), pd.Timestamp(r.end), color=RED, alpha=0.15, lw=0)
        if thr is not None:
            ax.axhline(thr, color=RED, ls="--", lw=0.9)
        ax.set_ylabel(label, rotation=0, ha="right", va="center", fontsize=8)
        ax.tick_params(labelsize=7.5)
        ax.yaxis.set_major_locator(matplotlib.ticker.MaxNLocator(2))
        ax.text(pd.Timestamp(r.end), ax.get_ylim()[1] * 0.75, "  " + inc, color=RED, fontsize=7.5)
    axes[-1].xaxis.set_major_formatter(mdates.DateFormatter("%d %b"))
    fig.subplots_adjust(hspace=0.25)
    return _save(fig, path)


def srm_chart(daily: pd.DataFrame, path: Path, w=3.1, h=1.9) -> str:
    fig, ax = plt.subplots(figsize=(w, h))
    x = daily["first_day"] + 1
    col = [RED if f else BLUE for f in daily["flag"]]
    ax.bar(x, daily["share_treatment"] - 0.5, bottom=0.5, color=col, width=0.7)
    ax.axhline(0.5, color=GREY, ls="--", lw=0.9)
    ax.set_ylim(0.42, 0.52)
    ax.yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1, decimals=0))
    ax.set_xlabel("test day (visitors by first exposure)")
    ax.set_ylabel("share in treatment")
    bad = daily[daily["flag"]]
    for _, r in bad.iterrows():
        p_txt = f"p = {r.p_value:.0e}" if r.p_value > 1e-12 else "p < 1e-12"
        ax.text(r.first_day + 1.6, r.share_treatment, f"day {int(r.first_day) + 1}: {r.share_treatment:.1%}\n{p_txt}",
                color=RED, fontsize=7.5, va="center")
    ax.grid(axis="x", visible=False)
    return _save(fig, path)


def lift_ci(results: pd.DataFrame, path: Path, w=3.0, h=2.3) -> str:
    fig, ax = plt.subplots(figsize=(w, h))
    r = results.iloc[::-1].reset_index(drop=True)
    for i, row in r.iterrows():
        sig = row.rel_ci_low > 0
        c = BLUE if sig else GREY
        ax.plot([row.rel_ci_low, row.rel_ci_high], [i, i], color=c, lw=2.2, solid_capstyle="round")
        ax.scatter(row.rel_lift, i, color=c, s=30, zorder=3)
        ax.text(max(row.rel_ci_high, 0) + 0.02, i, f"{row.rel_lift:+.1%}  [{row.rel_ci_low:+.1%}, {row.rel_ci_high:+.1%}]",
                va="center", fontsize=7.5, color=INK)
    ax.axvline(0, color=GREY, lw=0.9)
    short = {"Feed clicks per visitor (primary)": "Feed clicks / visitor\n(primary)", "Engaged-visitor rate (2+ clicks)": "Engaged visitors",
             "Add-to-cart rate": "Add-to-cart rate", "Purchase conversion": "Conversion", "Revenue per visitor (EUR)": "Revenue / visitor"}
    ax.set_yticks(range(len(r)), [short.get(m, m) for m in r["metric"]], fontsize=8)
    ax.xaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1, decimals=0))
    ax.set_xlim(-0.06, 0.62)
    ax.set_xticks([0, 0.1, 0.2])
    ax.grid(axis="y", visible=False)
    ax.set_xlabel("relative lift, treatment vs control (95 % CI)")
    return _save(fig, path)


def novelty_chart(nov: pd.DataFrame, path: Path, w=3.1, h=1.9) -> str:
    fig, ax = plt.subplots(figsize=(w, h))
    x = nov["week"]
    ax.bar(x, nov["rel_lift"], color=[BLUE_LIGHT, BLUE_LIGHT, BLUE], width=0.6)
    ax.errorbar(x, nov["rel_lift"], yerr=[nov["rel_lift"] - nov["rel_ci_low"], nov["rel_ci_high"] - nov["rel_lift"]],
                fmt="none", ecolor=INK, lw=1, capsize=3)
    for xi, v in zip(x, nov["rel_lift"]):
        ax.text(xi, v + 0.02, f"{v:+.0%}", ha="center", fontsize=8.5, color=INK)
    ax.set_xticks(x, [f"week {w}" for w in x])
    ax.yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1, decimals=0))
    ax.set_ylim(0, nov["rel_ci_high"].max() * 1.25)
    ax.grid(axis="x", visible=False)
    ax.set_ylabel("feed clicks lift")
    return _save(fig, path)


def business_bars(cases: pd.DataFrame, path: Path, w=3.4, h=2.3) -> str:
    fig, ax = plt.subplots(figsize=(w, h))
    labels = ["low\n(CI low)", "central", "high\n(CI high)"]
    x = np.arange(3)
    ax.bar(x - 0.18, cases["incremental_revenue"] / 1000, width=0.34, color=BLUE, label="incremental net revenue")
    ax.bar(x + 0.18, cases["annual_cost"] / 1000, width=0.34, color=GREY_LIGHT, label="platform cost (list price)")
    for xi, v in zip(x - 0.18, cases["incremental_revenue"] / 1000):
        ax.text(xi, v + 15, f"€{v:,.0f}k", ha="center", fontsize=8, color=INK)
    ax.text(x[-1] + 0.18, cases["annual_cost"].iloc[0] / 1000 + 15, f"€{cases['annual_cost'].iloc[0] / 1000:,.0f}k",
            ha="center", fontsize=8, color=MUTED)
    ax.set_xticks(x, [f"{l}\n{c:+.1%} conv." for l, c in zip(labels, cases["conversion_lift"])], fontsize=8)
    ax.set_ylabel("EUR k per year")
    ax.grid(axis="x", visible=False)
    ax.legend(fontsize=7.5, loc="upper left")
    ax.set_ylim(0, cases["incremental_revenue"].max() / 1000 * 1.25)
    return _save(fig, path)


def timeline(path: Path, w=9.6, h=2.3) -> str:
    """The 7-week evaluation as a Gantt chart with owners (from usealbatross.ai/evaluation + this playbook)."""
    rows = [("Kickoff, data request, sample file", 0, 1, GREY),
            ("Intake checks + readiness verdict", 0.6, 2, BLUE),
            ("Catalog + event APIs wired (customer)", 0, 2, GREY_LIGHT),
            ("Model training (Albatross)", 2, 4, GREY_LIGHT),
            ("Offline baselines + test plan sign-off", 2, 4, BLUE),
            ("Go-live: ramp 5 % -> 50 %", 4, 4.3, RED),
            ("Live A/B + daily health & SRM", 4, 7, BLUE),
            ("Readout + business case", 6.7, 7.5, GREEN)]
    fig, ax = plt.subplots(figsize=(w, h))
    for i, (lab, s, e, c) in enumerate(rows[::-1]):
        ax.barh(i, e - s, left=s, color=c, height=0.6)
        ax.text(-0.1, i, lab, ha="right", va="center", fontsize=8)
    for w, lab in ((0, "Weeks 1-2\ndata integration"), (2, "Weeks 3-4\nmodel training"), (4, "Weeks 5-7\nintegration & live A/B")):
        ax.axvline(w, color=GRID, lw=1)
        ax.text(w + 0.05, len(rows) - 0.3, lab, fontsize=7.5, color=MUTED, va="bottom")
    ax.set_yticks([])
    ax.set_xticks(np.arange(7) + 0.5, [f"week {k}" for k in range(1, 8)], fontsize=7.5)
    ax.tick_params(axis="x", length=0)
    ax.set_xlim(0, 7.6)
    ax.set_ylim(-0.6, len(rows) + 0.6)
    ax.grid(False)
    ax.spines["left"].set_visible(False)
    return _save(fig, path)
