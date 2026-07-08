# Framework Audit B — Research Signal / Gate / Backtester Sanity Audit

Research/simulation only. No live trading, broker adapters, order routing, webhooks, credential storage, automated execution, or LLM-driven trade decisions.

## Summary

- Audit candidates: `37`
- Next action: `separate_rare_setup_research_track`
- Rationale: Activity constraints are a dominant rejection mode among audited signals.

## Audited Signals

| Phase | Candidate | Interpretation | Net | Stress | Val | Holdout | Reject reasons |
| --- | --- | --- | ---: | ---: | ---: | ---: | --- |
| phase10b | `MNQ_10b_primary_short_midday_breakout_overnight_range_breakout_short_tf15_midday_response_exclude_widest_20_all_gaps_all_touches_mt1` | real_but_nontradable_signal | 2955.14 | 2877.14 | 334.40 | 811.84 | fold instability; concentration |
| phase10b | `MNQ_10b_primary_short_midday_breakout_overnight_range_breakout_short_tf15_midday_response_exclude_widest_20_all_gaps_all_touches_mt2` | real_but_nontradable_signal | 2955.14 | 2877.14 | 334.40 | 811.84 | fold instability; concentration |
| phase10b | `MNQ_10b_primary_short_midday_breakout_overnight_range_breakout_short_tf15_midday_response_all_ranges_all_gaps_all_touches_mt1` | real_but_nontradable_signal | 2730.48 | 2643.48 | 117.16 | 920.64 | fold instability; concentration |
| phase10b | `MNQ_10b_primary_short_midday_breakout_overnight_range_breakout_short_tf15_midday_response_all_ranges_all_gaps_all_touches_mt2` | real_but_nontradable_signal | 2730.48 | 2643.48 | 117.16 | 920.64 | fold instability; concentration |
| phase10b | `MNQ_10b_primary_short_midday_breakout_overnight_range_breakout_short_tf15_midday_response_middle_60_only_all_gaps_all_touches_mt1` | candidate_needs_more_history | 2517.19 | 2460.19 | 334.40 | 811.84 | low activity; fold instability; concentration |
| phase10b | `MNQ_10b_primary_short_midday_breakout_overnight_range_breakout_short_tf15_midday_response_middle_60_only_all_gaps_all_touches_mt2` | candidate_needs_more_history | 2517.19 | 2460.19 | 334.40 | 811.84 | low activity; fold instability; concentration |
| phase10b | `MNQ_10b_primary_short_midday_breakout_overnight_range_breakout_short_tf15_midday_response_middle_60_only_all_gaps_first_touch_only_mt1` | candidate_needs_more_history | 1943.33 | 1897.33 | 340.14 | 692.56 | low activity; fold instability; concentration |
| phase10b | `MNQ_10b_primary_short_midday_breakout_overnight_range_breakout_short_tf15_midday_response_middle_60_only_all_gaps_first_touch_only_mt2` | candidate_needs_more_history | 1943.33 | 1897.33 | 340.14 | 692.56 | low activity; fold instability; concentration |
| phase10b | `MNQ_10b_primary_short_midday_breakout_overnight_range_breakout_short_tf15_midday_response_exclude_narrowest_20_all_gaps_all_touches_mt1` | real_but_nontradable_signal | 2292.53 | 2226.53 | 117.16 | 920.64 | fold instability; concentration |
| phase10b | `MNQ_10b_primary_short_midday_breakout_overnight_range_breakout_short_tf15_midday_response_exclude_narrowest_20_all_gaps_all_touches_mt2` | real_but_nontradable_signal | 2292.53 | 2226.53 | 117.16 | 920.64 | fold instability; concentration |
| phase10b | `MNQ_10b_primary_short_midday_breakout_overnight_range_breakout_short_tf15_midday_response_exclude_narrowest_20_all_gaps_first_touch_only_mt1` | candidate_needs_more_history | 1752.41 | 1698.41 | 122.90 | 835.10 | low activity; fold instability; concentration |
| phase10b | `MNQ_10b_primary_short_midday_breakout_overnight_range_breakout_short_tf15_midday_response_exclude_narrowest_20_all_gaps_first_touch_only_mt2` | candidate_needs_more_history | 1752.41 | 1698.41 | 122.90 | 835.10 | low activity; fold instability; concentration |
| phase10b | `MNQ_10b_primary_short_midday_breakout_overnight_range_breakout_short_tf15_midday_response_exclude_widest_20_all_gaps_first_touch_only_mt1` | framework_gate_too_strict_possible | 1799.48 | 1737.48 | 340.14 | 692.56 | fold instability; concentration |
| phase10b | `MNQ_10b_primary_short_midday_breakout_overnight_range_breakout_short_tf15_midday_response_exclude_widest_20_all_gaps_first_touch_only_mt2` | framework_gate_too_strict_possible | 1799.48 | 1737.48 | 340.14 | 692.56 | fold instability; concentration |
| phase10b | `MNQ_10b_primary_short_midday_breakout_overnight_range_breakout_short_tf15_midday_response_all_ranges_all_gaps_first_touch_only_mt1` | framework_gate_too_strict_possible | 1608.56 | 1538.56 | 122.90 | 835.10 | fold instability; concentration |
| phase10b | `MNQ_10b_primary_short_midday_breakout_overnight_range_breakout_short_tf15_midday_response_all_ranges_all_gaps_first_touch_only_mt2` | framework_gate_too_strict_possible | 1608.56 | 1538.56 | 122.90 | 835.10 | fold instability; concentration |
| phase10b | `MNQ_10b_secondary_long_opening_fade_overnight_range_fade_long_tf5_opening_response_exclude_narrowest_20_all_gaps_all_touches_mt1` | candidate_needs_more_history | 1643.50 | 1587.50 | 644.66 | 2011.98 | low activity; fold instability; concentration |
| phase10b | `MNQ_10b_secondary_long_opening_fade_overnight_range_fade_long_tf5_opening_response_exclude_narrowest_20_all_gaps_all_touches_mt2` | candidate_needs_more_history | 1643.50 | 1587.50 | 644.66 | 2011.98 | low activity; fold instability; concentration |
| phase10b | `MNQ_10b_secondary_long_opening_fade_overnight_range_fade_long_tf15_opening_response_exclude_narrowest_20_all_gaps_all_touches_mt1` | candidate_needs_more_history | 996.36 | 947.36 | 534.01 | 749.88 | low activity; fold instability; concentration |
| phase10b | `MNQ_10b_secondary_long_opening_fade_overnight_range_fade_long_tf15_opening_response_exclude_narrowest_20_all_gaps_all_touches_mt2` | candidate_needs_more_history | 996.36 | 947.36 | 534.01 | 749.88 | low activity; fold instability; concentration |
| phase10b | `MNQ_10b_secondary_long_opening_fade_overnight_range_fade_long_tf15_opening_response_all_ranges_all_gaps_all_touches_mt1` | real_but_nontradable_signal | 969.70 | 898.70 | 729.27 | 912.14 | fold instability; concentration |
| phase10b | `MNQ_10b_secondary_long_opening_fade_overnight_range_fade_long_tf15_opening_response_all_ranges_all_gaps_all_touches_mt2` | real_but_nontradable_signal | 969.70 | 898.70 | 729.27 | 912.14 | fold instability; concentration |
| phase10b | `MNQ_10b_secondary_long_opening_fade_overnight_range_fade_long_tf5_opening_response_all_ranges_all_gaps_all_touches_mt1` | real_but_nontradable_signal | 1001.57 | 917.57 | 764.92 | 2095.74 | fold instability; concentration |
| phase10b | `MNQ_10b_secondary_long_opening_fade_overnight_range_fade_long_tf5_opening_response_all_ranges_all_gaps_all_touches_mt2` | real_but_nontradable_signal | 1001.57 | 917.57 | 764.92 | 2095.74 | fold instability; concentration |
| phase11a | `MNQ_11a_orfade_long_low_fade_OR5_midday_response_close_back_inside_fill_next_open_hard_stop_time_exit` | real_but_nontradable_signal | 1366.61 | 1215.61 | 82.84 | 303.50 | fold instability; concentration |
| phase11a | `MNQ_11a_orfade_long_low_fade_OR5_opening_response_close_back_inside_fill_next_open_hard_stop_time_exit` | real_but_nontradable_signal | 1042.64 | 859.64 | 720.79 | 1112.58 | fold instability; concentration |
| phase11a | `MNQ_11a_orfade_long_low_fade_OR5_opening_response_two_bar_inside_fill_next_open_hard_stop_time_exit` | real_but_nontradable_signal | 455.59 | 328.59 | 92.10 | 337.14 | fold instability; concentration |
| phase11a | `MNQ_11a_orfade_short_high_fade_OR30_opening_response_two_bar_inside_fill_next_open_hard_stop_time_exit` | real_but_nontradable_signal | 256.18 | 195.18 | 51.38 | 1229.88 | fold instability; concentration |
| phase12a | `MNQ_12a_odpullback_long_first_pullback_OD15_drive_boundary_retest_resume_close_fill_next_open_hard_stop_time_exit` | candidate_needs_more_history | 1006.49 | 953.49 | 41.79 | 226.88 | low activity; fold instability; concentration |
| phase12a | `MNQ_12a_odpullback_long_first_pullback_OD15_drive_boundary_retest_two_bar_resume_fill_next_open_hard_stop_time_exit` | candidate_needs_more_history | 761.81 | 715.81 | 313.11 | 51.38 | low activity; fold instability; concentration |
| phase12a | `MNQ_12a_odpullback_long_first_pullback_OD15_ema20_retest_two_bar_resume_fill_next_open_hard_stop_time_exit` | candidate_needs_more_history | 682.13 | 637.13 | 381.00 | 495.83 | low activity; fold instability; concentration |
| phase12a | `MNQ_12a_odpullback_long_first_pullback_OD15_ema20_retest_two_bar_resume_fill_next_open_structure_target_time_exit` | candidate_needs_more_history | 383.96 | 338.96 | 131.00 | 162.33 | low activity; fold instability; concentration |
| phase12a | `MNQ_12a_odpullback_short_first_pullback_OD30_drive_boundary_retest_resume_close_fill_next_open_hard_stop_time_exit` | candidate_needs_more_history | 470.97 | 429.97 | 92.84 | 200.26 | low activity; fold instability; concentration |
| phase12a | `MNQ_12a_odpullback_long_first_pullback_OD30_ema20_retest_two_bar_resume_fill_next_open_structure_target_time_exit` | candidate_needs_more_history | 267.42 | 212.42 | 139.04 | 123.22 | low activity; fold instability; concentration |
| phase12a | `MNQ_12a_odpullback_long_first_pullback_OD15_ema20_retest_resume_close_fill_next_open_hard_stop_time_exit` | candidate_needs_more_history | 220.86 | 166.86 | 315.08 | 131.90 | low activity; fold instability; concentration |
| phase12a | `MNQ_12a_odpullback_long_first_pullback_OD15_drive_boundary_retest_resume_close_fill_next_open_structure_target_time_exit` | candidate_needs_more_history | 67.49 | 14.49 | 58.79 | 173.88 | low activity; fold instability; concentration |
| phase12a | `MNQ_12a_odpullback_short_first_pullback_OD30_drive_boundary_retest_two_bar_resume_fill_next_open_hard_stop_time_exit` | candidate_needs_more_history | 66.32 | 33.32 | 360.32 | 45.76 | low activity; fold instability; concentration |

## Outputs

- `outputs/framework_audit_b_research_signal_summary.csv`
- `outputs/framework_audit_b_gate_sensitivity.csv`
- `outputs/framework_audit_b_cost_waterfall_summary.csv`
- `outputs/framework_audit_b_fold_stability_summary.csv`
- `outputs/framework_audit_b_concentration_summary.csv`
- `outputs/framework_audit_b_activity_summary.csv`
- `outputs/framework_audit_b_top_trade_day_dependency.csv`
- `outputs/framework_audit_b_next_action_recommendation.json`
- `C:/Users/ulzii/Documents/Short Term Strategy Discovery/reports/framework_audit_b_report.md`
