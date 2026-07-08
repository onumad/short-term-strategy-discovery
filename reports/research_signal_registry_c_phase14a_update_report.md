# Research Signal Registry C - Phase 14A Update

Research/simulation only. No live trading, broker adapters, order routing, webhooks, credential storage, automated execution, or LLM-driven trade decisions.

## Scope

This additive update adds accepted Phase 14A positive uncorrelated prior-level reaction research signals to the research signal registry and playbook module registry for Portfolio Audit C. It does not generate new signals, rerun Phase 14A, change candidate results, change official promotion gates, promote candidates, or approve paper trading.

## Inputs Used

- outputs/research_signal_registry.csv / .json
- outputs/playbook_module_registry.csv / .json
- outputs/playbook_module_registry_schema.json
- outputs/playbook_module_taxonomy.json
- outputs/phase14a_candidate_results.csv
- outputs/phase14a_correlation_to_registry.csv
- outputs/phase14a_correlation_to_playbook.csv
- outputs/phase14a_gap_coverage_summary.csv
- outputs/phase14a_next_action_recommendation.json
- reports/phase14a_prior_level_reaction_scout_report.md

## Phase 14A Rows Added

- Rows added: `2`
- Research signal registry rows before/after: `39` -> `41`
- Playbook module registry rows before/after: `39` -> `41`
- Classification applied to both rows: `positive_research_signal`, `not_tradable_concentrated`, `parked_research_signal`, `prior_level_interaction`, `prior_level_reaction`, `diversifier_module`.
- Plain-English rule: Short rejection from prior RTH midpoint after close-confirmed failure to hold above the level, filled at next bar open.
- Paper trading approved: `false`.
- Official gates passed: `false`.

| Rank | Candidate | Portfolio role | Net | Stress | Validation | Holdout | WF stress | Avg registry corr | Max registry corr |
| ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 4 | `MNQ_14a_prior_rth_midpoint_rejection_from_level_short_close_confirm_fill_next_open_structure_target_time_exit` | diversifier_module | 418.83 | 350.83 | 85.36 | 734.92 | 594.39 | 0.061 | 0.279 |
| 11 | `MNQ_14a_prior_rth_close_rejection_from_level_long_two_bar_confirm_fill_next_open_structure_target_time_exit` | diversifier_module | 379.14 | 306.14 | 161.41 | 437.23 | 122.36 | 0.103 | 0.268 |

## Watchlist Label Hygiene

Phase 14A rows labeled `phase14a_watchlist_needs_more_history` were not added to the registry and were not treated as review, watchlist, or paper-approved modules. Under the requested hygiene rule, Phase 14A watchlist rows require positive stress, validation, holdout, and walk-forward stress PnL before being treated as true watchlist modules; no such rows were promoted or approved here.

## Recommendation

- Next action: `portfolio_audit_c_with_phase14a_prior_level_modules`
- Rationale: Phase 14A added positive uncorrelated prior-RTH midpoint reaction modules to the playbook registry; test whether they improve combined playbook stability.
- Official gates changed: `false`
- Paper trading approved: `false`
