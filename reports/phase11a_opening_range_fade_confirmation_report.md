# Phase 11A Opening Range Fade With Stricter Confirmation

Research/simulation only. No live trading, broker adapters, order routing, webhooks, credential storage, automated execution, or LLM-driven trade decisions.

## Summary

- Specs evaluated: `48`
- Trade rows: `5846`
- Label counts: `{'phase11a_rejected_negative_stress': 37, 'phase11a_rejected_fold_instability': 4, 'phase11a_rejected_negative_validation': 3, 'phase11a_rejected_negative_holdout': 2, 'phase11a_rejected_low_activity': 2}`
- Research axis status counts: `{'axis_failed': 33, 'axis_positive_but_concentrated': 7, 'axis_positive_but_cost_sensitive': 6, 'axis_positive_but_unstable': 2}`
- Next action: `park_opening_range_fade_as_research_signal`
- Rationale: Phase 11A had positive axes but they remained concentrated or unstable.

## Candidate Results

| Candidate | Status | Label | Net | Stress | Val | Holdout | WF Stress | Notes |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| `MNQ_11a_orfade_long_low_fade_OR5_midday_response_two_bar_inside_fill_next_open_hard_stop_time_exit` | axis_positive_but_unstable | phase11a_rejected_negative_holdout | $1599.33 | $1473.33 | $252.52 | $-193.26 | $449.28 | negative holdout; fold instability; concentration |
| `MNQ_11a_orfade_long_low_fade_OR5_midday_response_close_back_inside_fill_next_open_hard_stop_time_exit` | axis_positive_but_concentrated | phase11a_rejected_fold_instability | $1366.61 | $1215.61 | $82.84 | $303.50 | $576.23 | fold instability; concentration |
| `MNQ_11a_orfade_long_low_fade_OR30_opening_response_close_back_inside_fill_next_open_midpoint_target_time_exit` | axis_positive_but_concentrated | phase11a_rejected_negative_validation | $1098.94 | $1029.94 | $-762.38 | $742.12 | $477.89 | negative validation; fold instability; concentration |
| `MNQ_11a_orfade_long_low_fade_OR5_opening_response_close_back_inside_fill_next_open_hard_stop_time_exit` | axis_positive_but_concentrated | phase11a_rejected_fold_instability | $1042.64 | $859.64 | $720.79 | $1112.58 | $993.45 | fold instability; concentration |
| `MNQ_11a_orfade_long_low_fade_OR30_midday_response_two_bar_inside_fill_next_open_midpoint_target_time_exit` | axis_positive_but_unstable | phase11a_rejected_negative_holdout | $390.95 | $251.95 | $1150.47 | $-188.28 | $674.07 | negative holdout; fold instability; concentration |
| `MNQ_11a_orfade_long_low_fade_OR5_opening_response_two_bar_inside_fill_next_open_hard_stop_time_exit` | axis_positive_but_concentrated | phase11a_rejected_fold_instability | $455.59 | $328.59 | $92.10 | $337.14 | $263.26 | fold instability; concentration |
| `MNQ_11a_orfade_long_low_fade_OR5_midday_response_close_back_inside_fill_next_open_midpoint_target_time_exit` | axis_positive_but_cost_sensitive | phase11a_rejected_negative_stress | $-100.96 | $-251.96 | $49.34 | $-139.75 | $-62.84 | negative stress; negative holdout; fold instability; concentration |
| `MNQ_11a_orfade_long_low_fade_OR30_opening_response_two_bar_inside_fill_next_open_midpoint_target_time_exit` | axis_positive_but_cost_sensitive | phase11a_rejected_low_activity | $-36.70 | $-91.70 | $-381.90 | $134.60 | $-18.44 | low activity; negative stress; negative validation; fold instability; concentration |
| `MNQ_11a_orfade_long_low_fade_OR30_midday_response_close_back_inside_fill_next_open_midpoint_target_time_exit` | axis_failed | phase11a_rejected_negative_stress | $-483.28 | $-639.28 | $704.14 | $-290.27 | $168.04 | negative stress; negative holdout; fold instability; concentration |
| `MNQ_11a_orfade_short_high_fade_OR5_midday_response_two_bar_inside_fill_next_open_midpoint_target_time_exit` | axis_positive_but_cost_sensitive | phase11a_rejected_negative_stress | $-186.88 | $-298.88 | $-120.50 | $-795.03 | $-571.81 | negative stress; negative validation; negative holdout; fold instability; concentration |
| `MNQ_11a_orfade_long_low_fade_OR15_opening_response_close_back_inside_fill_next_open_midpoint_target_time_exit` | axis_positive_but_cost_sensitive | phase11a_rejected_negative_stress | $-94.94 | $-219.94 | $-458.73 | $1017.75 | $-188.21 | negative stress; negative validation; fold instability; concentration |
| `MNQ_11a_orfade_long_low_fade_OR5_midday_response_two_bar_inside_fill_next_open_midpoint_target_time_exit` | axis_failed | phase11a_rejected_negative_stress | $-584.21 | $-710.21 | $-188.73 | $-151.51 | $-400.22 | negative stress; negative validation; negative holdout; fold instability; concentration |

## Outputs

- `outputs/phase11a_candidate_results.csv`
- `outputs/phase11a_trade_logs.csv`
- `outputs/phase11a_walk_forward_folds.csv`
- `outputs/phase11a_daily_pnl.csv`
- `outputs/phase11a_concentration_diagnostics.csv`
- `outputs/phase11a_or_window_summary.csv`
- `outputs/phase11a_side_summary.csv`
- `outputs/phase11a_entry_window_summary.csv`
- `outputs/phase11a_confirmation_summary.csv`
- `outputs/phase11a_exit_reason_summary.csv`
- `outputs/phase11a_touch_sequence_summary.csv`
- `outputs/phase11a_opening_range_width_summary.csv`
- `outputs/phase11a_sweep_distance_summary.csv`
- `outputs/phase11a_mfe_mae_summary.csv`
- `outputs/phase11a_strategy_specs.json`
- `outputs/phase11a_next_action_recommendation.json`
- `C:/Users/ulzii/Documents/Short Term Strategy Discovery/reports/phase11a_opening_range_fade_confirmation_report.md`
