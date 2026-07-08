# Playbook Module Registry - Phase 13A Addendum

Research/simulation only. No live trading, broker adapters, order routing, webhooks, credential storage, automated execution, or LLM-driven trade decisions.

## Purpose

This registry maps parked research signals into playbook module fields for Portfolio Audit B. It preserves official gates and paper-trading blocks.

## Counts

- Total module rows: `39`
- Phase 13A rows: `2`
- Phase 13A diversifier modules: `2`

## Phase 13A Modules

| Module | Market condition | Family | Portfolio role | Evidence | Tradability | Official gates | Paper trading |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `MNQ_13a_prior_rth_high_low_breakout_long_close_confirm_fill_next_open_hard_stop_time_exit` | prior_level_interaction | breakout | diversifier_module | positive_research_signal | not_tradable_concentrated | false | false |
| `MNQ_13a_prior_rth_high_low_breakout_long_close_confirm_fill_next_open_structure_target_time_exit` | prior_level_interaction | breakout | diversifier_module | positive_research_signal | not_tradable_concentrated | false | false |

## Next Action

`portfolio_audit_b_with_phase13a_uncorrelated_modules` - Phase 13A added positive uncorrelated prior-RTH breakout modules to the playbook registry; test whether they improve combined playbook stability.
