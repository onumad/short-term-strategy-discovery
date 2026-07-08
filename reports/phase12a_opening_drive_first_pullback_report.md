# Phase 12A Opening-Drive First Pullback Continuation

Research/simulation only. No live trading, broker adapters, order routing, webhooks, credential storage, automated execution, or LLM-driven trade decisions.

## Summary

- Specs evaluated: `48`
- Trade rows: `2172`
- Label counts: `{'phase12a_rejected_low_activity': 44, 'phase12a_rejected_negative_stress': 4}`
- Research axis status counts: `{'axis_failed': 26, 'axis_positive_but_concentrated': 9, 'axis_positive_but_unstable': 7, 'axis_positive_but_cost_sensitive': 6}`
- Next action: `park_opening_drive_pullback_as_research_signal`
- Rationale: Phase 12A had positive axes but they remained concentrated or unstable.

## Candidate Results

| Candidate | Status | Label | Net | Stress | Val | Holdout | WF Stress | Notes |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| `MNQ_12a_odpullback_short_first_pullback_OD15_drive_boundary_retest_two_bar_resume_fill_next_open_hard_stop_time_exit` | axis_positive_but_unstable | phase12a_rejected_low_activity | $1256.78 | $1219.78 | $390.48 | $-180.15 | $975.89 | low activity; negative holdout; fold instability; concentration |
| `MNQ_12a_odpullback_long_first_pullback_OD15_drive_boundary_retest_resume_close_fill_next_open_hard_stop_time_exit` | axis_positive_but_concentrated | phase12a_rejected_low_activity | $1006.49 | $953.49 | $41.79 | $226.88 | $440.05 | low activity; fold instability; concentration |
| `MNQ_12a_odpullback_long_first_pullback_OD15_drive_boundary_retest_two_bar_resume_fill_next_open_hard_stop_time_exit` | axis_positive_but_concentrated | phase12a_rejected_low_activity | $761.81 | $715.81 | $313.11 | $51.38 | $617.77 | low activity; fold instability; concentration |
| `MNQ_12a_odpullback_long_first_pullback_OD15_ema20_retest_two_bar_resume_fill_next_open_hard_stop_time_exit` | axis_positive_but_concentrated | phase12a_rejected_low_activity | $682.13 | $637.13 | $381.00 | $495.83 | $482.23 | low activity; fold instability; concentration |
| `MNQ_12a_odpullback_short_first_pullback_OD15_drive_boundary_retest_resume_close_fill_next_open_hard_stop_time_exit` | axis_positive_but_unstable | phase12a_rejected_low_activity | $721.77 | $680.77 | $-13.92 | $366.82 | $944.46 | low activity; negative validation; fold instability; concentration |
| `MNQ_12a_odpullback_long_first_pullback_OD15_ema20_retest_two_bar_resume_fill_next_open_structure_target_time_exit` | axis_positive_but_concentrated | phase12a_rejected_low_activity | $383.96 | $338.96 | $131.00 | $162.33 | $382.56 | low activity; fold instability; concentration |
| `MNQ_12a_odpullback_short_first_pullback_OD60_drive_boundary_retest_resume_close_fill_next_open_hard_stop_time_exit` | axis_positive_but_unstable | phase12a_rejected_low_activity | $848.39 | $814.39 | $-29.80 | $972.30 | $346.21 | low activity; negative validation; fold instability; concentration |
| `MNQ_12a_odpullback_short_first_pullback_OD30_drive_boundary_retest_resume_close_fill_next_open_hard_stop_time_exit` | axis_positive_but_concentrated | phase12a_rejected_low_activity | $470.97 | $429.97 | $92.84 | $200.26 | $497.22 | low activity; fold instability; concentration |
| `MNQ_12a_odpullback_long_first_pullback_OD30_ema20_retest_two_bar_resume_fill_next_open_structure_target_time_exit` | axis_positive_but_concentrated | phase12a_rejected_low_activity | $267.42 | $212.42 | $139.04 | $123.22 | $302.62 | low activity; fold instability; concentration |
| `MNQ_12a_odpullback_short_first_pullback_OD60_ema20_retest_two_bar_resume_fill_next_open_structure_target_time_exit` | axis_positive_but_unstable | phase12a_rejected_low_activity | $226.47 | $197.47 | $-137.12 | $10.52 | $-0.80 | low activity; negative validation; fold instability; concentration |
| `MNQ_12a_odpullback_long_first_pullback_OD15_ema20_retest_resume_close_fill_next_open_structure_target_time_exit` | axis_positive_but_unstable | phase12a_rejected_low_activity | $170.19 | $116.19 | $302.58 | $-5.10 | $561.21 | low activity; negative holdout; fold instability; concentration |
| `MNQ_12a_odpullback_long_first_pullback_OD15_ema20_retest_resume_close_fill_next_open_hard_stop_time_exit` | axis_positive_but_concentrated | phase12a_rejected_low_activity | $220.86 | $166.86 | $315.08 | $131.90 | $242.88 | low activity; fold instability; concentration |

## Outputs

- `outputs/phase12a_candidate_results.csv`
- `outputs/phase12a_trade_logs.csv`
- `outputs/phase12a_walk_forward_folds.csv`
- `outputs/phase12a_daily_pnl.csv`
- `outputs/phase12a_concentration_diagnostics.csv`
- `outputs/phase12a_od_window_summary.csv`
- `outputs/phase12a_side_summary.csv`
- `outputs/phase12a_pullback_anchor_summary.csv`
- `outputs/phase12a_confirmation_summary.csv`
- `outputs/phase12a_exit_reason_summary.csv`
- `outputs/phase12a_opening_drive_width_summary.csv`
- `outputs/phase12a_extension_distance_summary.csv`
- `outputs/phase12a_pullback_depth_summary.csv`
- `outputs/phase12a_mfe_mae_summary.csv`
- `outputs/phase12a_strategy_specs.json`
- `outputs/phase12a_next_action_recommendation.json`
- `C:/Users/ulzii/Documents/Short Term Strategy Discovery/reports/phase12a_opening_drive_first_pullback_report.md`
