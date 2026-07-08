# Phase 10A MNQ Overnight Range Breakout/Fade

Research/simulation only. No live trading, broker adapters, order routing, webhooks, credential storage, automated execution, or LLM-driven trade decisions.

## Summary

- Specs evaluated: `48`
- Trade rows: `6402`
- Label counts: `{'phase10a_rejected_negative_stress': 23, 'phase10a_rejected_negative_validation': 13, 'phase10a_rejected_fold_instability': 5, 'phase10a_rejected_low_activity': 5, 'phase10a_rejected_negative_holdout': 2}`
- Next action: `phase10b_targeted_overnight_range_diagnostic_retest`
- Rationale: One branch had positive stress/holdout but failed activity, fold, or concentration gates.

| Candidate | Label | Net | Stress | Val | Holdout | WF Stress | Notes |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| `MNQ_10a_onrange_overnight_range_breakout_short_tf15_midday_response_next_bar_open_hard_stop_time_exit` | phase10a_rejected_negative_validation | $3728.06 | $3577.06 | $-201.22 | $2720.72 | $2964.97 | negative validation; fold instability; concentration |
| `MNQ_10a_onrange_overnight_range_breakout_short_tf15_midday_response_next_bar_open_hard_stop_structure_target_time_exit` | phase10a_rejected_negative_validation | $2395.50 | $2244.50 | $-127.47 | $1843.49 | $2371.99 | negative validation; fold instability; concentration |
| `MNQ_10a_onrange_overnight_range_breakout_short_tf15_midday_response_close_confirm_fill_next_open_hard_stop_time_exit` | phase10a_rejected_negative_validation | $1921.64 | $1786.64 | $-464.26 | $2710.44 | $1741.13 | negative validation; fold instability; concentration |
| `MNQ_10a_onrange_overnight_range_breakout_short_tf5_midday_response_close_confirm_fill_next_open_hard_stop_time_exit` | phase10a_rejected_negative_validation | $1939.11 | $1781.11 | $-596.79 | $1910.28 | $1489.19 | negative validation; fold instability; concentration |
| `MNQ_10a_onrange_overnight_range_fade_long_tf15_opening_response_next_bar_open_hard_stop_time_exit` | phase10a_rejected_fold_instability | $969.70 | $898.70 | $729.27 | $912.14 | $1721.29 | fold instability; concentration |
| `MNQ_10a_onrange_overnight_range_fade_long_tf5_opening_response_next_bar_open_hard_stop_time_exit` | phase10a_rejected_fold_instability | $1344.18 | $1215.18 | $1243.87 | $1665.70 | $2205.98 | fold instability; concentration |
| `MNQ_10a_onrange_overnight_range_fade_long_tf15_opening_response_close_confirm_fill_next_open_hard_stop_time_exit` | phase10a_rejected_low_activity | $891.03 | $833.03 | $758.50 | $170.12 | $1116.70 | low activity; concentration |
| `MNQ_10a_onrange_overnight_range_breakout_short_tf5_midday_response_next_bar_open_hard_stop_time_exit` | phase10a_rejected_negative_validation | $2355.92 | $2181.92 | $-526.06 | $740.74 | $546.45 | negative validation; fold instability; concentration |
| `MNQ_10a_onrange_overnight_range_breakout_short_tf15_opening_response_close_confirm_fill_next_open_hard_stop_time_exit` | phase10a_rejected_low_activity | $1195.97 | $1148.97 | $-589.92 | $756.56 | $471.48 | low activity; negative validation; fold instability; concentration |
| `MNQ_10a_onrange_overnight_range_breakout_short_tf5_opening_response_close_confirm_fill_next_open_hard_stop_time_exit` | phase10a_rejected_negative_validation | $1049.06 | $956.06 | $-128.39 | $-427.15 | $690.38 | negative validation; negative holdout; fold instability; concentration |
| `MNQ_10a_onrange_overnight_range_fade_long_tf5_opening_response_close_confirm_fill_next_open_hard_stop_time_exit` | phase10a_rejected_fold_instability | $669.01 | $557.01 | $549.84 | $937.53 | $1279.94 | fold instability; concentration |
| `MNQ_10a_onrange_overnight_range_breakout_short_tf5_opening_response_next_bar_open_hard_stop_time_exit` | phase10a_rejected_negative_validation | $811.28 | $706.28 | $-161.54 | $-165.86 | $1359.04 | negative validation; negative holdout; fold instability; concentration |

## Outputs

- `outputs/phase10a_candidate_results.csv`
- `outputs/phase10a_trade_logs.csv`
- `outputs/phase10a_walk_forward_folds.csv`
- `outputs/phase10a_daily_pnl.csv`
- `outputs/phase10a_concentration_diagnostics.csv`
- `outputs/phase10a_level_diagnostics.csv`
- `outputs/phase10a_branch_summary.csv`
- `outputs/phase10a_side_summary.csv`
- `outputs/phase10a_time_window_summary.csv`
- `outputs/phase10a_exit_reason_summary.csv`
- `outputs/phase10a_range_regime_summary.csv`
- `outputs/phase10a_strategy_specs.json`
- `outputs/phase10a_next_action_recommendation.json`
- `C:/Users/ulzii/Documents/Short Term Strategy Discovery/artifacts/phase10a_overnight_range_breakout_fade/phase10a-r1-smoke/report.md`
