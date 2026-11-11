"""A/B readout on the SIMULATED test (page 7 of the report).

Follows the analysis plan written before the test (page 5):
  1. Sample-ratio mismatch (SRM): chi-square test of the 50/50 split, overall and per day.
     If it fails, find the cause, exclude the affected cohort from BOTH arms, re-test.
  2. Primary metric: feed clicks per visitor. Difference with a z-test (Welch) and a
     bootstrap confidence interval (resampling visitors, 500 times).
  3. Secondary metrics: engaged-visitor rate, add-to-cart rate, purchase conversion,
     revenue per visitor.
  4. Novelty: lift on clicks per active visitor, week by week.
  5. Segments (new / returning, mobile / desktop): Holm correction for 4 comparisons.
  6. Guardrails: page load time and bounce rate must not get worse beyond a margin.
  7. Decision, using the rules written before the test.
Run: python src/ab_readout.py   (after src/simulate.py)
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import chisquare, norm

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / "data" / "work"
OUT = ROOT / "data" / "simulated" / "ab_readout"
TEST_START = pd.Timestamp("2026-03-02")
SRM_ALPHA = 0.001            # SRM alarm threshold (strict: a real SRM gives tiny p-values)
B = 500                      # bootstrap resamples
GUARDRAIL_MARGIN = {"page_load_ms": 50.0, "bounce": 0.005}   # max tolerated degradation
CONVERSION_NO_HARM = -0.02   # relative lower bound we accept on conversion


def srm(control: int, treatment: int) -> float:
    return float(chisquare([control, treatment]).pvalue)


def diff_mean(c: np.ndarray, t: np.ndarray) -> dict:
    """Difference of means with a Welch z-test and a delta-method CI on the relative lift."""
    mc, mt = c.mean(), t.mean()
    vc, vt = c.var(ddof=1) / len(c), t.var(ddof=1) / len(t)
    se = np.sqrt(vc + vt)
    z = (mt - mc) / se
    rel = mt / mc - 1
    se_rel = np.sqrt(vt / mc ** 2 + mt ** 2 * vc / mc ** 4)
    return {"control": mc, "treatment": mt, "abs_diff": mt - mc, "ci_low": mt - mc - 1.96 * se,
            "ci_high": mt - mc + 1.96 * se, "rel_lift": rel, "rel_ci_low": rel - 1.96 * se_rel,
            "rel_ci_high": rel + 1.96 * se_rel, "p_value": 2 * (1 - norm.cdf(abs(z))), "n_control": len(c),
            "n_treatment": len(t)}


def bootstrap_rel(c: np.ndarray, t: np.ndarray, rng: np.random.Generator) -> tuple[float, float]:
    """Percentile bootstrap CI of the relative lift (resample visitors with replacement)."""
    lifts = np.empty(B)
    for b in range(B):
        mc = c[rng.integers(0, len(c), len(c))].mean()
        mt = t[rng.integers(0, len(t), len(t))].mean()
        lifts[b] = mt / mc - 1
    return float(np.percentile(lifts, 2.5)), float(np.percentile(lifts, 97.5))


def holm(pvals: list[float]) -> list[float]:
    """Holm-Bonferroni adjusted p-values (controls false positives across segments)."""
    order = np.argsort(pvals)
    m, adj, running = len(pvals), np.empty(len(pvals)), 0.0
    for i, k in enumerate(order):
        running = max(running, min(1.0, (m - i) * pvals[k]))
        adj[k] = running
    return adj.tolist()


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(42)
    u = pd.read_parquet(WORK / "ab_users.parquet")

    # ---- 1. SRM -------------------------------------------------------------------
    daily = u.groupby(["first_day", "arm"]).size().unstack("arm")
    daily["p_value"] = [srm(r.control, r.treatment) for r in daily.itertuples()]
    daily["share_treatment"] = daily["treatment"] / (daily["control"] + daily["treatment"])
    daily["date"] = (TEST_START + pd.to_timedelta(daily.index, unit="D")).date
    daily["flag"] = daily["p_value"] < SRM_ALPHA
    daily.reset_index().to_csv(OUT / "srm_daily.csv", index=False)
    bad_days = daily.index[daily["flag"]].tolist()
    counts_before = u["arm"].value_counts()
    # Drill-down: which device drives the imbalance on the flagged day?
    drill = (u[u.first_day.isin(bad_days)].groupby(["device", "arm"]).size().unstack("arm"))
    drill["share_treatment"] = drill["treatment"] / drill.sum(axis=1)
    drill.reset_index().to_csv(OUT / "srm_drilldown.csv", index=False)
    clean = u[~u.first_day.isin(bad_days)]          # exclude the affected cohort from BOTH arms
    counts_after = clean["arm"].value_counts()
    srm_summary = pd.DataFrame([
        {"stage": "all visitors", "control": counts_before["control"], "treatment": counts_before["treatment"],
         "share_treatment": counts_before["treatment"] / counts_before.sum(),
         "p_value": srm(counts_before["control"], counts_before["treatment"])},
        {"stage": f"excluding day(s) {[d + 1 for d in bad_days]}", "control": counts_after["control"],
         "treatment": counts_after["treatment"], "share_treatment": counts_after["treatment"] / counts_after.sum(),
         "p_value": srm(counts_after["control"], counts_after["treatment"])},
    ])
    srm_summary.to_csv(OUT / "srm_summary.csv", index=False)

    c, t = clean[clean.arm == "control"], clean[clean.arm == "treatment"]

    # ---- 2-3. primary + secondary metrics -----------------------------------------------
    defs = [("Feed clicks per visitor (primary)", lambda d: d["clicks"].to_numpy(float)),
            ("Engaged-visitor rate (2+ clicks)", lambda d: (d["clicks"] >= 2).to_numpy(float)),
            ("Add-to-cart rate", lambda d: d["cart"].to_numpy(float)),
            ("Purchase conversion", lambda d: d["purchase"].to_numpy(float)),
            ("Revenue per visitor (EUR)", lambda d: d["revenue"].to_numpy(float))]
    rows = []
    for label, f in defs:
        r = diff_mean(f(c), f(t))
        r["metric"] = label
        if label.startswith("Feed clicks") or label.startswith("Revenue"):
            r["boot_rel_ci_low"], r["boot_rel_ci_high"] = bootstrap_rel(f(c), f(t), rng)
        rows.append(r)
    results = pd.DataFrame(rows)
    cols = ["metric", "control", "treatment", "abs_diff", "ci_low", "ci_high", "rel_lift", "rel_ci_low",
            "rel_ci_high", "boot_rel_ci_low", "boot_rel_ci_high", "p_value", "n_control", "n_treatment"]
    results = results[cols]
    results.to_csv(OUT / "results.csv", index=False)

    # ---- 4. novelty: lift on clicks per ACTIVE visitor, week by week ---------------------
    nov = []
    for w in (1, 2, 3):
        col = f"clicks_w{w}"
        cw, tw = c.loc[c[col] >= 0, col].to_numpy(float), t.loc[t[col] >= 0, col].to_numpy(float)
        r = diff_mean(cw, tw)
        nov.append({"week": w, "rel_lift": r["rel_lift"], "rel_ci_low": r["rel_ci_low"],
                    "rel_ci_high": r["rel_ci_high"], "active_control": len(cw), "active_treatment": len(tw)})
    pd.DataFrame(nov).to_csv(OUT / "novelty.csv", index=False)

    # ---- 5. segments ----------------------------------------------------------------
    seg = []
    for dim in ("user_type", "device"):
        for val in sorted(clean[dim].unique()):
            for label, f in (defs[0], defs[3]):
                r = diff_mean(f(c[c[dim] == val]), f(t[t[dim] == val]))
                seg.append({"dimension": dim, "segment": val, "metric": label, "rel_lift": r["rel_lift"],
                            "rel_ci_low": r["rel_ci_low"], "rel_ci_high": r["rel_ci_high"], "p_value": r["p_value"]})
    seg = pd.DataFrame(seg)
    seg["p_holm"] = np.nan
    for m in seg["metric"].unique():
        k = seg["metric"] == m
        seg.loc[k, "p_holm"] = holm(seg.loc[k, "p_value"].tolist())
    seg.to_csv(OUT / "segments.csv", index=False)

    # ---- 6. guardrails ---------------------------------------------------------------
    g = []
    for col, label in (("page_load_ms", "Page load time (ms)"), ("bounce", "Bounce rate")):
        r = diff_mean(c[col].to_numpy(float), t[col].to_numpy(float))
        margin = GUARDRAIL_MARGIN[col]
        g.append({"guardrail": label, "control": r["control"], "treatment": r["treatment"], "abs_diff": r["abs_diff"],
                  "ci_high": r["ci_high"], "margin": margin, "ok": bool(r["ci_high"] < margin)})
    g = pd.DataFrame(g)
    g.to_csv(OUT / "guardrails.csv", index=False)

    # Average order value among buyers: if it does not move, revenue lift ~ conversion lift
    aov = diff_mean(c.loc[c.purchase, "revenue"].to_numpy(float), t.loc[t.purchase, "revenue"].to_numpy(float))
    pd.DataFrame([{"metric": "Average order value among buyers (EUR)", **aov}]).to_csv(OUT / "aov.csv", index=False)

    # ---- 7. decision (rules written before the test) -------------------------------------
    prim = results.iloc[0]
    conv = results[results.metric == "Purchase conversion"].iloc[0]
    rpv = results[results.metric.str.startswith("Revenue")].iloc[0]
    rules = {
        "SRM resolved (p >= 0.001 after documented exclusion)": bool(srm_summary.iloc[1]["p_value"] >= SRM_ALPHA),
        "Primary metric up, p < 0.05": bool(prim["rel_lift"] > 0 and prim["p_value"] < 0.05),
        "Guardrails within margin": bool(g["ok"].all()),
        "Conversion not harmed (CI low > -2 %)": bool(conv["rel_ci_low"] > CONVERSION_NO_HARM),
    }
    decision = "GO TO PRODUCTION" if all(rules.values()) else "DO NOT SHIP YET"
    out = {"decision": decision, "rules": rules, "srm_bad_days": [d + 1 for d in bad_days],
           "primary_rel_lift": prim["rel_lift"], "primary_ci": [prim["rel_ci_low"], prim["rel_ci_high"]],
           "week3_lift": nov[2]["rel_lift"], "week1_lift": nov[0]["rel_lift"],
           "conversion_rel_lift": conv["rel_lift"], "conversion_ci": [conv["rel_ci_low"], conv["rel_ci_high"]],
           "conversion_p": conv["p_value"], "rpv_rel_lift": rpv["rel_lift"],
           "rpv_ci": [rpv["rel_ci_low"], rpv["rel_ci_high"]], "rpv_boot_ci": [rpv["boot_rel_ci_low"], rpv["boot_rel_ci_high"]],
           "rpv_p": rpv["p_value"], "aov_rel_diff": aov["rel_lift"], "aov_p": aov["p_value"]}
    (OUT / "decision.json").write_text(json.dumps(out, indent=2, default=float), encoding="utf-8")

    pd.set_option("display.width", 200)
    print(srm_summary.to_string(index=False)); print(drill.to_string())
    print(results.to_string(index=False)); print(pd.DataFrame(nov).to_string(index=False))
    print(seg.to_string(index=False)); print(g.to_string(index=False)); print(json.dumps(out, indent=2, default=float))


if __name__ == "__main__":
    main()
