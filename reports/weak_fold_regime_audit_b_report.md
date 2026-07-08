# Weak Fold Regime Audit B — Portfolio Weak-Fold / Bad-Regime Diagnostic

Research/simulation only. No live trading, broker adapters, order routing, webhooks, credential storage, automated execution, or LLM-driven trade decisions.

Diagnostic only. No new signals generated, no strategy searches run, no candidate results changed, no official gates changed, no promotions, and no paper trading approval.

## Summary

- Weak folds identified: `163`
- Weak-fold day rows: `5921`
- Candidate remedy briefs: `3`
- Next action: `phase16a_targeted_regime_module_scout`
- Rationale: Weak folds cluster around identifiable market-regime feature differences.
- Paper trading approved: `false`

## Fold failure map

| Audit | Portfolio | Mode | Fold | Start | End | PnL | Stress PnL | Active Days | Same fold weak across B/C/D |
| --- | --- | --- | ---: | --- | --- | ---: | ---: | ---: | --- |
| B | audit_a_best_plus_phase13a | max_one_trade_per_session | 1 | 2025-07-15 | 2025-09-09 | -225.33 | -264.33 | 39 | True |
| B | top_cross_family_plus_phase13a | max_one_trade_per_session | 1 | 2025-07-14 | 2025-09-08 | -1152.96 | -1191.96 | 39 | True |
| B | diversifier_only_phase13a | max_one_trade_per_session | 1 | 2025-07-15 | 2025-09-04 | -13.14 | -33.14 | 20 | True |
| B | all_parked_modules_with_phase13a | max_one_trade_per_session | 1 | 2025-07-14 | 2025-09-11 | -962.89 | -1002.89 | 40 | True |
| B | rare_plus_diversifier_modules | max_one_trade_per_session | 1 | 2025-07-15 | 2025-09-10 | -265.39 | -298.39 | 33 | True |
| B | greedy_low_correlation_with_phase13a | max_one_trade_per_session | 1 | 2025-07-14 | 2025-09-08 | -920.67 | -960.67 | 40 | True |
| B | rare_plus_diversifier_modules | max_one_trade_per_session | 2 | 2025-09-11 | 2025-11-13 | -213.63 | -246.63 | 33 | True |
| B | audit_a_best_plus_phase13a | max_one_trade_per_session | 3 | 2025-11-06 | 2026-01-06 | -867.79 | -906.79 | 39 | True |
| B | top_cross_family_plus_phase13a | max_one_trade_per_session | 3 | 2025-11-05 | 2026-01-06 | -117.89 | -156.89 | 39 | True |
| B | diversifier_only_phase13a | max_one_trade_per_session | 3 | 2025-10-28 | 2026-01-09 | -967.61 | -987.61 | 20 | True |
| B | all_parked_modules_with_phase13a | max_one_trade_per_session | 3 | 2025-11-11 | 2026-01-08 | -546.63 | -586.63 | 40 | True |
| B | rare_plus_diversifier_modules | max_one_trade_per_session | 3 | 2025-11-14 | 2026-01-21 | -346.19 | -379.19 | 33 | True |
| B | greedy_low_correlation_with_phase13a | max_one_trade_per_session | 3 | 2025-11-05 | 2026-01-02 | -411.13 | -451.13 | 40 | True |
| B | audit_a_best_reconstructed | max_one_trade_per_session | 4 | 2026-01-06 | 2026-02-25 | -492.42 | -525.42 | 33 | True |
| B | top_cross_family_plus_phase13a | max_one_trade_per_session | 4 | 2026-01-07 | 2026-03-02 | -475.13 | -514.13 | 39 | True |
| B | all_parked_modules_with_phase13a | max_one_trade_per_session | 4 | 2026-01-09 | 2026-03-06 | -375.03 | -415.03 | 40 | True |
| B | greedy_low_correlation_with_phase13a | max_one_trade_per_session | 4 | 2026-01-05 | 2026-02-27 | -667.14 | -707.14 | 40 | True |
| B | audit_a_best_reconstructed | one_trade_at_a_time_chronological | 1 | 2025-07-15 | 2025-09-10 | -82.11 | -115.11 | 33 | True |
| B | audit_a_best_plus_phase13a | one_trade_at_a_time_chronological | 1 | 2025-07-15 | 2025-09-09 | -379.80 | -418.80 | 39 | True |
| B | top_cross_family_plus_phase13a | one_trade_at_a_time_chronological | 1 | 2025-07-14 | 2025-09-08 | -1236.61 | -1275.61 | 39 | True |
| B | diversifier_only_phase13a | one_trade_at_a_time_chronological | 1 | 2025-07-15 | 2025-09-04 | -13.14 | -33.14 | 20 | True |
| B | all_parked_modules_with_phase13a | one_trade_at_a_time_chronological | 1 | 2025-07-14 | 2025-09-11 | -2592.81 | -2632.81 | 40 | True |
| B | rare_plus_diversifier_modules | one_trade_at_a_time_chronological | 1 | 2025-07-15 | 2025-09-10 | -255.91 | -288.91 | 33 | True |
| B | greedy_low_correlation_with_phase13a | one_trade_at_a_time_chronological | 1 | 2025-07-14 | 2025-09-08 | -1175.93 | -1215.93 | 40 | True |
| B | all_parked_modules_with_phase13a | one_trade_at_a_time_chronological | 2 | 2025-09-12 | 2025-11-10 | -485.50 | -525.50 | 40 | True |
| B | diversifier_only_phase13a | one_trade_at_a_time_chronological | 3 | 2025-10-28 | 2026-01-09 | -1143.03 | -1163.03 | 20 | True |
| B | rare_plus_diversifier_modules | one_trade_at_a_time_chronological | 3 | 2025-11-14 | 2026-01-21 | -563.00 | -596.00 | 33 | True |
| B | top_cross_family_plus_phase13a | one_trade_at_a_time_chronological | 4 | 2026-01-07 | 2026-03-02 | -122.43 | -161.43 | 39 | True |
| B | all_parked_modules_with_phase13a | one_trade_at_a_time_chronological | 4 | 2026-01-09 | 2026-03-06 | -609.13 | -649.13 | 40 | True |
| B | greedy_low_correlation_with_phase13a | one_trade_at_a_time_chronological | 4 | 2026-01-05 | 2026-02-27 | 28.04 | -11.96 | 40 | True |

## Market-regime comparison

| cohort | day_count | average_rth_range | average_close_position | trend_day_frequency | reversal_day_frequency | range_day_frequency | high_vol_frequency | low_vol_frequency | power_hour_expansion_frequency | lunch_compression_frequency | lunch_expansion_frequency | prior_level_interaction_frequency | no_trade_frequency | module_overlap_frequency |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| weak_fold_days | 248 | 346.350806 | 0.57401 | 0.419355 | 0.112903 | 0.104839 | 0.516129 | 0.145161 | 0.298387 | 0.004032 | 0.620968 | 0.915323 | 0.0 | 0.991935 |
| non_weak_fold_days | 0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |

## Module contribution findings

- phase14a prior RTH midpoint/close reaction: weak-fold contribution `797.97` across `108` active days.
- phase15a trend/power continuation: weak-fold contribution `1259.11` across `102` active days.
- phase12a opening-drive pullback: weak-fold contribution `1688.62` across `60` active days.
- phase13a prior RTH high/low breakout: weak-fold contribution `1762.00` across `123` active days.
- phase11a opening range fade: weak-fold contribution `3121.02` across `196` active days.
- phase10b overnight/prior-level branch: weak-fold contribution `35145.21` across `120` active days.

## Scheduler/overlap findings

- Weak-fold overlap-risk rows: `163`
- Weak-fold early-loss/later-help days: `1632`
- Weak-fold skipped overlaps at portfolio level: `25518`

## Candidate remedy briefs

- `no_trade_regime_filter` -> `phase16a_targeted_regime_module_scout` (strategy logic); evidence: Weak-fold market feature frequencies differ from non-weak days.
- `add_hedging/opposite-regime module` -> `phase16a_targeted_regime_module_scout` (strategy logic); evidence: Weak days show identifiable trend/range/volatility traits.
- `scheduler_priority_adjustment` -> `playbook_scheduler_a_priority_audit` (scheduler logic); evidence: Weak folds include overlapping module fire-days and/or scheduler skipped overlaps.
