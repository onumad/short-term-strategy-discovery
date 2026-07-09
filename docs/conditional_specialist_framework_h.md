# Conditional Specialist Framework H

## Decision

The repository now treats the playbook as a portfolio of selective specialists,
not a collection of strategies expected to trade every day.

Framework H preserves the previous 16-module scheduler identifier as a
historical research replay universe so Target D, Baseline B, and earlier audits
remain reproducible. It does not treat those modules as currently admitted.

Current default admission is empty.

## Three eligibility layers

1. **Condition eligibility** asks whether the current point-in-time market state
   satisfies a specialist's activation contract.
2. **Research eligibility** permits a registered module to participate in an
   explicitly scoped offline audit.
3. **Default-scheduler admission** requires runtime-bound activation logic,
   regular-practice status, standalone tradability, unchanged official gates,
   and positive incremental playbook contribution.

These states cannot imply one another. A positive research signal can remain
rare or parked, and historical replay membership does not imply tradability.

## Activation contract

Every registered module receives additive metadata under
`specialist_activation_contract/v1`:

- activation condition identifier and version;
- market condition and session window;
- causal decision time and entry window;
- required point-in-time features;
- eligible and ineligible conditions;
- maximum setups per session;
- warm-up and invalid-input behavior;
- explicit no-trade validity;
- runtime-binding status;
- research and default-admission decisions with reasons.

The initial contracts normalize existing registered strategy semantics. They
are marked `metadata_only_not_runtime_enforced`, so they cannot satisfy default
admission until a future implementation binds and directly tests the contract
against the strategy's executable signal path.

## Current evidence

- registered modules: 47;
- rare modules: 25;
- parked modules: 22;
- regular-practice candidates: 0;
- historical replay modules: 16;
- default-admitted modules: 0;
- condition/session cells: 60;
- uncovered cells: 51;
- research-signal/nontradable coverage cells: 9;
- redundancy clusters: 8;
- recorded hypothesis families: 8.

The coverage matrix is a research map, not a mandate to fill every cell. New
work should address an economically meaningful gap only when it offers a
structurally distinct, causal hypothesis. The hypothesis ledger prevents a
failed family from being reopened through parameter variation alone.

## No-trade behavior

- `no_trade_is_valid=true`;
- `minimum_trades_per_day=null`;
- `forced_daily_activity=false`;
- missing, stale, incomplete, or inactive conditions fail closed;
- opportunity coverage is evaluated over rolling playbook windows;
- a strategy is not rewarded merely for increasing activity.

## Reproduction

```powershell
$env:EXPERIMENT_RUN_ID='playbook-scheduler-f-r2-conditional-semantics'
./.venv/Scripts/python.exe scripts/build_playbook_scheduler_policy.py

$env:EXPERIMENT_RUN_ID='conditional-specialist-framework-h-r1'
./.venv/Scripts/python.exe scripts/build_conditional_specialist_framework_h.py
```

Key local generated outputs:

- `outputs/playbook_specialist_activation_contracts.csv`;
- `outputs/playbook_specialist_condition_coverage_matrix.csv`;
- `outputs/playbook_specialist_redundancy_audit.csv`;
- `outputs/strategy_hypothesis_ledger.csv`;
- `outputs/playbook_historical_replay_universe.csv`;
- `outputs/playbook_default_admission_universe.csv`;
- `outputs/playbook_conditional_specialist_policy.json`;
- `reports/conditional_specialist_framework_h_report.md`.

## Guardrails

Framework H generated no strategy signals, changed no official gates, and
approved no paper, shadow, or live trading. Its next action is to define and
preregister one structurally new specialist for a meaningful coverage gap,
then test standalone evidence and incremental playbook contribution before any
admission decision.
