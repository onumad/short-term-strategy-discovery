# Research Signal Registry E - Phase 16A Rare Module Update

Research/simulation only. No live trading, broker adapters, order routing, webhooks, credential storage, automated execution, or LLM-driven trade decisions.

## Scope

This additive update adds the three Phase 16A rows approved by the Rare Module Validation Track for `registration_decision=add_to_registry_as_rare_setup_diversifier` to the research signal registry and playbook module registry. It does not generate new signals, rerun Phase 16A, rerun the Rare Module Validation Track, change candidate results, change official promotion gates, promote candidates, or approve paper trading.

## Inputs Used

- outputs/research_signal_registry.csv / .json
- outputs/research_signal_registry_next_action_recommendation.json
- outputs/playbook_module_registry.csv / .json
- outputs/playbook_module_registry_schema.json
- outputs/playbook_module_taxonomy.json
- outputs/phase16a_candidate_results.csv
- outputs/phase16a_correlation_to_registry.csv
- outputs/phase16a_correlation_to_playbook.csv
- outputs/phase16a_gap_coverage_summary.csv
- outputs/phase16a_fold_view_summary.csv
- outputs/phase16a_module_fold_adequacy.csv
- outputs/phase16a_next_action_recommendation.json
- reports/phase16a_high_vol_mixed_regime_scout_report.md
- outputs/rare_module_validation_track_phase16a_candidates.csv
- outputs/rare_module_validation_track_adequacy_summary.csv
- outputs/rare_module_validation_track_registration_decisions.csv
- outputs/rare_module_validation_track_policy.json
- outputs/rare_module_validation_track_next_action_recommendation.json
- reports/rare_module_validation_track_review_report.md

## Phase 16A Rows Added

- Rows added: `3`
- Research signal registry rows before/after: `44` -> `47`
- Playbook module registry rows before/after: `44` -> `47`
- Classification applied: `positive_research_signal`, `not_tradable_low_activity`, `rare_setup_research_signal`, `diversifier_module`, `low_activity_not_fully_interpretable`.
- Paper trading approved: `false`.
- Official gates passed: `false`.
- Top Phase 16A rule: On a broad high-volatility mixed morning, buy the late lunch-range breakout after close confirmation, filled at the next bar open.

| Rank | Candidate | Source family | Market condition | Module family | Portfolio role | Net | Stress | Validation | Holdout | WF stress | Avg registry corr | Trades | Fold adequacy |
| ---: | --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 1 | `MNQ_16a_high_vol_mixed_late_resolution_breakout_long_broad_high_vol_mixed_close_confirm_fill_next_open_structure_target_time_exit` | high_vol_mixed_late_resolution_breakout | high_volatility_day | range_expansion | diversifier_module | 516.62 | 486.62 | 67.03 | 703.28 | 568.28 | 0.071 | 30 | low_activity_not_fully_interpretable |
| 2 | `MNQ_16a_high_vol_mixed_late_resolution_breakout_long_broad_high_vol_mixed_close_confirm_fill_next_open_hard_stop_time_exit` | high_vol_mixed_late_resolution_breakout | high_volatility_day | range_expansion | diversifier_module | 356.91 | 326.91 | 284.75 | 415.60 | 498.32 | 0.062 | 30 | low_activity_not_fully_interpretable |
| 12 | `MNQ_16a_high_vol_mixed_late_resolution_breakout_long_broad_high_vol_mixed_two_bar_confirm_fill_next_open_hard_stop_time_exit` | high_vol_mixed_late_resolution_breakout | high_volatility_day | range_expansion | diversifier_module | 235.53 | 208.53 | 117.36 | 181.91 | 91.45 | 0.081 | 27 | low_activity_not_fully_interpretable |

## Rare-Module Caveat

Phase 16A rare modules are low-activity and fold adequacy is not fully interpretable. They are accepted only as rare setup diversifier research modules, not as watchlist, paper-review, or paper-trading candidates.

## Watchlist Hygiene

Phase 16A watchlist labels are not registry watchlist/review approval; all five watchlist-labeled rows from the Rare Module Validation Track remain excluded, are not review_packet_candidate, and are not paper-approved.

| Excluded watchlist candidate | Hygiene status | Registration decision |
| --- | --- | --- |
| `MNQ_16a_high_vol_mixed_late_resolution_breakout_long_strict_high_vol_mixed_close_confirm_fill_next_open_structure_target_time_exit` | blocked_from_registry_watchlist: zero_or_near_zero_trades; nonpositive_validation; high_max_registry_correlation; insufficient_fold_adequacy | reject_from_registry |
| `MNQ_16a_high_vol_mixed_late_resolution_breakout_long_broad_high_vol_mixed_two_bar_confirm_fill_next_open_structure_target_time_exit` | blocked_from_registry_watchlist: nonpositive_walk_forward_stress; high_max_registry_correlation; insufficient_fold_adequacy | reject_from_registry |
| `MNQ_16a_high_vol_mixed_midpoint_reclaim_long_broad_high_vol_mixed_two_bar_confirm_fill_next_open_hard_stop_time_exit` | blocked_from_registry_watchlist: nonpositive_holdout; insufficient_fold_adequacy | reject_from_registry |
| `MNQ_16a_high_vol_mixed_midpoint_reclaim_long_strict_high_vol_mixed_close_confirm_fill_next_open_hard_stop_time_exit` | blocked_from_registry_watchlist: zero_or_near_zero_trades; nonpositive_validation; nonpositive_holdout; nonpositive_walk_forward_stress; insufficient_fold_adequacy | reject_from_registry |
| `MNQ_16a_high_vol_mixed_midpoint_reclaim_long_broad_high_vol_mixed_two_bar_confirm_fill_next_open_structure_target_time_exit` | blocked_from_registry_watchlist: nonpositive_holdout; insufficient_fold_adequacy | reject_from_registry |

## Recommendation

- Next action: `playbook_framework_e_rare_module_policy_integration`
- Rationale: Phase 16A rare high-vol mixed modules were added as rare setup diversifiers; integrate rare-module policy into future playbook evaluation before Portfolio Audit E.
- Official gates changed: `false`
- Paper trading approved: `false`
- Rare module track enabled: `true`
