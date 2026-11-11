"""Small SYNTHETIC data drop with known, injected anomalies (used by the tests and the README demo).

Run `python tests/sample_data.py examples` to write examples/events.csv and examples/catalog.csv.

What is injected (so the tests know the right answer):
    3 exact duplicate rows
    4 near-duplicates (same user/item/type 0.4 s later)
    7 events on item 'i999', which is not in the catalog
    1 missing day (day 30)
    user 'bot1': 150 views in one day, 30 s apart        -> bot rule 1
    user 'bot2': 25 views inside one minute, 2 s apart   -> bot rule 2
    2 purchases with no earlier view of the item
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

START = pd.Timestamp("2026-01-01")
N_DAYS = 60
MISSING_DAY = 30
INJECTED = {"exact_duplicates": 3, "near_duplicates": 4, "unknown_item_events": 7, "missing_days": 1,
            "bot1_events": 150, "bot2_events": 25, "purchases_without_view": 2}


def make_sample() -> tuple[pd.DataFrame, pd.DataFrame]:
    rng = np.random.default_rng(42)
    items = [f"i{k}" for k in range(1, 301)]
    rows = []
    for day in range(N_DAYS):
        if day == MISSING_DAY:
            continue
        for u in rng.choice(200, size=20, replace=False):
            t = START + pd.Timedelta(days=day, hours=int(rng.integers(8, 20)))
            for _ in range(3):  # a 3-view session, events 1-5 minutes apart
                item = items[int(rng.integers(0, 300))]
                rows.append((f"u{u}", "view", item, t))
                if rng.random() < 0.15:
                    t += pd.Timedelta(seconds=30)
                    rows.append((f"u{u}", "addtocart", item, t))
                    if rng.random() < 0.5:
                        t += pd.Timedelta(seconds=60)
                        rows.append((f"u{u}", "transaction", item, t))
                t += pd.Timedelta(seconds=int(rng.integers(60, 300)))
    ev = pd.DataFrame(rows, columns=["user_id", "event_type", "item_id", "ts"])

    extra = []
    # unknown item: 7 views on i999 by normal users, on different days
    for k in range(7):
        extra.append((f"u{k}", "view", "i999", START + pd.Timedelta(days=k + 1, hours=23)))
    # bot 1: 150 views in one day, 30 s apart
    for k in range(150):
        extra.append(("bot1", "view", items[k % 300], START + pd.Timedelta(days=10, hours=1, seconds=30 * k)))
    # bot 2: 25 views inside one minute
    for k in range(25):
        extra.append(("bot2", "view", items[k], START + pd.Timedelta(days=12, hours=3, seconds=2 * k)))
    # 2 purchases with no earlier view (user 'buyer' never views anything)
    extra.append(("buyer", "transaction", "i5", START + pd.Timedelta(days=20, hours=22)))
    extra.append(("buyer", "transaction", "i6", START + pd.Timedelta(days=21, hours=22)))
    ev = pd.concat([ev, pd.DataFrame(extra, columns=ev.columns)], ignore_index=True)

    # near-duplicates: 4 rows repeated 0.4 s later
    near = ev.iloc[[10, 20, 30, 40]].copy()
    near["ts"] = near["ts"] + pd.Timedelta(milliseconds=400)
    # exact duplicates: 3 rows sent twice
    dup = ev.iloc[[50, 60, 70]].copy()
    ev = pd.concat([ev, near, dup], ignore_index=True).sort_values("ts", kind="stable")

    # Unix milliseconds, as many trackers send them
    ev["timestamp"] = (ev["ts"] - pd.Timestamp("1970-01-01")) // pd.Timedelta(milliseconds=1)
    events = ev[["user_id", "event_type", "item_id", "timestamp"]].reset_index(drop=True)

    catalog = pd.DataFrame({"item_id": items,
                            "category_id": [None if k < 10 else f"c{k % 12}" for k in range(300)],
                            "title": [f"Item {k}" for k in range(1, 301)]})
    return events, catalog


def write_sample(folder: str | Path) -> tuple[Path, Path]:
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    events, catalog = make_sample()
    events.to_csv(folder / "events.csv", index=False)
    catalog.to_csv(folder / "catalog.csv", index=False)
    return folder / "events.csv", folder / "catalog.csv"


if __name__ == "__main__":
    e, c = write_sample(sys.argv[1] if len(sys.argv) > 1 else "examples")
    print(f"wrote {e} and {c}")
