# Phase 14A — Prior RTH Close / Midpoint Reaction Scout

Research/simulation only. No live trading, broker adapters, order routing, webhooks, credential storage, automated execution, or LLM-driven trade decisions.

Bounded 48-spec MNQ-only module scout. No prior RTH high/low breakout, overnight, opening range, opening-drive, VWAP, volatility compression, gate changes, promotions, or paper trading approval.

## Summary

- Specs evaluated: `48`
- Trade rows: `3948`
- Label counts: `{'phase14a_rejected_negative_stress': 32, 'phase14a_watchlist_needs_more_history': 14, 'phase14a_positive_uncorrelated_research_signal': 2}`
- Next action: `add_to_registry_and_run_portfolio_audit_c`
- Rationale: A positive prior-level reaction signal was uncorrelated to existing registry/playbook diagnostics.
- Paper trading approved: `false`

## Top Candidates

| Candidate | Label | Net | Stress | Val | Holdout | WF Stress | Avg reg corr | Avg playbook corr | Gap days | Incremental gap days | Reasons |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `MNQ_14a_prior_rth_midpoint_reclaim_after_breach_short_close_confirm_fill_next_open_hard_stop_time_exit` | phase14a_watchlist_needs_more_history | 2531.84 | 2441.84 | -434.15 | 1751.99 | 9.31 | 0.113 | 0.120 | 76 | 1 | negative validation; fold instability; concentration |
| `MNQ_14a_prior_rth_midpoint_breakout_hold_short_close_confirm_fill_next_open_hard_stop_time_exit` | phase14a_watchlist_needs_more_history | 2169.54 | 2084.54 | -382.91 | 1314.23 | -162.71 | 0.120 | 0.130 | 72 | 1 | negative validation; fold instability; concentration |
| `MNQ_14a_prior_rth_midpoint_rejection_from_level_short_two_bar_confirm_fill_next_open_structure_target_time_exit` | phase14a_watchlist_needs_more_history | 914.97 | 858.97 | -25.65 | 304.63 | 94.22 | 0.073 | 0.064 | 44 | 0 | negative validation; low activity; fold instability; concentration |
| `MNQ_14a_prior_rth_midpoint_rejection_from_level_short_close_confirm_fill_next_open_structure_target_time_exit` | phase14a_positive_uncorrelated_research_signal | 418.83 | 350.83 | 85.36 | 734.92 | 594.39 | 0.061 | 0.062 | 55 | 0 | fold instability; concentration |
| `MNQ_14a_prior_rth_close_rejection_from_level_short_two_bar_confirm_fill_next_open_structure_target_time_exit` | phase14a_watchlist_needs_more_history | 1089.98 | 1024.98 | -233.62 | 797.07 | -55.86 | 0.044 | 0.053 | 56 | 1 | negative validation; fold instability; concentration |
| `MNQ_14a_prior_rth_midpoint_reclaim_after_breach_short_two_bar_confirm_fill_next_open_structure_target_time_exit` | phase14a_watchlist_needs_more_history | 871.14 | 791.14 | -3.14 | 645.21 | 83.81 | 0.090 | 0.070 | 66 | 0 | negative validation; fold instability; concentration |
| `MNQ_14a_prior_rth_midpoint_breakout_hold_short_two_bar_confirm_fill_next_open_structure_target_time_exit` | phase14a_watchlist_needs_more_history | 920.84 | 844.84 | -1.90 | 249.20 | 24.89 | 0.091 | 0.061 | 63 | 0 | negative validation; fold instability; concentration |
| `MNQ_14a_prior_rth_midpoint_rejection_from_level_long_two_bar_confirm_fill_next_open_structure_target_time_exit` | phase14a_watchlist_needs_more_history | 420.50 | 363.50 | 195.05 | -143.63 | 334.58 | 0.052 | 0.083 | 46 | 1 | negative holdout; low activity; fold instability; concentration |
| `MNQ_14a_prior_rth_midpoint_rejection_from_level_short_two_bar_confirm_fill_next_open_hard_stop_time_exit` | phase14a_watchlist_needs_more_history | 799.13 | 743.13 | -46.90 | 64.88 | -390.87 | 0.079 | 0.065 | 44 | 0 | negative validation; low activity; fold instability; concentration |
| `MNQ_14a_prior_rth_close_rejection_from_level_short_two_bar_confirm_fill_next_open_hard_stop_time_exit` | phase14a_watchlist_needs_more_history | 419.55 | 354.55 | -5.35 | 804.38 | -137.09 | 0.050 | 0.058 | 56 | 1 | negative validation; fold instability; concentration |
| `MNQ_14a_prior_rth_close_rejection_from_level_long_two_bar_confirm_fill_next_open_structure_target_time_exit` | phase14a_positive_uncorrelated_research_signal | 379.14 | 306.14 | 161.41 | 437.23 | 122.36 | 0.103 | 0.168 | 66 | 1 | fold instability; concentration |
| `MNQ_14a_prior_rth_midpoint_reclaim_after_breach_short_two_bar_confirm_fill_next_open_hard_stop_time_exit` | phase14a_watchlist_needs_more_history | 982.16 | 902.16 | -13.89 | 324.89 | -604.98 | 0.101 | 0.072 | 66 | 0 | negative validation; fold instability; concentration |

## Outputs

- `C:/Users/ulzii/Documents/Short Term Strategy Discovery/reports/phase14a_prior_level_reaction_scout_report.md`
- `outputs/phase14a_candidate_results.csv`
- `outputs/phase14a_trade_logs.csv`
- `outputs/phase14a_gap_coverage_summary.csv`
- `outputs/phase14a_next_action_recommendation.json`
