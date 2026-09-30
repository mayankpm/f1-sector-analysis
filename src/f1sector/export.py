"""Write the analysis tables as tidy CSVs. These are the data sources for the Tableau workbook."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from f1sector.aggregate import (
    driver_summary, sector_long, sector_summary, session_comparison, stint_trends,
)
from f1sector.clean import clean_laps, cleaning_log


@dataclass
class Results:
    laps: pd.DataFrame
    sector_laps: pd.DataFrame
    sector_summary: pd.DataFrame
    driver_summary: pd.DataFrame
    stint_trends: pd.DataFrame
    session_comparison: pd.DataFrame
    cleaning_log: pd.DataFrame

    def tables(self) -> dict[str, pd.DataFrame]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__ if name != "laps"}


def analyse(raw: pd.DataFrame, **clean_kwargs) -> Results:
    laps = clean_laps(raw, **clean_kwargs)
    summary = sector_summary(laps)
    return Results(
        laps=laps,
        sector_laps=sector_long(laps),
        sector_summary=summary,
        driver_summary=driver_summary(laps, summary),
        stint_trends=stint_trends(laps),
        session_comparison=session_comparison(summary),
        cleaning_log=cleaning_log(laps),
    )


def write_csvs(results: Results, out_dir: str | Path) -> list[Path]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    paths = []
    for name, table in results.tables().items():
        path = out / f"{name}.csv"
        table.to_csv(path, index=False, float_format="%.4f")
        paths.append(path)
    return paths
