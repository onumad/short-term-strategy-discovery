# Phase 8 Research Pivot Summary

Generated after implementing the flexible seven-hour pivot plan.

## Scope And Guardrails

- Research/simulation only.
- No live trading approval.
- No broker adapters, order routing, API-key storage, webhooks, or automated execution were added.
- No LLM-driven trade decisions were added.

## What Changed

The workflow pivoted away from manually grinding one MGC entry variant and added four broader research stages:

1. **Phase 8C:** no-trade/session-selection diagnostic on existing Phase 8A trade paths.
2. **Phase 8D:** broad hypothesis queue across instruments, sides, timeframes, and families.
3. **Phase 8E:** cheap event-study scout across diverse hypotheses.
4. **Phase 8F:** bounded full backtest probe for at most three supported event-study survivors.

## Phase 8C No-Trade / Session Filters

Artifacts:

- `outputs/phase8c_no_trade_filter_results.csv`
- `reports/phase8c_no_trade_filter_report.md`
- `artifacts/phase8c_no_trade_filter/phase8c-r1-smoke/`

Key facts:

- Source candidates: `2` Phase 8A specs.
- Source trades replayed: `2539`.
- Filters tested: `9`.
- Labels: `{'rejected': 8, 'insufficient_activity': 1}`.
- Best-ranked filter: `time_window:last_90`, but it kept only `5` trades and remained negative.

Decision:

- Simple no-trade/time/side/day filters do **not** rescue the two currently scored MGC Phase 8A candidates.
- Do not spend more time trying to patch those two candidates with coarse filters.

## Phase 8D Broad Hypothesis Queue

Artifacts:

- `outputs/phase8d_hypothesis_queue.csv`
- `reports/phase8d_hypothesis_queue_report.md`
- `artifacts/phase8d_hypothesis_queue/phase8d-r1-smoke/`

Key facts:

- Hypotheses generated: `60`.
- Families represented: `12`.
- Includes `MGC` and `MNQ`.
- Includes `long_only`, `short_only`, and `both`.
- Includes non-1m timeframes.

This achieved the main user request: stop being trapped in one strategy and create a broader idea map.

## Phase 8E Cheap Event Scout

Artifacts:

- `outputs/phase8e_event_scout_results.csv`
- `reports/phase8e_event_scout_report.md`
- `artifacts/phase8e_event_scout/phase8e-r1-smoke/`

Key facts:

- Hypotheses scouted: `40`.
- Minimum event count: `50`.
- Label counts: `{'ambiguous': 18, 'needs_filter': 17, 'backtest_candidate': 5}`.
- Backtest candidates found: `5`.

Top event-study positives:

1. `MNQ_vwap_pullback_continuation_tf5_long_only_a25f2113`
2. `MNQ_vwap_reclaim_rejection_tf1_long_only_bdbad7c5`
3. `MNQ_volatility_compression_breakout_tf15_long_only_aea99b32`
4. `MNQ_volatility_compression_breakout_tf15_both_bef83121`
5. `MNQ_opening_range_fade_tf3_long_only_ad380f25`

Interpretation:

- The broad scan found interesting **event-level** forward behavior, mostly in MNQ.
- The signal is not automatically tradable; many event rows have high ambiguity proxies or need filters.

## Phase 8F Bounded Diverse Backtest Probe

Artifacts:

- `outputs/phase8f_diverse_candidate_probe_results.csv`
- `outputs/phase8f_diverse_candidate_specs.json`
- `reports/phase8f_diverse_candidate_probe_report.md`
- `artifacts/phase8f_diverse_candidate_probe/phase8f-r1-smoke/`

Key facts:

- Specs scored: `3`.
- Families scored:
  - `opening_range_failure`
  - `vwap_pullback_continuation`
  - `vwap_reclaim_rejection`
- Labels: `{'rejected': 3}`.

Results:

| Candidate | Net PnL | 4-Tick Stress | Trades | Active % | Max DD | Label |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| `MNQ_opening_range_failure_tf3_497a7aff68` | `$-2677.89` | `$-4990.89` | `771` | `61.5%` | `$-5879.88` | rejected |
| `MNQ_vwap_pullback_continuation_tf5_a08cca486b` | `$-3611.78` | `$-7052.78` | `1147` | `75.2%` | `$-3776.48` | rejected |
| `MNQ_vwap_reclaim_rejection_tf1_81bf62d078` | `$-3275.86` | `$-8042.86` | `1589` | `93.5%` | `$-3677.18` | rejected |

Decision:

- Cheap event-study positives did **not** survive the first actual execution/cost probe for the three supported candidates.
- That is useful: it shows the event scout is good for broad triage, but too coarse to trust as a trading edge.

## Final Decision

Do **not** keep digging into the two MGC Phase 8A candidates.

Do **not** immediately deepen the three rejected Phase 8F probes.

The next best milestone is:

```text
Phase 8G: event-to-execution calibration and richer broad-family scouting
```

Goal of Phase 8G:

- keep the broad multi-idea workflow,
- improve the gap between event-study positives and executable backtests,
- add more strategy families that are not currently representable by `StrategySpec`,
- explicitly separate:
  - event-level directional tendency,
  - executable entry timing,
  - stop/target placement,
  - costs/slippage,
  - ambiguity.

## Practical Next Step

Before another full backtest, build one of these:

1. **Event-to-execution calibration:** for each Phase 8E event, measure whether realistic next-bar entry, stop, and target choices erase the event edge.
2. **New family support:** add deterministic specs for volatility compression breakout and overnight range breakout/fade, since these showed event interest but were not supported by current executable `StrategySpec` mapping.
3. **MNQ-focused short/long decomposition:** Phase 8E says the strongest broad hints are MNQ-heavy; test side/timeframe/family decomposition before touching more MGC.

Recommended order:

```text
8G event-to-execution calibration -> new supported family specs -> only then bounded backtests
```
