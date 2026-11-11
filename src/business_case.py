"""Business case for the production decision (page 8): SIMULATED customer, PUBLIC pricing.

Revenue side (customer = a mid-size marketplace, assumptions in data/ASSUMPTIONS.md):
    incremental GMV      = annual GMV x share of GMV from homepage visitors x conversion lift
    incremental revenue  = incremental GMV x take rate (the marketplace's commission)
  The lift comes from the A/B readout. Revenue per visitor was too noisy to read directly
  (order values vary a lot), and average order value did not move, so the conversion
  lift and its confidence interval give the low / central / high cases.

Cost side (usealbatross.ai/pricing, collected 2026-11-11):
    platform fee by MAU tier + usage per 1,000 predictions (marginal tiers).
Run: python src/business_case.py   (after src/ab_readout.py)
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "simulated" / "business_case"

# ---- customer assumptions (SIMULATED customer) ----
MAU = 3_000_000
ANNUAL_GMV_EUR = 250_000_000
SHARE_GMV_HOMEPAGE = 0.50          # share of GMV from visitors who land on the homepage feed
TAKE_RATE = 0.12                   # marketplace commission on GMV
ONE_OFF_EUR = 20_000               # customer integration effort (2 people, part-time, 7 weeks)
EVALUATION_FEE_EUR = 0             # not public; "waived for fast starts" (sensitivity below)

# ---- public pricing (usealbatross.ai/pricing, 2026-11-11) ----
TIERS = [(1_000_000, 10_000), (5_000_000, 20_000), (10_000_000, 30_000), (float("inf"), 40_000)]
USAGE = [(100e6, 0.50), (200e6, 0.25), (float("inf"), 0.10)]   # EUR per 1k predictions, marginal


def platform_fee(mau: int) -> float:
    return next(fee for cap, fee in TIERS if mau < cap)


def usage_fee(predictions: float) -> float:
    cost, lower = 0.0, 0.0
    for cap, price in USAGE:
        chunk = max(0.0, min(predictions, cap) - lower)
        cost += chunk / 1000 * price
        lower = cap
    return cost


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    dec = json.loads((ROOT / "data" / "simulated" / "ab_readout" / "decision.json").read_text())
    health = pd.read_csv(ROOT / "data" / "simulated" / "health_5min.csv")

    # Predictions per month at 100 % traffic: the test served the treatment half only.
    rpm = health["requests_per_min"].median()
    predictions_month = rpm * 60 * 24 * 30 * 2
    monthly_cost = platform_fee(MAU) + usage_fee(predictions_month)
    annual_cost = 12 * monthly_cost

    lifts = {"low (CI lower bound)": dec["conversion_ci"][0], "central (point estimate)": dec["conversion_rel_lift"],
             "high (CI upper bound)": dec["conversion_ci"][1]}
    rows = []
    for case, lift in lifts.items():
        gmv = ANNUAL_GMV_EUR * SHARE_GMV_HOMEPAGE * lift
        rev = gmv * TAKE_RATE
        net = rev - annual_cost
        monthly_net = net / 12
        payback = (ONE_OFF_EUR + EVALUATION_FEE_EUR) / monthly_net if monthly_net > 0 else None
        rows.append({"case": case, "conversion_lift": lift, "incremental_gmv": gmv, "incremental_revenue": rev,
                     "annual_cost": annual_cost, "net_benefit": net, "roi_multiple": rev / annual_cost,
                     "payback_months": payback})
    cases = pd.DataFrame(rows)
    cases.to_csv(OUT / "cases.csv", index=False)

    break_even_lift = annual_cost / (ANNUAL_GMV_EUR * SHARE_GMV_HOMEPAGE * TAKE_RATE)

    # Sensitivity: net annual benefit (EUR k) by conversion lift x take rate, and by lift x GMV
    lift_grid = [0.01, 0.02, round(dec["conversion_rel_lift"], 3), 0.05, round(dec["conversion_ci"][1], 3)]
    sens_take = pd.DataFrame({f"take {tr:.0%}": [(ANNUAL_GMV_EUR * SHARE_GMV_HOMEPAGE * l * tr - annual_cost) / 1000
                                                  for l in lift_grid] for tr in (0.08, 0.12, 0.15)},
                             index=[f"{l:+.1%}" for l in lift_grid])
    sens_take.index.name = "conversion lift"
    sens_take.round(0).to_csv(OUT / "sensitivity_take_rate.csv")
    sens_gmv = pd.DataFrame({f"GMV EUR {g / 1e6:.0f}M": [(g * SHARE_GMV_HOMEPAGE * l * TAKE_RATE - annual_cost) / 1000
                                                         for l in lift_grid] for g in (150e6, 250e6, 400e6)},
                            index=[f"{l:+.1%}" for l in lift_grid])
    sens_gmv.index.name = "conversion lift"
    sens_gmv.round(0).to_csv(OUT / "sensitivity_gmv.csv")

    summary = {"mau": MAU, "annual_gmv": ANNUAL_GMV_EUR, "share_gmv_homepage": SHARE_GMV_HOMEPAGE,
               "take_rate": TAKE_RATE, "predictions_per_month": predictions_month,
               "platform_fee_month": platform_fee(MAU), "usage_fee_month": usage_fee(predictions_month),
               "monthly_cost": monthly_cost, "annual_cost": annual_cost, "break_even_lift": break_even_lift,
               "one_off": ONE_OFF_EUR + EVALUATION_FEE_EUR,
               "engagement_week3_lift": dec["week3_lift"], "rpv_lift": dec["rpv_rel_lift"], "rpv_ci": dec["rpv_ci"]}
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2, default=float), encoding="utf-8")
    pd.set_option("display.width", 200)
    print(json.dumps(summary, indent=2, default=float))
    print(cases.to_string(index=False)); print(sens_take.round(0)); print(sens_gmv.round(0))


if __name__ == "__main__":
    main()
