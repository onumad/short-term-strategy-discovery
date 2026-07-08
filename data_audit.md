# Data Audit

Date generated: 2026-07-07

## Summary

- Raw data directory: `C:\Users\ulzii\Documents\Short Term Strategy Discovery\data\raw`
- Data source: local Databento CSV files only.
- Active instruments discovered: MGC, MNQ
- Detected schema: `timestamp,symbol,open,high,low,close,volume`.
- Timezone assumption: `America/New_York` from timestamp offsets.
- Trading session rule: bars at or after `18:00 ET` map to the next CME trade date.
- RTH rule: `09:30-16:00 ET`; all other included bars are ETH.
- Latest complete shared trading session: `2026-07-02`.
- Initial research window: last 63 shared complete sessions, `2026-04-06` through `2026-07-02`.
- Partial sessions are excluded from first-pass strategy windows.

## Files Discovered

| File | Symbols | Rows | First Timestamp | Last Timestamp | Complete Sessions | Latest Complete Session |
| --- | --- | ---: | --- | --- | ---: | --- |
| `mgc_1m_databento_20230101_20260703.csv` | MGC | 1,211,601 | `2023-01-02T18:00:00-05:00` | `2026-07-02T23:59:00-04:00` | 877 | `2026-07-02` |
| `mnq_1m_databento_20230101_20260703.csv` | MNQ | 1,239,427 | `2023-01-02T18:00:00-05:00` | `2026-07-02T23:59:00-04:00` | 901 | `2026-07-02` |

## Integrity Checks

| File | Sorted | Duplicate Timestamp-Symbol Rows | Bad OHLC Rows | Zero Volume Rows | Negative Volume Rows | Price Range |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| `mgc_1m_databento_20230101_20260703.csv` | true | 0 | 0 | 0 | 0 | 1,811.20 to 5,587.00 |
| `mnq_1m_databento_20230101_20260703.csv` | true | 0 | 0 | 0 | 0 | 10,751.00 to 30,967.75 |

## Session Coverage

A complete session is currently defined as at least `1,000` one-minute bars. This threshold keeps normal Globex sessions while excluding known partial download edges and holiday fragments.

### MGC

- Sessions observed: `904`.
- Complete sessions: `877`.
- Latest complete session: `2026-07-02`.
- Latest complete RTH bars: `390`.
- Latest complete ETH bars: `990`.
- Last observed session counts:

  - `2026-06-22`: `1380` bars
  - `2026-06-23`: `1380` bars
  - `2026-06-24`: `1380` bars
  - `2026-06-25`: `1380` bars
  - `2026-06-26`: `1380` bars
  - `2026-06-29`: `1380` bars
  - `2026-06-30`: `1380` bars
  - `2026-07-01`: `1380` bars
  - `2026-07-02`: `1380` bars
  - `2026-07-03`: `360` bars partial

### MNQ

- Sessions observed: `906`.
- Complete sessions: `901`.
- Latest complete session: `2026-07-02`.
- Latest complete RTH bars: `390`.
- Latest complete ETH bars: `990`.
- Last observed session counts:

  - `2026-06-22`: `1380` bars
  - `2026-06-23`: `1380` bars
  - `2026-06-24`: `1380` bars
  - `2026-06-25`: `1380` bars
  - `2026-06-26`: `1380` bars
  - `2026-06-29`: `1380` bars
  - `2026-06-30`: `1380` bars
  - `2026-07-01`: `1380` bars
  - `2026-07-02`: `1380` bars
  - `2026-07-03`: `360` bars partial

## Gap Summary

Expected recurring gaps include the daily CME maintenance break, weekend closures, Good Friday 2026, and the Juneteenth 2026 early close configured in the recent download validation note.

Configured closures:

- Good Friday 2026: `2026-04-03T09:15:00-04:00` through `2026-04-05T18:00:00-04:00`
- Juneteenth 2026 early close: `2026-06-19T13:00:00-04:00` through `2026-06-21T18:00:00-04:00`

### mgc_1m_databento_20230101_20260703.csv

- Non-1-minute gap count: `11747`.
- Most common gap lengths:

  - `2` minutes: `7638` occurrences
  - `3` minutes: `1409` occurrences
  - `61` minutes: `674` occurrences
  - `4` minutes: `556` occurrences
  - `5` minutes: `321` occurrences
  - `6` minutes: `178` occurrences
  - `2941` minutes: `159` occurrences
  - `7` minutes: `125` occurrences

- Sample gaps:

  - `2023-01-03T16:03:00-05:00` to `2023-01-03T16:05:00-05:00`: `2` minutes
  - `2023-01-03T16:13:00-05:00` to `2023-01-03T16:15:00-05:00`: `2` minutes
  - `2023-01-03T16:59:00-05:00` to `2023-01-03T18:00:00-05:00`: `61` minutes
  - `2023-01-03T18:28:00-05:00` to `2023-01-03T18:30:00-05:00`: `2` minutes
  - `2023-01-03T18:33:00-05:00` to `2023-01-03T18:35:00-05:00`: `2` minutes
  - `2023-01-03T18:47:00-05:00` to `2023-01-03T18:49:00-05:00`: `2` minutes
  - `2023-01-03T19:06:00-05:00` to `2023-01-03T19:08:00-05:00`: `2` minutes
  - `2023-01-03T23:10:00-05:00` to `2023-01-03T23:12:00-05:00`: `2` minutes
  - `2023-01-03T23:31:00-05:00` to `2023-01-03T23:34:00-05:00`: `3` minutes
  - `2023-01-04T00:14:00-05:00` to `2023-01-04T00:16:00-05:00`: `2` minutes

### mnq_1m_databento_20230101_20260703.csv

- Non-1-minute gap count: `912`.
- Most common gap lengths:

  - `61` minutes: `691` occurrences
  - `2941` minutes: `164` occurrences
  - `301` minutes: `23` occurrences
  - `2` minutes: `6` occurrences
  - `2881` minutes: `4` occurrences
  - `4381` minutes: `4` occurrences
  - `286` minutes: `3` occurrences
  - `3001` minutes: `3` occurrences

- Sample gaps:

  - `2023-01-03T16:59:00-05:00` to `2023-01-03T18:00:00-05:00`: `61` minutes
  - `2023-01-04T16:59:00-05:00` to `2023-01-04T18:00:00-05:00`: `61` minutes
  - `2023-01-05T16:59:00-05:00` to `2023-01-05T18:00:00-05:00`: `61` minutes
  - `2023-01-06T16:59:00-05:00` to `2023-01-08T18:00:00-05:00`: `2941` minutes
  - `2023-01-09T16:59:00-05:00` to `2023-01-09T18:00:00-05:00`: `61` minutes
  - `2023-01-10T16:59:00-05:00` to `2023-01-10T18:00:00-05:00`: `61` minutes
  - `2023-01-11T16:59:00-05:00` to `2023-01-11T18:00:00-05:00`: `61` minutes
  - `2023-01-12T16:59:00-05:00` to `2023-01-12T18:00:00-05:00`: `61` minutes
  - `2023-01-13T16:59:00-05:00` to `2023-01-15T18:00:00-05:00`: `2941` minutes
  - `2023-01-16T12:59:00-05:00` to `2023-01-16T18:00:00-05:00`: `301` minutes

## Limitations And Uncertainties

- This audit verifies structure and obvious data quality issues; it does not validate a trading edge.
- `2026-07-03` contains only overnight bars through `00:00 ET` download cutoff mechanics and is excluded from complete-session analysis.
- Continuous futures are suitable for tactical research, but rollover effects should still be monitored in later backtests.
- No news calendar, prop-firm rule model, fees, commissions, or slippage model is applied in this first phase.

## Readiness

The recent MNQ and MGC files are good enough to start deterministic edge discovery after this audit phase. The next phase should begin with simple, manually tradable intraday families and rank candidates by recent expectancy, trade frequency, risk, and sensitivity to worse slippage.
