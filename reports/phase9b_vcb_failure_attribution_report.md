# Phase 9B MNQ VCB Failure Attribution

Diagnostic only. No live trading, broker adapters, order routing, API-key storage, webhooks, automated execution, or candidate promotion.

## Summary

- Specs evaluated: `48`
- Trade rows: `8158`
- Next action recommendation: `phase9c_targeted_retest_only`
- Rationale: Phase 9B found at least one bounded diagnostic axis that is less-bad/positive; retest only that axis, not a broad expansion.

## Candidate Snapshot

| Candidate | TF | Method | Direction | Entry | Trades | Net | Stress | Holdout | Avg MFE | Avg MAE | Stop % | Target % |
| --- | ---: | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `MNQ_vcb_tf5_realized_vol_percentile_lb8_q02_short_only_target15R_mt2_gap30_first10_keep1000` | 5 | realized_vol_percentile | short_only | next_bar_close | 204 | $3727.29 | $3523.29 | $915.34 | $138.46 | $108.90 | 9.3% | 7.8% |
| `MNQ_vcb_tf5_atr_percentile_lb8_q02_short_only_target15R_mt2_gap30_first10_keep1000` | 5 | atr_percentile | short_only | next_bar_close | 226 | $3385.76 | $3159.76 | $1800.88 | $134.97 | $104.37 | 11.1% | 6.2% |
| `MNQ_vcb_tf5_realized_vol_percentile_lb12_q02_short_only_target20R_mt2_gap30_first10_keep1000` | 5 | realized_vol_percentile | short_only | next_bar_close | 172 | $3212.22 | $3040.22 | $2653.54 | $136.97 | $103.81 | 6.4% | 0.6% |
| `MNQ_vcb_tf5_realized_vol_percentile_lb12_q02_short_only_target20R_mt2_gap30_first10_keep1000` | 5 | realized_vol_percentile | short_only | next_bar_open | 172 | $3037.22 | $2865.22 | $1897.04 | $132.86 | $105.52 | 6.4% | 1.2% |
| `MNQ_vcb_tf15_range_percentile_lb12_q025_short_only_target20R_mt2_gap60_first10_keep1000` | 15 | range_percentile | short_only | next_bar_close | 66 | $2848.16 | $2782.16 | $1580.66 | $152.90 | $106.11 | 0.0% | 0.0% |
| `MNQ_vcb_tf5_realized_vol_percentile_lb8_q02_short_only_target15R_mt2_gap30_first10_keep1000` | 5 | realized_vol_percentile | short_only | next_bar_open | 204 | $2913.04 | $2709.04 | $1079.34 | $137.49 | $107.99 | 10.3% | 4.4% |
| `MNQ_vcb_tf15_range_percentile_lb8_q025_short_only_target15R_mt2_gap60_first10_keep1000` | 15 | range_percentile | short_only | next_bar_open | 87 | $2553.37 | $2466.37 | $1824.42 | $155.93 | $110.69 | 1.1% | 2.3% |
| `MNQ_vcb_tf15_range_percentile_lb8_q025_short_only_target15R_mt2_gap60_first10_keep1000` | 15 | range_percentile | short_only | next_bar_close | 87 | $2533.37 | $2446.37 | $1744.92 | $154.74 | $113.91 | 0.0% | 2.3% |
| `MNQ_vcb_tf15_atr_percentile_lb8_q02_short_only_target15R_mt2_gap60_first10_keep1000` | 15 | atr_percentile | short_only | next_bar_close | 107 | $2475.82 | $2368.82 | $1302.68 | $145.81 | $101.14 | 0.0% | 2.8% |
| `MNQ_vcb_tf5_realized_vol_percentile_lb8_q02_long_only_target15R_mt2_gap30_first10_keep1000` | 5 | realized_vol_percentile | long_only | next_bar_open | 244 | $2600.19 | $2356.19 | $5.09 | $89.79 | $78.19 | 5.7% | 1.2% |
| `MNQ_vcb_tf15_range_percentile_lb12_q025_short_only_target20R_mt2_gap60_first10_keep1000` | 15 | range_percentile | short_only | next_bar_open | 66 | $2386.16 | $2320.16 | $1557.66 | $145.90 | $113.11 | 0.0% | 0.0% |
| `MNQ_vcb_tf5_atr_percentile_lb12_q02_short_only_target20R_mt2_gap30_first10_keep1000` | 5 | atr_percentile | short_only | next_bar_open | 200 | $2360.50 | $2160.50 | $1018.08 | $132.42 | $110.20 | 6.5% | 1.5% |

## Side Attribution

| group | trades | net_pnl | stress_pnl | win_rate | profit_factor | avg_mfe | avg_mae | target_hit_rate | stop_hit_rate | same_bar_ambiguity_rate |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| short_only | 3230 | 35932.0500 | 32702.0500 | 0.4876 | 1.2046 | 137.1900 | 112.9000 | 0.0300 | 0.0560 | 0.0006 |
| long_only | 4928 | 13579.7800 | 8651.7800 | 0.5446 | 1.0735 | 86.8600 | 86.7400 | 0.0081 | 0.0461 | 0.0004 |

## Time Bucket Attribution

| group | trades | net_pnl | stress_pnl | win_rate | profit_factor | avg_mfe | avg_mae | target_hit_rate | stop_hit_rate | same_bar_ambiguity_rate |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 10:30-11:30 | 2012 | 33693.8700 | 31681.8700 | 0.5910 | 1.3609 | 125.0600 | 112.3300 | 0.0239 | 0.0398 | 0.0010 |
| 11:30-13:30 | 3114 | 17227.3900 | 14113.3900 | 0.5083 | 1.1292 | 103.4500 | 92.7500 | 0.0186 | 0.0491 | 0.0000 |
| 10:00-10:30 | 564 | 4683.8900 | 4119.8900 | 0.5213 | 1.1294 | 146.4100 | 138.5400 | 0.0089 | 0.0479 | 0.0000 |
| 09:30-10:00 | 42 | -746.0800 | -788.0800 | 0.5238 | 0.7802 | 125.2400 | 149.3600 | 0.0238 | 0.1905 | 0.0000 |
| 13:30-15:45 | 2426 | -5347.2400 | -7773.2400 | 0.4827 | 0.9432 | 86.3900 | 79.5000 | 0.0103 | 0.0577 | 0.0008 |

## Exit Reason Attribution

| group | trades | net_pnl | stress_pnl | win_rate | profit_factor | avg_mfe | avg_mae | target_hit_rate | stop_hit_rate | same_bar_ambiguity_rate |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| time_stop | 6785 | 95832.6000 | 89047.6000 | 0.5528 | 1.3736 | 109.1500 | 94.4600 | 0.0000 | 0.0000 | 0.0000 |
| target | 137 | 30163.8700 | 30026.8700 | 1.0000 | 999.0000 | 274.1200 | 25.8000 | 1.0000 | 0.0000 | 0.0000 |
| session_flatten | 828 | 4547.2800 | 3719.2800 | 0.4457 | 1.1995 | 85.5800 | 62.9300 | 0.0000 | 0.0000 | 0.0000 |
| stop_same_bar_conservative | 4 | 6.0400 | 2.0400 | 0.5000 | 1.0967 | 253.7500 | 24.2500 | 0.0000 | 1.0000 | 1.0000 |
| stop | 404 | -81037.9600 | -81441.9600 | 0.0000 | 0.0000 | 52.4400 | 236.2500 | 0.0000 | 1.0000 | 0.0000 |

## Entry Timing Attribution

| group | trades | net_pnl | stress_pnl | win_rate | profit_factor | avg_mfe | avg_mae | target_hit_rate | stop_hit_rate | same_bar_ambiguity_rate |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| next_bar_close | 4079 | 31725.0400 | 27646.0400 | 0.5210 | 1.1901 | 108.3400 | 95.5200 | 0.0201 | 0.0485 | 0.0010 |
| next_bar_open | 4079 | 17786.7900 | 13707.7900 | 0.5232 | 1.0919 | 105.2400 | 98.6700 | 0.0135 | 0.0515 | 0.0000 |

## Stop/Target Geometry Attribution

| group | trades | net_pnl | stress_pnl | win_rate | profit_factor | avg_mfe | avg_mae | target_hit_rate | stop_hit_rate | same_bar_ambiguity_rate |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| time_or_flatten | 7613 | 100379.8800 | 92766.8800 | 0.5412 | 1.3594 | 106.5800 | 91.0300 | 0.0000 | 0.0000 | 0.0000 |
| target_hit | 137 | 30163.8700 | 30026.8700 | 1.0000 | 999.0000 | 274.1200 | 25.8000 | 1.0000 | 0.0000 | 0.0000 |
| stopped_after_favorable_move | 14 | -1120.8600 | -1134.8600 | 0.1429 | 0.0576 | 174.1100 | 92.1400 | 0.0000 | 1.0000 | 0.2857 |
| quick_or_adverse_stop | 394 | -79911.0600 | -80305.0600 | 0.0000 | 0.0000 | 50.1600 | 239.2100 | 0.0000 | 1.0000 | 0.0000 |

## Outputs

- `outputs/phase9b_trade_attribution.csv`
- `outputs/phase9b_side_summary.csv`
- `outputs/phase9b_time_bucket_summary.csv`
- `outputs/phase9b_exit_reason_summary.csv`
- `outputs/phase9b_session_loss_summary.csv`
- `outputs/phase9b_mfe_mae_summary.csv`
- `outputs/phase9b_entry_timing_diagnostic.csv`
- `outputs/phase9b_stop_target_diagnostic.csv`
- `outputs/phase9b_next_action_recommendation.json`
- `C:/Users/ulzii/Documents/Short Term Strategy Discovery/reports/phase9b_vcb_failure_attribution_report.md`
