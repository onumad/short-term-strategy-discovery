# Phase 3 Manual Paper-Trading Plan

This is a deterministic paper-trading plan for manual practice only. It is not live-trading approval and does not include broker connectivity, API keys, webhooks, or automated execution.

## Strategy

- Candidate: `MNQ_opening_range_failure_or30_fail_opposite`.
- Instrument: `MNQ`, 1-minute chart, RTH only.
- Contract size: 1 MNQ for the 20-session paper test.
- Opening range starts at `09:30 ET` and ends after the `09:59 ET` bar closes, defining a 30-minute `09:30-10:00 ET` range.
- Mark the opening range high, low, and midpoint on the chart.
- Valid breakout: price trades above the opening range high or below the opening range low after 10:00 ET.
- Failure: after a breakout, a 1-minute candle closes back inside the opening range.
- Entry: paper-enter at the next 1-minute bar open after the failure close.
- Short setup: breakout above range high, close back below range high, enter short next bar open.
- Long setup: breakout below range low, close back above range low, enter long next bar open.
- Stop: 35% of the opening range beyond the failed side, with a minimum range floor of 10 MNQ points.
- Target: opposite side of the opening range.
- Time stop: flatten any open position at `15:55 ET`.
- Max trades: 2 per day baseline; record max-1-trade/day as a comparison note, but do not switch mid-test.

## Daily Controls

- Paper trade 1 MNQ contract for 20 complete RTH sessions.
- Stop for the day after 2 losing trades.
- Stop for the day after one full initial-risk loss or $500 daily loss, whichever comes first.
- Do not trade if the opening range is malformed, data is delayed, the chart has missing 1-minute bars, or the range high/low cannot be marked confidently.
- Do not add discretionary filters during the 20-session test.
- At 2 contracts, every PnL and drawdown number approximately doubles; use that only as a risk reference, not as the starting paper size.
- Expected frequency from Phase 3: `1.68` trades/session and active on `88.9%` of sessions.

## Entry Checklist

- Confirm symbol is MNQ continuous/paper feed and chart is 1-minute RTH.
- Mark 09:30-10:00 ET opening range high, low, and midpoint.
- Confirm current time is after 10:00 ET and before noon for new entries.
- Confirm price broke outside the range, then closed back inside the failed side.
- Pre-mark entry, stop, target, initial dollar risk, and 15:55 ET flatten time.
- Take a screenshot before entry with range, breakout, failure close, stop, and target visible.

## Trade Log

Record after every paper trade:

- Date, side, entry time, entry price, stop, target, exit time, exit price, exit reason.
- Opening range high/low/midpoint and range size.
- Whether it was first or second trade of the day.
- Screenshot before entry and after exit.
- MAE/MFE estimate from chart replay if available.
- Notes on trend day behavior, strong opening drive, large opening gap, unusual volatility, data gaps, or news-like price action.

## Pause Conditions

- Pause after any 5-session rolling paper drawdown worse than $1,000 on 1 MNQ.
- Pause after 3 consecutive losing days.
- Pause after any rule mistake, missed stop, missed flatten, or chart/data issue.
- Pause if results no longer resemble the Phase 3 profile after 20 sessions: trade frequency far below 1/day, losses concentrated in one condition, or slippage/entry quality consistently worse than modeled.

## Review Cadence

- Review screenshots and logs after each session.
- Do not change rules during the 20-session sample.
- After 20 sessions, compare actual fills, trade count, win rate, average trade, worst day, and rule adherence against Phase 3 diagnostics before deciding whether to continue paper testing.
