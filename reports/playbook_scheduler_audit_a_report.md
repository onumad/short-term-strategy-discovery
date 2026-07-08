# Playbook Scheduler Audit A — Priority / Overlap / Regime Filter Diagnostic

Research/simulation only. No live trading, broker adapters, order routing, webhooks, credential storage, automated execution, or LLM-driven trade decisions.

Diagnostic only. This audit uses existing module trade logs and Portfolio Audit D / Weak Fold Regime Audit B outputs only. It does not generate new signals, run strategy searches, change candidate results, change official gates, promote candidates, approve paper trading, or add live-trading functionality.

## Summary

- Scheduler variants tested: `existing_priority_baseline, phase15a_first, phase14a_first, phase13a_first, phase10b_first, rare_setup_first, lowest_correlation_first, highest_recent_validation_first`
- Modes tested: `one_trade_at_a_time_chronological, max_one_trade_per_session`
- Diagnostic regime filters tested: `exclude_high_vol_mixed_days, exclude_high_vol_mixed_power_expand_days, exclude_high_vol_mixed_no_power_expand_days, exclude_overlap_heavy_days, no_filter_baseline`
- Best scheduler/filter result: `existing_priority_baseline` / `max_one_trade_per_session` / `exclude_overlap_heavy_days` net `1683.34` positive folds `0.833`
- Next action: `playbook_scheduler_b_priority_retest`
- Rationale: At least one diagnostic priority change improved fold stability or concentration versus the Portfolio Audit D scheduler baseline.
- Paper trading approved: `false`

## Top scheduler/filter rows

| Variant | Mode | Filter | Net | Active days | Trades | Pos folds | Worst fold | Max DD | Best-day conc | Best-trade conc | Skipped overlap | Skipped session | Weak folds | Δ vs Audit D best |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| existing_priority_baseline | max_one_trade_per_session | exclude_overlap_heavy_days | 1683.34 | 46 | 46 | 0.833 | -266.63 | -344.61 | 0.244 | 0.244 | 0 | 5 | 1 | -2025.18 |
| highest_recent_validation_first | max_one_trade_per_session | exclude_overlap_heavy_days | 1683.34 | 46 | 46 | 0.833 | -266.63 | -344.61 | 0.244 | 0.244 | 0 | 5 | 1 | -2025.18 |
| lowest_correlation_first | max_one_trade_per_session | exclude_overlap_heavy_days | 1683.34 | 46 | 46 | 0.833 | -266.63 | -344.61 | 0.244 | 0.244 | 0 | 5 | 1 | -2025.18 |
| phase10b_first | max_one_trade_per_session | exclude_overlap_heavy_days | 1683.34 | 46 | 46 | 0.833 | -266.63 | -344.61 | 0.244 | 0.244 | 0 | 5 | 1 | -2025.18 |
| phase13a_first | max_one_trade_per_session | exclude_overlap_heavy_days | 1683.34 | 46 | 46 | 0.833 | -266.63 | -344.61 | 0.244 | 0.244 | 0 | 5 | 1 | -2025.18 |
| phase14a_first | max_one_trade_per_session | exclude_overlap_heavy_days | 1683.34 | 46 | 46 | 0.833 | -266.63 | -344.61 | 0.244 | 0.244 | 0 | 5 | 1 | -2025.18 |
| phase15a_first | max_one_trade_per_session | exclude_overlap_heavy_days | 1683.34 | 46 | 46 | 0.833 | -266.63 | -344.61 | 0.244 | 0.244 | 0 | 5 | 1 | -2025.18 |
| rare_setup_first | max_one_trade_per_session | exclude_overlap_heavy_days | 1683.34 | 46 | 46 | 0.833 | -266.63 | -344.61 | 0.244 | 0.244 | 0 | 5 | 1 | -2025.18 |
| existing_priority_baseline | one_trade_at_a_time_chronological | exclude_overlap_heavy_days | 1631.64 | 46 | 51 | 0.833 | -266.63 | -354.61 | 0.252 | 0.252 | 0 | 0 | 1 | -6434.97 |
| highest_recent_validation_first | one_trade_at_a_time_chronological | exclude_overlap_heavy_days | 1631.64 | 46 | 51 | 0.833 | -266.63 | -354.61 | 0.252 | 0.252 | 0 | 0 | 1 | -6434.97 |
| lowest_correlation_first | one_trade_at_a_time_chronological | exclude_overlap_heavy_days | 1631.64 | 46 | 51 | 0.833 | -266.63 | -354.61 | 0.252 | 0.252 | 0 | 0 | 1 | -6434.97 |
| phase10b_first | one_trade_at_a_time_chronological | exclude_overlap_heavy_days | 1631.64 | 46 | 51 | 0.833 | -266.63 | -354.61 | 0.252 | 0.252 | 0 | 0 | 1 | -6434.97 |
| phase13a_first | one_trade_at_a_time_chronological | exclude_overlap_heavy_days | 1631.64 | 46 | 51 | 0.833 | -266.63 | -354.61 | 0.252 | 0.252 | 0 | 0 | 1 | -6434.97 |
| phase14a_first | one_trade_at_a_time_chronological | exclude_overlap_heavy_days | 1631.64 | 46 | 51 | 0.833 | -266.63 | -354.61 | 0.252 | 0.252 | 0 | 0 | 1 | -6434.97 |
| phase15a_first | one_trade_at_a_time_chronological | exclude_overlap_heavy_days | 1631.64 | 46 | 51 | 0.833 | -266.63 | -354.61 | 0.252 | 0.252 | 0 | 0 | 1 | -6434.97 |
| rare_setup_first | one_trade_at_a_time_chronological | exclude_overlap_heavy_days | 1631.64 | 46 | 51 | 0.833 | -266.63 | -354.61 | 0.252 | 0.252 | 0 | 0 | 1 | -6434.97 |
| highest_recent_validation_first | one_trade_at_a_time_chronological | exclude_high_vol_mixed_power_expand_days | 8519.79 | 219 | 596 | 0.667 | -356.70 | -1257.55 | 0.103 | 0.087 | 86 | 0 | 2 | 453.18 |
| phase10b_first | one_trade_at_a_time_chronological | exclude_high_vol_mixed_power_expand_days | 8519.79 | 219 | 596 | 0.667 | -356.70 | -1257.55 | 0.103 | 0.087 | 86 | 0 | 2 | 453.18 |
| existing_priority_baseline | one_trade_at_a_time_chronological | exclude_high_vol_mixed_power_expand_days | 8440.55 | 219 | 597 | 0.667 | -356.70 | -1257.55 | 0.104 | 0.088 | 85 | 0 | 2 | 373.94 |
| phase13a_first | one_trade_at_a_time_chronological | exclude_high_vol_mixed_power_expand_days | 8440.55 | 219 | 597 | 0.667 | -356.70 | -1257.55 | 0.104 | 0.088 | 85 | 0 | 2 | 373.94 |

## Regime filter diagnostics

Diagnostic filters are not promotion filters or live rules.

| regime_filter | scheduler_variant | portfolio_mode | excluded_day_count | accepted_trades_after_filter | active_days_after_filter | net_pnl_after_filter | rejected_trade_count_after_scheduler | diagnostic_only_not_live_rule |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| exclude_high_vol_mixed_days | existing_priority_baseline | max_one_trade_per_session | 134 | 179 | 179 | 2682.86 | 395 | True |
| exclude_high_vol_mixed_days | existing_priority_baseline | one_trade_at_a_time_chronological | 134 | 505 | 179 | 5078.97 | 69 | True |
| exclude_high_vol_mixed_days | highest_recent_validation_first | max_one_trade_per_session | 134 | 179 | 179 | 2682.86 | 395 | True |
| exclude_high_vol_mixed_days | highest_recent_validation_first | one_trade_at_a_time_chronological | 134 | 504 | 179 | 5158.21 | 70 | True |
| exclude_high_vol_mixed_days | lowest_correlation_first | max_one_trade_per_session | 134 | 179 | 179 | 2641.36 | 395 | True |
| exclude_high_vol_mixed_days | lowest_correlation_first | one_trade_at_a_time_chronological | 134 | 505 | 179 | 4888.47 | 69 | True |
| exclude_high_vol_mixed_days | phase10b_first | max_one_trade_per_session | 134 | 179 | 179 | 2682.86 | 395 | True |
| exclude_high_vol_mixed_days | phase10b_first | one_trade_at_a_time_chronological | 134 | 504 | 179 | 5158.21 | 70 | True |
| exclude_high_vol_mixed_days | phase13a_first | max_one_trade_per_session | 134 | 179 | 179 | 2682.86 | 395 | True |
| exclude_high_vol_mixed_days | phase13a_first | one_trade_at_a_time_chronological | 134 | 505 | 179 | 5078.97 | 69 | True |
| exclude_high_vol_mixed_days | phase14a_first | max_one_trade_per_session | 134 | 179 | 179 | 2682.86 | 395 | True |
| exclude_high_vol_mixed_days | phase14a_first | one_trade_at_a_time_chronological | 134 | 505 | 179 | 5078.97 | 69 | True |
| exclude_high_vol_mixed_days | phase15a_first | max_one_trade_per_session | 134 | 179 | 179 | 2682.86 | 395 | True |
| exclude_high_vol_mixed_days | phase15a_first | one_trade_at_a_time_chronological | 134 | 505 | 179 | 5078.97 | 69 | True |
| exclude_high_vol_mixed_days | rare_setup_first | max_one_trade_per_session | 134 | 179 | 179 | 2682.86 | 395 | True |
| exclude_high_vol_mixed_days | rare_setup_first | one_trade_at_a_time_chronological | 134 | 505 | 179 | 5078.97 | 69 | True |
| exclude_high_vol_mixed_no_power_expand_days | existing_priority_baseline | max_one_trade_per_session | 81 | 205 | 205 | 1504.24 | 462 | True |
| exclude_high_vol_mixed_no_power_expand_days | existing_priority_baseline | one_trade_at_a_time_chronological | 81 | 587 | 205 | 4705.03 | 80 | True |
| exclude_high_vol_mixed_no_power_expand_days | highest_recent_validation_first | max_one_trade_per_session | 81 | 205 | 205 | 1614.74 | 462 | True |
| exclude_high_vol_mixed_no_power_expand_days | highest_recent_validation_first | one_trade_at_a_time_chronological | 81 | 585 | 205 | 4914.51 | 82 | True |
| exclude_high_vol_mixed_no_power_expand_days | lowest_correlation_first | max_one_trade_per_session | 81 | 205 | 205 | 1990.24 | 462 | True |
| exclude_high_vol_mixed_no_power_expand_days | lowest_correlation_first | one_trade_at_a_time_chronological | 81 | 585 | 205 | 4797.51 | 82 | True |
| exclude_high_vol_mixed_no_power_expand_days | phase10b_first | max_one_trade_per_session | 81 | 205 | 205 | 1504.24 | 462 | True |
| exclude_high_vol_mixed_no_power_expand_days | phase10b_first | one_trade_at_a_time_chronological | 81 | 586 | 205 | 4784.27 | 81 | True |
| exclude_high_vol_mixed_no_power_expand_days | phase13a_first | max_one_trade_per_session | 81 | 205 | 205 | 1504.24 | 462 | True |
| exclude_high_vol_mixed_no_power_expand_days | phase13a_first | one_trade_at_a_time_chronological | 81 | 587 | 205 | 4705.03 | 80 | True |
| exclude_high_vol_mixed_no_power_expand_days | phase14a_first | max_one_trade_per_session | 81 | 205 | 205 | 1504.24 | 462 | True |
| exclude_high_vol_mixed_no_power_expand_days | phase14a_first | one_trade_at_a_time_chronological | 81 | 587 | 205 | 4705.03 | 80 | True |
| exclude_high_vol_mixed_no_power_expand_days | phase15a_first | max_one_trade_per_session | 81 | 205 | 205 | 1504.24 | 462 | True |
| exclude_high_vol_mixed_no_power_expand_days | phase15a_first | one_trade_at_a_time_chronological | 81 | 587 | 205 | 4705.03 | 80 | True |

## Overlap diagnostics

| scheduler_variant | portfolio_mode | regime_filter | accepted_trades | skipped_overlap_count | skipped_session_count | rejected_positive_trade_count | rejected_positive_pnl | early_losing_module_when_later_module_helped_days |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| existing_priority_baseline | max_one_trade_per_session | exclude_high_vol_mixed_days | 179 | 0 | 395 | 151 | 14956.01 | 0 |
| existing_priority_baseline | max_one_trade_per_session | exclude_high_vol_mixed_no_power_expand_days | 205 | 0 | 462 | 176 | 18671.26 | 0 |
| existing_priority_baseline | max_one_trade_per_session | exclude_high_vol_mixed_power_expand_days | 219 | 0 | 463 | 180 | 18828.55 | 0 |
| existing_priority_baseline | max_one_trade_per_session | exclude_overlap_heavy_days | 46 | 0 | 5 | 1 | 95.76 | 0 |
| existing_priority_baseline | max_one_trade_per_session | no_filter_baseline | 245 | 0 | 530 | 205 | 22543.8 | 0 |
| existing_priority_baseline | one_trade_at_a_time_chronological | exclude_high_vol_mixed_days | 505 | 69 | 0 | 27 | 2781.02 | 38 |
| existing_priority_baseline | one_trade_at_a_time_chronological | exclude_high_vol_mixed_no_power_expand_days | 587 | 80 | 0 | 30 | 3096.8 | 47 |
| existing_priority_baseline | one_trade_at_a_time_chronological | exclude_high_vol_mixed_power_expand_days | 597 | 85 | 0 | 32 | 3514.32 | 48 |
| existing_priority_baseline | one_trade_at_a_time_chronological | exclude_overlap_heavy_days | 51 | 0 | 0 | 0 | 0.0 | 0 |
| existing_priority_baseline | one_trade_at_a_time_chronological | no_filter_baseline | 679 | 96 | 0 | 35 | 3830.1 | 57 |
| highest_recent_validation_first | max_one_trade_per_session | exclude_high_vol_mixed_days | 179 | 0 | 395 | 151 | 14956.01 | 0 |
| highest_recent_validation_first | max_one_trade_per_session | exclude_high_vol_mixed_no_power_expand_days | 205 | 0 | 462 | 176 | 18671.26 | 0 |
| highest_recent_validation_first | max_one_trade_per_session | exclude_high_vol_mixed_power_expand_days | 219 | 0 | 463 | 180 | 18828.55 | 0 |
| highest_recent_validation_first | max_one_trade_per_session | exclude_overlap_heavy_days | 46 | 0 | 5 | 1 | 95.76 | 0 |
| highest_recent_validation_first | max_one_trade_per_session | no_filter_baseline | 245 | 0 | 530 | 205 | 22543.8 | 0 |
| highest_recent_validation_first | one_trade_at_a_time_chronological | exclude_high_vol_mixed_days | 504 | 70 | 0 | 27 | 2781.02 | 38 |
| highest_recent_validation_first | one_trade_at_a_time_chronological | exclude_high_vol_mixed_no_power_expand_days | 585 | 82 | 0 | 30 | 3096.8 | 47 |
| highest_recent_validation_first | one_trade_at_a_time_chronological | exclude_high_vol_mixed_power_expand_days | 596 | 86 | 0 | 32 | 3514.32 | 48 |
| highest_recent_validation_first | one_trade_at_a_time_chronological | exclude_overlap_heavy_days | 51 | 0 | 0 | 0 | 0.0 | 0 |
| highest_recent_validation_first | one_trade_at_a_time_chronological | no_filter_baseline | 677 | 98 | 0 | 35 | 3830.1 | 57 |
| lowest_correlation_first | max_one_trade_per_session | exclude_high_vol_mixed_days | 179 | 0 | 395 | 152 | 14970.27 | 0 |
| lowest_correlation_first | max_one_trade_per_session | exclude_high_vol_mixed_no_power_expand_days | 205 | 0 | 462 | 176 | 18421.26 | 0 |
| lowest_correlation_first | max_one_trade_per_session | exclude_high_vol_mixed_power_expand_days | 219 | 0 | 463 | 181 | 18842.81 | 0 |
| lowest_correlation_first | max_one_trade_per_session | exclude_overlap_heavy_days | 46 | 0 | 5 | 1 | 95.76 | 0 |
| lowest_correlation_first | max_one_trade_per_session | no_filter_baseline | 245 | 0 | 530 | 205 | 22293.8 | 0 |
| lowest_correlation_first | one_trade_at_a_time_chronological | exclude_high_vol_mixed_days | 505 | 69 | 0 | 28 | 2924.28 | 38 |
| lowest_correlation_first | one_trade_at_a_time_chronological | exclude_high_vol_mixed_no_power_expand_days | 585 | 82 | 0 | 31 | 3240.06 | 46 |
| lowest_correlation_first | one_trade_at_a_time_chronological | exclude_high_vol_mixed_power_expand_days | 597 | 85 | 0 | 33 | 3657.58 | 48 |
| lowest_correlation_first | one_trade_at_a_time_chronological | exclude_overlap_heavy_days | 51 | 0 | 0 | 0 | 0.0 | 0 |
| lowest_correlation_first | one_trade_at_a_time_chronological | no_filter_baseline | 677 | 98 | 0 | 36 | 3973.36 | 56 |

## Guardrails

Official gates changed: `false`.
Paper trading approved: `false`.
New strategy signals generated: `false`.
Live trading approved: `false`.
