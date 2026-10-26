-- Cleaning tags laps but never drops them: every raw lap reaches clean.laps.
SELECT r.Year, r.Event, r.Session, r.laps AS raw_laps, c.laps AS clean_laps
FROM (SELECT Year, Event, Session, count(*) AS laps FROM raw.laps GROUP BY ALL) AS r
FULL JOIN (SELECT Year, Event, Session, count(*) AS laps FROM clean.laps GROUP BY ALL) AS c
    USING (Year, Event, Session)
WHERE r.laps IS DISTINCT FROM c.laps
