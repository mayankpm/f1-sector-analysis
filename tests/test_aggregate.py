import numpy as np
import pandas as pd
import pytest

from f1sector.aggregate import (
    driver_summary, sector_long, sector_summary, session_comparison, stint_trends,
)
from f1sector.clean import clean_laps
from f1sector.export import analyse, write_csvs


@pytest.fixture
def grid(laps_factory):
    """Three drivers, two teams, a qualifying and a race, no noise so values are exact."""
    frames = []
    for session in ("Q", "R"):
        frames += [
            laps_factory("AAA", "T1", session, s=(30.0, 40.0, 20.0), noise=0),
            laps_factory("BBB", "T1", session, s=(30.2, 39.9, 20.1), noise=0),
            laps_factory("CCC", "T2", session, s=(30.5, 40.5, 20.5), noise=0),
        ]
    return clean_laps(pd.concat(frames, ignore_index=True))


def row(df, **match):
    mask = np.logical_and.reduce([df[k] == v for k, v in match.items()])
    return df[mask].iloc[0]


def test_sector_long_has_three_rows_per_lap(grid):
    long = sector_long(grid)
    assert len(long) == 3 * len(grid)
    assert set(long["Sector"]) == {"S1", "S2", "S3"}


def test_sector_summary_deltas(grid):
    s = sector_summary(grid)
    r = row(s, Session="Q", Driver="BBB", Sector="S1")
    assert r["Best"] == pytest.approx(30.2)
    assert r["DeltaBest"] == pytest.approx(0.2)
    assert r["RankBest"] == 2
    # BBB is fastest in S2
    assert row(s, Session="Q", Driver="BBB", Sector="S2")["RankBest"] == 1
    assert row(s, Session="Q", Driver="AAA", Sector="S2")["DeltaBest"] == pytest.approx(0.1)


def test_teammate_delta(grid):
    s = sector_summary(grid)
    assert row(s, Session="Q", Driver="AAA", Sector="S1")["DeltaTeammateBest"] == pytest.approx(-0.2)
    assert row(s, Session="Q", Driver="BBB", Sector="S1")["DeltaTeammateBest"] == pytest.approx(0.2)
    # CCC has no teammate in this data
    assert np.isnan(row(s, Session="Q", Driver="CCC", Sector="S1")["DeltaTeammateBest"])


def test_summary_ignores_excluded_laps(laps_factory):
    df = laps_factory(session="Q", noise=0)
    df.loc[2, ["S1", "LapTime"]] = [25.0, 85.0]  # impossibly fast, but it is an out lap
    df.loc[2, "InPit"] = True
    s = sector_summary(clean_laps(df))
    assert row(s, Sector="S1")["Best"] == pytest.approx(30.0)
    assert row(s, Sector="S1")["Laps"] == len(df) - 1


def test_theoretical_best(laps_factory):
    df = laps_factory(session="Q", noise=0, n=3)
    # Each lap has a different best sector: theoretical best combines them.
    df.loc[0, ["S1", "S2", "S3"]] = [29.8, 40.2, 20.1]
    df.loc[1, ["S1", "S2", "S3"]] = [30.1, 39.7, 20.2]
    df.loc[2, ["S1", "S2", "S3"]] = [30.0, 40.1, 19.9]
    df["LapTime"] = df[["S1", "S2", "S3"]].sum(axis=1)
    laps = clean_laps(df)
    d = driver_summary(laps, sector_summary(laps)).iloc[0]
    assert d["TheoreticalBest"] == pytest.approx(29.8 + 39.7 + 19.9)
    assert d["BestLap"] == pytest.approx(90.0)
    assert d["TheoreticalGain"] == pytest.approx(0.6)


def test_driver_summary_weakest_sector_and_gap(grid):
    d = driver_summary(grid, sector_summary(grid))
    ccc = row(d, Session="Q", Driver="CCC")
    assert ccc["GapToPole"] == pytest.approx(1.5)
    assert ccc["WeakestSector"] == "S2"
    assert ccc["TotalLaps"] == 12 and ccc["CleanLaps"] == 12


def test_stint_slope_recovers_known_degradation(laps_factory):
    df = laps_factory(session="R", n=20, noise=0)
    df["S3"] = 20.0 + 0.05 * df["TyreLife"]  # 50 ms per lap in S3
    df["LapTime"] = df[["S1", "S2", "S3"]].sum(axis=1)
    t = stint_trends(clean_laps(df))
    assert len(t) == 1
    assert t.loc[0, "S3Slope"] == pytest.approx(0.05)
    assert t.loc[0, "S1Slope"] == pytest.approx(0.0, abs=1e-9)
    assert t.loc[0, "LapTimeSlope"] == pytest.approx(0.05)


def test_stint_trends_skip_short_stints_and_qualifying(laps_factory):
    df = pd.concat([laps_factory(session="R", n=4), laps_factory(session="Q", n=20)])
    assert stint_trends(clean_laps(df)).empty


def test_session_comparison_is_wide(grid):
    wide = session_comparison(sector_summary(grid))
    assert {"DeltaBest_Q", "DeltaBest_R", "RankBest_Q"} <= set(wide.columns)
    assert len(wide) == 3 * 3


def test_end_to_end_csv_export(grid, tmp_path, laps_factory):
    raw = pd.concat([laps_factory("AAA", session="R", n=15),
                     laps_factory("BBB", "T2", session="R", n=15, seed=2)])
    paths = write_csvs(analyse(raw), tmp_path)
    names = {p.stem for p in paths}
    assert names == {"sector_laps", "sector_summary", "driver_summary", "stint_trends",
                     "session_comparison", "cleaning_log"}
    back = pd.read_csv(tmp_path / "sector_laps.csv")
    assert len(back) == 3 * 30
