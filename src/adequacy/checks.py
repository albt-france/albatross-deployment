"""Intake checks: is the customer's first data drop usable, and what must be cleaned?

The SQL lives in sql/01_intake_checks.sql (one block per check, easy to re-run by
hand in DuckDB). This module:
  1. loads the events and catalog files into DuckDB and normalises the timestamp,
  2. runs every "check_*" block and turns the counts into OK / WARNING / BLOCKER
     using the thresholds below,
  3. runs the "filter_*" blocks in order and records how many rows each one removes.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import duckdb
import pandas as pd

SQL_DIR = Path(__file__).resolve().parents[2] / "sql"
REQUIRED_EVENT_COLUMNS = ["user_id", "event_type", "item_id", "timestamp"]


# --------------------------------------------------------------------------------------
# Thresholds. "rate" = affected / base; "count" = affected rows.
# warn: at or above -> WARNING ; block: at or above -> BLOCKER (None = never blocking).
# They are the playbook's own rules of thumb, written down so the customer can challenge them.
# --------------------------------------------------------------------------------------
@dataclass
class Rule:
    label: str
    kind: str          # "rate" or "count"
    warn: float
    block: float | None
    advice: str        # what we tell the customer / do when the check is not OK


RULES: dict[str, Rule] = {
    "check_null_fields": Rule("Rows missing user, item, type or timestamp", "rate", 1e-9, 0.01,
        "Drop these rows; above 1 % ask the customer to fix the export."),
    "check_timestamp_range": Rule("Timestamps outside 2000-01-01 .. now", "rate", 1e-9, 0.01,
        "Usually a seconds/milliseconds mix-up: confirm the unit with the customer."),
    "check_event_types": Rule("Event types outside the agreed list", "rate", 1e-9, None,
        "Agree on the meaning of each event type before training."),
    "check_unknown_items": Rule("Events on items missing from the catalog", "rate", 0.01, 0.10,
        "Ask for a full catalog export (including sold / delisted items)."),
    "check_items_without_events": Rule("Catalog items with no event in the period", "rate", 0.50, None,
        "Expected in a marketplace: these items depend on content embeddings (cold start)."),
    "check_catalog_duplicate_ids": Rule("Duplicate item ids in the catalog", "rate", 1e-9, 0.01,
        "Keep the latest version of each item; ask which one is authoritative."),
    "check_exact_duplicates": Rule("Exact duplicate events", "rate", 0.001, 0.05,
        "Remove duplicates; ask the customer's engineer whether the tracker retries."),
    "check_near_duplicates": Rule("Same event repeated within 1 second", "rate", 0.005, 0.05,
        "Collapse to one event (double taps / reloads)."),
    "check_missing_days": Rule("Days with no event at all", "count", 1, 3,
        "Ask whether tracking was down or the export is incomplete."),
    "check_volume_drops": Rule("Days below 50 % of the previous 7-day median", "count", 1, None,
        "Check each date with the customer (outage, partial export, holiday)."),
    "check_heavy_users": Rule("Events from users with >100 events in one day (bot rule 1)", "rate", 0.01, 0.10,
        "Exclude these users from training and from A/B metrics."),
    "check_bursts": Rule("Events from users with >=20 events in one minute (bot rule 2)", "rate", 0.005, 0.10,
        "Exclude these users from training and from A/B metrics."),
    "check_purchase_without_view": Rule("Purchases with no earlier view of the item", "rate", 0.05, 0.50,
        "Some is normal (other device, e-mail link); a high share means views are missing."),
    "check_cart_without_view": Rule("Add-to-carts with no earlier view of the item", "rate", 0.05, 0.50,
        "Same as above: check whether every surface sends view events."),
}


def read_named_blocks(path: Path) -> list[tuple[str, str]]:
    """Split a .sql file on '-- name: xxx' markers -> [(name, sql), ...] in file order."""
    blocks, name, lines = [], None, []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip().startswith("-- name:"):
            if name:
                blocks.append((name, "\n".join(lines)))
            name, lines = line.split(":", 1)[1].strip(), []
        elif name:
            lines.append(line)
    if name:
        blocks.append((name, "\n".join(lines)))
    return blocks


def _source(path: str | Path) -> str:
    """DuckDB table function for a CSV or Parquet file."""
    p = Path(path).as_posix()
    return f"read_parquet('{p}')" if p.endswith(".parquet") else f"read_csv('{p}', all_varchar=false)"


def load_inputs(events_path: str | Path, catalog_path: str | Path) -> tuple[duckdb.DuckDBPyConnection, list[dict]]:
    """Load files, check the schema, build the events_raw (UTC) and catalog views.

    Returns the connection and the list of schema-level check results.
    """
    con = duckdb.connect()
    con.execute("SET TimeZone = 'UTC'")
    con.execute(f"CREATE VIEW events_input AS SELECT * FROM {_source(events_path)}")
    con.execute(f"CREATE VIEW catalog_input AS SELECT * FROM {_source(catalog_path)}")
    results = []

    # --- schema: required columns -------------------------------------------------------
    cols = {r[0]: r[1] for r in con.execute("DESCRIBE events_input").fetchall()}
    missing = [c for c in REQUIRED_EVENT_COLUMNS if c not in cols]
    cat_cols = [r[0] for r in con.execute("DESCRIBE catalog_input").fetchall()]
    if "item_id" not in cat_cols:
        missing.append("catalog.item_id")
    results.append(_result("schema_columns", "Required columns present", 1 if missing else 0, 1,
                           "missing: " + ", ".join(missing) if missing else "user_id, event_type, item_id, timestamp + catalog.item_id",
                           "BLOCKER" if missing else "OK",
                           "Send the customer the expected format (see playbook/01_data_request.md)."))
    if missing:
        return con, results

    # --- schema: timestamp type and time zone ---------------------------------------------
    ts_type = cols["timestamp"].upper()
    if any(t in ts_type for t in ("INT", "DOUBLE", "DECIMAL", "FLOAT")):
        # Unix time: guess the unit from the order of magnitude (ms ~ 1.4e12, s ~ 1.4e9).
        med = con.execute("SELECT median(timestamp) FROM events_input").fetchone()[0] or 0
        unit = "ms" if med > 1e11 else "s"
        expr = "epoch_ms(CAST(timestamp AS BIGINT))" if unit == "ms" else "to_timestamp(CAST(timestamp AS DOUBLE))::TIMESTAMP"
        tz_note, tz_status = f"Unix time in {unit}: UTC by definition", "OK"
    elif "TIMESTAMP WITH TIME ZONE" in ts_type:
        expr, tz_note, tz_status = "timestamp::TIMESTAMP", "timestamps carry a time zone, converted to UTC", "OK"
    elif "TIMESTAMP" in ts_type or "DATE" in ts_type:
        expr = "CAST(timestamp AS TIMESTAMP)"
        tz_note, tz_status = "no time zone in the data: assumed UTC, to confirm with the customer", "WARNING"
    else:  # text: try to parse, and remember how many rows fail
        expr = "TRY_CAST(timestamp AS TIMESTAMP)"
        tz_note, tz_status = "text timestamps without explicit zone: assumed UTC, to confirm", "WARNING"
    results.append(_result("schema_timezone", "Timestamp type and time zone", 0, 1,
                           f"column type {ts_type}; {tz_note}", tz_status,
                           "Confirm the time zone in writing before computing daily metrics."))

    con.execute(f"""
        CREATE VIEW events_raw AS
        SELECT CAST(user_id AS VARCHAR) AS user_id,
               CAST(event_type AS VARCHAR) AS event_type,
               CAST(item_id AS VARCHAR) AS item_id,
               {expr} AS ts
        FROM events_input
    """)
    # Item ids are compared as text on both sides, whatever type each file uses.
    con.execute("CREATE VIEW catalog AS SELECT * EXCLUDE (item_id), CAST(item_id AS VARCHAR) AS item_id FROM catalog_input")

    bad = con.execute("""SELECT count(*) FILTER (WHERE timestamp IS NOT NULL AND ts IS NULL), count(*)
                         FROM (SELECT timestamp, {e} AS ts FROM events_input)""".format(e=expr)).fetchone()
    status = "OK" if bad[0] == 0 else ("BLOCKER" if bad[0] / bad[1] >= 0.01 else "WARNING")
    results.append(_result("schema_timestamp_parse", "Timestamps that cannot be parsed", bad[0], bad[1], None, status,
                           "Ask for ISO-8601 timestamps with a UTC offset, or Unix milliseconds."))
    return con, results


def _result(check, label, affected, base, detail, status, advice) -> dict:
    return {"check": check, "label": label, "affected": int(affected or 0), "base": int(base or 0),
            "rate": (affected or 0) / base if base else 0.0, "detail": detail or "",
            "status": status, "recommendation": "" if status == "OK" else advice}


def status_for(rule: Rule, affected: int, base: int) -> str:
    """Compare a count with its rule -> 'OK' / 'WARNING' / 'BLOCKER'."""
    value = affected if rule.kind == "count" else (affected / base if base else 0.0)
    if rule.block is not None and value >= rule.block:
        return "BLOCKER"
    if value >= rule.warn:
        return "WARNING"
    return "OK"


def run_checks(con: duckdb.DuckDBPyConnection, schema_results: list[dict] | None = None) -> pd.DataFrame:
    """Run every check_* block of 01_intake_checks.sql and grade it."""
    rows = list(schema_results or [])
    for name, sql in read_named_blocks(SQL_DIR / "01_intake_checks.sql"):
        if not name.startswith("check_"):
            continue
        affected, base, detail = con.execute(sql).fetchone()
        rule = RULES[name]
        status = status_for(rule, affected or 0, base or 0)
        if name == "check_items_without_events" and status != "OK":
            status = "WARNING"  # informative: never blocking
        rows.append(_result(name, rule.label, affected, base, detail, status, rule.advice))
    return pd.DataFrame(rows)


def apply_filters(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Run the filter_* blocks in order; return the row count after each step (waterfall)."""
    steps = [("raw events", con.execute("SELECT count(*) FROM events_raw").fetchone()[0])]
    table_after = {"filter_1_valid_rows": "events_f1", "filter_2_exact_duplicates": "events_f2",
                   "filter_3_near_duplicates": "events_f3", "filter_4_bots": "events_clean"}
    labels = {"filter_1_valid_rows": "invalid rows", "filter_2_exact_duplicates": "exact duplicates",
              "filter_3_near_duplicates": "repeats < 1 s", "filter_4_bots": "bot users (rules 1-2)"}
    for name, sql in read_named_blocks(SQL_DIR / "01_intake_checks.sql"):
        if name.startswith("filter_"):
            con.execute(sql)
            steps.append((labels[name], con.execute(f"SELECT count(*) FROM {table_after[name]}").fetchone()[0]))
    df = pd.DataFrame(steps, columns=["step", "rows_after"])
    df["removed"] = (-df["rows_after"].diff()).fillna(0).astype(int)
    df["share_removed"] = df["removed"] / df["rows_after"].iloc[0]
    return df
