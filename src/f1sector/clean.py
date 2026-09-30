"""Tag laps that should not be used for pace comparison, and repair what can be repaired.

Nothing is dropped here. Every lap gets an ``ExcludeReason`` (empty when the lap is
usable) so the exclusions can be audited and filtered downstream, for example in Tableau.
Rules run in order and the first match wins:

1. ``deleted``        lap time removed by race control (track limits)
2. ``pit_in_out``     in lap or out lap
3. ``track_status``   any yellow, safety car, VSC or red flag during the lap
4. ``standing_start`` lap 1 of a race or sprint
5. ``missing_timing`` a time is still missing after imputation
6. ``timing_mismatch`` S1 + S2 + S3 disagrees with the lap time
7. ``slow_lap``       slower than 107% of the driver's best clean lap in that session
8. ``sector_outlier`` a sector whose robust (median/MAD) z score is above the threshold on the slow side,
                      computed per driver and stint

Imputation: when exactly one of S1, S2, S3 and LapTime is missing, it is rebuilt from
the other three (the lap time is the sum of the sectors). ``Imputed`` names the column.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from f1sector import SECTORS

SESSION_KEYS = ["Year", "Event", "Session"]
DRIVER_KEYS = SESSION_KEYS + ["Driver"]

# FastF1 TrackStatus codes: 1 green, 2 yellow, 4 safety car, 5 red, 6 VSC, 7 VSC ending.
NON_GREEN = set("24567")
RACE_SESSIONS = {"R", "S"}

SLOW_LAP_FACTOR = 1.07
MISMATCH_TOLERANCE_S = 0.1
OUTLIER_Z = 3.5
# Sector timing resolves to the millisecond but a clean lap still varies by tenths. Flooring
# the MAD stops a very consistent driver's normal 0.1 s wobble reading as an outlier: with
# this floor a sector has to be at least ~0.26 s off the group median to be flagged.
MAD_FLOOR_S = 0.05
MIN_GROUP_FOR_STINT = 5


def impute_single_missing(df: pd.DataFrame) -> pd.DataFrame:
    """Fill a lap's one missing timing value from the other three."""
    df = df.copy()
    cols = list(SECTORS) + ["LapTime"]
    missing = df[cols].isna()
    one = missing.sum(axis=1) == 1
    df["Imputed"] = ""

    sector_sum = df[list(SECTORS)].sum(axis=1, min_count=2)
    for col in SECTORS:
        rows = one & missing[col]
        others = df.loc[rows, [s for s in SECTORS if s != col]].sum(axis=1)
        value = df.loc[rows, "LapTime"] - others
        ok = value > 0
        df.loc[value[ok].index, col] = value[ok]
        df.loc[value[ok].index, "Imputed"] = col

    rows = one & missing["LapTime"]
    df.loc[rows, "LapTime"] = sector_sum[rows]
    df.loc[rows, "Imputed"] = "LapTime"
    return df


def robust_z(x: pd.Series, mad_floor: float = MAD_FLOOR_S) -> pd.Series:
    """Median/MAD z score, with the MAD floored. Zeros when the group is too small."""
    med = x.median()
    mad = max((x - med).abs().median(), mad_floor)
    if len(x) < 3 or not np.isfinite(mad) or mad == 0:
        return pd.Series(0.0, index=x.index)
    return 0.6745 * (x - med) / mad


def _sector_outliers(df: pd.DataFrame, candidates: pd.Series, z: float) -> pd.Series:
    """True for candidate laps with any sector more than ``z`` robust SDs slower than usual.

    Only the slow side is flagged. Traffic, lock-ups and mistakes cost time; an unusually
    fast sector in a race is a genuine push lap (fastest lap attempt, low fuel, new tyres),
    and fast timing glitches are already caught by the mismatch rule.

    Grouped per stint so tyre wear and fuel burn do not read as outliers; stints
    with too few laps fall back to the driver's whole session.
    """
    pool = df[candidates]
    stint_size = pool.groupby(DRIVER_KEYS + ["Stint"], dropna=False)["LapTime"].transform("size")
    group_stint = pool["Stint"].where(stint_size >= MIN_GROUP_FOR_STINT, -1)
    keys = [pool[k] for k in DRIVER_KEYS] + [group_stint.fillna(-1)]

    flagged = pd.Series(False, index=pool.index)
    for s in SECTORS:
        scores = pool.groupby(keys, dropna=False)[s].transform(robust_z)
        flagged |= scores > z
    return flagged.reindex(df.index, fill_value=False)


def clean_laps(
    laps: pd.DataFrame,
    slow_factor: float = SLOW_LAP_FACTOR,
    outlier_z: float = OUTLIER_Z,
) -> pd.DataFrame:
    df = impute_single_missing(laps.reset_index(drop=True))
    reason = pd.Series("", index=df.index, dtype=object)

    def tag(mask: pd.Series, label: str) -> None:
        reason[mask & (reason == "")] = label

    tag(df["Deleted"], "deleted")
    tag(df["InPit"], "pit_in_out")
    tag(df["TrackStatus"].map(lambda s: bool(NON_GREEN & set(s))), "track_status")
    tag(df["Session"].isin(RACE_SESSIONS) & (df["LapNumber"] == 1), "standing_start")
    tag(df[list(SECTORS) + ["LapTime"]].isna().any(axis=1), "missing_timing")
    tag((df[list(SECTORS)].sum(axis=1) - df["LapTime"]).abs() > MISMATCH_TOLERANCE_S,
        "timing_mismatch")

    ok = reason == ""
    best = df["LapTime"].where(ok).groupby([df[k] for k in DRIVER_KEYS]).transform("min")
    tag(ok & (df["LapTime"] > slow_factor * best), "slow_lap")

    tag(_sector_outliers(df, reason == "", outlier_z), "sector_outlier")

    df["ExcludeReason"] = reason
    df["Included"] = reason == ""
    return df


def cleaning_log(df: pd.DataFrame) -> pd.DataFrame:
    """Lap counts per session and exclusion reason, plus imputation counts."""
    counts = (
        df.assign(Reason=df["ExcludeReason"].replace("", "included"))
        .groupby(SESSION_KEYS + ["Reason"]).size().rename("Laps").reset_index()
    )
    imputed = (
        df[df["Imputed"] != ""]
        .assign(Reason=lambda d: "imputed_" + d["Imputed"])
        .groupby(SESSION_KEYS + ["Reason"]).size().rename("Laps").reset_index()
    )
    return pd.concat([counts, imputed], ignore_index=True).sort_values(SESSION_KEYS + ["Reason"])
