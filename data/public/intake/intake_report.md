# Data intake report: RetailRocket public dataset, treated as a new customer's first data drop

_Generated 2026-11-11 15:18 UTC by the adequacy toolkit._

**Checks:** 11 OK · 6 warning · 0 blocking

## Readiness: **GO WITH CONDITIONS** (score 73/100)

## 1. Intake checks

| Status | Check | Rows affected | Share | Detail | Recommendation |
|---|---|---:|---:|---|---|
| OK | Required columns present | 0 | 0.00% | user_id, event_type, item_id, timestamp + catalog.item_id |  |
| OK | Timestamp type and time zone | 0 | 0.00% | column type BIGINT; Unix time in ms: UTC by definition |  |
| OK | Timestamps that cannot be parsed | 0 | 0.00% |  |  |
| OK | Rows missing user, item, type or timestamp | 0 | 0.00% |  |  |
| OK | Timestamps outside 2000-01-01 .. now | 0 | 0.00% | range 2015-05-03 03:00:04.384 -> 2015-09-18 02:59:47.788 (UTC) |  |
| OK | Event types outside the agreed list | 0 | 0.00% | view=2664312, addtocart=69332, transaction=22457 |  |
| WARNING | Events on items missing from the catalog | 255,585 | 9.27% | 49815 distinct item ids missing from the catalog | Ask for a full catalog export (including sold / delisted items). |
| WARNING | Catalog items with no event in the period | 231,807 | 55.58% |  | Expected in a marketplace: these items depend on content embeddings (cold start). |
| OK | Duplicate item ids in the catalog | 0 | 0.00% |  |  |
| OK | Exact duplicate events | 460 | 0.02% |  |  |
| OK | Same event repeated within 1 second | 4,705 | 0.17% |  |  |
| OK | Days with no event at all | 0 | 0.00% |  |  |
| WARNING | Days below 50 % of the previous 7-day median | 2 | 1.44% | 2015-09-17 (10128 vs median 20427), 2015-09-18 (1528 vs median 16859) | Check each date with the customer (outage, partial export, holiday). |
| WARNING | Events from users with >100 events in one day (bot rule 1) | 93,012 | 3.37% | 129 users flagged | Exclude these users from training and from A/B metrics. |
| OK | Events from users with >=20 events in one minute (bot rule 2) | 3,640 | 0.13% | 14 users flagged |  |
| WARNING | Purchases with no earlier view of the item | 2,633 | 11.72% |  | Some is normal (other device, e-mail link); a high share means views are missing. |
| WARNING | Add-to-carts with no earlier view of the item | 19,188 | 27.68% |  | Same as above: check whether every surface sends view events. |

## 2. Filtering rules and their effect

| Step | Rows removed | Share removed | Rows after |
|---|---:|---:|---:|
| raw events | 0 | 0.00% | 2,756,101 |
| invalid rows | 0 | 0.00% | 2,756,101 |
| exact duplicates | 460 | 0.02% | 2,755,641 |
| repeats < 1 s | 4,705 | 0.17% | 2,750,936 |
| bot users (rules 1-2) | 93,361 | 3.39% | 2,657,575 |

## 3. Readiness scorecard

| Grade | Criterion | Value | Threshold | Critical | Why it matters |
|---|---|---:|---|---|---|
| PASS | History length (days) | 139 | pass >= 56; fail < 28 | yes | Enough weeks to train on the past and validate on a later hold-out. |
| CONDITION | Median events per day | 19,836 | pass >= 50,000; fail < 5,000 | no | Volume drives how fast the model learns new items and how fast an A/B test reads. |
| CONDITION | Users with 2+ events | 29% | pass >= 40%; fail < 20% | no | A sequence model learns from what users do next; single-event users teach it little. |
| CONDITION | Sessions with 2+ events | 21% | pass >= 40%; fail < 20% | yes | In-session intent is the core signal; it needs sessions with several events. |
| CONDITION | Events on items missing from catalog | 9.3% | pass <= 1.0%; fail >= 10.0% | yes | Items without catalog data cannot get content embeddings nor be served. |
| PASS | Catalog items with a category | 100% | pass >= 95%; fail < 70% | no | Content (category, text, images) is what makes new items recommendable before their first click. |
| PASS | Events beyond views (cart, purchase) | 2.9% | pass >= 1.0%; fail < 0.2% | no | Purchase-type signals let us optimise and measure revenue, not only clicks. |
| CONDITION | Catalog items with < 5 interactions | 81% | pass <= 50%; above: condition | no | A large cold catalog is normal in marketplaces; it makes content-based cold start essential. |
| PASS | Blocking intake checks | 0 | pass = 0, else fail | yes | A blocking data-quality issue would bias training and the A/B readout. |

## 4. Message to the customer

```text
Hi both,

Thanks for the data drop. We validated 2,657,575 events from 1,407,445 users over 139 days.
Our readiness verdict is GO WITH CONDITIONS (score 73/100).
We can start training now. In parallel, could you help us with the points below before the A/B test starts (week 5)?
- Median events per day (19,836): Add more surfaces or event types (clicks on all pages, not only the homepage).
- Users with 2+ events (29%): Send a stable user id (logged-in id or long-lived cookie) so visits link together.
- Sessions with 2+ events (21%): Check that every page view / click is tracked, not only the first one.
- Events on items missing from catalog (9.3%): Send a full catalog export, including sold and delisted items.
- Catalog items with < 5 interactions (81%): Make sure every listing has a title, category and image URL: content is what makes the long tail and brand-new items recommendable.

The full intake report is attached. Shall we review it in Thursday's check-in?

Best,
```
