-- Impossible values: a best sector slower than the median, or a theoretical best slower
-- than the best lap it is built from.
SELECT 'sector_summary' AS tbl, Event, Session, Driver, Sector AS detail
FROM marts.sector_summary
WHERE Best > Median OR DeltaBest < 0
UNION ALL
SELECT 'driver_summary', Event, Session, Driver, 'theoretical best > best lap'
FROM marts.driver_summary
WHERE TheoreticalBest > BestLap + 1e-9
