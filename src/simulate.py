"""SIMULATED data for weeks 5-7: live deployment health + A/B test (seed 42).

Nothing here is Albatross or customer data. The simulation exists to show the
dashboards, checks and reasoning a Deployment Strategist runs during a live test.
Calibration (all listed in data/ASSUMPTIONS.md):
  - per-visitor base rates come from the REAL dataset (data/public/ab_design/base_rates.json);
  - traffic is scaled to a mid-size marketplace (2 M unique homepage visitors in 3 weeks);
  - true treatment effects are set BELOW the lifts Albatross's customers published
    (e.g. +16 % steady-state engagement vs +84 % / +119 % published).

Outputs
  data/simulated/health_5min.csv      5-minute monitoring series with 5 injected incidents
  data/simulated/incidents_truth.csv  what was injected (to check that monitoring finds it)
  data/simulated/ab_daily.csv         daily exposure counts by arm (for the SRM chart)
  data/work/ab_users.parquet          one row per visitor (local; regenerate with this script)
Run: python src/simulate.py
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SIM = ROOT / "data" / "simulated"
WORK = ROOT / "data" / "work"
SEED = 42

# ---------------------------------------------------------------- A/B parameters
N_VISITORS = 2_000_000          # unique homepage visitors over the 3-week test
TEST_DAYS = 21
TEST_START = pd.Timestamp("2026-03-02")   # an arbitrary Monday: weeks 5-7 of the evaluation
SHARE_RETURNING, SHARE_MOBILE = 0.55, 0.70
P_ACTIVE_LATER_WEEK = {"returning": 0.45, "new": 0.20}   # chance to come back in a later week
CLICK_MEAN_WEEK, CLICK_SHAPE = 1.25, 0.30                # negative binomial per active week
# True lift on feed clicks by calendar week of the test (novelty effect that fades)
CLICK_LIFT = {"returning": [0.34, 0.22, 0.18], "new": [0.24, 0.15, 0.12]}
CART_LIFT, AOV_EUR, AOV_SIGMA = 0.05, 45.0, 0.8          # purchase follows cart (same +5 %)
SRM_DAY, SRM_DROP = 8, 0.35       # day 9: 35 % of treatment mobile visitors lost by a logging bug
LOAD_MS_CONTROL, LOAD_MS_DELTA = 820.0, 6.0              # guardrail: page load time
BOUNCE_CONTROL, BOUNCE_DELTA = 0.38, -0.012              # guardrail: bounce rate


def simulate_ab(rng: np.random.Generator, base: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    n = N_VISITORS
    arm = np.where(rng.random(n) < 0.5, "treatment", "control")
    user_type = np.where(rng.random(n) < SHARE_RETURNING, "returning", "new")
    device = np.where(rng.random(n) < SHARE_MOBILE, "mobile", "desktop")
    first_day = rng.integers(0, TEST_DAYS, n)
    first_week = first_day // 7
    treat = arm == "treatment"

    # Latent activity of each visitor (gamma) -> drives clicks AND cart probability,
    # so engaged visitors buy more, as in real data.
    activity = rng.gamma(CLICK_SHAPE, 1 / CLICK_SHAPE, n)        # mean 1
    clicks = np.zeros((n, 3), dtype=np.int32)
    for w in range(3):
        active = first_week == w
        later = first_week < w
        p_back = np.where(user_type == "returning", P_ACTIVE_LATER_WEEK["returning"], P_ACTIVE_LATER_WEEK["new"])
        active |= later & (rng.random(n) < p_back)
        lift = np.where(user_type == "returning", CLICK_LIFT["returning"][w], CLICK_LIFT["new"][w])
        mean = CLICK_MEAN_WEEK * activity * np.where(treat, 1 + lift, 1.0)
        clicks[:, w] = np.where(active, rng.poisson(mean), -1)   # -1 = not active that week

    # Cart: base rate from the real data, tilted by activity (sqrt keeps it moderate)
    tilt = np.sqrt(activity)
    p_cart = base["cart_rate"] * tilt / tilt.mean() * np.where(treat, 1 + CART_LIFT, 1.0)
    cart = rng.random(n) < np.clip(p_cart, 0, 1)
    p_buy_given_cart = base["conversion"] / base["cart_rate"]
    purchase = cart & (rng.random(n) < p_buy_given_cart)
    mu = np.log(AOV_EUR) - AOV_SIGMA ** 2 / 2                     # lognormal with mean AOV_EUR
    revenue = np.where(purchase, rng.lognormal(mu, AOV_SIGMA, n), 0.0).round(2)

    total_clicks = np.where(clicks < 0, 0, clicks).sum(axis=1)
    load_ms = rng.lognormal(np.log(LOAD_MS_CONTROL), 0.35, n) + np.where(treat, LOAD_MS_DELTA, 0)
    bounce = rng.random(n) < np.where(treat, BOUNCE_CONTROL + BOUNCE_DELTA, BOUNCE_CONTROL)

    df = pd.DataFrame({
        "visitor_id": np.arange(n), "arm": arm, "user_type": user_type, "device": device,
        "first_day": first_day, "clicks_w1": clicks[:, 0], "clicks_w2": clicks[:, 1], "clicks_w3": clicks[:, 2],
        "clicks": total_clicks, "cart": cart, "purchase": purchase, "revenue": revenue,
        "page_load_ms": load_ms.round(0), "bounce": bounce,
    })
    # Injected sample-ratio mismatch: a logging bug in a mobile release on day 9 loses
    # part of the treatment visitors who arrived that day (they never reach the logs).
    lost = treat & (first_day == SRM_DAY) & (device == "mobile") & (rng.random(n) < SRM_DROP)
    df = df[~lost].reset_index(drop=True)

    daily = (df.groupby(["first_day", "arm"]).size().unstack("arm").reset_index())
    daily["date"] = (TEST_START + pd.to_timedelta(daily["first_day"], unit="D")).dt.date
    return df, daily[["first_day", "date", "control", "treatment"]]


# ---------------------------------------------------------------- health parameters
INCIDENTS = [
    # name, start (day, hour), duration hours, what happens
    ("Event stream cut", (2, 2.0), 3.0, "events received drop to zero; backlog replayed after"),
    ("Latency spike", (7, 19.0), 0.75, "p95 latency jumps, errors and fallback rise"),
    ("Duplicate events", (10, 9.0), 6.0, "tracker retries: ~40 % of events sent twice"),
    ("Catalog feed stalled", (13, 6.0), 30.0, "no catalog update: new listings not recommendable"),
    ("Bot traffic", (17, 1.0), 4.0, "one client floods the feed API; click-through drops"),
]


def simulate_health(rng: np.random.Generator) -> tuple[pd.DataFrame, pd.DataFrame]:
    idx = pd.date_range(TEST_START, periods=TEST_DAYS * 24 * 12, freq="5min")
    t = np.arange(len(idx))
    hour = np.asarray(idx.hour + idx.minute / 60, dtype=float)
    # diurnal shape: low at night, peak around 21:00; slightly higher at weekends
    diurnal = 0.35 + 0.65 * np.exp(-((hour - 21) % 24 - 0) ** 2 / 30) + 0.45 * np.exp(-((hour - 13) ** 2) / 18)
    weekend = np.where(idx.day_of_week >= 5, 1.12, 1.0)
    rpm = 230 * diurnal * weekend * rng.normal(1, 0.04, len(idx))          # feed requests / minute (treatment arm)
    events = 9.0 * rpm * rng.normal(1, 0.05, len(idx))                     # tracked events / minute (both arms)
    p50 = rng.normal(18, 1.2, len(idx))
    p95 = rng.normal(46, 3.0, len(idx)) + 6 * (diurnal - diurnal.mean())
    err = np.clip(rng.normal(0.0005, 0.00015, len(idx)), 0, None)
    fallback = np.clip(rng.normal(0.006, 0.0012, len(idx)), 0, None)
    lag = np.clip(rng.gamma(4, 0.5, len(idx)), 0.3, None)                  # event lag p95, seconds
    dup = np.clip(rng.normal(0.002, 0.0007, len(idx)), 0, None)
    top_client = np.clip(rng.normal(0.004, 0.001, len(idx)), 0, None)
    ctr = np.clip(rng.normal(0.042, 0.002, len(idx)), 0, None)
    # catalog: an update batch lands every 2-6 minutes; freshness = minutes since a new listing
    # arrived until it becomes recommendable (median over the bucket)
    fresh = np.clip(rng.gamma(3, 1.4, len(idx)), 1, None)

    truth = []
    for name, (day, h), dur, what in INCIDENTS:
        start = TEST_START + pd.Timedelta(days=day, hours=h)
        end = start + pd.Timedelta(hours=dur)
        m = (idx >= start) & (idx < end)
        if name == "Event stream cut":
            events[m] = 0
            after = (idx >= end) & (idx < end + pd.Timedelta(minutes=40))
            events[after] *= 4.5                                        # backlog replay
            lag[after] = np.linspace(dur * 3600, 5, after.sum())
            fallback[m] += 0.02                                         # stale user state -> more fallback
        elif name == "Latency spike":
            p95[m] = rng.normal(420, 40, m.sum()); p50[m] = rng.normal(95, 10, m.sum())
            err[m] = rng.normal(0.03, 0.004, m.sum()); fallback[m] = rng.normal(0.22, 0.02, m.sum())
        elif name == "Duplicate events":
            dup[m] = rng.normal(0.40, 0.02, m.sum()); events[m] *= 1.4
        elif name == "Catalog feed stalled":
            fresh[m] = (idx[m] - start).total_seconds() / 60 + 5
        elif name == "Bot traffic":
            top_client[m] = rng.normal(0.27, 0.02, m.sum()); rpm[m] *= 1.38; ctr[m] = rng.normal(0.031, 0.002, m.sum())
        truth.append({"incident": name, "start": start, "end": end, "duration_h": dur, "what_happened": what})

    health = pd.DataFrame({
        "ts": idx, "requests_per_min": rpm.round(1), "events_per_min": events.round(1),
        "latency_p50_ms": p50.round(1), "latency_p95_ms": p95.round(1), "error_rate": err.round(5),
        "fallback_share": fallback.round(4), "event_lag_p95_s": lag.round(1), "duplicate_share": dup.round(4),
        "catalog_freshness_min": fresh.round(1), "top_client_share": top_client.round(4), "feed_ctr": ctr.round(4),
    })
    return health, pd.DataFrame(truth)


def daily_coverage(rng: np.random.Generator, health: pd.DataFrame) -> pd.DataFrame:
    """Share of the live catalog recommended at least once per day (rises as the model warms up),
    and share of new listings recommendable within 15 minutes (drops when the catalog feed stalls)."""
    days = pd.date_range(TEST_START, periods=TEST_DAYS, freq="D")
    cov = 0.55 + 0.20 * (1 - np.exp(-np.arange(TEST_DAYS) / 6)) + rng.normal(0, 0.008, TEST_DAYS)
    fresh = health.set_index("ts")["catalog_freshness_min"].resample("D").apply(lambda s: float((s <= 15).mean()))
    return pd.DataFrame({"date": days.date, "catalog_coverage": cov.round(4),
                         "new_items_live_15min": fresh.values.round(4)})


def main() -> None:
    SIM.mkdir(parents=True, exist_ok=True)
    WORK.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(SEED)
    base = json.loads((ROOT / "data" / "public" / "ab_design" / "base_rates.json").read_text())

    users, daily = simulate_ab(rng, base)
    users.to_parquet(WORK / "ab_users.parquet", index=False)
    daily.to_csv(SIM / "ab_daily.csv", index=False)

    health, truth = simulate_health(rng)
    health.to_csv(SIM / "health_5min.csv", index=False)
    truth.to_csv(SIM / "incidents_truth.csv", index=False)
    daily_coverage(rng, health).to_csv(SIM / "coverage_daily.csv", index=False)

    c = users[users.arm == "control"]
    print(f"visitors {len(users):,} | control clicks/visitor {c.clicks.mean():.2f} (sd {c.clicks.std():.2f}) "
          f"| engaged {(c.clicks >= 2).mean():.3f} | cart {c.cart.mean():.4f} | conv {c.purchase.mean():.4f} "
          f"| RPV {c.revenue.mean():.3f}")
    print(f"real base: views/visitor {base['views_mean']:.2f} (sd {base['views_sd']:.2f}) engaged {base['engaged_rate']:.3f} "
          f"cart {base['cart_rate']:.4f} conv {base['conversion']:.4f}")
    print(daily.head(10).to_string(index=False))


if __name__ == "__main__":
    main()
