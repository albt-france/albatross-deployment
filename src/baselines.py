"""Offline baselines on a time split of the REAL dataset (page 4 of the report).

Runs sql/03_baselines.sql, then computes for each baseline:
    Recall@20 : share of test transitions where the true next item is in the top 20
    NDCG@20   : same, but a hit at rank 1 counts more than a hit at rank 20 (1 / log2(rank + 1))
    Coverage  : share of the items people interacted with in the test weeks that the
                baseline recommends at least once
and the same metrics by segment (new / cold / warm target item, short / longer
context, new / returning user).

Run: python src/baselines.py
"""
from __future__ import annotations

from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

from adequacy.checks import read_named_blocks

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / "data" / "work"
OUT = ROOT / "data" / "public" / "baselines"
SPLIT = "2015-08-21"  # train: 2015-05-03 .. 2015-08-20 (16 weeks) / test: 2015-08-21 .. 2015-09-18 (4 weeks)
K = 20
BASELINES = {"rank_pop_global": "(a) Global popularity",
             "rank_pop_recent": "(b) Recent popularity (7 days)",
             "rank_covis": "(c) Co-visitation + popularity fill"}


def metrics(df: pd.DataFrame, col: str) -> dict:
    rank = df[col]
    hit = rank.notna() & (rank <= K)
    ndcg = np.where(hit, 1 / np.log2(rank.fillna(K + 1) + 1), 0.0)
    return {"recall@20": hit.mean(), "ndcg@20": ndcg.mean(), "n_targets": len(df)}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    con.execute("SET TimeZone = 'UTC'")
    con.execute(f"CREATE VIEW events_clean AS SELECT * FROM '{(WORK / 'events_clean.parquet').as_posix()}'")
    con.execute(f"CREATE TABLE params AS SELECT TIMESTAMP '{SPLIT}' AS split_ts")
    for name, sql in read_named_blocks(ROOT / "sql" / "03_baselines.sql"):
        con.execute(sql)
        print("done:", name)

    ranks = con.execute("SELECT * FROM ranks").df()
    test_items = con.execute(f"SELECT count(DISTINCT item_id) FROM events_clean WHERE ts >= TIMESTAMP '{SPLIT}'").fetchone()[0]

    # Coverage: distinct items each baseline actually shows over the test transitions
    served = {
        "rank_pop_global": con.execute("SELECT count(DISTINCT item_id) FROM pop_global").fetchone()[0],
        "rank_pop_recent": con.execute("SELECT count(DISTINCT r.item_id) FROM pop_recent r "
                                       "WHERE r.day IN (SELECT day FROM targets)").fetchone()[0],
        "rank_covis": con.execute("SELECT count(DISTINCT item_id) FROM covis_lists").fetchone()[0],
    }
    overall = []
    for col, label in BASELINES.items():
        m = metrics(ranks, col)
        m.update({"baseline": label, "items_recommended": served[col], "coverage": served[col] / test_items})
        overall.append(m)
    overall = pd.DataFrame(overall)[["baseline", "recall@20", "ndcg@20", "coverage", "items_recommended", "n_targets"]]
    overall.to_csv(OUT / "results_overall.csv", index=False)

    ranks["prev_segment"] = np.where(ranks["n_neighbours"] == 0, "current item has no co-visitation",
                                     "current item has co-visitation")
    seg_rows = []
    for seg_col in ("target_segment", "context_segment", "user_segment", "prev_segment"):
        for seg, part in ranks.groupby(seg_col):
            for col, label in BASELINES.items():
                m = metrics(part, col)
                m.update({"dimension": seg_col.replace("_segment", ""), "segment": seg, "baseline": label})
                seg_rows.append(m)
    seg = pd.DataFrame(seg_rows)[["dimension", "segment", "baseline", "recall@20", "ndcg@20", "n_targets"]]
    seg.to_csv(OUT / "results_by_segment.csv", index=False)

    mix = (ranks.groupby("target_segment").size() / len(ranks)).rename("share").reset_index()
    mix.to_csv(OUT / "target_mix.csv", index=False)
    no_nb = float((ranks["n_neighbours"] == 0).mean())
    facts = pd.DataFrame([
        {"fact": "split_date", "value": SPLIT},
        {"fact": "test_transitions", "value": len(ranks)},
        {"fact": "test_sessions", "value": ranks["session_id"].nunique()},
        {"fact": "items_interacted_in_test", "value": test_items},
        {"fact": "share_prev_item_without_covis_neighbour", "value": round(no_nb, 4)},
        {"fact": "share_targets_new_item", "value": round(float((ranks["target_segment"] == "new item (0 in train)").mean()), 4)},
        {"fact": "covis_pairs_kept", "value": con.execute("SELECT count(*) FROM covis").fetchone()[0]},
    ])
    facts.to_csv(OUT / "facts.csv", index=False)
    print(overall.to_string(index=False))
    print(seg.to_string(index=False))
    print(facts.to_string(index=False))


if __name__ == "__main__":
    main()
