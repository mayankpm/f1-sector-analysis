"""Load session laps from FastF1 into a flat frame with times in seconds."""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

log = logging.getLogger(__name__)

# Columns kept from FastF1's Laps object. Timedeltas are converted to float seconds.
_TIME_COLS = {
    "LapTime": "LapTime",
    "Sector1Time": "S1",
    "Sector2Time": "S2",
    "Sector3Time": "S3",
}
_KEEP_COLS = [
    "Driver", "Team", "LapNumber", "Stint", "Compound", "TyreLife",
    "TrackStatus", "IsAccurate", "Deleted", "PitInTime", "PitOutTime",
]


def enable_cache(path: str | Path) -> None:
    import fastf1

    Path(path).mkdir(parents=True, exist_ok=True)
    fastf1.Cache.enable_cache(str(path))
    fastf1.set_log_level("WARNING")


def laps_to_frame(laps: pd.DataFrame, year: int, event: str, session: str) -> pd.DataFrame:
    """Flatten a FastF1 Laps frame. Kept separate from I/O so it can be tested."""
    out = laps[_KEEP_COLS].copy()
    for src, dst in _TIME_COLS.items():
        out[dst] = laps[src].dt.total_seconds()
    out["InPit"] = laps["PitInTime"].notna() | laps["PitOutTime"].notna()
    out = out.drop(columns=["PitInTime", "PitOutTime"])
    # Deleted is only populated when race control messages are loaded; treat unknown as kept.
    out["Deleted"] = out["Deleted"].astype("boolean").fillna(False).astype(bool)
    out["IsAccurate"] = out["IsAccurate"].astype("boolean").fillna(False).astype(bool)
    out["TrackStatus"] = out["TrackStatus"].fillna("").astype(str)
    out["LapNumber"] = out["LapNumber"].astype("Int64")
    out.insert(0, "Session", session)
    out.insert(0, "Event", event)
    out.insert(0, "Year", year)
    return out.reset_index(drop=True)


def load_session(year: int, event: str, session: str) -> pd.DataFrame:
    """Download (or read from cache) one session and return its flattened laps."""
    import fastf1

    s = fastf1.get_session(year, resolve_event(event), session)
    # Messages are needed for FastF1 to mark laps deleted for track limits.
    s.load(laps=True, telemetry=False, weather=False, messages=True)
    name = s.event["EventName"].replace(" Grand Prix", "")
    log.info("loaded %s %s %s: %d laps", year, name, s.name, len(s.laps))
    return laps_to_frame(s.laps, year, name, session.upper())


def resolve_event(event: str | int) -> str | int:
    """Round numbers arrive from the command line as strings. FastF1 fuzzy matches any
    string against event names, so "8" would silently load the wrong race; pass an int."""
    if isinstance(event, str) and event.strip().isdigit():
        return int(event)
    return event


def load_sessions(year: int, events: list[str], sessions: list[str]) -> pd.DataFrame:
    frames = []
    seen = set()
    for event in events:
        for session in sessions:
            try:
                frame = load_session(year, event, session)
            except Exception as exc:  # one bad session should not sink the batch
                log.warning("skipping %s %s %s: %s", year, event, session, exc)
                continue
            key = (frame["Event"].iat[0], frame["Session"].iat[0]) if len(frame) else None
            if key in seen:  # e.g. "Bahrain" and "1" both requested
                log.warning("skipping duplicate %s %s %s", year, *key)
                continue
            seen.add(key)
            frames.append(frame)
    if not frames:
        raise RuntimeError("no sessions could be loaded")
    return pd.concat(frames, ignore_index=True)
