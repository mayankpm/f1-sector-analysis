-- Staging: one row per lap, typed as loaded, with a single missing timing value rebuilt.
-- The lap time is the sum of the three sectors, so when exactly one of S1, S2, S3 and
-- LapTime is missing it can be solved for. Mirrors clean.impute_single_missing.

CREATE SCHEMA IF NOT EXISTS staging;

CREATE OR REPLACE TABLE staging.laps AS
WITH counted AS (
    SELECT
        *,
        (S1 IS NULL)::INT + (S2 IS NULL)::INT + (S3 IS NULL)::INT + (LapTime IS NULL)::INT AS n_missing
    FROM raw.laps
),
solved AS (
    SELECT
        *,
        CASE WHEN n_missing = 1 AND S1 IS NULL THEN LapTime - (S2 + S3) END AS s1_fill,
        CASE WHEN n_missing = 1 AND S2 IS NULL THEN LapTime - (S1 + S3) END AS s2_fill,
        CASE WHEN n_missing = 1 AND S3 IS NULL THEN LapTime - (S1 + S2) END AS s3_fill,
        CASE WHEN n_missing = 1 AND LapTime IS NULL THEN S1 + S2 + S3 END AS lap_fill
    FROM counted
)
SELECT
    -- Surrogate key: one id per lap, used to join the lap back to its outlier scores.
    row_number() OVER (ORDER BY Year, Event, Session, Driver, LapNumber) AS lap_id,
    Year, Event, Session, Driver, Team, LapNumber, Stint, Compound, TyreLife,
    TrackStatus, IsAccurate, Deleted, InPit,
    -- A rebuilt sector must be positive; a negative one means the row is corrupt.
    CASE WHEN s1_fill > 0 THEN s1_fill ELSE S1 END AS S1,
    CASE WHEN s2_fill > 0 THEN s2_fill ELSE S2 END AS S2,
    CASE WHEN s3_fill > 0 THEN s3_fill ELSE S3 END AS S3,
    coalesce(LapTime, lap_fill) AS LapTime,
    CASE
        WHEN s1_fill > 0 THEN 'S1'
        WHEN s2_fill > 0 THEN 'S2'
        WHEN s3_fill > 0 THEN 'S3'
        WHEN lap_fill IS NOT NULL THEN 'LapTime'
        ELSE ''
    END AS Imputed
FROM solved;
