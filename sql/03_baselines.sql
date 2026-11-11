-- =============================================================================
-- 03_baselines.sql : simple offline baselines on a time split (REAL dataset)
-- =============================================================================
-- Task: inside a test-period session, the user just looked at item P.
--       Which item will they look at next (a different item)? Each baseline returns
--       a ranked list of 20 items; we check where the true next item lands.
-- Input : events_clean (user_id, event_type, item_id, ts), parameter table params(split_ts)
-- Train : everything before split_ts. Test: sessions that start on/after split_ts.
-- Baselines:
--   (a) global popularity  : the 20 most-interacted items in the training period
--   (b) recent popularity  : the 20 most-interacted items in the 7 days before the target's day
--   (c) co-visitation      : "users who viewed P in a session also viewed ..." (training sessions),
--                            topped up with (b) when P has fewer than 20 neighbours
-- These are NOT Albatross's models: they are the usual "incumbent" logic a
-- marketplace already runs, used to show where a session-aware model must do better.
-- =============================================================================


-- name: sessions
-- A session = events of one user with gaps of 30 minutes or less.
CREATE OR REPLACE TABLE sess AS
WITH o AS (
    SELECT user_id, item_id, ts,
           CASE WHEN ts - lag(ts) OVER (PARTITION BY user_id ORDER BY ts) <= INTERVAL 30 MINUTE
                THEN 0 ELSE 1 END AS new_s
    FROM events_clean
)
SELECT user_id, item_id, ts,
       user_id || '-' || sum(new_s) OVER (PARTITION BY user_id ORDER BY ts)::VARCHAR AS session_id
FROM o;


-- name: session_start
CREATE OR REPLACE TABLE sess_start AS
SELECT session_id, min(ts) AS start_ts FROM sess GROUP BY 1;


-- name: train_counts
-- Interactions per item in the training period (popularity + cold/warm label).
CREATE OR REPLACE TABLE train_counts AS
SELECT item_id, count(*) AS n FROM events_clean
WHERE ts < (SELECT split_ts FROM params) GROUP BY 1;


-- name: targets
-- Test transitions: previous item P -> next different item T, in sessions starting after the split.
-- Consecutive repeats of the same item are collapsed first. Ties on the timestamp are
-- broken by item_id so the result is identical on every run.
CREATE OR REPLACE TABLE targets AS
WITH test_sess AS (
    SELECT s.* FROM sess s JOIN sess_start USING (session_id)
    WHERE start_ts >= (SELECT split_ts FROM params)
),
ordered AS (
    SELECT *, lag(item_id) OVER (PARTITION BY session_id ORDER BY ts, item_id) AS prev_item
    FROM test_sess
),
changes AS (  -- keep only rows where the item changes
    SELECT * FROM ordered WHERE prev_item IS NULL OR prev_item <> item_id
),
trans AS (
    SELECT session_id, user_id, ts,
           lag(item_id) OVER (PARTITION BY session_id ORDER BY ts, item_id) AS prev_item,
           item_id AS target_item,
           row_number() OVER (PARTITION BY session_id ORDER BY ts, item_id) - 1 AS position
    FROM changes
)
SELECT t.*, ts::DATE AS day,
       CASE WHEN tc.n IS NULL THEN 'new item (0 in train)'
            WHEN tc.n < 5      THEN 'cold item (1-4)'
            ELSE 'warm item (5+)' END                                   AS target_segment,
       CASE WHEN t.position = 1 THEN '1 item seen' ELSE '2+ items seen' END AS context_segment,
       CASE WHEN EXISTS (SELECT 1 FROM events_clean e WHERE e.user_id = t.user_id
                         AND e.ts < (SELECT split_ts FROM params))
            THEN 'returning user' ELSE 'new user' END                   AS user_segment
FROM trans t LEFT JOIN train_counts tc ON tc.item_id = t.target_item
WHERE t.prev_item IS NOT NULL;


-- name: pop_global
CREATE OR REPLACE TABLE pop_global AS
SELECT item_id, row_number() OVER (ORDER BY n DESC, item_id) AS rnk
FROM train_counts QUALIFY rnk <= 20;


-- name: pop_recent
-- For every test day: the 20 most-interacted items over the 7 previous days.
CREATE OR REPLACE TABLE pop_recent AS
WITH days AS (SELECT DISTINCT day FROM targets),
counts AS (
    SELECT d.day, e.item_id, count(*) AS n
    FROM days d JOIN events_clean e
      ON e.ts >= d.day - INTERVAL 7 DAY AND e.ts < d.day
    GROUP BY 1, 2
)
SELECT day, item_id, row_number() OVER (PARTITION BY day ORDER BY n DESC, item_id) AS rnk
FROM counts QUALIFY rnk <= 20;


-- name: covis
-- Item-to-item co-visitation from TRAINING sessions: number of sessions in which
-- both items were viewed. Sessions are capped at 30 distinct items (long sessions
-- would otherwise dominate and the pair count grows quadratically).
CREATE OR REPLACE TABLE covis AS
WITH tr AS (
    SELECT DISTINCT s.session_id, s.item_id FROM sess s JOIN sess_start USING (session_id)
    WHERE start_ts < (SELECT split_ts FROM params) AND s.ts < (SELECT split_ts FROM params)
),
capped AS (
    SELECT * FROM tr WHERE session_id IN (
        SELECT session_id FROM tr GROUP BY 1 HAVING count(*) BETWEEN 2 AND 30)
),
pairs AS (
    SELECT a.item_id AS item_a, b.item_id AS item_b, count(*) AS n_sessions
    FROM capped a JOIN capped b ON a.session_id = b.session_id AND a.item_id <> b.item_id
    GROUP BY 1, 2
)
SELECT item_a, item_b, n_sessions,
       row_number() OVER (PARTITION BY item_a ORDER BY n_sessions DESC, item_b) AS rnk
FROM pairs QUALIFY rnk <= 20;


-- name: covis_lists
-- Co-visitation list for each (previous item, day) seen in the test, topped up with
-- recent popularity (items not already in the list) up to 20 items.
CREATE OR REPLACE TABLE covis_lists AS
WITH pd AS (SELECT DISTINCT prev_item, day FROM targets),
nb AS (
    SELECT pd.prev_item, pd.day, c.item_b AS item_id, c.rnk
    FROM pd JOIN covis c ON c.item_a = pd.prev_item
),
n_nb AS (SELECT prev_item, day, count(*) AS k FROM nb GROUP BY 1, 2),
fill AS (
    SELECT pd.prev_item, pd.day, r.item_id,
           coalesce(n.k, 0) + row_number() OVER (PARTITION BY pd.prev_item, pd.day ORDER BY r.rnk) AS rnk
    FROM pd
    JOIN pop_recent r ON r.day = pd.day
    LEFT JOIN n_nb n ON n.prev_item = pd.prev_item AND n.day = pd.day
    WHERE NOT EXISTS (SELECT 1 FROM nb WHERE nb.prev_item = pd.prev_item AND nb.day = pd.day
                      AND nb.item_id = r.item_id)
)
SELECT prev_item, day, item_id, rnk FROM nb
UNION ALL
SELECT prev_item, day, item_id, rnk FROM fill WHERE rnk <= 20;


-- name: ranks
-- Rank of the true next item in each baseline's list (NULL = not in the top 20).
CREATE OR REPLACE TABLE ranks AS
SELECT t.*,
       g.rnk AS rank_pop_global,
       r.rnk AS rank_pop_recent,
       c.rnk AS rank_covis,
       (SELECT count(*) FROM covis cv WHERE cv.item_a = t.prev_item) AS n_neighbours
FROM targets t
LEFT JOIN pop_global  g ON g.item_id = t.target_item
LEFT JOIN pop_recent  r ON r.item_id = t.target_item AND r.day = t.day
LEFT JOIN covis_lists c ON c.item_id = t.target_item AND c.prev_item = t.prev_item AND c.day = t.day;
