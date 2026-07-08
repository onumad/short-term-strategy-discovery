# Playbook Module Registry - Phase 14A Addendum

Research/simulation only. No live trading, broker adapters, order routing, webhooks, credential storage, automated execution, or LLM-driven trade decisions.

## Purpose

This registry maps parked research signals into playbook module fields for Portfolio Audit C. It preserves official gates and paper-trading blocks.

## Counts

- Total module rows: `41`
- Phase 14A rows: `2`
- Phase 14A diversifier modules: `2`

## Phase 14A Modules

| Module | Market condition | Family | Portfolio role | Evidence | Tradability | Official gates | Paper trading |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `MNQ_14a_prior_rth_midpoint_rejection_from_level_short_close_confirm_fill_next_open_structure_target_time_exit` | prior_level_interaction | prior_level_reaction | diversifier_module | positive_research_signal | not_tradable_concentrated | false | false |
| `MNQ_14a_prior_rth_close_rejection_from_level_long_two_bar_confirm_fill_next_open_structure_target_time_exit` | prior_level_interaction | prior_level_reaction | diversifier_module | positive_research_signal | not_tradable_concentrated | false | false |

## Watchlist Label Hygiene

No Phase 14A `phase14a_watchlist_needs_more_history` row is marked review, paper-approved, or included as a true watchlist module in this update.

## Next Action

`portfolio_audit_c_with_phase14a_prior_level_modules` - Phase 14A added positive uncorrelated prior-RTH midpoint reaction modules to the playbook registry; test whether they improve combined playbook stability.
