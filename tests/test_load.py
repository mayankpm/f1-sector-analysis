import pandas as pd

from f1sector.load import laps_to_frame


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
