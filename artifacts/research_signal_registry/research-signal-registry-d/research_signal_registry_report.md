# Research Signal Registry A — Two-Tier Labeling System

Research/simulation only. No live trading, broker adapters, order routing, webhooks, credential storage, automated execution, or LLM-driven trade decisions.

## Why Two-Tier Labeling Was Added

Framework Audit B/C found signals that can show positive bootstrap/outlier evidence while still failing tradability gates. The registry is additive and does not alter official phase labels or promotion gates.

## Signal Evidence vs Tradability

Signal evidence describes whether the historical rule appears better than noise. Tradability/practice readiness describes whether unchanged official gates allow review. A real-but-nontradable signal remains blocked from paper-review unless official gates pass.

## Parked Families

- opening_drive_first_pullback, opening_range_fade_confirmation, overnight_range_targeted_retest

## Priority For More Data

- none

## Paper Trading Status

No candidate is approved for paper trading. This registry only separates research evidence from tradability labels.

## Recommendation

- Next action: `maintain_two_tier_research_signal_registry`
- Rationale: Audit C supports separating signal evidence from tradability/practice readiness while preserving official gates.

## Registry

| Phase | Candidate | Evidence | Tradability | Track |
| --- | --- | --- | --- | --- |
| phase10b | `MNQ_10b_primary_short_midday_breakout_overnight_range_breakout_short_tf15_midday_response_all_ranges_all_gaps_all_touches_mt1` | real_but_nontradable_signal | not_tradable_concentrated | parked_research_signal |
| phase10b | `MNQ_10b_primary_short_midday_breakout_overnight_range_breakout_short_tf15_midday_response_all_ranges_all_gaps_all_touches_mt2` | real_but_nontradable_signal | not_tradable_concentrated | parked_research_signal |
| phase10b | `MNQ_10b_primary_short_midday_breakout_overnight_range_breakout_short_tf15_midday_response_all_ranges_all_gaps_first_touch_only_mt1` | positive_research_signal | not_tradable_concentrated | parked_research_signal |
| phase10b | `MNQ_10b_primary_short_midday_breakout_overnight_range_breakout_short_tf15_midday_response_all_ranges_all_gaps_first_touch_only_mt2` | positive_research_signal | not_tradable_concentrated | parked_research_signal |
| phase10b | `MNQ_10b_primary_short_midday_breakout_overnight_range_breakout_short_tf15_midday_response_exclude_narrowest_20_all_gaps_all_touches_mt1` | real_but_nontradable_signal | not_tradable_concentrated | parked_research_signal |
| phase10b | `MNQ_10b_primary_short_midday_breakout_overnight_range_breakout_short_tf15_midday_response_exclude_narrowest_20_all_gaps_all_touches_mt2` | real_but_nontradable_signal | not_tradable_concentrated | parked_research_signal |
| phase10b | `MNQ_10b_primary_short_midday_breakout_overnight_range_breakout_short_tf15_midday_response_exclude_widest_20_all_gaps_all_touches_mt1` | real_but_nontradable_signal | not_tradable_concentrated | parked_research_signal |
| phase10b | `MNQ_10b_primary_short_midday_breakout_overnight_range_breakout_short_tf15_midday_response_exclude_widest_20_all_gaps_all_touches_mt2` | real_but_nontradable_signal | not_tradable_concentrated | parked_research_signal |
| phase10b | `MNQ_10b_primary_short_midday_breakout_overnight_range_breakout_short_tf15_midday_response_exclude_widest_20_all_gaps_first_touch_only_mt1` | real_but_nontradable_signal | not_tradable_concentrated | parked_research_signal |
| phase10b | `MNQ_10b_primary_short_midday_breakout_overnight_range_breakout_short_tf15_midday_response_exclude_widest_20_all_gaps_first_touch_only_mt2` | real_but_nontradable_signal | not_tradable_concentrated | parked_research_signal |
| phase10b | `MNQ_10b_secondary_long_opening_fade_overnight_range_fade_long_tf15_opening_response_all_ranges_all_gaps_all_touches_mt1` | real_but_nontradable_signal | not_tradable_concentrated | parked_research_signal |
| phase10b | `MNQ_10b_secondary_long_opening_fade_overnight_range_fade_long_tf15_opening_response_all_ranges_all_gaps_all_touches_mt2` | real_but_nontradable_signal | not_tradable_concentrated | parked_research_signal |
| phase10b | `MNQ_10b_secondary_long_opening_fade_overnight_range_fade_long_tf5_opening_response_all_ranges_all_gaps_all_touches_mt1` | real_but_nontradable_signal | not_tradable_concentrated | parked_research_signal |
| phase10b | `MNQ_10b_secondary_long_opening_fade_overnight_range_fade_long_tf5_opening_response_all_ranges_all_gaps_all_touches_mt2` | real_but_nontradable_signal | not_tradable_concentrated | parked_research_signal |
| phase10b | `MNQ_10b_primary_short_midday_breakout_overnight_range_breakout_short_tf15_midday_response_exclude_narrowest_20_all_gaps_first_touch_only_mt1` | positive_research_signal | not_tradable_low_activity | rare_setup_research_signal |
| phase10b | `MNQ_10b_primary_short_midday_breakout_overnight_range_breakout_short_tf15_midday_response_exclude_narrowest_20_all_gaps_first_touch_only_mt2` | positive_research_signal | not_tradable_low_activity | rare_setup_research_signal |
| phase10b | `MNQ_10b_primary_short_midday_breakout_overnight_range_breakout_short_tf15_midday_response_middle_60_only_all_gaps_all_touches_mt1` | real_but_nontradable_signal | not_tradable_low_activity | rare_setup_research_signal |
| phase10b | `MNQ_10b_primary_short_midday_breakout_overnight_range_breakout_short_tf15_midday_response_middle_60_only_all_gaps_all_touches_mt2` | real_but_nontradable_signal | not_tradable_low_activity | rare_setup_research_signal |
| phase10b | `MNQ_10b_primary_short_midday_breakout_overnight_range_breakout_short_tf15_midday_response_middle_60_only_all_gaps_first_touch_only_mt1` | real_but_nontradable_signal | not_tradable_low_activity | rare_setup_research_signal |
| phase10b | `MNQ_10b_primary_short_midday_breakout_overnight_range_breakout_short_tf15_midday_response_middle_60_only_all_gaps_first_touch_only_mt2` | real_but_nontradable_signal | not_tradable_low_activity | rare_setup_research_signal |
| phase10b | `MNQ_10b_secondary_long_opening_fade_overnight_range_fade_long_tf15_opening_response_exclude_narrowest_20_all_gaps_all_touches_mt1` | positive_research_signal | not_tradable_low_activity | rare_setup_research_signal |
| phase10b | `MNQ_10b_secondary_long_opening_fade_overnight_range_fade_long_tf15_opening_response_exclude_narrowest_20_all_gaps_all_touches_mt2` | positive_research_signal | not_tradable_low_activity | rare_setup_research_signal |
| phase10b | `MNQ_10b_secondary_long_opening_fade_overnight_range_fade_long_tf5_opening_response_exclude_narrowest_20_all_gaps_all_touches_mt1` | positive_research_signal | not_tradable_low_activity | rare_setup_research_signal |
| phase10b | `MNQ_10b_secondary_long_opening_fade_overnight_range_fade_long_tf5_opening_response_exclude_narrowest_20_all_gaps_all_touches_mt2` | positive_research_signal | not_tradable_low_activity | rare_setup_research_signal |
| phase11a | `MNQ_11a_orfade_long_low_fade_OR5_midday_response_close_back_inside_fill_next_open_hard_stop_time_exit` | real_but_nontradable_signal | not_tradable_concentrated | parked_research_signal |
| phase11a | `MNQ_11a_orfade_long_low_fade_OR5_opening_response_close_back_inside_fill_next_open_hard_stop_time_exit` | real_but_nontradable_signal | not_tradable_concentrated | parked_research_signal |
| phase11a | `MNQ_11a_orfade_long_low_fade_OR5_opening_response_two_bar_inside_fill_next_open_hard_stop_time_exit` | real_but_nontradable_signal | not_tradable_concentrated | parked_research_signal |
| phase11a | `MNQ_11a_orfade_short_high_fade_OR30_opening_response_two_bar_inside_fill_next_open_hard_stop_time_exit` | real_but_nontradable_signal | not_tradable_concentrated | parked_research_signal |
| phase12a | `MNQ_12a_odpullback_long_first_pullback_OD15_drive_boundary_retest_resume_close_fill_next_open_hard_stop_time_exit` | real_but_nontradable_signal | not_tradable_low_activity | rare_setup_research_signal |
| phase12a | `MNQ_12a_odpullback_long_first_pullback_OD15_drive_boundary_retest_resume_close_fill_next_open_structure_target_time_exit` | positive_research_signal | not_tradable_low_activity | rare_setup_research_signal |
| phase12a | `MNQ_12a_odpullback_long_first_pullback_OD15_drive_boundary_retest_two_bar_resume_fill_next_open_hard_stop_time_exit` | positive_research_signal | not_tradable_low_activity | rare_setup_research_signal |
| phase12a | `MNQ_12a_odpullback_long_first_pullback_OD15_ema20_retest_resume_close_fill_next_open_hard_stop_time_exit` | positive_research_signal | not_tradable_low_activity | rare_setup_research_signal |
| phase12a | `MNQ_12a_odpullback_long_first_pullback_OD15_ema20_retest_two_bar_resume_fill_next_open_hard_stop_time_exit` | positive_research_signal | not_tradable_low_activity | rare_setup_research_signal |
| phase12a | `MNQ_12a_odpullback_long_first_pullback_OD15_ema20_retest_two_bar_resume_fill_next_open_structure_target_time_exit` | positive_research_signal | not_tradable_low_activity | rare_setup_research_signal |
| phase12a | `MNQ_12a_odpullback_long_first_pullback_OD30_ema20_retest_two_bar_resume_fill_next_open_structure_target_time_exit` | positive_research_signal | not_tradable_low_activity | rare_setup_research_signal |
| phase12a | `MNQ_12a_odpullback_short_first_pullback_OD30_drive_boundary_retest_resume_close_fill_next_open_hard_stop_time_exit` | positive_research_signal | not_tradable_low_activity | rare_setup_research_signal |
| phase12a | `MNQ_12a_odpullback_short_first_pullback_OD30_drive_boundary_retest_two_bar_resume_fill_next_open_hard_stop_time_exit` | positive_research_signal | not_tradable_low_activity | rare_setup_research_signal |
## Registry B - Phase 13A Addendum

Phase 13A added 2 positive uncorrelated prior-RTH breakout research signals for Portfolio Audit B. Both are positive research signals but remain `not_tradable_concentrated`, `parked_research_signal`, with `paper_trading_approved=false` and `official_gates_passed=false`.

Next action: `portfolio_audit_b_with_phase13a_uncorrelated_modules`.

## Registry C - Phase 14A Addendum

Phase 14A added 2 positive uncorrelated prior-level reaction research signals for Portfolio Audit C. Both are positive research signals but remain `not_tradable_concentrated`, `parked_research_signal`, with `portfolio_role=diversifier_module`, `market_condition=prior_level_interaction`, `module_family=prior_level_reaction`, `paper_trading_approved=false`, and `official_gates_passed=false`.

Watchlist hygiene: Phase 14A `phase14a_watchlist_needs_more_history` rows were not treated as review/paper-approved modules.

Next action: `portfolio_audit_c_with_phase14a_prior_level_modules`.

## Registry D - Phase 15A Addendum

Phase 15A added 3 positive uncorrelated trend/power continuation research signals for Portfolio Audit D. All are positive research signals but remain `not_tradable_low_activity`, `rare_setup_research_signal`, with `portfolio_role=diversifier_module`, `paper_trading_approved=false`, and `official_gates_passed=false`.

Gap-coverage caveat: Phase 15A positive candidates had incremental_gap_days_covered = 0; record them as uncorrelated diversifier modules, not confirmed gap-filling modules.

Next action: `portfolio_audit_d_with_phase15a_trend_power_modules`.
