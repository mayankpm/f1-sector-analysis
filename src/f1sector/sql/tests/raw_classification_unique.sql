-- One official result per driver and session.
SELECT Year, Event, Session, Driver, count(*) AS copies
FROM raw.classification
GROUP BY ALL
HAVING count(*) > 1
