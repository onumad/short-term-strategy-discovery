# Playbook Research Objective

## 1. New Objective

Build a diversified playbook of specialized deterministic MNQ intraday setups. No individual setup must trade daily; the combined playbook must provide enough regular opportunities while preserving strict research-only validation.

## 2. Module-Level Evaluation

Individual modules should be evaluated on:

- signal evidence
- stress PnL
- validation and holdout
- MFE/MAE behavior
- concentration
- fold stability
- correlation to existing modules
- plain-English market logic
- whether it belongs to a rare setup track or regular-practice track

Low activity is no longer an automatic research failure when a module has evidence, explains a specific market condition, and diversifies the playbook. Low activity still blocks paper-review unless official gates pass.

## 3. Playbook-Level Evaluation

The combined playbook should be evaluated on:

- total active days
- total opportunities per day
- fold stability
- drawdown
- day/trade concentration
- correlation between modules
- overlap between trades
- contribution by module/family
- whether the playbook improves over individual modules

The playbook, not every individual module, is responsible for regular opportunity.

## 4. Two-Tier Labels

Preserve the registry distinction between signal evidence and tradability/practice readiness.

signal_evidence_status:

- no_signal
- weak_research_signal
- positive_research_signal
- real_but_nontradable_signal
- priority_research_signal_for_more_data

tradability_status:

- not_tradable_negative
- not_tradable_low_activity
- not_tradable_concentrated
- not_tradable_fold_unstable
- watchlist_needs_more_history
- review_packet_candidate

research_track:

- regular_practice_candidate
- rare_setup_research_signal
- parked_research_signal
- priority_research_signal_for_more_data

## 5. Module Taxonomy

market_condition:

- trend_day
- range_day
- reversal_day
- breakout_day
- failed_breakout_day
- low_volatility_day
- high_volatility_day
- midday_range
- power_hour_expansion
- prior_level_interaction

module_family:

- breakout
- fade
- pullback_continuation
- sweep_reversal
- range_expansion
- range_reversion
- trend_continuation
- volatility_expansion
- prior_level_reaction

portfolio_role:

- core_module
- rare_setup_module
- diversifier_module
- parked_module
- candidate_for_more_data

## 6. Guardrails

- Research/simulation only.
- No broker/live functionality.
- No LLM-driven trade decisions.
- No paper-trading approval unless official gates pass.
- No loosening official gates.
- No post-hoc date/session exclusions.
- No weekday rescue filters unless structurally justified.
- Deterministic, serializable rules only.

## 7. Future Workflow

Future phases should follow this sequence:

A. Scout specialized module.
B. Classify signal evidence and tradability separately.
C. Add promising module to research signal registry.
D. Test contribution in portfolio/playbook audit.
E. Only then consider targeted retest or review packet.

## Framework E rare-module policy note

Future registry and portfolio-audit reports should treat Phase 16A-style rows as rare positive research signal / rare setup diversifier candidates only when rare-module evidence rules pass. Low activity / fold result not fully interpretable does not convert positive signal evidence to no_signal, but the module remains not tradable by itself and paper trading not approved. Portfolio contribution required before further review; official gates unchanged.
