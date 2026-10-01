# Tableau dashboard

The pipeline writes tidy CSVs designed to drop straight into Tableau (Desktop or Public). This page describes the data model and the worksheets used for exploration. The 2024 sample data is in [`data/2024`](data/2024).

Published version: [F1 Sector Analysis 2024 on Tableau Public](https://public.tableau.com/app/profile/mayank.manohar.polepalli/viz/F1SectorAnalysis2024/Overview). It contains worksheets 1, 2 and 4 below on one dashboard, with Event and Session filters shared across sheets.

## Data model

Connect to the folder as a text file source and add the tables below. Relate them (Tableau relationships, not joins) on the listed fields so a single Event and Session filter drives every sheet.

| Table | Relate on |
|---|---|
| `sector_summary.csv` | (base table) |
| `sector_laps.csv` | Year, Event, Session, Driver, Sector |
| `driver_summary.csv` | Year, Event, Session, Driver |
| `stint_trends.csv` | Year, Event, Session, Driver |
| `cleaning_log.csv` | Year, Event, Session |

Set `LapNumber`, `Stint` and `RankBest` to Dimension (discrete) and `Included` to a Boolean filter.

## Worksheets

**1. Sector gap heatmap** (`sector_summary`)
* Columns: `Sector`. Rows: `Driver`, sorted ascending by SUM(`DeltaBest`).
* Marks: Square. Color: `DeltaBest`, sequential single hue, starting at 0. Label: `DeltaBest` formatted to 3 decimals.
* Answers: where on the lap each driver gains or loses time against the fastest driver in that sector.

**2. Sector time by lap** (`sector_laps`)
* Filter: `Included` = True, `Session` = R.
* Columns: `LapNumber`, then `Sector` as small multiples. Rows: `SectorTime` (independent axis per sector).
* Marks: Line with markers. Color: `Driver` (limit to 3 or 4 drivers with a multi select filter so colors stay distinct). Detail: `Stint`, which breaks the line at pit stops.
* Answers: how each sector evolves over a stint and after each pit stop.

**3. Teammate comparison** (`sector_summary`)
* Columns: `DeltaTeammateMedian`. Rows: `Team`, `Driver`. Color: `Sector`.
* Marks: Bar, with a reference line at 0.
* Answers: which teammate is quicker in which part of the lap, using the median so one lap does not decide it.

**4. Time left in the lap** (`driver_summary`)
* Columns: `TheoreticalGain`. Rows: `Driver`, sorted by `BestLap`. Tooltip: `BestLap`, `TheoreticalBest`, `WeakestSector`.
* Answers: how much each driver would gain by stringing together their own best sectors.

**5. Sector distributions** (`sector_laps`)
* Filter: `Included` = True. Columns: `Driver`. Rows: `SectorTime`. Pages or filter: `Sector`.
* Marks: Circle, then Analytics pane, Box Plot.
* Answers: consistency. A tight box is a driver repeating the same sector time; a wide one is traffic, wear or mistakes.

**6. Tyre stint slopes** (`stint_trends`)
* Columns: `Compound`. Rows: `LapTimeSlope` (and `S1Slope` to `S3Slope` as a Measure Names view). Color: `Compound`.
* Answers: how quickly pace changes with tyre age on each compound. Positive means slowing down.

**7. Cleaning audit** (`cleaning_log`)
* Columns: SUM(`Laps`). Rows: `Event`, `Session`. Color: `Reason`. Marks: stacked Bar.
* Answers: how many laps each rule removed, so the pace comparisons can be trusted.

## Dashboard

Put the Event and Session filters in one row across the top and set them to "Apply to all using related data sources". Lay out sheets 1 and 4 side by side, with 2 below them at full width, and put 3, 5, 6 and 7 on a second tab. Use sheet 1 as a filter action: clicking a driver filters sheets 2, 4 and 5.

To refresh with new races, rerun `f1sector` into the same folder and use Data, Refresh All Extracts.
