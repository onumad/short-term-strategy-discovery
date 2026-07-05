# Phase 3B Updated Paper-Trading Plan

This replaces the Phase 3 manual plan. It remains research-only paper practice and does not approve live trading, broker connectivity, order routing, webhooks, credentials, or automation.

## Execution Rule

- Recommended execution mode: `D_stop_after_first_loser` (One open position only, stop for day after first loser).
- Trade 1 MNQ contract only.
- No pyramiding, scaling in, add-on entries, or overlapping positions.
- A second trade is allowed only if the first trade was a winner and has fully exited.
- Max 2 completed trades per day.
- Stop for the day after the first completed losing trade.

## Setup Rules

- Use the MNQ 1-minute RTH chart.
- Mark the 09:30-10:00 ET opening range after the 09:59 bar closes.
- Valid short: price breaks above opening range high, then a 1-minute candle closes back below that high.
- Valid long: price breaks below opening range low, then a 1-minute candle closes back above that low.
- Enter at the next 1-minute bar open after the failure close.
- Stop is 35% of opening range beyond the failed side, using the 10-point minimum range floor.
- Target is the opposite side of the opening range.
- Flatten any open position at 15:55 ET.

## Daily Stop Hierarchy

- Stop immediately after one full stop-loss.
- Stop immediately once realized daily PnL reaches -$500 or worse.
- Stop after 2 completed trades even if neither stop condition fired.
- Do not take a same-side re-entry while the first trade is still open.

## Paper-Test Invalidation Metrics

- Pause if 20-session realized PnL is negative after fees/slippage.
- Pause if max drawdown exceeds $1,000 on 1 MNQ during the 20-session test.
- Pause if worst rolling 5-session PnL is below -$750.
- Pause after 3 consecutive losing days.
- Pause after any rule violation, missed flatten, overlapping entry, or chart/data issue.
- Pause if average realized slippage/fill quality is materially worse than the 4-tick-per-side stress profile.
