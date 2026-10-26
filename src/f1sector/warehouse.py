"""Load sessions into a DuckDB warehouse and rebuild the cleaning and summaries in SQL.

Layers, one schema each:

* ``raw``      laps and official classification exactly as FastF1 returns them
* ``staging``  one missing timing value rebuilt (``sql/01_staging.sql``)
* ``clean``    every lap tagged with an exclusion reason (``sql/02_clean.sql``)
* ``marts``    summaries for analysis and Tableau (``sql/03_marts.sql``)

Loading is idempotent: each session is replaced in one transaction, so re-running a load
never duplicates laps. The SQL mirrors clean.py and aggregate.py, and
tests/test_warehouse.py checks that both give the same answers.
"""

from __future__ import annotations

import argparse
import logging
from importlib.resources import files
from pathlib import Path

import duckdb
import pandas as pd

from f1sector.clean import OUTLIER_Z, SESSION_KEYS, SLOW_LAP_FACTOR

SQL = files("f1sector") / "sql"
LAYERS = ("01_staging.sql", "02_clean.sql", "03_marts.sql")


# Warehouse: open (or create) the DuckDB file and make sure the raw schema exists.
def connect(path: str | Path = ":memory:") -> duckdb.DuckDBPyConnection:
    if path != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(path))
    con.execute("CREATE SCHEMA IF NOT EXISTS raw")
    return con


# Warehouse helper: delete the incoming sessions from a raw table, then insert them again.
def _replace_sessions(con: duckdb.DuckDBPyConnection, table: str, frame: pd.DataFrame) -> None:
    """Replace every session in ``frame`` in ``raw.<table>``: delete, then insert by name."""
    con.register("incoming", frame)
    con.execute(f"CREATE TABLE IF NOT EXISTS raw.{table} AS SELECT * FROM incoming WHERE false")
    con.execute(f"""
        DELETE FROM raw.{table} AS t
        USING (SELECT DISTINCT Year, Event, Session FROM incoming) AS s
        WHERE t.Year = s.Year AND t.Event = s.Event AND t.Session = s.Session
    """)
    con.execute(f"INSERT INTO raw.{table} BY NAME SELECT * FROM incoming")
    con.unregister("incoming")


# Warehouse load: replace laps and classification per session in one transaction and log the load.
def ingest(con: duckdb.DuckDBPyConnection, laps: pd.DataFrame,
           classification: pd.DataFrame) -> pd.DataFrame:
    """Load laps and classification into ``raw``, replacing any sessions already there.
    Both tables change in one transaction, and each load is recorded in ``raw.ingest_log``."""
    con.execute("""
        CREATE TABLE IF NOT EXISTS raw.ingest_log (
            Year INTEGER, Event VARCHAR, Session VARCHAR, Laps INTEGER, Drivers INTEGER,
            LoadedAt TIMESTAMP DEFAULT current_timestamp)
    """)
    log_rows = laps.groupby(SESSION_KEYS).agg(Laps=("Driver", "size"), Drivers=("Driver", "nunique"))
    con.execute("BEGIN TRANSACTION")
    try:
        _replace_sessions(con, "laps", laps)
        _replace_sessions(con, "classification", classification)
        con.register("loaded", log_rows.reset_index())
        con.execute("INSERT INTO raw.ingest_log BY NAME SELECT * FROM loaded")
        con.unregister("loaded")
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise
    return log_rows.reset_index()


# Warehouse build: run the staging, clean and marts SQL files in order with the chosen thresholds.
def build(con: duckdb.DuckDBPyConnection, slow_factor: float = SLOW_LAP_FACTOR,
          outlier_z: float = OUTLIER_Z) -> None:
    """Rebuild staging, clean and marts from ``raw``."""
    con.execute(f"SET VARIABLE slow_factor = {float(slow_factor)!r}::DOUBLE")
    con.execute(f"SET VARIABLE outlier_z = {float(outlier_z)!r}::DOUBLE")
    for name in LAYERS:
        con.execute((SQL / name).read_text(encoding="utf-8"))


# Warehouse checks: run every SQL data test; each returns the rows that break its rule.
def run_tests(con: duckdb.DuckDBPyConnection) -> dict[str, int]:
    """Run every query in ``sql/tests``. Each returns the rows that break its rule, so a
    passing test returns none. Returns the number of failing rows per test."""
    tests = sorted(p for p in (SQL / "tests").iterdir() if p.name.endswith(".sql"))
    return {p.name.removesuffix(".sql"): len(con.sql(p.read_text(encoding="utf-8")).fetchall())
            for p in tests}


# Warehouse helper: read a whole table into pandas.
def table(con: duckdb.DuckDBPyConnection, name: str) -> pd.DataFrame:
    return con.sql(f"SELECT * FROM {name}").df()


# Entry point for f1sector-warehouse: load, ingest, build, then report row counts and tests.
def main(argv: list[str] | None = None) -> int:
    from f1sector.load import enable_cache, load_sessions

    p = argparse.ArgumentParser(prog="f1sector-warehouse", description=__doc__.splitlines()[0])
    p.add_argument("--year", type=int, required=True)
    p.add_argument("--event", action="append", required=True,
                   help="event name or round number; repeat for several events")
    p.add_argument("--session", action="append", default=None,
                   help="session code such as Q, R, S; repeat for several (default Q and R)")
    p.add_argument("--db", type=Path, default=Path("warehouse/f1.duckdb"))
    p.add_argument("--cache", type=Path, default=Path("cache"))
    p.add_argument("--slow-factor", type=float, default=SLOW_LAP_FACTOR)
    p.add_argument("--outlier-z", type=float, default=OUTLIER_Z)
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")

    enable_cache(args.cache)
    laps, classification = load_sessions(args.year, args.event, args.session or ["Q", "R"])
    con = connect(args.db)
    loaded = ingest(con, laps, classification)
    build(con, args.slow_factor, args.outlier_z)
    print(f"loaded {len(loaded)} sessions into {args.db}")
    for name in ("raw.laps", "staging.laps", "clean.laps", "marts.sector_summary",
                 "marts.driver_summary", "marts.cleaning_log"):
        print(f"  {name:22} {con.sql(f'SELECT count(*) FROM {name}').fetchone()[0]:>8,} rows")
    failures = {k: v for k, v in run_tests(con).items() if v}
    print("data tests:", "all passed" if not failures else f"FAILED {failures}")
    return 1 if failures else 0
