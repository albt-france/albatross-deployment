# 04 · Escalate or resolve? Decision grid

Principle: **resolve alone** what is reversible, inside my scope and has no customer-visible impact; **escalate** as soon as users, revenue, the timeline or trust are at stake, or when I am not sure. Escalating early with facts is cheap; escalating late is expensive.

| situation | threshold (from the monitoring rules) | severity | I resolve | I escalate to | within |
|---|---|---|---|---|---|
| p95 latency high | > 150 ms for 10 min | SEV1 | check that fallback serves the incumbent feed | Albatross on-call engineer, then customer PM | immediately |
| Error rate high | > 1 % for 10 min | SEV1 | — | Albatross on-call engineer | immediately |
| Event stream down | < 20 % of same time yesterday for 15 min | SEV2 | pause A/B metric collection for the window | customer engineering lead | 30 min |
| Catalog feed stalled | freshness > 30 min (was 60) | SEV2 | confirm which side stopped | customer engineering lead + Albatross data engineer | 1 h |
| A/B sample-ratio mismatch | chi-square p < 0.001 (daily) | SEV2 | find the affected cohort (day, device, app version) | Albatross data scientist; customer PM informed | same day |
| Duplicate events | > 5 % of events for 15 min | SEV3 | de-duplicate at ingestion; ask engineer about retries | — (weekly report) | next check-in |
| Bot / single client flood | one client > 5 % of requests | SEV3 | block or tag the client, exclude from A/B | — (weekly report) | same day |
| Data drop late | 2 working days late | — | follow-up e-mail (`02_follow_up.md`) | customer PM if no answer after 5 days | week |
| Customer disputes a number | any | — | re-run the query, share SQL + definitions | Albatross data scientist if definitions differ | 48 h |
| Scope or contract question (pricing, new surface) | any | — | — | Albatross account lead / sales | same day |

**Escalation message template (3 lines):** what happened (fact + number) · impact (users, A/B, timeline) · what I have already done and what I need from you, by when.
