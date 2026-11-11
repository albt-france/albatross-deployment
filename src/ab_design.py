"""A/B test design for weeks 5-7, sized on REAL base rates (page 5 of the report).

1. Base rates per visitor over a 3-week window (the planned test length), from the
   cleaned RetailRocket events: engaged-visitor rate, add-to-cart rate, purchase
   conversion, views per visitor (mean and standard deviation).
2. Sample size per arm for each metric and each minimum detectable effect (MDE),
   two-sided alpha = 5 %, power = 80 %, 50/50 split.
3. Weeks needed at two traffic levels:
     - the real dataset's traffic (unique visitors observed over 1..8 weeks),
     - the SIMULATED mid-size marketplace used on pages 6-8 (assumption in ASSUMPTIONS.md).

Formulas (standard, easy to check by hand):
  proportion: n = (z_a * sqrt(2 p q) + z_b * sqrt(p1 q1 + p2 q2))^2 / (p2 - p1)^2
  mean      : n = 2 (z_a + z_b)^2 sigma^2 / delta^2
Run: python src/ab_design.py
"""
from __future__ import annotations

import json
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
from scipy.stats import norm

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / "data" / "work"
OUT = ROOT / "data" / "public" / "ab_design"
ALPHA, POWER = 0.05, 0.80
MDES = [0.02, 0.05, 0.10, 0.20]
SIM_VISITORS_3W = 2_000_000   # simulated customer: unique homepage visitors in 3 weeks (ASSUMPTIONS.md)


def n_proportion(p: float, rel_mde: float) -> float:
    p1, p2 = p, p * (1 + rel_mde)
    za, zb = norm.ppf(1 - ALPHA / 2), norm.ppf(POWER)
    pbar = (p1 + p2) / 2
    num = (za * np.sqrt(2 * pbar * (1 - pbar)) + zb * np.sqrt(p1 * (1 - p1) + p2 * (1 - p2))) ** 2
    return num / (p2 - p1) ** 2


def n_mean(mean: float, sd: float, rel_mde: float) -> float:
    za, zb = norm.ppf(1 - ALPHA / 2), norm.ppf(POWER)
    return 2 * (za + zb) ** 2 * sd ** 2 / (mean * rel_mde) ** 2


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    con.execute("SET TimeZone = 'UTC'")
    con.execute(f"CREATE VIEW e AS SELECT * FROM '{(WORK / 'events_clean.parquet').as_posix()}'")

    # Base rates per visitor in every full 3-week window (start every week), then averaged.
    windows = con.execute("""
        WITH starts AS (
            SELECT unnest(generate_series(TIMESTAMP '2015-05-04', TIMESTAMP '2015-08-24', INTERVAL 7 DAY)) AS s
        ),
        u AS (
            SELECT st.s, e.user_id,
                   sum((e.event_type = 'view')::INT)              AS views,
                   max((e.event_type = 'addtocart')::INT)         AS cart,
                   max((e.event_type = 'transaction')::INT)       AS buy
            FROM starts st JOIN e ON e.ts >= st.s AND e.ts < st.s + INTERVAL 21 DAY
            GROUP BY 1, 2
        )
        SELECT s AS window_start, count(*) AS visitors,
               avg((views >= 2)::INT) AS engaged_rate, avg(cart) AS cart_rate, avg(buy) AS conversion,
               avg(views) AS views_mean, stddev(views) AS views_sd
        FROM u GROUP BY 1 ORDER BY 1
    """).df()
    windows.to_csv(OUT / "base_rate_windows.csv", index=False)
    base = windows.drop(columns="window_start").mean().to_dict()

    # Unique visitors reachable in w weeks (median over start weeks) -> traffic curve
    reach = []
    for w in range(1, 9):
        v = con.execute(f"""
            WITH starts AS (SELECT unnest(generate_series(TIMESTAMP '2015-05-04',
                            TIMESTAMP '2015-09-14' - INTERVAL {7 * w} DAY, INTERVAL 7 DAY)) AS s)
            SELECT median(n) FROM (
                SELECT st.s, count(DISTINCT user_id) AS n FROM starts st
                JOIN e ON e.ts >= st.s AND e.ts < st.s + INTERVAL {7 * w} DAY GROUP BY 1)
        """).fetchone()[0]
        reach.append({"weeks": w, "unique_visitors_real": v})
    reach = pd.DataFrame(reach)
    # Simulated customer: same shape of the curve, scaled so that 3 weeks = SIM_VISITORS_3W
    scale = SIM_VISITORS_3W / reach.loc[reach.weeks == 3, "unique_visitors_real"].iloc[0]
    reach["unique_visitors_sim"] = (reach["unique_visitors_real"] * scale).round()
    reach.to_csv(OUT / "traffic_reach.csv", index=False)

    metrics = [
        ("Engaged-visitor rate (2+ views)", "proportion", base["engaged_rate"], None),
        ("Views per visitor", "mean", base["views_mean"], base["views_sd"]),
        ("Add-to-cart rate", "proportion", base["cart_rate"], None),
        ("Purchase conversion", "proportion", base["conversion"], None),
    ]
    rows = []
    for label, kind, p, sd in metrics:
        for mde in MDES:
            n = n_proportion(p, mde) if kind == "proportion" else n_mean(p, sd, mde)
            row = {"metric": label, "base": p, "sd": sd, "relative_mde": mde, "n_per_arm": int(np.ceil(n))}
            for col, tag in (("unique_visitors_real", "real"), ("unique_visitors_sim", "sim")):
                ok = reach[reach[col] >= 2 * n]
                row[f"weeks_{tag}"] = int(ok["weeks"].min()) if len(ok) else None  # None = more than 8 weeks
            rows.append(row)
    power = pd.DataFrame(rows)
    power.to_csv(OUT / "power_table.csv", index=False)

    # Achieved MDE (80 % power) after 3 weeks for each metric and traffic level
    mde_rows = []
    for label, kind, p, sd in metrics:
        for tag, col in (("real", "unique_visitors_real"), ("sim", "unique_visitors_sim")):
            n_avail = reach.loc[reach.weeks == 3, col].iloc[0] / 2
            grid = np.linspace(0.001, 2.0, 4000)
            need = np.array([n_proportion(p, g) if kind == "proportion" else n_mean(p, sd, g) for g in grid])
            mde_rows.append({"metric": label, "traffic": tag, "n_per_arm_3w": int(n_avail),
                             "mde_3w": float(grid[np.argmax(need <= n_avail)])})
    pd.DataFrame(mde_rows).to_csv(OUT / "mde_after_3_weeks.csv", index=False)

    (OUT / "base_rates.json").write_text(json.dumps({k: float(v) for k, v in base.items()}, indent=2), encoding="utf-8")
    print(pd.Series(base).to_string())
    print(reach.to_string(index=False))
    print(power.to_string(index=False))
    print(pd.DataFrame(mde_rows).to_string(index=False))


if __name__ == "__main__":
    main()
