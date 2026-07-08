# Framework Audit C — Null / Bootstrap Research Signal Audit

Research/simulation only. No live trading, broker adapters, order routing, webhooks, credential storage, automated execution, or LLM-driven trade decisions.

## Summary

- Audit candidates: `20`
- Next action: `create_two_tier_research_signal_labeling`
- Rationale: Several signals remain positive under bootstrap/outlier diagnostics but fail concentration, activity, or fold gates.
- Matched random-entry raw-bar backtester: skipped; existing trade/daily pools used for null baselines.

## Candidate Classifications

| Phase | Candidate | Classification | Net | Stress | Val | Holdout |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| phase10b | `MNQ_10b_primary_short_midday_breakout_overnight_range_breakout_short_tf15_midday_response_exclude_widest_20_all_gaps_all_touches_mt1` | real_but_nontradable_signal | 2955.14 | 2877.14 | 334.40 | 811.84 |
| phase11a | `MNQ_11a_orfade_long_low_fade_OR5_midday_response_close_back_inside_fill_next_open_hard_stop_time_exit` | real_but_nontradable_signal | 1366.61 | 1215.61 | 82.84 | 303.50 |
| phase12a | `MNQ_12a_odpullback_long_first_pullback_OD15_drive_boundary_retest_resume_close_fill_next_open_hard_stop_time_exit` | real_but_nontradable_signal | 1006.49 | 953.49 | 41.79 | 226.88 |
| phase10b | `MNQ_10b_primary_short_midday_breakout_overnight_range_breakout_short_tf15_midday_response_exclude_widest_20_all_gaps_all_touches_mt2` | real_but_nontradable_signal | 2955.14 | 2877.14 | 334.40 | 811.84 |
| phase10b | `MNQ_10b_primary_short_midday_breakout_overnight_range_breakout_short_tf15_midday_response_all_ranges_all_gaps_all_touches_mt1` | real_but_nontradable_signal | 2730.48 | 2643.48 | 117.16 | 920.64 |
| phase10b | `MNQ_10b_primary_short_midday_breakout_overnight_range_breakout_short_tf15_midday_response_all_ranges_all_gaps_all_touches_mt2` | real_but_nontradable_signal | 2730.48 | 2643.48 | 117.16 | 920.64 |
| phase10b | `MNQ_10b_primary_short_midday_breakout_overnight_range_breakout_short_tf15_midday_response_middle_60_only_all_gaps_all_touches_mt1` | real_but_nontradable_signal | 2517.19 | 2460.19 | 334.40 | 811.84 |
| phase10b | `MNQ_10b_primary_short_midday_breakout_overnight_range_breakout_short_tf15_midday_response_middle_60_only_all_gaps_all_touches_mt2` | real_but_nontradable_signal | 2517.19 | 2460.19 | 334.40 | 811.84 |
| phase10b | `MNQ_10b_primary_short_midday_breakout_overnight_range_breakout_short_tf15_midday_response_middle_60_only_all_gaps_first_touch_only_mt1` | real_but_nontradable_signal | 1943.33 | 1897.33 | 340.14 | 692.56 |
| phase10b | `MNQ_10b_primary_short_midday_breakout_overnight_range_breakout_short_tf15_midday_response_middle_60_only_all_gaps_first_touch_only_mt2` | real_but_nontradable_signal | 1943.33 | 1897.33 | 340.14 | 692.56 |
| phase10b | `MNQ_10b_primary_short_midday_breakout_overnight_range_breakout_short_tf15_midday_response_exclude_narrowest_20_all_gaps_all_touches_mt1` | real_but_nontradable_signal | 2292.53 | 2226.53 | 117.16 | 920.64 |
| phase10b | `MNQ_10b_primary_short_midday_breakout_overnight_range_breakout_short_tf15_midday_response_exclude_narrowest_20_all_gaps_all_touches_mt2` | real_but_nontradable_signal | 2292.53 | 2226.53 | 117.16 | 920.64 |
| phase10b | `MNQ_10b_primary_short_midday_breakout_overnight_range_breakout_short_tf15_midday_response_exclude_narrowest_20_all_gaps_first_touch_only_mt1` | weak_research_signal | 1752.41 | 1698.41 | 122.90 | 835.10 |
| phase10b | `MNQ_10b_primary_short_midday_breakout_overnight_range_breakout_short_tf15_midday_response_exclude_narrowest_20_all_gaps_first_touch_only_mt2` | weak_research_signal | 1752.41 | 1698.41 | 122.90 | 835.10 |
| phase10b | `MNQ_10b_primary_short_midday_breakout_overnight_range_breakout_short_tf15_midday_response_exclude_widest_20_all_gaps_first_touch_only_mt1` | real_but_nontradable_signal | 1799.48 | 1737.48 | 340.14 | 692.56 |
| phase10b | `MNQ_10b_primary_short_midday_breakout_overnight_range_breakout_short_tf15_midday_response_exclude_widest_20_all_gaps_first_touch_only_mt2` | real_but_nontradable_signal | 1799.48 | 1737.48 | 340.14 | 692.56 |
| phase10b | `MNQ_10b_primary_short_midday_breakout_overnight_range_breakout_short_tf15_midday_response_all_ranges_all_gaps_first_touch_only_mt1` | weak_research_signal | 1608.56 | 1538.56 | 122.90 | 835.10 |
| phase10b | `MNQ_10b_primary_short_midday_breakout_overnight_range_breakout_short_tf15_midday_response_all_ranges_all_gaps_first_touch_only_mt2` | weak_research_signal | 1608.56 | 1538.56 | 122.90 | 835.10 |
| phase10b | `MNQ_10b_secondary_long_opening_fade_overnight_range_fade_long_tf5_opening_response_exclude_narrowest_20_all_gaps_all_touches_mt1` | weak_research_signal | 1643.50 | 1587.50 | 644.66 | 2011.98 |
| phase10b | `MNQ_10b_secondary_long_opening_fade_overnight_range_fade_long_tf5_opening_response_exclude_narrowest_20_all_gaps_all_touches_mt2` | weak_research_signal | 1643.50 | 1587.50 | 644.66 | 2011.98 |

## Outputs

- `outputs/framework_audit_c_candidate_selection.csv`
- `outputs/framework_audit_c_trade_bootstrap_summary.csv`
- `outputs/framework_audit_c_daily_bootstrap_summary.csv`
- `outputs/framework_audit_c_weekly_block_bootstrap_summary.csv`
- `outputs/framework_audit_c_monthly_block_bootstrap_summary.csv`
- `outputs/framework_audit_c_outlier_removal_summary.csv`
- `outputs/framework_audit_c_gate_probability_summary.csv`
- `outputs/framework_audit_c_null_baseline_summary.csv`
- `outputs/framework_audit_c_family_comparison.csv`
- `outputs/framework_audit_c_next_action_recommendation.json`
- `C:/Users/ulzii/Documents/Short Term Strategy Discovery/artifacts/framework_audit_c_null_bootstrap/framework-audit-c-smoke/report.md`
