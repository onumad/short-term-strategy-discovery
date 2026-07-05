# Phase 5B Deterministic Feature/Regime Engine Report

Date generated: 2026-07-05 01:57:15 EDT

## Scope And Guardrails

- Research/simulation only; no live trading, broker adapters, order routing, webhooks, or automated execution were added.
- The script loads existing local CSV files under `data/raw` only and does not download data.
- Outputs are deterministic feature datasets for offline research and search, not live signals.
- Focus order is MNQ first, then MGC; both symbols are exported with the same stable schema.

## Outputs

- Feature dataset: `C:\Users\ulzii\Documents\Short Term Strategy Discovery\outputs\phase5b_features.parquet`
- Feature summary: `C:\Users\ulzii\Documents\Short Term Strategy Discovery\outputs\phase5b_feature_summary.csv`
- Report: `C:\Users\ulzii\Documents\Short Term Strategy Discovery\reports\phase5b_feature_report.md`

## Stable Feature Schema

- Columns: `40`
- Key feature groups: prior-session range/return, overnight range, gap, opening-range width, realized volatility, trend/slope, volume regime, calendar features, and RTH cumulative summaries.
- Offline labels are isolated under `label_*`; non-label columns are intended to be available at or before the bar close.

## Symbol Summary

| Symbol | Rows | Sessions | First Timestamp | Last Timestamp | OR Width Rows | Overnight Rows |
| --- | ---: | ---: | --- | --- | ---: | ---: |
| MNQ | 345960 | 902 | 2023-01-03 09:30:00-05:00 | 2026-07-02 15:59:00-04:00 | 318900 | 345960 |
| MGC | 342237 | 903 | 2023-01-03 09:30:00-05:00 | 2026-07-02 15:59:00-04:00 | 315224 | 342237 |

## No-Lookahead Notes

- Prior-session high/low/close/range/return are shifted by completed trading session.
- Overnight high/low/range use ETH bars before that session's RTH open and are available at 09:30 ET.
- Current RTH high/low/range and volume are cumulative through the current row only.
- Opening-range high/low/width remain null until the 30-minute window has completed.
- Forward returns are label columns only and are excluded from strategy-spec search inputs by convention.

## Repro Command

```bash
./.venv/Scripts/python.exe scripts/run_phase5b_features.py
```
