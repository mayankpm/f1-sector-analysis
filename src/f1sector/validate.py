"""Reconcile the lap timing feed against the official classification.

The two come from different sources: FastF1 rebuilds laps from F1's live timing stream,
and takes the classification from the Jolpica (formerly Ergast) results database. One
overlap: the live stream has no lap 1 time in races, so FastF1 fills it from Jolpica.
Agreement between them is evidence the laps can be trusted; every disagreement is
listed with a ``Result``:

* ``match``           the two agree (to the millisecond for times)
* ``explained``       a known difference in definition, described in ``Note``
* ``not_comparable``  the feed lacks what the check needs, described in ``Note``
* ``MISMATCH``        an unexplained disagreement, to investigate

Checks:

1. ``best_quali_lap`` (Q, SQ): a driver's best non-deleted feed lap equals their best
   official Q1/Q2/Q3 time.
2. ``laps_completed`` (R, S): the number of laps in the feed equals the official count.
3. ``winner_race_time`` (R, S): the winner's lap times add up to the official race time.
"""

from __future__ import annotations

import pandas as pd

from f1sector.clean import QUALI_SESSIONS, RACE_SESSIONS, SESSION_KEYS

TIME_TOLERANCE_S = 0.0005  # official times are to the millisecond
COLUMNS = SESSION_KEYS + ["Driver", "Check", "Official", "Feed", "Diff", "Result", "Note"]


# Validate helper: build one result row (official vs feed value, difference, result, note).
def _row(keys, driver, check, official, feed, result, note=""):
    diff = feed - official if pd.notna(official) and pd.notna(feed) else float("nan")
    return dict(zip(SESSION_KEYS, keys), Driver=driver, Check=check, Official=official,
                Feed=feed, Diff=diff, Result=result, Note=note)


# Validate helper: 'match' if two times agree to the millisecond, else 'MISMATCH'.
def _time_result(official, feed):
    return "match" if abs(feed - official) < TIME_TOLERANCE_S else "MISMATCH"


# Validate check: each driver's best non-deleted feed lap vs their best official Q1/Q2/Q3 time.
def _best_quali_lap(keys, laps, official):
    rows = []
    feed_best = laps.loc[~laps["Deleted"]].groupby("Driver")["LapTime"].min()
    for _, o in official.iterrows():
        feed = feed_best.get(o["Driver"], float("nan"))
        best = o["OfficialBest"]
        if pd.isna(best) and pd.isna(feed):
            continue
        if pd.isna(best):
            rows.append(_row(keys, o["Driver"], "best_quali_lap", best, feed, "MISMATCH",
                             "classification lists no qualifying time but the feed has laps"))
        elif pd.isna(feed):
            rows.append(_row(keys, o["Driver"], "best_quali_lap", best, feed, "MISMATCH",
                             "official time has no lap in the feed"))
        else:
            result = _time_result(best, feed)
            note = ("feed lap faster than any counted lap; excluded as not_counted"
                    if result == "MISMATCH" and feed < best else "")
            rows.append(_row(keys, o["Driver"], "best_quali_lap", best, feed, result, note))
    return rows


# Validate checks: laps completed per driver, and the winner's summed laps vs official race time.
def _race_checks(keys, laps, official):
    rows = []
    by_driver = {d: g.sort_values("LapNumber") for d, g in laps.groupby("Driver")}
    for _, o in official.iterrows():
        drv = o["Driver"]
        dl = by_driver.get(drv, laps.iloc[0:0])
        feed_laps = float(dl["LapNumber"].max()) if len(dl) else 0.0
        result, note = ("match", "") if feed_laps == o["Laps"] else ("MISMATCH", "")
        if result == "MISMATCH" and o["Status"] == "Disqualified":
            result, note = "explained", "disqualified: the classification counts no laps"
        elif (result == "MISMATCH" and o["Status"] == "Retired" and feed_laps == o["Laps"] + 1
              and pd.isna(dl["LapTime"].iat[-1])):
            result, note = "explained", "retired: the feed includes the unfinished lap, which has no time"
        rows.append(_row(keys, drv, "laps_completed", float(o["Laps"]), feed_laps, result, note))

        if pd.notna(o["RaceTime"]):
            missing = int(dl["LapTime"].isna().sum())
            total = float(dl["LapTime"].sum())
            if missing:
                rows.append(_row(keys, drv, "winner_race_time", o["RaceTime"], total, "not_comparable",
                                 f"{missing} lap(s) have no time: a sprint's lap 1, or laps "
                                 "under a safety car, red flag or restart"))
            else:
                rows.append(_row(keys, drv, "winner_race_time", o["RaceTime"], total,
                                 _time_result(o["RaceTime"], total)))
    return rows


# Validate step: run the qualifying or race checks for every session in the classification.
def reconcile(raw_laps: pd.DataFrame, classification: pd.DataFrame) -> pd.DataFrame:
    """One row per check. ``raw_laps`` are the laps before cleaning or imputation."""
    rows = []
    for keys, official in classification.groupby(SESSION_KEYS, sort=False):
        mask = pd.Series(True, index=raw_laps.index)
        for k, v in zip(SESSION_KEYS, keys):
            mask &= raw_laps[k] == v
        laps = raw_laps[mask]
        if keys[-1] in QUALI_SESSIONS:
            rows += _best_quali_lap(keys, laps, official)
        elif keys[-1] in RACE_SESSIONS and len(laps):
            rows += _race_checks(keys, laps, official)
    return pd.DataFrame(rows, columns=COLUMNS)


# Validate output: count of each result per check, printed by the CLI.
def summarize(checks: pd.DataFrame) -> pd.DataFrame:
    """Counts of each result per check, for the command line and the README."""
    return checks.pivot_table(index="Check", columns="Result", values="Driver",
                              aggfunc="count", fill_value=0)
