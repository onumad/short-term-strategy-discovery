# Phase 4A Multi-Timeframe Discovery Report

Date generated: 2026-07-03

## Summary

- Research window: `2026-04-06` through `2026-07-02` (63 complete shared sessions).
- Planned variants tested: `433`.
- Timeframes generated: `1m, 2m, 3m, 5m, 10m, 15m, 30m, 60m`.
- Timestamp semantics: `bar_start`. Complete RTH sessions contain 390 minute rows from 09:30 through 15:59, matching bar-start labels where the 09:59 bar completes the 09:30-10:00 opening range.
- Phase 4A is exploratory because this 63-session dataset has already influenced prior research direction.
- No live trading, broker connectivity, credentials, webhooks, or order routing were added.

## Tier 1 Infrastructure Validation

- Resampling is anchored to each RTH session at `09:30 ET`, not midnight.
- Source 1-minute timestamps are treated as bar-start labels.
- Higher-timeframe signals become available only at `bar_end` after all source 1-minute bars are complete.
- Entries and exits are simulated on the original 1-minute bars.
- The executor enforces one open position, daily trade limits, and stop-after-first-loser modes.
- Same-bar stop/target ambiguity is counted and resolved stop-first.

## Benchmark

- Benchmark: `MNQ_opening_range_failure_or30_fail_opposite` in `D_stop_after_first_loser` mode.
- Benchmark net PnL `$3246.85`, holdout `$1147.33`, 4-tick slippage `$3075.85`, trades `57`, active sessions `88.9%`, max exposure `1`.

## Variant Counts By Family

| Family | Planned Variants |
| --- | ---: |
| compression_breakout | 18 |
| first_hour_range | 12 |
| moving_average_pullback | 12 |
| opening_range_breakout | 60 |
| opening_range_failure | 240 |
| overnight_levels | 18 |
| prior_session_levels | 24 |
| time_of_day | 20 |
| vwap_pullback_trend | 12 |
| vwap_reclaim_rejection | 17 |

## Broad Exploratory Results

| Family | Variants | Best Net | Best Holdout | Best 4-Tick Slip | Best Score | Paper Candidates |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| opening_range_failure | 240 | $5769.28 | $3160.82 | $5514.28 | 88.97 | 70 |
| compression_breakout | 18 | $3379.10 | $1238.86 | $3199.10 | 84.10 | 2 |
| vwap_pullback_trend | 12 | $2147.16 | $1078.72 | $1949.16 | 81.65 | 1 |
| opening_range_breakout | 60 | $3886.45 | $836.08 | $3751.45 | 80.46 | 8 |
| overnight_levels | 18 | $2509.58 | $286.83 | $2335.58 | 75.77 | 0 |
| first_hour_range | 12 | $3992.08 | $835.58 | $3893.08 | 72.41 | 0 |
| time_of_day | 20 | $489.36 | $1464.62 | $211.55 | 47.61 | 0 |
| vwap_reclaim_rejection | 17 | $571.42 | $98.38 | $370.42 | 43.52 | 2 |
| moving_average_pullback | 12 | $1157.43 | $147.00 | $803.43 | 40.04 | 0 |
| prior_session_levels | 24 | $163.52 | $1216.40 | $-67.48 | -25.44 | 0 |

## Timeframe Summary

| Signal TF | Variants | Best Net | Best Holdout | Best 4-Tick Slip | Best Score | Paper Candidates |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1m | 96 | $5769.28 | $3160.82 | $5514.28 | 88.97 | 31 |
| 3m | 83 | $4578.77 | $3047.32 | $4341.77 | 87.38 | 15 |
| 2m | 54 | $5474.47 | $2958.00 | $5228.47 | 87.14 | 12 |
| 5m | 136 | $4798.23 | $3155.57 | $4558.23 | 87.06 | 18 |
| 15m | 39 | $3992.08 | $1238.86 | $3893.08 | 84.10 | 5 |
| 10m | 25 | $3625.44 | $715.38 | $3493.44 | 73.27 | 2 |

## Tier 3 Focused Top-Family Table

| Candidate | Family | TF | Label | Net | Holdout | 4-Tick Slip | Trades | Active % | Max Exp | Role | Risk Notes |
| --- | --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| `MNQ_opening_range_failure_or20_tf1_mid_stop_after_first_loser` | opening_range_failure | 1m | paper_trade_candidate | $2275.31 | $1856.90 | $2026.31 | 83 | 96.8% | 1 | new_candidate | No major Phase 4A risk flags. |
| `MNQ_opening_range_failure_or30_tf3_opposite_max2` | opening_range_failure | 3m | paper_trade_candidate | $4275.42 | $2773.78 | $4038.42 | 79 | 87.3% | 1 | robustness_confirmation | opening-range-failure robustness confirmation, not independent discovery |
| `MNQ_opening_range_failure_or30_tf2_opposite_max2` | opening_range_failure | 2m | paper_trade_candidate | $4390.12 | $2567.78 | $4153.12 | 79 | 88.9% | 1 | robustness_confirmation | opening-range-failure robustness confirmation, not independent discovery |
| `MNQ_opening_range_failure_or25_tf5_opposite_max2` | opening_range_failure | 5m | paper_trade_candidate | $4798.23 | $2947.42 | $4558.23 | 80 | 87.3% | 1 | robustness_confirmation | opening-range-failure robustness confirmation, not independent discovery |
| `MNQ_opening_range_failure_or20_tf1_mid_max1` | opening_range_failure | 1m | paper_trade_candidate | $2181.86 | $1637.23 | $1998.86 | 61 | 96.8% | 1 | new_candidate | No major Phase 4A risk flags. |
| `MNQ_opening_range_failure_or30_tf1_opposite_max2` | opening_range_failure | 1m | paper_trade_candidate | $4771.90 | $2169.53 | $4540.90 | 77 | 88.9% | 1 | robustness_confirmation | opening-range-failure robustness confirmation, not independent discovery |
| `MNQ_opening_range_failure_or25_tf3_opposite_max2` | opening_range_failure | 3m | paper_trade_candidate | $4578.77 | $2890.06 | $4341.77 | 79 | 85.7% | 1 | robustness_confirmation | opening-range-failure robustness confirmation, not independent discovery |
| `MNQ_opening_range_failure_or30_tf5_opposite_max2` | opening_range_failure | 5m | paper_trade_candidate | $3950.55 | $2458.08 | $3719.55 | 77 | 85.7% | 1 | robustness_confirmation | opening-range-failure robustness confirmation, not independent discovery |
| `MNQ_opening_range_failure_or20_tf1_mid_max2` | opening_range_failure | 1m | paper_trade_candidate | $2312.58 | $2170.67 | $2018.58 | 98 | 96.8% | 1 | new_candidate | No major Phase 4A risk flags. |
| `MNQ_opening_range_failure_or25_tf2_opposite_max2` | opening_range_failure | 2m | paper_trade_candidate | $5474.47 | $2822.08 | $5228.47 | 82 | 87.3% | 1 | robustness_confirmation | opening-range-failure robustness confirmation, not independent discovery |
| `MNQ_opening_range_failure_or25_tf1_opposite_max2` | opening_range_failure | 1m | paper_trade_candidate | $5769.28 | $3122.36 | $5514.28 | 85 | 93.7% | 1 | robustness_confirmation | opening-range-failure robustness confirmation, not independent discovery |
| `MNQ_opening_range_failure_or25_tf1_opposite_stop_after_first_loser` | opening_range_failure | 1m | paper_trade_candidate | $5465.27 | $2783.45 | $5249.27 | 72 | 93.7% | 1 | robustness_confirmation | opening-range-failure robustness confirmation, not independent discovery |
| `MNQ_opening_range_failure_or20_tf2_mid_max1` | opening_range_failure | 2m | paper_trade_candidate | $2039.48 | $1978.86 | $1856.48 | 61 | 96.8% | 1 | new_candidate | No major Phase 4A risk flags. |
| `MNQ_opening_range_failure_or30_tf3_opposite_stop_after_first_loser` | opening_range_failure | 3m | paper_trade_candidate | $3521.22 | $1932.27 | $3320.22 | 67 | 87.3% | 1 | robustness_confirmation | opening-range-failure robustness confirmation, not independent discovery |
| `MNQ_opening_range_failure_or30_tf1_opposite_stop_after_first_loser` | opening_range_failure | 1m | paper_trade_candidate | $4324.18 | $1882.27 | $4120.18 | 68 | 88.9% | 1 | robustness_confirmation | opening-range-failure robustness confirmation, not independent discovery |
| `MNQ_opening_range_failure_or30_tf5_opposite_stop_after_first_loser` | opening_range_failure | 5m | paper_trade_candidate | $3760.11 | $2190.82 | $3562.11 | 66 | 85.7% | 1 | robustness_confirmation | opening-range-failure robustness confirmation, not independent discovery |
| `MNQ_opening_range_failure_or30_tf2_opposite_stop_after_first_loser` | opening_range_failure | 2m | paper_trade_candidate | $3757.68 | $1737.77 | $3553.68 | 68 | 88.9% | 1 | robustness_confirmation | opening-range-failure robustness confirmation, not independent discovery |
| `MNQ_opening_range_failure_or25_tf2_opposite_stop_after_first_loser` | opening_range_failure | 2m | paper_trade_candidate | $4733.86 | $2309.47 | $4529.86 | 68 | 87.3% | 1 | robustness_confirmation | opening-range-failure robustness confirmation, not independent discovery |
| `MNQ_opening_range_failure_or20_tf2_opposite_max2` | opening_range_failure | 2m | paper_trade_candidate | $3424.11 | $2958.00 | $3145.11 | 93 | 96.8% | 1 | robustness_confirmation | opening-range-failure robustness confirmation, not independent discovery |
| `MNQ_opening_range_failure_or20_tf2_opposite_stop_after_first_loser` | opening_range_failure | 2m | watchlist | $3239.40 | $2731.05 | $3014.40 | 75 | 96.8% | 1 | robustness_confirmation | opening-range-failure robustness confirmation, not independent discovery |

## High-Confidence Candidates

- `MNQ_opening_range_failure_or20_tf1_mid_stop_after_first_loser`: net `$2275.31`, holdout `$1856.90`, 4-tick `$2026.31`, active `96.8%`.
- `MNQ_opening_range_failure_or30_tf3_opposite_max2`: net `$4275.42`, holdout `$2773.78`, 4-tick `$4038.42`, active `87.3%`.
- `MNQ_opening_range_failure_or30_tf2_opposite_max2`: net `$4390.12`, holdout `$2567.78`, 4-tick `$4153.12`, active `88.9%`.
- `MNQ_opening_range_failure_or25_tf5_opposite_max2`: net `$4798.23`, holdout `$2947.42`, 4-tick `$4558.23`, active `87.3%`.
- `MNQ_opening_range_failure_or20_tf1_mid_max1`: net `$2181.86`, holdout `$1637.23`, 4-tick `$1998.86`, active `96.8%`.
- `MNQ_opening_range_failure_or30_tf1_opposite_max2`: net `$4771.90`, holdout `$2169.53`, 4-tick `$4540.90`, active `88.9%`.
- `MNQ_opening_range_failure_or25_tf3_opposite_max2`: net `$4578.77`, holdout `$2890.06`, 4-tick `$4341.77`, active `85.7%`.
- `MNQ_opening_range_failure_or30_tf5_opposite_max2`: net `$3950.55`, holdout `$2458.08`, 4-tick `$3719.55`, active `85.7%`.

## Robustness Confirmations

- `MNQ_opening_range_failure_or30_tf3_opposite_max2` supports the nearby opening-range-failure family: net `$4275.42`, label `paper_trade_candidate`.
- `MNQ_opening_range_failure_or30_tf2_opposite_max2` supports the nearby opening-range-failure family: net `$4390.12`, label `paper_trade_candidate`.
- `MNQ_opening_range_failure_or25_tf5_opposite_max2` supports the nearby opening-range-failure family: net `$4798.23`, label `paper_trade_candidate`.
- `MNQ_opening_range_failure_or30_tf1_opposite_max2` supports the nearby opening-range-failure family: net `$4771.90`, label `paper_trade_candidate`.
- `MNQ_opening_range_failure_or25_tf3_opposite_max2` supports the nearby opening-range-failure family: net `$4578.77`, label `paper_trade_candidate`.
- `MNQ_opening_range_failure_or30_tf5_opposite_max2` supports the nearby opening-range-failure family: net `$3950.55`, label `paper_trade_candidate`.

## Likely Over-Search / Overfit Results

- Ignore or heavily discount `MNQ_first_hour_range_tf15_pullback` despite net `$3992.08` because `active on less than 70% of sessions; one-trade concentration risk`.
- Ignore or heavily discount `MNQ_first_hour_range_tf15_expansion` despite net `$3992.08` because `active on less than 70% of sessions; one-trade concentration risk`.
- Ignore or heavily discount `MNQ_opening_range_breakout_or60_tf5_half_range_2R` despite net `$3496.97` because `one-trade concentration risk`.
- Ignore or heavily discount `MNQ_opening_range_breakout_or60_tf3_half_range_2R` despite net `$2985.45` because `active on less than 70% of sessions; one-trade concentration risk`.
- Ignore or heavily discount `MNQ_first_hour_range_tf5_pullback` despite net `$2883.62` because `active on less than 70% of sessions; one-day concentration risk; one-trade concentration risk`.
- Ignore or heavily discount `MNQ_first_hour_range_tf5_expansion` despite net `$2883.62` because `active on less than 70% of sessions; one-day concentration risk; one-trade concentration risk`.

## Final Decision Answers

1. Yes, higher chart timeframes can be tested from 1-minute data by session-anchored OHLCV resampling and delayed signal availability.
2. Generated timeframes: `1m, 2m, 3m, 5m, 10m, 15m, 30m, 60m`.
3. Strategy variants tested: `433`.
4. Best-performing family by focused ranking: `opening_range_failure`.
5. Best signal timeframe overall: `1m`.
6. Did anything beat the Phase 3B no-overlap benchmark? `true`.
7. New `paper_trade_candidate` count: `60` (`83` total including robustness confirmations).
8. Phase 4B candidates: `MNQ_opening_range_failure_or20_tf1_mid_stop_after_first_loser, MNQ_opening_range_failure_or30_tf3_opposite_max2, MNQ_opening_range_failure_or30_tf2_opposite_max2, MNQ_opening_range_failure_or25_tf5_opposite_max2`.
9. Candidates to ignore despite high PnL: `MNQ_first_hour_range_tf15_pullback, MNQ_first_hour_range_tf15_expansion, MNQ_opening_range_breakout_or60_tf5_half_range_2R, MNQ_opening_range_breakout_or60_tf3_half_range_2R`.
10. Exact command: `python scripts/run_phase4a_multitimeframe_discovery.py`.

## Practical Readout

- Which strategy family looks most promising? `opening_range_failure`.
- Which timeframe looks most useful? `1m`.
- Which result is practical to paper trade? `MNQ_opening_range_failure_or20_tf1_mid_stop_after_first_loser`.
- Should Phase 4B validate a new candidate? `validate the strongest new candidate alongside the current MNQ opening-range-failure benchmark`.

## Outputs

- Ranked edges: `C:\Users\ulzii\Documents\Short Term Strategy Discovery\outputs\phase4a_ranked_edges.csv`
- Top edges: `C:\Users\ulzii\Documents\Short Term Strategy Discovery\outputs\phase4a_top_edges.csv`
- Family summary: `C:\Users\ulzii\Documents\Short Term Strategy Discovery\outputs\phase4a_family_summary.csv`
- Timeframe summary: `C:\Users\ulzii\Documents\Short Term Strategy Discovery\outputs\phase4a_timeframe_summary.csv`
- Trade logs: `C:\Users\ulzii\Documents\Short Term Strategy Discovery\trade_logs\phase4a`
- Charts: `C:\Users\ulzii\Documents\Short Term Strategy Discovery\charts\phase4a`
