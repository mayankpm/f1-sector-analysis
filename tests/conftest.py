import numpy as np
import pandas as pd
import pytest


def make_laps(driver="AAA", team="T1", session="R", n=12, s=(30.0, 40.0, 20.0),
              noise=0.05, stint=1, start_lap=1, seed=0, **overrides):
    """Synthetic laps in the shape produced by ``load.laps_to_frame``."""
    rng = np.random.default_rng(seed)
    rows = []
    for i in range(n):
        s1, s2, s3 = (x + rng.normal(0, noise) for x in s)
        rows.append({
            "Year": 2024, "Event": "Test", "Session": session, "Driver": driver,
            "Team": team, "LapNumber": start_lap + i, "Stint": stint, "Compound": "MEDIUM",
            "TyreLife": float(i + 1), "TrackStatus": "1", "IsAccurate": True,
            "Deleted": False, "InPit": False, "S1": s1, "S2": s2, "S3": s3,
            "LapTime": s1 + s2 + s3,
        })
    df = pd.DataFrame(rows)
    for col, value in overrides.items():
        df[col] = value
    df["LapNumber"] = df["LapNumber"].astype("Int64")
    return df


@pytest.fixture
def laps_factory():
    return make_laps
