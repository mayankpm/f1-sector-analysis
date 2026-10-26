-- Each driver's lap appears once per session: a re-run must replace a session, not add to it.
SELECT Year, Event, Session, Driver, LapNumber, count(*) AS copies
FROM raw.laps
GROUP BY ALL
HAVING count(*) > 1
