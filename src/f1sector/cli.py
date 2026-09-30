"""Load F1 sessions with FastF1, clean the laps, aggregate sector times and export CSVs."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from f1sector.export import analyse, write_csvs
from f1sector.load import enable_cache, load_sessions


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="f1sector", description=__doc__)
    p.add_argument("--year", type=int, required=True)
    p.add_argument("--event", action="append", required=True,
                   help="event name or round number; repeat for several events")
    p.add_argument("--session", action="append", default=None,
                   help="session code such as Q, R, S, FP2; repeat for several (default Q and R)")
    p.add_argument("--out", type=Path, default=Path("output"))
    p.add_argument("--cache", type=Path, default=Path("cache"))
    p.add_argument("--slow-factor", type=float, default=1.07)
    p.add_argument("--outlier-z", type=float, default=3.5)
    p.add_argument("--plots", action="store_true", help="also render PNG charts")
    p.add_argument("-v", "--verbose", action="store_true")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING,
                        format="%(levelname)s %(message)s")
    enable_cache(args.cache)
    sessions = args.session or ["Q", "R"]
    raw = load_sessions(args.year, args.event, sessions)
    results = analyse(raw, slow_factor=args.slow_factor, outlier_z=args.outlier_z)
    for path in write_csvs(results, args.out):
        print(f"wrote {path}")

    if args.plots:
        from f1sector import plots

        img = args.out / "img"
        img.mkdir(parents=True, exist_ok=True)
        ds = results.driver_summary
        for (event, session), grp in ds.groupby(["Event", "Session"]):
            slug = f"{event}_{session}".lower().replace(" ", "_")
            plots.sector_heatmap(results.sector_summary, event, session,
                                 img / f"{slug}_sector_heatmap.png")
            plots.theoretical_gain(ds, event, session, img / f"{slug}_theoretical_gain.png")
            if session == "R":
                fastest = grp.nsmallest(3, "MedianLap")["Driver"].tolist()
                plots.stint_trend(results.sector_laps, event, fastest,
                                  img / f"{slug}_stint_trend.png")
        print(f"wrote charts to {img}")

    log = results.cleaning_log
    included = log.loc[log["Reason"] == "included", "Laps"].sum()
    total = len(results.laps)
    print(f"{total} laps loaded, {included} used for pace ({total - included} excluded)")
    return 0
