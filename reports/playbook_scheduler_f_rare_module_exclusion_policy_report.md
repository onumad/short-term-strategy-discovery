# Playbook Scheduler F — Rare Module Scheduler Exclusion Policy

Research/simulation only. No live trading, broker adapters, order routing, webhooks, credential storage, automated execution, or LLM-driven trade decisions.

This is a policy/configuration artifact only. It generated no new signals, ran no strategy searches, changed no historical candidate results, changed no official promotion gates, promoted no candidates, and approved no paper or live trading.

## Policy summary

- Rare modules remain in the research and playbook registries.
- Rare modules are registry-only and excluded from default active scheduler candidate sets.
- Rare modules may be included only in explicit rare-module or diversifier audits.
- Phase 16A rare modules are not deleted and are not rejected as no_signal.
- Low activity does not erase signal evidence, but low activity still blocks tradability.

## Default scheduler policy

- default_include_rare_modules_in_scheduler: `false`
- rare_modules_allowed_in_explicit_audits: `true`
- rare_module_default_scheduler_status: `registry_only_excluded_from_default_scheduler`
- default_scheduler_module_count: `16`
- current_default_admitted_module_count: `0`
- excluded_rare_module_count: `25`
- The compatibility universe is historical research replay only; it does not imply current admission or tradability.
- no_trade_is_valid: `true`
- minimum_trades_per_day: `null`

## Rare module registry summary

- rare_module_count: `25`
- phase16a_rare_module_count: `3`
- all_rare_modules_registry_only_by_default: `true`
- all_rare_modules_paper_trading_false: `true`
- all_rare_modules_official_gates_false: `true`

## Exception rules

- Allowed only with explicit context: `explicit_rare_module_audit`
- Allowed only with explicit context: `explicit_diversifier_audit`
- Allowed only with explicit context: `rare_module_more_data_review`
- Explicit flag required: `include_rare_modules_in_scheduler=true`
- Without that flag, rare modules remain excluded from active scheduler candidates.
- Any explicit rare/diversifier audit must keep paper_trading_approved=false and official_gates_changed=false.

## Future audit requirements

- Require more evidence before any default scheduler inclusion is reconsidered.
- Keep signal evidence separate from tradability/practice readiness.
- Report rare-module active days, trades, PnL, overlap, drawdown, and fold effects separately.
- Verify Phase 16A rare modules remain registered, not deleted, and not mapped to no_signal solely because of low activity.

## Official gates and approvals

- official_gates_changed: `false`
- paper_trading_approved: `false`
- live_trading_approved: `false`

## Recommended next action

- next_action: `phase17a_next_gap_module_scout_without_rare_scheduler_inclusion`
- rationale: Rare modules remain tracked as research signals but should be excluded from default scheduler construction until more evidence is available.
- official_gates_changed: `false`
- paper_trading_approved: `false`
- default_include_rare_modules_in_scheduler: `false`
