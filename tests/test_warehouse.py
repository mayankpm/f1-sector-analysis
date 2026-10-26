import numpy as np
import pandas as pd
import pytest

from f1sector.export import analyse
from f1sector.warehouse import build, connect, ingest, run_tests, table

KEYS = ["Year", "Event", "Session", "Driver"]


# Fixture: a Q and an R session in which all nine cleaning rules fire, plus their classification.
@pytest.fixture
def dataset(laps_factory):
    """Two sessions in which every rule fires at least once."""
    q = pd.concat([
        laps_factory(driver="AAA", team="T1", session="Q", n=15, noise=0.02),
        laps_factory(driver="BBB", team="T1", session="Q", n=12, s=(30.2, 40.1, 20.1), seed=1),
        laps_factory(driver="CCC", team="T2", session="Q", n=10, s=(30.4, 40.3, 20.0), seed=2),
    ], ignore_index=True)
    q.loc[1, "Deleted"] = True
    q.loc[2, "InPit"] = True
    q.loc[3, "TrackStatus"] = "14"
    q.loc[4, "S1"] = np.nan                                 # imputed and used
    q.loc[5, ["S1", "S2"]] = np.nan                         # missing_timing
    q.loc[6, "LapTime"] += 0.5                              # timing_mismatch
    q.loc[7, ["S1", "S2", "S3", "LapTime"]] = [40.0, 50.0, 25.0, 115.0]  # slow_lap
    q.loc[8, "S2"] += 1.5                                   # sector_outlier
    q.loc[8, "LapTime"] += 1.5
    q.loc[16, ["S1", "S2", "S3"]] -= 1.0                    # BBB: not_counted
    q.loc[16, "LapTime"] -= 3.0

    r = pd.concat([
        laps_factory(driver="AAA", team="T1", session="R", n=8, stint=1),
        laps_factory(driver="AAA", team="T1", session="R", n=3, stint=2, start_lap=9, seed=3),
        laps_factory(driver="BBB", team="T1", session="R", n=11, s=(30.3, 40.2, 20.2), seed=4),
    ], ignore_index=True)
    r.loc[5, "LapTime"] = np.nan                            # lap time rebuilt from sectors
    raw = pd.concat([q, r], ignore_index=True)

    official = raw[raw["Session"] == "Q"].drop(index=16).groupby(KEYS)["LapTime"].min()
    finished = raw[raw["Session"] == "R"].groupby(KEYS)["LapNumber"].max()
    rows = [dict(zip(KEYS, k), OfficialBest=v, Laps=np.nan, Status="") for k, v in official.items()]
    rows += [dict(zip(KEYS, k), OfficialBest=np.nan, Laps=float(v), Status="Finished")
             for k, v in finished.items()]
    classification = pd.DataFrame(rows).assign(Position=1.0, RaceTime=np.nan)
    return raw, classification


# Fixture: an in-memory DuckDB loaded with the dataset and built through all SQL layers.
@pytest.fixture
def warehouse(dataset):
    raw, classification = dataset
    con = connect()
    ingest(con, raw, classification)
    build(con)
    return con


# Helper: two tables are equal column by column (numbers to 1e-9) after sorting by keys.
def assert_same(pandas_df, sql_df, keys):
    a = pandas_df.sort_values(keys).reset_index(drop=True)
    b = sql_df[a.columns].sort_values(keys).reset_index(drop=True)
    for col in a.columns:
        if pd.api.types.is_numeric_dtype(a[col]) and not pd.api.types.is_bool_dtype(a[col]):
            np.testing.assert_allclose(a[col].astype(float), b[col].astype(float), atol=1e-9,
                                       err_msg=col)
        else:
            assert list(a[col]) == list(b[col]), col


# Guards the fixture itself: every exclusion reason appears at least once.
def test_every_rule_fires_in_the_fixture(warehouse):
    reasons = set(table(warehouse, "clean.laps")["ExcludeReason"])
    assert reasons == {"", "deleted", "not_counted", "pit_in_out", "track_status", "standing_start",
                       "missing_timing", "timing_mismatch", "slow_lap", "sector_outlier"}


# SQL and pandas give every lap the same reason, rebuilt values and Included flag.
def test_sql_cleaning_matches_pandas_lap_by_lap(dataset, warehouse):
    expected = analyse(*dataset).laps
    cols = KEYS + ["LapNumber", "S1", "S2", "S3", "LapTime", "Imputed", "ExcludeReason", "Included"]
    assert_same(expected[cols], table(warehouse, "clean.laps"), KEYS + ["LapNumber"])


# The SQL summary tables equal the pandas ones.
@pytest.mark.parametrize("name, keys", [
    ("sector_summary", KEYS + ["Sector"]),
    ("driver_summary", KEYS),
    ("cleaning_log", ["Year", "Event", "Session", "Reason"]),
])
def test_sql_marts_match_pandas(dataset, warehouse, name, keys):
    expected = getattr(analyse(*dataset), name)
    assert_same(expected, table(warehouse, f"marts.{name}"), keys)


# Loading the same sessions twice replaces them instead of doubling the laps.
def test_reloading_a_session_replaces_it(dataset, warehouse):
    raw, classification = dataset
    ingest(warehouse, raw, classification)
    build(warehouse)
    assert warehouse.sql("SELECT count(*) FROM raw.laps").fetchone()[0] == len(raw)
    assert warehouse.sql("SELECT count(*) FROM raw.ingest_log").fetchone()[0] == 4  # 2 sessions x 2 loads


# SQL data tests pass on good data and catch a duplicated lap.
def test_data_tests_pass_and_catch_duplicates(dataset, warehouse):
    assert not any(run_tests(warehouse).values())
    warehouse.execute("INSERT INTO raw.laps SELECT * FROM raw.laps LIMIT 1")  # simulate a bad load
    build(warehouse)
    failures = {k for k, v in run_tests(warehouse).items() if v}
    assert "raw_laps_unique" in failures
