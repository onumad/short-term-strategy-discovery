from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from .backtest import Candidate, prepare_indicators, simulate_candidate
from .data_loader import discover_data_files, load_ohlcv_csv
from .discovery import _shared_complete_sessions, build_candidates, score_candidate
from .instruments import InstrumentSpec, get_instrument


PRIMARY_CANDIDATE_ID = "MNQ_opening_range_failure_or30_fail_opposite"
SECONDARY_CANDIDATE_IDS = [
    "MNQ_opening_range_failure_or30_fail_mid",
    "MNQ_opening_range_failure_or15_fail_mid",
    "MNQ_opening_range_failure_or15_fail_opposite",
    "MNQ_opening_range_failure_or5_fail_opposite",
    "MNQ_overnight_levels_sweep_reverse_40x60",
    "MNQ_overnight_levels_sweep_reverse_60x90",
    "MNQ_vwap_reclaim_rejection_reclaim_80x120",
    "MGC_opening_range_failure_or15_fail_opposite",
    "MGC_opening_range_failure_or30_fail_opposite",
]
VALIDATION_CANDIDATE_IDS = [PRIMARY_CANDIDATE_ID, *SECONDARY_CANDIDATE_IDS]

GENERIC_ACCOUNT = {
    "name": "Generic 50K research proxy",
    "daily_loss_stop": 2_000.0,
    "drawdown_limit": 2_500.0,
    "contracts": [1, 2],
}


def run_phase3(project_root: Path) -> dict[str, Any]:
    output_dir = project_root / "outputs"
    report_dir = project_root / "reports"
    chart_dir = project_root / "charts"
    for path in [output_dir, report_dir, chart_dir]:
        path.mkdir(parents=True, exist_ok=True)

    full_data = _load_project_data(project_root)
    complete_sessions = _shared_complete_sessions(full_data)
    rth_by_symbol = {
        symbol: prepare_indicators(symbol_full).loc[
            lambda df: df["trading_session"].isin(complete_sessions)
        ].copy()
        for symbol, symbol_full in full_data.groupby("symbol", sort=True)
    }
    full_by_symbol = {
        symbol: symbol_full[symbol_full["trading_session"].isin(complete_sessions)].copy()
        for symbol, symbol_full in full_data.groupby("symbol", sort=True)
    }

    candidates = _selected_candidates()
    trade_logs = _simulate_candidates(candidates, rth_by_symbol, full_by_symbol, complete_sessions)
    diagnostics = _candidate_diagnostics(candidates, trade_logs, complete_sessions)
    diagnostics.to_csv(output_dir / "phase3_candidate_diagnostics.csv", index=False)

    daily_pnl = _daily_pnl(trade_logs, complete_sessions)
    daily_pnl.to_csv(output_dir / "phase3_daily_pnl.csv", index=False)

    primary = next(candidate for candidate in candidates if candidate.candidate_id == PRIMARY_CANDIDATE_ID)
    primary_trades = trade_logs[PRIMARY_CANDIDATE_ID]
    primary_spec = get_instrument(primary.instrument)
    trade_review = build_trade_review(primary_trades, rth_by_symbol[primary.instrument], primary, primary_spec)
    trade_review.to_csv(output_dir / "phase3_trade_review.csv", index=False)

    neighbor_results = _neighbor_robustness(rth_by_symbol["MNQ"], full_by_symbol["MNQ"], complete_sessions)
    risk_overlays = _risk_overlays(primary_trades)
    write_phase3_charts(primary_trades, trade_review, chart_dir)

    paths = {
        "diagnostics": output_dir / "phase3_candidate_diagnostics.csv",
        "daily_pnl": output_dir / "phase3_daily_pnl.csv",
        "trade_review": output_dir / "phase3_trade_review.csv",
        "validation_report": report_dir / "phase3_validation_report.md",
        "manual_plan": report_dir / "phase3_manual_paper_trading_plan.md",
        "charts": chart_dir,
    }
    result = {
        "complete_sessions": complete_sessions,
        "diagnostics": diagnostics,
        "daily_pnl": daily_pnl,
        "trade_review": trade_review,
        "neighbor_results": neighbor_results,
        "risk_overlays": risk_overlays,
        "trade_logs": trade_logs,
        "paths": paths,
    }
    write_phase3_validation_report(result)
    write_manual_paper_trading_plan(result)
    return result


def build_trade_review(
    trades: pd.DataFrame,
    rth: pd.DataFrame,
    candidate: Candidate,
    spec: InstrumentSpec,
) -> pd.DataFrame:
    if trades.empty:
        return pd.DataFrame()

    rows: list[dict[str, Any]] = []
    rth_by_session = {session: day.reset_index(drop=True) for session, day in rth.groupby("trading_session", sort=True)}
    for trade_number, (_, trade) in enumerate(trades.sort_values("entry_time").iterrows(), start=1):
        session = trade["trading_session"]
        day = rth_by_session.get(session)
        if day is None or day.empty:
            continue
        opening = day.iloc[: int(candidate.params["or_minutes"])]
        or_high = float(opening["high"].max())
        or_low = float(opening["low"].min())
        or_range = or_high - or_low
        entry_time = pd.Timestamp(trade["entry_time"])
        exit_time = pd.Timestamp(trade["exit_time"])
        trade_bars = day[(day["timestamp"] >= entry_time) & (day["timestamp"] <= exit_time)]
        if trade_bars.empty:
            trade_bars = day[day["timestamp"] >= entry_time].head(1)
        side_mult = 1 if trade["side"] == "long" else -1
        if trade["side"] == "long":
            mae = (float(trade_bars["low"].min()) - float(trade["entry_price"])) * spec.point_value
            mfe = (float(trade_bars["high"].max()) - float(trade["entry_price"])) * spec.point_value
        else:
            mae = (float(trade["entry_price"]) - float(trade_bars["high"].max())) * spec.point_value
            mfe = (float(trade["entry_price"]) - float(trade_bars["low"].min())) * spec.point_value
        initial_risk = abs(float(trade["entry_price"]) - float(trade["stop_price"])) * spec.point_value
        r_multiple = float(trade["net_pnl"]) / initial_risk if initial_risk else np.nan
        open_gap = _open_gap(day)
        max_gap = _max_gap_minutes(day, entry_time, exit_time)
        same_bar_ambiguous = _same_bar_stop_target_ambiguity(trade_bars, trade)
        breakout_side = "high" if trade["reason"] == "or_failure_short" else "low"
        opening_drive = float(opening.iloc[-1]["close"] - opening.iloc[0]["open"]) * spec.point_value
        day_range = float(day["high"].max() - day["low"].min())
        trend_day_proxy = day_range >= 1.5 * or_range if or_range else False
        rows.append(
            {
                "trade_number": trade_number,
                "candidate_id": trade["candidate_id"],
                "trading_session": session,
                "split": trade["split"],
                "side": trade["side"],
                "entry_time": trade["entry_time"],
                "exit_time": trade["exit_time"],
                "entry_hour": trade["entry_hour"],
                "entry_time_bucket": _time_bucket(entry_time),
                "exit_reason": trade["exit_reason"],
                "net_pnl": float(trade["net_pnl"]),
                "gross_pnl": float(trade["gross_pnl"]),
                "mae_dollars": float(mae),
                "mfe_dollars": float(mfe),
                "initial_risk_dollars": float(initial_risk),
                "r_multiple": float(r_multiple) if pd.notna(r_multiple) else np.nan,
                "opening_range_high": or_high,
                "opening_range_low": or_low,
                "opening_range_points": or_range,
                "opening_drive_dollars": opening_drive,
                "breakout_side": breakout_side,
                "day_range_points": day_range,
                "trend_day_proxy": bool(trend_day_proxy),
                "low_volatility_proxy": bool(or_range < 40.0),
                "high_volatility_proxy": bool(or_range > 120.0),
                "opening_gap_points": open_gap,
                "large_gap_proxy": bool(abs(open_gap) > 100.0),
                "rollover_proximity_flag": _rollover_proximity(session),
                "data_gap_near_trade_minutes": max_gap,
                "data_gap_proximity_flag": bool(max_gap > 1),
                "same_bar_stop_target_ambiguity": same_bar_ambiguous,
            }
        )
    return pd.DataFrame(rows)


def slippage_net_pnl(trades: pd.DataFrame, spec: InstrumentSpec, ticks_per_side: float) -> float:
    if trades.empty:
        return 0.0
    cost = spec.round_turn_fees + 2 * ticks_per_side * spec.tick_value
    return float((trades["gross_pnl"] - cost).sum())


def longest_losing_streak(values: pd.Series) -> int:
    longest = 0
    current = 0
    for value in values:
        if value < 0:
            current += 1
            longest = max(longest, current)
        else:
            current = 0
    return longest


def apply_daily_loss_stop(trades: pd.DataFrame, daily_loss_stop: float) -> pd.DataFrame:
    if trades.empty:
        return trades.copy()
    rows = []
    for _, day in trades.sort_values("entry_time").groupby("trading_session", sort=True):
        running = 0.0
        stopped = False
        for _, trade in day.iterrows():
            if stopped:
                continue
            rows.append(trade.to_dict())
            running += float(trade["net_pnl"])
            if running <= -abs(daily_loss_stop):
                stopped = True
    return pd.DataFrame(rows)


def write_phase3_validation_report(result: dict[str, Any]) -> None:
    diagnostics = result["diagnostics"]
    trade_review = result["trade_review"]
    primary = diagnostics.loc[diagnostics["candidate_id"] == PRIMARY_CANDIDATE_ID].iloc[0]
    mid = diagnostics.loc[diagnostics["candidate_id"] == "MNQ_opening_range_failure_or30_fail_mid"].iloc[0]
    risk = result["risk_overlays"]
    neighbors = result["neighbor_results"]
    paths = result["paths"]

    side_balance = primary["side_balance"]
    final_label = primary["phase3_label"]
    kill_condition = _dominant_failure_mode(trade_review)
    first_trade = risk.loc[risk["overlay"] == "skip_first_trade_each_day"].iloc[0]
    max_one = risk.loc[risk["overlay"] == "max_1_trade_per_day"].iloc[0]
    strict_slippage_ok = bool(primary["slippage_4_ticks_net_pnl"] > 0)

    lines = [
        "# Phase 3 Validation Report",
        "",
        f"Date generated: {datetime.now(ZoneInfo('America/New_York')).date()}",
        "",
        "## Main Findings",
        "",
        f"- Primary candidate: `{PRIMARY_CANDIDATE_ID}`.",
        f"- Research window: `{result['complete_sessions'][0]}` through `{result['complete_sessions'][-1]}` ({len(result['complete_sessions'])} complete shared sessions).",
        "- Phase 3 reruns frozen Phase 2 candidates only; neighbor checks are robustness context, not new parameter selection.",
        "- Highest allowed label remains `paper_trade_candidate`; this report does not approve live trading.",
        f"- Primary net PnL: `${primary['net_pnl']:.2f}`; holdout PnL: `${primary['holdout_pnl']:.2f}`; stress 4 ticks/side PnL: `${primary['slippage_4_ticks_net_pnl']:.2f}`.",
        f"- Primary activity: `{primary['trades']}` trades, `{primary['trades_per_session']:.2f}` trades/session, active on `{primary['active_session_pct']:.1%}` of sessions.",
        f"- Phase 3 label: `{final_label}`.",
        "",
        "## Candidate Comparison",
        "",
        "| Candidate | Label | Net PnL | Holdout | 4-Tick Slip | Trades | Active % | Long PnL | Short PnL | Max DD | Losing Streak |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for _, row in diagnostics.iterrows():
        lines.append(
            f"| `{row['candidate_id']}` | {row['phase3_label']} | ${row['net_pnl']:.2f} | "
            f"${row['holdout_pnl']:.2f} | ${row['slippage_4_ticks_net_pnl']:.2f} | "
            f"{int(row['trades'])} | {row['active_session_pct']:.1%} | "
            f"${row['long_net_pnl']:.2f} | ${row['short_net_pnl']:.2f} | "
            f"${row['max_drawdown']:.2f} | {int(row['longest_losing_streak'])} |"
        )

    lines.extend(
        [
            "",
            "## Risk Diagnostics",
            "",
            f"- Side balance: `{side_balance}`. Long PnL `${primary['long_net_pnl']:.2f}` over `{int(primary['long_trades'])}` trades; short PnL `${primary['short_net_pnl']:.2f}` over `{int(primary['short_trades'])}` trades.",
            f"- PnL concentration: best day is `{primary['one_day_concentration']:.1%}` of net PnL; best trade is `{primary['one_trade_concentration']:.1%}` of net PnL.",
            f"- Longest losing streak: `{int(primary['longest_losing_streak'])}` trades.",
            f"- MAE/MFE medians: `${trade_review['mae_dollars'].median():.2f}` MAE and `${trade_review['mfe_dollars'].median():.2f}` MFE.",
            f"- Same-bar stop/target ambiguity flags: `{int(trade_review['same_bar_stop_target_ambiguity'].sum())}` trades; those remain conservative because the simulator assumes stop first.",
            f"- Main observed failure mode: {kill_condition}.",
            "",
            "## Prop-Style Risk Overlay",
            "",
            "- Account proxy: generic 50K research model, 1-2 MNQ contracts, $2,000 daily loss stop, $2,500 drawdown proxy.",
            "",
            "| Overlay | Contracts | Net PnL | Max DD | Worst Day | Worst Rolling 5 Days | Drawdown Breach | Trades |",
            "| --- | ---: | ---: | ---: | ---: | ---: | --- | ---: |",
        ]
    )
    for _, row in risk.iterrows():
        lines.append(
            f"| {row['overlay']} | {int(row['contracts'])} | ${row['net_pnl']:.2f} | "
            f"${row['max_drawdown']:.2f} | ${row['worst_day']:.2f} | ${row['worst_rolling_5_day']:.2f} | "
            f"{str(bool(row['drawdown_breach'])).lower()} | {int(row['trades'])} |"
        )

    lines.extend(
        [
            "",
            "## Manual Feasibility",
            "",
            "- The setup is manually observable: mark the 09:30-10:00 ET range, wait for a breakout beyond range high/low, then require a 1-minute close back inside the range.",
            "- Entry timing remains conservative and executable on paper: enter at the next 1-minute bar open after the failure close.",
            "- Baseline is max 2 trades/day, 1 MNQ contract, hard flatten by 15:55 ET.",
            f"- Skipping the first trade each day changes primary net PnL to `${first_trade['net_pnl']:.2f}`; max 1 trade/day changes it to `${max_one['net_pnl']:.2f}`.",
            "",
            "## Neighbor Robustness",
            "",
            "| Neighbor | Net PnL | Holdout | 4-Tick Slip | Trades | Active % |",
            "| --- | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for _, row in neighbors.head(12).iterrows():
        lines.append(
            f"| `{row['candidate_id']}` | ${row['net_pnl']:.2f} | ${row['holdout_pnl']:.2f} | "
            f"${row['slippage_4_ticks_net_pnl']:.2f} | {int(row['trades'])} | {row['active_session_pct']:.1%} |"
        )

    lines.extend(
        [
            "",
            "## Final Decision Answers",
            "",
            f"1. `{PRIMARY_CANDIDATE_ID}` remains the best offensive candidate among the frozen Phase 3 set by net PnL.",
            f"2. `MNQ_opening_range_failure_or30_fail_mid` is safer/easier only in target distance and win rate terms; it produces lower net PnL (`${mid['net_pnl']:.2f}`) with similar drawdown (`${mid['max_drawdown']:.2f}`).",
            f"3. The edge is `{side_balance}`.",
            f"4. Strict slippage survival through 4 ticks/side: `{str(strict_slippage_ok).lower()}`.",
            f"5. Max 1 trade/day {'improves' if max_one['net_pnl'] > primary['net_pnl'] else 'hurts'} net PnL in this sample.",
            f"6. Market condition that most clearly hurts it: {kill_condition}.",
            f"7. Phase 3 label: `{final_label}`.",
            "8. For a 20-session paper test, follow the separate manual plan exactly and do not alter parameters during the test.",
            "9. Use a practical daily stop of one full initial-risk loss or $500 for 1 MNQ, whichever comes first; stop for the day after 2 losing trades.",
            "10. Before trusting results, manually review the flagged same-bar ambiguity trades, high-volatility opening ranges, large gap days, and any data-gap proximity flags.",
            "",
            "## Reproducibility",
            "",
            "```powershell",
            "python scripts/run_phase3_validation.py",
            "```",
            "",
            "Outputs:",
            "",
            f"- Candidate diagnostics: `{paths['diagnostics']}`",
            f"- Daily PnL: `{paths['daily_pnl']}`",
            f"- Main trade review: `{paths['trade_review']}`",
            f"- Manual plan: `{paths['manual_plan']}`",
            f"- Charts: `{paths['charts'] / 'phase3_primary_equity.png'}` and other `phase3_*.png` files",
            "",
        ]
    )
    paths["validation_report"].write_text("\n".join(lines), encoding="utf-8")


def write_manual_paper_trading_plan(result: dict[str, Any]) -> None:
    primary = result["diagnostics"].loc[
        result["diagnostics"]["candidate_id"] == PRIMARY_CANDIDATE_ID
    ].iloc[0]
    lines = [
        "# Phase 3 Manual Paper-Trading Plan",
        "",
        "This is a deterministic paper-trading plan for manual practice only. It is not live-trading approval and does not include broker connectivity, API keys, webhooks, or automated execution.",
        "",
        "## Strategy",
        "",
        f"- Candidate: `{PRIMARY_CANDIDATE_ID}`.",
        "- Instrument: `MNQ`, 1-minute chart, RTH only.",
        "- Contract size: 1 MNQ for the 20-session paper test.",
        "- Opening range starts at `09:30 ET` and ends after the `09:59 ET` bar closes, defining a 30-minute `09:30-10:00 ET` range.",
        "- Mark the opening range high, low, and midpoint on the chart.",
        "- Valid breakout: price trades above the opening range high or below the opening range low after 10:00 ET.",
        "- Failure: after a breakout, a 1-minute candle closes back inside the opening range.",
        "- Entry: paper-enter at the next 1-minute bar open after the failure close.",
        "- Short setup: breakout above range high, close back below range high, enter short next bar open.",
        "- Long setup: breakout below range low, close back above range low, enter long next bar open.",
        "- Stop: 35% of the opening range beyond the failed side, with a minimum range floor of 10 MNQ points.",
        "- Target: opposite side of the opening range.",
        "- Time stop: flatten any open position at `15:55 ET`.",
        "- Max trades: 2 per day baseline; record max-1-trade/day as a comparison note, but do not switch mid-test.",
        "",
        "## Daily Controls",
        "",
        "- Paper trade 1 MNQ contract for 20 complete RTH sessions.",
        "- Stop for the day after 2 losing trades.",
        "- Stop for the day after one full initial-risk loss or $500 daily loss, whichever comes first.",
        "- Do not trade if the opening range is malformed, data is delayed, the chart has missing 1-minute bars, or the range high/low cannot be marked confidently.",
        "- Do not add discretionary filters during the 20-session test.",
        "- At 2 contracts, every PnL and drawdown number approximately doubles; use that only as a risk reference, not as the starting paper size.",
        f"- Expected frequency from Phase 3: `{primary['trades_per_session']:.2f}` trades/session and active on `{primary['active_session_pct']:.1%}` of sessions.",
        "",
        "## Entry Checklist",
        "",
        "- Confirm symbol is MNQ continuous/paper feed and chart is 1-minute RTH.",
        "- Mark 09:30-10:00 ET opening range high, low, and midpoint.",
        "- Confirm current time is after 10:00 ET and before noon for new entries.",
        "- Confirm price broke outside the range, then closed back inside the failed side.",
        "- Pre-mark entry, stop, target, initial dollar risk, and 15:55 ET flatten time.",
        "- Take a screenshot before entry with range, breakout, failure close, stop, and target visible.",
        "",
        "## Trade Log",
        "",
        "Record after every paper trade:",
        "",
        "- Date, side, entry time, entry price, stop, target, exit time, exit price, exit reason.",
        "- Opening range high/low/midpoint and range size.",
        "- Whether it was first or second trade of the day.",
        "- Screenshot before entry and after exit.",
        "- MAE/MFE estimate from chart replay if available.",
        "- Notes on trend day behavior, strong opening drive, large opening gap, unusual volatility, data gaps, or news-like price action.",
        "",
        "## Pause Conditions",
        "",
        "- Pause after any 5-session rolling paper drawdown worse than $1,000 on 1 MNQ.",
        "- Pause after 3 consecutive losing days.",
        "- Pause after any rule mistake, missed stop, missed flatten, or chart/data issue.",
        "- Pause if results no longer resemble the Phase 3 profile after 20 sessions: trade frequency far below 1/day, losses concentrated in one condition, or slippage/entry quality consistently worse than modeled.",
        "",
        "## Review Cadence",
        "",
        "- Review screenshots and logs after each session.",
        "- Do not change rules during the 20-session sample.",
        "- After 20 sessions, compare actual fills, trade count, win rate, average trade, worst day, and rule adherence against Phase 3 diagnostics before deciding whether to continue paper testing.",
        "",
    ]
    result["paths"]["manual_plan"].write_text("\n".join(lines), encoding="utf-8")


def write_phase3_charts(trades: pd.DataFrame, trade_review: pd.DataFrame, chart_dir: Path) -> None:
    import matplotlib.pyplot as plt

    trades = trades.sort_values("entry_time").copy()
    entry_times = _naive_entry_times(trades)
    equity = trades["net_pnl"].cumsum()
    drawdown = equity - equity.cummax()

    plt.figure(figsize=(10, 4))
    plt.plot(entry_times, equity)
    plt.title("Phase 3 Primary Equity Curve")
    plt.xlabel("Entry time")
    plt.ylabel("Net PnL ($)")
    plt.tight_layout()
    plt.savefig(chart_dir / "phase3_primary_equity.png")
    plt.close()

    plt.figure(figsize=(10, 4))
    plt.plot(entry_times, drawdown)
    plt.title("Phase 3 Primary Drawdown")
    plt.xlabel("Entry time")
    plt.ylabel("Drawdown ($)")
    plt.tight_layout()
    plt.savefig(chart_dir / "phase3_primary_drawdown.png")
    plt.close()

    weekly = trades.groupby(entry_times.dt.to_period("W"))["net_pnl"].sum()
    plt.figure(figsize=(10, 4))
    weekly.plot(kind="bar")
    plt.title("Phase 3 Weekly PnL")
    plt.xlabel("Week")
    plt.ylabel("Net PnL ($)")
    plt.tight_layout()
    plt.savefig(chart_dir / "phase3_weekly_pnl.png")
    plt.close()

    tod = trades.groupby("entry_hour")["net_pnl"].mean()
    plt.figure(figsize=(10, 4))
    tod.plot(kind="bar")
    plt.title("Phase 3 Average PnL By Entry Time")
    plt.xlabel("Entry time")
    plt.ylabel("Average net PnL ($)")
    plt.tight_layout()
    plt.savefig(chart_dir / "phase3_time_of_day_pnl.png")
    plt.close()

    side = trades.groupby("side")["net_pnl"].sum()
    plt.figure(figsize=(6, 4))
    side.plot(kind="bar")
    plt.title("Phase 3 Long Vs Short Net PnL")
    plt.xlabel("Side")
    plt.ylabel("Net PnL ($)")
    plt.tight_layout()
    plt.savefig(chart_dir / "phase3_long_vs_short.png")
    plt.close()

    if not trade_review.empty:
        plt.figure(figsize=(7, 5))
        plt.scatter(trade_review["mae_dollars"], trade_review["mfe_dollars"], alpha=0.75)
        plt.title("Phase 3 MAE/MFE")
        plt.xlabel("MAE ($)")
        plt.ylabel("MFE ($)")
        plt.tight_layout()
        plt.savefig(chart_dir / "phase3_mae_mfe.png")
        plt.close()

    daily = trades.groupby("trading_session")["net_pnl"].sum().sort_index()
    daily_equity = daily.cumsum()
    daily_drawdown = daily_equity - daily_equity.cummax()
    plt.figure(figsize=(10, 4))
    plt.plot(pd.to_datetime(daily_drawdown.index), daily_drawdown)
    plt.title("Phase 3 Daily Drawdown")
    plt.xlabel("Trading session")
    plt.ylabel("Daily drawdown ($)")
    plt.tight_layout()
    plt.savefig(chart_dir / "phase3_daily_drawdown.png")
    plt.close()


def _load_project_data(project_root: Path) -> pd.DataFrame:
    raw_dir = project_root / "data" / "raw"
    frames = [load_ohlcv_csv(path) for path in discover_data_files(raw_dir)]
    if not frames:
        raise RuntimeError(f"No CSV files found in {raw_dir}")
    return pd.concat(frames, ignore_index=True).sort_values(["symbol", "timestamp"])


def _selected_candidates() -> list[Candidate]:
    candidates_by_id = {candidate.candidate_id: candidate for candidate in build_candidates()}
    missing = [candidate_id for candidate_id in VALIDATION_CANDIDATE_IDS if candidate_id not in candidates_by_id]
    if missing:
        raise RuntimeError(f"Missing expected Phase 3 candidates: {', '.join(missing)}")
    return [candidates_by_id[candidate_id] for candidate_id in VALIDATION_CANDIDATE_IDS]


def _simulate_candidates(
    candidates: list[Candidate],
    rth_by_symbol: dict[str, pd.DataFrame],
    full_by_symbol: dict[str, pd.DataFrame],
    complete_sessions: list[Any],
) -> dict[str, pd.DataFrame]:
    trade_logs = {}
    for candidate in candidates:
        spec = get_instrument(candidate.instrument)
        trades = simulate_candidate(
            rth_by_symbol[candidate.instrument],
            full_by_symbol[candidate.instrument],
            candidate,
            spec,
            complete_sessions,
        )
        trade_logs[candidate.candidate_id] = trades
    return trade_logs


def _candidate_diagnostics(
    candidates: list[Candidate],
    trade_logs: dict[str, pd.DataFrame],
    complete_sessions: list[Any],
) -> pd.DataFrame:
    rows = []
    for candidate in candidates:
        spec = get_instrument(candidate.instrument)
        trades = trade_logs[candidate.candidate_id]
        row = score_candidate(candidate, trades, complete_sessions)
        rows.append({**row, **_extra_metrics(trades, spec, complete_sessions)})
    return pd.DataFrame(rows).sort_values(["net_pnl", "trades_per_session"], ascending=[False, False])


def _extra_metrics(trades: pd.DataFrame, spec: InstrumentSpec, complete_sessions: list[Any]) -> dict[str, Any]:
    if trades.empty:
        return {
            "long_trades": 0,
            "short_trades": 0,
            "long_net_pnl": 0.0,
            "short_net_pnl": 0.0,
            "side_balance": "none",
            "longest_losing_streak": 0,
            "slippage_2_ticks_net_pnl": 0.0,
            "slippage_3_ticks_net_pnl": 0.0,
            "slippage_4_ticks_net_pnl": 0.0,
            "skip_first_trade_net_pnl": 0.0,
            "max_1_trade_per_day_net_pnl": 0.0,
            "time_of_day_pnl": "",
            "day_of_week_pnl": "",
            "phase3_label": "rejected",
        }
    ordered = trades.sort_values("entry_time").copy()
    by_side = ordered.groupby("side")["net_pnl"].sum()
    long_pnl = float(by_side.get("long", 0.0))
    short_pnl = float(by_side.get("short", 0.0))
    net_pnl = float(ordered["net_pnl"].sum())
    strict_slippage_pnl = slippage_net_pnl(ordered, spec, 4)
    active_pct = ordered["trading_session"].nunique() / len(complete_sessions)
    if long_pnl > 0 and short_pnl > 0 and min(long_pnl, short_pnl) / max(long_pnl, short_pnl) >= 0.35:
        side_balance = "balanced"
    elif long_pnl >= short_pnl:
        side_balance = "mostly long"
    else:
        side_balance = "mostly short"
    skip_first = _skip_first_trade_each_day(ordered)
    max_one = _limit_trades_per_day(ordered, 1)
    label = "paper_trade_candidate" if net_pnl > 0 and strict_slippage_pnl > 0 and active_pct >= 0.60 else "watchlist"
    entry_times = _naive_entry_times(ordered)
    time_of_day = ordered.groupby("entry_hour")["net_pnl"].sum()
    day_of_week = ordered.groupby(entry_times.dt.day_name())["net_pnl"].sum()
    return {
        "long_trades": int((ordered["side"] == "long").sum()),
        "short_trades": int((ordered["side"] == "short").sum()),
        "long_net_pnl": long_pnl,
        "short_net_pnl": short_pnl,
        "side_balance": side_balance,
        "longest_losing_streak": longest_losing_streak(ordered["net_pnl"]),
        "slippage_2_ticks_net_pnl": slippage_net_pnl(ordered, spec, 2),
        "slippage_3_ticks_net_pnl": slippage_net_pnl(ordered, spec, 3),
        "slippage_4_ticks_net_pnl": strict_slippage_pnl,
        "skip_first_trade_net_pnl": float(skip_first["net_pnl"].sum()) if not skip_first.empty else 0.0,
        "max_1_trade_per_day_net_pnl": float(max_one["net_pnl"].sum()) if not max_one.empty else 0.0,
        "time_of_day_pnl": _format_named_pnl(time_of_day),
        "day_of_week_pnl": _format_named_pnl(day_of_week),
        "phase3_label": label,
    }


def _daily_pnl(trade_logs: dict[str, pd.DataFrame], complete_sessions: list[Any]) -> pd.DataFrame:
    rows = []
    for candidate_id, trades in trade_logs.items():
        by_day = trades.groupby("trading_session")["net_pnl"].sum() if not trades.empty else pd.Series(dtype=float)
        for session in complete_sessions:
            rows.append(
                {
                    "candidate_id": candidate_id,
                    "trading_session": session,
                    "net_pnl": float(by_day.get(session, 0.0)),
                    "trades": int((trades["trading_session"] == session).sum()) if not trades.empty else 0,
                }
            )
    return pd.DataFrame(rows)


def _neighbor_robustness(
    rth: pd.DataFrame,
    full: pd.DataFrame,
    complete_sessions: list[Any],
) -> pd.DataFrame:
    spec = get_instrument("MNQ")
    candidates = []
    for minutes in [20, 25, 30, 35, 40]:
        for target in ["mid", "opposite"]:
            for max_trades in [1, 2]:
                for min_range in [8.0, 10.0, 12.0]:
                    candidates.append(
                        Candidate(
                            candidate_id=f"MNQ_opening_range_failure_or{minutes}_fail_{target}_max{max_trades}_min{min_range:g}",
                            instrument="MNQ",
                            family="opening_range_failure",
                            variant=f"or{minutes}_fail_{target}_max{max_trades}_min{min_range:g}",
                            params={
                                "or_minutes": minutes,
                                "target": target,
                                "max_trades": max_trades,
                                "min_range": min_range,
                            },
                        )
                    )
    rows = []
    for candidate in candidates:
        trades = simulate_candidate(rth, full, candidate, spec, complete_sessions)
        row = score_candidate(candidate, trades, complete_sessions)
        row["slippage_4_ticks_net_pnl"] = slippage_net_pnl(trades, spec, 4)
        rows.append(row)
    return pd.DataFrame(rows).sort_values(["net_pnl", "holdout_pnl"], ascending=[False, False])


def _risk_overlays(trades: pd.DataFrame) -> pd.DataFrame:
    overlays = {
        "baseline": trades,
        "skip_first_trade_each_day": _skip_first_trade_each_day(trades),
        "max_1_trade_per_day": _limit_trades_per_day(trades, 1),
        "max_2_trades_per_day": _limit_trades_per_day(trades, 2),
        "stop_after_first_winner": _stop_after_result(trades, winning=True),
        "stop_after_first_loser": _stop_after_result(trades, winning=False),
        "max_1_losing_trade_per_day": _max_losing_trades_per_day(trades, 1),
        "max_2_losing_trades_per_day": _max_losing_trades_per_day(trades, 2),
        "daily_loss_stop_2000": apply_daily_loss_stop(trades, GENERIC_ACCOUNT["daily_loss_stop"]),
    }
    rows = []
    for overlay, overlay_trades in overlays.items():
        for contracts in GENERIC_ACCOUNT["contracts"]:
            scaled = overlay_trades.copy()
            if not scaled.empty:
                scaled["net_pnl"] = scaled["net_pnl"] * contracts
            rows.append({"overlay": overlay, "contracts": contracts, **_risk_summary(scaled)})
    return pd.DataFrame(rows)


def _risk_summary(trades: pd.DataFrame) -> dict[str, Any]:
    if trades.empty:
        return {
            "net_pnl": 0.0,
            "max_drawdown": 0.0,
            "worst_day": 0.0,
            "worst_rolling_5_day": 0.0,
            "drawdown_breach": False,
            "trades": 0,
        }
    ordered = trades.sort_values("entry_time")
    equity = ordered["net_pnl"].cumsum()
    drawdown = equity - equity.cummax()
    day_pnl = ordered.groupby("trading_session")["net_pnl"].sum()
    rolling_5 = day_pnl.rolling(5, min_periods=1).sum()
    max_drawdown = float(drawdown.min())
    return {
        "net_pnl": float(ordered["net_pnl"].sum()),
        "max_drawdown": max_drawdown,
        "worst_day": float(day_pnl.min()),
        "worst_rolling_5_day": float(rolling_5.min()),
        "drawdown_breach": bool(max_drawdown <= -GENERIC_ACCOUNT["drawdown_limit"]),
        "trades": int(len(ordered)),
    }


def _skip_first_trade_each_day(trades: pd.DataFrame) -> pd.DataFrame:
    if trades.empty:
        return trades.copy()
    return trades.sort_values("entry_time").groupby("trading_session", group_keys=False).tail(-1)


def _limit_trades_per_day(trades: pd.DataFrame, count: int) -> pd.DataFrame:
    if trades.empty:
        return trades.copy()
    return trades.sort_values("entry_time").groupby("trading_session", group_keys=False).head(count)


def _stop_after_result(trades: pd.DataFrame, winning: bool) -> pd.DataFrame:
    if trades.empty:
        return trades.copy()
    rows = []
    for _, day in trades.sort_values("entry_time").groupby("trading_session", sort=True):
        stopped = False
        for _, trade in day.iterrows():
            if stopped:
                continue
            rows.append(trade.to_dict())
            if (float(trade["net_pnl"]) > 0) == winning:
                stopped = True
    return pd.DataFrame(rows)


def _max_losing_trades_per_day(trades: pd.DataFrame, max_losses: int) -> pd.DataFrame:
    if trades.empty:
        return trades.copy()
    rows = []
    for _, day in trades.sort_values("entry_time").groupby("trading_session", sort=True):
        losses = 0
        for _, trade in day.iterrows():
            if losses >= max_losses:
                continue
            rows.append(trade.to_dict())
            if float(trade["net_pnl"]) < 0:
                losses += 1
    return pd.DataFrame(rows)


def _open_gap(day: pd.DataFrame) -> float:
    if "prior_close" not in day.columns or pd.isna(day.iloc[0]["prior_close"]):
        return 0.0
    return float(day.iloc[0]["open"] - day.iloc[0]["prior_close"])


def _max_gap_minutes(day: pd.DataFrame, entry_time: pd.Timestamp, exit_time: pd.Timestamp) -> int:
    window = day[(day["timestamp"] >= entry_time) & (day["timestamp"] <= exit_time)]
    if len(window) < 2:
        return 0
    return int(window["timestamp"].diff().dt.total_seconds().div(60).dropna().max())


def _same_bar_stop_target_ambiguity(trade_bars: pd.DataFrame, trade: pd.Series) -> bool:
    if trade_bars.empty:
        return False
    if trade["side"] == "long":
        both = (trade_bars["low"] <= float(trade["stop_price"])) & (
            trade_bars["high"] >= float(trade["target_price"])
        )
    else:
        both = (trade_bars["high"] >= float(trade["stop_price"])) & (
            trade_bars["low"] <= float(trade["target_price"])
        )
    return bool(both.any())


def _rollover_proximity(session: Any) -> bool:
    date_value = pd.Timestamp(session)
    return bool(date_value.day >= 12 and date_value.day <= 18 and date_value.month in [6])


def _time_bucket(timestamp: pd.Timestamp) -> str:
    hour = timestamp.hour
    minute = timestamp.minute
    if hour == 10 and minute < 30:
        return "10:00-10:29"
    if hour == 10:
        return "10:30-10:59"
    if hour == 11:
        return "11:00-11:59"
    return "later"


def _dominant_failure_mode(trade_review: pd.DataFrame) -> str:
    losses = trade_review[trade_review["net_pnl"] < 0]
    if losses.empty:
        return "no dominant losing condition detected"
    checks = [
        ("trend-day proxy", "trend_day_proxy"),
        ("high-volatility opening range", "high_volatility_proxy"),
        ("low-volatility opening range", "low_volatility_proxy"),
        ("large opening gap", "large_gap_proxy"),
        ("data-gap proximity", "data_gap_proximity_flag"),
        ("same-bar stop/target ambiguity", "same_bar_stop_target_ambiguity"),
    ]
    shares = [(label, float(losses[column].mean())) for label, column in checks]
    label, share = max(shares, key=lambda item: item[1])
    return f"{label} losses ({share:.0%} of losing trades flagged)"


def _naive_entry_times(trades: pd.DataFrame) -> pd.Series:
    return pd.to_datetime(trades["entry_time"], utc=True).dt.tz_convert("America/New_York").dt.tz_localize(None)


def _format_named_pnl(series: pd.Series) -> str:
    return ";".join(f"{index}={value:.2f}" for index, value in series.items())
