# Databento Data Handoff Report

Date: 2026-07-03

Project: Short Term Strategy Discovery

## Executive Summary

The project currently contains only the recent Databento 1-minute continuous futures downloads for MGC and MNQ.

Data directory:

```text
C:\Users\ulzii\Documents\Short Term Strategy Discovery\data\raw
```

Previously copied 2023-2025 full-history files and the MES smoke fixture were removed from this project. No MES data is currently present in `data\raw`.

This is research data only. It does not approve paper trading, live trading, broker adapters, API-key storage, automated execution, or LLM trade decisions.

## Data Source And Format

- Vendor: Databento
- Dataset: `GLBX.MDP3`
- Schema: `ohlcv-1m`
- Symbology: Databento continuous futures
- Continuous symbols: `MGC.v.0`, `MNQ.v.0`
- Roll convention: `v.0` volume-ranked front month
- Price policy: original, unadjusted prices
- Time zone: `America/New_York`
- CSV schema:

```text
timestamp,symbol,open,high,low,close,volume
```

Continuous futures prices are not back-adjusted. Rollover gaps remain in the data and should not be optimized away.

## Current Files

| File | Symbol | Rows | First timestamp | Last timestamp | SHA-256 |
| --- | --- | ---: | --- | --- | --- |
| `mgc_1m_databento_20260403_20260703.csv` | MGC | 87,665 | `2026-04-05T18:00:00-04:00` | `2026-07-02T23:59:00-04:00` | `399A4C668A1C7EC6ECD5DFCEBFC9E76B6AB9C10677828BB790E90F9BFE777C56` |
| `mnq_1m_databento_20260403_20260703.csv` | MNQ | 88,755 | `2026-04-03T00:00:00-04:00` | `2026-07-02T23:59:00-04:00` | `8D64FA44048EBAB287236B99CD08706C1A02259694D8D194BEFB3221548758C0` |

Requested Databento window:

```text
start = 2026-04-03T00:00:00-04:00
end   = 2026-07-03T00:00:00-04:00
```

The `end` timestamp is exclusive.

## Removed Files

These previously copied files were removed from the new project:

- `mes_1m_databento.csv`
- `mes_1m_databento_smoke.csv`
- `mgc_1m_databento.csv`
- `mnq_1m_databento.csv`

## Validation Status

Focused offline OHLCV audit passed for both current files after configuring expected CME closures:

- Good Friday 2026: `2026-04-03T09:15:00` through `2026-04-05T18:00:00`
- Juneteenth 2026 early close: `2026-06-19T13:00:00` through `2026-06-21T18:00:00`

Audit result:

| Symbol | Passed | Issue count | Unexplained gaps | Gap classifications |
| --- | --- | ---: | ---: | --- |
| MGC | true | 0 | 0 | `configured_closure=1`, `expected_weekend_closure=11` |
| MNQ | true | 0 | 0 | `configured_closure=2`, `expected_weekend_closure=11` |

## Research Guardrails For A New Chat

Use these datasets for deterministic research, backtesting, and paper-trading preparation only.

Before treating any strategy result as meaningful:

- Split development and holdout periods explicitly.
- Avoid lookahead, repainting indicators, future-bar leakage, and same-bar fills unless the engine can prove order of events.
- Include realistic fees, slippage, tick size, point value, and contract metadata.
- Model exchange sessions, maintenance breaks, holidays, early closes, flatten deadlines, and prop-firm rules.
- Record exact config paths, commands, data hashes, parameters, and report outputs.
- Do not use an LLM to make live entries, exits, sizing, or execution decisions.

## Suggested Opening Prompt For A New Chat

```text
We are working in C:\Users\ulzii\Documents\Short Term Strategy Discovery.

The project currently has recent Databento 1-minute continuous futures CSVs under data/raw:
- MGC: mgc_1m_databento_20260403_20260703.csv
- MNQ: mnq_1m_databento_20260403_20260703.csv

The files use timestamp,symbol,open,high,low,close,volume and cover an exclusive requested window from 2026-04-03T00:00:00-04:00 through 2026-07-03T00:00:00-04:00. The latest included bars are 2026-07-02T23:59:00-04:00. Focused OHLCV audit passed with 0 issues and 0 unexplained gaps after configuring expected Good Friday 2026 and Juneteenth 2026 CME closures.

Treat this as deterministic futures research data only. No live trading, broker adapters, API-key files, automated order routing, or LLM trade decisions are approved.
```
