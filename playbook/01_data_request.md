# 01 · Data request e-mail (kickoff, day 1)

**To:** customer PM, customer engineering lead
**Subject:** Evaluation week 1 – data we need, format and timeline

---

Hi [PM name], hi [engineering lead name],

Great to kick off. To keep us on the 7-week plan, here is everything we need for weeks 1–2 (data integration).

**1. Events (required).** One row per user action. Clicks only is fine to start; we can add more types after the pilot.

| column | type | example | notes |
|---|---|---|---|
| `user_id` | text | `u_83kd02` | stable id: logged-in id, or a long-lived cookie / device id |
| `event_type` | text | `view`, `click`, `add_to_cart`, `purchase` | please send us the list of types you use |
| `item_id` | text | `48211907` | must match `item_id` in the catalog |
| `timestamp` | Unix ms **or** ISO-8601 with offset | `1741946400000` / `2026-03-14T10:00:00Z` | please confirm the time zone |

**2. Catalog (required).** One row per listing, **including sold and delisted items** from the history period.
`item_id`, `title`, `category_id` (+ parent category), `price`, `created_at`, `status`, `image_url` if available.

**3. History.** At least **8 weeks** of events (4 weeks minimum), plus a live feed through the Event API from day 1.

**4. Delivery.** Through the Catalog and Event APIs (live from day 1), or a one-off file drop (CSV or Parquet) to the shared bucket. Example files in the expected format are attached (`examples/events.csv`, `examples/catalog.csv`).

**Timeline**

| when | what | owner |
|---|---|---|
| Day 3 | Sample file (1 day of events + catalog extract) | your engineering lead |
| Day 5 | Our intake report on the sample: format OK / fixes needed | us |
| Day 8 | Full history drop + live event feed | your engineering lead |
| Day 10 | Intake report + readiness verdict (Go / Go with conditions / Not yet) | us |

We validate every drop with the same automated checks (schema, duplicates, unknown items, gaps, bots) and share the report with you, so there are no surprises in week 3.

Questions on anything above: happy to do a 20-minute call with your engineer.

Best,
[name] · Deployment Strategist
