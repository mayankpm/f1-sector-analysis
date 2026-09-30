"""Static charts for the README. The interactive views live in Tableau."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.colors import LinearSegmentedColormap  # noqa: E402

from f1sector import SECTORS  # noqa: E402

SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_2 = "#52514e"
GRID = "#e4e3df"
SERIES = ["#2a78d6", "#eb6834", "#1baf7a"]  # categorical slots 1 to 3
BLUES = LinearSegmentedColormap.from_list(
    "blues", ["#cde2fb", "#86b6ef", "#3987e5", "#256abf", "#184f95", "#0d366b"])

plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
    "axes.edgecolor": GRID, "axes.labelcolor": INK_2, "text.color": INK,
    "xtick.color": INK_2, "ytick.color": INK_2, "axes.grid": True, "grid.color": GRID,
    "grid.linewidth": 0.8, "axes.spines.top": False, "axes.spines.right": False,
    "font.size": 10, "axes.titlesize": 12, "axes.titleweight": "bold",
})


def sector_heatmap(summary: pd.DataFrame, event: str, session: str, path: Path,
                   top: int = 20) -> None:
    """Drivers by sector, shaded by gap to the fastest time in that sector."""
    d = summary[(summary["Event"] == event) & (summary["Session"] == session)]
    grid = d.pivot_table(index="Driver", columns="Sector", values="DeltaBest")[list(SECTORS)]
    grid = grid.loc[grid.sum(axis=1).sort_values().index].head(top)

    fig, ax = plt.subplots(figsize=(5.2, 0.32 * len(grid) + 1.4))
    vmax = float(np.nanpercentile(grid.to_numpy(), 95)) or 1.0
    im = ax.imshow(grid.to_numpy(), cmap=BLUES, vmin=0, vmax=vmax, aspect="auto")
    ax.grid(False)
    ax.set_xticks(range(3), SECTORS)
    ax.set_yticks(range(len(grid)), grid.index)
    ax.tick_params(length=0)
    for (i, j), v in np.ndenumerate(grid.to_numpy()):
        if np.isfinite(v):
            ax.text(j, i, f"{v:.3f}", ha="center", va="center", fontsize=8,
                    color="white" if v > 0.45 * vmax else INK)
    ax.set_title(f"{event} {session}: gap to fastest sector (s)", loc="left")
    cb = fig.colorbar(im, ax=ax, fraction=0.05, pad=0.03)
    cb.outline.set_visible(False)
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)


def stint_trend(sector_laps: pd.DataFrame, event: str, drivers: list[str], path: Path,
                session: str = "R") -> None:
    """Clean race laps: sector time against lap number, one panel per sector."""
    d = sector_laps[(sector_laps["Event"] == event) & (sector_laps["Session"] == session)
                    & sector_laps["Included"] & sector_laps["Driver"].isin(drivers)]
    fig, axes = plt.subplots(1, 3, figsize=(11, 3.4))
    for ax, sector in zip(axes, SECTORS):
        for color, drv in zip(SERIES, drivers):
            s = d[(d["Driver"] == drv) & (d["Sector"] == sector)].sort_values("LapNumber")
            # Break the line across pit stops and neutralised laps instead of joining them.
            gap = s["LapNumber"].diff().fillna(1) > 1
            for i, (_, seg) in enumerate(s.groupby(gap.cumsum())):
                ax.plot(seg["LapNumber"], seg["SectorTime"], color=color, lw=2,
                        marker="o", ms=3, label=drv if i == 0 else None)
        ax.set_title(sector, loc="left")
        ax.set_xlabel("Lap")
    axes[0].set_ylabel("Sector time (s)")
    axes[0].legend(frameon=False, loc="upper right")
    fig.suptitle(f"{event} race: clean sector times by lap", x=0.01, ha="left",
                 fontweight="bold")
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)


def theoretical_gain(drivers: pd.DataFrame, event: str, session: str, path: Path,
                     top: int = 20) -> None:
    """Time left on the table: best lap minus the sum of the driver's best sectors."""
    d = drivers[(drivers["Event"] == event) & (drivers["Session"] == session)]
    d = d.dropna(subset=["TheoreticalGain"]).nsmallest(top, "BestLap")[::-1]
    fig, ax = plt.subplots(figsize=(5.8, 0.3 * len(d) + 1.2))
    ax.barh(d["Driver"], d["TheoreticalGain"], color=SERIES[0], height=0.7)
    ax.grid(axis="y", visible=False)
    ax.set_xlabel("Best lap minus theoretical best (s)")
    ax.set_title(f"{event} {session}: time left in the lap", loc="left")
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)
