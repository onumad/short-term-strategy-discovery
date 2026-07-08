# Validation Framework Audit C — Fold Design

Research/simulation only. No live trading, broker adapters, order routing, webhooks, credential storage, automated execution, or LLM-driven trade decisions.

Diagnostic fold-design audit only. No new signals, no strategy searches, no candidate-result changes, no official gate changes, no promotions, no paper-trading approval, and no live-trading functionality were added.

## Summary

- Primary playbook series for fold-regime diagnostics: `scheduler_d` / `scheduler_d|portfolio_mode=max_one_trade_per_session|priority_policy=hybrid_validation_then_correlation|pruning_variant=no_overlay_baseline`
- Current fold rows audited: `1296`
- Alternative fold rows computed: `7862`
- Module activity rows computed: `36`
- Fold conclusions change by design: `True`
- Rare modules too sparse for module-level fold gates: `False`
- Weak folds regime-composition driven: `False`
- Fold instability consistent across designs: `True`
- Next action: `validation_framework_d_standardize_playbook_folds`
- Rationale: Diagnostic conclusions materially change under deterministic fold-design alternatives.

## Current fold boundary findings

| source | entity_label | fold_id | fold_start | fold_end | days_in_fold | active_days_in_fold | trades_in_fold | fold_pnl | fold_stress_pnl | weak_or_positive_status | calendar_region_key | weak_source_count_same_calendar_region | same_calendar_region_weak_across_b_c_d_scheduler_b_c_d |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| portfolio_b | portfolio_b|portfolio_mode=max_one_trade_per_session|portfolio_set=all_parked_modules_with_phase13a | 1 | 2025-07-14 | 2025-09-11 | 40 | 40 | 40 | -962.89 | -1002.89 | weak | fold_1 | 6 | True |
| portfolio_b | portfolio_b|portfolio_mode=max_one_trade_per_session|portfolio_set=all_parked_modules_with_phase13a | 2 | 2025-09-12 | 2025-11-10 | 40 | 40 | 40 | 1197.61 | 1157.61 | positive | fold_2 | 6 | True |
| portfolio_b | portfolio_b|portfolio_mode=max_one_trade_per_session|portfolio_set=all_parked_modules_with_phase13a | 3 | 2025-11-11 | 2026-01-08 | 40 | 40 | 40 | -546.63 | -586.63 | weak | fold_3 | 6 | True |
| portfolio_b | portfolio_b|portfolio_mode=max_one_trade_per_session|portfolio_set=all_parked_modules_with_phase13a | 4 | 2026-01-09 | 2026-03-06 | 40 | 40 | 40 | -375.03 | -415.03 | weak | fold_4 | 6 | True |
| portfolio_b | portfolio_b|portfolio_mode=max_one_trade_per_session|portfolio_set=all_parked_modules_with_phase13a | 5 | 2026-03-09 | 2026-05-05 | 40 | 40 | 40 | 465.72 | 425.72 | positive | fold_5 | 6 | True |
| portfolio_b | portfolio_b|portfolio_mode=max_one_trade_per_session|portfolio_set=all_parked_modules_with_phase13a | 6 | 2026-05-06 | 2026-07-02 | 40 | 40 | 40 | 1143.37 | 1103.37 | positive | fold_6 | 2 | False |
| portfolio_b | portfolio_b|portfolio_mode=max_one_trade_per_session|portfolio_set=audit_a_best_plus_phase13a | 1 | 2025-07-15 | 2025-09-09 | 39 | 39 | 39 | -225.33 | -264.33 | weak | fold_1 | 6 | True |
| portfolio_b | portfolio_b|portfolio_mode=max_one_trade_per_session|portfolio_set=audit_a_best_plus_phase13a | 2 | 2025-09-10 | 2025-11-04 | 39 | 39 | 39 | 738.08 | 699.08 | positive | fold_2 | 6 | True |
| portfolio_b | portfolio_b|portfolio_mode=max_one_trade_per_session|portfolio_set=audit_a_best_plus_phase13a | 3 | 2025-11-06 | 2026-01-06 | 39 | 39 | 39 | -867.79 | -906.79 | weak | fold_3 | 6 | True |
| portfolio_b | portfolio_b|portfolio_mode=max_one_trade_per_session|portfolio_set=audit_a_best_plus_phase13a | 4 | 2026-01-07 | 2026-03-02 | 39 | 39 | 39 | 155.5 | 116.5 | positive | fold_4 | 6 | True |
| portfolio_b | portfolio_b|portfolio_mode=max_one_trade_per_session|portfolio_set=audit_a_best_plus_phase13a | 5 | 2026-03-03 | 2026-04-30 | 39 | 39 | 39 | 2340.75 | 2301.75 | positive | fold_5 | 6 | True |
| portfolio_b | portfolio_b|portfolio_mode=max_one_trade_per_session|portfolio_set=audit_a_best_plus_phase13a | 6 | 2026-05-01 | 2026-07-02 | 41 | 41 | 41 | 1992.44 | 1951.44 | positive | fold_6 | 2 | False |
| portfolio_b | portfolio_b|portfolio_mode=max_one_trade_per_session|portfolio_set=audit_a_best_reconstructed | 1 | 2025-07-15 | 2025-09-10 | 33 | 33 | 33 | 34.95 | 1.95 | positive | fold_1 | 6 | True |
| portfolio_b | portfolio_b|portfolio_mode=max_one_trade_per_session|portfolio_set=audit_a_best_reconstructed | 2 | 2025-09-11 | 2025-11-07 | 33 | 33 | 33 | 1044.57 | 1011.57 | positive | fold_2 | 6 | True |
| portfolio_b | portfolio_b|portfolio_mode=max_one_trade_per_session|portfolio_set=audit_a_best_reconstructed | 3 | 2025-11-10 | 2026-01-05 | 33 | 33 | 33 | 960.42 | 927.42 | positive | fold_3 | 6 | True |
| portfolio_b | portfolio_b|portfolio_mode=max_one_trade_per_session|portfolio_set=audit_a_best_reconstructed | 4 | 2026-01-06 | 2026-02-25 | 33 | 33 | 33 | -492.42 | -525.42 | weak | fold_4 | 6 | True |
| portfolio_b | portfolio_b|portfolio_mode=max_one_trade_per_session|portfolio_set=audit_a_best_reconstructed | 5 | 2026-02-26 | 2026-04-28 | 33 | 33 | 33 | 1292.29 | 1259.29 | positive | fold_5 | 6 | True |
| portfolio_b | portfolio_b|portfolio_mode=max_one_trade_per_session|portfolio_set=audit_a_best_reconstructed | 6 | 2026-04-30 | 2026-07-02 | 34 | 34 | 34 | 2689.44 | 2655.44 | positive | fold_6 | 2 | False |
| portfolio_b | portfolio_b|portfolio_mode=max_one_trade_per_session|portfolio_set=diversifier_only_phase13a | 1 | 2025-07-15 | 2025-09-04 | 20 | 20 | 20 | -13.14 | -33.14 | weak | fold_1 | 6 | True |
| portfolio_b | portfolio_b|portfolio_mode=max_one_trade_per_session|portfolio_set=diversifier_only_phase13a | 2 | 2025-09-05 | 2025-10-27 | 20 | 20 | 20 | 171.4 | 151.4 | positive | fold_2 | 6 | True |
| portfolio_b | portfolio_b|portfolio_mode=max_one_trade_per_session|portfolio_set=diversifier_only_phase13a | 3 | 2025-10-28 | 2026-01-09 | 20 | 20 | 20 | -967.61 | -987.61 | weak | fold_3 | 6 | True |
| portfolio_b | portfolio_b|portfolio_mode=max_one_trade_per_session|portfolio_set=diversifier_only_phase13a | 4 | 2026-01-12 | 2026-03-17 | 20 | 20 | 20 | 469.92 | 449.92 | positive | fold_4 | 6 | True |
| portfolio_b | portfolio_b|portfolio_mode=max_one_trade_per_session|portfolio_set=diversifier_only_phase13a | 5 | 2026-03-23 | 2026-05-04 | 20 | 20 | 20 | 1190.12 | 1170.12 | positive | fold_5 | 6 | True |
| portfolio_b | portfolio_b|portfolio_mode=max_one_trade_per_session|portfolio_set=diversifier_only_phase13a | 6 | 2026-05-05 | 2026-06-30 | 23 | 23 | 23 | 28.31 | 5.31 | positive | fold_6 | 2 | False |
| portfolio_b | portfolio_b|portfolio_mode=max_one_trade_per_session|portfolio_set=greedy_low_correlation_with_phase13a | 1 | 2025-07-14 | 2025-09-08 | 40 | 40 | 40 | -920.67 | -960.67 | weak | fold_1 | 6 | True |
| portfolio_b | portfolio_b|portfolio_mode=max_one_trade_per_session|portfolio_set=greedy_low_correlation_with_phase13a | 2 | 2025-09-09 | 2025-11-04 | 40 | 40 | 40 | 893.4 | 853.4 | positive | fold_2 | 6 | True |
| portfolio_b | portfolio_b|portfolio_mode=max_one_trade_per_session|portfolio_set=greedy_low_correlation_with_phase13a | 3 | 2025-11-05 | 2026-01-02 | 40 | 40 | 40 | -411.13 | -451.13 | weak | fold_3 | 6 | True |
| portfolio_b | portfolio_b|portfolio_mode=max_one_trade_per_session|portfolio_set=greedy_low_correlation_with_phase13a | 4 | 2026-01-05 | 2026-02-27 | 40 | 40 | 40 | -667.14 | -707.14 | weak | fold_4 | 6 | True |
| portfolio_b | portfolio_b|portfolio_mode=max_one_trade_per_session|portfolio_set=greedy_low_correlation_with_phase13a | 5 | 2026-03-02 | 2026-04-28 | 40 | 40 | 40 | 1112.63 | 1072.63 | positive | fold_5 | 6 | True |
| portfolio_b | portfolio_b|portfolio_mode=max_one_trade_per_session|portfolio_set=greedy_low_correlation_with_phase13a | 6 | 2026-04-29 | 2026-07-01 | 43 | 43 | 43 | 1070.74 | 1027.74 | positive | fold_6 | 2 | False |

## Alternative fold design findings

| source | entity_label | fold_design | fold_count | positive_fold_pct | worst_fold_pnl | median_fold_pnl | fold_pnl_standard_deviation | median_active_days_per_fold | median_trades_per_fold | folds_with_too_few_trades | folds_dominated_by_one_day | median_one_day_concentration | positive_fold_pct_range | conclusion_materially_changes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| portfolio_b | portfolio_b|portfolio_mode=max_one_trade_per_session|portfolio_set=diversifier_only_phase13a | calendar_year_folds | 2 | 0.5 | -463.19 | 439.5 | 902.69 | 61.5 | 61.5 | 0 | 0 | 0.052511 | 0.571429 | True |
| portfolio_b | portfolio_b|portfolio_mode=max_one_trade_per_session|portfolio_set=diversifier_only_phase13a | existing_project_folds | 6 | 0.666667 | -967.61 | 99.855 | 642.269168 | 20.0 | 20.0 | 0 | 0 | 0.136929 | 0.571429 | True |
| portfolio_b | portfolio_b|portfolio_mode=max_one_trade_per_session|portfolio_set=diversifier_only_phase13a | expanding_train_recent_test_style | 2 | 1.0 | 336.54 | 671.095 | 334.555 | 33.5 | 33.5 | 0 | 0 | 0.099223 | 0.571429 | True |
| portfolio_b | portfolio_b|portfolio_mode=max_one_trade_per_session|portfolio_set=diversifier_only_phase13a | half_year_folds | 2 | 0.5 | -463.19 | 439.5 | 902.69 | 61.5 | 61.5 | 0 | 0 | 0.052511 | 0.571429 | True |
| portfolio_b | portfolio_b|portfolio_mode=max_one_trade_per_session|portfolio_set=diversifier_only_phase13a | quarterly_folds | 4 | 0.75 | -571.69 | 222.52 | 563.478604 | 28.5 | 28.5 | 0 | 0 | 0.106151 | 0.571429 | True |
| portfolio_b | portfolio_b|portfolio_mode=max_one_trade_per_session|portfolio_set=diversifier_only_phase13a | rolling_3_month_test_folds | 10 | 0.7 | -760.82 | 230.305 | 930.936253 | 29.5 | 29.5 | 0 | 0 | 0.100697 | 0.571429 | True |
| portfolio_b | portfolio_b|portfolio_mode=max_one_trade_per_session|portfolio_set=diversifier_only_phase13a | rolling_6_month_test_folds | 7 | 0.428571 | -501.29 | -235.15 | 836.957508 | 58.0 | 58.0 | 0 | 0 | 0.04926 | 0.571429 | True |
| portfolio_b | portfolio_b|portfolio_mode=one_trade_at_a_time_chronological|portfolio_set=diversifier_only_phase13a | calendar_year_folds | 2 | 0.5 | -638.61 | 199.84 | 838.45 | 61.5 | 61.5 | 0 | 0 | 0.071284 | 0.571429 | True |
| portfolio_b | portfolio_b|portfolio_mode=one_trade_at_a_time_chronological|portfolio_set=diversifier_only_phase13a | existing_project_folds | 6 | 0.5 | -1143.03 | 81.52 | 679.090436 | 20.0 | 20.0 | 0 | 0 | 0.147865 | 0.571429 | True |
| portfolio_b | portfolio_b|portfolio_mode=one_trade_at_a_time_chronological|portfolio_set=diversifier_only_phase13a | expanding_train_recent_test_style | 2 | 1.0 | 69.31 | 519.145 | 449.835 | 33.5 | 33.5 | 0 | 0 | 0.095863 | 0.571429 | True |
| portfolio_b | portfolio_b|portfolio_mode=one_trade_at_a_time_chronological|portfolio_set=diversifier_only_phase13a | half_year_folds | 2 | 0.5 | -638.61 | 199.84 | 838.45 | 61.5 | 61.5 | 0 | 0 | 0.071284 | 0.571429 | True |
| portfolio_b | portfolio_b|portfolio_mode=one_trade_at_a_time_chronological|portfolio_set=diversifier_only_phase13a | quarterly_folds | 4 | 0.75 | -747.11 | 88.905 | 606.987581 | 28.5 | 28.5 | 0 | 0 | 0.114899 | 0.571429 | True |
| portfolio_b | portfolio_b|portfolio_mode=one_trade_at_a_time_chronological|portfolio_set=diversifier_only_phase13a | rolling_3_month_test_folds | 10 | 0.7 | -1044.87 | 88.905 | 989.304055 | 29.5 | 29.5 | 0 | 0 | 0.114899 | 0.571429 | True |
| portfolio_b | portfolio_b|portfolio_mode=one_trade_at_a_time_chronological|portfolio_set=diversifier_only_phase13a | rolling_6_month_test_folds | 7 | 0.428571 | -924.07 | -638.61 | 836.652519 | 58.0 | 58.0 | 0 | 0 | 0.073833 | 0.571429 | True |
| portfolio_d | portfolio_d|portfolio_mode=max_one_trade_per_session|portfolio_set=greedy_low_correlation_with_15a | calendar_year_folds | 2 | 0.5 | -2102.99 | 1854.26 | 3957.25 | 122.5 | 122.5 | 0 | 0 | 0.036286 | 0.545455 | True |
| portfolio_d | portfolio_d|portfolio_mode=max_one_trade_per_session|portfolio_set=greedy_low_correlation_with_15a | existing_project_folds | 6 | 0.5 | -1176.97 | -71.795 | 1867.235298 | 40.0 | 40.0 | 0 | 0 | 0.090328 | 0.545455 | True |
| portfolio_d | portfolio_d|portfolio_mode=max_one_trade_per_session|portfolio_set=greedy_low_correlation_with_15a | expanding_train_recent_test_style | 3 | 1.0 | 743.79 | 1063.02 | 1467.761828 | 60.0 | 60.0 | 1 | 1 | 0.068173 | 0.545455 | True |
| portfolio_d | portfolio_d|portfolio_mode=max_one_trade_per_session|portfolio_set=greedy_low_correlation_with_15a | half_year_folds | 3 | 0.666667 | -2102.99 | 1063.02 | 2799.783457 | 120.0 | 120.0 | 1 | 1 | 0.035677 | 0.545455 | True |
| portfolio_d | portfolio_d|portfolio_mode=max_one_trade_per_session|portfolio_set=greedy_low_correlation_with_15a | quarterly_folds | 5 | 0.6 | -1445.81 | 743.79 | 1870.426965 | 60.0 | 60.0 | 1 | 1 | 0.068173 | 0.545455 | True |
| portfolio_d | portfolio_d|portfolio_mode=max_one_trade_per_session|portfolio_set=greedy_low_correlation_with_15a | rolling_3_month_test_folds | 11 | 0.454545 | -1445.81 | -427.1 | 1851.213666 | 62.0 | 62.0 | 0 | 0 | 0.056637 | 0.545455 | True |
| portfolio_d | portfolio_d|portfolio_mode=max_one_trade_per_session|portfolio_set=greedy_low_correlation_with_15a | rolling_6_month_test_folds | 8 | 0.5 | -2102.99 | -90.5 | 2581.220778 | 123.0 | 123.0 | 0 | 0 | 0.030595 | 0.545455 | True |
| scheduler_d | scheduler_d|portfolio_mode=max_one_trade_per_session|priority_policy=concentration_adjusted_priority|pruning_variant=overlay_exclude_parked | calendar_year_folds | 2 | 0.5 | -1462.17 | 938.15 | 2400.32 | 124.0 | 248.0 | 0 | 0 | 0.032225 | 0.545455 | True |
| scheduler_d | scheduler_d|portfolio_mode=max_one_trade_per_session|priority_policy=concentration_adjusted_priority|pruning_variant=overlay_exclude_parked | existing_project_folds | 6 | 0.666667 | -1232.77 | 256.475 | 1044.529292 | 41.0 | 248.0 | 0 | 0 | 0.083143 | 0.545455 | True |
| scheduler_d | scheduler_d|portfolio_mode=max_one_trade_per_session|priority_policy=concentration_adjusted_priority|pruning_variant=overlay_exclude_parked | expanding_train_recent_test_style | 3 | 1.0 | 285.52 | 537.87 | 996.882792 | 62.0 | 248.0 | 1 | 1 | 0.06683 | 0.545455 | True |
| scheduler_d | scheduler_d|portfolio_mode=max_one_trade_per_session|priority_policy=concentration_adjusted_priority|pruning_variant=overlay_exclude_parked | half_year_folds | 3 | 0.666667 | -1462.17 | 285.52 | 1858.894467 | 121.0 | 248.0 | 1 | 1 | 0.034454 | 0.545455 | True |
| scheduler_d | scheduler_d|portfolio_mode=max_one_trade_per_session|priority_policy=concentration_adjusted_priority|pruning_variant=overlay_exclude_parked | quarterly_folds | 5 | 0.6 | -1140.63 | 285.52 | 1216.287601 | 62.0 | 248.0 | 1 | 1 | 0.06683 | 0.545455 | True |
| scheduler_d | scheduler_d|portfolio_mode=max_one_trade_per_session|priority_policy=concentration_adjusted_priority|pruning_variant=overlay_exclude_parked | rolling_3_month_test_folds | 11 | 0.454545 | -1140.63 | -74.83 | 1096.363909 | 63.0 | 248.0 | 0 | 0 | 0.053236 | 0.545455 | True |
| scheduler_d | scheduler_d|portfolio_mode=max_one_trade_per_session|priority_policy=concentration_adjusted_priority|pruning_variant=overlay_exclude_parked | rolling_6_month_test_folds | 8 | 0.5 | -1462.17 | -124.02 | 1570.236007 | 125.5 | 248.0 | 0 | 0 | 0.03047 | 0.545455 | True |
| scheduler_d | scheduler_d|portfolio_mode=max_one_trade_per_session|priority_policy=concentration_adjusted_priority|pruning_variant=overlay_keep_representatives_only | calendar_year_folds | 2 | 0.5 | -2152.18 | 793.225 | 2945.405 | 118.5 | 248.0 | 0 | 0 | 0.036704 | 0.545455 | True |
| scheduler_d | scheduler_d|portfolio_mode=max_one_trade_per_session|priority_policy=concentration_adjusted_priority|pruning_variant=overlay_keep_representatives_only | existing_project_folds | 6 | 0.5 | -1761.29 | 215.65 | 1222.596943 | 39.0 | 248.0 | 0 | 0 | 0.08757 | 0.545455 | True |

## Rare-module fold adequacy

| module_group | folds | low_activity_folds | median_active_days | median_trades | total_pnl |
| --- | --- | --- | --- | --- | --- |
| phase10b | 6 | 0 | 20.5 | 354.0 | 60928.020000000004 |
| phase11a | 6 | 0 | 41.0 | 988.0 | -34733.08 |
| phase12a | 6 | 0 | 33.5 | 349.0 | -2059.52 |
| phase13a | 6 | 0 | 40.5 | 721.0 | -27363.48 |
| phase14a | 6 | 0 | 23.5 | 657.0 | -28617.34 |
| phase15a | 6 | 0 | 33.0 | 276.0 | -2294.39 |

## Fold regime composition

| source | entity_label | fold_design | fold_id | fold_start | fold_end | day_count_with_features | fold_pnl | is_weak_fold | high_vol_frequency | trend_day_frequency | range_day_frequency | power_hour_expansion_frequency | prior_level_interaction_frequency | no_trade_high_movement_day_frequency | diagnosis_regime_heavy | diagnosis_low_sample | diagnosis_outlier_affected | diagnosis_broadly_weak_across_conditions |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| scheduler_d | scheduler_d|portfolio_mode=max_one_trade_per_session|priority_policy=hybrid_validation_then_correlation|pruning_variant=no_overlay_baseline | existing_project_folds | 1 | 2025-07-14 | 2025-09-08 | 41 | -936.45 | True | 0.219512 | 0.463415 | 0.219512 | 0.317073 | 0.878049 | 0.0 | False | False | False | True |
| scheduler_d | scheduler_d|portfolio_mode=max_one_trade_per_session|priority_policy=hybrid_validation_then_correlation|pruning_variant=no_overlay_baseline | existing_project_folds | 2 | 2025-09-09 | 2025-11-04 | 41 | 886.16 | False | 0.268293 | 0.390244 | 0.121951 | 0.243902 | 0.878049 | 0.0 | False | False | False | False |
| scheduler_d | scheduler_d|portfolio_mode=max_one_trade_per_session|priority_policy=hybrid_validation_then_correlation|pruning_variant=no_overlay_baseline | existing_project_folds | 3 | 2025-11-05 | 2026-01-05 | 41 | -72.37 | True | 0.487805 | 0.414634 | 0.097561 | 0.243902 | 0.878049 | 0.0 | False | False | False | True |
| scheduler_d | scheduler_d|portfolio_mode=max_one_trade_per_session|priority_policy=hybrid_validation_then_correlation|pruning_variant=no_overlay_baseline | existing_project_folds | 4 | 2026-01-06 | 2026-03-03 | 41 | -1008.88 | True | 0.585366 | 0.390244 | 0.121951 | 0.292683 | 0.95122 | 0.0 | True | False | False | False |
| scheduler_d | scheduler_d|portfolio_mode=max_one_trade_per_session|priority_policy=hybrid_validation_then_correlation|pruning_variant=no_overlay_baseline | existing_project_folds | 5 | 2026-03-04 | 2026-04-30 | 41 | 1305.17 | False | 0.658537 | 0.463415 | 0.04878 | 0.439024 | 0.97561 | 0.0 | True | False | False | False |
| scheduler_d | scheduler_d|portfolio_mode=max_one_trade_per_session|priority_policy=hybrid_validation_then_correlation|pruning_variant=no_overlay_baseline | existing_project_folds | 6 | 2026-05-01 | 2026-07-02 | 43 | 2635.14 | False | 0.860465 | 0.395349 | 0.023256 | 0.255814 | 0.930233 | 0.0 | True | False | False | False |

## Recommended validation policy

- `diagnostic_only`: `True`
- `official_gates_changed`: `False`
- `paper_trading_approved`: `False`
- `live_trading_approved`: `False`
- `new_strategy_signals_generated`: `False`
- `keep_official_gates_unchanged`: `True`
- `add_rare_module_fold_adequacy_diagnostics`: `True`
- `report_module_and_playbook_fold_stability_separately`: `True`
- `require_minimum_fold_activity_before_interpreting_module_fold_result`: `True`
- `minimum_module_active_days_per_fold_for_interpretation`: `5`
- `minimum_module_trades_per_fold_for_interpretation`: `10`
- `alternative_fold_designs_are_diagnostic_companion_only`: `True`
- `require_out_of_sample_future_data_before_promotion`: `True`
- `do_not_loosen_paper_review_gates`: `True`
- `rare_modules_too_sparse_for_module_level_fold_gates`: `False`
- `fold_conclusions_change_by_design`: `True`
- `weak_folds_regime_composition_driven`: `False`
- `fold_instability_consistent_across_designs`: `True`

## Guardrails

Official gates changed: `false`.
Paper trading approved: `false`.
New strategy signals generated: `false`.
Strategy searches run: `false`.
Live trading approved: `false`.
