"""Deployment-health monitoring rules on the SIMULATED live series (page 6).

Each rule is a plain threshold that must hold for a few consecutive 5-minute buckets
(to avoid paging on a single noisy point). When a rule fires we open an incident with
its severity, who owns the fix, and whether we escalate (see playbook/04_escalation_grid.md).
The script then compares detected incidents with what was injected (incidents_truth.csv).
Run: python src/health_monitor.py   (after src/simulate.py)
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SIM = ROOT / "data" / "simulated"

# metric, condition, consecutive 5-min buckets, severity, owner, action
RULES = [
    ("events_per_min", "lt_rel", 0.2, 3, "SEV2", "Customer engineering lead",
     "Event stream down: escalate to the customer's engineering lead; pause A/B metric collection for the window."),
    ("latency_p95_ms", "gt", 150, 2, "SEV1", "Albatross on-call engineer",
     "Escalate at once to on-call; confirm fallback serves the incumbent feed; inform customer PM."),
    ("duplicate_share", "gt", 0.05, 3, "SEV3", "Customer engineering lead",
     "Ask the customer's engineer to check tracker retries; de-duplicate at ingestion; no escalation."),
    ("catalog_freshness_min", "gt", 60, 3, "SEV2", "Customer engineering lead + Albatross data engineer",
     "Catalog feed stalled: new listings not recommendable. Escalate to both data owners."),
    ("top_client_share", "gt", 0.05, 3, "SEV3", "Deployment Strategist (resolve)",
     "Bot traffic: block / tag the client id, exclude it from A/B metrics, tell the customer in the weekly report."),
]


def detect(health: pd.DataFrame) -> pd.DataFrame:
    h = health.copy()
    h["ts"] = pd.to_datetime(h["ts"])
    # "lt_rel": below 20 % of the same 5-minute slot one day earlier (traffic is seasonal)
    h["events_ref"] = h["events_per_min"].shift(288)
    rows = []
    for metric, kind, thr, k, sev, owner, action in RULES:
        if kind == "gt":
            breach = h[metric] > thr
        else:
            breach = h[metric] < thr * h["events_ref"]
        # alert when the breach holds for k consecutive buckets
        run = breach.astype(int).groupby((~breach).cumsum()).cumsum()
        fired = run >= k
        # group consecutive breached buckets into one incident
        block = (breach != breach.shift()).cumsum()
        for _, seg in h[breach].groupby(block[breach]):
            if not fired.loc[seg.index].any():
                continue
            first_alert = h.loc[fired.loc[seg.index][fired.loc[seg.index]].index[0], "ts"]
            rows.append({"metric": metric, "rule": f"{metric} {'>' if kind == 'gt' else '< 20% of yesterday'} "
                                                   f"{thr if kind == 'gt' else ''} for {k} x 5 min".replace("  ", " "),
                         "breach_start": seg["ts"].iloc[0], "alert_at": first_alert,
                         "breach_end": seg["ts"].iloc[-1] + pd.Timedelta(minutes=5),
                         "peak": seg[metric].max() if kind == "gt" else seg[metric].min(),
                         "severity": sev, "owner": owner, "action": action})
    return pd.DataFrame(rows).sort_values("alert_at").reset_index(drop=True)


def main() -> None:
    health = pd.read_csv(SIM / "health_5min.csv")
    truth = pd.read_csv(SIM / "incidents_truth.csv", parse_dates=["start", "end"])
    inc = detect(health)
    # Match each detection to the injected incident it overlaps
    def match(r):
        hit = truth[(truth.start <= r.breach_end) & (truth.end >= r.breach_start)]
        return hit["incident"].iloc[0] if len(hit) else "false alarm"
    inc["injected_incident"] = inc.apply(match, axis=1)
    inc["minutes_to_alert"] = ((inc["alert_at"] - inc["breach_start"]).dt.total_seconds() / 60).round(0)
    # Time from the real start of the problem (known here because we injected it) to the alert
    starts = truth.set_index("incident")["start"]
    inc["minutes_from_true_start"] = inc.apply(
        lambda r: round((r.alert_at - starts[r.injected_incident]).total_seconds() / 60)
        if r.injected_incident in starts else None, axis=1)
    out = SIM / "incident_log.csv"
    inc.to_csv(out, index=False)
    found = set(inc["injected_incident"]) - {"false alarm"}
    print(inc[["alert_at", "severity", "metric", "injected_incident", "minutes_to_alert", "owner"]].to_string(index=False))
    print(f"\ninjected: {len(truth)} | detected: {len(found)} | false alarms: {(inc.injected_incident == 'false alarm').sum()}")


if __name__ == "__main__":
    main()
