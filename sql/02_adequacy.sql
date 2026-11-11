-- =============================================================================
-- 02_adequacy.sql : "is this customer's data ready for training?"
-- =============================================================================
-- Runs on the CLEANED events (events_clean, built by 01_intake_checks.sql) and the
-- catalog. Each block returns ONE row of named metrics; src/adequacy/readiness.py
-- compares them with explicit thresholds.
-- Sessions = consecutive events of a user with gaps of 30 minutes or less.
-- =============================================================================


-- name: volume
SELECT count(*)                                              AS n_events,
       count(DISTINCT user_id)                               AS n_users,
       count(DISTINCT item_id)                               AS n_items_with_events,
       min(ts)                                               AS first_ts,
       max(ts)                                               AS last_ts,
       date_diff('day', min(ts), max(ts)) + 1                AS days_covered
FROM events_clean;


-- name: daily
-- Median daily volume, ignoring the first and last day (often partial).
WITH d AS (
    SELECT ts::DATE AS day, count(*) AS n FROM events_clean GROUP BY 1
)
SELECT median(n) AS median_events_per_day,
       min(n)    AS min_events_per_day,
       max(n)    AS max_events_per_day
FROM d
WHERE day > (SELECT min(day) FROM d) AND day < (SELECT max(day) FROM d);


-- name: users
WITH u AS (SELECT user_id, count(*) AS n FROM events_clean GROUP BY 1)
SELECT median(n)                       AS median_events_per_user,
       quantile_cont(n, 0.9)           AS p90_events_per_user,
       avg((n >= 2)::INT)              AS share_users_2plus,
       avg((n >= 5)::INT)              AS share_users_5plus
FROM u;


-- name: sessions
WITH ordered AS (
    SELECT user_id, ts,
           CASE WHEN ts - lag(ts) OVER (PARTITION BY user_id ORDER BY ts) <= INTERVAL 30 MINUTE
                THEN 0 ELSE 1 END AS new_session
    FROM events_clean
),
numbered AS (
    SELECT user_id, sum(new_session) OVER (PARTITION BY user_id ORDER BY ts) AS session_no
    FROM ordered
),
s AS (SELECT user_id, session_no, count(*) AS len FROM numbered GROUP BY 1, 2)
SELECT count(*)                  AS n_sessions,
       median(len)               AS median_session_length,
       avg(len)                  AS mean_session_length,
       avg((len >= 2)::INT)      AS share_sessions_2plus,
       avg((len >= 5)::INT)      AS share_sessions_5plus
FROM s;


-- name: density
-- Share of the user x item matrix that has at least one interaction.
SELECT count(*)                                                   AS n_pairs,
       count(*) / ((SELECT count(DISTINCT user_id) FROM events_clean)::DOUBLE
                 * (SELECT count(DISTINCT item_id) FROM events_clean)) AS density
FROM (SELECT DISTINCT user_id, item_id FROM events_clean);


-- name: event_mix
SELECT avg((lower(event_type) IN ('addtocart','add_to_cart','cart'))::INT)         AS share_cart,
       avg((lower(event_type) IN ('transaction','purchase','order'))::INT)         AS share_purchase,
       avg((lower(event_type) NOT IN ('view','click','detail_view','impression_click'))::INT) AS share_beyond_views
FROM events_clean;


-- name: cold_items
-- Interactions per CATALOG item over the whole period (0 for items never touched).
WITH per_item AS (
    SELECT c.item_id, count(e.item_id) AS n
    FROM (SELECT DISTINCT item_id FROM catalog) c
    LEFT JOIN events_clean e USING (item_id)
    GROUP BY 1
)
SELECT count(*)                      AS n_catalog_items,
       avg((n = 0)::INT)             AS share_catalog_zero,
       avg((n < 5)::INT)             AS share_catalog_under5
FROM per_item;


-- name: concentration
-- Share of events that land on the top 1 % most-interacted items.
WITH per_item AS (SELECT item_id, count(*) AS n FROM events_clean GROUP BY 1),
ranked AS (
    SELECT n, row_number() OVER (ORDER BY n DESC) AS rk, count(*) OVER () AS k FROM per_item
)
SELECT sum(n) FILTER (WHERE rk <= greatest(1, k // 100)) / sum(n)::DOUBLE AS share_top1pct
FROM ranked;


-- name: new_items
-- Arrival rate of new items: items whose FIRST event happens after a 14-day warm-up
-- (before that, "first seen" just means "first seen since the export started").
WITH first_ev AS (SELECT item_id, min(ts) AS first_ts FROM events_clean GROUP BY 1),
bounds AS (SELECT min(ts) + INTERVAL 14 DAY AS warm, max(ts) AS last FROM events_clean)
SELECT count(*) FILTER (WHERE first_ts >= warm)                                   AS n_new_items,
       count(*) FILTER (WHERE first_ts >= warm)
           / greatest(1, date_diff('day', any_value(warm), any_value(last)))::DOUBLE AS new_items_per_day,
       count(*) FILTER (WHERE first_ts >= warm) / count(*)::DOUBLE                AS share_items_new
FROM first_ev, bounds;
