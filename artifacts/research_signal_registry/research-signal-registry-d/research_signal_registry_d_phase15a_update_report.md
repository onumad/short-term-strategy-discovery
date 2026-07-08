# Research Signal Registry D - Phase 15A Update

Research/simulation only. No live trading, broker adapters, order routing, webhooks, credential storage, automated execution, or LLM-driven trade decisions.

## Scope

This additive update adds accepted Phase 15A positive uncorrelated trend/power continuation research signals to the research signal registry and playbook module registry for Portfolio Audit D. It does not generate new signals, rerun Phase 15A, change candidate results, change official promotion gates, promote candidates, or approve paper trading.

## Inputs Used

- outputs/research_signal_registry.csv / .json
- outputs/playbook_module_registry.csv / .json
- outputs/playbook_module_registry_schema.json
- outputs/playbook_module_taxonomy.json
- outputs/phase15a_candidate_results.csv
- outputs/phase15a_correlation_to_registry.csv
- outputs/phase15a_correlation_to_playbook.csv
- outputs/phase15a_gap_coverage_summary.csv
- outputs/phase15a_next_action_recommendation.json
- reports/phase15a_trend_power_continuation_scout_report.md

## Phase 15A Rows Added

- Rows added: `3`
- Research signal registry rows before/after: `41` -> `44`
- Playbook module registry rows before/after: `41` -> `44`
- Classification applied: `positive_research_signal`, `not_tradable_low_activity`, `rare_setup_research_signal`, `diversifier_module`.
- Paper trading approved: `false`.
- Official gates passed: `false`.
- Top Phase 15A candidate included: `MNQ_15a_trend_day_late_pullback_continuation_short_ema20_pullback_resume_close_confirm_fill_next_open_hard_stop_time_exit`.

| Rank | Candidate | Source family | Market condition | Module family | Portfolio role | Net | Stress | Validation | Holdout | WF stress | Avg registry corr | Incremental gap days |
| ---: | --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | `MNQ_15a_trend_day_late_pullback_continuation_short_ema20_pullback_resume_close_confirm_fill_next_open_hard_stop_time_exit` | trend_day_late_pullback_continuation | trend_day | trend_continuation | diversifier_module | 959.11 | 905.11 | 166.84 | 340.21 | 855.91 | 0.121 | 0 |
| 6 | `MNQ_15a_power_hour_continuation_long_power_range_breakout_continuation_close_confirm_fill_next_open_hard_stop_time_exit` | power_hour_continuation | power_hour_expansion | trend_continuation | diversifier_module | 150.00 | 100.00 | 94.55 | 312.84 | 491.50 | 0.037 | 0 |
| 7 | `MNQ_15a_power_hour_continuation_long_power_range_edge_retest_resume_close_confirm_fill_next_open_hard_stop_time_exit` | power_hour_continuation | power_hour_expansion | trend_continuation | diversifier_module | 150.00 | 100.00 | 94.55 | 312.84 | 491.50 | 0.037 | 0 |

## Gap-Coverage Caveat

Phase 15A positive candidates had incremental_gap_days_covered = 0; record them as uncorrelated diversifier modules, not confirmed gap-filling modules.

## Recommendation

- Next action: `portfolio_audit_d_with_phase15a_trend_power_modules`
- Rationale: Phase 15A added positive uncorrelated trend/power continuation modules to the playbook registry; test whether they improve combined playbook stability despite limited target-gap coverage.
- Official gates changed: `false`
- Paper trading approved: `false`
