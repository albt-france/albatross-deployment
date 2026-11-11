"""Tests for the adequacy toolkit, on a small synthetic data drop with known anomalies."""
from pathlib import Path

import pandas as pd
import pytest

from adequacy.__main__ import main
from adequacy.checks import apply_filters, load_inputs, run_checks, status_for, RULES
from adequacy.readiness import CRITERIA, compute_metrics, grade, readiness

from sample_data import INJECTED, write_sample


@pytest.fixture(scope="module")
def sample(tmp_path_factory):
    return write_sample(tmp_path_factory.mktemp("drop"))


@pytest.fixture(scope="module")
def checked(sample):
    con, schema = load_inputs(*sample)
    checks = run_checks(con, schema).set_index("check")
    waterfall = apply_filters(con).set_index("step")
    return con, checks, waterfall


def test_schema_and_timezone_are_ok_for_unix_ms(checked):
    _, checks, _ = checked
    assert checks.loc["schema_columns", "status"] == "OK"
    assert checks.loc["schema_timezone", "status"] == "OK"
    assert "ms" in checks.loc["schema_timezone", "detail"]


def test_detects_every_injected_anomaly(checked):
    _, c, _ = checked
    assert c.loc["check_exact_duplicates", "affected"] == INJECTED["exact_duplicates"]
    assert c.loc["check_near_duplicates", "affected"] == INJECTED["near_duplicates"]
    assert c.loc["check_unknown_items", "affected"] == INJECTED["unknown_item_events"]
    assert c.loc["check_missing_days", "affected"] == INJECTED["missing_days"]
    assert c.loc["check_heavy_users", "detail"].startswith("1 users")
    assert c.loc["check_bursts", "detail"].startswith("1 users")
    assert c.loc["check_purchase_without_view", "affected"] >= INJECTED["purchases_without_view"]
    assert c.loc["check_missing_days", "status"] == "WARNING"


def test_filter_waterfall_removes_what_was_injected(checked):
    _, _, w = checked
    assert w.loc["exact duplicates", "removed"] == INJECTED["exact_duplicates"]
    assert w.loc["repeats < 1 s", "removed"] == INJECTED["near_duplicates"]
    assert w.loc["bot users (rules 1-2)", "removed"] == INJECTED["bot1_events"] + INJECTED["bot2_events"]


def test_missing_column_is_blocking(tmp_path):
    events, catalog = write_sample(tmp_path)
    df = pd.read_csv(events).drop(columns=["event_type"])
    df.to_csv(events, index=False)
    _, schema = load_inputs(events, catalog)
    assert schema[0]["status"] == "BLOCKER"
    assert "event_type" in schema[0]["detail"]


def test_text_timestamps_without_zone_raise_a_warning(tmp_path):
    events, catalog = write_sample(tmp_path)
    df = pd.read_csv(events)
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms").dt.strftime("%Y-%m-%d %H:%M:%S.%f")
    df.to_csv(events, index=False)
    con, schema = load_inputs(events, catalog)
    tz = [r for r in schema if r["check"] == "schema_timezone"][0]
    assert tz["status"] == "WARNING"
    parse = [r for r in schema if r["check"] == "schema_timestamp_parse"][0]
    assert parse["affected"] == 0


def test_status_thresholds():
    rule = RULES["check_unknown_items"]  # warn 1 %, block 10 %
    assert status_for(rule, 0, 100) == "OK"
    assert status_for(rule, 5, 100) == "WARNING"
    assert status_for(rule, 10, 100) == "BLOCKER"


def test_grade_and_verdict(checked):
    con, checks, _ = checked
    history = next(c for c in CRITERIA if c.key == "days_covered")
    assert grade(history, 60) == "PASS" and grade(history, 30) == "CONDITION" and grade(history, 10) == "FAIL"
    metrics = compute_metrics(con)
    assert metrics["days_covered"] == 60
    res = readiness(metrics, checks.reset_index())
    assert res["verdict"] in {"GO", "GO WITH CONDITIONS", "NOT YET"}
    # a blocking check is a critical failure -> NOT YET
    blocked = checks.reset_index().copy()
    blocked.loc[0, "status"] = "BLOCKER"
    assert readiness(metrics, blocked)["verdict"] == "NOT YET"


def test_cli_writes_reports(sample, tmp_path):
    out = tmp_path / "reports"
    assert main(["check", "--events", str(sample[0]), "--catalog", str(sample[1]), "--out", str(out)]) == 0
    for f in ("intake_report.md", "intake_report.html", "checks.csv", "filtering.csv", "readiness.csv"):
        assert (out / f).exists()
    assert "Readiness" in (out / "intake_report.md").read_text(encoding="utf-8")
