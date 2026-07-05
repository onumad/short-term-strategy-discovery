# Short-Term Futures Edge Discovery

This project is a focused research workspace for finding short-term, manually tradable intraday futures edges using only local Databento data.

The active raw data lives in `data/raw` and currently contains recent 1-minute OHLCV continuous futures files for `MNQ` and `MGC`.

## Guardrails

- Research and simulation only.
- No live trading approval.
- No broker adapters, order routing, API-key storage, webhooks, or automated execution.
- No LLM-driven trade entries, exits, sizing, or discretionary decisions.
- Treat every later strategy result as a paper-trading candidate at most until independently validated.

## Setup

```powershell
python -m pip install -r requirements.txt
```

## Reproduce The Data Audit

```powershell
python scripts/audit_data.py
```

The audit writes `data_audit.md` and reports the latest shared complete trading session plus the initial 63-session research window.

## Run Phase 2 Discovery

```powershell
python scripts/run_phase2_discovery.py
```

The discovery sweep writes:

- `reports/phase2_discovery_report.md`
- `outputs/ranked_edges.csv`
- `outputs/top_edges.csv`
- top-candidate trade logs under `trade_logs/`
- top-candidate charts under `charts/`

## Run Phase 3 Validation

```powershell
python scripts/run_phase3_validation.py
```

The Phase 3 validation is a bounded follow-up to Phase 2. It re-runs the frozen top candidates, adds diagnostics for the primary MNQ opening-range-failure candidate, applies a simple prop-style research risk overlay, and writes a manual paper-trading plan.

Outputs:

- `reports/phase3_validation_report.md`
- `reports/phase3_manual_paper_trading_plan.md`
- `outputs/phase3_candidate_diagnostics.csv`
- `outputs/phase3_daily_pnl.csv`
- `outputs/phase3_trade_review.csv`
- `charts/phase3_*.png`

## Current Research Scope

- Instruments: `MNQ`, `MGC`
- Data source: local Databento CSV files only
- Schema: `timestamp,symbol,open,high,low,close,volume`
- Timezone: `America/New_York`
- Session rule: bars at or after `18:00 ET` map to the next CME trade date
- RTH: `09:30-16:00 ET`
- ETH: all other included bars

The first strategy-discovery phase should use the shared complete-session window from `2026-04-06` through `2026-07-02` and exclude the partial `2026-07-03` session.

## Current Next Work

Use the Phase 3 manual paper-trading plan for a fixed 20-session paper test before considering any later research phase. Do not add live automation or broker connectivity.
