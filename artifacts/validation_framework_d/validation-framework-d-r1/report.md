# Validation Framework D — Standardize Playbook Folds

Research/simulation only. No live trading, broker adapters, order routing, webhooks, credential storage, automated execution, or LLM-driven trade decisions.

This is an additive validation-policy artifact only. It generated no new signals, ran no strategy searches, changed no candidate results, loosened no official gates, promoted no candidates, and approved no paper or live trading.

## Official gates and approvals

- official_gates_changed: `false`
- paper_trading_approved: `false`
- live_trading_approved: `false`
- No official paper-review threshold is loosened.
- Alternative fold views are diagnostic only unless explicitly promoted later by human review.

## Validation levels

### module_level_validation

- used_for: `individual specialized modules`
- may_be_sparse: `True`
- requires_fold_adequacy_before_interpreting_pass_fail: `True`
- low_activity_alone_means_no_signal: `False`
- low_activity_can_block_tradability: `True`
- required_diagnostics: `['active_days_per_fold', 'trades_per_fold', 'folds_below_min_activity', 'fold_result_interpretable', 'module_level_positive_fold_pct']`

### playbook_level_validation

- used_for: `combined module portfolios and schedulers`
- responsible_for_regular_opportunity: `True`
- required_diagnostics: `['fold_stability', 'concentration', 'drawdown', 'active_days', 'module_contribution', 'playbook_level_positive_fold_pct']`

### paper_review_validation

- strictest_level: `True`
- official_gates_changed: `False`
- paper_trading_approved_by_this_policy: `False`
- no_official_paper_review_threshold_loosened: `True`
- alternative_folds_diagnostic_unless_later_human_promoted: `True`

## Standard fold views

| fold_view | role | required_in_future_reports | diagnostic_companion_only | official_promotion_gate | adequacy_warning_required | reporting_rule |
| --- | --- | --- | --- | --- | --- | --- |
| existing_project_folds | continuity_primary_reported_view | True | False | False | False | Retained for continuity with prior research and still reported. |
| half_year_folds | diagnostic_companion_less_coarse_view | True | True | False | False | Diagnostic companion fold view; Audit C showed it may be less coarse than existing folds. |
| quarterly_folds | diagnostic_stress_view | True | True | False | True | Diagnostic stress view. It may be too sparse for rare modules, so adequacy warnings are required. |
| rolling_3_month_test_folds | excluded_from_standard_required_views | False | True | False | True | Do not make rolling 3-month folds official promotion gates; use only if explicitly requested as extra diagnostics. |
| rolling_6_month_test_folds | diagnostic_regime_sensitivity_view | True | True | False | False | Diagnostic regime-sensitivity view; not an official promotion gate. |

Quarterly folds and rolling 3-month folds are not official promotion gates.

## Rare-module fold adequacy rules

| validation_level | rule | configurable_default | diagnostic_only | effect | converts_to_no_signal | can_block_tradability |
| --- | --- | --- | --- | --- | --- | --- |
| module_level_validation | minimum_active_days_per_fold | 10 | True | fold result is low-activity / not fully interpretable below this value | False | True |
| module_level_validation | minimum_trades_per_fold | 10 | True | fold result is low-activity / not fully interpretable below this value | False | True |
| module_level_validation | report_folds_below_min_activity | True | True | report active days, trades, adequacy status, and count of sparse folds before interpreting pass/fail | False | True |

Low activity alone does not mean no signal. Low activity can still block tradability. Future reports should state when a fold result is low-activity / not fully interpretable.

## Playbook fold reporting rules

| validation_level | reporting_rule | configurable_default | required_metric |
| --- | --- | --- | --- |
| playbook_level_validation | minimum_active_days_per_fold | 30 | active_days_per_fold |
| playbook_level_validation | minimum_trades_per_fold | 30 | trades_per_fold |
| playbook_level_validation | fold_stability_and_concentration | required | fold stability, concentration, drawdown, active days, module contribution |
| paper_review_validation | official_gates_unchanged | False | official_gates_changed=false and paper_trading_approved=false |

## Future candidate output fields

validation_level, primary_fold_view, companion_fold_views, fold_adequacy_status, folds_below_min_activity, module_level_positive_fold_pct, playbook_level_positive_fold_pct, fold_design_sensitivity_flag, official_gates_passed, paper_trading_approved

## Required reporting language

- fold result is low-activity / not fully interpretable
- positive research signal but not tradable
- playbook-level fold stability failed
- alternative fold views are diagnostic only
- official gates unchanged

## Audit C evidence used

- observed_fold_views: `['calendar_year_folds', 'existing_project_folds', 'expanding_train_recent_test_style', 'half_year_folds', 'quarterly_folds', 'rolling_3_month_test_folds', 'rolling_6_month_test_folds']`
- fold_designs_with_material_sensitivity_rows: `1006`
- audit_c_policy_fold_conclusions_change_by_design: `True`
- audit_c_policy_alternative_folds_diagnostic_only: `True`

## Recommended next action

- next_action: `phase16a_targeted_regime_module_scout`
- rationale: Playbook fold policy is standardized diagnostically; next module search should target unresolved weak regimes while reporting existing, half-year, and rolling 6-month fold views.
- official_gates_changed: `false`
- paper_trading_approved: `false`
- live_trading_approved: `false`
