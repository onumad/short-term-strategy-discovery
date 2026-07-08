# Research Signal Registry B - Phase 13A Update

Research/simulation only. No live trading, broker adapters, order routing, webhooks, credential storage, automated execution, or LLM-driven trade decisions.

## Scope

This additive update adds accepted Phase 13A positive uncorrelated research signals to the research signal registry and playbook module registry for Portfolio Audit B. It does not generate new signals, rerun Phase 13A, change candidate results, change official promotion gates, promote candidates, or approve paper trading.

## Inputs Used

- outputs/research_signal_registry.csv / .json
- outputs/phase13a_candidate_results.csv
- outputs/phase13a_correlation_to_registry.csv
- outputs/phase13a_correlation_to_portfolios.csv
- reports/phase13a_uncorrelated_family_scout_report.md

## Phase 13A Rows Added

- Rows added: `2`
- Research signal registry rows before/after: `37` -> `39`
- Playbook module registry rows after: `39`
- Classification applied to both rows: `positive_research_signal`, `not_tradable_concentrated`, `parked_research_signal`, `prior_level_interaction`, `breakout`, `diversifier_module`.
- Plain-English rule: Long breakout above prior RTH high after close confirmation, filled at next bar open.
- Paper trading approved: `false`.
- Official gates passed: `false`.

| Rank | Candidate | Portfolio role | Net | Stress | Validation | Holdout | WF stress | Avg registry corr | Max registry corr |
| ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | `MNQ_13a_prior_rth_high_low_breakout_long_close_confirm_fill_next_open_structure_target_time_exit` | diversifier_module | 883.00 | 760.00 | 1407.83 | 69.79 | 675.08 | 0.079 | 0.246 |
| 2 | `MNQ_13a_prior_rth_high_low_breakout_long_close_confirm_fill_next_open_hard_stop_time_exit` | diversifier_module | 879.00 | 756.00 | 1407.83 | 100.29 | 705.58 | 0.079 | 0.248 |

## NaN Cleanup

- Prior-RTH source windows are represented as `prior_rth_session`; JSON outputs are written with strict `allow_nan=false`.

## Recommendation

- Next action: `portfolio_audit_b_with_phase13a_uncorrelated_modules`
- Rationale: Phase 13A added positive uncorrelated prior-RTH breakout modules to the playbook registry; test whether they improve combined playbook stability.
- Official gates changed: `false`
- Paper trading approved: `false`
