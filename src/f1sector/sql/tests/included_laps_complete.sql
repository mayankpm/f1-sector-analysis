-- A lap used for pace has every time, and its sectors add up to its lap time.
SELECT lap_id, Event, Session, Driver, LapNumber, S1, S2, S3, LapTime
FROM clean.laps
WHERE Included
  AND (S1 IS NULL OR S2 IS NULL OR S3 IS NULL OR LapTime IS NULL OR abs(S1 + S2 + S3 - LapTime) > 0.1)
