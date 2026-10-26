-- Clean: every lap tagged with the first exclusion rule it breaks. Nothing is dropped;
-- ExcludeReason is '' for laps used in the pace comparisons. Mirrors clean.clean_laps.
-- Parameters: getvariable('slow_factor') and getvariable('outlier_z').

CREATE SCHEMA IF NOT EXISTS clean;

CREATE OR REPLACE TABLE clean.laps AS
WITH row_rules AS (
    -- Rules that need only the lap itself (and the official classification), in priority order.
    SELECT
        l.*,
        CASE
            WHEN l.Deleted THEN 'deleted'
            WHEN l.Session IN ('Q', 'SQ') AND l.LapTime < c.OfficialBest - 0.0005 THEN 'not_counted'
            WHEN l.InPit THEN 'pit_in_out'
            WHEN regexp_matches(l.TrackStatus, '[24567]') THEN 'track_status'
            WHEN l.Session IN ('R', 'S') AND l.LapNumber = 1 THEN 'standing_start'
            WHEN l.S1 IS NULL OR l.S2 IS NULL OR l.S3 IS NULL OR l.LapTime IS NULL THEN 'missing_timing'
            WHEN abs(l.S1 + l.S2 + l.S3 - l.LapTime) > 0.1 THEN 'timing_mismatch'
            ELSE ''
        END AS reason
    FROM staging.laps AS l
    LEFT JOIN raw.classification AS c USING (Year, Event, Session, Driver)
),
slow AS (
    -- 107% rule: against the driver's own best lap among the laps still clean.
    SELECT
        * EXCLUDE (reason),
        CASE
            WHEN reason = '' AND LapTime > getvariable('slow_factor') * min(CASE WHEN reason = '' THEN LapTime END)
                OVER (PARTITION BY Year, Event, Session, Driver)
            THEN 'slow_lap'
            ELSE reason
        END AS reason
    FROM row_rules
),
candidates AS (
    -- Outliers are scored per stint; stints under 5 laps fall back to the whole session (-1).
    SELECT
        *,
        CASE
            WHEN count(*) OVER (PARTITION BY Year, Event, Session, Driver, Stint) >= 5 THEN coalesce(Stint, -1)
            ELSE -1
        END AS grp
    FROM slow
    WHERE reason = ''
),
centred AS (
    SELECT
        *,
        median(S1) OVER g AS m1,
        median(S2) OVER g AS m2,
        median(S3) OVER g AS m3,
        count(*) OVER g AS n
    FROM candidates
    WINDOW g AS (PARTITION BY Year, Event, Session, Driver, grp)
),
spread AS (
    -- MAD: the median distance from the median, floored at 0.05 s.
    SELECT
        *,
        greatest(median(abs(S1 - m1)) OVER g, 0.05) AS d1,
        greatest(median(abs(S2 - m2)) OVER g, 0.05) AS d2,
        greatest(median(abs(S3 - m3)) OVER g, 0.05) AS d3
    FROM centred
    WINDOW g AS (PARTITION BY Year, Event, Session, Driver, grp)
),
outliers AS (
    -- Robust z score, slow side only. Groups under 3 laps are never flagged.
    SELECT lap_id
    FROM spread
    WHERE n >= 3 AND (
        0.6745 * (S1 - m1) / d1 > getvariable('outlier_z')
        OR 0.6745 * (S2 - m2) / d2 > getvariable('outlier_z')
        OR 0.6745 * (S3 - m3) / d3 > getvariable('outlier_z')
    )
)
SELECT
    s.* EXCLUDE (reason),
    CASE WHEN o.lap_id IS NOT NULL THEN 'sector_outlier' ELSE s.reason END AS ExcludeReason,
    o.lap_id IS NULL AND s.reason = '' AS Included
FROM slow AS s
LEFT JOIN outliers AS o USING (lap_id);
