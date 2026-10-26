import numpy as np
import pandas as pd
import pytest

from f1sector.validate import reconcile, summarize


# Helper: a minimal official classification for one session, with sensible defaults.
def classification(session, **cols):
    base = {"Year": 2024, "Event": "Test", "Session": session}
    n = len(next(iter(cols.values())))
    defaults = {"Position": list(range(1, n + 1)), "Status": ["Finished"] * n,
                "Laps": [np.nan] * n, "OfficialBest": [np.nan] * n, "RaceTime": [np.nan] * n}
    return pd.DataFrame({**{k: [v] * n for k, v in base.items()}, **{**defaults, **cols}})


# Helper: the result row of one check for one driver.
def result_of(checks, driver, check):
    return checks.loc[(checks["Driver"] == driver) & (checks["Check"] == check)].iloc[0]


# Equal best times match; a feed lap 1 s faster is a MISMATCH noted as not_counted.
def test_quali_best_lap_matches_and_mismatches(laps_factory):
    a = laps_factory(driver="AAA", session="Q")
    b = laps_factory(driver="BBB", session="Q", seed=1)
    raw = pd.concat([a, b], ignore_index=True)
    official = classification("Q", Driver=["AAA", "BBB"],
                              OfficialBest=[a["LapTime"].min(), b["LapTime"].min() + 1.0])
    checks = reconcile(raw, official)
    assert result_of(checks, "AAA", "best_quali_lap")["Result"] == "match"
    bbb = result_of(checks, "BBB", "best_quali_lap")
    assert bbb["Result"] == "MISMATCH"
    assert bbb["Diff"] == pytest.approx(-1.0)
    assert "not_counted" in bbb["Note"]


# A deleted fastest lap is skipped when finding the feed's best.
def test_deleted_laps_do_not_count_as_the_feed_best(laps_factory):
    raw = laps_factory(session="Q")
    fastest = raw["LapTime"].idxmin()
    raw.loc[fastest, "Deleted"] = True
    official = classification("Q", Driver=["AAA"],
                              OfficialBest=[raw.drop(index=fastest)["LapTime"].min()])
    assert result_of(reconcile(raw, official), "AAA", "best_quali_lap")["Result"] == "match"


# Finisher matches; a retirement and a disqualification are explained, not mismatches.
def test_race_lap_counts_and_explained_differences(laps_factory):
    winner = laps_factory(driver="AAA", n=10)
    retired = laps_factory(driver="BBB", n=6, seed=1)
    retired.loc[5, ["LapTime", "S3"]] = np.nan  # the lap the car stopped on has no time
    dsq = laps_factory(driver="CCC", n=10, seed=2)
    raw = pd.concat([winner, retired, dsq], ignore_index=True)
    official = classification(
        "R", Driver=["AAA", "BBB", "CCC"], Laps=[10, 5, 0],
        Status=["Finished", "Retired", "Disqualified"],
        RaceTime=[winner["LapTime"].sum(), np.nan, np.nan])
    checks = reconcile(raw, official)
    assert result_of(checks, "AAA", "laps_completed")["Result"] == "match"
    assert result_of(checks, "BBB", "laps_completed")["Result"] == "explained"
    assert result_of(checks, "CCC", "laps_completed")["Result"] == "explained"
    assert result_of(checks, "AAA", "winner_race_time")["Result"] == "match"
    assert (checks["Check"] == "winner_race_time").sum() == 1


# An untimed lap (red flag) makes the race-time check not_comparable.
def test_winner_time_is_not_comparable_when_a_lap_has_no_time(laps_factory):
    raw = laps_factory(n=10)
    total = raw["LapTime"].sum()
    raw.loc[3, "LapTime"] = np.nan  # red flag: the lap spanning the stoppage has no time
    official = classification("R", Driver=["AAA"], Laps=[10], RaceTime=[total + 1200.0])
    row = result_of(reconcile(raw, official), "AAA", "winner_race_time")
    assert row["Result"] == "not_comparable"
    assert "1 lap(s)" in row["Note"]


# A lap count difference with no known cause is a MISMATCH.
def test_unexplained_lap_count_difference_is_a_mismatch(laps_factory):
    raw = laps_factory(n=10)
    official = classification("R", Driver=["AAA"], Laps=[8])
    assert result_of(reconcile(raw, official), "AAA", "laps_completed")["Result"] == "MISMATCH"


# The summary table counts each result per check.
def test_summarize_counts_results(laps_factory):
    raw = laps_factory(n=10)
    official = classification("R", Driver=["AAA"], Laps=[10], RaceTime=[raw["LapTime"].sum()])
    table = summarize(reconcile(raw, official))
    assert table.loc["laps_completed", "match"] == 1
    assert table.loc["winner_race_time", "match"] == 1
