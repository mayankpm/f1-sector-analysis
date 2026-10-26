-- Only known rule names (or '' for included laps).
SELECT ExcludeReason, count(*) AS laps
FROM clean.laps
WHERE ExcludeReason NOT IN ('', 'deleted', 'not_counted', 'pit_in_out', 'track_status', 'standing_start',
                            'missing_timing', 'timing_mismatch', 'slow_lap', 'sector_outlier')
GROUP BY ALL
