import pandas as pd

from f1sector.load import laps_to_frame, resolve_event, results_to_frame


# Regression test for the Bahrain bug: digit strings become ints.
def test_round_numbers_become_ints_so_fastf1_does_not_fuzzy_match_them():
    assert resolve_event("8") == 8
    assert resolve_event(" 24 ") == 24
    assert resolve_event("Monaco") == "Monaco"
    assert resolve_event(3) == 3


# FastF1 timedeltas become seconds, pit times become InPit, unknown Deleted becomes False.
def test_laps_to_frame_converts_times_and_pit_flags():
    td = pd.to_timedelta
    laps = pd.DataFrame({
        "Driver": ["VER", "VER"], "Team": ["Red Bull Racing"] * 2, "LapNumber": [1.0, 2.0],
        "Stint": [1.0, 1.0], "Compound": ["SOFT"] * 2, "TyreLife": [4.0, 5.0],
        "TrackStatus": ["12", "1"], "IsAccurate": [False, True], "Deleted": [None, None],
        "PitInTime": [pd.NaT, pd.NaT], "PitOutTime": [td("1min"), pd.NaT],
        "LapTime": [td("97.284s"), td("96.296s")],
        "Sector1Time": [pd.NaT, td("30.916s")],
        "Sector2Time": [td("41.266s"), td("41.661s")],
        "Sector3Time": [td("23.616s"), td("23.719s")],
    })
    out = laps_to_frame(laps, 2024, "Bahrain", "r")
    assert list(out["InPit"]) == [True, False]
    assert out.loc[1, "S1"] == 30.916
    assert pd.isna(out.loc[0, "S1"])
    assert not out["Deleted"].any()
    assert out.loc[0, "Session"] == "r"
    assert {"Year", "Event", "LapTime", "S2", "S3"} <= set(out.columns)


# OfficialBest is the best of Q1-Q3; RaceTime is set for the winner only.
def test_results_to_frame_takes_best_q_time_and_winner_race_time():
    td = pd.to_timedelta
    results = pd.DataFrame({
        "Abbreviation": ["VER", "LEC", "SAR"], "Position": [1.0, 2.0, 20.0],
        "Status": ["Finished", "Finished", None], "Laps": [57.0, 57.0, 56.0],
        "Q1": [td("90.031s"), td("90.243s"), pd.NaT],
        "Q2": [td("89.374s"), td("89.165s"), pd.NaT],
        "Q3": [td("89.179s"), td("89.407s"), pd.NaT],
        "Time": [td("1:31:44.742"), td("22.457s"), pd.NaT],  # FastF1 stores gaps after P1
    })
    out = results_to_frame(results, 2024, "Bahrain", "Q")
    assert list(out["OfficialBest"].round(3).fillna(-1)) == [89.179, 89.165, -1]
    assert out.loc[0, "RaceTime"] == 5504.742
    assert out["RaceTime"].iloc[1:].isna().all()
    assert out.loc[2, "Status"] == ""
