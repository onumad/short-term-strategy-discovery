# Portfolio Audit E — Playbook With Phase 16A Rare High-Vol Modules

Research/simulation only. No live trading, broker adapters, order routing, webhooks, credential storage, automated execution, or LLM-driven trade decisions.

## Scope

Diagnostic portfolio audit only. It uses existing registries, scheduler/portfolio baselines, weak-regime context, and completed phase outputs; it does not generate signals, run searches, change official gates, promote candidates, approve paper trading, or add live-trading functionality.

## Summary

- Selected modules: `32`
- Portfolio rows: `27`
- Next action: `playbook_scheduler_e_rare_module_priority_audit`
- Rationale: Rare modules improved activity as a group but increased overlap or drawdown diagnostics.
- Paper trading approved: `false`

## Phase 16A Impact Versus Scheduler D Best

| Mode | Active days Δ | Fold Δ | Best-day conc Δ | Best-trade conc Δ | Drawdown Δ | Correlation Δ | PnL | Trades | Active days | Overlap skipped | Session skipped | No-trade days | Negative-PnL days | Contribution status |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| raw_sum_diagnostic | 1 | 0.000 | 0.001 | -0.014 | -505.15 | 0.032 | 1109.06 | 87 | 30 | 0 | 0 | 1 | 12 | improves_activity |
| one_trade_at_a_time_chronological | 1 | 0.000 | 0.020 | -0.003 | -252.45 | 0.032 | 106.97 | 36 | 30 | 143 | 0 | 1 | 12 | improves_activity |
| max_one_trade_per_session | 1 | 0.000 | 0.000 | 0.000 | -54.81 | 0.032 | 98.47 | 3 | 3 | 0 | 434 | 1 | 1 | improves_activity |

## Rare Module Contribution

| Signal | Phase | Validation class | Fold adequacy | Research track | Tradability | Role | Playbook contribution | Net | Trades | Days |
| --- | --- | --- | --- | --- | --- | --- | --- | ---: | ---: | ---: |
| phase10b::MNQ_10b_primary_short_midday_breakout_overnight_range_breakout_short_tf15_midday_response_middle_60_only_all_gaps_all_touches_mt1 | phase10b | rare_positive_research_signal | not_available | rare_setup_research_signal | not_tradable_low_activity | parked_module | positive_contribution | 2517.19 | 57 | 57 |
| phase10b::MNQ_10b_primary_short_midday_breakout_overnight_range_breakout_short_tf15_midday_response_middle_60_only_all_gaps_all_touches_mt2 | phase10b | rare_positive_research_signal | not_available | rare_setup_research_signal | not_tradable_low_activity | parked_module | positive_contribution | 2517.19 | 57 | 57 |
| phase10b::MNQ_10b_primary_short_midday_breakout_overnight_range_breakout_short_tf15_midday_response_middle_60_only_all_gaps_first_touch_only_mt1 | phase10b | rare_positive_research_signal | not_available | rare_setup_research_signal | not_tradable_low_activity | parked_module | positive_contribution | 1943.33 | 46 | 46 |
| phase10b::MNQ_10b_primary_short_midday_breakout_overnight_range_breakout_short_tf15_midday_response_middle_60_only_all_gaps_first_touch_only_mt2 | phase10b | rare_positive_research_signal | not_available | rare_setup_research_signal | not_tradable_low_activity | parked_module | positive_contribution | 1943.33 | 46 | 46 |
| phase10b::MNQ_10b_secondary_long_opening_fade_overnight_range_fade_long_tf5_opening_response_exclude_narrowest_20_all_gaps_all_touches_mt1 | phase10b | rare_positive_research_signal | not_available | rare_setup_research_signal | not_tradable_low_activity | parked_module | positive_contribution | 1643.50 | 56 | 56 |
| phase10b::MNQ_10b_secondary_long_opening_fade_overnight_range_fade_long_tf5_opening_response_exclude_narrowest_20_all_gaps_all_touches_mt2 | phase10b | rare_positive_research_signal | not_available | rare_setup_research_signal | not_tradable_low_activity | parked_module | positive_contribution | 1643.50 | 56 | 56 |
| phase12a::MNQ_12a_odpullback_long_first_pullback_OD15_ema20_retest_two_bar_resume_fill_next_open_hard_stop_time_exit | phase12a | rare_positive_research_signal | not_available | rare_setup_research_signal | not_tradable_low_activity | rare_setup_module | positive_contribution | 682.13 | 45 | 45 |
| phase15a::MNQ_15a_power_hour_continuation_long_power_range_breakout_continuation_close_confirm_fill_next_open_hard_stop_time_exit | phase15a | rare_uncorrelated_diversifier_candidate | not_available | rare_setup_research_signal | not_tradable_low_activity | diversifier_module | positive_contribution | 150.00 | 50 | 50 |
| phase15a::MNQ_15a_power_hour_continuation_long_power_range_edge_retest_resume_close_confirm_fill_next_open_hard_stop_time_exit | phase15a | rare_uncorrelated_diversifier_candidate | not_available | rare_setup_research_signal | not_tradable_low_activity | diversifier_module | positive_contribution | 150.00 | 50 | 50 |
| phase15a::MNQ_15a_trend_day_late_pullback_continuation_short_ema20_pullback_resume_close_confirm_fill_next_open_hard_stop_time_exit | phase15a | rare_uncorrelated_diversifier_candidate | not_available | rare_setup_research_signal | not_tradable_low_activity | diversifier_module | positive_contribution | 959.11 | 54 | 54 |
| phase16a::MNQ_16a_high_vol_mixed_late_resolution_breakout_long_broad_high_vol_mixed_close_confirm_fill_next_open_hard_stop_time_exit | phase16a | rare_uncorrelated_diversifier_candidate | not_available | rare_setup_research_signal | not_tradable_low_activity | diversifier_module | positive_contribution | 356.91 | 30 | 30 |
| phase16a::MNQ_16a_high_vol_mixed_late_resolution_breakout_long_broad_high_vol_mixed_close_confirm_fill_next_open_structure_target_time_exit | phase16a | rare_uncorrelated_diversifier_candidate | not_available | rare_setup_research_signal | not_tradable_low_activity | diversifier_module | positive_contribution | 516.62 | 30 | 30 |
| phase16a::MNQ_16a_high_vol_mixed_late_resolution_breakout_long_broad_high_vol_mixed_two_bar_confirm_fill_next_open_hard_stop_time_exit | phase16a | rare_uncorrelated_diversifier_candidate | not_available | rare_setup_research_signal | not_tradable_low_activity | diversifier_module | positive_contribution | 235.53 | 27 | 27 |

## Weak-Regime Coverage

| Set | Regime days | Phase16A days | Helped | Hurt | Net |
| --- | ---: | ---: | ---: | ---: | ---: |
| scheduler_d_best_reconstructed | 248 | 30 | 14 | 16 | 1109.06 |
| scheduler_d_best_plus_phase16a | 248 | 30 | 14 | 16 | 1109.06 |
| portfolio_d_best_plus_phase16a | 248 | 30 | 14 | 16 | 1109.06 |
| top_cross_family_plus_13a_14a_15a_16a | 248 | 30 | 14 | 16 | 1109.06 |
| rare_modules_only | 248 | 30 | 14 | 16 | 1109.06 |
| phase16a_only | 248 | 30 | 14 | 16 | 1109.06 |
| diversifier_modules_all | 248 | 30 | 14 | 16 | 1109.06 |
| greedy_low_correlation_with_phase16a | 248 | 30 | 14 | 16 | 1109.06 |
| weak_regime_focused_mix | 248 | 30 | 14 | 16 | 1109.06 |

## Portfolio Results

| Set | Mode | Net | Active days | Max DD | Avg corr | Best-day conc | Best-trade conc | Positive folds | Label | Status |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| greedy_low_correlation_with_phase16a | max_one_trade_per_session | 4790.03 | 242 | -1576.45 | 0.071 | 0.155 | 0.155 | 0.667 | portfolio_e_positive_but_concentrated | phase16a_reduces_concentration |
| portfolio_d_best_plus_phase16a | max_one_trade_per_session | 3676.28 | 246 | -2585.66 | 0.101 | 0.202 | 0.202 | 0.500 | portfolio_e_positive_but_concentrated | phase16a_reduces_concentration |
| weak_regime_focused_mix | max_one_trade_per_session | 3443.45 | 105 | -505.29 | 0.690 | 0.263 | 0.263 | 0.833 | portfolio_e_improves_rare_module_contribution_needs_review | phase16a_improves_weak_regime_coverage |
| rare_modules_only | max_one_trade_per_session | 2419.08 | 187 | -1784.40 | 0.185 | 0.374 | 0.374 | 0.500 | portfolio_e_positive_but_concentrated | phase16a_reduces_concentration |
| top_cross_family_plus_13a_14a_15a_16a | max_one_trade_per_session | 2414.65 | 247 | -1564.49 | 0.130 | 0.257 | 0.257 | 0.500 | portfolio_e_positive_but_concentrated | phase16a_reduces_concentration |
| scheduler_d_best_reconstructed | max_one_trade_per_session | 1538.95 | 237 | -2848.96 | 0.098 | 0.377 | 0.377 | 0.500 | portfolio_e_positive_but_concentrated | portfolio_still_nontradable |
| scheduler_d_best_plus_phase16a | max_one_trade_per_session | 1537.15 | 238 | -2903.77 | 0.130 | 0.378 | 0.378 | 0.500 | portfolio_e_positive_but_concentrated | portfolio_still_nontradable |
| diversifier_modules_all | max_one_trade_per_session | 1231.09 | 218 | -1362.95 | 0.176 | 0.504 | 0.504 | 0.500 | portfolio_e_positive_but_concentrated | portfolio_still_nontradable |
| phase16a_only | max_one_trade_per_session | 356.91 | 30 | -435.92 | 0.556 | 1.012 | 1.012 | 0.667 | portfolio_e_positive_but_concentrated | portfolio_still_nontradable |
| greedy_low_correlation_with_phase16a | one_trade_at_a_time_chronological | 9823.73 | 242 | -1812.50 | 0.071 | 0.150 | 0.092 | 0.833 | portfolio_e_positive_but_concentrated | phase16a_reduces_correlation |
| portfolio_d_best_plus_phase16a | one_trade_at_a_time_chronological | 8189.06 | 246 | -1944.18 | 0.101 | 0.114 | 0.091 | 0.667 | portfolio_e_positive_but_concentrated | phase16a_reduces_concentration |
| top_cross_family_plus_13a_14a_15a_16a | one_trade_at_a_time_chronological | 6877.51 | 247 | -1670.81 | 0.130 | 0.206 | 0.132 | 0.667 | portfolio_e_positive_but_concentrated | portfolio_still_nontradable |
| scheduler_d_best_plus_phase16a | one_trade_at_a_time_chronological | 5329.11 | 238 | -2422.81 | 0.130 | 0.161 | 0.109 | 0.500 | portfolio_e_positive_but_concentrated | portfolio_still_nontradable |
| scheduler_d_best_reconstructed | one_trade_at_a_time_chronological | 5190.42 | 237 | -2170.36 | 0.098 | 0.142 | 0.112 | 0.500 | portfolio_e_positive_but_concentrated | portfolio_still_nontradable |
| rare_modules_only | one_trade_at_a_time_chronological | 3481.62 | 187 | -2475.04 | 0.185 | 0.404 | 0.260 | 0.500 | portfolio_e_positive_but_concentrated | portfolio_still_nontradable |
| diversifier_modules_all | one_trade_at_a_time_chronological | 2210.65 | 218 | -2003.77 | 0.176 | 0.407 | 0.281 | 0.333 | portfolio_e_positive_but_concentrated | portfolio_still_nontradable |
| phase16a_only | one_trade_at_a_time_chronological | 64.49 | 30 | -571.64 | 0.556 | 5.602 | 5.602 | 0.500 | portfolio_e_positive_but_concentrated | portfolio_still_nontradable |
| weak_regime_focused_mix | one_trade_at_a_time_chronological | -4194.34 | 105 | -5034.89 | 0.690 | 1.000 | 1.000 | 0.167 | portfolio_e_failed_negative | no_portfolio_benefit |
| weak_regime_focused_mix | raw_sum_diagnostic | 23450.63 | 105 | -3811.38 | 0.690 | 0.309 | 0.039 | 0.667 | portfolio_e_positive_but_concentrated | portfolio_still_nontradable |
| rare_modules_only | raw_sum_diagnostic | 15258.34 | 187 | -3254.17 | 0.185 | 0.152 | 0.059 | 0.667 | portfolio_e_positive_but_concentrated | phase16a_reduces_concentration |
| top_cross_family_plus_13a_14a_15a_16a | raw_sum_diagnostic | 9608.05 | 247 | -3349.91 | 0.130 | 0.130 | 0.094 | 0.667 | portfolio_e_positive_but_concentrated | phase16a_reduces_concentration |
| portfolio_d_best_plus_phase16a | raw_sum_diagnostic | 8577.70 | 246 | -2611.45 | 0.101 | 0.146 | 0.086 | 0.500 | portfolio_e_positive_but_concentrated | phase16a_reduces_concentration |
| greedy_low_correlation_with_phase16a | raw_sum_diagnostic | 8000.22 | 242 | -1895.40 | 0.071 | 0.152 | 0.113 | 0.833 | portfolio_e_improves_rare_module_contribution_needs_review | phase16a_improves_weak_regime_coverage |
| scheduler_d_best_plus_phase16a | raw_sum_diagnostic | 7669.89 | 238 | -3937.89 | 0.130 | 0.276 | 0.081 | 0.500 | portfolio_e_positive_but_concentrated | portfolio_still_nontradable |
| scheduler_d_best_reconstructed | raw_sum_diagnostic | 6560.83 | 237 | -3432.74 | 0.098 | 0.275 | 0.095 | 0.500 | portfolio_e_positive_but_concentrated | portfolio_still_nontradable |
| diversifier_modules_all | raw_sum_diagnostic | 4928.14 | 218 | -3519.78 | 0.176 | 0.253 | 0.126 | 0.500 | portfolio_e_positive_but_concentrated | phase16a_reduces_concentration |
| phase16a_only | raw_sum_diagnostic | 1109.06 | 30 | -1072.34 | 0.556 | 0.641 | 0.326 | 0.667 | portfolio_e_positive_but_concentrated | portfolio_still_nontradable |

## Interpretation

Phase 16A and rare modules remain research-only. Portfolio Audit E reports diagnostic playbook contribution only; no portfolio is paper-trading approved and no live-trading functionality is added.
