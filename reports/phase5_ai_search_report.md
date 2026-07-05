# Phase 5A AI Strategy Finder Foundation Report

Date generated: 2026-07-05 01:53:32 EDT

## Scope And Guardrails

- This is a deterministic AI-assisted/search foundation, not an opaque neural-net trader.
- The search proposes serializable rule specs from explicit bounded grids; validation scores them on historical data.
- No live trading, broker adapters, API-key storage, webhooks, order routing, or automated execution were added.
- Source data was local only under `data/raw`; the script does not download more data.
- Strategy results remain research/simulation candidates only and require independent validation before any paper-trading process.

## Bounded Run Configuration

- Symbols: `MNQ, MGC`
- Max candidates: `32`
- Recent complete shared sessions: `120`
- Actual session window: `2026-04-06` through `2026-07-02` (`63` sessions)
- Timeframes: `1m, 3m, 5m`
- Opening range windows: `15m, 30m, 60m`
- Cost model: instrument `base_cost` and `stress_cost` are included in each score row; strict 4-tick slippage is also reported.

## Outputs

- Candidate scores: `C:\Users\ulzii\Documents\Short Term Strategy Discovery\outputs\phase5_ai_candidates.csv`
- Feature summary: `C:\Users\ulzii\Documents\Short Term Strategy Discovery\outputs\phase5_feature_summary.csv`
- Report: `C:\Users\ulzii\Documents\Short Term Strategy Discovery\reports\phase5_ai_search_report.md`

## Feature Foundation

The feature builder creates inspectable no-lookahead columns: session VWAP, EMA/SMA, realized range, shifted prior-session levels, opening-range levels only after the opening window is complete, and offline-only `label_*` forward returns.

| Symbol | Rows | Sessions | First Timestamp | Last Timestamp |
| --- | ---: | ---: | --- | --- |
| MGC | 24299 | 63 | 2026-04-06 09:30:00-04:00 | 2026-07-02 15:59:00-04:00 |
| MNQ | 24210 | 63 | 2026-04-06 09:30:00-04:00 | 2026-07-02 15:59:00-04:00 |

## Top Candidate Scores

| Rank | Candidate | Family | TF | Label | Score | Net | Holdout | 4-Tick Slip | Trades | Active % | Risk Notes |
| ---: | --- | --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 1 | `MNQ_opening_range_failure_tf1_982fe6172f` | opening_range_failure | 1m | paper_research_candidate | 84.04 | $4771.90 | $2169.53 | $4540.90 | 77 | 88.9% | No major Phase 5A risk flags. |
| 2 | `MNQ_opening_range_failure_tf1_edf563d7d8` | opening_range_failure | 1m | paper_research_candidate | 76.61 | $3424.19 | $1147.33 | $3256.19 | 56 | 88.9% | No major Phase 5A risk flags. |
| 3 | `MNQ_opening_range_failure_tf3_d343e86b15` | opening_range_failure | 3m | watchlist | 64.54 | $2127.46 | $911.54 | $1839.46 | 96 | 92.1% | one-trade concentration risk |
| 4 | `MNQ_opening_range_failure_tf1_812c066564` | opening_range_failure | 1m | watchlist | 60.17 | $1486.62 | $1085.07 | $1240.62 | 82 | 88.9% | one-day concentration risk |
| 5 | `MNQ_opening_range_failure_tf1_41b10f5cee` | opening_range_failure | 1m | paper_research_candidate | 58.39 | $1537.86 | $612.36 | $1369.86 | 56 | 88.9% | No major Phase 5A risk flags. |
| 6 | `MNQ_opening_range_breakout_tf1_a3cbc18936` | opening_range_breakout | 1m | watchlist | 58.20 | $2642.98 | $836.08 | $2498.98 | 48 | 76.2% | one-trade concentration risk |
| 7 | `MNQ_opening_range_failure_tf1_61f4235e9e` | opening_range_failure | 1m | watchlist | 43.84 | $900.56 | $764.51 | $582.56 | 106 | 95.2% | negative validation PnL |
| 8 | `MNQ_opening_range_failure_tf3_8fc1ffc34b` | opening_range_failure | 3m | paper_research_candidate | 42.51 | $821.16 | $451.80 | $647.16 | 58 | 92.1% | No major Phase 5A risk flags. |
| 9 | `MNQ_opening_range_failure_tf1_454ba8d5ae` | opening_range_failure | 1m | paper_research_candidate | 41.29 | $950.60 | $321.13 | $770.60 | 60 | 95.2% | No major Phase 5A risk flags. |
| 10 | `MNQ_opening_range_failure_tf3_ab6ebea02e` | opening_range_failure | 3m | watchlist | 40.47 | $848.12 | $725.19 | $536.12 | 104 | 92.1% | negative validation PnL; one-day concentration risk; one-trade concentration risk |
| 11 | `MNQ_opening_range_failure_tf3_e87fec6982` | opening_range_failure | 3m | watchlist | 35.25 | $909.61 | $561.57 | $735.61 | 58 | 92.1% | one-day concentration risk; one-trade concentration risk |
| 12 | `MNQ_opening_range_failure_tf1_20d354e90e` | opening_range_failure | 1m | watchlist | 32.43 | $1278.96 | $438.35 | $990.96 | 96 | 95.2% | negative validation PnL; one-day concentration risk; one-trade concentration risk |

## Initial Readout

- Label counts: `{'watchlist': 14, 'rejected': 12, 'paper_research_candidate': 5, 'interesting_but_needs_validation': 1}`
- Treat all positive results as candidates for further walk-forward / out-of-sample review, not deployable systems.
- Concentration, low coverage, negative holdout, and strict-slippage failures are intentionally conservative risk flags.

## How To Scale Later

- Increase `max_candidates` gradually after reviewing generated specs and runtime.
- Increase `recent_sessions` or remove the cap for a slower full-history validation.
- Add new families only as deterministic, serializable rule templates with unit tests and no-lookahead checks.
- Keep LLM/AI involvement limited to proposing or ranking auditable rule specs; validation must remain deterministic.

## Repro Command

```bash
./.venv/Scripts/python.exe scripts/run_phase5_ai_search.py
```
