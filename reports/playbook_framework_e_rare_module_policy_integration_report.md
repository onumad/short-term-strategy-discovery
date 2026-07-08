# Playbook Framework E — Rare Module Policy Integration

Research/simulation only. No live trading, broker adapters, order routing, webhooks, credential storage, automated execution, or LLM-driven trade decisions.

This is additive/config/reporting policy integration only. It generated no new signals, ran no strategy searches, changed no existing candidate results, changed no official promotion gates, promoted no candidates, and approved no paper or live trading.

## Official gates and approvals

- official_gates_changed: `false`
- paper_trading_approved: `false`
- live_trading_approved: `false`
- No official paper-review threshold is loosened.
- Rare module track is research-only.

## Rare module definition

A rare module is a specialized module with positive research evidence that may be low activity and may have low_activity_not_fully_interpretable fold adequacy. It is not tradable by itself, but may contribute as a rare setup diversifier inside the playbook after portfolio contribution is measured.

## Required rare-module fields

rare_module_track_enabled, rare_module_validation_class, fold_adequacy_status, fold_interpretability, rare_module_registration_decision, rare_module_revisit_condition, rare_module_portfolio_role, module_level_fold_warning, playbook_level_contribution_status

## Rare-module validation classes

- rare_signal_insufficient_evidence: Rare/sparse module without enough positive stress, validation, holdout, and walk-forward stress evidence.
- rare_positive_research_signal: Rare positive research signal with positive research evidence but not enough module-level activity for tradability.
- rare_uncorrelated_diversifier_candidate: Rare positive research signal with low average correlation and possible playbook diversification value.
- rare_priority_for_more_data: Rare setup that should be revisited after materially more history before tradability/review consideration.
- rare_rejected_negative_or_unstable: Rare/watchlist-labeled row blocked by negative, unstable, high-correlation, or misleading evidence.

## Rare-module registry behavior

Rare modules may be added only when stress_pnl, validation_pnl, holdout_pnl, and walk_forward_stress_pnl are all positive, average correlation to registry is <= 0.35, and paper_trading_approved is false.
Registered rare modules must remain research_track=`rare_setup_research_signal`, tradability_status=`not_tradable_low_activity`, paper_trading_approved=`false`, and official_gates_passed=`false`.

## Portfolio-audit rare-module behavior

- Report whether rare modules add active days.
- Report whether rare modules improve weak folds.
- Report whether rare modules reduce correlation.
- Report whether rare modules increase overlap or drawdown.
- Include rare modules as diversifier candidates and report rare-module contribution separately.
- Avoid treating low activity as no_signal.
- Still block paper-review unless official gates pass at playbook/review level.

## Fold adequacy behavior

- Module-level folds with too few trades should be marked low_activity_not_fully_interpretable.
- Low fold adequacy does not erase positive signal evidence.
- Low fold adequacy blocks tradability/review unless later playbook-level evidence supports review.
- Portfolio-level fold stability remains required for playbook review.

## Watchlist hygiene

Future reports must not treat watchlist_needs_more_history labels as review approval unless positive stress/validation/holdout/walk-forward stress evidence exists, fold adequacy is interpretable or explicitly rare-track compatible, and paper_trading_approved remains false.

## Future reporting language

- Use: rare positive research signal
- Use: rare setup diversifier
- Use: low activity / fold result not fully interpretable
- Use: not tradable by itself
- Use: portfolio contribution required before further review
- Use: paper trading not approved
- Avoid unqualified: watchlist, approved, tradable, passed unless official gates passed.

## Phase 16A rare modules in registry

- phase16a_rare_modules_present_in_registry: `3`
- all_paper_trading_approved_false: `true`
- all_official_gates_passed_false: `true`

## Registry schema additions

rare_module_track_enabled, rare_module_validation_class, fold_adequacy_status, fold_interpretability, rare_module_registration_decision, rare_module_revisit_condition, rare_module_portfolio_role, module_level_fold_warning, playbook_level_contribution_status

## Recommended next action

- next_action: `portfolio_audit_e_with_phase16a_rare_modules`
- rationale: Rare-module policy is integrated; next audit should test whether Phase 16A rare high-vol mixed modules improve playbook-level activity, folds, concentration, and weak-regime coverage.
- official_gates_changed: `false`
- paper_trading_approved: `false`
- rare_module_track_enabled: `true`
