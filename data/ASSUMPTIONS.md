# Assumptions

Everything on the report pages tagged **SIMULATED** rests on the assumptions below. Change a value in the script named in brackets and
re-run the pipeline to see how the conclusions move.

## Simulated customer (`src/simulate.py`, `src/business_case.py`)
| Assumption | Value | Why this value |
|---|---|---|
| Size | 3 M monthly active users | inside Albatross's public GROWTH tier (1-5 M MAU) |
| Unique homepage visitors during the 3-week test | 2,000,000 | enough to read a +5 % conversion lift at 80 % power (see `data/public/ab_design/`) |
| Returning / new visitors | 55 % / 45 % | typical marketplace mix; only used for segments |
| Mobile / desktop | 70 % / 30 % | typical marketplace mix; only used for segments and the SRM bug |
| Chance a visitor comes back in a later test week | 45 % returning, 20 % new | gives about 1.3 active weeks per visitor |
| Annual GMV | EUR 250 M | order of magnitude for a 3 M MAU marketplace (assumption, not a public figure) |
| Share of GMV from visitors exposed to the homepage feed | 50 % | assumption; the sensitivity table varies GMV |
| Take rate (marketplace commission) | 12 % | assumption; sensitivity uses 8 / 12 / 15 % |
| One-off integration effort on the customer side | EUR 20,000 | 2 people part-time for 7 weeks |
| Evaluation fee | EUR 0 | not public; Albatross says it is waived for fast starts |

## Calibration on the REAL dataset (`data/public/ab_design/base_rates.json`)
Per-visitor rates over 3-week windows of the cleaned RetailRocket events: engaged visitors (2+ views) 25.9 %, add-to-cart 2.59 %,
purchase 0.80 %, 1.72 views per visitor (sd 3.38). The simulated control group reproduces them: 1.67 feed clicks per visitor
(sd 3.61), 27.6 % engaged, 2.59 % add-to-cart, 0.81 % conversion. Feed clicks stand in for RetailRocket views (the dataset has no feed).

## True effects built into the simulation (kept below published results, on purpose)
| Metric | Simulated true effect | Published by Albatross customers |
|---|---|---|
| Feed clicks per visitor | +34 / +22 / +18 % (returning) and +24 / +15 / +12 % (new) in weeks 1 / 2 / 3: a novelty effect that fades | +84 % (OfferUp) and +119 % (Wallapop) homepage engagement |
| Add-to-cart and purchase | +5 % | +15 % purchase intent (OfferUp), +11 % sold items (Wallapop) |
| Average order value | unchanged (lognormal, mean EUR 45, sigma 0.8) | n/a |
| Page load time | +6 ms (feed call) on 820 ms | n/a |
| Bounce rate | -1.2 pt on 38 % | n/a |

The measured effects (page 7) differ from these true values because of sampling noise; that is the point of the confidence intervals.

## Injected problems
| Problem | When | What the analysis must do |
|---|---|---|
| Sample-ratio mismatch | test day 9: 35 % of treatment **mobile** visitors lost by a logging bug | detect with a daily chi-square, find the cohort, exclude day 9 from both arms |
| Event stream cut | day 3, 02:00-05:00 | alert, pause A/B collection for the window |
| Latency spike | day 8, 19:00-19:45 (p95 ~420 ms, errors 3 %, fallback 22 %) | page on-call |
| Duplicate events | day 11, 09:00-15:00 (~40 % duplicates) | de-duplicate, ask about tracker retries |
| Catalog feed stalled | day 14 06:00 -> day 15 12:00 | escalate to both data owners |
| Bot traffic | day 18, 01:00-05:00 (one client = 27 % of requests) | block, exclude from A/B metrics |

## Live-health baseline (`src/simulate.py`)
Feed requests ~230 / minute at peak in the treatment arm (daily cycle, +12 % at weekends), 9 tracked events per request, p50 / p95 latency
18 / 46 ms, error rate 0.05 %, fallback 0.6 %, event lag p95 ~2 s, new listing recommendable in ~4 min, catalog coverage rising from 55 % to
75 % as the model warms up. Predictions per month at 100 % traffic = median requests per minute x 60 x 24 x 30 x 2.

## Playbook thresholds (not Albatross's)
Intake rules (`src/adequacy/checks.py`), readiness criteria (`src/adequacy/readiness.py`) and alert rules (`src/health_monitor.py`)
are this study's own rules of thumb, written down so a customer or a colleague can challenge them.
