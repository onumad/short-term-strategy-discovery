---
name: short-term-strategy-discovery
description: Guide research, diagnosis, implementation, validation, and next-step selection in the Short Term Strategy Discovery repository. Use for deterministic MNQ futures modules, playbook registries, schedulers, portfolio audits, causal ML datasets and labels, bounded LLM architecture, research reports, phase scripts, promotion-gate questions, or requests asking what this project should do next.
---

# Short-Term Strategy Discovery

Work within this repository's research-only hybrid ML/LLM futures program. Base decisions on the current code, policies, and latest reproducible evidence rather than on a generic trading-research sequence.

## Establish authority and state

1. Confirm the working directory is this repository.
2. Read `AGENTS.md` completely before taking action. Treat it as the controlling contract.
3. Inspect `git status --short --branch`. Preserve all unrelated user changes.
4. Read only the project context needed for the task:
   - `research_status_summary.md` for the current stage and direction.
   - `project_plan.md` for architecture and delivery stages.
   - `playbook_research_objective.md` for module, portfolio, and label semantics.
   - `docs/hybrid_ml_llm_trading_architecture.md` for authority boundaries.
   - Relevant README phase sections, source, tests, scripts, and local generated artifacts.
5. Prefer tracked source, tests, scripts, configuration, and curated documentation as the source of truth. Treat ignored `outputs/`, `reports/`, and `artifacts/` as regenerable evidence whose provenance and freshness must be checked.

## Preserve the research-stage boundary

- Keep `paper_trading_approved=false`, `live_trading_approved=false`, and official promotion gates unchanged unless the user explicitly requests a project policy change.
- Do not infer authorization from candidate, watchlist, review-packet, positive-signal, gate-pass, or scheduler labels.
- Do not add broker adapters, credentials, order routing, webhooks, automated execution, paper trading, or shadow execution during the current stage.
- Keep ML outputs non-authoritative: versioned predictions, rankings, calibrated scores, or signal inputs only after validation.
- Keep LLM outputs non-authoritative and schema constrained. Never allow an LLM to authorize orders, sizing, risk overrides, or broker actions.
- Require deterministic policy and independent risk validation for every possible later-stage action. Fail closed.

## Select the next milestone from evidence

When asked what to do next:

1. Inspect the latest relevant `*_next_action_recommendation.json` files and their matching reports.
2. Trace their input dependencies and distinguish the newest file from the latest valid decision in the active workflow.
3. Check whether newer code or uncommitted work supersedes those artifacts.
4. Identify the earliest unresolved blocker in dependency order. Prefer fixing data, session, causality, replay, label, or validation integrity before expanding strategy search or training models.
5. Recommend one bounded milestone with explicit deliverables, verification, and stop conditions.
6. Explain which attractive downstream work remains blocked and why.

Do not reopen a rejected strategy family without new data, a structurally different hypothesis, or explicit evidence justifying the retest. Do not train an ML model when target coverage, causality, class balance, chronological splits, or replay fidelity is unresolved.

## Follow the project research pipeline

Use this dependency order unless current artifacts establish a narrower prerequisite:

1. Audit local data and canonical session semantics.
2. Define a deterministic, serializable, no-lookahead module.
3. Simulate conservative order timing with explicit fees, slippage, tick economics, flattening, and risk measurements.
4. Validate chronologically with discovery, validation, holdout, walk-forward, stress, concentration, and stability diagnostics.
5. Classify signal evidence separately from tradability and research track.
6. Register qualifying research signals without implying tradability.
7. Evaluate correlation, overlap, contribution, weak folds, and concentration at playbook level.
8. Apply scheduler policy; keep rare modules registry-only unless an explicit audit includes them.
9. Build point-in-time ML features and replay-derived labels. Represent missing coverage as unknown, never as zero or no-trade.
10. Train ML baselines only after causal, coverage-aligned targets pass readiness checks.
11. Evaluate bounded LLM tasks only outside the order-authority path and only with versioned schemas and prompts.

## Enforce causal implementation

- Parse source timestamps as UTC and convert through `src/short_term_edge/sessions.py` to `America/New_York`.
- Preserve bar-start semantics and the repository's documented session behavior.
- Use only information available at the decision timestamp.
- Fit thresholds, quantiles, scalers, encoders, and models on permitted historical training data only.
- Calculate rolling or expanding regime thresholds from prior completed observations; define warm-up behavior explicitly.
- Never silently replace a historical module definition. Quarantine an invalid version and introduce a new versioned definition.
- Keep missing source coverage null/unknown. Do not coerce it to zero, inactive, or negative.
- Prefer next-bar fills unless intrabar ordering is provable.
- Record exact configs, commands, inputs, run IDs, assumptions, and generated paths.

## Evaluate modules and playbooks correctly

For modules, report signal evidence, stress PnL, validation and holdout results, walk-forward folds, MFE/MAE, drawdown, costs, activity, concentration, correlation, and plain-English logic.

Keep these dimensions separate:

- `signal_evidence_status`: whether evidence for an effect exists.
- `tradability_status`: whether the module meets robustness and activity requirements.
- `research_track`: regular practice, rare setup, parked signal, or priority for more data.
- Portfolio contribution: whether the module improves combined coverage, diversification, drawdown, concentration, or fold stability.

Low activity may preserve a rare research signal but still blocks tradability. The combined playbook, not every individual module, is responsible for regular opportunity.

## Implement scoped changes

- Reuse existing loaders, phase helpers, artifact writers, manifests, registries, scheduler policies, and reporting patterns.
- Prefer a small phase or audit with a clear question over a broad parameter sweep.
- Add direct regression and adversarial tests for the changed assumption.
- Preserve historical artifacts and identifiers when introducing corrected versions.
- Do not mutate generated registries or policies during a diagnostic-only audit unless mutation is the explicit task.
- Do not install dependencies, commit, push, or modify external state unless requested.

## Verify proportionately

Before reporting code changes complete, run:

```powershell
./.venv/Scripts/python.exe -m unittest discover -s tests -v
```

For data-loading, timestamp, session, or audit-assumption changes, also run:

```powershell
./.venv/Scripts/python.exe scripts/audit_data.py --no-write
```

Run the affected phase or audit script when practical. Inspect its manifest, recommendation, key CSVs, and report for internal consistency and unchanged safety flags. Report exact commands, outputs, failures, and anything not verified.

## Communicate decisions

Lead with the decision or completed outcome. Distinguish facts from inference. State:

- current stage and blocker;
- evidence supporting the decision;
- the single next milestone and its deliverables;
- pass, fail, and stop conditions;
- what remains unauthorized or deferred;
- verification performed and generated paths.

Use research and simulation language, not financial advice or performance promises.
