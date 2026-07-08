# Phase 10B Overnight Range Targeted Diagnostic Retest

Research/simulation only. No live trading, broker adapters, order routing, webhooks, credential storage, automated execution, or LLM-driven trade decisions.

## Summary

- Specs evaluated: `48`
- Trade rows: `2228`
- Label counts: `{'phase10b_rejected_low_activity': 34, 'phase10b_rejected_fold_instability': 14}`
- Research axis status counts: `{'axis_positive_but_concentrated': 40, 'axis_failed': 8}`
- Next action: `park_overnight_range_as_research_signal`
- Rationale: Phase 10B remained positive on some axes but failed promotion gates, usually concentration/fold/validation.

## Attribution Then Retest

Part A attributes Phase 10A-like targeted axes by validation, range/gap/touch, branch, exit reason, and MFE/MAE. Part B retests only pre-entry no-lookahead controls.

| Candidate | Status | Label | Net | Stress | Val | Holdout | WF Stress | Notes |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| `MNQ_10b_primary_short_midday_breakout_overnight_range_breakout_short_tf15_midday_response_exclude_widest_20_all_gaps_all_touches_mt1` | axis_positive_but_concentrated | phase10b_rejected_fold_instability | $2955.14 | $2877.14 | $334.40 | $811.84 | $1766.62 | fold instability; concentration |
| `MNQ_10b_primary_short_midday_breakout_overnight_range_breakout_short_tf15_midday_response_exclude_widest_20_all_gaps_all_touches_mt2` | axis_positive_but_concentrated | phase10b_rejected_fold_instability | $2955.14 | $2877.14 | $334.40 | $811.84 | $1766.62 | fold instability; concentration |
| `MNQ_10b_primary_short_midday_breakout_overnight_range_breakout_short_tf15_midday_response_all_ranges_all_gaps_all_touches_mt1` | axis_positive_but_concentrated | phase10b_rejected_fold_instability | $2730.48 | $2643.48 | $117.16 | $920.64 | $1624.18 | fold instability; concentration |
| `MNQ_10b_primary_short_midday_breakout_overnight_range_breakout_short_tf15_midday_response_all_ranges_all_gaps_all_touches_mt2` | axis_positive_but_concentrated | phase10b_rejected_fold_instability | $2730.48 | $2643.48 | $117.16 | $920.64 | $1624.18 | fold instability; concentration |
| `MNQ_10b_primary_short_midday_breakout_overnight_range_breakout_short_tf15_midday_response_middle_60_only_all_gaps_all_touches_mt1` | axis_positive_but_concentrated | phase10b_rejected_low_activity | $2517.19 | $2460.19 | $334.40 | $811.84 | $1929.34 | low activity; fold instability; concentration |
| `MNQ_10b_primary_short_midday_breakout_overnight_range_breakout_short_tf15_midday_response_middle_60_only_all_gaps_all_touches_mt2` | axis_positive_but_concentrated | phase10b_rejected_low_activity | $2517.19 | $2460.19 | $334.40 | $811.84 | $1929.34 | low activity; fold instability; concentration |
| `MNQ_10b_primary_short_midday_breakout_overnight_range_breakout_short_tf15_midday_response_middle_60_only_all_gaps_first_touch_only_mt1` | axis_positive_but_concentrated | phase10b_rejected_low_activity | $1943.33 | $1897.33 | $340.14 | $692.56 | $1929.02 | low activity; fold instability; concentration |
| `MNQ_10b_primary_short_midday_breakout_overnight_range_breakout_short_tf15_midday_response_middle_60_only_all_gaps_first_touch_only_mt2` | axis_positive_but_concentrated | phase10b_rejected_low_activity | $1943.33 | $1897.33 | $340.14 | $692.56 | $1929.02 | low activity; fold instability; concentration |
| `MNQ_10b_primary_short_midday_breakout_overnight_range_breakout_short_tf15_midday_response_exclude_narrowest_20_all_gaps_all_touches_mt1` | axis_positive_but_concentrated | phase10b_rejected_fold_instability | $2292.53 | $2226.53 | $117.16 | $920.64 | $1786.90 | fold instability; concentration |
| `MNQ_10b_primary_short_midday_breakout_overnight_range_breakout_short_tf15_midday_response_exclude_narrowest_20_all_gaps_all_touches_mt2` | axis_positive_but_concentrated | phase10b_rejected_fold_instability | $2292.53 | $2226.53 | $117.16 | $920.64 | $1786.90 | fold instability; concentration |
| `MNQ_10b_primary_short_midday_breakout_overnight_range_breakout_short_tf15_midday_response_exclude_narrowest_20_all_gaps_first_touch_only_mt1` | axis_positive_but_concentrated | phase10b_rejected_low_activity | $1752.41 | $1698.41 | $122.90 | $835.10 | $1821.32 | low activity; fold instability; concentration |
| `MNQ_10b_primary_short_midday_breakout_overnight_range_breakout_short_tf15_midday_response_exclude_narrowest_20_all_gaps_first_touch_only_mt2` | axis_positive_but_concentrated | phase10b_rejected_low_activity | $1752.41 | $1698.41 | $122.90 | $835.10 | $1821.32 | low activity; fold instability; concentration |
