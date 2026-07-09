# Agent Instructions

This file is the portable, cross-agent contract for this repository. Agent-specific files may add workflow details, but they must not weaken or duplicate these shared rules.

## Repo Hygiene

- Keep edits scoped to the requested task.
- Prefer inspectable, boring code over clever abstractions.
- Avoid unrelated refactors, generated noise, and formatting churn.
- Test appropriately for the risk and blast radius before reporting completion.
- Do not commit unless explicitly asked.

## Project Scope And Safety

- The long-term project goal is a production-grade hybrid ML/LLM intraday futures trading bot built around deterministic, independently validated playbook modules and risk controls.
- The current project stage is research and simulation only. No paper or live trading is currently approved.
- Candidate, watchlist, and paper-review labels are research language only. Independent validation does not authorize paper trading.
- Keep `paper_trading_approved=false`, `live_trading_approved=false`, and official promotion gates unchanged until the user explicitly promotes the project to a later delivery stage through a project policy change.
- During the current research stage, do not add broker adapters, order routing, API-key storage, webhooks, or automated execution.
- ML models may produce versioned predictions, rankings, and trade-signal inputs only after stage-specific validation for causality, calibration, stability, and drift.
- LLMs may produce versioned structured analysis and trade proposals, but they must not directly authorize orders, position sizing, risk overrides, or broker actions.
- Every proposed action must pass deterministic policy and independent risk validation. Model processes must not hold broker credentials or direct order-routing capability, and failures must stop safely.

## Environment

Use the project virtual environment:

```bash
./.venv/Scripts/python.exe
```

Install or update dependencies only when the task requires it:

```bash
./.venv/Scripts/python.exe -m pip install -r requirements.txt
```

## Canonical Verification

Before reporting code changes as complete, run:

```bash
./.venv/Scripts/python.exe -m unittest discover -s tests -v
```

For changes that touch data loading or audit assumptions, run the read-only audit:

```bash
./.venv/Scripts/python.exe scripts/audit_data.py --no-write
```

Omit `--no-write` only when the task explicitly requires regenerating `data_audit.md`, and report that tracked output change. For changes to a specific research phase, run that phase script when practical and report generated output paths. If a required audit or phase run is skipped, report the command and the concrete reason.

## Research Rules

- Use only local CSV files under `data/raw` unless the user explicitly changes scope.
- Preserve the required schema: `timestamp,symbol,open,high,low,close,volume`.
- Use `America/New_York` time.
- Treat `src/short_term_edge/sessions.py` as the canonical session implementation. Parse source timestamps as UTC and convert them to `America/New_York` through that helper.
- Under the current implementation, bars at or after `18:00 ET` map to the next local calendar date. This is not an exchange-calendar calculation and does not adjust weekends, holidays, or early closes.
- Treat RTH as the half-open interval `[09:30, 16:00) ET`; a bar starting at `16:00 ET` is not RTH.
- Do not describe the current session mapping as holiday-aware or fully CME-calendar-aware. Any exchange-calendar or boundary change must update the canonical helper and documentation and add or update direct boundary tests.
- Preserve bar-start timestamp semantics unless a change explicitly documents otherwise.
- Avoid lookahead: indicators and signals may use only information available at the decision timestamp.
- Prefer deterministic, serializable strategy configs.
- Include costs and slippage assumptions in strategy reports.
- Document commands, assumptions, generated reports, generated CSVs, and chart or trade-log paths.

## Git Workflow

- Work directly in this repo unless the user asks for a clone or worktree.
- Check `git status --short --branch` before editing and before committing.
- Keep `.venv/`, caches, and generated Python bytecode ignored.
- Do not push unless the user explicitly asks.
