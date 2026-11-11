"""Turn the raw RetailRocket files into the customer "triplet" format.

Albatross asks a new customer for event triplets (user ID, event type, item ID,
with a timestamp) plus catalog access. This script reshapes the public
RetailRocket dataset into exactly that shape, so the rest of the study can treat
it as a customer's first data drop.

Input  (not redistributed, CC BY-NC-SA 4.0): data/raw/retailrocket/*.csv
Output (local, git-ignored):                 data/work/events.parquet, data/work/catalog.parquet

Run: python src/load_dataset.py
"""
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "retailrocket"
WORK = ROOT / "data" / "work"


def main() -> None:
    WORK.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    con.execute("SET TimeZone = 'UTC'")

    # 1) Events -> triplets + timestamp.
    #    RetailRocket stores Unix time in milliseconds. We keep it as sent (a real
    #    customer would too) and let the toolkit detect the unit and convert to UTC.
    #    Rows are untouched (duplicates included): cleaning is the job of the
    #    intake checks, not of the loader.
    con.execute(f"""
        COPY (
            SELECT
                CAST(visitorid AS VARCHAR)  AS user_id,
                event                       AS event_type,
                CAST(itemid AS VARCHAR)     AS item_id,
                timestamp                   AS timestamp
            FROM read_csv('{(RAW / 'events.csv').as_posix()}')
        ) TO '{(WORK / 'events.parquet').as_posix()}' (FORMAT parquet)
    """)

    # 2) Catalog. RetailRocket publishes item properties as weekly snapshots
    #    (timestamp, itemid, property, value). Most property names and values are
    #    hashed; only 'categoryid' and 'available' are readable.
    #    We build one row per item with:
    #      - its latest category and availability flag,
    #      - the number of distinct properties it has (catalog richness),
    #      - the first time it appears in the catalog (to measure new-item arrivals).
    props = [(RAW / f).as_posix() for f in ("item_properties_part1.csv", "item_properties_part2.csv")]
    con.execute(f"""
        CREATE TEMP TABLE props AS
        SELECT itemid, property, value, epoch_ms(timestamp) AS ts
        FROM read_csv({props}, columns={{'timestamp':'BIGINT','itemid':'BIGINT','property':'VARCHAR','value':'VARCHAR'}})
    """)
    con.execute(f"""
        CREATE TEMP TABLE cats AS
        SELECT CAST(categoryid AS VARCHAR) AS category_id,
               CAST(parentid AS VARCHAR)   AS parent_category_id
        FROM read_csv('{(RAW / 'category_tree.csv').as_posix()}')
    """)
    con.execute(f"""
        COPY (
            WITH latest_cat AS (
                SELECT itemid, arg_max(value, ts) AS category_id
                FROM props WHERE property = 'categoryid' GROUP BY itemid
            ),
            latest_avail AS (
                SELECT itemid, arg_max(value, ts) AS available
                FROM props WHERE property = 'available' GROUP BY itemid
            ),
            per_item AS (
                SELECT itemid,
                       count(DISTINCT property) AS n_properties,
                       min(ts)                  AS first_seen
                FROM props GROUP BY itemid
            )
            SELECT CAST(p.itemid AS VARCHAR) AS item_id,
                   c.category_id,
                   t.parent_category_id,
                   CAST(a.available AS INTEGER) AS available,
                   p.n_properties,
                   p.first_seen
            FROM per_item p
            LEFT JOIN latest_cat   c USING (itemid)
            LEFT JOIN latest_avail a USING (itemid)
            LEFT JOIN cats         t ON t.category_id = c.category_id
        ) TO '{(WORK / 'catalog.parquet').as_posix()}' (FORMAT parquet)
    """)

    for name in ("events", "catalog"):
        n = con.execute(f"SELECT count(*) FROM '{(WORK / (name + '.parquet')).as_posix()}'").fetchone()[0]
        print(f"{name}: {n:,} rows -> data/work/{name}.parquet")


if __name__ == "__main__":
    main()
