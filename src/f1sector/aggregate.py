"""Sector-level aggregates over cleaned laps. All inputs are the output of ``clean_laps``."""

from __future__ import annotations

import numpy as np
import pandas as pd

from f1sector import SECTORS
from f1sector.clean import DRIVER_KEYS, RACE_SESSIONS, SESSION_KEYS

MIN_STINT_LAPS = 5


def sector_long(df: pd.DataFrame) -> pd.DataFrame:
    """One row per lap and sector. Keeps excluded laps so they can be filtered, not lost."""
    id_cols = [c for c in df.columns if c not in SECTORS]
    long = df.melt(id_vars=id_cols, value_vars=list(SECTORS), var_name="Sector",
                   value_name="SectorTime")
    usable = long["SectorTime"].where(long["Included"])
    by_driver = [long[k] for k in DRIVER_KEYS] + [long["Sector"]]
    by_session = [long[k] for k in SESSION_KEYS] + [long["Sector"]]
    long["DeltaToDriverBest"] = long["SectorTime"] - usable.groupby(by_driver).transform("min")
    long["DeltaToSessionBest"] = long["SectorTime"] - usable.groupby(by_session).transform("min")
    return long.sort_values(DRIVER_KEYS + ["LapNumber", "Sector"]).reset_index(drop=True)


def sector_summary(df: pd.DataFrame) -> pd.DataFrame:
    """Per driver, session and sector: distribution of clean sector times and deltas."""
    long = sector_long(df)
    long = long[long["Included"]]
    keys = DRIVER_KEYS + ["Team", "Sector"]
    g = long.groupby(keys)["SectorTime"]
    out = pd.DataFrame({
        "Laps": g.size(),
        "Best": g.min(),
        "Median": g.median(),
        "Mean": g.mean(),
        "Std": g.std(),
        "P25": g.quantile(0.25),
        "P75": g.quantile(0.75),
    }).reset_index()

    sess = SESSION_KEYS + ["Sector"]
    out["DeltaBest"] = out["Best"] - out.groupby(sess)["Best"].transform("min")
    out["DeltaMedian"] = out["Median"] - out.groupby(sess)["Median"].transform("median")
    out["RankBest"] = out.groupby(sess)["Best"].rank(method="min").astype(int)

    # Teammate delta: compare against the other car of the same team in the same session.
    team = sess + ["Team"]
    for stat in ("Best", "Median"):
        total = out.groupby(team)[stat].transform("sum")
        n = out.groupby(team)[stat].transform("count")
        mate = (total - out[stat]).where(n == 2)
        out[f"DeltaTeammate{stat}"] = out[stat] - mate
    return out.sort_values(sess + ["RankBest"]).reset_index(drop=True)


def driver_summary(df: pd.DataFrame, summary: pd.DataFrame) -> pd.DataFrame:
    """Per driver and session: best lap, theoretical best from best sectors, weakest sector."""
    clean = df[df["Included"]]
    g = clean.groupby(DRIVER_KEYS + ["Team"])
    out = pd.DataFrame({
        "CleanLaps": g.size(),
        "BestLap": g["LapTime"].min(),
        "MedianLap": g["LapTime"].median(),
    }).reset_index()
    out = out.merge(
        df.groupby(DRIVER_KEYS).size().rename("TotalLaps").reset_index(), on=DRIVER_KEYS)

    best = summary.pivot_table(index=DRIVER_KEYS, columns="Sector", values="Best")
    delta = summary.pivot_table(index=DRIVER_KEYS, columns="Sector", values="DeltaBest")
    extra = pd.DataFrame({
        "TheoreticalBest": best[list(SECTORS)].sum(axis=1, min_count=3),
        "WeakestSector": delta[list(SECTORS)].idxmax(axis=1),
        "WeakestSectorDelta": delta[list(SECTORS)].max(axis=1),
    }).reset_index()
    out = out.merge(extra, on=DRIVER_KEYS, how="left")
    out["TheoreticalGain"] = out["BestLap"] - out["TheoreticalBest"]
    out["GapToPole"] = out["BestLap"] - out.groupby(SESSION_KEYS)["BestLap"].transform("min")
    return out.sort_values(SESSION_KEYS + ["BestLap"]).reset_index(drop=True)


def stint_trends(df: pd.DataFrame, min_laps: int = MIN_STINT_LAPS) -> pd.DataFrame:
    """Race only: least squares slope of each sector time against tyre age, per stint.

    The slope mixes tyre wear with fuel burn (cars get lighter every lap), so a
    negative or flat slope is common and the numbers compare drivers on the same
    strategy rather than measure degradation in isolation.
    """
    clean = df[df["Included"] & df["Session"].isin(RACE_SESSIONS)].dropna(subset=["TyreLife"])
    rows = []
    for key, stint in clean.groupby(DRIVER_KEYS + ["Team", "Stint", "Compound"]):
        if len(stint) < min_laps or stint["TyreLife"].nunique() < 3:
            continue
        x = stint["TyreLife"].to_numpy(float)
        rec = dict(zip(DRIVER_KEYS + ["Team", "Stint", "Compound"], key))
        rec.update(Laps=len(stint), TyreLifeStart=x.min(), TyreLifeEnd=x.max())
        for s in list(SECTORS) + ["LapTime"]:
            slope, intercept = np.polyfit(x, stint[s].to_numpy(float), 1)
            rec[f"{s}Slope"] = slope
            if s == "LapTime":
                rec["LapTimeIntercept"] = intercept
        rows.append(rec)
    return pd.DataFrame(rows)


def session_comparison(summary: pd.DataFrame) -> pd.DataFrame:
    """Wide view of each driver's sector deltas across the sessions of one event."""
    wide = summary.pivot_table(
        index=["Year", "Event", "Driver", "Team", "Sector"], columns="Session",
        values=["DeltaBest", "DeltaMedian", "RankBest"])
    wide.columns = [f"{stat}_{sess}" for stat, sess in wide.columns]
    return wide.reset_index()
