"""Weeks 1-2 on the REAL dataset: intake checks, filtering, readiness score + aggregates for the report.

Runs the adequacy toolkit on data/work/events.parquet + catalog.parquet (built by
load_dataset.py), saves the cleaned events locally, and publishes only AGGREGATED
tables in data/public/intake/ (the raw dataset is not redistributed).

Run: python src/run_intake.py
"""
from __future__ import annotations

import json
from pathlib import Path

from adequacy.checks import apply_filters, load_inputs, run_checks
from adequacy.readiness import compute_metrics, readiness
from adequacy.report import to_html, to_markdown

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / "data" / "work"
OUT = ROOT / "data" / "public" / "intake"
NAME = "RetailRocket public dataset, treated as a new customer's first data drop"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    con, schema = load_inputs(WORK / "events.parquet", WORK / "catalog.parquet")
    checks = run_checks(con, schema)
    waterfall = apply_filters(con)
    metrics = compute_metrics(con)
    result = readiness(metrics, checks)

    # Toolkit outputs (all aggregated)
    checks.to_csv(OUT / "checks.csv", index=False)
    waterfall.to_csv(OUT / "filtering.csv", index=False)
    result["scorecard"].to_csv(OUT / "readiness.csv", index=False)
    clean = {k: (v.isoformat() if hasattr(v, "isoformat") else float(v)) for k, v in metrics.items()}
    clean.update({"verdict": result["verdict"], "score": result["score"]})
    (OUT / "metrics.json").write_text(json.dumps(clean, indent=2), encoding="utf-8")
    (OUT / "intake_report.md").write_text(to_markdown(NAME, checks, waterfall, result), encoding="utf-8")
    (OUT / "intake_report.html").write_text(to_html(NAME, checks, waterfall, result), encoding="utf-8")
    (OUT / "customer_message.txt").write_text(result["message"].replace("**", ""), encoding="utf-8")

    # Cleaned events, kept locally for the baselines and the A/B design
    con.execute(f"COPY events_clean TO '{(WORK / 'events_clean.parquet').as_posix()}' (FORMAT parquet)")

    # Extra aggregates for the report pages
    q = lambda sql, name: con.execute(sql).df().to_csv(OUT / name, index=False)
    q("""SELECT r.d AS day, r.n AS raw_events, coalesce(c.n, 0) AS clean_events
         FROM (SELECT ts::DATE d, count(*) n FROM events_raw GROUP BY 1) r
         LEFT JOIN (SELECT ts::DATE d, count(*) n FROM events_clean GROUP BY 1) c USING (d)
         ORDER BY 1""", "daily_volume.csv")
    q("""WITH u AS (SELECT user_id, count(*) n FROM events_clean GROUP BY 1)
         SELECT least(n, 20) AS events_per_user, count(*) AS users FROM u GROUP BY 1 ORDER BY 1""",
      "events_per_user.csv")
    q("""WITH o AS (SELECT user_id, ts, CASE WHEN ts - lag(ts) OVER (PARTITION BY user_id ORDER BY ts)
                    <= INTERVAL 30 MINUTE THEN 0 ELSE 1 END AS new_s FROM events_clean),
              n AS (SELECT user_id, sum(new_s) OVER (PARTITION BY user_id ORDER BY ts) AS s FROM o),
              l AS (SELECT user_id, s, count(*) len FROM n GROUP BY 1, 2)
         SELECT least(len, 20) AS session_length, count(*) AS sessions FROM l GROUP BY 1 ORDER BY 1""",
      "session_length.csv")
    q("""WITH p AS (SELECT c.item_id, count(e.item_id) n FROM (SELECT DISTINCT item_id FROM catalog) c
                    LEFT JOIN events_clean e USING (item_id) GROUP BY 1)
         SELECT CASE WHEN n = 0 THEN '0' WHEN n < 5 THEN '1-4' WHEN n < 20 THEN '5-19'
                     WHEN n < 100 THEN '20-99' ELSE '100+' END AS interactions,
                count(*) AS items FROM p GROUP BY 1""", "item_interactions.csv")
    # New items entering the catalog: RetailRocket ships weekly catalog snapshots, so an item's
    # first snapshot date is when it entered the catalog (the first snapshot is the initial stock).
    q("""SELECT first_seen::DATE AS snapshot_day, count(*) AS new_items
         FROM catalog WHERE first_seen > (SELECT min(first_seen) FROM catalog)
         GROUP BY 1 ORDER BY 1""", "catalog_new_items.csv")
    q("""SELECT event_type, count(*) AS events FROM events_clean GROUP BY 1 ORDER BY 2 DESC""", "event_mix.csv")

    print(f"{result['verdict']} ({result['score']}/100); outputs in data/public/intake/")


if __name__ == "__main__":
    main()
