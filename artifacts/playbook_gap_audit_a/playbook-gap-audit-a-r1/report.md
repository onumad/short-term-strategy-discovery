# Playbook Gap Audit A — Missing Days / Weak Fold Diagnostic

Research/simulation only. No live trading, broker adapters, order routing, webhooks, credential storage, automated execution, or LLM-driven trade decisions.

Diagnostic only. No signals generated, no strategy rules changed, no gate changes, no promotions, and no paper trading approval.

## Summary

- Weak folds: `44`
- Candidate module briefs: `4`
- Next action: `phase14a_targeted_gap_module_scout`
- Rationale: Weak/no-trade days cluster around prior_level_interaction_not_covered_by_phase13a.
- Paper trading approved: `false`

## Top Gap Summary

| Gap | Days | Evidence |
| --- | ---: | --- |
| prior_level_interaction_not_covered_by_phase13a | 673 | prior RTH level touched but Phase 13A did not cover |
| trend_days_with_no_module | 321 | trend proxy and no selected module coverage |
| power_hour_expansion_days_with_no_module | 274 | power-hour expansion and no coverage |
| low_volatility_expansion_days_with_no_module | 196 | low daily range with intraday expansion and no coverage |
| overlap_heavy_days | 147 | negative days where diversifier hurt/overlapped |
| range_days_with_no_module | 96 | range proxy and no selected module coverage |
| weak_folds_after_phase13a | 41 | weak folds where Phase 13A contributed |
| high_volatility_reversal_days_with_no_module | 0 | high range, range close, no coverage |

## Candidate Module Briefs

- `low_volatility_lunch_expansion` targets `low_volatility_expansion_days_with_no_module` via `range_expansion`; window `13:00-15:00`.
- `power_hour_continuation` targets `power_hour_expansion_days_with_no_module` via `trend_continuation`; window `14:30-15:45`.
- `previous_day_midpoint_reaction` targets `prior_level_interaction_not_covered_by_phase13a` via `prior_level_reaction`; window `10:00-14:30`.
- `trend_day_late_pullback_continuation` targets `trend_days_with_no_module` via `pullback_continuation`; window `13:30-15:30`.
