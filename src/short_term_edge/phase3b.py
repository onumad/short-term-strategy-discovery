from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from .backtest import Candidate, _simulate_trade, generate_signals, prepare_indicators, simulate_candidate, split_sessions
from .data_loader import discover_data_files, load_ohlcv_csv
from .discovery import _shared_complete_sessions, build_candidates
from .instruments import InstrumentSpec, get_instrument
from .phase3 import (
    GENERIC_ACCOUNT,
    PRIMARY_CANDIDATE_ID,
    longest_losing_streak,
    slippage_net_pnl,
)


MODE_DEFINITIONS = {
    "A_baseline": "Original Phase 3 baseline",
    "B_one_open_position": "One open position only, max 2 completed trades/day",
    "C_max_1_trade_per_day": "Max 1 completed trade/day",
    "D_stop_after_first_loser": "One open position only, stop for day after first loser",
    "E_first_failure_per_side": "One open position only, first failure per breakout side",
    "F_cooldown_10_min": "One open position only, 10-minute cooldown after exit",
}


@dataclass(frozen=True)
class ExecutionMode:
    mode_id: str
    max_trades_per_day: int
    one_open_position: bool = True
    stop_after_first_loser: bool = False
    first_failure_per_side: bool = False
    cooldown_minutes: int = 0


def run_phase3b(project_root: Path) -> dict[str, Any]:
    output_dir = project_root / "outputs"
    report_dir = project_root / "reports"
    chart_dir = project_root / "charts"
    for path in [output_dir, report_dir, chart_dir]:
        path.mkdir(parents=True, exist_ok=True)

    full_data = _load_project_data(project_root)
    complete_sessions = _shared_complete_sessions(full_data)
    candidate = _primary_candidate()
    spec = get_instrument(candidate.instrument)
    symbol_full = full_data[
        (full_data["symbol"] == candidate.instrument)
        & (full_data["trading_session"].isin(complete_sessions))
    ].copy()
    rth = prepare_indicators(full_data[full_data["symbol"] == candidate.instrument]).loc[
        lambda df: df["trading_session"].isin(complete_sessions)
    ].copy()

    baseline = simulate_candidate(rth, symbol_full, candidate, spec, complete_sessions)
    modes = {
        "A_baseline": baseline,
        "B_one_open_position": simulate_execution_mode(
            rth,
            symbol_full,
            candidate,
            spec,
            complete_sessions,
            ExecutionMode("B_one_open_position", max_trades_per_day=2),
        ),
        "C_max_1_trade_per_day": simulate_execution_mode(
            rth,
            symbol_full,
            candidate,
            spec,
            complete_sessions,
            ExecutionMode("C_max_1_trade_per_day", max_trades_per_day=1),
        ),
        "D_stop_after_first_loser": simulate_execution_mode(
            rth,
            symbol_full,
            candidate,
            spec,
            complete_sessions,
            ExecutionMode("D_stop_after_first_loser", max_trades_per_day=2, stop_after_first_loser=True),
        ),
        "E_first_failure_per_side": simulate_execution_mode(
            rth,
            symbol_full,
            candidate,
            spec,
            complete_sessions,
            ExecutionMode("E_first_failure_per_side", max_trades_per_day=2, first_failure_per_side=True),
        ),
        "F_cooldown_10_min": simulate_execution_mode(
            rth,
            symbol_full,
            candidate,
            spec,
            complete_sessions,
            ExecutionMode("F_cooldown_10_min", max_trades_per_day=2, cooldown_minutes=10),
        ),
    }

    overlap_pairs, overlap_summary = audit_overlaps(baseline)
    overlap_pairs.to_csv(output_dir / "phase3b_overlap_audit.csv", index=False)

    mode_metrics = pd.DataFrame(
        [
            execution_mode_metrics(mode_id, trades, spec, complete_sessions)
            for mode_id, trades in modes.items()
        ]
    )
    mode_metrics.to_csv(output_dir / "phase3b_execution_modes.csv", index=False)

    paths = {
        "execution_modes": output_dir / "phase3b_execution_modes.csv",
        "overlap_audit": output_dir / "phase3b_overlap_audit.csv",
        "execution_report": report_dir / "phase3b_execution_audit.md",
        "updated_plan": report_dir / "phase3b_updated_paper_trading_plan.md",
        "charts": chart_dir,
    }
    result = {
        "candidate": candidate,
        "spec": spec,
        "complete_sessions": complete_sessions,
        "modes": modes,
        "mode_metrics": mode_metrics,
        "overlap_pairs": overlap_pairs,
        "overlap_summary": overlap_summary,
        "paths": paths,
    }
    write_phase3b_charts(result)
    write_execution_audit_report(result)
    write_updated_paper_trading_plan(result)
    return result


def simulate_execution_mode(
    rth: pd.DataFrame,
    full_df: pd.DataFrame,
    candidate: Candidate,
    spec: InstrumentSpec,
    complete_sessions: list[Any],
    mode: ExecutionMode,
) -> pd.DataFrame:
    signals = generate_signals(rth, full_df, candidate)
    if not signals:
        return pd.DataFrame()

    rows: list[dict[str, Any]] = []
    by_session = {session: day.reset_index(drop=True) for session, day in rth.groupby("trading_session", sort=True)}
    sessions_map = split_sessions(complete_sessions)
    signals_by_session: dict[Any, list[dict[str, Any]]] = {}
    for signal in signals:
        signals_by_session.setdefault(signal["trading_session"], []).append(signal)

    for session in complete_sessions:
        day = by_session.get(session)
        if day is None:
            continue
        accepted = 0
        stopped = False
        available_after: pd.Timestamp | None = None
        used_sides: set[str] = set()
        for signal in sorted(signals_by_session.get(session, []), key=lambda item: int(item["row_pos"])):
            if stopped or accepted >= mode.max_trades_per_day:
                break
            entry_pos = int(signal["row_pos"]) + 1
            if entry_pos >= len(day):
                continue
            entry_row = day.iloc[entry_pos]
            entry_time = pd.Timestamp(entry_row["timestamp"])
            if entry_time.time() >= pd.Timestamp("15:55").time():
                continue
            if mode.one_open_position and available_after is not None and entry_time < available_after:
                continue
            if mode.cooldown_minutes and available_after is not None:
                if entry_time < available_after + pd.Timedelta(minutes=mode.cooldown_minutes):
                    continue
            breakout_side = _breakout_side(signal)
            if mode.first_failure_per_side and breakout_side in used_sides:
                continue
            trade = _simulate_trade(day, entry_pos, signal["side"], signal["stop"], signal["target"], spec)
            if trade is None:
                continue
            row = _trade_row(trade, candidate, signal, spec, sessions_map)
            rows.append(row)
            accepted += 1
            used_sides.add(breakout_side)
            available_after = pd.Timestamp(row["exit_time"])
            if mode.stop_after_first_loser and float(row["net_pnl"]) < 0:
                stopped = True

    result = pd.DataFrame(rows)
    if result.empty:
        return result
    result["entry_hour"] = pd.to_datetime(result["entry_time"]).dt.strftime("%H:%M")
    return result


def audit_overlaps(trades: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    if trades.empty:
        return pd.DataFrame(), _empty_overlap_summary()

    ordered = _normalized_trades(trades)
    pair_rows = []
    overlap_trade_numbers: set[int] = set()
    max_exposure = 0
    cluster_rows = []
    for session, day in ordered.groupby("trading_session", sort=True):
        day = day.sort_values("entry_time").reset_index(drop=True)
        max_exposure = max(max_exposure, _max_simultaneous(day))
        clusters = _overlap_clusters(day)
        for cluster_id, cluster in enumerate(clusters, start=1):
            if len(cluster) < 2:
                continue
            for number in cluster["trade_number"].tolist():
                overlap_trade_numbers.add(int(number))
            cluster_rows.append(
                {
                    "trading_session": session,
                    "cluster_id": cluster_id,
                    "cluster_size": len(cluster),
                    "cluster_pnl": float(cluster["net_pnl"].sum()),
                    "first_entry_only_pnl": float(cluster.iloc[0]["net_pnl"]),
                }
            )
        for left in range(len(day)):
            for right in range(left + 1, len(day)):
                a = day.iloc[left]
                b = day.iloc[right]
                if b["entry_time"] < a["exit_time"]:
                    same_side = a["side"] == b["side"]
                    same_exit = a["exit_time"] == b["exit_time"]
                    likely_duplicate = bool(same_side and (same_exit or a["breakout_side"] == b["breakout_side"]))
                    pair_rows.append(
                        {
                            "trading_session": session,
                            "left_trade_number": int(a["trade_number"]),
                            "right_trade_number": int(b["trade_number"]),
                            "left_entry_time": a["entry_time"],
                            "right_entry_time": b["entry_time"],
                            "left_exit_time": a["exit_time"],
                            "right_exit_time": b["exit_time"],
                            "same_side": same_side,
                            "same_exit_time": same_exit,
                            "likely_duplicate_or_pyramid": likely_duplicate,
                            "pair_net_pnl": float(a["net_pnl"] + b["net_pnl"]),
                        }
                    )

    sessions_with_trades = ordered.groupby("trading_session").size()
    cluster_df = pd.DataFrame(cluster_rows)
    overlap_pnl = float(ordered[ordered["trade_number"].isin(overlap_trade_numbers)]["net_pnl"].sum())
    first_only_cluster_pnl = float(cluster_df["first_entry_only_pnl"].sum()) if not cluster_df.empty else 0.0
    non_cluster_numbers = set(ordered["trade_number"].astype(int)) - overlap_trade_numbers
    first_entry_total = float(ordered[ordered["trade_number"].isin(non_cluster_numbers)]["net_pnl"].sum() + first_only_cluster_pnl)
    summary = {
        "active_sessions": int(ordered["trading_session"].nunique()),
        "sessions_with_1_trade": int((sessions_with_trades == 1).sum()),
        "sessions_with_2_trades": int((sessions_with_trades == 2).sum()),
        "overlapping_trade_pairs": len(pair_rows),
        "same_side_overlap_pairs": int(sum(row["same_side"] for row in pair_rows)),
        "same_exit_overlap_pairs": int(sum(row["same_exit_time"] for row in pair_rows)),
        "likely_duplicate_or_pyramid_entries": int(sum(row["likely_duplicate_or_pyramid"] for row in pair_rows)),
        "overlap_cluster_count": int(len(cluster_df)),
        "overlap_trade_pnl": overlap_pnl,
        "first_entry_only_total_pnl": first_entry_total,
        "baseline_total_pnl": float(ordered["net_pnl"].sum()),
        "max_simultaneous_exposure": int(max_exposure),
        "has_more_than_1_mnq_exposure": bool(max_exposure > 1),
    }
    pair_df = pd.DataFrame(pair_rows)
    if pair_df.empty:
        pair_df = pd.DataFrame(columns=["trading_session", "left_trade_number", "right_trade_number"])
    for key, value in summary.items():
        pair_df[key] = value
    return pair_df, summary


def execution_mode_metrics(
    mode_id: str,
    trades: pd.DataFrame,
    spec: InstrumentSpec,
    complete_sessions: list[Any],
) -> dict[str, Any]:
    base = {"mode": mode_id, "description": MODE_DEFINITIONS[mode_id], "session_count": len(complete_sessions)}
    if trades.empty:
        return {
            **base,
            "net_pnl": 0.0,
            "holdout_pnl": 0.0,
            "slippage_4_ticks_net_pnl": 0.0,
            "trades": 0,
            "trades_per_session": 0.0,
            "active_session_pct": 0.0,
            "win_rate": 0.0,
            "avg_trade": 0.0,
            "median_trade": 0.0,
            "profit_factor": 0.0,
            "max_drawdown": 0.0,
            "worst_day": 0.0,
            "worst_rolling_5_day": 0.0,
            "longest_losing_streak": 0,
            "long_net_pnl": 0.0,
            "short_net_pnl": 0.0,
            "best_day_concentration": 0.0,
            "best_trade_concentration": 0.0,
            "max_simultaneous_exposure": 0,
            "phase3b_label": "rejected",
        }

    ordered = _normalized_trades(trades)
    day_pnl = ordered.groupby("trading_session")["net_pnl"].sum()
    rolling_5 = day_pnl.rolling(5, min_periods=1).sum()
    equity = ordered["net_pnl"].cumsum()
    drawdown = equity - equity.cummax()
    net_pnl = float(ordered["net_pnl"].sum())
    holdout_pnl = float(ordered.loc[ordered["split"] == "holdout", "net_pnl"].sum())
    wins = float(ordered.loc[ordered["net_pnl"] > 0, "net_pnl"].sum())
    losses = float(ordered.loc[ordered["net_pnl"] < 0, "net_pnl"].sum())
    strict_slippage = slippage_net_pnl(ordered, spec, 4)
    active_pct = ordered["trading_session"].nunique() / len(complete_sessions)
    max_exposure = _max_simultaneous_by_session(ordered)
    label = (
        "paper_trade_candidate"
        if net_pnl > 0
        and strict_slippage > 0
        and active_pct >= 0.60
        and max_exposure <= 1
        and float(drawdown.min()) > -GENERIC_ACCOUNT["drawdown_limit"]
        else "watchlist" if net_pnl > 0 else "rejected"
    )
    return {
        **base,
        "net_pnl": net_pnl,
        "holdout_pnl": holdout_pnl,
        "slippage_4_ticks_net_pnl": strict_slippage,
        "trades": int(len(ordered)),
        "trades_per_session": float(len(ordered) / len(complete_sessions)),
        "active_session_pct": float(active_pct),
        "win_rate": float((ordered["net_pnl"] > 0).mean()),
        "avg_trade": float(ordered["net_pnl"].mean()),
        "median_trade": float(ordered["net_pnl"].median()),
        "profit_factor": _profit_factor(wins, losses),
        "max_drawdown": float(drawdown.min()),
        "worst_day": float(day_pnl.min()),
        "worst_rolling_5_day": float(rolling_5.min()),
        "longest_losing_streak": longest_losing_streak(ordered["net_pnl"]),
        "long_net_pnl": float(ordered.loc[ordered["side"] == "long", "net_pnl"].sum()),
        "short_net_pnl": float(ordered.loc[ordered["side"] == "short", "net_pnl"].sum()),
        "best_day_concentration": _concentration(float(day_pnl.max()), net_pnl),
        "best_trade_concentration": _concentration(float(ordered["net_pnl"].max()), net_pnl),
        "max_simultaneous_exposure": int(max_exposure),
        "phase3b_label": label,
    }


def write_execution_audit_report(result: dict[str, Any]) -> None:
    summary = result["overlap_summary"]
    metrics = result["mode_metrics"]
    baseline = _mode_row(metrics, "A_baseline")
    no_overlap = _mode_row(metrics, "B_one_open_position")
    max_one = _mode_row(metrics, "C_max_1_trade_per_day")
    recommended = _recommended_mode(metrics)
    paths = result["paths"]
    pnl_impact = float(baseline["net_pnl"] - no_overlap["net_pnl"])
    dd_impact = float(no_overlap["max_drawdown"] - baseline["max_drawdown"])

    lines = [
        "# Phase 3B Execution Audit",
        "",
        f"Date generated: {datetime.now(ZoneInfo('America/New_York')).date()}",
        "",
        "## Summary",
        "",
        f"- Candidate audited: `{PRIMARY_CANDIDATE_ID}`.",
        f"- Baseline active sessions: `{summary['active_sessions']}`.",
        f"- Sessions with 1 trade: `{summary['sessions_with_1_trade']}`.",
        f"- Sessions with 2 trades: `{summary['sessions_with_2_trades']}`.",
        f"- Overlapping trade pairs: `{summary['overlapping_trade_pairs']}`.",
        f"- Same-side overlap pairs: `{summary['same_side_overlap_pairs']}`.",
        f"- Same-exit overlap pairs: `{summary['same_exit_overlap_pairs']}`.",
        f"- Likely duplicate/pyramided entries: `{summary['likely_duplicate_or_pyramid_entries']}`.",
        f"- Max simultaneous exposure in the reported 1 MNQ baseline: `{summary['max_simultaneous_exposure']}` MNQ.",
        f"- Baseline net PnL: `${baseline['net_pnl']:.2f}`.",
        f"- One-open-position net PnL: `${no_overlap['net_pnl']:.2f}`.",
        "",
        "## Execution Mode Results",
        "",
        "| Mode | Label | Net PnL | Holdout | 4-Tick Slip | Trades | Active % | Win Rate | Avg | PF | Max DD | Worst 5-Day | Max Exposure |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for _, row in metrics.iterrows():
        lines.append(
            f"| {row['mode']} | {row['phase3b_label']} | ${row['net_pnl']:.2f} | "
            f"${row['holdout_pnl']:.2f} | ${row['slippage_4_ticks_net_pnl']:.2f} | "
            f"{int(row['trades'])} | {row['active_session_pct']:.1%} | {row['win_rate']:.1%} | "
            f"${row['avg_trade']:.2f} | {row['profit_factor']:.2f} | ${row['max_drawdown']:.2f} | "
            f"${row['worst_rolling_5_day']:.2f} | {int(row['max_simultaneous_exposure'])} |"
        )

    lines.extend(
        [
            "",
            "## Overlap Impact",
            "",
            f"- Unique overlapping-trade PnL in baseline: `${summary['overlap_trade_pnl']:.2f}`.",
            f"- Baseline PnL if each overlap cluster keeps only its first entry: `${summary['first_entry_only_total_pnl']:.2f}`.",
            f"- Switching from baseline to one-open-position changes PnL by `${-pnl_impact:.2f}` and max drawdown by `${dd_impact:.2f}`.",
            "- The baseline does not represent strict 1-contract manual exposure on days where entries overlap.",
            "",
            "## Final Decision Answers",
            "",
            f"1. Did Phase 3 baseline allow overlapping positions? `{str(summary['has_more_than_1_mnq_exposure']).lower()}`.",
            f"2. Overlap impact: baseline net `${baseline['net_pnl']:.2f}` versus no-overlap net `${no_overlap['net_pnl']:.2f}`; baseline max DD `${baseline['max_drawdown']:.2f}` versus no-overlap max DD `${no_overlap['max_drawdown']:.2f}`.",
            f"3. Most realistic manual mode: `{recommended['mode']}` ({recommended['description']}).",
            f"4. Candidate remains `paper_trade_candidate` without overlapping positions: `{str(no_overlap['phase3b_label'] == 'paper_trade_candidate').lower()}`.",
            f"5. Recommendation: {'start a small 1 MNQ paper test using the updated no-overlap rules' if no_overlap['phase3b_label'] == 'paper_trade_candidate' else 'wait; do not paper trade until the no-overlap version is stronger'}.",
            "6. Replace the previous plan with the updated Phase 3B paper-trading plan: no pyramiding, second trade only after the first exits, stop after one full stop-loss or $500 realized daily loss, max 2 completed trades/day.",
            "",
            "## Reproducibility",
            "",
            "```powershell",
            "python scripts/run_phase3b_execution_audit.py",
            "```",
            "",
            "Outputs:",
            "",
            f"- Execution modes: `{paths['execution_modes']}`",
            f"- Overlap audit: `{paths['overlap_audit']}`",
            f"- Updated plan: `{paths['updated_plan']}`",
            f"- Charts: `{paths['charts'] / 'phase3b_baseline_vs_no_overlap_equity.png'}` and other `phase3b_*.png` files",
            "",
        ]
    )
    paths["execution_report"].write_text("\n".join(lines), encoding="utf-8")


def write_updated_paper_trading_plan(result: dict[str, Any]) -> None:
    metrics = result["mode_metrics"]
    recommended = _recommended_mode(metrics)
    lines = [
        "# Phase 3B Updated Paper-Trading Plan",
        "",
        "This replaces the Phase 3 manual plan. It remains research-only paper practice and does not approve live trading, broker connectivity, order routing, webhooks, credentials, or automation.",
        "",
        "## Execution Rule",
        "",
        f"- Recommended execution mode: `{recommended['mode']}` ({recommended['description']}).",
        "- Trade 1 MNQ contract only.",
        "- No pyramiding, scaling in, add-on entries, or overlapping positions.",
        "- A second trade is allowed only if the first trade was a winner and has fully exited.",
        "- Max 2 completed trades per day.",
        "- Stop for the day after the first completed losing trade.",
        "",
        "## Setup Rules",
        "",
        "- Use the MNQ 1-minute RTH chart.",
        "- Mark the 09:30-10:00 ET opening range after the 09:59 bar closes.",
        "- Valid short: price breaks above opening range high, then a 1-minute candle closes back below that high.",
        "- Valid long: price breaks below opening range low, then a 1-minute candle closes back above that low.",
        "- Enter at the next 1-minute bar open after the failure close.",
        "- Stop is 35% of opening range beyond the failed side, using the 10-point minimum range floor.",
        "- Target is the opposite side of the opening range.",
        "- Flatten any open position at 15:55 ET.",
        "",
        "## Daily Stop Hierarchy",
        "",
        "- Stop immediately after one full stop-loss.",
        "- Stop immediately once realized daily PnL reaches -$500 or worse.",
        "- Stop after 2 completed trades even if neither stop condition fired.",
        "- Do not take a same-side re-entry while the first trade is still open.",
        "",
        "## Paper-Test Invalidation Metrics",
        "",
        "- Pause if 20-session realized PnL is negative after fees/slippage.",
        "- Pause if max drawdown exceeds $1,000 on 1 MNQ during the 20-session test.",
        "- Pause if worst rolling 5-session PnL is below -$750.",
        "- Pause after 3 consecutive losing days.",
        "- Pause after any rule violation, missed flatten, overlapping entry, or chart/data issue.",
        "- Pause if average realized slippage/fill quality is materially worse than the 4-tick-per-side stress profile.",
        "",
    ]
    result["paths"]["updated_plan"].write_text("\n".join(lines), encoding="utf-8")


def write_phase3b_charts(result: dict[str, Any]) -> None:
    import matplotlib.pyplot as plt

    chart_dir = result["paths"]["charts"]
    modes = result["modes"]

    def equity(trades: pd.DataFrame) -> pd.Series:
        if trades.empty:
            return pd.Series(dtype=float)
        ordered = _normalized_trades(trades)
        return pd.Series(ordered["net_pnl"].cumsum().to_numpy(), index=ordered["entry_time"])

    for filename, mode_ids, title in [
        ("phase3b_baseline_vs_no_overlap_equity.png", ["A_baseline", "B_one_open_position"], "Baseline Vs No-Overlap Equity"),
        ("phase3b_baseline_vs_max1_equity.png", ["A_baseline", "C_max_1_trade_per_day"], "Baseline Vs Max-1-Trade Equity"),
    ]:
        plt.figure(figsize=(10, 4))
        for mode_id in mode_ids:
            curve = equity(modes[mode_id])
            plt.plot(curve.index, curve.values, label=mode_id)
        plt.title(f"Phase 3B {title}")
        plt.xlabel("Entry time")
        plt.ylabel("Net PnL ($)")
        plt.legend()
        plt.tight_layout()
        plt.savefig(chart_dir / filename)
        plt.close()

    daily = []
    for mode_id in ["A_baseline", "B_one_open_position", "C_max_1_trade_per_day"]:
        trades = _normalized_trades(modes[mode_id])
        day_pnl = trades.groupby("trading_session")["net_pnl"].sum() if not trades.empty else pd.Series(dtype=float)
        for session, value in day_pnl.items():
            daily.append({"mode": mode_id, "trading_session": session, "net_pnl": value})
    daily_df = pd.DataFrame(daily)
    pivot = daily_df.pivot_table(index="trading_session", columns="mode", values="net_pnl", aggfunc="sum").fillna(0)
    plt.figure(figsize=(10, 4))
    pivot.cumsum().plot(ax=plt.gca())
    plt.title("Phase 3B Daily PnL Comparison")
    plt.xlabel("Trading session")
    plt.ylabel("Cumulative daily PnL ($)")
    plt.tight_layout()
    plt.savefig(chart_dir / "phase3b_daily_pnl_comparison.png")
    plt.close()


def _load_project_data(project_root: Path) -> pd.DataFrame:
    frames = [load_ohlcv_csv(path) for path in discover_data_files(project_root / "data" / "raw")]
    if not frames:
        raise RuntimeError("No raw CSV files found")
    return pd.concat(frames, ignore_index=True).sort_values(["symbol", "timestamp"])


def _primary_candidate() -> Candidate:
    candidates = {candidate.candidate_id: candidate for candidate in build_candidates()}
    return candidates[PRIMARY_CANDIDATE_ID]


def _trade_row(
    trade: dict[str, Any],
    candidate: Candidate,
    signal: dict[str, Any],
    spec: InstrumentSpec,
    sessions_map: dict[Any, str],
) -> dict[str, Any]:
    return {
        **trade,
        "candidate_id": candidate.candidate_id,
        "instrument": candidate.instrument,
        "family": candidate.family,
        "variant": candidate.variant,
        "params": ";".join(f"{key}={value}" for key, value in sorted(candidate.params.items())),
        "signal_time": signal["timestamp"],
        "trading_session": signal["trading_session"],
        "side": signal["side"],
        "reason": signal["reason"],
        "breakout_side": _breakout_side(signal),
        "base_cost": spec.base_cost,
        "stress_cost": spec.stress_cost,
        "net_pnl": trade["gross_pnl"] - spec.base_cost,
        "stress_net_pnl": trade["gross_pnl"] - spec.stress_cost,
        "split": sessions_map.get(signal["trading_session"]),
    }


def _breakout_side(signal: dict[str, Any] | pd.Series) -> str:
    reason = signal["reason"]
    if reason == "or_failure_short":
        return "high"
    if reason == "or_failure_long":
        return "low"
    return str(signal.get("breakout_side", "unknown")) if isinstance(signal, dict) else "unknown"


def _normalized_trades(trades: pd.DataFrame) -> pd.DataFrame:
    out = trades.copy()
    if "trade_number" not in out.columns:
        out = out.sort_values("entry_time").reset_index(drop=True)
        out["trade_number"] = np.arange(1, len(out) + 1)
    out["entry_time"] = pd.to_datetime(out["entry_time"])
    out["exit_time"] = pd.to_datetime(out["exit_time"])
    if "breakout_side" not in out.columns:
        out["breakout_side"] = out["reason"].map({"or_failure_short": "high", "or_failure_long": "low"}).fillna("unknown")
    return out.sort_values(["trading_session", "entry_time"]).reset_index(drop=True)


def _max_simultaneous(day: pd.DataFrame) -> int:
    events = []
    for _, row in day.iterrows():
        events.append((row["entry_time"], 1))
        events.append((row["exit_time"], -1))
    active = 0
    max_active = 0
    for _, delta in sorted(events, key=lambda item: (item[0], item[1])):
        active += delta
        max_active = max(max_active, active)
    return max_active


def _max_simultaneous_by_session(trades: pd.DataFrame) -> int:
    if trades.empty:
        return 0
    return int(max(_max_simultaneous(day) for _, day in trades.groupby("trading_session", sort=True)))


def _overlap_clusters(day: pd.DataFrame) -> list[pd.DataFrame]:
    clusters = []
    current_rows = []
    current_end = None
    for _, row in day.sort_values("entry_time").iterrows():
        if current_end is None or row["entry_time"] >= current_end:
            if current_rows:
                clusters.append(pd.DataFrame(current_rows))
            current_rows = [row.to_dict()]
            current_end = row["exit_time"]
        else:
            current_rows.append(row.to_dict())
            current_end = max(current_end, row["exit_time"])
    if current_rows:
        clusters.append(pd.DataFrame(current_rows))
    return clusters


def _empty_overlap_summary() -> dict[str, Any]:
    return {
        "active_sessions": 0,
        "sessions_with_1_trade": 0,
        "sessions_with_2_trades": 0,
        "overlapping_trade_pairs": 0,
        "same_side_overlap_pairs": 0,
        "same_exit_overlap_pairs": 0,
        "likely_duplicate_or_pyramid_entries": 0,
        "overlap_cluster_count": 0,
        "overlap_trade_pnl": 0.0,
        "first_entry_only_total_pnl": 0.0,
        "baseline_total_pnl": 0.0,
        "max_simultaneous_exposure": 0,
        "has_more_than_1_mnq_exposure": False,
    }


def _profit_factor(wins: float, losses: float) -> float:
    if losses == 0:
        return float("inf") if wins > 0 else 0.0
    return float(wins / abs(losses))


def _concentration(value: float, net_pnl: float) -> float:
    return float(value / net_pnl) if net_pnl > 0 else 1.0


def _mode_row(metrics: pd.DataFrame, mode_id: str) -> pd.Series:
    return metrics.loc[metrics["mode"] == mode_id].iloc[0]


def _recommended_mode(metrics: pd.DataFrame) -> pd.Series:
    candidates = metrics[
        (metrics["mode"].isin(["B_one_open_position", "D_stop_after_first_loser", "E_first_failure_per_side", "F_cooldown_10_min"]))
        & (metrics["phase3b_label"] == "paper_trade_candidate")
    ].copy()
    if candidates.empty:
        candidates = metrics[metrics["mode"].isin(["B_one_open_position", "C_max_1_trade_per_day"])].copy()
    return candidates.sort_values(["net_pnl", "active_session_pct"], ascending=[False, False]).iloc[0]
