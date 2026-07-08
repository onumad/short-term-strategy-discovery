# Seven-Hour Research Pivot Plan

> **For Hermes:** Use `futures-strategy-research`, `test-driven-development`, and `long-running-agent-runs` discipline if this plan is executed. Keep work research/simulation-only and do not add live trading, broker adapters, order routing, API-key storage, webhooks, or automated execution.

**Goal:** Spend the next 7 hours turning the project away from single-strategy grind and toward a broader, faster, evidence-ranked strategy discovery loop.

**Architecture:** Preserve the Phase 7C/7D/8A/8B baseline, then add only one narrow diagnostic implementation: Phase 8C no-trade/session-selection filters. In parallel, build a broad hypothesis queue and cheap event-study scouting layer so future strategy work compares many families, sides, timeframes, and instruments before any deep backtest.

**Tech Stack:** Python 3.11 via `./.venv/Scripts/python.exe`, pandas/numpy, existing `short_term_edge` modules, local CSVs under `data/raw`, run-scoped artifacts under `artifacts/<experiment>/<run_id>/`.

---

## Current Context

- Branch: `master`.
- Worktree is intentionally dirty with uncommitted Phase 7C/7D/8A/R1/8B work.
- Phase 8B evidence says the dominant failure classes are:
  - `ambiguity`: 36
  - `drawdown`: 36
  - `concentration`: 12
  - `split_instability`: 9
  - `cost_slippage`: 7
  - `negative_expectancy`: 4
  - `overtrading`: 2
- Phase 7D payout-path diagnostic: `0 / 32` successes.
- Phase 8A scored only `2 / 12` specs; both are rejected.
- Phase 8B decision: `phase8c_no_trade_session_filters` and stop entry-variant grinding.

## Operating Rules For The 7 Hours

1. **No single-family rabbit holes.** Max 45 minutes on any one family unless it clears a predeclared gate.
2. **No manual babysitting Phase 8A.** Do not spend the block scoring the remaining 10 clean-family specs by hand.
3. **Every research action must compare alternatives.** At minimum compare across side, timeframe, or family.
4. **Cheap evidence first.** Use event studies / diagnostics before full backtests when possible.
5. **Kill criteria are explicit.** Park ideas that fail gross expectancy, trade-quality, ambiguity, or cost-stress gates.
6. **Preserve provenance.** Every new phase writes legacy outputs plus run-scoped artifacts/manifests.
7. **No live-trading scope.** Research artifacts only.

---

## 0:00-0:35 — Checkpoint And Scope Control

**Objective:** Make the current workspace safe enough to continue without losing the Phase 7/8/R1/8B work.

**Files:**
- Read: `reports/phase8b_failure_synthesis_report.md`
- Read: `outputs/phase8b_failure_summary.csv`
- Inspect: `git status --short --branch`
- Optional commit only if user explicitly approves.

**Steps:**

1. Run:
   ```bash
   git status --short --branch
   ./.venv/Scripts/python.exe -m unittest discover -s tests -v
   ```
2. If tests fail, fix only the failing infrastructure issue; do not start new research.
3. If tests pass, create a short checkpoint note in the final report/handoff, not a new phase.
4. Do **not** commit unless the user explicitly says to commit.

**Success criteria:**
- Current baseline is understood.
- Full suite passes or blocker is documented.
- No new strategy work starts before baseline is stable.

---

## 0:35-1:45 — Phase 8C No-Trade / Session-Selection Diagnostic

**Objective:** Test the Phase 8B recommendation: whether pre-entry session filters can reduce overtrading, concentration, ambiguity, drawdown, or cost exposure before we try more entries.

**Files likely to change:**
- Create: `src/short_term_edge/phase8c.py`
- Create: `scripts/run_phase8c_no_trade_filter_diagnostic.py`
- Create: `tests/test_phase8c.py`
- Create: `outputs/phase8c_no_trade_filter_results.csv`
- Create: `reports/phase8c_no_trade_filter_report.md`
- Create run artifacts under: `artifacts/phase8c_no_trade_filter/<run_id>/`

**Filter families to test first:**

Pre-entry only, no lookahead:

1. Time-of-day windows:
   - first 30m only
   - first 60m only
   - exclude lunch
   - last 90m only
2. Day/session filters:
   - day-of-week
   - prior session range tercile/quartile
   - overnight range tercile/quartile
3. Opening conditions:
   - opening gap direction/magnitude bucket
   - first 15m opening range width bucket
   - first 15m direction bucket, only after the first 15m completes
4. Volatility/trend context:
   - prior-session ATR/range bucket
   - price relative to prior close/opening range/VWAP only when known

**TDD steps:**

1. Write tests that prove filters only use information available at decision timestamp.
2. Write tests that filter specs are deterministic and serializable.
3. Write tests that a filter can reduce active sessions/trades without changing trade simulation internals.
4. Implement minimal filter application to existing Phase 8A candidate/trade outputs or, if trade logs are not reusable, to replayed candidate results with a bounded candidate set.
5. Generate a ranked filter summary.

**Output columns:**

```text
filter_id, filter_family, filter_params_json,
source_candidate_count, kept_trade_count, kept_active_sessions,
net_pnl, validation_pnl, holdout_pnl, slippage_4_ticks_net_pnl,
max_drawdown, best_day_concentration, best_trade_concentration,
same_bar_stop_target_ambiguity_count, phase8c_label, phase8c_notes
```

**Kill criteria:**
- If filters cannot be evaluated without large refactor, stop at diagnostic design + tests.
- If every filter only improves results by deleting almost all trades, label as `insufficient_activity`, not promising.

**Success criteria:**
- Phase 8C says whether no-trade/session filters are worth deeper work.
- No strategy entry logic changes.

---

## 1:45-2:50 — Build A Broad Hypothesis Queue

**Objective:** Create a research queue that represents the user’s broader idea space instead of a single MGC entry variant.

**Files likely to change:**
- Create: `src/short_term_edge/phase8d_hypothesis_queue.py`
- Create: `scripts/run_phase8d_hypothesis_queue.py`
- Create: `tests/test_phase8d_hypothesis_queue.py`
- Create: `outputs/phase8d_hypothesis_queue.csv`
- Create: `reports/phase8d_hypothesis_queue_report.md`

**Queue dimensions:**

- Instruments: `MGC`, `MNQ`
- Timeframes: `1m`, `3m`, `5m`, `15m`
- Sides: `long_only`, `short_only`, `both`
- Families:
  - opening range breakout
  - opening range fade
  - prior high/low breakout
  - prior high/low rejection
  - VWAP reclaim/rejection
  - VWAP pullback continuation
  - opening drive continuation
  - first-pullback trend continuation
  - session reversal after failed breakout
  - volatility compression breakout
  - overnight range breakout/fade
  - time-of-day momentum/reversion

**Do not backtest everything.** This phase only creates and ranks hypotheses by cheap feasibility.

**Ranking fields:**

```text
hypothesis_id, instrument, timeframe, side, family,
setup_description, decision_time_requirements,
expected_trade_frequency, expected_cost_sensitivity,
lookahead_risk, ambiguity_risk, implementation_cost,
scout_priority, reason_to_try, kill_condition
```

**Success criteria:**
- At least 30 diverse hypotheses.
- No more than 3 hypotheses from one family in the top 10.
- At least one long-only, one short-only, one MGC, one MNQ, one non-1m candidate in the top 10.

---

## 2:50-4:25 — Cheap Event-Study Scouting Across Diverse Ideas

**Objective:** Use simple event studies to avoid expensive full backtests on weak ideas.

**Files likely to change:**
- Create: `src/short_term_edge/phase8e_event_scout.py`
- Create: `scripts/run_phase8e_event_scout.py`
- Create: `tests/test_phase8e_event_scout.py`
- Create: `outputs/phase8e_event_scout_results.csv`
- Create: `reports/phase8e_event_scout_report.md`

**Event-study measurements:**

For each hypothesis event, measure forward behavior after the event time using only future labels for evaluation, never for signal construction:

- `mfe_15m`, `mae_15m`
- `mfe_30m`, `mae_30m`
- `mfe_60m`, `mae_60m`
- directional hit rate after estimated cost
- event count
- session coverage
- side asymmetry
- timeframe sensitivity
- ambiguity proxy

**Hard caps:**

- Scout at most 40 hypotheses in this block.
- Use at most 4 variants per family.
- If an event has fewer than 50 occurrences, label it `too_sparse` and move on.

**Scouting labels:**

```text
reject_event, needs_filter, backtest_candidate, too_sparse, ambiguous
```

**Success criteria:**
- Select at most 6 `backtest_candidate` ideas.
- The selected set must be diverse: no duplicate instrument+family+side unless one is clearly stronger.

---

## 4:25-5:35 — Bounded Backtests For Top 3 Diverse Ideas

**Objective:** Backtest only a few diverse ideas that passed cheap scouting, not endless variants.

**Files likely to change:**
- Ideally reuse existing `StrategySpec`/Phase 5N/8A scoring paths.
- If needed, create a thin runner: `scripts/run_phase8f_diverse_candidate_probe.py`
- Create: `outputs/phase8f_diverse_candidate_probe_results.csv`
- Create: `reports/phase8f_diverse_candidate_probe_report.md`

**Selection rule:**

Pick at most 3, each from a different bucket:

1. One MGC candidate.
2. One MNQ candidate.
3. One side-only candidate that is not just “both directions with one side removed.”

**Gates:**

A candidate is immediately parked if:

- net PnL is negative after base costs,
- 4-tick stress is deeply negative,
- holdout is negative,
- active session percentage is too high without a filter thesis,
- concentration is dominated by one day/trade,
- same-bar ambiguity is non-trivial.

**Success criteria:**
- Get a clean reject/watchlist decision for each top idea.
- Do not tune parameters after seeing a reject unless the event-study result explicitly predicted that variant.

---

## 5:35-6:15 — Combo / Portfolio Decision Only If Evidence Supports It

**Objective:** Consider combinations, long-only/short-only splits, or multiple timeframes only after the individual ideas show complementary behavior.

**Files likely to change only if justified:**
- Create: `src/short_term_edge/phase8g_portfolio_probe.py`
- Create: `scripts/run_phase8g_portfolio_probe.py`
- Create: `tests/test_phase8g_portfolio_probe.py`
- Create: `outputs/phase8g_portfolio_probe_results.csv`
- Create: `reports/phase8g_portfolio_probe_report.md`

**Proceed only if:**

- At least two ideas have non-negative gross behavior before strict gates, and
- Their worst days/trades are not the same sessions, and
- Combining them reduces drawdown/concentration or trade frequency.

**Otherwise:**
- Skip combo work.
- Use the remaining time to improve the hypothesis queue and report.

---

## 6:15-6:45 — Synthesis And Next Decision

**Objective:** End the 7 hours with a decision, not a pile of partial scripts.

**Files likely to change:**
- Create: `reports/phase8_research_pivot_summary.md`
- Optional: `outputs/phase8_research_pivot_decisions.csv`

**Report must answer:**

1. Did Phase 8C filters help enough to justify deeper filtering work?
2. Which broad hypotheses survived cheap scouting?
3. Which ideas were rejected quickly and why?
4. Should the next block focus on:
   - no-trade/session filters,
   - MNQ instead of MGC,
   - long-only/short-only decomposition,
   - new family search,
   - or project/tooling improvements?

**Success criteria:**
- The next block is obvious.
- We do not need to re-read the whole session to know what happened.

---

## 6:45-7:00 — Verification, Cleanup, Handoff

**Objective:** Leave the repo in a verifiable state.

**Commands:**

```bash
./.venv/Scripts/python.exe -m unittest discover -s tests -v
```

If a new phase script was added and is practical to run:

```bash
./.venv/Scripts/python.exe scripts/run_phase8c_no_trade_filter_diagnostic.py
./.venv/Scripts/python.exe scripts/run_phase8d_hypothesis_queue.py
./.venv/Scripts/python.exe scripts/run_phase8e_event_scout.py
```

Run focused ad-hoc verification if Hermes guard requests it.

Final handoff should include:

- changed files,
- generated outputs/reports/artifacts,
- exact commands and exit codes,
- top surviving ideas,
- explicit parked/rejected ideas,
- next recommended milestone,
- whether commit is recommended.

---

## If Running Autonomously

Use three parallel workstreams where possible:

1. **Worker A — Phase 8C filters:** implement/test/run no-trade diagnostics.
2. **Worker B — Hypothesis queue + event scout:** build broad queue and cheap event-study ranking.
3. **Worker C — Review/verification:** inspect guardrails, artifacts, tests, and lookahead risks.

Do not let any worker commit or push unless the user explicitly approves. Each worker must return file paths, commands, exit codes, and blockers.

## Recommended Outcome For This Block

Best realistic outcome after 7 hours:

- Phase 8C tells us whether no-trade filters are promising.
- We have a ranked, diverse strategy hypothesis queue.
- We have cheap event-study evidence across many ideas.
- We backtest at most 3 diverse candidates.
- We stop spending hours manually tuning one rejected strategy.
