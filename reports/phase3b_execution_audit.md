# Phase 3B Execution Audit

Date generated: 2026-07-03

## Summary

- Candidate audited: `MNQ_opening_range_failure_or30_fail_opposite`.
- Baseline active sessions: `56`.
- Sessions with 1 trade: `6`.
- Sessions with 2 trades: `50`.
- Overlapping trade pairs: `45`.
- Same-side overlap pairs: `45`.
- Same-exit overlap pairs: `45`.
- Likely duplicate/pyramided entries: `45`.
- Max simultaneous exposure in the reported 1 MNQ baseline: `2` MNQ.
- Baseline net PnL: `$6696.49`.
- One-open-position net PnL: `$2573.59`.

## Execution Mode Results

| Mode | Label | Net PnL | Holdout | 4-Tick Slip | Trades | Active % | Win Rate | Avg | PF | Max DD | Worst 5-Day | Max Exposure |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| A_baseline | watchlist | $6696.49 | $2378.17 | $6378.49 | 106 | 88.9% | 42.5% | $63.17 | 1.74 | $-2237.55 | $-1463.82 | 2 |
| B_one_open_position | paper_trade_candidate | $2573.59 | $911.34 | $2390.59 | 61 | 88.9% | 39.3% | $42.19 | 1.44 | $-1618.98 | $-1127.24 | 1 |
| C_max_1_trade_per_day | paper_trade_candidate | $3424.19 | $1147.33 | $3256.19 | 56 | 88.9% | 42.9% | $61.15 | 1.69 | $-1384.33 | $-979.92 | 1 |
| D_stop_after_first_loser | paper_trade_candidate | $3246.85 | $1147.33 | $3075.85 | 57 | 88.9% | 42.1% | $56.96 | 1.63 | $-1384.33 | $-979.92 | 1 |
| E_first_failure_per_side | paper_trade_candidate | $3246.85 | $1147.33 | $3075.85 | 57 | 88.9% | 42.1% | $56.96 | 1.63 | $-1384.33 | $-979.92 | 1 |
| F_cooldown_10_min | paper_trade_candidate | $2750.93 | $911.34 | $2570.93 | 60 | 88.9% | 40.0% | $45.85 | 1.49 | $-1618.98 | $-1127.24 | 1 |

## Overlap Impact

- Unique overlapping-trade PnL in baseline: `$8095.80`.
- Baseline PnL if each overlap cluster keeps only its first entry: `$2573.59`.
- Switching from baseline to one-open-position changes PnL by `$-4122.90` and max drawdown by `$618.56`.
- The baseline does not represent strict 1-contract manual exposure on days where entries overlap.

## Final Decision Answers

1. Did Phase 3 baseline allow overlapping positions? `true`.
2. Overlap impact: baseline net `$6696.49` versus no-overlap net `$2573.59`; baseline max DD `$-2237.55` versus no-overlap max DD `$-1618.98`.
3. Most realistic manual mode: `D_stop_after_first_loser` (One open position only, stop for day after first loser).
4. Candidate remains `paper_trade_candidate` without overlapping positions: `true`.
5. Recommendation: start a small 1 MNQ paper test using the updated no-overlap rules.
6. Replace the previous plan with the updated Phase 3B paper-trading plan: no pyramiding, second trade only after the first exits, stop after one full stop-loss or $500 realized daily loss, max 2 completed trades/day.

## Reproducibility

```powershell
python scripts/run_phase3b_execution_audit.py
```

Outputs:

- Execution modes: `C:\Users\ulzii\Documents\Short Term Strategy Discovery\outputs\phase3b_execution_modes.csv`
- Overlap audit: `C:\Users\ulzii\Documents\Short Term Strategy Discovery\outputs\phase3b_overlap_audit.csv`
- Updated plan: `C:\Users\ulzii\Documents\Short Term Strategy Discovery\reports\phase3b_updated_paper_trading_plan.md`
- Charts: `C:\Users\ulzii\Documents\Short Term Strategy Discovery\charts\phase3b_baseline_vs_no_overlap_equity.png` and other `phase3b_*.png` files
