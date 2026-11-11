"""Command line entry point.

    python -m adequacy check --events events.csv --catalog catalog.csv [--out reports] [--format md|html|both] [--name "Customer"]

Writes intake_report.md / .html, plus checks.csv, filtering.csv and readiness.csv
so the numbers can be reused in a dashboard.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .checks import apply_filters, load_inputs, run_checks
from .readiness import compute_metrics, readiness
from .report import to_html, to_markdown


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="adequacy", description="Data intake checks and readiness score.")
    sub = parser.add_subparsers(dest="command", required=True)
    chk = sub.add_parser("check", help="validate a data drop and score its readiness")
    chk.add_argument("--events", required=True, help="events file (.csv or .parquet): user_id, event_type, item_id, timestamp")
    chk.add_argument("--catalog", required=True, help="catalog file (.csv or .parquet): item_id + attributes")
    chk.add_argument("--out", default="reports", help="output folder (default: reports)")
    chk.add_argument("--format", choices=["md", "html", "both"], default="both")
    chk.add_argument("--name", default="New customer", help="name printed in the report title")
    args = parser.parse_args(argv)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    con, schema = load_inputs(args.events, args.catalog)
    if any(r["status"] == "BLOCKER" and r["check"] == "schema_columns" for r in schema):
        import pandas as pd
        checks = pd.DataFrame(schema)
        waterfall, result = None, None
    else:
        checks = run_checks(con, schema)
        waterfall = apply_filters(con)
        metrics = compute_metrics(con)
        result = readiness(metrics, checks)
        waterfall.to_csv(out / "filtering.csv", index=False)
        result["scorecard"].to_csv(out / "readiness.csv", index=False)
        clean = {k: (v.isoformat() if hasattr(v, "isoformat") else (float(v) if v is not None else None))
                 for k, v in metrics.items()}
        (out / "metrics.json").write_text(json.dumps(clean, indent=2), encoding="utf-8")
    checks.to_csv(out / "checks.csv", index=False)

    if args.format in ("md", "both"):
        (out / "intake_report.md").write_text(to_markdown(args.name, checks, waterfall, result), encoding="utf-8")
    if args.format in ("html", "both"):
        (out / "intake_report.html").write_text(to_html(args.name, checks, waterfall, result), encoding="utf-8")

    counts = checks["status"].value_counts().to_dict()
    print(f"checks: {counts}")
    if result:
        print(f"readiness: {result['verdict']} ({result['score']}/100)")
    print(f"report written to {out}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
