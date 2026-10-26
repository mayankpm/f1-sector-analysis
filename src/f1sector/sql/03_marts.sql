-- Marts: the summary tables the analysis and Tableau read. Mirrors aggregate.py and
-- clean.cleaning_log.

CREATE SCHEMA IF NOT EXISTS marts;

-- Lap counts per session and exclusion reason, plus how many laps had a value rebuilt
-- (imputed_<col>) and how many of those reached a metric (imputed_<col>_used).
CREATE OR REPLACE TABLE marts.cleaning_log AS
SELECT Year, Event, Session, CASE WHEN ExcludeReason = '' THEN 'included' ELSE ExcludeReason END AS Reason,
       count(*) AS Laps
FROM clean.laps
GROUP BY ALL
UNION ALL
SELECT Year, Event, Session, 'imputed_' || Imputed, count(*)
FROM clean.laps
WHERE Imputed <> ''
GROUP BY ALL
UNION ALL
SELECT Year, Event, Session, 'imputed_' || Imputed || '_used', count(*)
FROM clean.laps
WHERE Imputed <> '' AND Included
GROUP BY ALL;

-- Per driver, session and sector: the spread of clean sector times and the gaps to others.
CREATE OR REPLACE TABLE marts.sector_summary AS
WITH sectors AS (
    UNPIVOT (SELECT Year, Event, Session, Driver, Team, S1, S2, S3 FROM clean.laps WHERE Included)
    ON S1, S2, S3
    INTO NAME Sector VALUE SectorTime
),
stats AS (
    SELECT
        Year, Event, Session, Driver, Team, Sector,
        count(*) AS Laps,
        min(SectorTime) AS Best,
        median(SectorTime) AS Median,
        avg(SectorTime) AS Mean,
        stddev_samp(SectorTime) AS Std,
        quantile_cont(SectorTime, 0.25) AS P25,
        quantile_cont(SectorTime, 0.75) AS P75
    FROM sectors
    GROUP BY ALL
)
SELECT
    *,
    Best - min(Best) OVER s AS DeltaBest,
    Median - median(Median) OVER s AS DeltaMedian,
    rank() OVER (PARTITION BY Year, Event, Session, Sector ORDER BY Best) AS RankBest,
    -- Teammate: the other car of the same team, only when both cars have clean laps.
    CASE WHEN count(Best) OVER t = 2 THEN Best - (sum(Best) OVER t - Best) END AS DeltaTeammateBest,
    CASE WHEN count(Median) OVER t = 2 THEN Median - (sum(Median) OVER t - Median) END AS DeltaTeammateMedian
FROM stats
WINDOW
    s AS (PARTITION BY Year, Event, Session, Sector),
    t AS (PARTITION BY Year, Event, Session, Sector, Team);

-- Per driver and session: best lap, theoretical best from the driver's best sectors, and
-- the sector where they lose the most to the fastest driver.
CREATE OR REPLACE TABLE marts.driver_summary AS
WITH clean_laps AS (
    SELECT Year, Event, Session, Driver, Team,
           count(*) AS CleanLaps, min(LapTime) AS BestLap, median(LapTime) AS MedianLap
    FROM clean.laps
    WHERE Included
    GROUP BY ALL
),
total AS (
    SELECT Year, Event, Session, Driver, count(*) AS TotalLaps
    FROM clean.laps
    GROUP BY ALL
),
sectors AS (
    SELECT
        Year, Event, Session, Driver,
        max(Best) FILTER (Sector = 'S1') AS b1,
        max(Best) FILTER (Sector = 'S2') AS b2,
        max(Best) FILTER (Sector = 'S3') AS b3,
        max(DeltaBest) FILTER (Sector = 'S1') AS d1,
        max(DeltaBest) FILTER (Sector = 'S2') AS d2,
        max(DeltaBest) FILTER (Sector = 'S3') AS d3
    FROM marts.sector_summary
    GROUP BY ALL
)
SELECT
    c.*,
    t.TotalLaps,
    s.b1 + s.b2 + s.b3 AS TheoreticalBest,
    -- Ties go to the earlier sector.
    CASE WHEN s.d1 >= s.d2 AND s.d1 >= s.d3 THEN 'S1' WHEN s.d2 >= s.d3 THEN 'S2' ELSE 'S3' END AS WeakestSector,
    greatest(s.d1, s.d2, s.d3) AS WeakestSectorDelta,
    c.BestLap - (s.b1 + s.b2 + s.b3) AS TheoreticalGain,
    c.BestLap - min(c.BestLap) OVER (PARTITION BY c.Year, c.Event, c.Session) AS GapToPole
FROM clean_laps AS c
JOIN total AS t USING (Year, Event, Session, Driver)
LEFT JOIN sectors AS s USING (Year, Event, Session, Driver);
