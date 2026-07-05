# Phase 5A AI Strategy Finder Foundation Implementation Plan

> For Hermes: implement directly in this repo using cautious TDD and the project guardrails in `.hermes.md`.

Goal: Build a deterministic, serializable, inspectable AI-assisted strategy-search foundation over local Databento MNQ/MGC 1-minute data without live trading, broker adapters, API keys, webhooks, or automated execution.

Architecture: Add small reusable modules for strategy specs, causal features, scoring, and bounded deterministic search. The search layer proposes auditable rule candidates from explicit grids/heuristics, then validation scores them with existing one-minute simulation primitives. No neural-net trader or discretionary LLM trade logic.

Tech stack: Python stdlib, pandas/numpy already in requirements, existing `short_term_edge` modules, `unittest`.

Plan:

1. Add `src/short_term_edge/strategy_spec.py`
   - Define frozen dataclasses for `StrategySpec`, `EntryRule`, `ExitRule`, `RiskRule`, and `SearchSpace`.
   - Include stable `to_dict`, `to_json`, `from_dict`, `from_json`, `canonical_id`, and validation.
   - Only allow explicit strategy families and parameters used by the deterministic search.

2. Add `tests/test_strategy_spec.py`
   - Verify canonical IDs are deterministic and insensitive to param insertion order.
   - Verify JSON round trip and unknown family/side/risk errors.

3. Add `src/short_term_edge/features.py`
   - Build no-lookahead RTH feature frames from 1-minute bars.
   - Include per-session `bar_index`, session VWAP, EMA/SMA, rolling realized range, prior-session levels shifted by one session, opening-range levels available after the opening window, and future-return labels for offline scoring only.
   - Keep feature generation pure/deterministic.

4. Add `tests/test_features.py`
   - Verify opening-range levels are unavailable until the configured window completes.
   - Verify prior-session levels are shifted and do not use current-session highs/lows.
   - Verify forward labels use future close but are separate `label_*` columns.

5. Add `src/short_term_edge/scoring.py`
   - Define `CandidateScore` and scoring helpers that summarize trades with net PnL, splits, strict slippage, drawdown, concentration, trade counts, active-session percent, and conservative labels.
   - Return explicit risk notes and include cost/slippage assumptions.

6. Add `tests/test_scoring.py`
   - Verify empty trades are rejected.
   - Verify profitable but concentrated trades are not promoted.
   - Verify deterministic split-aware scoring.

7. Add `src/short_term_edge/ai_search.py`
   - Implement deterministic proposal generation from an explicit bounded search space.
   - Implement conversion from specs to existing `Phase4ACandidate`/signals/simulator where possible.
   - Run bounded validation over local data only, capped by `max_candidates`, `symbols`, and recent sessions for runtime control.
   - Persist candidates as CSV with serialized JSON specs.

8. Add `tests/test_ai_search.py`
   - Verify candidate proposal ordering is deterministic.
   - Verify bounded search respects `max_candidates`.
   - Verify unsupported/non-serializable specs fail closed.

9. Add `scripts/run_phase5_ai_search.py`
   - Use the project venv and local `data/raw` only.
   - Run a small first search (`max_candidates` around 24-40, recent sessions around 80-120) to avoid excessive runtime.
   - Write `outputs/phase5_ai_candidates.csv` and `reports/phase5_ai_search_report.md`.
   - Document scaling knobs and guardrails in the report.

10. Verification and commit
   - Run targeted tests as files are added.
   - Run canonical verification: `./.venv/Scripts/python.exe -m unittest discover -s tests -v`.
   - Run Phase 5 script if practical: `./.venv/Scripts/python.exe scripts/run_phase5_ai_search.py`.
   - Review generated output paths and `git status --short`.
   - Commit coherent changes with concise Conventional Commit messages. Do not push.
