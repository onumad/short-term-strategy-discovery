# Phase 8K Next Five Steps Implementation Plan

> **For Hermes:** Implement this plan directly with TDD and research-only guardrails. Do not commit unless explicitly asked.

**Goal:** Convert Phase 8J's positive-but-fragile MNQ VWAP result into five deterministic next-step diagnostics that explain the weak fold/concentration failure and produce a bounded follow-up queue.

**Architecture:** Add a Phase 8K module that consumes only Phase 8J artifacts (`filtered_trade_log`, `walk_forward_folds`, `walk_forward_summary`) and produces inspectable CSV/Markdown outputs. Keep the work diagnostic-only: no live trading, no paper-trading promotion, no post-hoc filter promotion.

**Tech Stack:** Python 3.11, pandas, unittest, existing run-scoped artifact helpers.

---

## Current Context

Phase 8J mapped `time_window:pre_14_00` to `MNQ_vwap_pullback_continuation_tf5_cdd66a8b8a`. Aggregate test PnL and stress PnL are positive, but the candidate is `phase8j_watchlist_needs_more_history` because only 2/3 test folds are positive and concentration gates fail. The known weak test fold is `2026-04-22` through `2026-05-27`.

## The Next 5 Steps To Implement Now

1. **Fold failure attribution** — tag each Phase 8J trade with fold/segment membership and identify failing validation/test folds.
2. **Session concentration decomposition** — compute session-level PnL/trades/drawdown contribution and list worst/best concentration sessions.
3. **Pre-entry bucket decomposition** — summarize fold-segment performance by no-lookahead entry metadata (`rth_bucket`, `weekday`, `minute_bucket`).
4. **Diagnostic rescue candidates** — propose fixed, no-lookahead follow-up filters from bucket evidence, but label them as diagnostic-only until retested in a later phase.
5. **Decision queue** — write a five-row next-action queue that tells us whether to deepen this VWAP path, retest a fixed filter, add risk gates, require more history, or broaden away.

## Files To Add

- `src/short_term_edge/phase8k_fold_failure_diagnostic.py`
- `tests/test_phase8k_fold_failure_diagnostic.py`
- `scripts/run_phase8k_fold_failure_diagnostic.py`

## Legacy Outputs

- `outputs/phase8k_tagged_trades.csv`
- `outputs/phase8k_session_diagnostics.csv`
- `outputs/phase8k_bucket_diagnostics.csv`
- `outputs/phase8k_candidate_actions.csv`
- `outputs/phase8k_next_step_queue.csv`
- `reports/phase8k_fold_failure_diagnostic_report.md`

## Run-Scoped Outputs

```text
artifacts/phase8k_fold_failure_diagnostic/<run_id>/
  manifest.json
  results.csv
  specs.json
  tagged_trades.csv
  session_diagnostics.csv
  bucket_diagnostics.csv
  candidate_actions.csv
  report.md
```

## Implementation Tasks

### Task 1: RED tests for fold tagging and session concentration

Create `tests/test_phase8k_fold_failure_diagnostic.py` with tiny in-memory Phase 8J trades/folds. Verify:

- a trade can belong to multiple fold/segment rows when rolling folds overlap;
- failing test folds are flagged from negative segment PnL;
- session diagnostics include `best_session_contribution`, `worst_session_pnl`, and deterministic labels.

Run:

```bash
./.venv/Scripts/python.exe -m unittest discover -s tests -p 'test_phase8k_fold_failure_diagnostic.py' -v
```

Expected: fail because module does not exist.

### Task 2: GREEN implementation for fold/session/bucket diagnostics

Create `src/short_term_edge/phase8k_fold_failure_diagnostic.py` with:

- `Phase8KConfig`
- `tag_phase8k_trades_with_folds`
- `summarize_phase8k_sessions`
- `summarize_phase8k_buckets`
- `build_phase8k_candidate_actions`
- `build_phase8k_next_step_queue`
- `render_phase8k_report`

Keep all filters no-lookahead: timestamp/weekday/rth bucket/session/fold metadata only.

### Task 3: Runner and artifacts

Create `scripts/run_phase8k_fold_failure_diagnostic.py`. It should read Phase 8J artifacts, write legacy outputs and run-scoped outputs, write manifest, and print row counts plus the top decision.

### Task 4: README update

Append a concise Phase 8K section with command, outputs, and current result. Emphasize diagnostic-only and no paper/live promotion.

### Task 5: Verification

Run:

```bash
./.venv/Scripts/python.exe -m unittest discover -s tests -p 'test_phase8k_fold_failure_diagnostic.py' -v
EXPERIMENT_RUN_ID=phase8k-r1-smoke ./.venv/Scripts/python.exe scripts/run_phase8k_fold_failure_diagnostic.py
./.venv/Scripts/python.exe -m unittest discover -s tests -v
./.venv/Scripts/python.exe scripts/audit_data.py
```

If Hermes asks for focused evidence, create a temp verifier under `C:\Users\ulzii\AppData\Local\Temp` using a `hermes-verify-` prefix, run it, clean it up, and call it ad-hoc verification.

## Guardrails

- Research/simulation only.
- No live trading approval.
- No broker adapters, order routing, API-key storage, webhooks, or automated execution.
- No paper-trading promotion from Phase 8K; it can only produce diagnostics and next-action candidates.
- Do not tune on the weak fold and call it validation. Any proposed filter must be retested as fixed in a later phase.
