# 03 · Weekly deployment report (example: end of week 6)

**To:** customer PM + engineering lead · **Cc:** Albatross account lead
**Format:** one page, same structure every week. Status colours: 🟢 on track · 🟠 at risk · 🔴 blocked.

---

## Evaluation status – week 6 of 7 · overall 🟢

| workstream | status | this week |
|---|---|---|
| Data feeds | 🟠 | Catalog feed stalled 30 h (Sun–Mon); fixed Monday 12:00 by your team. Detection took 70 min: we lower the alert threshold from 60 to 30 min. |
| Model & serving | 🟢 | p95 latency 46 ms (target < 150 ms). One 45-min spike on day 8, fallback served the incumbent feed, error rate back to 0.05 %. |
| A/B test | 🟢 | Day 15 of 21. Split back to 50.0 / 50.0 after the day-9 logging bug (mobile release); day-9 visitors excluded from both arms, as agreed. |
| Data quality | 🟢 | Duplicate events on day 11 (6 h, ~40 % of events sent twice by tracker retries); de-duplicated at ingestion, your engineer is checking the retry setting. |

**Key numbers (no peeking rule: shown for health only, the readout is at day 21)**
- Visitors in test so far: 1.4 M · requests served: 99.4 % by the model, 0.6 % fallback
- Catalog coverage: 72 % of live listings recommended at least once a day this week (56 % on day 1)

**Risks**
1. *Novelty effect:* week-1 engagement lifts are usually inflated; we will judge on the full 3 weeks and show week 3 on its own.
2. *Revenue readability:* order values vary a lot, so revenue per visitor may stay inconclusive in 3 weeks. Conversion is the agreed business metric; we propose a holdout after launch to confirm revenue.

**Next steps**
| what | who | when |
|---|---|---|
| Confirm catalog feed monitoring on your side | your engineering lead | Wed |
| Prepare readout deck (results + business case) | us | day 22 |
| Readout meeting with your PM and finance | both | day 23 |

**Decisions needed from you:** none this week.
