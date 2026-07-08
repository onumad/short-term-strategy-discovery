# Phase 9C MNQ Short-Only VCB Targeted Retest

Research/simulation only. No live trading, broker adapters, order routing, webhooks, API-key storage, automated execution, or automatic paper-trading approval.

## Summary

- Specs evaluated: `48`
- Label counts: `{'phase9c_rejected_low_activity': 24, 'phase9c_rejected_negative_stress': 17, 'phase9c_rejected_negative_validation': 5, 'phase9c_rejected_fold_instability': 2}`
- Next action: `phase10a_overnight_range_breakout_fade`
- Rationale: Phase 9C failed validation/holdout/fold/concentration gates; kill compression breakout and pivot.

## Primary Eligible Branch: 10:30-13:30

| Candidate | Label | Net | Stress | Val | Holdout | WF Stress | Quick Stop % | Notes |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `MNQ_9c_vcb_tf15_range_percentile_lb12_q02_short_core_midday_close_confirm_fill_next_open_close_back_inside_box_invalidation_with_hard_cap` | phase9c_rejected_low_activity | $1878.46 | $1855.46 | $147.20 | $1556.59 | $1810.05 | 17.4% | low activity; fold instability; concentration; quick/adverse stops not reduced |
| `MNQ_9c_vcb_tf15_range_percentile_lb12_q02_short_core_midday_close_confirm_fill_next_open_capped_opposite_box_stop_time_exit` | phase9c_rejected_low_activity | $1830.92 | $1807.92 | $147.20 | $1513.09 | $1766.55 | 26.1% | low activity; fold instability; concentration; quick/adverse stops not reduced |
| `MNQ_9c_vcb_tf15_range_percentile_lb12_q02_short_core_midday_next_bar_open_capped_opposite_box_stop_time_exit` | phase9c_rejected_low_activity | $1620.83 | $1586.83 | $-141.93 | $1614.39 | $1710.98 | 29.4% | low activity; negative validation; fold instability; concentration; quick/adverse stops not reduced |
| `MNQ_9c_vcb_tf5_realized_vol_percentile_lb8_q02_short_core_midday_close_confirm_fill_next_open_capped_opposite_box_stop_time_exit` | phase9c_rejected_fold_instability | $1208.67 | $1072.68 | $41.98 | $174.20 | $396.61 | 50.0% | fold instability; concentration; quick/adverse stops not reduced |
| `MNQ_9c_vcb_tf15_realized_vol_percentile_lb12_q02_short_core_midday_close_confirm_fill_next_open_capped_opposite_box_stop_time_exit` | phase9c_rejected_low_activity | $697.44 | $679.44 | $27.60 | $278.52 | $279.52 | 11.1% | low activity; fold instability; concentration |
| `MNQ_9c_vcb_tf15_range_percentile_lb12_q02_short_core_midday_next_bar_open_close_back_inside_box_invalidation_with_hard_cap` | phase9c_rejected_low_activity | $1254.37 | $1220.37 | $-107.89 | $1487.39 | $1526.02 | 20.6% | low activity; negative validation; fold instability; concentration; quick/adverse stops not reduced |
| `MNQ_9c_vcb_tf15_realized_vol_percentile_lb12_q02_short_core_midday_close_confirm_fill_next_open_close_back_inside_box_invalidation_with_hard_cap` | phase9c_rejected_low_activity | $527.94 | $509.94 | $27.60 | $278.52 | $218.52 | 11.1% | low activity; fold instability; concentration |
| `MNQ_9c_vcb_tf5_atr_percentile_lb8_q02_short_core_midday_close_confirm_fill_next_open_capped_opposite_box_stop_time_exit` | phase9c_rejected_negative_validation | $980.43 | $818.44 | $-533.63 | $-111.90 | $-687.61 | 50.0% | negative validation; negative holdout; fold instability; concentration; quick/adverse stops not reduced |
| `MNQ_9c_vcb_tf15_realized_vol_percentile_lb12_q02_short_core_midday_next_bar_open_capped_opposite_box_stop_time_exit` | phase9c_rejected_low_activity | $458.89 | $430.89 | $-6.19 | $95.95 | $-31.96 | 32.1% | low activity; negative validation; fold instability; concentration; quick/adverse stops not reduced |
| `MNQ_9c_vcb_tf5_realized_vol_percentile_lb8_q02_short_core_midday_close_confirm_fill_next_open_close_back_inside_box_invalidation_with_hard_cap` | phase9c_rejected_fold_instability | $683.19 | $547.20 | $8.87 | $112.33 | $-3.05 | 38.2% | fold instability; concentration; quick/adverse stops not reduced |
| `MNQ_9c_vcb_tf5_atr_percentile_lb8_q02_short_core_midday_close_confirm_fill_next_open_close_back_inside_box_invalidation_with_hard_cap` | phase9c_rejected_negative_validation | $630.19 | $468.20 | $-665.25 | $212.85 | $-796.85 | 37.0% | negative validation; fold instability; concentration; quick/adverse stops not reduced |
| `MNQ_9c_vcb_tf15_atr_percentile_lb12_q02_short_core_midday_close_confirm_fill_next_open_capped_opposite_box_stop_time_exit` | phase9c_rejected_low_activity | $-166.91 | $-190.91 | $-49.64 | $-331.99 | $-512.47 | 25.0% | low activity; negative stress; negative validation; negative holdout; fold instability; concentration; quick/adverse stops not reduced |

## Diagnostic Branch: 10:00-13:30

| Candidate | Label | Net | Stress | Val | Holdout | WF Stress | Quick Stop % | Notes |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `MNQ_9c_vcb_tf15_range_percentile_lb12_q02_short_extended_midday_close_confirm_fill_next_open_close_back_inside_box_invalidation_with_hard_cap` | phase9c_rejected_low_activity | $1878.46 | $1855.46 | $147.20 | $1556.59 | $1810.05 | 17.4% | low activity; fold instability; concentration; quick/adverse stops not reduced |
| `MNQ_9c_vcb_tf15_range_percentile_lb12_q02_short_extended_midday_close_confirm_fill_next_open_capped_opposite_box_stop_time_exit` | phase9c_rejected_low_activity | $1830.92 | $1807.92 | $147.20 | $1513.09 | $1766.55 | 26.1% | low activity; fold instability; concentration; quick/adverse stops not reduced |
| `MNQ_9c_vcb_tf15_range_percentile_lb12_q02_short_extended_midday_next_bar_open_capped_opposite_box_stop_time_exit` | phase9c_rejected_low_activity | $1620.83 | $1586.83 | $-141.93 | $1614.39 | $1710.98 | 29.4% | low activity; negative validation; fold instability; concentration; quick/adverse stops not reduced |
| `MNQ_9c_vcb_tf15_realized_vol_percentile_lb12_q02_short_extended_midday_close_confirm_fill_next_open_capped_opposite_box_stop_time_exit` | phase9c_rejected_low_activity | $697.44 | $679.44 | $27.60 | $278.52 | $279.52 | 11.1% | low activity; fold instability; concentration |
| `MNQ_9c_vcb_tf15_range_percentile_lb12_q02_short_extended_midday_next_bar_open_close_back_inside_box_invalidation_with_hard_cap` | phase9c_rejected_low_activity | $1254.37 | $1220.37 | $-107.89 | $1487.39 | $1526.02 | 20.6% | low activity; negative validation; fold instability; concentration; quick/adverse stops not reduced |
| `MNQ_9c_vcb_tf15_realized_vol_percentile_lb12_q02_short_extended_midday_close_confirm_fill_next_open_close_back_inside_box_invalidation_with_hard_cap` | phase9c_rejected_low_activity | $527.94 | $509.94 | $27.60 | $278.52 | $218.52 | 11.1% | low activity; fold instability; concentration |
| `MNQ_9c_vcb_tf15_realized_vol_percentile_lb12_q02_short_extended_midday_next_bar_open_capped_opposite_box_stop_time_exit` | phase9c_rejected_low_activity | $458.89 | $430.89 | $-6.19 | $95.95 | $-31.96 | 32.1% | low activity; negative validation; fold instability; concentration; quick/adverse stops not reduced |
| `MNQ_9c_vcb_tf5_atr_percentile_lb8_q02_short_extended_midday_close_confirm_fill_next_open_capped_opposite_box_stop_time_exit` | phase9c_rejected_negative_validation | $818.35 | $637.36 | $-1129.33 | $512.82 | $-1058.42 | 49.7% | negative validation; fold instability; concentration; quick/adverse stops not reduced |
| `MNQ_9c_vcb_tf15_atr_percentile_lb12_q02_short_extended_midday_close_confirm_fill_next_open_capped_opposite_box_stop_time_exit` | phase9c_rejected_low_activity | $-166.91 | $-190.91 | $-49.64 | $-331.99 | $-512.47 | 25.0% | low activity; negative stress; negative validation; negative holdout; fold instability; concentration; quick/adverse stops not reduced |
| `MNQ_9c_vcb_tf15_atr_percentile_lb12_q02_short_extended_midday_close_confirm_fill_next_open_close_back_inside_box_invalidation_with_hard_cap` | phase9c_rejected_low_activity | $-240.79 | $-264.79 | $-49.64 | $-288.49 | $-637.47 | 12.5% | low activity; negative stress; negative validation; negative holdout; fold instability; concentration; quick/adverse stops not reduced |
| `MNQ_9c_vcb_tf15_atr_percentile_lb12_q02_short_extended_midday_next_bar_open_close_back_inside_box_invalidation_with_hard_cap` | phase9c_rejected_low_activity | $-420.42 | $-455.42 | $-66.10 | $-196.45 | $-519.75 | 22.9% | low activity; negative stress; negative validation; negative holdout; fold instability; concentration; quick/adverse stops not reduced |
| `MNQ_9c_vcb_tf15_atr_percentile_lb12_q02_short_extended_midday_next_bar_open_capped_opposite_box_stop_time_exit` | phase9c_rejected_low_activity | $-444.75 | $-479.75 | $-141.93 | $-311.45 | $-731.58 | 34.3% | low activity; negative stress; negative validation; negative holdout; fold instability; concentration; quick/adverse stops not reduced |

## Outputs

- `outputs/phase9c_candidate_results.csv`
- `outputs/phase9c_trade_logs.csv`
- `outputs/phase9c_walk_forward_folds.csv`
- `outputs/phase9c_daily_pnl.csv`
- `outputs/phase9c_concentration_diagnostics.csv`
- `outputs/phase9c_exit_reason_summary.csv`
- `outputs/phase9c_stop_failure_summary.csv`
- `outputs/phase9c_time_window_summary.csv`
- `outputs/phase9c_strategy_specs.json`
- `outputs/phase9c_next_action_recommendation.json`
- `C:/Users/ulzii/Documents/Short Term Strategy Discovery/artifacts/phase9c_vcb_targeted_retest/phase9c-r1-smoke/report.md`
