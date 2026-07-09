# Playbook Research Objective

## 1. New Objective

Build and validate the deterministic playbook that will anchor a production-grade hybrid ML/LLM automated intraday futures trading bot. No individual setup must trade daily; the combined playbook must provide enough regular opportunities while preserving strict research-only validation.

The current authorization remains research and simulation only. Paper trading, shadow execution, and controlled live execution are later delivery stages that require explicit policy changes; research labels or gate results do not activate them automatically.

ML research may produce versioned regime classifications, rankings, and signal inputs. LLM research may produce schema-constrained analysis and proposals. In later stages, deterministic policy and independent risk controls must validate every proposed action, and model processes must remain isolated from broker credentials and direct order routing.

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

- Current stage: research and simulation only.
- No broker or live-execution functionality during the current stage.
- No model may directly authorize orders, sizing, risk overrides, or broker actions.
- ML outputs and LLM proposals must be versioned, schema-validated where applicable, and evaluated without lookahead.
- Passing official gates does not authorize paper trading; stage promotion requires an explicit project policy change.
- No loosening official gates without an explicit project policy change.
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
F. Build point-in-time features and replay-derived labels with unknown coverage preserved as null.
G. Train ML baselines only after target-readiness gates pass.
H. Validate calibration, drift, abstention, and deterministic counterfactual playbook impact before approving a versioned score as a non-authoritative signal input.
I. Evaluate bounded LLM tasks only under versioned schemas and outside the order-authority path.

All research releases must record an explicit authorization stage, source revision, schema versions, input lineage or content hashes, and immutable identifiers. The default authorization stage is `research`; model and LLM releases default to not approved as signal inputs.

## Framework E rare-module policy note

Future registry and portfolio-audit reports should treat Phase 16A-style rows as rare positive research signal / rare setup diversifier candidates only when rare-module evidence rules pass. Low activity / fold result not fully interpretable does not convert positive signal evidence to no_signal, but the module remains not tradable by itself and paper trading not approved. Portfolio contribution required before further review; official gates unchanged.

## Scheduler F rare-module scheduler policy note

Scheduler E found that rare modules should remain tracked as research/playbook registry signals but should be excluded from default active scheduler candidate sets until more evidence/data is available. Rare modules may be included only in explicit rare-module or diversifier audits. Low activity does not erase signal evidence and Phase 16A rare modules are not deleted or rejected as no_signal, but low activity still blocks tradability. Official gates remain unchanged and paper trading remains not approved.
