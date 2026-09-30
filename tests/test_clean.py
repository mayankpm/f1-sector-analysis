import numpy as np
import pandas as pd
import pytest

from f1sector.clean import clean_laps, cleaning_log, impute_single_missing, robust_z


def reason_of(df, lap):
    return df.loc[df["LapNumber"] == lap, "ExcludeReason"].item()


def test_clean_session_keeps_everything_but_race_lap_one(laps_factory):
    out = clean_laps(laps_factory(session="Q"))
    assert out["Included"].all()

    out = clean_laps(laps_factory(session="R"))
    assert reason_of(out, 1) == "standing_start"
    assert out["Included"].sum() == len(out) - 1


def test_imputes_single_missing_sector_from_lap_time(laps_factory):
    df = laps_factory(session="Q")
    expected = df.loc[3, "S1"]
    df.loc[3, "S1"] = np.nan
    out = impute_single_missing(df)
    assert out.loc[3, "S1"] == pytest.approx(expected)
    assert out.loc[3, "Imputed"] == "S1"
    assert (out.drop(index=3)["Imputed"] == "").all()


def test_imputes_missing_lap_time_from_sectors(laps_factory):
    df = laps_factory(session="Q")
    expected = df.loc[2, "LapTime"]
    df.loc[2, "LapTime"] = np.nan
    out = impute_single_missing(df)
    assert out.loc[2, "LapTime"] == pytest.approx(expected)
    assert out.loc[2, "Imputed"] == "LapTime"


def test_two_missing_values_are_not_imputed(laps_factory):
    df = laps_factory(session="Q")
    df.loc[4, ["S1", "S2"]] = np.nan
    out = clean_laps(df)
    assert out.loc[4, "Imputed"] == ""
    assert reason_of(out, 5) == "missing_timing"


def test_rejects_negative_imputation(laps_factory):
    df = laps_factory(session="Q")
    df.loc[1, "S1"] = np.nan
    df.loc[1, "LapTime"] = 10.0  # shorter than S2 + S3: corrupt row
    out = impute_single_missing(df)
    assert np.isnan(out.loc[1, "S1"])


@pytest.mark.parametrize("column, value, reason", [
    ("Deleted", True, "deleted"),
    ("InPit", True, "pit_in_out"),
    ("TrackStatus", "14", "track_status"),
    ("TrackStatus", "6", "track_status"),
    ("TrackStatus", "2", "track_status"),
])
def test_flag_rules(laps_factory, column, value, reason):
    df = laps_factory(session="Q")
    df.loc[5, column] = value
    out = clean_laps(df)
    assert reason_of(out, 6) == reason
    assert out["Included"].sum() == len(df) - 1


def test_first_matching_rule_wins(laps_factory):
    df = laps_factory(session="Q")
    df.loc[5, ["Deleted", "InPit"]] = True
    df.loc[5, "TrackStatus"] = "4"
    assert reason_of(clean_laps(df), 6) == "deleted"


def test_timing_mismatch(laps_factory):
    df = laps_factory(session="Q")
    df.loc[7, "LapTime"] += 0.5
    assert reason_of(clean_laps(df), 8) == "timing_mismatch"


def test_slow_lap_uses_drivers_own_best(laps_factory):
    df = laps_factory(session="Q")
    df.loc[3, ["S1", "S2", "S3"]] = [40.0, 50.0, 25.0]  # 115 s against a 90 s best
    df.loc[3, "LapTime"] = 115.0
    out = clean_laps(df)
    assert reason_of(out, 4) == "slow_lap"
    # A different, slower driver is judged against their own best, not the field's.
    slow = laps_factory(driver="BBB", session="Q", s=(33.0, 44.0, 22.0), seed=1)
    out = clean_laps(pd.concat([df, slow], ignore_index=True))
    assert out.loc[out["Driver"] == "BBB", "Included"].all()


def test_sector_outlier_within_threshold_lap(laps_factory):
    df = laps_factory(session="Q", n=15, noise=0.02)
    df.loc[6, "S2"] += 1.5  # well inside 107% but far outside the driver's S2 spread
    df.loc[6, "LapTime"] += 1.5
    out = clean_laps(df)
    assert reason_of(out, 7) == "sector_outlier"
    assert out["Included"].sum() == len(df) - 1


def test_fast_push_lap_is_not_an_outlier(laps_factory):
    df = laps_factory(session="R", n=20, noise=0.05)
    df.loc[15, ["S1", "S2", "S3"]] -= [0.8, 1.2, 0.6]  # late fastest lap attempt
    df.loc[15, "LapTime"] -= 2.6
    out = clean_laps(df)
    assert out.loc[15, "Included"]
    assert out["Included"].sum() == len(df) - 1  # only the standing start is dropped


def test_outliers_grouped_by_stint(laps_factory):
    # Second stint on fresh tyres is 1 s faster in S2; neither stint should be flagged.
    a = laps_factory(session="Q", n=10, noise=0.02, stint=1)
    b = laps_factory(session="Q", n=10, noise=0.02, stint=2, start_lap=11, s=(30, 39, 20),
                     seed=3)
    out = clean_laps(pd.concat([a, b], ignore_index=True))
    assert out["Included"].all()


def test_robust_z_handles_zero_spread():
    assert (robust_z(pd.Series([1.0, 1.0, 1.0, 1.0])) == 0).all()
    z = robust_z(pd.Series([1.0, 1.1, 0.9, 1.0, 5.0]))
    assert z.iloc[-1] > 3.5


def test_cleaning_log_counts_every_lap(laps_factory):
    df = laps_factory(session="R")
    df.loc[4, "InPit"] = True
    df.loc[8, "S3"] = np.nan
    out = clean_laps(df)
    log = cleaning_log(out)
    counts = dict(zip(log["Reason"], log["Laps"]))
    assert counts["standing_start"] == 1
    assert counts["pit_in_out"] == 1
    assert counts["imputed_S3"] == 1
    assert counts["included"] == len(df) - 2
    assert log.loc[~log["Reason"].str.startswith("imputed"), "Laps"].sum() == len(df)
