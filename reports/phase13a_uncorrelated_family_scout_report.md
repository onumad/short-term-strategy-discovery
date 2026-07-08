# Phase 13A — Uncorrelated Family Scout

Research/simulation only. No live trading, broker adapters, order routing, webhooks, credential storage, automated execution, or LLM-driven trade decisions.

## Summary

- Specs evaluated: `48`
- Trade rows: `4382`
- Label counts: `{'phase13a_rejected_negative_stress': 43, 'phase13a_positive_uncorrelated_research_signal': 2, 'phase13a_rejected_negative_holdout': 2, 'phase13a_rejected_fold_instability': 1}`
- Next action: `add_to_research_signal_registry_and_run_portfolio_audit_b`
- Rationale: A positive but nontradable uncorrelated axis appeared.
- Paper trading approved: `false`

## Top Candidates

| Candidate | Label | Net | Stress | Val | Holdout | WF Stress | Avg registry corr | Max registry corr | Reasons |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `MNQ_13a_prior_rth_high_low_breakout_long_close_confirm_fill_next_open_structure_target_time_exit` | phase13a_positive_uncorrelated_research_signal | 883.00 | 760.00 | 1407.83 | 69.79 | 675.08 | 0.079 | 0.246 | fold instability; concentration |
| `MNQ_13a_prior_rth_high_low_breakout_long_close_confirm_fill_next_open_hard_stop_time_exit` | phase13a_positive_uncorrelated_research_signal | 879.00 | 756.00 | 1407.83 | 100.29 | 705.58 | 0.079 | 0.248 | fold instability; concentration |
| `MNQ_13a_lunch_range_fade_short_close_confirm_fill_next_open_hard_stop_time_exit` | phase13a_rejected_negative_stress | -50.86 | -166.86 | 356.48 | 26.15 | 255.28 | 0.054 | 0.085 | negative stress; fold instability; concentration |
| `MNQ_13a_power_hour_range_fade_short_two_bar_confirm_fill_next_open_hard_stop_time_exit` | phase13a_rejected_fold_instability | 138.69 | 49.69 | 64.92 | 173.70 | -154.26 | 0.032 | 0.068 | fold instability; concentration |
| `MNQ_13a_power_hour_range_fade_long_two_bar_confirm_fill_next_open_hard_stop_time_exit` | phase13a_rejected_negative_holdout | 170.88 | 95.88 | 109.72 | -695.21 | -166.59 | 0.061 | 0.245 | negative holdout; fold instability; concentration |
| `MNQ_13a_power_hour_range_breakout_long_close_confirm_fill_next_open_structure_target_time_exit` | phase13a_rejected_negative_stress | -66.47 | -165.47 | -269.01 | 95.10 | -93.45 | 0.090 | 0.144 | negative stress; negative validation; fold instability; concentration |
| `MNQ_13a_power_hour_range_fade_long_two_bar_confirm_fill_next_open_structure_target_time_exit` | phase13a_rejected_negative_stress | -36.76 | -111.76 | 52.34 | -448.31 | -244.28 | 0.037 | 0.112 | negative stress; negative holdout; fold instability; concentration |
| `MNQ_13a_power_hour_range_breakout_short_two_bar_confirm_fill_next_open_structure_target_time_exit` | phase13a_rejected_negative_holdout | 236.15 | 162.15 | 649.32 | -838.14 | -227.90 | 0.064 | 0.119 | negative holdout; fold instability; concentration |
| `MNQ_13a_lunch_range_breakout_long_close_confirm_fill_next_open_hard_stop_time_exit` | phase13a_rejected_negative_stress | -265.07 | -385.07 | 115.15 | 668.16 | 398.00 | 0.063 | 0.163 | negative stress; fold instability; concentration |
| `MNQ_13a_prior_rth_high_low_breakout_long_two_bar_confirm_fill_next_open_structure_target_time_exit` | phase13a_rejected_negative_stress | -117.48 | -235.48 | 1034.33 | -374.91 | 260.94 | 0.068 | 0.229 | negative stress; negative holdout; fold instability; concentration |
| `MNQ_13a_power_hour_range_breakout_long_close_confirm_fill_next_open_hard_stop_time_exit` | phase13a_rejected_negative_stress | -215.47 | -314.47 | -269.01 | 17.60 | -167.45 | 0.093 | 0.148 | negative stress; negative validation; fold instability; concentration |
| `MNQ_13a_lunch_range_breakout_long_close_confirm_fill_next_open_structure_target_time_exit` | phase13a_rejected_negative_stress | -243.02 | -363.02 | 37.15 | 627.66 | 279.50 | 0.065 | 0.153 | negative stress; fold instability; concentration |

## Outputs

- `outputs/phase13a_candidate_results.csv`
- `outputs/phase13a_trade_logs.csv`
- `outputs/phase13a_daily_pnl.csv`
- `outputs/phase13a_walk_forward_folds.csv`
- `outputs/phase13a_correlation_to_registry.csv`
- `outputs/phase13a_correlation_to_portfolios.csv`
- `C:/Users/ulzii/Documents/Short Term Strategy Discovery/reports/phase13a_uncorrelated_family_scout_report.md`
