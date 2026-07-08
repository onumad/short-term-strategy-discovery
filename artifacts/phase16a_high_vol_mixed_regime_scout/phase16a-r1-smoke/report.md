# Phase 16A — High-Vol Mixed Regime Module Scout

Research/simulation only. No live trading, broker adapters, order routing, webhooks, credential storage, automated execution, or LLM-driven trade decisions.

Bounded 48-spec MNQ-only high-volatility mixed-regime scout. No MGC, no prior-RTH high/low breakout, no prior-RTH close/midpoint reaction, no Phase 15A trend/power continuation, no overnight levels, no opening range/opening-drive/VWAP/volatility-compression logic, no official gate changes, no promotions, and no paper trading approval.

## Summary

- Specs evaluated: `48`
- Trade rows: `608`
- Label counts: `{'phase16a_rejected_negative_stress': 40, 'phase16a_watchlist_needs_more_history': 5, 'phase16a_positive_uncorrelated_research_signal': 3}`
- Next action: `rare_module_validation_track_review`
- Rationale: Fold adequacy is sparse under standardized module-level policy.
- Paper trading approved: `false`

## Top Candidates

| Candidate | Label | Net | Stress | Val | Holdout | WF Stress | Avg reg corr | Avg playbook corr | Gap days | Incremental gap days | Fold adequacy | Reasons |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| `MNQ_16a_high_vol_mixed_late_resolution_breakout_long_broad_high_vol_mixed_close_confirm_fill_next_open_structure_target_time_exit` | phase16a_positive_uncorrelated_research_signal | 516.62 | 486.62 | 67.03 | 703.28 | 568.28 | 0.071 | 0.087 | 29 | 0 | low_activity_not_fully_interpretable | low activity; fold instability; concentration; fold adequacy |
| `MNQ_16a_high_vol_mixed_late_resolution_breakout_long_broad_high_vol_mixed_close_confirm_fill_next_open_hard_stop_time_exit` | phase16a_positive_uncorrelated_research_signal | 356.91 | 326.91 | 284.75 | 415.60 | 498.32 | 0.062 | 0.074 | 29 | 0 | low_activity_not_fully_interpretable | low activity; fold instability; concentration; fold adequacy |
| `MNQ_16a_high_vol_mixed_late_resolution_breakout_long_strict_high_vol_mixed_close_confirm_fill_next_open_structure_target_time_exit` | phase16a_watchlist_needs_more_history | 159.00 | 155.00 | 0.00 | 242.20 | 240.20 | 0.066 | 0.103 | 4 | 0 | low_activity_not_fully_interpretable | negative validation; high correlation; low activity; fold instability; concentration; fold adequacy |
| `MNQ_16a_high_vol_mixed_extreme_fade_long_strict_high_vol_mixed_close_confirm_fill_next_open_hard_stop_time_exit` | phase16a_rejected_negative_stress | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.000 | 0.000 | 0 | 0 | low_activity_not_fully_interpretable | negative stress; negative validation; negative holdout; low activity; fold instability; concentration; fold adequacy |
| `MNQ_16a_high_vol_mixed_extreme_fade_long_strict_high_vol_mixed_close_confirm_fill_next_open_structure_target_time_exit` | phase16a_rejected_negative_stress | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.000 | 0.000 | 0 | 0 | low_activity_not_fully_interpretable | negative stress; negative validation; negative holdout; low activity; fold instability; concentration; fold adequacy |
| `MNQ_16a_high_vol_mixed_extreme_fade_long_strict_high_vol_mixed_two_bar_confirm_fill_next_open_hard_stop_time_exit` | phase16a_rejected_negative_stress | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.000 | 0.000 | 0 | 0 | low_activity_not_fully_interpretable | negative stress; negative validation; negative holdout; low activity; fold instability; concentration; fold adequacy |
| `MNQ_16a_high_vol_mixed_extreme_fade_long_strict_high_vol_mixed_two_bar_confirm_fill_next_open_structure_target_time_exit` | phase16a_rejected_negative_stress | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.000 | 0.000 | 0 | 0 | low_activity_not_fully_interpretable | negative stress; negative validation; negative holdout; low activity; fold instability; concentration; fold adequacy |
| `MNQ_16a_high_vol_mixed_extreme_fade_short_strict_high_vol_mixed_close_confirm_fill_next_open_hard_stop_time_exit` | phase16a_rejected_negative_stress | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.000 | 0.000 | 0 | 0 | low_activity_not_fully_interpretable | negative stress; negative validation; negative holdout; low activity; fold instability; concentration; fold adequacy |
| `MNQ_16a_high_vol_mixed_extreme_fade_short_strict_high_vol_mixed_close_confirm_fill_next_open_structure_target_time_exit` | phase16a_rejected_negative_stress | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.000 | 0.000 | 0 | 0 | low_activity_not_fully_interpretable | negative stress; negative validation; negative holdout; low activity; fold instability; concentration; fold adequacy |
| `MNQ_16a_high_vol_mixed_extreme_fade_short_strict_high_vol_mixed_two_bar_confirm_fill_next_open_hard_stop_time_exit` | phase16a_rejected_negative_stress | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.000 | 0.000 | 0 | 0 | low_activity_not_fully_interpretable | negative stress; negative validation; negative holdout; low activity; fold instability; concentration; fold adequacy |
| `MNQ_16a_high_vol_mixed_extreme_fade_short_strict_high_vol_mixed_two_bar_confirm_fill_next_open_structure_target_time_exit` | phase16a_rejected_negative_stress | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.000 | 0.000 | 0 | 0 | low_activity_not_fully_interpretable | negative stress; negative validation; negative holdout; low activity; fold instability; concentration; fold adequacy |
| `MNQ_16a_high_vol_mixed_late_resolution_breakout_long_broad_high_vol_mixed_two_bar_confirm_fill_next_open_hard_stop_time_exit` | phase16a_positive_uncorrelated_research_signal | 235.53 | 208.53 | 117.36 | 181.91 | 91.45 | 0.081 | 0.062 | 26 | 0 | low_activity_not_fully_interpretable | low activity; fold instability; concentration; fold adequacy |

## Fold Views

Required fold views reported: existing_project_folds, half_year_folds, rolling_6_month_test_folds, quarterly_folds. Alternative folds are diagnostic companions only; official gates unchanged.

## Outputs

- `C:/Users/ulzii/Documents/Short Term Strategy Discovery/artifacts/phase16a_high_vol_mixed_regime_scout/phase16a-r1-smoke/report.md`
- `outputs/phase16a_candidate_results.csv`
- `outputs/phase16a_trade_logs.csv`
- `outputs/phase16a_gap_coverage_summary.csv`
- `outputs/phase16a_fold_view_summary.csv`
- `outputs/phase16a_module_fold_adequacy.csv`
- `outputs/phase16a_next_action_recommendation.json`
