# Short-Term Futures Edge Discovery

Project for developing a production-grade hybrid ML/LLM automated intraday futures trading bot built from a diversified playbook of deterministic, independently validated modules.

## Project Goal

The intended end product is an auditable trading bot that uses validated ML models and bounded LLM analysis to evaluate market conditions and select from a deterministic playbook, while independent policy and risk controls retain final authority over execution. Development is deliberately staged:

1. **Research and simulation (current):** discover modules, remove lookahead, validate costs and slippage, and test playbook behavior across chronological out-of-sample periods.
2. **Paper trading:** run frozen strategy and risk configurations against live market data using simulated orders and fills.
3. **Shadow execution:** exercise the production order lifecycle and reconciliation path with order transmission disabled and no market exposure.
4. **Controlled live execution:** enable broker routing only after an explicit policy change, operational safeguards, and a limited-size rollout plan are approved.

Passing a research gate does not automatically promote the project to the next stage. Each stage requires an explicit policy decision. ML models may provide versioned scores and signal inputs, and LLMs may provide versioned structured analysis and proposals, but neither may bypass deterministic policy, independent risk validation, or execution controls.

## Guardrails

- The current stage is research and simulation only.
- No paper or live trading is currently approved.
- Broker adapters, order routing, API-key storage, webhooks, and automated execution remain out of scope until an explicit stage promotion.
- ML and LLM components may not directly authorize orders, sizing, risk overrides, or broker actions.
- Model processes must not hold broker credentials or direct order-routing capability.
- Candidate and watchlist labels are research language only and do not authorize paper trading.

## Environment

Use the project virtual environment:

```bash
./.venv/Scripts/python.exe
```

Install or refresh dependencies with:

```bash
./.venv/Scripts/python.exe -m pip install -r requirements.txt
```

## Canonical Verification

Run the full test suite before reporting code changes as complete:

```bash
./.venv/Scripts/python.exe -m unittest discover -s tests -v
```

For data loading or audit-assumption changes, also run:

```bash
./.venv/Scripts/python.exe scripts/audit_data.py --no-write
```

## Current Research Scope

- Instruments: `MNQ`, `MGC`
- Data source: local CSV files under `data/raw`
- Required schema: `timestamp,symbol,open,high,low,close,volume`
- Timezone: `America/New_York`
- Session rule: under the current implementation, bars at or after `18:00 ET` map to the next local calendar date; this is not an exchange-calendar calculation
- RTH: `[09:30,16:00) ET`; a bar starting at `16:00 ET` is not RTH
- Current active work: calibrate and validate coverage-aligned ML Baseline B under versioned research-release contracts; deterministic playbook research continues, and no model is approved as a signal input or for paper trading.

## Current Playbook Direction

- Project direction shifted to specialized deterministic intraday playbook discovery.
- Individual modules may be rare and do not need to trade daily.
- The combined playbook is responsible for regular opportunity, diversification, concentration reduction, and fold stability.
- Official promotion gates remain unchanged.
- No paper trading is approved.

## Repo Hygiene And Label Safety

- Generated/raw research artifacts under `data/raw/`, `outputs/`, `reports/`, `artifacts/`, `charts/`, and `trade_logs/` are ignored going forward; already tracked files are not deleted or untracked by `.gitignore` alone.
- Legacy labels such as `paper_test_candidate`, `candidate_for_paper_review`, and watchlist-style labels are research/review language only and must not be interpreted as paper-trading approval.
- Paper trading remains unapproved unless an explicit project policy changes; current project outputs must keep `paper_trading_approved=false` and official promotion gates unchanged.

## Research Platform Shape

The project is being refactored toward a reusable research runner:

```text
local bars -> feature library -> deterministic StrategySpec candidates -> checkpointed scoring -> reports/manifests
```

The backtester/scoring code remains the research source of truth. The target production data flow is:

```text
market data -> point-in-time features -> deterministic modules + ML scores + LLM proposals
            -> deterministic policy -> independent risk engine -> execution
            -> reconciliation, monitoring, and immutable decision logs
```

- ML models produce calibrated, versioned predictions, rankings, and signal inputs.
- LLMs produce schema-constrained, versioned analysis and proposals.
- Deterministic policy resolves model outputs into an intended action.
- An independent risk engine approves, reduces, or rejects that action and fails closed.
- The execution process is isolated from model processes and owns broker credentials.

The detailed authority boundaries and promotion requirements are defined in `docs/hybrid_ml_llm_trading_architecture.md`.

Framework G extends the research runner with versioned release manifests, content hashes, explicit `authorization_stage=research`, strict ML prediction envelopes, abstention semantics, model-specific promotion gates, and a deterministic counterfactual policy-impact contract. These contracts record evidence and fail closed; they do not authorize execution or make model outputs authoritative.

The future production path extends this research platform with frozen strategy releases, live-data ingestion, paper and shadow execution, deterministic portfolio risk controls, broker reconciliation, monitoring, and kill-switch behavior. Those components belong to later delivery stages and are not authorized by research results alone.

## Phase 8A Clean-Family Prefilter

Phase 8A tests deterministic MGC-only families that avoid the failed legacy combo legs:

- `opening_range_breakout`
- `vwap_reclaim_rejection`
- `prior_session_levels`

Run a bounded continuation pass:

```bash
PHASE8A_MAX_NEW_SPECS=1 ./.venv/Scripts/python.exe scripts/run_phase8a_mgc_clean_family_search.py
```

Run a checkpoint-only artifact refresh:

```bash
PHASE8A_MAX_NEW_SPECS=0 ./.venv/Scripts/python.exe scripts/run_phase8a_mgc_clean_family_search.py
```

Legacy compatibility outputs are still written to:

- `outputs/phase8a_mgc_clean_family_results.csv`
- `outputs/phase8a_candidate_specs.json`
- `reports/phase8a_mgc_clean_family_report.md`

Each runner invocation also writes run-scoped artifacts:

```text
artifacts/phase8a_mgc_clean_family/<run_id>/
  manifest.json
  specs.json
  results.csv
  report.md
```

`manifest.json` records command, config, selected spec count, result row count, label/family counts, legacy artifact paths, data files, git state, and guardrails.

Use `EXPERIMENT_RUN_ID=<stable-id>` when a deterministic artifact folder is useful for testing or comparison.

## Phase 8B Failure Synthesis

Phase 8B converts the Phase 7C/7D/8A failure wall into an explicit decision gate. It reads only existing local artifacts:

- `outputs/phase7c_assumption_drift.csv`
- `outputs/phase7d_payout_diagnostic_results.csv`
- `outputs/phase8a_mgc_clean_family_results.csv`
- `artifacts/phase8a_mgc_clean_family/phase8a-r1-smoke/manifest.json`

Run it with:

```bash
./.venv/Scripts/python.exe scripts/run_phase8b_failure_synthesis.py
```

Legacy compatibility outputs:

- `outputs/phase8b_failure_summary.csv`
- `reports/phase8b_failure_synthesis_report.md`

Run-scoped artifacts:

```text
artifacts/phase8b_failure_synthesis/<run_id>/
  manifest.json
  failure_summary.csv
  results.csv
  inputs.json
  specs.json
  report.md
```

Current decision rule: if Phase 8B confirms the dominant failures are overtrading/cost/concentration/drawdown/ambiguity, stop widening entry variants and implement a pre-entry `phase8c_no_trade_session_filters` experiment next.

## Current Interpretation

Recent MGC candidates are being rejected for structural reasons: cost/slippage stress, concentration, drawdown, overtrading, ambiguity, and weak validation/holdout behavior. Do not keep widening entry variants indefinitely. Use Phase 8B to summarize the failure class, then prefer no-trade/session-selection filters before any walk-forward or paper-test promotion.

The current broad-pivot workflow is documented in:

- `reports/phase8_research_pivot_summary.md`
- `outputs/phase8c_no_trade_filter_results.csv`
- `outputs/phase8d_hypothesis_queue.csv`
- `outputs/phase8e_event_scout_results.csv`
- `outputs/phase8f_diverse_candidate_probe_results.csv`
- `outputs/phase8g_event_execution_calibration.csv`
- `outputs/phase8h_mnq_vwap_exit_shape_results.csv`

Phase 8C did not rescue the scored MGC Phase 8A candidates. Phase 8D/8E broadened the queue across strategies, sides, instruments, and timeframes. Phase 8F found that the first three executable event-study survivors were still rejected once realistic execution/cost gates were applied. Phase 8G found MNQ VWAP horizon-close positives but rejected them as concentrated and duplicate-shaped. Phase 8H confirms the two top VWAP hypotheses are the same signal at the event timestamp level; treat them as one diagnostic branch, not independent evidence.

## Phase 8G Event-To-Execution Calibration

Phase 8G reads the top capped/diversified Phase 8E `backtest_candidate` rows and local OHLCV data, then compares simple execution assumptions before any deeper StrategySpec sweep.

Run it with:

```bash
./.venv/Scripts/python.exe scripts/run_phase8g_event_execution_calibration.py
```

Legacy compatibility outputs:

- `outputs/phase8g_event_execution_calibration.csv`
- `reports/phase8g_event_execution_calibration_report.md`

Run-scoped artifacts:

```text
artifacts/phase8g_event_execution_calibration/<run_id>/
  manifest.json
  results.csv
  specs.json
  report.md
```

Decision rule: if horizon-close rows are positive but fixed stop/target rows fail, design a better deterministic exit family before parameter sweeps; if every realistic entry delay fails net or 4-tick stress, park the event family as timing/cost sensitive.

## Phase 8H MNQ VWAP Concentration / Exit Diagnostic

Phase 8H reads Phase 8E and Phase 8G artifacts, replays trade-level rows for the positive/stress-positive MNQ VWAP horizon-close diagnostics, measures concentration and duplicate-signal overlap, and compares a small set of non-intrabar exit shapes before any executable `StrategySpec` mapping.

Run it with:

```bash
./.venv/Scripts/python.exe scripts/run_phase8h_mnq_vwap_concentration_exit_diagnostic.py
```

Legacy compatibility outputs:

- `outputs/phase8h_mnq_vwap_trade_log.csv`
- `outputs/phase8h_mnq_vwap_concentration_summary.csv`
- `outputs/phase8h_mnq_vwap_exit_shape_results.csv`
- `outputs/phase8h_mnq_vwap_overlap_summary.csv`
- `reports/phase8h_mnq_vwap_concentration_exit_diagnostic_report.md`

Run-scoped artifacts:

```text
artifacts/phase8h_mnq_vwap_concentration_exit_diagnostic/<run_id>/
  manifest.json
  results.csv
  specs.json
  trade_log.csv
  concentration_summary.csv
  overlap_summary.csv
  report.md
```

Current Phase 8H result: selected hypotheses `2`; baseline trade rows `5194`; exit-shape rows `10`; overlap label `phase8h_duplicate_signal`. The two selected MNQ VWAP hypotheses have identical event timestamps (`2597` overlap, Jaccard `1.000`, PnL correlation `1.000`), so de-duplicate them before any future work. Baseline horizon-close rows remain `rejected_concentration_artifact`; `session_bucket_flatten` is diagnostic-only and was followed by Phase 8I no-lookahead pre-entry filter testing before any StrategySpec mapping.

## Phase 8I No-Lookahead Time / Session Filter

Phase 8I reads the Phase 8H trade log and overlap summary, de-duplicates the MNQ VWAP signal to one canonical hypothesis, then applies fixed pre-entry filters using only entry timestamp, weekday, and session metadata. It reports chronological discovery/validation/holdout metrics, stress PnL, drawdown, and concentration. It remains research-only and does not promote paper trading.

Run it with:

```bash
./.venv/Scripts/python.exe scripts/run_phase8i_no_lookahead_filter.py
```

Legacy compatibility outputs:

- `outputs/phase8i_deduped_mnq_vwap_trade_log.csv`
- `outputs/phase8i_no_lookahead_filter_results.csv`
- `outputs/phase8i_no_lookahead_filter_specs.json`
- `reports/phase8i_no_lookahead_filter_report.md`

Run-scoped artifacts:

```text
artifacts/phase8i_no_lookahead_filter/<run_id>/
  manifest.json
  results.csv
  specs.json
  deduped_trade_log.csv
  report.md
```

Current Phase 8I result with `EXPERIMENT_RUN_ID=phase8i-r1-smoke`: source rows `5194`, de-duplicated rows `2597`, filters evaluated `9`. Top candidate is `time_window:pre_14_00`: net `$13587.90`, stress `$11422.90`, discovery `$5154.32`, validation `$1699.98`, holdout `$6733.60`, max drawdown `$-5130.06`, best-day concentration `27.6%`, label `phase8i_filter_candidate`. `exclude_window:late_after_14` is equivalent to `pre_14_00`. Weekday filters also pass gates but have weaker validation (`$90.26`) and should rank behind the cleaner time-window candidate. Next best milestone is a narrow walk-forward-aware StrategySpec mapping for the de-duplicated MNQ VWAP signal with a fixed pre-14:00 entry filter and no live/paper promotion until that validation passes.

## Phase 8J Walk-Forward Strategy Mapping

Phase 8J maps the Phase 8I `time_window:pre_14_00` candidate to a deterministic `StrategySpec`-style artifact, allows the research-only `horizon_close` exit rule, applies the fixed pre-entry filter to the de-duplicated trade log, and evaluates rolling chronological train/validation/test folds. It is still a diagnostic mapping, not paper-trading promotion.

Run it with:

```bash
./.venv/Scripts/python.exe scripts/run_phase8j_walk_forward_strategy_mapping.py
```

Legacy compatibility outputs:

- `outputs/phase8j_strategy_spec.json`
- `outputs/phase8j_filtered_trade_log.csv`
- `outputs/phase8j_walk_forward_folds.csv`
- `outputs/phase8j_walk_forward_summary.csv`
- `reports/phase8j_walk_forward_strategy_mapping_report.md`

Run-scoped artifacts:

```text
artifacts/phase8j_walk_forward_strategy_mapping/<run_id>/
  manifest.json
  results.csv
  specs.json
  filtered_trade_log.csv
  folds.csv
  report.md
```

Current Phase 8J result with `EXPERIMENT_RUN_ID=phase8j-r1-smoke`: candidate `MNQ_vwap_pullback_continuation_tf5_cdd66a8b8a`, source rows `2597`, filtered rows `2165`, fold rows `9`, summary rows `1`. Aggregate test PnL remains positive (`$7289.62`, stress `$6327.62`, `962` test trades), but only `2/3` test folds are positive and concentration gates fail (`184.8%` max test best-day concentration; one negative test fold from `2026-04-22` through `2026-05-27`). Label: `phase8j_watchlist_needs_more_history`. Do not promote; next research should explain the losing April/May fold or require more independent history before any paper-test plan.

## Phase 8K Fold Failure Diagnostic And Next Five Steps

Phase 8K implements the next five research steps after Phase 8J: fold failure attribution, session concentration decomposition, pre-entry bucket decomposition, diagnostic-only rescue candidates, and a five-row decision queue. It consumes only Phase 8J artifacts and no-lookahead entry/session metadata. It is diagnostic-only and cannot promote anything to paper/live trading.

Run it with:

```bash
./.venv/Scripts/python.exe scripts/run_phase8k_fold_failure_diagnostic.py
```

Legacy compatibility outputs:

- `outputs/phase8k_tagged_trades.csv`
- `outputs/phase8k_session_diagnostics.csv`
- `outputs/phase8k_bucket_diagnostics.csv`
- `outputs/phase8k_candidate_actions.csv`
- `outputs/phase8k_next_step_queue.csv`
- `reports/phase8k_fold_failure_diagnostic_report.md`

Run-scoped artifacts:

```text
artifacts/phase8k_fold_failure_diagnostic/<run_id>/
  manifest.json
  results.csv
  specs.json
  tagged_trades.csv
  session_diagnostics.csv
  bucket_diagnostics.csv
  candidate_actions.csv
  report.md
```

Current Phase 8K result with `EXPERIMENT_RUN_ID=phase8k-r1-smoke`: source Phase 8J trades `2165`, tagged fold-trade rows `4568`, session diagnostics `375`, bucket diagnostics `18`, candidate actions `10`, next-step queue `5`. The worst failing session is `2026-05-18` (`$-1754.14`) and appears as both fold 2 test and fold 3 validation due to rolling-window overlap. Top diagnostic-only fixed-filter retest candidate is `exclude weekday=Wednesday` (`test_pnl=-3559.24`, `validation_pnl=-1977.84`, `201` test trades), followed by `exclude minute_bucket=10:00-10:30` and `exclude weekday=Tuesday`. These are not promotions; Phase 8L must retest any rule as fixed with chronological splits before further StrategySpec remapping.

## Phase 8L Fixed No-Lookahead Filter Retest

Phase 8L retests the Phase 8K diagnostic actions as fixed no-lookahead filters on the Phase 8J pre-14:00 trade log. It evaluates baseline plus fixed exclusions with chronological discovery/validation/holdout metrics and a rolling `75/25/25` walk-forward test. Phase 8L is still research-only and cannot promote a strategy to paper/live trading.

Run it with:

```bash
./.venv/Scripts/python.exe scripts/run_phase8l_fixed_filter_retest.py
```

Legacy compatibility outputs:

- `outputs/phase8l_filter_retest_results.csv`
- `outputs/phase8l_filter_retest_specs.json`
- `outputs/phase8l_filtered_trade_logs.csv`
- `reports/phase8l_fixed_filter_retest_report.md`

Run-scoped artifacts:

```text
artifacts/phase8l_fixed_filter_retest/<run_id>/
  manifest.json
  results.csv
  specs.json
  filtered_trade_logs.csv
  report.md
```

Current Phase 8L result with `EXPERIMENT_RUN_ID=phase8l-r1-smoke`: specs evaluated `9`, all labels `phase8l_watchlist_needs_strategy_remap`. The top fixed filter is `exclude:weekday:Wednesday`: trades `1738`, removed `427`, net `$16498.38`, stress `$14760.38`, discovery `$5503.34`, validation `$1065.50`, holdout `$9929.54`, walk-forward test `$10848.86`, walk-forward stress `$10087.86`, but only `66.7%` positive test folds and walk-forward concentration gates fail. `exclude:minute_bucket:10:00-10:30` is the only rule with `100.0%` positive walk-forward test folds, but it still fails concentration gates. Do not remap/promote yet; the next decision should be either a narrowly bounded concentration/risk diagnostic or a pivot away from this VWAP path if concentration remains structural.

## Phase 8M MNQ VWAP Risk / Exit / Concentration Diagnostic

Phase 8M gives the current MNQ VWAP long-only pre-14:00 branch one bounded remediation pass. It retests the Phase 8J entries with fixed no-lookahead base filters, simple sequential risk throttles, and three exit models: the diagnostic 15-minute horizon close, a fixed 1.5R/time-stop model, and a VWAP-failure/1.5R/time-stop model. It is still research-only and cannot promote a strategy to paper/live trading.

Run it with:

```bash
./.venv/Scripts/python.exe scripts/run_phase8m_risk_concentration_diagnostic.py
```

Legacy compatibility outputs:

- `outputs/phase8m_candidate_results.csv`
- `outputs/phase8m_filtered_trade_logs.csv`
- `outputs/phase8m_walk_forward_folds.csv`
- `outputs/phase8m_daily_pnl.csv`
- `outputs/phase8m_concentration_diagnostics.csv`
- `outputs/phase8m_outlier_session_diagnostics.csv`
- `outputs/phase8m_strategy_specs.json`
- `reports/phase8m_risk_concentration_diagnostic_report.md`

Run-scoped artifacts:

```text
artifacts/phase8m_mnq_vwap_risk_exit_concentration/<run_id>/
  manifest.json
  results.csv
  specs.json
  filtered_trade_logs.csv
  walk_forward_folds.csv
  daily_pnl.csv
  concentration_diagnostics.csv
  outlier_session_diagnostics.csv
  exit_remapped_trades.csv
  report.md
```

Current Phase 8M result with `EXPERIMENT_RUN_ID=phase8m-r1-smoke`: specs evaluated `192`; label counts `{'phase8m_rejected_low_activity': 124, 'phase8m_rejected_fold_instability': 31, 'phase8m_rejected_negative_stress': 29, 'phase8m_rejected_concentration': 8}`. No candidate reached watchlist or paper-review status. The top-ranked row is diagnostic-only `exclude_wednesday__horizon_close_15m__mt3_gap60_sal0_saw0_dl2.0_dp2.0`: net `$3805.24`, stress `$3531.24`, walk-forward stress `$2385.42`, `100.0%` positive walk-forward folds, but rejected for concentration and weekday-style diagnostic dependence. The best non-weekday top row is `exclude_10_00_10_30__vwap_failure_1_5_time30__mt3_gap15_sal0_saw0_dlnone_dpnone`: net `$1048.11`, stress `$608.11`, walk-forward stress `$913.59`, `100.0%` positive folds, but rejected for one-day/trade and walk-forward concentration. Phase 8M therefore supports killing or parking this MNQ VWAP branch unless a separate human decision asks for more history; the next research pivot should prioritize a structurally different MNQ family such as volatility compression breakout.

## Phase 9A MNQ Volatility Compression Breakout

Phase 9A implemented the first bounded pivot away from the MNQ VWAP branch: a deterministic MNQ volatility-compression breakout probe. It used shifted compression boxes, next-bar execution, opposite-box-edge stops, R-multiple/time-stop exits, max-trades/day controls, spacing, walk-forward folds, daily PnL, and concentration diagnostics. It remained research/simulation only.

Current Phase 9A result with `EXPERIMENT_RUN_ID=phase9a-r1-smoke`: specs evaluated `24`; label counts `{'phase9a_rejected_negative_stress': 22, 'phase9a_rejected_low_activity': 2}`. No candidate reached watchlist or paper-review status. The top row was `MNQ_vcb_tf5_range_percentile_lb8_q025_short_only_target15R_mt2_gap30_first10_keep1000`: net `-$254.47`, stress `-$432.47`, validation `$52.07`, holdout `-$1223.14`, walk-forward stress `$173.85`, and `66.7%` positive walk-forward folds. This is not an exhaustive rejection of compression breakout; it is a bounded first-pass failure.

## Phase 9B MNQ VCB Failure Attribution

Phase 9B is a diagnostic-only failure attribution pass for Phase 9A. It does not promote candidates. It asks whether the Phase 9A failure came from the broad volatility-compression idea or from first-pass choices around side, timeframe, compression definition, entry timing, stop/target geometry, and time windows.

Current Phase 9B result with `EXPERIMENT_RUN_ID=phase9b-r1-smoke`: specs evaluated `48`; trade attribution rows `8158`; generated `reports/phase9b_vcb_failure_attribution_report.md` plus side, time-bucket, exit-reason, session-loss, MFE/MAE, entry-timing, stop/target, and next-action artifacts. The diagnostic recommendation is `phase9c_targeted_retest_only`, not a broad expansion. Strongest diagnostic rows were short-only variants using `realized_vol_percentile` or `atr_percentile`, often with `next_bar_close`; the top candidate-level diagnostic row was `MNQ_vcb_tf5_realized_vol_percentile_lb8_q02_short_only_target15R_mt2_gap30_first10_keep1000` with net `$3727.29`, stress `$3523.29`, holdout `$915.34`, average MFE `$138.46`, average MAE `$108.90`, stop-hit rate `9.3%`, and target-hit rate `7.8%`. Side attribution favored `short_only` over `long_only`; time attribution favored `10:30-11:30` and `11:30-13:30`, while `13:30-15:45` and `09:30-10:00` were negative. The next phase, if pursued, should be a narrow Phase 9C retest of these diagnostic axes only, not a generalized optimizer.

## Phase 9C MNQ Short-Only VCB Targeted Retest

Phase 9C is the narrow targeted retest approved after Phase 9B. It tests short-only MNQ compression breakout candidates across `5m` and `15m`, `range_percentile` / `atr_percentile` / `realized_vol_percentile`, core `10:30-13:30` and diagnostic `10:00-13:30` windows, `next_bar_open` and `close_confirm_fill_next_open` entry semantics, plus capped opposite-box/time-exit and close-back-inside-box invalidation models. It remains research/simulation only and cannot approve paper/live trading.

Current Phase 9C result with `EXPERIMENT_RUN_ID=phase9c-r1-smoke`: specs evaluated `48`; trade rows `4802`; label counts `{'phase9c_rejected_low_activity': 24, 'phase9c_rejected_negative_stress': 17, 'phase9c_rejected_negative_validation': 5, 'phase9c_rejected_fold_instability': 2}`. No candidate reached watchlist or paper-review status. The top primary candidate was `MNQ_9c_vcb_tf15_range_percentile_lb12_q02_short_core_midday_close_confirm_fill_next_open_close_back_inside_box_invalidation_with_hard_cap`: trades `23`, active days `20`, net `$1878.46`, stress `$1855.46`, validation `$147.20`, holdout `$1556.59`, walk-forward stress `$1810.05`, but only `50.0%` positive walk-forward stress folds, best-day/trade concentration `45.9%`, quick/adverse stop rate `17.4%`, and low activity. The generated next action is `phase10a_overnight_range_breakout_fade`: Phase 9C failed validation/holdout/fold/concentration gates overall, so compression breakout should be killed unless a separate human decision asks for more history.

## Phase 10A MNQ Overnight Range Breakout/Fade

Phase 10A tests frozen overnight high/low levels for MNQ only, with separate `overnight_range_breakout` and `overnight_range_fade` branches. Overnight levels are computed from ETH bars before RTH, frozen at 09:30 ET, and entries are RTH-only in `opening_response` (`09:35-10:30`) or `midday_response` (`10:30-13:30`). The run remains research/simulation only with no broker, order-routing, webhook, credential, automated-execution, or paper/live approval scope.

Current Phase 10A result with `EXPERIMENT_RUN_ID=phase10a-r1-smoke`: specs evaluated `48`; trade rows `6402`; label counts `{'phase10a_rejected_negative_stress': 23, 'phase10a_rejected_negative_validation': 13, 'phase10a_rejected_fold_instability': 5, 'phase10a_rejected_low_activity': 5, 'phase10a_rejected_negative_holdout': 2}`. No candidate reached watchlist or paper-review status. The top row was `MNQ_10a_onrange_overnight_range_breakout_short_tf15_midday_response_next_bar_open_hard_stop_time_exit`: trades `151`, active days `87`, net `$3728.06`, stress `$3577.06`, validation `-$201.22`, holdout `$2720.72`, walk-forward stress `$2964.97`, positive WF folds `83.3%`, best-day concentration `28.5%`, and best-trade concentration `28.3%`. It was rejected for negative validation, fold instability, and concentration. The generated next action is `phase10b_targeted_overnight_range_diagnostic_retest` because one branch had positive stress/holdout but failed validation/fold/concentration gates.

## Phase 10B Overnight Range Targeted Diagnostic Retest

Phase 10B is a targeted diagnostic/retest of the Phase 10A positive axes. It remains MNQ-only and research/simulation only. It tests 32 primary specs for short 15m midday overnight-range breakout and 16 secondary specs for long opening-response overnight-range fade, using only pre-entry no-lookahead controls: overnight range percentile bucket, gap bucket, first-touch only vs all touches, and max one vs two trades per day. No weekday filters, date/session exclusions, high-concentration day removal, MGC, opening range fade, generalized optimizer, or live/paper approval were added.

Current Phase 10B result with `EXPERIMENT_RUN_ID=phase10b-r1-smoke`: specs evaluated `48`; trade rows `2228`; label counts `{'phase10b_rejected_low_activity': 34, 'phase10b_rejected_fold_instability': 14}`; research-axis status counts `{'axis_positive_but_concentrated': 40, 'axis_failed': 8}`. No candidate reached watchlist or paper-review status. The top row was `MNQ_10b_primary_short_midday_breakout_overnight_range_breakout_short_tf15_midday_response_exclude_widest_20_all_gaps_all_touches_mt1`: gross `$3168.88`, net `$2955.14`, stress `$2877.14`, validation `$334.40`, holdout `$811.84`, walk-forward stress `$1766.62`, positive WF folds `83.3%`, best-day/trade concentration `30.7%`, trades `78`, and active days `78`. It was rejected for fold instability and concentration. The generated next action is `park_overnight_range_as_research_signal`: Phase 10B improved validation for the primary axis but did not clear fold/concentration gates, so do not retest immediately or promote.

Phase 10B was parked as a research signal, with closeout packet `reports/phase10b_research_signal_packet.md`.
