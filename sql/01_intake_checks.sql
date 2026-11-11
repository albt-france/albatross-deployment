-- =============================================================================
-- 01_intake_checks.sql : data-intake checks for a customer's first data drop
-- =============================================================================
-- Runs in DuckDB. The adequacy toolkit (src/adequacy/checks.py) loads this file,
-- splits it on the "-- name:" markers and runs each block in order.
--
-- Expected input views (created by the toolkit):
--   events_raw (user_id VARCHAR, event_type VARCHAR, item_id VARCHAR, ts TIMESTAMP)  -- UTC
--   catalog    (item_id VARCHAR, ... any attribute columns ...)
--
-- Every CHECK block returns ONE row:  affected (rows concerned), base (denominator), detail (text).
-- The status (OK / WARNING / BLOCKER) is decided in Python from explicit thresholds,
-- so the SQL stays easy to read and to re-run by hand.
--
-- Event-type families (edit here for another customer's naming):
--   view-like : 'view', 'click', 'detail_view', 'impression_click'
--   cart      : 'addtocart', 'add_to_cart', 'cart'
--   purchase  : 'transaction', 'purchase', 'order'
-- =============================================================================


-- name: check_null_fields
-- Rows that miss one of the four triplet fields cannot be used at all.
SELECT count(*) FILTER (WHERE user_id IS NULL OR item_id IS NULL
                           OR event_type IS NULL OR ts IS NULL) AS affected,
       count(*)                                                 AS base,
       NULL                                                     AS detail
FROM events_raw;


-- name: check_timestamp_range
-- Timestamps in the future or before 2000 usually mean a unit error
-- (seconds vs milliseconds) or a default value such as 1970-01-01.
SELECT count(*) FILTER (WHERE ts > now()::TIMESTAMP + INTERVAL 1 DAY
                           OR ts < TIMESTAMP '2000-01-01')   AS affected,
       count(*)                                              AS base,
       'range ' || min(ts)::VARCHAR || ' -> ' || max(ts)::VARCHAR || ' (UTC)' AS detail
FROM events_raw;


-- name: check_event_types
-- Event-type mix. Unknown types are not an error, but we must agree with the
-- customer on what each one means before training.
WITH mix AS (
    SELECT event_type, count(*) AS n FROM events_raw GROUP BY event_type
)
SELECT sum(n) FILTER (WHERE lower(event_type) NOT IN
          ('view','click','detail_view','impression_click',
           'addtocart','add_to_cart','cart',
           'transaction','purchase','order'))                  AS affected,
       sum(n)                                                  AS base,
       string_agg(event_type || '=' || n::VARCHAR, ', ' ORDER BY n DESC) AS detail
FROM mix;


-- name: check_unknown_items
-- Events on items that are not in the catalog: no content to describe them,
-- and the model cannot serve them. Often a catalog export that is late or filtered.
SELECT count(*) FILTER (WHERE c.item_id IS NULL)                       AS affected,
       count(*)                                                        AS base,
       count(DISTINCT e.item_id) FILTER (WHERE c.item_id IS NULL)::VARCHAR
           || ' distinct item ids missing from the catalog'            AS detail
FROM events_raw e
LEFT JOIN (SELECT DISTINCT item_id FROM catalog) c USING (item_id);


-- name: check_items_without_events
-- Catalog items nobody interacted with in the period ("cold" items).
-- Expected in a marketplace; it tells us how much the content layer will matter.
SELECT count(*) FILTER (WHERE e.item_id IS NULL) AS affected,
       count(*)                                  AS base,
       NULL                                      AS detail
FROM (SELECT DISTINCT item_id FROM catalog) c
LEFT JOIN (SELECT DISTINCT item_id FROM events_raw) e USING (item_id);


-- name: check_catalog_duplicate_ids
SELECT count(*) - count(DISTINCT item_id) AS affected,
       count(*)                           AS base,
       NULL                               AS detail
FROM catalog;


-- name: check_exact_duplicates
-- Same user, item, event type and timestamp: the same event sent twice
-- (retries in the tracking pipeline).
SELECT count(*) - count(DISTINCT (user_id, item_id, event_type, ts)) AS affected,
       count(*)                                                      AS base,
       NULL                                                          AS detail
FROM events_raw;


-- name: check_near_duplicates
-- Same user, item and event type less than 1 second after the previous one
-- (double taps, page reloads). Exact duplicates (0 s) are counted above.
WITH ordered AS (
    SELECT ts - lag(ts) OVER (PARTITION BY user_id, item_id, event_type ORDER BY ts) AS gap
    FROM events_raw
)
SELECT count(*) FILTER (WHERE gap > INTERVAL 0 SECOND AND gap < INTERVAL 1 SECOND) AS affected,
       count(*)                                                                     AS base,
       NULL                                                                         AS detail
FROM ordered;


-- name: check_missing_days
-- Calendar days between the first and last event with no event at all.
WITH days AS (
    SELECT unnest(generate_series(min(ts)::DATE, max(ts)::DATE, INTERVAL 1 DAY))::DATE AS d
    FROM events_raw
),
seen AS (SELECT DISTINCT ts::DATE AS d FROM events_raw)
SELECT count(*) FILTER (WHERE s.d IS NULL)                                   AS affected,
       count(*)                                                              AS base,
       coalesce(string_agg(days.d::VARCHAR, ', ') FILTER (WHERE s.d IS NULL), '') AS detail
FROM days LEFT JOIN seen s USING (d);


-- name: check_volume_drops
-- Days whose volume is below half the median of the 7 previous days:
-- a tracking outage, a partial export, or a partial last day.
WITH daily AS (
    SELECT ts::DATE AS d, count(*) AS n FROM events_raw GROUP BY 1
),
w AS (
    SELECT d, n,
           median(n) OVER (ORDER BY d ROWS BETWEEN 7 PRECEDING AND 1 PRECEDING) AS med7,
           count(*)  OVER (ORDER BY d ROWS BETWEEN 7 PRECEDING AND 1 PRECEDING) AS k
    FROM daily
)
SELECT count(*) FILTER (WHERE k = 7 AND n < 0.5 * med7)                         AS affected,
       count(*)                                                                 AS base,
       coalesce(string_agg(d::VARCHAR || ' (' || n::VARCHAR || ' vs median ' || med7::BIGINT::VARCHAR || ')', ', ')
                FILTER (WHERE k = 7 AND n < 0.5 * med7), '')                    AS detail
FROM w;


-- name: check_heavy_users
-- Bot rule 1: a user with more than 100 events on a single day.
-- A person browsing a shop rarely does that; crawlers and scripts do.
WITH per_day AS (
    SELECT user_id, ts::DATE AS d, count(*) AS n FROM events_raw GROUP BY 1, 2
),
flagged AS (SELECT DISTINCT user_id FROM per_day WHERE n > 100)
SELECT (SELECT count(*) FROM events_raw WHERE user_id IN (SELECT user_id FROM flagged)) AS affected,
       (SELECT count(*) FROM events_raw)                                                AS base,
       (SELECT count(*) FROM flagged)::VARCHAR || ' users flagged'                      AS detail;


-- name: check_bursts
-- Bot rule 2: a user with 20 or more events inside the same clock minute.
WITH per_min AS (
    SELECT user_id, date_trunc('minute', ts) AS m, count(*) AS n FROM events_raw GROUP BY 1, 2
),
flagged AS (SELECT DISTINCT user_id FROM per_min WHERE n >= 20)
SELECT (SELECT count(*) FROM events_raw WHERE user_id IN (SELECT user_id FROM flagged)) AS affected,
       (SELECT count(*) FROM events_raw)                                                AS base,
       (SELECT count(*) FROM flagged)::VARCHAR || ' users flagged'                      AS detail;


-- name: check_purchase_without_view
-- Purchases with no earlier view/click of the same item by the same user.
-- Some is normal (purchase from another device, e-mail link); a lot means
-- the view stream is incomplete.
WITH buys AS (
    SELECT user_id, item_id, ts FROM events_raw
    WHERE lower(event_type) IN ('transaction','purchase','order')
),
first_view AS (
    SELECT user_id, item_id, min(ts) AS first_ts FROM events_raw
    WHERE lower(event_type) IN ('view','click','detail_view','impression_click')
    GROUP BY 1, 2
)
SELECT count(*) FILTER (WHERE v.first_ts IS NULL OR v.first_ts > b.ts) AS affected,
       count(*)                                                        AS base,
       NULL                                                            AS detail
FROM buys b LEFT JOIN first_view v USING (user_id, item_id);


-- name: check_cart_without_view
WITH carts AS (
    SELECT user_id, item_id, ts FROM events_raw
    WHERE lower(event_type) IN ('addtocart','add_to_cart','cart')
),
first_view AS (
    SELECT user_id, item_id, min(ts) AS first_ts FROM events_raw
    WHERE lower(event_type) IN ('view','click','detail_view','impression_click')
    GROUP BY 1, 2
)
SELECT count(*) FILTER (WHERE v.first_ts IS NULL OR v.first_ts > c.ts) AS affected,
       count(*)                                                        AS base,
       NULL                                                            AS detail
FROM carts c LEFT JOIN first_view v USING (user_id, item_id);


-- =============================================================================
-- FILTERING RULES (applied in this order; the toolkit counts rows after each step)
-- =============================================================================

-- name: filter_1_valid_rows
CREATE OR REPLACE TABLE events_f1 AS
SELECT * FROM events_raw
WHERE user_id IS NOT NULL AND item_id IS NOT NULL AND event_type IS NOT NULL AND ts IS NOT NULL
  AND ts BETWEEN TIMESTAMP '2000-01-01' AND now()::TIMESTAMP + INTERVAL 1 DAY;


-- name: filter_2_exact_duplicates
CREATE OR REPLACE TABLE events_f2 AS
SELECT DISTINCT user_id, event_type, item_id, ts FROM events_f1;


-- name: filter_3_near_duplicates
CREATE OR REPLACE TABLE events_f3 AS
SELECT user_id, event_type, item_id, ts
FROM (
    SELECT *, ts - lag(ts) OVER (PARTITION BY user_id, item_id, event_type ORDER BY ts) AS gap
    FROM events_f2
)
WHERE gap IS NULL OR gap >= INTERVAL 1 SECOND;


-- name: filter_4_bots
-- Removes every event of a user flagged by bot rule 1 or bot rule 2.
CREATE OR REPLACE TABLE events_clean AS
WITH r1 AS (
    SELECT DISTINCT user_id FROM (
        SELECT user_id, ts::DATE AS d, count(*) AS n FROM events_f3 GROUP BY 1, 2
    ) WHERE n > 100
),
r2 AS (
    SELECT DISTINCT user_id FROM (
        SELECT user_id, date_trunc('minute', ts) AS m, count(*) AS n FROM events_f3 GROUP BY 1, 2
    ) WHERE n >= 20
)
SELECT * FROM events_f3
WHERE user_id NOT IN (SELECT user_id FROM r1 UNION SELECT user_id FROM r2);
