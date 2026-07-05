# Data Audit

Date generated: 2026-07-05

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
| `mgc_1m_databento_20260403_20260703.csv` | MGC | 87,665 | `2026-04-05T18:00:00-04:00` | `2026-07-02T23:59:00-04:00` | 63 | `2026-07-02` |
| `mnq_1m_databento_20260403_20260703.csv` | MNQ | 88,755 | `2026-04-03T00:00:00-04:00` | `2026-07-02T23:59:00-04:00` | 64 | `2026-07-02` |

## Integrity Checks

| File | Sorted | Duplicate Timestamp-Symbol Rows | Bad OHLC Rows | Zero Volume Rows | Negative Volume Rows | Price Range |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| `mgc_1m_databento_20260403_20260703.csv` | true | 0 | 0 | 0 | 0 | 3,955.30 to 4,914.00 |
| `mnq_1m_databento_20260403_20260703.csv` | true | 0 | 0 | 0 | 0 | 23,941.50 to 30,967.75 |

## Session Coverage

A complete session is currently defined as at least `1,000` one-minute bars. This threshold keeps normal Globex sessions while excluding known partial download edges and holiday fragments.

### MGC

- Sessions observed: `65`.
- Complete sessions: `63`.
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

- Sessions observed: `66`.
- Complete sessions: `64`.
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

### mgc_1m_databento_20260403_20260703.csv

- Non-1-minute gap count: `286`.
- Most common gap lengths:

  - `2` minutes: `120` occurrences
  - `61` minutes: `50` occurrences
  - `3` minutes: `49` occurrences
  - `4` minutes: `15` occurrences
  - `5` minutes: `12` occurrences
  - `2941` minutes: `11` occurrences
  - `6` minutes: `7` occurrences
  - `7` minutes: `6` occurrences

- Sample gaps:

  - `2026-04-06T16:59:00-04:00` to `2026-04-06T18:00:00-04:00`: `61` minutes
  - `2026-04-07T16:59:00-04:00` to `2026-04-07T18:00:00-04:00`: `61` minutes
  - `2026-04-08T16:59:00-04:00` to `2026-04-08T18:00:00-04:00`: `61` minutes
  - `2026-04-09T16:59:00-04:00` to `2026-04-09T18:00:00-04:00`: `61` minutes
  - `2026-04-10T16:59:00-04:00` to `2026-04-12T18:00:00-04:00`: `2941` minutes
  - `2026-04-13T16:59:00-04:00` to `2026-04-13T18:00:00-04:00`: `61` minutes
  - `2026-04-14T16:59:00-04:00` to `2026-04-14T18:00:00-04:00`: `61` minutes
  - `2026-04-15T16:59:00-04:00` to `2026-04-15T18:00:00-04:00`: `61` minutes
  - `2026-04-16T16:59:00-04:00` to `2026-04-16T18:00:00-04:00`: `61` minutes
  - `2026-04-17T16:59:00-04:00` to `2026-04-19T18:00:00-04:00`: `2941` minutes

### mnq_1m_databento_20260403_20260703.csv

- Non-1-minute gap count: `65`.
- Most common gap lengths:

  - `61` minutes: `51` occurrences
  - `2941` minutes: `11` occurrences
  - `3406` minutes: `1` occurrences
  - `301` minutes: `1` occurrences
  - `3181` minutes: `1` occurrences

- Sample gaps:

  - `2026-04-03T09:14:00-04:00` to `2026-04-05T18:00:00-04:00`: `3406` minutes
  - `2026-04-06T16:59:00-04:00` to `2026-04-06T18:00:00-04:00`: `61` minutes
  - `2026-04-07T16:59:00-04:00` to `2026-04-07T18:00:00-04:00`: `61` minutes
  - `2026-04-08T16:59:00-04:00` to `2026-04-08T18:00:00-04:00`: `61` minutes
  - `2026-04-09T16:59:00-04:00` to `2026-04-09T18:00:00-04:00`: `61` minutes
  - `2026-04-10T16:59:00-04:00` to `2026-04-12T18:00:00-04:00`: `2941` minutes
  - `2026-04-13T16:59:00-04:00` to `2026-04-13T18:00:00-04:00`: `61` minutes
  - `2026-04-14T16:59:00-04:00` to `2026-04-14T18:00:00-04:00`: `61` minutes
  - `2026-04-15T16:59:00-04:00` to `2026-04-15T18:00:00-04:00`: `61` minutes
  - `2026-04-16T16:59:00-04:00` to `2026-04-16T18:00:00-04:00`: `61` minutes

## Limitations And Uncertainties

- This audit verifies structure and obvious data quality issues; it does not validate a trading edge.
- `2026-07-03` contains only overnight bars through `00:00 ET` download cutoff mechanics and is excluded from complete-session analysis.
- Continuous futures are suitable for tactical research, but rollover effects should still be monitored in later backtests.
- No news calendar, prop-firm rule model, fees, commissions, or slippage model is applied in this first phase.

## Readiness

The recent MNQ and MGC files are good enough to start deterministic edge discovery after this audit phase. The next phase should begin with simple, manually tradable intraday families and rank candidates by recent expectancy, trade frequency, risk, and sensitivity to worse slippage.
