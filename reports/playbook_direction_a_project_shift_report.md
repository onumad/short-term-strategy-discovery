# Playbook Direction A — Project Objective Shift

Research/simulation only. No live trading, broker adapters, order routing, webhooks, credential storage, automated execution, or LLM-driven trade decisions.

## Why Direction Changed

The prior objective emphasized finding one manually tradable intraday futures strategy with regular daily activity. Recent audit work changed the evidence base:

- Framework Audit B showed costs were not the main failure reason; activity, fold instability, and concentration were the dominant blockers.
- Framework Audit C found several real-but-nontradable research signals.
- Research Signal Registry A added two-tier labeling so signal evidence and tradability readiness remain separate.
- Portfolio Audit A showed combinations improved activity and concentration, but not enough to pass fold/trade-concentration gates.
- Phase 13A outputs are present and may add uncorrelated research signals, but no paper-trading approval is implied.

The project direction is therefore shifted from finding one daily-trading strategy to building a diversified playbook of specialized deterministic MNQ intraday modules.

## What Stays The Same

- Official promotion gates remain unchanged.
- Research/simulation-only guardrails remain unchanged.
- No candidate is approved for paper trading unless official gates pass.
- Historical phase labels and reports remain unchanged.
- Rules must remain deterministic, serializable, and explainable in plain English.
- No broker/live functionality, order routing, credential storage, webhooks, automated execution, or LLM-driven trade decisions are allowed.

## What Changes

- Individual modules no longer need to trade daily.
- A module may specialize in a specific market condition or pattern.
- Low activity is not automatically a research failure when the module has signal evidence and diversifies the playbook.
- The combined playbook, not each individual module, is responsible for enough regular opportunities.
- Future work should evaluate module contribution to playbook diversification before targeted retests or review packets.

## How To Interpret Low-Activity Strategies Now

Low activity remains a tradability blocker for official paper-review unless the unchanged gates pass. It is no longer, by itself, a reason to discard a module from the research track. A rare module can remain useful if it has credible signal evidence, low correlation to existing modules, a clear market-condition role, and improves playbook-level opportunity/concentration/fold behavior.

## How Future Modules Should Be Evaluated

Module-level evaluation should include signal evidence, stress PnL, validation/holdout behavior, MFE/MAE behavior, concentration, fold stability, correlation to existing modules, plain-English market logic, and whether the module belongs to a rare setup track or regular-practice track.

Playbook-level evaluation should include total active days, total opportunities per day, fold stability, drawdown, day/trade concentration, module correlation, trade overlap, contribution by module/family, and whether the combined playbook improves over individual modules.

## Why No Candidate Is Approved For Paper Trading

This direction update does not change historical results, official gates, or promotion labels. Recent audits found research signals and some diversification benefit, but the combined evidence still includes fold instability and concentration blockers. Paper trading remains disallowed unless a candidate or diagnostic review packet passes the unchanged official gates.

## Next Recommended Implementation Step

Implement `playbook_framework_b_module_registry_schema`: a module registry schema that records market condition, module family, portfolio role, signal evidence status, tradability status, research track, playbook contribution fields, and unchanged official-gate outcomes.
