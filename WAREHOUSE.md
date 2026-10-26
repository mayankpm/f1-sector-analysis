# SQL warehouse (DuckDB)

The same cleaning and summaries as the pandas pipeline, rebuilt as layered SQL in a [DuckDB](https://duckdb.org) database file. Both versions give identical results on the full 2024 season, so either can check the other.

## Layers

```
FastF1 cache ──> raw ──> staging ──> clean ──> marts
                 │        │           │          │
                 │        │           │          └─ sector_summary, driver_summary, cleaning_log
                 │        │           └─ every lap tagged with an ExcludeReason (02_clean.sql)
                 │        └─ one missing timing value rebuilt (01_staging.sql)
                 └─ laps, classification and ingest_log, exactly as loaded
```

Each layer is a schema, and each step is a plain SQL file in [`src/f1sector/sql`](src/f1sector/sql), readable without knowing Python. `warehouse.py` loads the raw data, runs the three files in order, then runs the data tests.

| SQL file | Mirrors | Techniques |
|---|---|---|
| `01_staging.sql` | `clean.impute_single_missing` | Conditional logic with `CASE`, surrogate key with `row_number()` |
| `02_clean.sql` | `clean.clean_laps` | Rules in priority order as one `CASE`; 107% rule and median/MAD outliers with window functions (`min`, `median ... OVER`) |
| `03_marts.sql` | `aggregate.py`, `clean.cleaning_log` | `UNPIVOT` sectors into rows, aggregates, `rank()`, teammate deltas over a team window, `FILTER` to pivot back |

Not ported yet: `stint_trends`, `session_comparison`, the per-lap `sector_laps` export and the source checks in `validate.py`. Those still run in pandas.

## Run it

```bash
f1sector-warehouse --year 2024 --event Bahrain --event Monaco --session Q --session R
f1sector-warehouse --year 2024 --event 1 --event 2 ... --event 24 --session Q --session S --session R
```

Output for the full 2024 season (54 sessions, a 4 MB database file):

```
loaded 54 sessions into warehouse\f1.duckdb
  raw.laps                 36,612 rows
  staging.laps             36,612 rows
  clean.laps               36,612 rows
  marts.sector_summary      3,171 rows
  marts.driver_summary      1,057 rows
  marts.cleaning_log          354 rows
data tests: all passed
```

**Loads are idempotent.** Each session is deleted and reinserted inside one transaction, so loading a session twice replaces it rather than doubling it, and a failed load leaves the previous data intact. Every load is recorded in `raw.ingest_log` with its lap count and timestamp.

## Data tests

Each file in [`src/f1sector/sql/tests`](src/f1sector/sql/tests) is a query that returns the rows breaking a rule, so a passing test returns nothing. The same idea as dbt tests.

| Test | Rule |
|---|---|
| `raw_laps_unique` | A driver's lap appears once per session |
| `raw_classification_unique` | One official result per driver and session |
| `no_laps_lost` | Every raw lap reaches `clean.laps`; cleaning tags, never drops |
| `exclude_reason_accepted` | Only known rule names |
| `included_laps_complete` | A lap used for pace has every time, and its sectors add up to its lap time |
| `summary_values_consistent` | No best sector slower than the median, no theoretical best slower than the best lap |

`tests/test_warehouse.py` inserts a duplicate lap and checks that `raw_laps_unique` catches it.

## Proof that SQL and pandas agree

* **Unit tests** (`tests/test_warehouse.py`): a synthetic dataset where all nine rules fire, run through both versions. Every lap's `ExcludeReason`, rebuilt values and every summary table must match to 1e-9.
* **Full 2024 season**: all 36,612 laps through both. Zero differences in `clean.laps`, `sector_summary` (3,171 rows), `driver_summary` (1,057) and `cleaning_log` (354).

## Explore it

From Python (on Windows, set `PYTHONIOENCODING=utf-8` so the table borders print):

```python
import duckdb
con = duckdb.connect("warehouse/f1.duckdb", read_only=True)
con.sql("SELECT * FROM marts.driver_summary WHERE Event = 'Bahrain' AND Session = 'Q' ORDER BY BestLap")
```

Questions worth trying, all run against the 2024 season:

```sql
-- Which rule removed the most laps in each race?
SELECT Event, Reason, Laps
FROM marts.cleaning_log
WHERE Session = 'R' AND Reason <> 'included' AND Reason NOT LIKE 'imputed%'
QUALIFY row_number() OVER (PARTITION BY Event ORDER BY Laps DESC) = 1
ORDER BY Laps DESC;
-- Canada (slow_lap, 651), Monaco (slow_lap, 280), São Paulo (track_status, 258), ...

-- Who set the fastest sector in the most qualifying sessions?
SELECT Sector, Driver, count(*) AS sessions_fastest
FROM marts.sector_summary
WHERE Session = 'Q' AND RankBest = 1
GROUP BY Sector, Driver
QUALIFY rank() OVER (PARTITION BY Sector ORDER BY count(*) DESC) = 1;
-- S1: Verstappen (9), S2: Norris (7), S3: Norris and Verstappen (6 each)

-- Every load, newest first
SELECT Event, Session, Laps, Drivers, LoadedAt FROM raw.ingest_log ORDER BY LoadedAt DESC;
```

## How this maps to a production warehouse

| Here | In production |
|---|---|
| DuckDB file on a laptop | A cloud warehouse such as BigQuery or Snowflake, same SQL ideas |
| `sql/*.sql` run in order by `warehouse.py` | dbt models, which also track dependencies between them |
| `sql/tests/*.sql` | dbt tests, run on every build |
| `raw.ingest_log` | Load audit tables or the orchestrator's run history |
| Delete and reinsert a session in a transaction | `MERGE` or partition overwrite, so reruns are safe |
