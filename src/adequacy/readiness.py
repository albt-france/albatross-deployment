"""Data-adequacy analysis and the Readiness score.

Question answered: "is this customer's data ready for the first training run?"
Metrics come from sql/02_adequacy.sql (run on the cleaned events). Each metric is
compared with explicit thresholds and graded:
    PASS (1 point) / CONDITION (0.5 point) / FAIL (0 point)
The verdict:
    - any FAIL on a critical criterion           -> NOT YET
    - otherwise any CONDITION or non-critical FAIL -> GO WITH CONDITIONS
    - otherwise                                   -> GO
The score (0-100) is the weighted share of points, to track progress between data drops.

Thresholds are this playbook's rules of thumb, not Albatross's internal criteria.
"""
from __future__ import annotations

from dataclasses import dataclass

import duckdb
import pandas as pd

from .checks import SQL_DIR, read_named_blocks


def compute_metrics(con: duckdb.DuckDBPyConnection) -> dict:
    """Run every block of 02_adequacy.sql on events_clean + catalog; return one flat dict."""
    metrics: dict = {}
    for _, sql in read_named_blocks(SQL_DIR / "02_adequacy.sql"):
        df = con.execute(sql).df()
        metrics.update(df.iloc[0].to_dict())

    # Catalog richness depends on which columns the customer sent, so it is done here.
    cols = [r[0] for r in con.execute("DESCRIBE catalog").fetchall()]
    attr_cols = [c for c in cols if c != "item_id"]
    metrics["catalog_attribute_columns"] = len(attr_cols)
    if "category_id" in cols:
        metrics["share_items_with_category"] = con.execute(
            "SELECT avg((category_id IS NOT NULL)::INT) FROM catalog").fetchone()[0]
    else:
        metrics["share_items_with_category"] = 0.0
    if "n_properties" in cols:
        metrics["median_properties_per_item"] = con.execute(
            "SELECT median(n_properties) FROM catalog").fetchone()[0]
    return metrics


@dataclass
class Criterion:
    key: str            # metric name
    label: str
    pass_at: float      # >= pass_at -> PASS (or <= when lower_is_better)
    cond_at: float      # >= cond_at -> CONDITION, else FAIL
    critical: bool
    weight: float
    fmt: str            # how to print the value
    why: str            # why it matters for a sequential recommender
    condition: str      # what we ask for if not PASS
    lower_is_better: bool = False


CRITERIA: list[Criterion] = [
    Criterion("days_covered", "History length (days)", 56, 28, True, 2, "{:.0f}",
              "Enough weeks to train on the past and validate on a later hold-out.",
              "Send at least 8 weeks of history (4 weeks minimum)."),
    Criterion("median_events_per_day", "Median events per day", 50_000, 5_000, False, 1, "{:,.0f}",
              "Volume drives how fast the model learns new items and how fast an A/B test reads.",
              "Add more surfaces or event types (clicks on all pages, not only the homepage)."),
    Criterion("share_users_2plus", "Users with 2+ events", 0.40, 0.20, False, 1, "{:.0%}",
              "A sequence model learns from what users do next; single-event users teach it little.",
              "Send a stable user id (logged-in id or long-lived cookie) so visits link together."),
    Criterion("share_sessions_2plus", "Sessions with 2+ events", 0.40, 0.20, True, 2, "{:.0%}",
              "In-session intent is the core signal; it needs sessions with several events.",
              "Check that every page view / click is tracked, not only the first one."),
    Criterion("unknown_item_rate", "Events on items missing from catalog", 0.01, 0.10, True, 2, "{:.1%}",
              "Items without catalog data cannot get content embeddings nor be served.",
              "Send a full catalog export, including sold and delisted items.", lower_is_better=True),
    Criterion("share_items_with_category", "Catalog items with a category", 0.95, 0.70, False, 1, "{:.0%}",
              "Content (category, text, images) is what makes new items recommendable before their first click.",
              "Add category and title/description fields to the catalog feed."),
    Criterion("share_beyond_views", "Events beyond views (cart, purchase)", 0.01, 0.002, False, 1, "{:.1%}",
              "Purchase-type signals let us optimise and measure revenue, not only clicks.",
              "Add add-to-cart and purchase events (clicks alone are enough to start)."),
    Criterion("share_catalog_under5", "Catalog items with < 5 interactions", 0.50, 1.01, False, 1, "{:.0%}",
              "A large cold catalog is normal in marketplaces; it makes content-based cold start essential.",
              "Make sure every listing has a title, category and image URL: content is what "
              "makes the long tail and brand-new items recommendable.", lower_is_better=True),
    Criterion("blocking_checks", "Blocking intake checks", 0, 0, True, 2, "{:.0f}",
              "A blocking data-quality issue would bias training and the A/B readout.",
              "Fix the blocking checks listed in the intake report.", lower_is_better=True),
]


def grade(c: Criterion, value: float) -> str:
    if c.lower_is_better:
        if value <= c.pass_at:
            return "PASS"
        return "CONDITION" if value < c.cond_at else "FAIL"
    if value >= c.pass_at:
        return "PASS"
    return "CONDITION" if value >= c.cond_at else "FAIL"


def rule_text(c: Criterion) -> str:
    """Human-readable threshold, printed next to each criterion in the report."""
    p, f = c.fmt.format(c.pass_at), c.fmt.format(c.cond_at)
    if c.key == "blocking_checks":
        return "pass = 0, else fail"
    if c.lower_is_better:
        return f"pass <= {p}; above: condition" if c.cond_at > 1 else f"pass <= {p}; fail >= {f}"
    return f"pass >= {p}; fail < {f}"


def readiness(metrics: dict, checks: pd.DataFrame) -> dict:
    """Grade every criterion and return the scorecard, verdict, score and customer message."""
    m = dict(metrics)
    unknown = checks.loc[checks["check"] == "check_unknown_items", "rate"]
    m["unknown_item_rate"] = float(unknown.iloc[0]) if len(unknown) else 0.0
    m["blocking_checks"] = int((checks["status"] == "BLOCKER").sum())

    rows, points, weights = [], 0.0, 0.0
    for c in CRITERIA:
        value = float(m.get(c.key, 0) or 0)
        g = grade(c, value)
        points += {"PASS": 1, "CONDITION": 0.5, "FAIL": 0}[g] * c.weight
        weights += c.weight
        rows.append({"criterion": c.label, "value": c.fmt.format(value), "raw_value": value,
                     "threshold": rule_text(c), "grade": g, "critical": c.critical,
                     "why_it_matters": c.why, "condition": "" if g == "PASS" else c.condition})
    card = pd.DataFrame(rows)

    critical_fail = ((card["grade"] == "FAIL") & card["critical"]).any()
    if critical_fail:
        verdict = "NOT YET"
    elif (card["grade"] != "PASS").any():
        verdict = "GO WITH CONDITIONS"
    else:
        verdict = "GO"
    score = round(100 * points / weights)
    return {"verdict": verdict, "score": score, "scorecard": card,
            "message": customer_message(verdict, score, card, m)}


def customer_message(verdict: str, score: int, card: pd.DataFrame, m: dict) -> str:
    """Short e-mail-style summary for the customer's PM and engineering lead."""
    conds = card[card["grade"] != "PASS"]
    lines = [
        "Hi both,",
        "",
        f"Thanks for the data drop. We validated {int(m.get('n_events', 0)):,} events from "
        f"{int(m.get('n_users', 0)):,} users over {int(m.get('days_covered', 0))} days.",
        f"Our readiness verdict is **{verdict}** (score {score}/100).",
    ]
    if verdict == "GO":
        lines.append("Everything we need is in place: we start the first training run this week.")
    elif verdict == "GO WITH CONDITIONS":
        lines.append("We can start training now. In parallel, could you help us with the points below "
                     "before the A/B test starts (week 5)?")
    else:
        lines.append("We need the points below fixed before the first training run; "
                     "this keeps the 7-week timeline realistic. Happy to walk your engineer through them.")
    for _, r in conds.iterrows():
        lines.append(f"- {r['criterion']} ({r['value']}): {r['condition']}")
    lines += ["", "The full intake report is attached. Shall we review it in Thursday's check-in?", "", "Best,"]
    return "\n".join(lines)
