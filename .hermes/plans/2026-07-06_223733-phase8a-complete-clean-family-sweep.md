# Phase 8A Clean-Family Sweep Continuation Plan

> **For Hermes:** Parent keeps planning/review in this chat; use focused tester/reviewer subagents only when the change set or verification scope warrants it.

**Goal:** Continue the Phase 8A MGC clean-family prefilter from `1 / 12` scored specs toward a complete deterministic sweep without widening strategy scope.

**Architecture:** Keep using the existing checkpointed Phase 8A runner. Score one new spec per invocation by default because full-history MGC scoring is slow. Refresh the CSV/spec/report artifacts after each bounded pass and do not promote any strategy unless strict Phase 8A gates and later walk-forward validation pass.

**Tech Stack:** Python 3.11 via `./.venv/Scripts/python.exe`, pandas CSV artifacts, local data under `data/raw`, existing Phase 8A module/script/tests.

---

## Current Context

- Current Phase 8A report shows `Rows scored: 1 / selected specs: 12`.
- The first scored candidate is rejected on 4-tick stress, concentration, drawdown, and negative holdout.
- The selector is now balanced across timeframes: 6 specs at `tf=1`, 6 specs at `tf=3`.
- No live trading, broker adapters, order routing, API-key storage, or automated execution are in scope.

## Implementation Steps

1. Run one bounded continuation pass:

   ```bash
   PHASE8A_MAX_NEW_SPECS=1 ./.venv/Scripts/python.exe scripts/run_phase8a_mgc_clean_family_search.py
   ```

2. Inspect updated artifacts:
   - `outputs/phase8a_mgc_clean_family_results.csv`
   - `outputs/phase8a_candidate_specs.json`
   - `reports/phase8a_mgc_clean_family_report.md`

3. Verify:
   - row count increased by one or the runner reports no new specs remaining;
   - report row count matches CSV row count;
   - no `phase5n_*` stale columns leaked into Phase 8A output;
   - scored candidate IDs remain a subset of the JSON spec canonical IDs;
   - guardrail and cost-assumption text remain present.

4. Run a focused verification command:

   ```bash
   ./.venv/Scripts/python.exe tests/test_phase8a.py -v
   ```

5. If Hermes coding guard asks for ad-hoc evidence, create and run a temp `hermes-verify-*` script under `C:\Users\ulzii\AppData\Local\Temp` and clean it up.

## Stop / Continue Rules

- Stop this turn after one successful bounded new-spec scoring pass plus verification.
- Continue later with the same command until `12 / 12` specs are scored.
- Only start a Phase 8B walk-forward/deep-validation plan if Phase 8A produces at least one `mgc_clean_family_prefilter_survivor` or explicit watchlist candidate worth validating.
- If all 12 are rejected, write a failure synthesis before designing a new family/search axis.
