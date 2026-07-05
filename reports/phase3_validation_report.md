# Phase 3 Validation Report

Date generated: 2026-07-03

## Main Findings

- Primary candidate: `MNQ_opening_range_failure_or30_fail_opposite`.
- Research window: `2026-04-06` through `2026-07-02` (63 complete shared sessions).
- Phase 3 reruns frozen Phase 2 candidates only; neighbor checks are robustness context, not new parameter selection.
- Highest allowed label remains `paper_trade_candidate`; this report does not approve live trading.
- Primary net PnL: `$6696.49`; holdout PnL: `$2378.17`; stress 4 ticks/side PnL: `$6378.49`.
- Primary activity: `106` trades, `1.68` trades/session, active on `88.9%` of sessions.
- Phase 3 label: `paper_trade_candidate`.

## Candidate Comparison

| Candidate | Label | Net PnL | Holdout | 4-Tick Slip | Trades | Active % | Long PnL | Short PnL | Max DD | Losing Streak |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `MNQ_opening_range_failure_or30_fail_opposite` | paper_trade_candidate | $6696.49 | $2378.17 | $6378.49 | 106 | 88.9% | $5258.11 | $1438.38 | $-2237.55 | 17 |
| `MNQ_opening_range_failure_or30_fail_mid` | paper_trade_candidate | $2904.36 | $1308.22 | $2586.36 | 106 | 88.9% | $3363.86 | $-459.49 | $-2045.42 | 15 |
| `MNQ_overnight_levels_sweep_reverse_60x90` | watchlist | $2819.64 | $119.09 | $2627.64 | 64 | 55.6% | $2259.29 | $560.35 | $-414.44 | 7 |
| `MNQ_overnight_levels_sweep_reverse_40x60` | watchlist | $2394.64 | $199.09 | $2202.64 | 64 | 55.6% | $1554.29 | $840.35 | $-490.82 | 11 |
| `MNQ_opening_range_failure_or15_fail_opposite` | paper_trade_candidate | $1852.45 | $984.82 | $1492.45 | 120 | 95.2% | $3715.70 | $-1863.25 | $-1205.22 | 8 |
| `MGC_opening_range_failure_or15_fail_opposite` | paper_trade_candidate | $1849.51 | $97.42 | $1117.51 | 122 | 98.4% | $622.53 | $1226.98 | $-1516.70 | 20 |
| `MGC_opening_range_failure_or30_fail_opposite` | paper_trade_candidate | $1664.17 | $1603.21 | $980.17 | 114 | 93.7% | $-1362.07 | $3026.24 | $-2290.61 | 15 |
| `MNQ_opening_range_failure_or15_fail_mid` | paper_trade_candidate | $1402.00 | $984.14 | $1042.00 | 120 | 95.2% | $1975.43 | $-573.42 | $-868.72 | 8 |
| `MNQ_opening_range_failure_or5_fail_opposite` | paper_trade_candidate | $1038.10 | $237.89 | $693.10 | 115 | 92.1% | $406.47 | $631.63 | $-1047.51 | 9 |
| `MNQ_vwap_reclaim_rejection_reclaim_80x120` | paper_trade_candidate | $720.60 | $210.82 | $240.60 | 160 | 96.8% | $720.60 | $0.00 | $-541.24 | 10 |

## Risk Diagnostics

- Side balance: `mostly long`. Long PnL `$5258.11` over `43` trades; short PnL `$1438.38` over `63` trades.
- PnL concentration: best day is `21.8%` of net PnL; best trade is `11.0%` of net PnL.
- Longest losing streak: `17` trades.
- MAE/MFE medians: `$-114.00` MAE and `$156.25` MFE.
- Same-bar stop/target ambiguity flags: `0` trades; those remain conservative because the simulator assumes stop first.
- Main observed failure mode: trend-day proxy losses (97% of losing trades flagged).

## Prop-Style Risk Overlay

- Account proxy: generic 50K research model, 1-2 MNQ contracts, $2,000 daily loss stop, $2,500 drawdown proxy.

| Overlay | Contracts | Net PnL | Max DD | Worst Day | Worst Rolling 5 Days | Drawdown Breach | Trades |
| --- | ---: | ---: | ---: | ---: | ---: | --- | ---: |
| baseline | 1 | $6696.49 | $-2237.55 | $-580.88 | $-1463.82 | false | 106 |
| baseline | 2 | $13392.97 | $-4475.10 | $-1161.76 | $-2927.64 | true | 106 |
| skip_first_trade_each_day | 1 | $3272.30 | $-899.89 | $-259.92 | $-507.50 | false | 50 |
| skip_first_trade_each_day | 2 | $6544.60 | $-1799.77 | $-519.83 | $-1015.00 | false | 50 |
| max_1_trade_per_day | 1 | $3424.19 | $-1384.33 | $-339.99 | $-979.92 | false | 56 |
| max_1_trade_per_day | 2 | $6848.37 | $-2768.66 | $-679.98 | $-1959.85 | true | 56 |
| max_2_trades_per_day | 1 | $6696.49 | $-2237.55 | $-580.88 | $-1463.82 | false | 106 |
| max_2_trades_per_day | 2 | $13392.97 | $-4475.10 | $-1161.76 | $-2927.64 | true | 106 |
| stop_after_first_winner | 1 | $-548.63 | $-3465.35 | $-580.88 | $-1463.82 | true | 84 |
| stop_after_first_winner | 2 | $-1097.27 | $-6930.70 | $-1161.76 | $-2927.64 | true | 84 |
| stop_after_first_loser | 1 | $10669.31 | $-995.78 | $-339.99 | $-979.92 | false | 78 |
| stop_after_first_loser | 2 | $21338.61 | $-1991.57 | $-679.98 | $-1959.85 | false | 78 |
| max_1_losing_trade_per_day | 1 | $10669.31 | $-995.78 | $-339.99 | $-979.92 | false | 78 |
| max_1_losing_trade_per_day | 2 | $21338.61 | $-1991.57 | $-679.98 | $-1959.85 | false | 78 |
| max_2_losing_trades_per_day | 1 | $6696.49 | $-2237.55 | $-580.88 | $-1463.82 | false | 106 |
| max_2_losing_trades_per_day | 2 | $13392.97 | $-4475.10 | $-1161.76 | $-2927.64 | true | 106 |
| daily_loss_stop_2000 | 1 | $6696.49 | $-2237.55 | $-580.88 | $-1463.82 | false | 106 |
| daily_loss_stop_2000 | 2 | $13392.97 | $-4475.10 | $-1161.76 | $-2927.64 | true | 106 |

## Manual Feasibility

- The setup is manually observable: mark the 09:30-10:00 ET range, wait for a breakout beyond range high/low, then require a 1-minute close back inside the range.
- Entry timing remains conservative and executable on paper: enter at the next 1-minute bar open after the failure close.
- Baseline is max 2 trades/day, 1 MNQ contract, hard flatten by 15:55 ET.
- Skipping the first trade each day changes primary net PnL to `$3272.30`; max 1 trade/day changes it to `$3424.19`.

## Neighbor Robustness

| Neighbor | Net PnL | Holdout | 4-Tick Slip | Trades | Active % |
| --- | ---: | ---: | ---: | ---: | ---: |
| `MNQ_opening_range_failure_or25_fail_opposite_max2_min8` | $9310.66 | $3938.23 | $8983.66 | 109 | 93.7% |
| `MNQ_opening_range_failure_or25_fail_opposite_max2_min10` | $9310.66 | $3938.23 | $8983.66 | 109 | 93.7% |
| `MNQ_opening_range_failure_or25_fail_opposite_max2_min12` | $9310.66 | $3938.23 | $8983.66 | 109 | 93.7% |
| `MNQ_opening_range_failure_or20_fail_opposite_max2_min8` | $7861.70 | $4597.22 | $7510.70 | 117 | 96.8% |
| `MNQ_opening_range_failure_or20_fail_opposite_max2_min10` | $7861.70 | $4597.22 | $7510.70 | 117 | 96.8% |
| `MNQ_opening_range_failure_or20_fail_opposite_max2_min12` | $7861.70 | $4597.22 | $7510.70 | 117 | 96.8% |
| `MNQ_opening_range_failure_or35_fail_opposite_max2_min8` | $6881.49 | $3884.40 | $6578.49 | 101 | 84.1% |
| `MNQ_opening_range_failure_or35_fail_opposite_max2_min10` | $6881.49 | $3884.40 | $6578.49 | 101 | 84.1% |
| `MNQ_opening_range_failure_or35_fail_opposite_max2_min12` | $6881.49 | $3884.40 | $6578.49 | 101 | 84.1% |
| `MNQ_opening_range_failure_or30_fail_opposite_max2_min8` | $6696.49 | $2378.17 | $6378.49 | 106 | 88.9% |
| `MNQ_opening_range_failure_or30_fail_opposite_max2_min10` | $6696.49 | $2378.17 | $6378.49 | 106 | 88.9% |
| `MNQ_opening_range_failure_or30_fail_opposite_max2_min12` | $6696.49 | $2378.17 | $6378.49 | 106 | 88.9% |

## Final Decision Answers

1. `MNQ_opening_range_failure_or30_fail_opposite` remains the best offensive candidate among the frozen Phase 3 set by net PnL.
2. `MNQ_opening_range_failure_or30_fail_mid` is safer/easier only in target distance and win rate terms; it produces lower net PnL (`$2904.36`) with similar drawdown (`$-2045.42`).
3. The edge is `mostly long`.
4. Strict slippage survival through 4 ticks/side: `true`.
5. Max 1 trade/day hurts net PnL in this sample.
6. Market condition that most clearly hurts it: trend-day proxy losses (97% of losing trades flagged).
7. Phase 3 label: `paper_trade_candidate`.
8. For a 20-session paper test, follow the separate manual plan exactly and do not alter parameters during the test.
9. Use a practical daily stop of one full initial-risk loss or $500 for 1 MNQ, whichever comes first; stop for the day after 2 losing trades.
10. Before trusting results, manually review the flagged same-bar ambiguity trades, high-volatility opening ranges, large gap days, and any data-gap proximity flags.

## Reproducibility

```powershell
python scripts/run_phase3_validation.py
```

Outputs:

- Candidate diagnostics: `C:\Users\ulzii\Documents\Short Term Strategy Discovery\outputs\phase3_candidate_diagnostics.csv`
- Daily PnL: `C:\Users\ulzii\Documents\Short Term Strategy Discovery\outputs\phase3_daily_pnl.csv`
- Main trade review: `C:\Users\ulzii\Documents\Short Term Strategy Discovery\outputs\phase3_trade_review.csv`
- Manual plan: `C:\Users\ulzii\Documents\Short Term Strategy Discovery\reports\phase3_manual_paper_trading_plan.md`
- Charts: `C:\Users\ulzii\Documents\Short Term Strategy Discovery\charts\phase3_primary_equity.png` and other `phase3_*.png` files
