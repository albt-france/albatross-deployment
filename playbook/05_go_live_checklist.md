# 05 · Go-live checklist (start of week 5: A/B test launch day)

## D-3 to D-1
- [ ] Analysis plan signed off by customer PM (primary metric, guardrails, duration, stopping rules, SRM rule).
- [ ] Randomisation: user-level, sticky hash of `user_id` + experiment salt; 50 / 50; same salt on web and apps.
- [ ] A/A check on 24 h of traffic: split 50.0 % ± 0.2, no metric difference.
- [ ] Exposure logging: one `feed_impression` event per visitor and arm, on every platform (web, iOS, Android).
- [ ] Fallback tested: if the Prediction API times out (> 150 ms), the page shows the incumbent feed.
- [ ] Monitoring dashboard live; alert rules and on-call names shared with the customer.
- [ ] Bot filter rules from the intake applied to A/B metrics (same rules for both arms).

## D-day
- [ ] Ramp: 5 % of traffic for 2 h → check latency, errors, fallback, exposure counts → 50 %.
- [ ] SRM check after the first 2 h and at the end of the day.
- [ ] Short message to customer PM + engineer: "Live at 50 %, health green, next check tomorrow 10:00".

## Every day of the test
- [ ] Health: latency, errors, fallback, event lag, catalog freshness, coverage.
- [ ] SRM by day and by device / app version.
- [ ] **No decision on the primary metric before day 21** (no peeking). Stop early only for a guardrail breach or a SEV1.

## End of test (day 21)
- [ ] Freeze data, run the pre-registered analysis (`src/ab_readout.py`).
- [ ] Readout with business case; decision: production / extend / stop.
- [ ] If production: keep a 5 % holdout for 3 months to confirm revenue per visitor.
