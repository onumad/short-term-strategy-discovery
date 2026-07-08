# Playbook Framework C — Evaluation Config, Labels, and Reporting Alignment

Research/simulation only. No live trading, broker adapters, order routing, webhooks, credential storage, automated execution, or LLM-driven trade decisions.

## Purpose

This additive framework aligns future phases with the diversified playbook direction. It does not generate new signals, alter historical candidate results, change official gates, promote candidates, or approve paper trading.

## Config Sections Created

- module_activity_gate
- playbook_activity_gate
- rare_setup_activity_gate
- signal_score_components
- tradability_score_components
- portfolio_score_components
- future_candidate_output_fields
- official_promotion_gates_reference

## Activity Gate Alignment

Individual modules do not need to trade daily. Rare setup low activity does not force `signal_evidence_status` to `no_signal`; it can still force `tradability_status` to `not_tradable_low_activity`. The combined playbook remains responsible for regular opportunity.

## Reporting Language

Use `positive research signal but not tradable`, `rare setup research signal`, `tradability failed due to low activity`, `blocked by concentration/fold stability`, and `no paper trading approved` where appropriate.

## Existing Registry Compatibility

Existing research signal registry rows classified without changing old labels: 37.

## Official Gates And Paper Trading

Official gates changed: `false`.
Paper trading approved: `false`.

## Next Recommendation

- Next action: `phase13a_final_acceptance_then_module_registry_update`
- Rationale: Playbook evaluation config now separates module signal evidence, tradability, and portfolio contribution while preserving official gates.

## Output Field Defaults

Future candidate output fields: module_id, signal_evidence_status, tradability_status, research_track, market_condition, module_family, portfolio_role, plain_english_rule, official_gates_passed, paper_trading_approved, portfolio_contribution_status.
`paper_trading_approved` defaults to `false`.
