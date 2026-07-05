# Phase 2 Discovery Report

Date generated: 2026-07-03

## Summary

- Strategy variants tested: `114`.
- Variants with at least one trade: `114`.
- Research window: `2026-04-06` through `2026-07-02` (63 complete shared sessions).
- Partial `2026-07-03` session excluded.
- Highest possible label remains `paper_trade_candidate`; no live-trading approval is implied.
- Candidates labeled `paper_trade_candidate`: `9`.

## Cost And Execution Assumptions

- Entry timing: signal is evaluated after a 1-minute bar closes; entry is next bar open.
- Exit timing: target/stop/time flatten is evaluated after entry using 1-minute OHLC.
- Conservative intrabar rule: if stop and target are both touched in the same bar, stop is assumed first.
- Flatten time: `15:55 ET`.
- Base slippage: 1 tick per side plus round-turn fees.
- Stress slippage: 2 ticks per side plus the same round-turn fees.

| Instrument | Tick Size | Tick Value | Point Value | Round-Turn Fees | Base Cost | Stress Cost |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| MNQ | 0.25 | $0.50 | $2.00 | $1.74 | $2.74 | $3.74 |
| MGC | 0.1 | $1.00 | $10.00 | $1.22 | $3.22 | $5.22 |

MNQ uses CME's Micro E-mini Nasdaq-100 contract sizing assumption of `$2 x index` and `0.25` index-point ticks. MGC uses CME's Micro Gold `10 troy ounces` contract sizing assumption; the audit assumes `0.10` price ticks worth `$1.00` per contract. Fee values are research assumptions and should be replaced with broker-specific all-in costs before paper-trading evaluation.

Contract reference links: [CME MNQ contract specs](https://www.cmegroup.com/markets/equities/nasdaq/micro-e-mini-nasdaq-100.contractSpecs.html), [CME MGC contract specs](https://www.cmegroup.com/markets/metals/precious/e-micro-gold.contractSpecs.html).

## Best Candidates

- Best offensive candidate: `MNQ_opening_range_failure_or30_fail_opposite` (paper_trade_candidate), net `$6696.49`, holdout `$2378.17`, trades/session `1.68`, score `75.74`.
- Highest-frequency candidate: `MNQ_vwap_reclaim_rejection_both_60x90` (rejected), net `$-156.96`, holdout `$-365.14`, trades/session `2.84`, score `-54.86`.
- Best risk-adjusted candidate: `MNQ_overnight_levels_sweep_reverse_60x90` (watchlist), net `$2819.64`, holdout `$119.09`, trades/session `1.02`, score `69.94`.
- Best Phase 3 validation candidate: `MNQ_opening_range_failure_or30_fail_opposite` (paper_trade_candidate), net `$6696.49`, holdout `$2378.17`, trades/session `1.68`, score `75.74`.

## Top Edge Table

| Rank | Candidate | Label | Net PnL | Holdout PnL | Stress Net PnL | Trades | Trades/Session | Active % | Max DD | Score | Risk Notes |
| ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 1 | `MNQ_opening_range_failure_or30_fail_opposite` | paper_trade_candidate | $6696.49 | $2378.17 | $6590.49 | 106 | 1.68 | 88.9% | $-2237.55 | 75.74 | No major Phase 2 risk flags. |
| 2 | `MNQ_opening_range_failure_or30_fail_mid` | paper_trade_candidate | $2904.36 | $1308.22 | $2798.36 | 106 | 1.68 | 88.9% | $-2045.42 | 75.24 | No major Phase 2 risk flags. |
| 3 | `MNQ_vwap_reclaim_rejection_both_60x90` | rejected | $-156.96 | $-365.14 | $-335.96 | 179 | 2.84 | 96.8% | $-714.62 | -54.86 | negative net PnL; negative final holdout; fails worse-slippage stress; one-day concentration risk; one-trade concentration risk |
| 4 | `MNQ_vwap_reclaim_rejection_both_80x120` | rejected | $-146.96 | $-250.14 | $-325.96 | 179 | 2.84 | 96.8% | $-869.62 | -55.86 | negative net PnL; negative final holdout; fails worse-slippage stress; one-day concentration risk; one-trade concentration risk |
| 5 | `MNQ_overnight_levels_sweep_reverse_60x90` | watchlist | $2819.64 | $119.09 | $2755.64 | 64 | 1.02 | 55.6% | $-414.44 | 69.94 | active on less than 70% of sessions |
| 6 | `MNQ_overnight_levels_sweep_reverse_80x120` | watchlist | $2355.64 | $39.09 | $2291.64 | 64 | 1.02 | 55.6% | $-474.44 | 60.77 | active on less than 70% of sessions |
| 7 | `MNQ_overnight_levels_sweep_reverse_40x60` | watchlist | $2394.64 | $199.09 | $2330.64 | 64 | 1.02 | 55.6% | $-490.82 | 72.79 | active on less than 70% of sessions |
| 8 | `MGC_opening_range_failure_or15_fail_opposite` | paper_trade_candidate | $1849.51 | $97.42 | $1605.51 | 122 | 1.94 | 98.4% | $-1516.70 | 64.63 | one-day concentration risk |

## Family Summary

| Family | Variants | Traded | Best Net PnL | Best Score | Paper Candidates |
| --- | ---: | ---: | ---: | ---: | ---: |
| opening_range_failure | 12 | 12 | $6696.49 | 75.74 | 7 |
| overnight_levels | 12 | 12 | $2819.64 | 72.79 | 0 |
| vwap_reclaim_rejection | 18 | 18 | $720.60 | 57.03 | 1 |
| prior_session_levels | 18 | 18 | $1346.08 | 51.18 | 1 |
| opening_range_breakout | 24 | 24 | $540.28 | 25.49 | 0 |
| power_hour | 12 | 12 | $203.42 | 22.83 | 0 |
| vwap_pullback_trend | 12 | 12 | $234.24 | -0.23 | 0 |
| first_hour_continuation | 6 | 6 | $-197.48 | -41.55 | 0 |

## Risks And Failure Modes

- Phase 2 is a discovery sweep, not a full validation study.
- The final holdout was scored after variant generation; it should not be used for further tuning.
- One-minute OHLC data cannot prove intrabar order, so the simulator uses a conservative stop-first rule.
- Results are sensitive to fee and slippage assumptions; stress results are included in the ranking table.
- Continuous futures can include rollover effects; Phase 3 should inspect top candidates around roll periods.
- MGC has more small non-1-minute gaps than MNQ in the Phase 1 audit; top MGC trade logs should be spot-checked.

## Recommended Phase 3

- Re-run the top candidates with parameter-neighbor sensitivity and stricter slippage.
- Inspect each top trade log manually for obvious data-gap, time-of-day, or rollover artifacts.
- Add MAE/MFE and a prop-firm style daily-loss rule model before any paper-trading plan.
- Keep the same candidate labels and do not introduce live-trading approval language.

## Reproducibility

Command:

```powershell
python scripts/run_phase2_discovery.py
```

Outputs:

- Ranked candidates: `C:\Users\ulzii\Documents\Short Term Strategy Discovery\outputs\ranked_edges.csv`
- Top candidates: `C:\Users\ulzii\Documents\Short Term Strategy Discovery\outputs\top_edges.csv`
- Trade logs: `C:\Users\ulzii\Documents\Short Term Strategy Discovery\trade_logs`
- Charts: `C:\Users\ulzii\Documents\Short Term Strategy Discovery\charts`
