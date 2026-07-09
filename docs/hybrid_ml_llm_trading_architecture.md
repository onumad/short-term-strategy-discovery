# Hybrid ML and LLM Trading Architecture

## Purpose

This document defines a future-state architecture for an auditable intraday futures trading system that combines deterministic market features, conventional machine learning, and bounded LLM assistance. It is an architectural target, not an authorization to paper trade, connect to a broker, or place live orders. The repository remains research and simulation only.

The design keeps trading authority in deterministic, versioned policy and independent risk controls. ML may estimate defined quantities. An LLM may produce structured research or operational recommendations, but it must not directly decide live entries, exits, position size, risk limits, or risk overrides.

## Authority Boundaries

| Layer | Permitted authority | Prohibited authority |
| --- | --- | --- |
| Features and data | Produce point-in-time, reproducible inputs | Use future data or silently repair material data defects |
| ML models | Produce versioned scores, forecasts, classifications, and uncertainty estimates | Place orders, set risk limits, or bypass policy gates |
| LLM services | Summarize evidence, classify bounded context, and emit schema-constrained candidate proposals | Directly authorize trades, set sizing or risk, access credentials, or emit executable broker payloads |
| Deterministic policy | Convert approved inputs into candidate actions under frozen rules | Change its own parameters, release, or approval state |
| Independent risk | Reduce, reject, halt, or flatten according to configured limits | Increase exposure beyond policy output or waive a breach |
| Execution | Translate approved intents into idempotent broker commands in a later authorized stage | Invent intents, alter size upward, or retry without bounded rules |
| Monitoring and operators | Observe, alert, halt, and approve controlled stage changes | Treat a model score or research label as deployment approval |

No component may infer authorization from a candidate, watchlist, paper-review, gate-pass, or model-confidence label. Stage authorization is explicit configuration controlled through a reviewed project policy change.

## Components

### Features and Data

- Ingest versioned market, reference, calendar, and approved operational data.
- Normalize timestamps through the canonical session helper and preserve bar-start semantics.
- Validate schema, ordering, duplicates, gaps, freshness, symbol mapping, and session boundaries.
- Compute point-in-time features with recorded availability timestamps and lineage.
- Store immutable input snapshots or content hashes sufficient for deterministic replay.

### ML Services

- Train only from declared chronological splits with discovery-only fitting and threshold selection.
- Publish immutable model releases containing code version, feature contract, training-data lineage, hyperparameters, dependency versions, metrics, and approval state.
- Return structured predictions with model version, event time, feature timestamp, uncertainty, and validation status.
- Abstain when inputs are missing, stale, out of distribution, or incompatible with the model contract.

### LLM Services

- Operate outside the order-authority path by default. In a later explicitly approved stage, a validated LLM release may emit a typed candidate proposal as a non-authoritative policy input.
- Accept only redacted, allowlisted context; never receive broker credentials or unrestricted account access.
- Produce schema-validated outputs such as research hypotheses, incident classifications, evidence summaries, operator checklists, or bounded candidate proposals.
- Attach model identifier, prompt-template version, tool policy, input references, and output-validation result to every response.
- Treat free-form text as commentary only. It cannot become an executable trade or risk command.

### Deterministic Policy Engine

- Consume only approved, schema-valid features, ML outputs, and explicitly allowlisted LLM proposal fields.
- Apply frozen strategy, scheduler, portfolio, sizing, and flatten rules.
- Emit a typed trade intent containing reason codes, input versions, limits, and expiry.
- Reject unknown strategies, unapproved releases, stale inputs, ambiguous states, and non-deterministic parameters.

### Independent Risk Engine

- Run in a separate authority boundary from strategy and execution.
- Enforce contract limits, position and notional limits, daily loss, trailing or static drawdown, concentration, session restrictions, stale-data rules, order-rate limits, and flatten deadlines.
- Recalculate exposure from reconciled broker state rather than trusting strategy state alone.
- Hold unilateral authority to reject, reduce, cancel, flatten, or trigger a kill switch. It never increases requested exposure.

### Execution and Reconciliation

- Remain absent or disabled during the current research stage.
- In a later explicitly authorized stage, accept only signed, unexpired intents approved by independent risk.
- Use idempotency keys, bounded retries, duplicate-order prevention, explicit order-state transitions, and startup reconciliation.
- Reconcile intended orders, acknowledgements, fills, positions, cash, and rejects; uncertain state blocks new exposure.

### Monitoring and Operations

- Track data freshness, feature health, model drift, abstention, policy decisions, risk rejects, order lifecycle, reconciliation, latency, and service health.
- Alert on contract violations, unexpected output distributions, missing logs, clock drift, and authorization changes.
- Provide operator-controlled pause, cancel, flatten, and kill-switch procedures that do not depend on ML or LLM availability.

## Data Flow

1. Versioned raw inputs enter validation and point-in-time normalization.
2. Feature computation emits a schema-versioned feature record with lineage and availability time.
3. Approved ML releases may add predictions and uncertainty; invalid or unavailable models abstain.
4. Optional LLM analysis may add non-authoritative, schema-validated research, operational context, or a bounded candidate proposal.
5. The deterministic policy engine evaluates the frozen release and emits either no action or a typed candidate intent.
6. Independent risk recomputes limits and emits an approval, reduction, rejection, flatten, or halt decision.
7. Only in an authorized execution stage may an approved intent reach the execution adapter.
8. Broker and internal state are reconciled continuously; monitoring records outcomes and raises alerts.
9. All inputs, decisions, versions, and state transitions feed an append-only audit log and replay store.

The dependency direction is one way. Monitoring may halt the system, but model, LLM, strategy, and execution layers cannot bypass independent risk or change authorization.

## Versioning and Structured Contracts

Every deployable release must pin:

- source revision and dependency lock;
- dataset snapshot or content hashes and feature-schema version;
- ML artifact digest, training configuration, thresholds, and evaluation report;
- LLM provider/model identifier, prompt-template version, system/tool policy, and output-schema version;
- deterministic policy, risk configuration, instrument metadata, session calendar, and execution-adapter version.

Research releases use the same provenance discipline even though they are not deployable. A research release must declare `authorization_stage=research`, immutable contract identifiers, input and output content hashes, source revision, dirty-worktree state, and explicit approval defaults. ML and LLM research releases default to `approved_as_signal_input=false`.

Machine-to-machine messages use strict schemas with unknown fields rejected. Minimum envelopes include `schema_version`, `event_id`, `correlation_id`, `created_at`, `effective_at`, `expires_at`, `environment`, `release_id`, `source_versions`, and `authorization_stage`.

Prediction records include feature availability, model version, score, uncertainty, and abstention reason. Trade intents include strategy ID, instrument, side, quantity cap, order constraints, stop/target policy, expiry, and reason codes. Risk decisions include the input-intent digest, reconciled exposure snapshot, applied limits, decision, and reject or reduction reasons. LLM outputs use task-specific enumerations and bounded fields; a candidate proposal may reference only allowlisted modules, instruments, directions, evidence codes, and expiry, and it may not set quantity, risk limits, broker instructions, or credentials. Invalid output is discarded, never coerced into an executable default.

## Fail-Closed Behavior

The system emits no new exposure when any required input is missing, stale, malformed, out of sequence, version-incompatible, or unauthorized. The same applies when clocks disagree, reconciliation is incomplete, limits cannot be computed, a dependency times out, an ML model abstains where its output is required, or an LLM output fails schema validation.

Loss of an optional ML or LLM service must not prevent risk controls, reconciliation, cancel, flatten, or kill-switch operation. Recovery requires deterministic state reconciliation and an explicit health transition; process restart alone does not restore trading authority.

## Credentials and Security

- Keep broker and market-data credentials out of source code, prompts, model features, logs, and research artifacts.
- Store secrets in an approved secret manager with environment separation, least privilege, rotation, and access auditing.
- Isolate execution credentials in the execution boundary. ML and LLM services receive no broker secret and no capability to submit orders.
- Separate research, paper, shadow, and live accounts, identities, networks, and authorization policies.
- Redact sensitive account and operator data before any external model call.

## Replay and Audit Logging

Record an append-only event for each input snapshot, feature computation, prediction, LLM request and validated response, policy decision, risk decision, order transition, fill, reconciliation result, operator action, configuration change, and authorization change. Logs must include content digests and version identifiers without storing secrets.

A replay must reconstruct decisions from captured point-in-time inputs and pinned releases without consulting future data. Deterministic policy and risk outputs must reproduce exactly. Non-deterministic external responses, including LLM output, are replayed from their recorded validated payloads and may be re-evaluated separately for diagnostics, never substituted silently.

## Staged Promotion Criteria

Promotion is never automatic. Passing a research metric, model gate, or paper-review label does not change authorization. Each transition requires documented acceptance evidence, an explicit project policy change, named approval, a frozen release, rollback criteria, and a reviewed incident response plan.

### Research to Paper Trading

- Point-in-time and no-lookahead tests pass across chronological out-of-sample and walk-forward evaluation.
- Costs, slippage, fills, sessions, contract metadata, concentration, and prop-style risk constraints are validated.
- Feature, model, policy, risk, logging, replay, monitoring, and kill-switch contracts are tested.
- The paper environment has isolated credentials and cannot route real orders.

### Paper Trading to Shadow Execution

- A predefined observation window meets data-quality, decision-replay, stability, latency, and risk-reject criteria.
- Frozen releases show no unauthorized configuration drift.
- Intended positions and simulated fills reconcile under restart, disconnect, duplicate, reject, and partial-fill scenarios.

### Shadow to Controlled Live Execution

- Broker certification, credential isolation, reconciliation, independent risk, bounded retry, duplicate prevention, monitoring, alerts, flatten, and kill-switch drills pass.
- Operational ownership, trading hours, support coverage, incident severity, rollback triggers, and limited-size exposure caps are approved.
- A human-controlled enablement changes the explicit authorization stage for a named release and account.

### Expansion Within Live Execution

- Size, instruments, sessions, or strategy coverage increase only through another reviewed release and policy change.
- Breaches, unexplained divergence, missing audit data, or reconciliation uncertainty force rollback or halt rather than automatic adaptation.

## Current Status

This architecture describes possible later delivery stages. The current repository remains authorized only for research and simulation. Paper trading, shadow execution, broker connectivity, credentials, order routing, automated execution, and live trading are not currently approved. All current outputs must preserve `paper_trading_approved=false`, `live_trading_approved=false`, and unchanged official promotion gates.
