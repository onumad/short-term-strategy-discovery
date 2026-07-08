# Phase 15A — Trend Day / Power Hour Continuation Scout

Research/simulation only. No live trading, broker adapters, order routing, webhooks, credential storage, automated execution, or LLM-driven trade decisions.

Bounded 48-spec MNQ-only late-session continuation scout. No MGC, no prior-RTH high/low breakout, no prior-RTH close/midpoint reaction, no overnight levels, no opening range/opening-drive/VWAP/compression logic, no gate changes, no promotions, and no paper trading approval.

## Summary

- Specs evaluated: `48`
- Trade rows: `1680`
- Label counts: `{'phase15a_rejected_negative_stress': 35, 'phase15a_rejected_negative_holdout': 7, 'phase15a_positive_uncorrelated_research_signal': 3, 'phase15a_rejected_negative_validation': 3}`
- Next action: `add_to_registry_and_run_portfolio_audit_d`
- Rationale: A positive trend/power continuation axis was uncorrelated to existing registry/playbook diagnostics.
- Paper trading approved: `false`

## Top Candidates

| Candidate | Label | Net | Stress | Val | Holdout | WF Stress | Avg reg corr | Avg playbook corr | Gap days | Incremental gap days | Reasons |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `MNQ_15a_trend_day_late_pullback_continuation_short_ema20_pullback_resume_close_confirm_fill_next_open_hard_stop_time_exit` | phase15a_positive_uncorrelated_research_signal | 959.11 | 905.11 | 166.84 | 340.21 | 855.91 | 0.121 | 0.153 | 0 | 0 | low activity; fold instability; concentration |
| `MNQ_15a_trend_day_late_pullback_continuation_short_ema20_pullback_resume_close_confirm_fill_next_open_structure_target_time_exit` | phase15a_rejected_negative_validation | 758.26 | 704.26 | -92.66 | 445.90 | 718.56 | 0.112 | 0.126 | 0 | 0 | negative validation; low activity; fold instability; concentration |
| `MNQ_15a_trend_day_late_pullback_continuation_long_ema20_pullback_resume_close_confirm_fill_next_open_structure_target_time_exit` | phase15a_rejected_negative_holdout | 421.58 | 334.58 | 425.97 | -102.42 | 582.66 | 0.041 | 0.022 | 0 | 0 | negative holdout; fold instability; concentration |
| `MNQ_15a_trend_day_late_pullback_continuation_long_ema20_pullback_resume_close_confirm_fill_next_open_hard_stop_time_exit` | phase15a_rejected_negative_holdout | 517.04 | 430.04 | 334.24 | -214.15 | 507.12 | 0.043 | 0.021 | 0 | 0 | negative holdout; fold instability; concentration |
| `MNQ_15a_trend_day_late_pullback_continuation_long_morning_midpoint_retest_resume_close_confirm_fill_next_open_hard_stop_time_exit` | phase15a_rejected_negative_holdout | 268.42 | 249.42 | 191.06 | -298.98 | 215.14 | 0.034 | 0.049 | 0 | 0 | negative holdout; low activity; fold instability; concentration |
| `MNQ_15a_power_hour_continuation_long_power_range_breakout_continuation_close_confirm_fill_next_open_hard_stop_time_exit` | phase15a_positive_uncorrelated_research_signal | 150.00 | 100.00 | 94.55 | 312.84 | 491.50 | 0.037 | 0.081 | 0 | 0 | low activity; fold instability; concentration |
| `MNQ_15a_power_hour_continuation_long_power_range_edge_retest_resume_close_confirm_fill_next_open_hard_stop_time_exit` | phase15a_positive_uncorrelated_research_signal | 150.00 | 100.00 | 94.55 | 312.84 | 491.50 | 0.037 | 0.081 | 0 | 0 | low activity; fold instability; concentration |
| `MNQ_15a_trend_day_late_pullback_continuation_long_morning_midpoint_retest_resume_close_confirm_fill_next_open_structure_target_time_exit` | phase15a_rejected_negative_holdout | 112.84 | 93.84 | 217.56 | -241.48 | 129.06 | 0.035 | 0.056 | 0 | 0 | negative holdout; low activity; fold instability; concentration |
| `MNQ_15a_low_volatility_late_expansion_short_lunch_expansion_breakout_close_confirm_fill_next_open_structure_target_time_exit` | phase15a_rejected_negative_stress | -14.18 | -30.18 | 85.65 | 15.52 | 224.35 | 0.021 | 0.033 | 0 | 0 | negative stress; low activity; fold instability; concentration |
| `MNQ_15a_low_volatility_late_expansion_short_lunch_expansion_retest_resume_close_confirm_fill_next_open_structure_target_time_exit` | phase15a_rejected_negative_stress | -14.18 | -30.18 | 85.65 | 15.52 | 224.35 | 0.021 | 0.033 | 0 | 0 | negative stress; low activity; fold instability; concentration |
| `MNQ_15a_trend_day_late_pullback_continuation_short_morning_midpoint_retest_resume_close_confirm_fill_next_open_structure_target_time_exit` | phase15a_rejected_negative_validation | 78.98 | 65.98 | -53.98 | -29.74 | -92.20 | 0.034 | 0.063 | 0 | 0 | negative validation; negative holdout; low activity; fold instability; concentration |
| `MNQ_15a_trend_day_late_pullback_continuation_long_ema20_pullback_resume_two_bar_confirm_fill_next_open_structure_target_time_exit` | phase15a_rejected_negative_holdout | 158.84 | 74.84 | 96.72 | -122.68 | 61.46 | 0.053 | 0.055 | 0 | 0 | negative holdout; fold instability; concentration |

## Outputs

- `C:/Users/ulzii/Documents/Short Term Strategy Discovery/artifacts/phase15a_trend_power_continuation_scout/phase15a-r1-smoke/report.md`
- `outputs/phase15a_candidate_results.csv`
- `outputs/phase15a_trade_logs.csv`
- `outputs/phase15a_gap_coverage_summary.csv`
- `outputs/phase15a_next_action_recommendation.json`
