# Phase 5C Robust Deterministic Search Report

Date generated: 2026-07-05 02:00:37 EDT

## Scope And Guardrails

- Research/simulation only. No live trading, broker adapters, API-key storage, webhooks, order routing, or automated execution were added.
- The search emits serializable deterministic strategy specs only; it does not emit live signals.
- Source data is local only under `data/raw`; no additional data was downloaded.
- Optuna was intentionally not added: the bounded deterministic seeded search is sufficient for this milestone and avoids a new dependency.
- Focus order is MNQ first, then MGC; candidate selection preserves that order before final score ranking.

## Bounded Run Configuration

- Symbols: `MNQ, MGC`
- Candidates per symbol: `32`
- Seed: `505`
- Recent complete shared sessions: `120`
- Actual session window: `2026-04-06` through `2026-07-02` (`63` sessions)
- Robust score penalties: drawdown, low activity, concentration, complexity, weak holdout, and 4-tick slippage stress failure.

## Outputs

- Search results: `C:\Users\ulzii\Documents\Short Term Strategy Discovery\outputs\phase5c_search_results.csv`
- Candidate specs: `C:\Users\ulzii\Documents\Short Term Strategy Discovery\outputs\phase5c_candidate_specs.json`
- Report: `C:\Users\ulzii\Documents\Short Term Strategy Discovery\reports\phase5c_search_report.md`

## Top Robust Scores

| Rank | Candidate | Symbol | Family | TF | Label | Score | Net | Holdout | 4-Tick Slip | Trades | Penalty Notes |
| ---: | --- | --- | --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | --- |
| 1 | `MNQ_opening_range_failure_tf1_982fe6172f` | MNQ | opening_range_failure | 1m | robust_research_candidate | 76.15 | $4771.90 | $2169.53 | $4540.90 | 77 | drawdown; complexity |
| 2 | `MNQ_opening_range_failure_tf3_1dce415f36` | MNQ | opening_range_failure | 3m | robust_research_candidate | 74.59 | $4275.42 | $2773.78 | $4038.42 | 79 | drawdown; complexity |
| 3 | `MNQ_opening_range_failure_tf1_edf563d7d8` | MNQ | opening_range_failure | 1m | watchlist | 67.19 | $3424.19 | $1147.33 | $3256.19 | 56 | drawdown; concentration; complexity |
| 4 | `MNQ_opening_range_failure_tf1_41b10f5cee` | MNQ | opening_range_failure | 1m | watchlist | 49.67 | $1537.86 | $612.36 | $1369.86 | 56 | drawdown; concentration; complexity |
| 5 | `MNQ_opening_range_failure_tf1_812c066564` | MNQ | opening_range_failure | 1m | watchlist | 49.51 | $1486.62 | $1085.07 | $1240.62 | 82 | drawdown; concentration; complexity |
| 6 | `MGC_opening_range_failure_tf1_9454d5e6d4` | MGC | opening_range_failure | 1m | robust_research_candidate | 47.55 | $1958.85 | $919.71 | $1718.85 | 40 | drawdown; complexity |
| 7 | `MGC_opening_range_failure_tf5_ab026e105a` | MGC | opening_range_failure | 5m | watchlist | 46.96 | $1564.53 | $654.96 | $958.53 | 101 | drawdown; concentration; complexity |
| 8 | `MGC_opening_range_failure_tf1_8cc53a3ab4` | MGC | opening_range_failure | 1m | watchlist | 38.79 | $1269.92 | $1006.53 | $945.92 | 54 | drawdown; concentration; complexity |
| 9 | `MNQ_opening_range_failure_tf5_abd89ecc94` | MNQ | opening_range_failure | 5m | watchlist | 36.14 | $950.29 | $642.41 | $788.29 | 54 | drawdown; concentration; complexity |
| 10 | `MNQ_opening_range_failure_tf1_454ba8d5ae` | MNQ | opening_range_failure | 1m | watchlist | 35.82 | $950.60 | $321.13 | $770.60 | 60 | drawdown; concentration; complexity |
| 11 | `MNQ_opening_range_failure_tf1_61f4235e9e` | MNQ | opening_range_failure | 1m | watchlist | 35.19 | $900.56 | $764.51 | $582.56 | 106 | drawdown; concentration; complexity |
| 12 | `MNQ_opening_range_failure_tf3_8fc1ffc34b` | MNQ | opening_range_failure | 3m | watchlist | 34.94 | $821.16 | $451.80 | $647.16 | 58 | drawdown; concentration; complexity |
| 13 | `MNQ_opening_range_failure_tf3_d685706c9d` | MNQ | opening_range_failure | 3m | watchlist | 33.88 | $915.40 | $657.86 | $750.40 | 55 | drawdown; concentration; complexity |
| 14 | `MGC_opening_range_failure_tf1_99b17f96d6` | MGC | opening_range_failure | 1m | watchlist | 30.97 | $1507.12 | $910.13 | $1153.12 | 59 | drawdown; concentration; complexity |
| 15 | `MNQ_opening_range_failure_tf3_8169a41881` | MNQ | opening_range_failure | 3m | watchlist | 29.52 | $991.58 | $1539.57 | $742.58 | 83 | drawdown; concentration; complexity |

## Readout

- Label counts: `{'rejected': 26, 'watchlist_needs_validation': 22, 'watchlist': 13, 'robust_research_candidate': 3}`
- Label counts by symbol: `{('MGC', 'rejected'): 17, ('MGC', 'watchlist_needs_validation'): 10, ('MGC', 'watchlist'): 4, ('MGC', 'robust_research_candidate'): 1, ('MNQ', 'watchlist_needs_validation'): 12, ('MNQ', 'watchlist'): 9, ('MNQ', 'rejected'): 9, ('MNQ', 'robust_research_candidate'): 2}`

## Repro Command

```bash
./.venv/Scripts/python.exe scripts/run_phase5c_search.py
```
