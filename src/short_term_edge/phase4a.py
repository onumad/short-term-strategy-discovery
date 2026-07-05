from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from .backtest import FLATTEN_TIME, Candidate, split_sessions
from .data_loader import discover_data_files, load_ohlcv_csv
from .discovery import _shared_complete_sessions
from .instruments import InstrumentSpec, get_instrument
from .phase3 import longest_losing_streak, slippage_net_pnl
from .phase3b import ExecutionMode, _max_simultaneous_by_session


TIMEFRAMES = [1, 2, 3, 5, 10, 15, 30, 60]
PHASE3B_BENCHMARK = {
    "candidate_id": "MNQ_opening_range_failure_or30_fail_opposite",
    "mode": "D_stop_after_first_loser",
    "net_pnl": 3246.85,
    "holdout_pnl": 1147.33,
    "slippage_4_ticks_net_pnl": 3075.85,
    "trades": 57,
    "active_session_pct": 0.889,
    "max_simultaneous_exposure": 1,
}


@dataclass(frozen=True)
class Phase4ACandidate:
    candidate_id: str
    instrument: str
    family: str
    variant: str
    signal_timeframe: int
    execution_timeframe: str
    entry_rule: str
    stop_rule: str
    target_rule: str
    time_stop: str
    mode: ExecutionMode
    params: dict[str, Any]
    discovery_role: str = "new_candidate"
    manual_rule: bool = True


def run_phase4a(project_root: Path) -> dict[str, Any]:
    output_dir = project_root / "outputs"
    report_dir = project_root / "reports"
    log_dir = project_root / "trade_logs" / "phase4a"
    chart_dir = project_root / "charts" / "phase4a"
    for path in [output_dir, report_dir, log_dir, chart_dir]:
        path.mkdir(parents=True, exist_ok=True)
    _clear_generated_dir(log_dir)
    _clear_generated_dir(chart_dir)

    full_data = _load_project_data(project_root)
    timestamp_semantics = inspect_timestamp_semantics(full_data)
    complete_sessions = _shared_complete_sessions(full_data)
    candidates = build_phase4a_candidates(full_data, complete_sessions)
    variant_counts = (
        pd.DataFrame([{"strategy_family": c.family} for c in candidates])
        .groupby("strategy_family")
        .size()
        .rename("planned_variants")
        .reset_index()
        .sort_values("strategy_family")
    )
    planned_count = len(candidates)
    if planned_count > 1_500:
        raise RuntimeError(f"Planned Phase 4A variant count is too large for the controlled sweep: {planned_count}")

    prepared = _prepare_symbol_data(full_data, complete_sessions)
    metrics_rows: list[dict[str, Any]] = []
    trade_logs: dict[str, pd.DataFrame] = {}

    for candidate in candidates:
        one_minute = prepared[candidate.instrument]["one_minute"]
        full_symbol = prepared[candidate.instrument]["full"]
        signal_bars = prepared[candidate.instrument]["timeframes"][candidate.signal_timeframe]
        spec = get_instrument(candidate.instrument)
        signals = generate_phase4a_signals(signal_bars, full_symbol, candidate)
        trades = simulate_phase4a_candidate(one_minute, signals, candidate, spec, complete_sessions)
        metrics_rows.append(score_phase4a_candidate(candidate, trades, spec, complete_sessions))
        if not trades.empty:
            trade_logs[candidate.candidate_id] = trades

    ranked = pd.DataFrame(metrics_rows).sort_values(
        ["ranking_score", "net_pnl", "trades_per_session"],
        ascending=[False, False, False],
    )
    top = select_phase4a_top_edges(ranked)
    family_summary = build_family_summary(ranked)
    timeframe_summary = build_timeframe_summary(ranked)

    ranked.to_csv(output_dir / "phase4a_ranked_edges.csv", index=False)
    top.to_csv(output_dir / "phase4a_top_edges.csv", index=False)
    family_summary.to_csv(output_dir / "phase4a_family_summary.csv", index=False)
    timeframe_summary.to_csv(output_dir / "phase4a_timeframe_summary.csv", index=False)
    write_phase4a_trade_logs(top, trade_logs, log_dir)
    write_phase4a_charts(top, ranked, trade_logs, family_summary, timeframe_summary, chart_dir)

    result = {
        "ranked": ranked,
        "top": top,
        "family_summary": family_summary,
        "timeframe_summary": timeframe_summary,
        "variant_counts": variant_counts,
        "planned_count": planned_count,
        "timestamp_semantics": timestamp_semantics,
        "complete_sessions": complete_sessions,
        "paths": {
            "ranked": output_dir / "phase4a_ranked_edges.csv",
            "top": output_dir / "phase4a_top_edges.csv",
            "family_summary": output_dir / "phase4a_family_summary.csv",
            "timeframe_summary": output_dir / "phase4a_timeframe_summary.csv",
            "report": report_dir / "phase4a_multitimeframe_discovery_report.md",
            "trade_logs": log_dir,
            "charts": chart_dir,
        },
    }
    write_phase4a_report(result)
    return result


def inspect_timestamp_semantics(full_data: pd.DataFrame) -> dict[str, Any]:
    rth = full_data[full_data["session_segment"] == "RTH"].copy()
    by_day = rth.groupby(["symbol", "trading_session"], sort=True)
    complete_counts = by_day.size()
    first_times = by_day["timestamp"].first().dt.strftime("%H:%M").value_counts().to_dict()
    last_times = by_day["timestamp"].last().dt.strftime("%H:%M").value_counts().to_dict()
    rth_390 = int((complete_counts == 390).sum())
    semantics = "bar_start"
    rationale = (
        "Complete RTH sessions contain 390 minute rows from 09:30 through 15:59, "
        "matching bar-start labels where the 09:59 bar completes the 09:30-10:00 opening range."
    )
    return {
        "semantics": semantics,
        "rationale": rationale,
        "complete_rth_390_sessions": rth_390,
        "first_rth_times": first_times,
        "last_rth_times": last_times,
    }


def resample_signal_bars(one_minute: pd.DataFrame, timeframe: int) -> pd.DataFrame:
    if timeframe == 1:
        out = one_minute.copy()
        out["signal_timeframe"] = 1
        out["bar_start"] = out["timestamp"]
        out["bar_end"] = out["timestamp"] + pd.Timedelta(minutes=1)
        out["source_bar_count"] = 1
        return _prepare_signal_indicators(out)

    rows: list[dict[str, Any]] = []
    for session, day in one_minute.groupby("trading_session", sort=True):
        day = day.sort_values("timestamp").reset_index(drop=True)
        session_start = pd.Timestamp(day.iloc[0]["timestamp"]).replace(hour=9, minute=30, second=0, microsecond=0)
        offset = ((day["timestamp"] - session_start).dt.total_seconds() // 60).astype(int)
        day = day.assign(_bucket=(offset // timeframe).astype(int))
        for bucket, group in day.groupby("_bucket", sort=True):
            if len(group) != timeframe:
                continue
            expected_start = session_start + pd.Timedelta(minutes=int(bucket) * timeframe)
            if pd.Timestamp(group.iloc[0]["timestamp"]) != expected_start:
                continue
            expected_end_start = expected_start + pd.Timedelta(minutes=timeframe - 1)
            if pd.Timestamp(group.iloc[-1]["timestamp"]) != expected_end_start:
                continue
            rows.append(
                {
                    "timestamp": expected_start,
                    "bar_start": expected_start,
                    "bar_end": expected_start + pd.Timedelta(minutes=timeframe),
                    "symbol": group.iloc[0]["symbol"],
                    "open": float(group.iloc[0]["open"]),
                    "high": float(group["high"].max()),
                    "low": float(group["low"].min()),
                    "close": float(group.iloc[-1]["close"]),
                    "volume": float(group["volume"].sum()),
                    "trading_session": session,
                    "session_segment": "RTH",
                    "signal_timeframe": timeframe,
                    "source_bar_count": int(len(group)),
                }
            )
    return _prepare_signal_indicators(pd.DataFrame(rows))


def _prepare_signal_indicators(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    out = df.sort_values(["trading_session", "timestamp"]).copy()
    typical = (out["high"] + out["low"] + out["close"]) / 3.0
    pv = typical * out["volume"]
    out["vwap"] = pv.groupby(out["trading_session"]).cumsum() / out["volume"].groupby(out["trading_session"]).cumsum()
    out["ema9"] = out.groupby("trading_session")["close"].transform(lambda s: s.ewm(span=9, adjust=False).mean())
    out["ema20"] = out.groupby("trading_session")["close"].transform(lambda s: s.ewm(span=20, adjust=False).mean())
    out["bar_index"] = out.groupby("trading_session").cumcount()
    daily = out.groupby("trading_session").agg(
        session_high=("high", "max"),
        session_low=("low", "min"),
        session_close=("close", "last"),
    )
    out["prior_high"] = out["trading_session"].map(daily["session_high"].shift(1))
    out["prior_low"] = out["trading_session"].map(daily["session_low"].shift(1))
    out["prior_close"] = out["trading_session"].map(daily["session_close"].shift(1))
    out["prior_mid"] = (out["prior_high"] + out["prior_low"]) / 2.0
    return out


def simulate_phase4a_candidate(
    one_minute: pd.DataFrame,
    signals: list[dict[str, Any]],
    candidate: Phase4ACandidate,
    spec: InstrumentSpec,
    complete_sessions: list[Any],
) -> pd.DataFrame:
    if not signals:
        return pd.DataFrame()
    sessions_map = split_sessions(complete_sessions)
    day_map = {session: day.sort_values("timestamp").reset_index(drop=True) for session, day in one_minute.groupby("trading_session", sort=True)}
    timestamp_map = {session: pd.to_datetime(day["timestamp"]) for session, day in day_map.items()}
    signals_by_session: dict[Any, list[dict[str, Any]]] = {}
    for signal in signals:
        signals_by_session.setdefault(signal["trading_session"], []).append(signal)

    rows: list[dict[str, Any]] = []
    for session in complete_sessions:
        day = day_map.get(session)
        if day is None or day.empty:
            continue
        accepted = 0
        stopped = False
        available_after: pd.Timestamp | None = None
        for signal in sorted(signals_by_session.get(session, []), key=lambda item: item["available_time"]):
            if stopped or accepted >= candidate.mode.max_trades_per_day:
                break
            entry_pos = _entry_pos_after_signal(day, pd.Timestamp(signal["available_time"]), timestamp_map.get(session))
            if entry_pos is None:
                continue
            entry_time = pd.Timestamp(day.iloc[entry_pos]["timestamp"])
            if entry_time.time() >= FLATTEN_TIME:
                continue
            if candidate.mode.one_open_position and available_after is not None and entry_time < available_after:
                continue
            trade = simulate_one_minute_trade(day, entry_pos, signal["side"], signal["stop"], signal["target"], spec)
            if trade is None:
                continue
            row = {
                **trade,
                "candidate_id": candidate.candidate_id,
                "instrument": candidate.instrument,
                "family": candidate.family,
                "strategy_family": candidate.family,
                "variant": candidate.variant,
                "signal_timeframe": candidate.signal_timeframe,
                "execution_timeframe": candidate.execution_timeframe,
                "entry_rule": candidate.entry_rule,
                "stop_rule": candidate.stop_rule,
                "target_rule": candidate.target_rule,
                "time_stop": candidate.time_stop,
                "max_trades_per_day": candidate.mode.max_trades_per_day,
                "stop_after_first_loser": candidate.mode.stop_after_first_loser,
                "one_open_position": candidate.mode.one_open_position,
                "execution_mode": candidate.mode.mode_id,
                "discovery_role": candidate.discovery_role,
                "params": _format_params(candidate.params),
                "signal_time": signal["timestamp"],
                "signal_available_time": signal["available_time"],
                "trading_session": session,
                "side": signal["side"],
                "reason": signal["reason"],
                "base_cost": spec.base_cost,
                "stress_cost": spec.stress_cost,
                "net_pnl": trade["gross_pnl"] - spec.base_cost,
                "stress_net_pnl": trade["gross_pnl"] - spec.stress_cost,
                "split": sessions_map.get(session),
            }
            rows.append(row)
            accepted += 1
            available_after = pd.Timestamp(row["exit_time"])
            if candidate.mode.stop_after_first_loser and float(row["net_pnl"]) < 0:
                stopped = True

    trades = pd.DataFrame(rows)
    if trades.empty:
        return trades
    trades["entry_hour"] = pd.to_datetime(trades["entry_time"]).dt.strftime("%H:%M")
    return trades


def _entry_pos_after_signal(day: pd.DataFrame, available_time: pd.Timestamp, timestamps: pd.Series | None = None) -> int | None:
    if timestamps is None:
        timestamps = pd.to_datetime(day["timestamp"])
    pos = int(timestamps.searchsorted(available_time, side="left"))
    if pos >= len(day):
        return None
    return pos


def simulate_one_minute_trade(
    day: pd.DataFrame,
    entry_pos: int,
    side: str,
    stop: float,
    target: float,
    spec: InstrumentSpec,
) -> dict[str, Any] | None:
    entry_row = day.iloc[entry_pos]
    entry_price = float(entry_row["open"])
    side_mult = 1 if side == "long" else -1
    exit_price = float(day.iloc[-1]["close"])
    exit_time = day.iloc[-1]["timestamp"]
    exit_reason = "session_close"
    same_bar_ambiguity = 0

    for row in day.iloc[entry_pos:].itertuples(index=False):
        row_time = row.timestamp
        if row_time.time() >= FLATTEN_TIME:
            exit_price = float(row.open)
            exit_time = row_time
            exit_reason = "time_flatten"
            break
        high = float(row.high)
        low = float(row.low)
        if side == "long":
            stop_hit = low <= stop
            target_hit = high >= target
        else:
            stop_hit = high >= stop
            target_hit = low <= target
        if stop_hit and target_hit:
            same_bar_ambiguity += 1
            exit_price = stop
            exit_time = row_time
            exit_reason = "stop"
            break
        if stop_hit:
            exit_price = stop
            exit_time = row_time
            exit_reason = "stop"
            break
        if target_hit:
            exit_price = target
            exit_time = row_time
            exit_reason = "target"
            break

    gross_pnl = (exit_price - entry_price) * side_mult * spec.point_value
    return {
        "entry_time": entry_row["timestamp"],
        "entry_price": entry_price,
        "exit_time": exit_time,
        "exit_price": exit_price,
        "exit_reason": exit_reason,
        "stop_price": float(stop),
        "target_price": float(target),
        "gross_pnl": float(gross_pnl),
        "holding_minutes": int((pd.Timestamp(exit_time) - pd.Timestamp(entry_row["timestamp"])).total_seconds() / 60),
        "same_bar_stop_target_ambiguity": int(same_bar_ambiguity),
    }


def build_phase4a_candidates(full_data: pd.DataFrame | None = None, complete_sessions: list[Any] | None = None) -> list[Phase4ACandidate]:
    candidates: list[Phase4ACandidate] = []
    for symbol in ["MGC", "MNQ"]:
        spec = get_instrument(symbol)
        min_range = {"MGC": 1.0, "MNQ": 10.0}[symbol]
        stop_sets = {"MGC": [(12, 18), (18, 27)], "MNQ": [(40, 60), (60, 90)]}[symbol]
        or_minutes_grid = [5, 10, 15, 20, 25, 30, 35, 45, 60] if symbol == "MNQ" else [15, 30, 60]
        or_timeframes = [1, 2, 3, 5] if symbol == "MNQ" else [1, 5]
        or_modes = [
            ExecutionMode("max1", 1),
            ExecutionMode("max2", 2),
            ExecutionMode("stop_after_first_loser", 2, stop_after_first_loser=True),
        ] if symbol == "MNQ" else [
            ExecutionMode("max2", 2),
            ExecutionMode("stop_after_first_loser", 2, stop_after_first_loser=True),
        ]
        for minutes in or_minutes_grid:
            for timeframe in or_timeframes:
                for target in ["mid", "opposite"]:
                    for mode in or_modes:
                        role = "robustness_confirmation" if symbol == "MNQ" and target == "opposite" and minutes in [20, 25, 30, 35] else "new_candidate"
                        candidates.append(
                            _p4_candidate(
                                symbol,
                                "opening_range_failure",
                                f"or{minutes}_tf{timeframe}_{target}_{mode.mode_id}",
                                timeframe,
                                "close back inside failed opening range",
                                "35pct opening range beyond failed side",
                                f"{target} of opening range",
                                mode,
                                {"or_minutes": minutes, "target": target, "min_range": min_range},
                                role,
                            )
                        )

        breakout_minutes = [15, 30, 60] if symbol == "MNQ" else [30]
        for timeframe in [1, 3, 5, 10, 15]:
            for minutes in breakout_minutes:
                for stop_mode in ["half_range"]:
                    for target in ["1R", "2R", "range_extension"]:
                        candidates.append(
                            _p4_candidate(
                                symbol,
                                "opening_range_breakout",
                                f"or{minutes}_tf{timeframe}_{stop_mode}_{target}",
                                timeframe,
                                "close outside opening range",
                                stop_mode,
                                target,
                                ExecutionMode("max2", 2),
                                {"or_minutes": minutes, "stop_mode": stop_mode, "target": target, "min_range": min_range},
                            )
                        )

        vwap_timeframes = [1, 3, 5, 10, 15] if symbol == "MNQ" else [1, 5]
        vwap_modes = ["reclaim", "rejection", "both"] if symbol == "MNQ" else ["both"]
        for timeframe in vwap_timeframes:
            for mode_name in vwap_modes:
                for stop_ticks, target_ticks in [stop_sets[-1]]:
                    candidates.append(
                        _p4_candidate(
                            symbol,
                            "vwap_reclaim_rejection",
                            f"tf{timeframe}_{mode_name}_{stop_ticks}x{target_ticks}",
                            timeframe,
                            "VWAP cross confirmation",
                            f"{stop_ticks} ticks",
                            f"{target_ticks} ticks",
                            ExecutionMode("max2", 2),
                            {"mode": mode_name, "stop_ticks": stop_ticks, "target_ticks": target_ticks, "tick_size": spec.tick_size},
                        )
                    )

        for timeframe in ([3, 5, 10, 15] if symbol == "MNQ" else [5, 15]):
            for pullback_ref in ["vwap", "ema20"]:
                for rr in [1.5]:
                    candidates.append(
                        _p4_candidate(
                            symbol,
                            "vwap_pullback_trend",
                            f"tf{timeframe}_{pullback_ref}_{rr:g}R",
                            timeframe,
                            "trend pullback reclaim",
                            "pullback swing",
                            f"{rr:g}R",
                            ExecutionMode("max2", 2),
                            {"pullback_ref": pullback_ref, "rr": rr, "tick_size": spec.tick_size},
                        )
                    )

        for timeframe in ([1, 3, 5, 15] if symbol == "MNQ" else [1, 5]):
            for mode_name in ["break_hold", "sweep_reverse", "prior_close_reclaim", "prior_mid_reclaim"]:
                for stop_ticks, target_ticks in stop_sets[:1]:
                    candidates.append(
                        _p4_candidate(
                            symbol,
                            "prior_session_levels",
                            f"tf{timeframe}_{mode_name}_{stop_ticks}x{target_ticks}",
                            timeframe,
                            mode_name,
                            f"{stop_ticks} ticks or level based",
                            f"{target_ticks} ticks or reference level",
                            ExecutionMode("max2", 2),
                            {"mode": mode_name, "stop_ticks": stop_ticks, "target_ticks": target_ticks, "tick_size": spec.tick_size},
                        )
                    )

        if _has_overnight_data(full_data, symbol, complete_sessions):
            for timeframe in ([1, 3, 5, 15] if symbol == "MNQ" else [1, 5]):
                for mode_name in ["sweep_reverse", "break_hold", "midpoint_reclaim"]:
                    for stop_ticks, target_ticks in stop_sets[:1]:
                        candidates.append(
                            _p4_candidate(
                                symbol,
                                "overnight_levels",
                                f"tf{timeframe}_{mode_name}_{stop_ticks}x{target_ticks}",
                                timeframe,
                                mode_name,
                                f"{stop_ticks} ticks or overnight level",
                                "overnight midpoint or fixed ticks",
                                ExecutionMode("max2", 2),
                                {"mode": mode_name, "stop_ticks": stop_ticks, "target_ticks": target_ticks, "tick_size": spec.tick_size},
                            )
                        )

        for timeframe in ([5, 10, 15] if symbol == "MNQ" else [5]):
            for mode_name in ["expansion", "pullback", "failed_extension"]:
                candidates.append(
                    _p4_candidate(
                        symbol,
                        "first_hour_range",
                        f"tf{timeframe}_{mode_name}",
                        timeframe,
                        mode_name,
                        "first-hour range based",
                        "1.5R",
                        ExecutionMode("max1", 1),
                        {"mode": mode_name, "rr": 1.5, "tick_size": spec.tick_size},
                    )
                )

        for timeframe in ([3, 5, 10, 15] if symbol == "MNQ" else [5, 15]):
            for trend_tf in [5, 15]:
                candidates.append(
                    _p4_candidate(
                        symbol,
                        "moving_average_pullback",
                        f"tf{timeframe}_trend{trend_tf}",
                        timeframe,
                        "9/20 EMA trend continuation",
                        "pullback swing",
                        "1.5R",
                        ExecutionMode("max2", 2),
                        {"trend_timeframe": trend_tf, "rr": 1.5, "tick_size": spec.tick_size},
                    )
                )

        for timeframe in ([3, 5, 10, 15] if symbol == "MNQ" else [5, 15]):
            for mode_name in ["narrow_range", "inside_bar", "low_realized_vol"]:
                candidates.append(
                    _p4_candidate(
                        symbol,
                        "compression_breakout",
                        f"tf{timeframe}_{mode_name}",
                        timeframe,
                        mode_name,
                        "inside compression range",
                        "2R",
                        ExecutionMode("max2", 2),
                        {"mode": mode_name, "rr": 2.0, "tick_size": spec.tick_size},
                    )
                )

        for window in ["09:30-10:30", "10:00-11:30", "11:30-13:30", "13:30-15:00", "15:00-15:55"]:
            for mode_name in ["breakout", "fade"]:
                candidates.append(
                    _p4_candidate(
                        symbol,
                        "time_of_day",
                        f"{window}_{mode_name}".replace(":", ""),
                        5,
                        f"{window} {mode_name}",
                        "window range",
                        "1.5R",
                        ExecutionMode("max1", 1),
                        {"window": window, "mode": mode_name, "rr": 1.5, "tick_size": spec.tick_size},
                    )
                )
    return candidates


def generate_phase4a_signals(signal_bars: pd.DataFrame, full_df: pd.DataFrame, candidate: Phase4ACandidate) -> list[dict[str, Any]]:
    family = candidate.family
    if family == "opening_range_failure":
        return _signals_opening_range_failure(signal_bars, candidate)
    if family == "opening_range_breakout":
        return _signals_opening_range_breakout(signal_bars, candidate)
    if family == "vwap_reclaim_rejection":
        return _signals_vwap_reclaim_rejection(signal_bars, candidate)
    if family == "vwap_pullback_trend":
        return _signals_vwap_pullback(signal_bars, candidate)
    if family == "prior_session_levels":
        return _signals_prior_levels(signal_bars, candidate)
    if family == "overnight_levels":
        return _signals_overnight_levels(signal_bars, full_df, candidate)
    if family == "first_hour_range":
        return _signals_first_hour(signal_bars, candidate)
    if family == "moving_average_pullback":
        return _signals_ma_pullback(signal_bars, candidate)
    if family == "compression_breakout":
        return _signals_compression(signal_bars, candidate)
    if family == "time_of_day":
        return _signals_time_of_day(signal_bars, candidate)
    raise ValueError(f"Unknown Phase 4A family: {family}")


def score_phase4a_candidate(
    candidate: Phase4ACandidate,
    trades: pd.DataFrame,
    spec: InstrumentSpec,
    complete_sessions: list[Any],
) -> dict[str, Any]:
    base = {
        "candidate_id": candidate.candidate_id,
        "instrument": candidate.instrument,
        "strategy_family": candidate.family,
        "variant": candidate.variant,
        "signal_timeframe": candidate.signal_timeframe,
        "execution_timeframe": candidate.execution_timeframe,
        "entry_rule": candidate.entry_rule,
        "stop_rule": candidate.stop_rule,
        "target_rule": candidate.target_rule,
        "time_stop": candidate.time_stop,
        "max_trades_per_day": candidate.mode.max_trades_per_day,
        "stop_after_first_loser": candidate.mode.stop_after_first_loser,
        "one_open_position": candidate.mode.one_open_position,
        "execution_mode": candidate.mode.mode_id,
        "discovery_role": candidate.discovery_role,
        "params": _format_params(candidate.params),
        "session_count": len(complete_sessions),
    }
    if trades.empty:
        return {**base, **_empty_metrics(), "label": "rejected", "ranking_score": -999.0, "risk_notes": "No trades generated."}

    ordered = trades.sort_values("entry_time").copy()
    net_pnl = float(ordered["net_pnl"].sum())
    day_pnl = ordered.groupby("trading_session")["net_pnl"].sum()
    rolling_5 = day_pnl.rolling(5, min_periods=1).sum()
    equity = ordered["net_pnl"].cumsum()
    drawdown = equity - equity.cummax()
    strict_slippage = slippage_net_pnl(ordered, spec, 4)
    active_sessions = int(ordered["trading_session"].nunique())
    active_pct = active_sessions / len(complete_sessions)
    wins = float(ordered.loc[ordered["net_pnl"] > 0, "net_pnl"].sum())
    losses = float(ordered.loc[ordered["net_pnl"] < 0, "net_pnl"].sum())
    max_exposure = _max_simultaneous_by_session(ordered)
    no_overlap = bool(max_exposure <= 1)
    best_day = float(day_pnl.max()) if len(day_pnl) else 0.0
    best_trade = float(ordered["net_pnl"].max())
    best_day_conc = _concentration(best_day, net_pnl)
    best_trade_conc = _concentration(best_trade, net_pnl)
    holdout_pnl = float(ordered.loc[ordered["split"] == "holdout", "net_pnl"].sum())
    validation_pnl = float(ordered.loc[ordered["split"] == "validation", "net_pnl"].sum())
    long_pnl = float(ordered.loc[ordered["side"] == "long", "net_pnl"].sum())
    short_pnl = float(ordered.loc[ordered["side"] == "short", "net_pnl"].sum())
    score = _phase4a_score(net_pnl, holdout_pnl, validation_pnl, strict_slippage, active_pct, len(ordered), drawdown.min(), best_day_conc, best_trade_conc)
    notes = _phase4a_risk_notes(net_pnl, holdout_pnl, strict_slippage, active_pct, best_day_conc, best_trade_conc, max_exposure, candidate.discovery_role)
    label = _phase4a_label(candidate, net_pnl, holdout_pnl, strict_slippage, active_pct, best_day_conc, best_trade_conc, max_exposure, len(ordered), score)
    return {
        **base,
        "net_pnl": net_pnl,
        "holdout_pnl": holdout_pnl,
        "slippage_4_ticks_net_pnl": strict_slippage,
        "trades": int(len(ordered)),
        "trades_per_session": float(len(ordered) / len(complete_sessions)),
        "active_sessions": active_sessions,
        "active_session_pct": float(active_pct),
        "win_rate": float((ordered["net_pnl"] > 0).mean()),
        "avg_trade": float(ordered["net_pnl"].mean()),
        "median_trade": float(ordered["net_pnl"].median()),
        "profit_factor": _profit_factor(wins, losses),
        "max_drawdown": float(drawdown.min()),
        "worst_day": float(day_pnl.min()),
        "worst_rolling_5_day": float(rolling_5.min()),
        "longest_losing_streak": longest_losing_streak(ordered["net_pnl"]),
        "long_net_pnl": long_pnl,
        "short_net_pnl": short_pnl,
        "best_day_concentration": best_day_conc,
        "best_trade_concentration": best_trade_conc,
        "max_simultaneous_exposure": int(max_exposure),
        "same_bar_stop_target_ambiguity_count": int(ordered["same_bar_stop_target_ambiguity"].sum()),
        "one_open_position_respected": no_overlap,
        "beats_phase3b_benchmark_net": bool(net_pnl > PHASE3B_BENCHMARK["net_pnl"]),
        "beats_phase3b_benchmark_slippage": bool(strict_slippage > PHASE3B_BENCHMARK["slippage_4_ticks_net_pnl"]),
        "label": label,
        "ranking_score": score,
        "risk_notes": "; ".join(notes) if notes else "No major Phase 4A risk flags.",
    }


def select_phase4a_top_edges(ranked: pd.DataFrame) -> pd.DataFrame:
    usable = ranked[ranked["trades"] > 0].copy()
    if usable.empty:
        return ranked.head(12)
    picks = []
    for _, row in usable.sort_values("net_pnl", ascending=False).head(4).iterrows():
        picks.append(row)
    for _, row in usable.sort_values("slippage_4_ticks_net_pnl", ascending=False).head(4).iterrows():
        picks.append(row)
    risk = usable.assign(risk_adjusted=usable["net_pnl"] / usable["max_drawdown"].abs().replace(0, np.nan))
    for _, row in risk.sort_values(["risk_adjusted", "net_pnl"], ascending=False).head(4).iterrows():
        picks.append(row)
    for _, row in usable.sort_values("ranking_score", ascending=False).head(12).iterrows():
        picks.append(row)
    return pd.DataFrame(picks).drop_duplicates("candidate_id").head(16).reset_index(drop=True)


def build_family_summary(ranked: pd.DataFrame) -> pd.DataFrame:
    return (
        ranked.groupby("strategy_family")
        .agg(
            variants=("candidate_id", "count"),
            traded=("trades", lambda s: int((s > 0).sum())),
            best_net_pnl=("net_pnl", "max"),
            best_holdout_pnl=("holdout_pnl", "max"),
            best_slippage_4_ticks=("slippage_4_ticks_net_pnl", "max"),
            best_score=("ranking_score", "max"),
            paper_candidates=("label", lambda s: int((s == "paper_trade_candidate").sum())),
            median_net_pnl=("net_pnl", "median"),
        )
        .reset_index()
        .sort_values(["best_score", "best_net_pnl"], ascending=[False, False])
    )


def build_timeframe_summary(ranked: pd.DataFrame) -> pd.DataFrame:
    return (
        ranked.groupby("signal_timeframe")
        .agg(
            variants=("candidate_id", "count"),
            traded=("trades", lambda s: int((s > 0).sum())),
            best_net_pnl=("net_pnl", "max"),
            best_holdout_pnl=("holdout_pnl", "max"),
            best_slippage_4_ticks=("slippage_4_ticks_net_pnl", "max"),
            best_score=("ranking_score", "max"),
            paper_candidates=("label", lambda s: int((s == "paper_trade_candidate").sum())),
            median_net_pnl=("net_pnl", "median"),
        )
        .reset_index()
        .sort_values(["best_score", "best_net_pnl"], ascending=[False, False])
    )


def write_phase4a_report(result: dict[str, Any]) -> None:
    ranked = result["ranked"]
    top = result["top"]
    family_summary = result["family_summary"]
    timeframe_summary = result["timeframe_summary"]
    sessions = result["complete_sessions"]
    paths = result["paths"]
    semantics = result["timestamp_semantics"]
    best_family = family_summary.iloc[0] if not family_summary.empty else None
    best_timeframe = timeframe_summary.iloc[0] if not timeframe_summary.empty else None
    best_practical = _best_practical(top, ranked)
    beaters = ranked[(ranked["beats_phase3b_benchmark_net"]) & (ranked["beats_phase3b_benchmark_slippage"]) & (ranked["max_simultaneous_exposure"] == 1)]
    paper = ranked[ranked["label"] == "paper_trade_candidate"]
    new_paper_count = int(((ranked["label"] == "paper_trade_candidate") & (ranked["discovery_role"] == "new_candidate")).sum())
    overfit = ranked[(ranked["net_pnl"] > 0) & ((ranked["best_day_concentration"] > 0.50) | (ranked["best_trade_concentration"] > 0.35))].sort_values("net_pnl", ascending=False)
    robustness = ranked[ranked["discovery_role"] == "robustness_confirmation"].sort_values("ranking_score", ascending=False)
    top_families = family_summary.head(4)["strategy_family"].tolist()
    focused = ranked[ranked["strategy_family"].isin(top_families)].sort_values("ranking_score", ascending=False).head(20)

    lines = [
        "# Phase 4A Multi-Timeframe Discovery Report",
        "",
        f"Date generated: {datetime.now(ZoneInfo('America/New_York')).date()}",
        "",
        "## Summary",
        "",
        f"- Research window: `{sessions[0]}` through `{sessions[-1]}` ({len(sessions)} complete shared sessions).",
        f"- Planned variants tested: `{len(ranked)}`.",
        f"- Timeframes generated: `{', '.join(f'{tf}m' for tf in TIMEFRAMES)}`.",
        f"- Timestamp semantics: `{semantics['semantics']}`. {semantics['rationale']}",
        "- Phase 4A is exploratory because this 63-session dataset has already influenced prior research direction.",
        "- No live trading, broker connectivity, credentials, webhooks, or order routing were added.",
        "",
        "## Tier 1 Infrastructure Validation",
        "",
        "- Resampling is anchored to each RTH session at `09:30 ET`, not midnight.",
        "- Source 1-minute timestamps are treated as bar-start labels.",
        "- Higher-timeframe signals become available only at `bar_end` after all source 1-minute bars are complete.",
        "- Entries and exits are simulated on the original 1-minute bars.",
        "- The executor enforces one open position, daily trade limits, and stop-after-first-loser modes.",
        "- Same-bar stop/target ambiguity is counted and resolved stop-first.",
        "",
        "## Benchmark",
        "",
        f"- Benchmark: `{PHASE3B_BENCHMARK['candidate_id']}` in `{PHASE3B_BENCHMARK['mode']}` mode.",
        f"- Benchmark net PnL `${PHASE3B_BENCHMARK['net_pnl']:.2f}`, holdout `${PHASE3B_BENCHMARK['holdout_pnl']:.2f}`, 4-tick slippage `${PHASE3B_BENCHMARK['slippage_4_ticks_net_pnl']:.2f}`, trades `{PHASE3B_BENCHMARK['trades']}`, active sessions `{PHASE3B_BENCHMARK['active_session_pct']:.1%}`, max exposure `{PHASE3B_BENCHMARK['max_simultaneous_exposure']}`.",
        "",
        "## Variant Counts By Family",
        "",
        "| Family | Planned Variants |",
        "| --- | ---: |",
    ]
    for _, row in result["variant_counts"].iterrows():
        lines.append(f"| {row['strategy_family']} | {int(row['planned_variants'])} |")

    lines.extend(["", "## Broad Exploratory Results", "", "| Family | Variants | Best Net | Best Holdout | Best 4-Tick Slip | Best Score | Paper Candidates |", "| --- | ---: | ---: | ---: | ---: | ---: | ---: |"])
    for _, row in family_summary.iterrows():
        lines.append(
            f"| {row['strategy_family']} | {int(row['variants'])} | ${row['best_net_pnl']:.2f} | ${row['best_holdout_pnl']:.2f} | ${row['best_slippage_4_ticks']:.2f} | {row['best_score']:.2f} | {int(row['paper_candidates'])} |"
        )

    lines.extend(["", "## Timeframe Summary", "", "| Signal TF | Variants | Best Net | Best Holdout | Best 4-Tick Slip | Best Score | Paper Candidates |", "| ---: | ---: | ---: | ---: | ---: | ---: | ---: |"])
    for _, row in timeframe_summary.iterrows():
        lines.append(
            f"| {int(row['signal_timeframe'])}m | {int(row['variants'])} | ${row['best_net_pnl']:.2f} | ${row['best_holdout_pnl']:.2f} | ${row['best_slippage_4_ticks']:.2f} | {row['best_score']:.2f} | {int(row['paper_candidates'])} |"
        )

    lines.extend(["", "## Tier 3 Focused Top-Family Table", "", "| Candidate | Family | TF | Label | Net | Holdout | 4-Tick Slip | Trades | Active % | Max Exp | Role | Risk Notes |", "| --- | --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |"])
    for _, row in focused.iterrows():
        lines.append(_report_candidate_row(row))

    lines.extend(["", "## High-Confidence Candidates", ""])
    if paper.empty:
        lines.append("- No new candidate reached `paper_trade_candidate` under the Phase 4A promotion rules.")
    else:
        for _, row in paper.sort_values("ranking_score", ascending=False).head(8).iterrows():
            lines.append(f"- `{row['candidate_id']}`: net `${row['net_pnl']:.2f}`, holdout `${row['holdout_pnl']:.2f}`, 4-tick `${row['slippage_4_ticks_net_pnl']:.2f}`, active `{row['active_session_pct']:.1%}`.")

    lines.extend(["", "## Robustness Confirmations", ""])
    if robustness.empty:
        lines.append("- No opening-range-failure robustness rows were generated.")
    else:
        top_robust = robustness.head(6)
        for _, row in top_robust.iterrows():
            lines.append(f"- `{row['candidate_id']}` supports the nearby opening-range-failure family: net `${row['net_pnl']:.2f}`, label `{row['label']}`.")

    lines.extend(["", "## Likely Over-Search / Overfit Results", ""])
    if overfit.empty:
        lines.append("- No positive candidate was flagged primarily for one-day or one-trade concentration.")
    else:
        for _, row in overfit.head(6).iterrows():
            lines.append(f"- Ignore or heavily discount `{row['candidate_id']}` despite net `${row['net_pnl']:.2f}` because `{row['risk_notes']}`.")

    lines.extend(
        [
            "",
            "## Final Decision Answers",
            "",
            "1. Yes, higher chart timeframes can be tested from 1-minute data by session-anchored OHLCV resampling and delayed signal availability.",
            f"2. Generated timeframes: `{', '.join(f'{tf}m' for tf in TIMEFRAMES)}`.",
            f"3. Strategy variants tested: `{len(ranked)}`.",
            f"4. Best-performing family by focused ranking: `{best_family['strategy_family'] if best_family is not None else 'none'}`.",
            f"5. Best signal timeframe overall: `{int(best_timeframe['signal_timeframe'])}m`." if best_timeframe is not None else "5. Best signal timeframe overall: none.",
            f"6. Did anything beat the Phase 3B no-overlap benchmark? `{str(not beaters.empty).lower()}`.",
            f"7. New `paper_trade_candidate` count: `{new_paper_count}` (`{len(paper)}` total including robustness confirmations).",
            f"8. Phase 4B candidates: `{_phase4b_recommendations(ranked)}`.",
            f"9. Candidates to ignore despite high PnL: `{_ignore_list(overfit)}`.",
            f"10. Exact command: `python scripts/run_phase4a_multitimeframe_discovery.py`.",
            "",
            "## Practical Readout",
            "",
            f"- Which strategy family looks most promising? `{best_family['strategy_family'] if best_family is not None else 'none'}`.",
            f"- Which timeframe looks most useful? `{int(best_timeframe['signal_timeframe'])}m`." if best_timeframe is not None else "- Which timeframe looks most useful? none.",
            f"- Which result is practical to paper trade? `{best_practical['candidate_id'] if best_practical is not None else PHASE3B_BENCHMARK['candidate_id']}`.",
            f"- Should Phase 4B validate a new candidate? `{_phase4b_decision(beaters, paper)}`.",
            "",
            "## Outputs",
            "",
            f"- Ranked edges: `{paths['ranked']}`",
            f"- Top edges: `{paths['top']}`",
            f"- Family summary: `{paths['family_summary']}`",
            f"- Timeframe summary: `{paths['timeframe_summary']}`",
            f"- Trade logs: `{paths['trade_logs']}`",
            f"- Charts: `{paths['charts']}`",
            "",
        ]
    )
    paths["report"].write_text("\n".join(lines), encoding="utf-8")


def write_phase4a_trade_logs(top: pd.DataFrame, trade_logs: dict[str, pd.DataFrame], log_dir: Path) -> None:
    for _, row in top.iterrows():
        trades = trade_logs.get(row["candidate_id"])
        if trades is not None and not trades.empty:
            trades.to_csv(log_dir / f"{row['candidate_id']}.csv", index=False)


def write_phase4a_charts(
    top: pd.DataFrame,
    ranked: pd.DataFrame,
    trade_logs: dict[str, pd.DataFrame],
    family_summary: pd.DataFrame,
    timeframe_summary: pd.DataFrame,
    chart_dir: Path,
) -> None:
    import matplotlib.pyplot as plt

    for _, row in top.head(8).iterrows():
        trades = trade_logs.get(row["candidate_id"])
        if trades is None or trades.empty:
            continue
        ordered = trades.sort_values("entry_time")
        times = pd.to_datetime(ordered["entry_time"], utc=True).dt.tz_convert("America/New_York").dt.tz_localize(None)
        equity = ordered["net_pnl"].cumsum()
        drawdown = equity - equity.cummax()
        safe_id = _safe_filename(row["candidate_id"])
        plt.figure(figsize=(10, 4))
        plt.plot(times, equity)
        plt.title(f"Phase 4A Equity: {row['candidate_id']}")
        plt.xlabel("Entry time")
        plt.ylabel("Net PnL ($)")
        plt.tight_layout()
        plt.savefig(chart_dir / f"{safe_id}_equity.png")
        plt.close()

        plt.figure(figsize=(10, 4))
        plt.plot(times, drawdown)
        plt.title(f"Phase 4A Drawdown: {row['candidate_id']}")
        plt.xlabel("Entry time")
        plt.ylabel("Drawdown ($)")
        plt.tight_layout()
        plt.savefig(chart_dir / f"{safe_id}_drawdown.png")
        plt.close()

        weekly = ordered.groupby(times.dt.to_period("W"))["net_pnl"].sum()
        plt.figure(figsize=(10, 4))
        weekly.plot(kind="bar")
        plt.title(f"Phase 4A Weekly PnL: {row['candidate_id']}")
        plt.xlabel("Week")
        plt.ylabel("Net PnL ($)")
        plt.tight_layout()
        plt.savefig(chart_dir / f"{safe_id}_weekly.png")
        plt.close()

    if not family_summary.empty:
        plt.figure(figsize=(10, 5))
        family_summary.set_index("strategy_family")["best_score"].sort_values().plot(kind="barh")
        plt.title("Phase 4A Family Comparison")
        plt.xlabel("Best ranking score")
        plt.tight_layout()
        plt.savefig(chart_dir / "phase4a_family_comparison.png")
        plt.close()

    if not timeframe_summary.empty:
        plt.figure(figsize=(8, 4))
        timeframe_summary.sort_values("signal_timeframe").plot(x="signal_timeframe", y="best_score", kind="bar", legend=False, ax=plt.gca())
        plt.title("Phase 4A Timeframe Comparison")
        plt.xlabel("Signal timeframe (minutes)")
        plt.ylabel("Best ranking score")
        plt.tight_layout()
        plt.savefig(chart_dir / "phase4a_timeframe_comparison.png")
        plt.close()


def _prepare_symbol_data(full_data: pd.DataFrame, complete_sessions: list[Any]) -> dict[str, dict[str, Any]]:
    prepared: dict[str, dict[str, Any]] = {}
    for symbol, symbol_full in full_data.groupby("symbol", sort=True):
        full_symbol = symbol_full[symbol_full["trading_session"].isin(complete_sessions)].copy()
        one_minute = full_symbol[full_symbol["session_segment"] == "RTH"].sort_values("timestamp").copy()
        timeframes = {tf: resample_signal_bars(one_minute, tf) for tf in TIMEFRAMES}
        prepared[symbol] = {"full": full_symbol, "one_minute": one_minute, "timeframes": timeframes}
    return prepared


def _load_project_data(project_root: Path) -> pd.DataFrame:
    frames = [load_ohlcv_csv(path) for path in discover_data_files(project_root / "data" / "raw")]
    if not frames:
        raise RuntimeError("No raw CSV files found")
    return pd.concat(frames, ignore_index=True).sort_values(["symbol", "timestamp"])


def _clear_generated_dir(path: Path) -> None:
    for child in path.iterdir():
        if child.is_file():
            child.unlink()


def _p4_candidate(symbol: str, family: str, variant: str, timeframe: int, entry_rule: str, stop_rule: str, target_rule: str, mode: ExecutionMode, params: dict[str, Any], discovery_role: str = "new_candidate") -> Phase4ACandidate:
    return Phase4ACandidate(
        candidate_id=f"{symbol}_{family}_{variant}",
        instrument=symbol,
        family=family,
        variant=variant,
        signal_timeframe=timeframe,
        execution_timeframe="1m",
        entry_rule=entry_rule,
        stop_rule=stop_rule,
        target_rule=target_rule,
        time_stop="15:55 ET",
        mode=mode,
        params=params,
        discovery_role=discovery_role,
    )


def _has_overnight_data(full_data: pd.DataFrame | None, symbol: str, complete_sessions: list[Any] | None) -> bool:
    if full_data is None or complete_sessions is None:
        return True
    scoped = full_data[(full_data["symbol"] == symbol) & (full_data["trading_session"].isin(complete_sessions))]
    eth_counts = scoped[scoped["session_segment"] == "ETH"].groupby("trading_session").size()
    return bool(len(eth_counts) and (eth_counts > 0).mean() >= 0.90)


def _signals_opening_range_failure(df: pd.DataFrame, candidate: Phase4ACandidate) -> list[dict[str, Any]]:
    minutes = int(candidate.params["or_minutes"])
    bars_needed = int(np.ceil(minutes / candidate.signal_timeframe))
    signals = []
    for _, day in df.groupby("trading_session", sort=True):
        day = day.reset_index(drop=True)
        if len(day) <= bars_needed:
            continue
        opening = day.iloc[:bars_needed]
        or_high = float(opening["high"].max())
        or_low = float(opening["low"].min())
        midpoint = (or_high + or_low) / 2.0
        rng = max(or_high - or_low, float(candidate.params["min_range"]))
        broke_high = False
        broke_low = False
        emitted = 0
        cap = _signal_cap(candidate)
        for i in range(bars_needed, len(day)):
            if emitted >= cap:
                break
            row = day.iloc[i]
            if pd.Timestamp(row["bar_end"]).time() > time(12, 0):
                break
            broke_high = broke_high or float(row["high"]) > or_high
            broke_low = broke_low or float(row["low"]) < or_low
            if broke_high and float(row["close"]) < or_high:
                target = midpoint if candidate.params["target"] == "mid" else or_low
                signals.append(_signal(row, "short", or_high + rng * 0.35, target, "or_failure_short"))
                emitted += 1
                broke_high = False
            elif broke_low and float(row["close"]) > or_low:
                target = midpoint if candidate.params["target"] == "mid" else or_high
                signals.append(_signal(row, "long", or_low - rng * 0.35, target, "or_failure_long"))
                emitted += 1
                broke_low = False
    return signals


def _signals_opening_range_breakout(df: pd.DataFrame, candidate: Phase4ACandidate) -> list[dict[str, Any]]:
    minutes = int(candidate.params["or_minutes"])
    bars_needed = int(np.ceil(minutes / candidate.signal_timeframe))
    signals = []
    for _, day in df.groupby("trading_session", sort=True):
        day = day.reset_index(drop=True)
        if len(day) <= bars_needed:
            continue
        opening = day.iloc[:bars_needed]
        or_high = float(opening["high"].max())
        or_low = float(opening["low"].min())
        rng = max(or_high - or_low, float(candidate.params["min_range"]))
        used_sides: set[str] = set()
        emitted = 0
        cap = _signal_cap(candidate)
        for i in range(bars_needed, len(day)):
            if emitted >= cap:
                break
            row = day.iloc[i]
            if pd.Timestamp(row["bar_end"]).time() > time(11, 30):
                break
            if float(row["close"]) > or_high and "long" not in used_sides:
                stop = or_high - rng * (0.25 if candidate.params["stop_mode"] == "inside" else 0.50)
                target = _target_from_r(row["close"], stop, "long", rng, candidate.params["target"])
                signals.append(_signal(row, "long", stop, target, "or_breakout_long"))
                emitted += 1
                used_sides.add("long")
            elif float(row["close"]) < or_low and "short" not in used_sides:
                stop = or_low + rng * (0.25 if candidate.params["stop_mode"] == "inside" else 0.50)
                target = _target_from_r(row["close"], stop, "short", rng, candidate.params["target"])
                signals.append(_signal(row, "short", stop, target, "or_breakout_short"))
                emitted += 1
                used_sides.add("short")
    return signals


def _signals_vwap_reclaim_rejection(df: pd.DataFrame, candidate: Phase4ACandidate) -> list[dict[str, Any]]:
    signals = []
    mode = candidate.params["mode"]
    tick = candidate.params["tick_size"]
    for _, day in df.groupby("trading_session", sort=True):
        day = day.reset_index(drop=True)
        emitted = 0
        cap = _signal_cap(candidate)
        for i in range(2, len(day)):
            if emitted >= cap:
                break
            row = day.iloc[i]
            prev = day.iloc[i - 1]
            if pd.Timestamp(row["bar_end"]).time() < time(9, 45) or pd.Timestamp(row["bar_end"]).time() > time(15, 0):
                continue
            if mode in ["reclaim", "both"] and float(prev["close"]) <= float(prev["vwap"]) and float(row["close"]) > float(row["vwap"]):
                signals.append(_fixed_signal(row, "long", candidate, tick, "vwap_reclaim_long"))
                emitted += 1
            if mode in ["rejection", "both"] and float(prev["close"]) >= float(prev["vwap"]) and float(row["close"]) < float(row["vwap"]):
                signals.append(_fixed_signal(row, "short", candidate, tick, "vwap_rejection_short"))
                emitted += 1
    return signals


def _signals_vwap_pullback(df: pd.DataFrame, candidate: Phase4ACandidate) -> list[dict[str, Any]]:
    signals = []
    for _, day in df.groupby("trading_session", sort=True):
        day = day.reset_index(drop=True)
        emitted = 0
        cap = _signal_cap(candidate)
        for i in range(3, len(day)):
            if emitted >= cap:
                break
            row = day.iloc[i]
            prev = day.iloc[i - 1]
            if pd.Timestamp(row["bar_end"]).time() > time(14, 30):
                break
            ref = float(row["vwap"] if candidate.params["pullback_ref"] == "vwap" else row["ema20"])
            uptrend = float(row["close"]) > float(row["vwap"]) and float(row["ema9"]) > float(row["ema20"])
            downtrend = float(row["close"]) < float(row["vwap"]) and float(row["ema9"]) < float(row["ema20"])
            if uptrend and float(row["low"]) <= ref <= float(row["high"]) and float(row["close"]) > float(prev["close"]):
                stop = float(row["low"]) - candidate.params["tick_size"]
                signals.append(_risk_signal(row, "long", stop, float(candidate.params["rr"]), "vwap_pullback_long"))
                emitted += 1
            elif downtrend and float(row["low"]) <= ref <= float(row["high"]) and float(row["close"]) < float(prev["close"]):
                stop = float(row["high"]) + candidate.params["tick_size"]
                signals.append(_risk_signal(row, "short", stop, float(candidate.params["rr"]), "vwap_pullback_short"))
                emitted += 1
    return signals


def _signals_prior_levels(df: pd.DataFrame, candidate: Phase4ACandidate) -> list[dict[str, Any]]:
    signals = []
    mode = candidate.params["mode"]
    tick = candidate.params["tick_size"]
    for _, day in df.groupby("trading_session", sort=True):
        day = day.reset_index(drop=True)
        if pd.isna(day.iloc[0]["prior_high"]):
            continue
        emitted = 0
        cap = _signal_cap(candidate)
        for i in range(1, len(day)):
            if emitted >= cap:
                break
            row = day.iloc[i]
            prev = day.iloc[i - 1]
            if pd.Timestamp(row["bar_end"]).time() > time(14, 30):
                break
            ph, pl, pc, pm = map(float, [row["prior_high"], row["prior_low"], row["prior_close"], row["prior_mid"]])
            if mode == "break_hold":
                if float(row["close"]) > ph:
                    signals.append(_fixed_signal(row, "long", candidate, tick, "prior_high_break_hold"))
                    emitted += 1
                elif float(row["close"]) < pl:
                    signals.append(_fixed_signal(row, "short", candidate, tick, "prior_low_break_hold"))
                    emitted += 1
            elif mode == "sweep_reverse":
                if float(row["high"]) > ph and float(row["close"]) < ph:
                    signals.append(_signal(row, "short", ph + candidate.params["stop_ticks"] * tick, pc, "prior_high_sweep_reverse"))
                    emitted += 1
                elif float(row["low"]) < pl and float(row["close"]) > pl:
                    signals.append(_signal(row, "long", pl - candidate.params["stop_ticks"] * tick, pc, "prior_low_sweep_reverse"))
                    emitted += 1
            elif mode == "prior_close_reclaim":
                if float(prev["close"]) <= pc < float(row["close"]):
                    signals.append(_fixed_signal(row, "long", candidate, tick, "prior_close_reclaim"))
                    emitted += 1
                elif float(prev["close"]) >= pc > float(row["close"]):
                    signals.append(_fixed_signal(row, "short", candidate, tick, "prior_close_failure"))
                    emitted += 1
            elif mode == "prior_mid_reclaim":
                if float(prev["close"]) <= pm < float(row["close"]):
                    signals.append(_fixed_signal(row, "long", candidate, tick, "prior_mid_reclaim"))
                    emitted += 1
                elif float(prev["close"]) >= pm > float(row["close"]):
                    signals.append(_fixed_signal(row, "short", candidate, tick, "prior_mid_failure"))
                    emitted += 1
    return signals


def _signals_overnight_levels(df: pd.DataFrame, full_df: pd.DataFrame, candidate: Phase4ACandidate) -> list[dict[str, Any]]:
    eth = full_df[full_df["session_segment"] == "ETH"]
    levels = eth.groupby("trading_session").agg(overnight_high=("high", "max"), overnight_low=("low", "min"))
    merged = df.merge(levels, left_on="trading_session", right_index=True, how="left")
    signals = []
    mode = candidate.params["mode"]
    tick = candidate.params["tick_size"]
    for _, day in merged.groupby("trading_session", sort=True):
        day = day.reset_index(drop=True)
        if pd.isna(day.iloc[0]["overnight_high"]):
            continue
        emitted = 0
        cap = _signal_cap(candidate)
        for i in range(1, len(day)):
            if emitted >= cap:
                break
            row = day.iloc[i]
            prev = day.iloc[i - 1]
            if pd.Timestamp(row["bar_end"]).time() > time(13, 0):
                break
            oh, ol = float(row["overnight_high"]), float(row["overnight_low"])
            mid = (oh + ol) / 2.0
            if mode == "sweep_reverse":
                if float(row["high"]) > oh and float(row["close"]) < oh:
                    signals.append(_signal(row, "short", oh + candidate.params["stop_ticks"] * tick, mid, "overnight_high_sweep"))
                    emitted += 1
                elif float(row["low"]) < ol and float(row["close"]) > ol:
                    signals.append(_signal(row, "long", ol - candidate.params["stop_ticks"] * tick, mid, "overnight_low_sweep"))
                    emitted += 1
            elif mode == "break_hold":
                if float(row["close"]) > oh:
                    signals.append(_fixed_signal(row, "long", candidate, tick, "overnight_high_break"))
                    emitted += 1
                elif float(row["close"]) < ol:
                    signals.append(_fixed_signal(row, "short", candidate, tick, "overnight_low_break"))
                    emitted += 1
            elif mode == "midpoint_reclaim":
                if float(prev["close"]) <= mid < float(row["close"]):
                    signals.append(_fixed_signal(row, "long", candidate, tick, "overnight_mid_reclaim"))
                    emitted += 1
                elif float(prev["close"]) >= mid > float(row["close"]):
                    signals.append(_fixed_signal(row, "short", candidate, tick, "overnight_mid_failure"))
                    emitted += 1
    return signals


def _signals_first_hour(df: pd.DataFrame, candidate: Phase4ACandidate) -> list[dict[str, Any]]:
    signals = []
    bars_needed = int(np.ceil(60 / candidate.signal_timeframe))
    for _, day in df.groupby("trading_session", sort=True):
        day = day.reset_index(drop=True)
        if len(day) <= bars_needed:
            continue
        first = day.iloc[:bars_needed]
        high, low = float(first["high"].max()), float(first["low"].min())
        direction = "long" if float(first.iloc[-1]["close"]) >= float(first.iloc[0]["open"]) else "short"
        for i in range(bars_needed, len(day)):
            row = day.iloc[i]
            if pd.Timestamp(row["bar_end"]).time() > time(12, 30):
                break
            if candidate.params["mode"] in ["expansion", "pullback"] and direction == "long" and float(row["close"]) > high:
                signals.append(_risk_signal(row, "long", low, float(candidate.params["rr"]), "first_hour_long"))
                break
            if candidate.params["mode"] in ["expansion", "pullback"] and direction == "short" and float(row["close"]) < low:
                signals.append(_risk_signal(row, "short", high, float(candidate.params["rr"]), "first_hour_short"))
                break
            if candidate.params["mode"] == "failed_extension" and float(row["high"]) > high and float(row["close"]) < high:
                signals.append(_risk_signal(row, "short", float(row["high"]), float(candidate.params["rr"]), "first_hour_failed_high"))
                break
            if candidate.params["mode"] == "failed_extension" and float(row["low"]) < low and float(row["close"]) > low:
                signals.append(_risk_signal(row, "long", float(row["low"]), float(candidate.params["rr"]), "first_hour_failed_low"))
                break
    return signals


def _signals_ma_pullback(df: pd.DataFrame, candidate: Phase4ACandidate) -> list[dict[str, Any]]:
    signals = []
    for _, day in df.groupby("trading_session", sort=True):
        day = day.reset_index(drop=True)
        emitted = 0
        cap = _signal_cap(candidate)
        for i in range(3, len(day)):
            if emitted >= cap:
                break
            row = day.iloc[i]
            prev = day.iloc[i - 1]
            if pd.Timestamp(row["bar_end"]).time() > time(14, 30):
                break
            up = float(row["ema9"]) > float(row["ema20"]) and float(row["close"]) > float(row["ema20"])
            down = float(row["ema9"]) < float(row["ema20"]) and float(row["close"]) < float(row["ema20"])
            if up and float(row["low"]) <= float(row["ema20"]) and float(row["close"]) > float(prev["close"]):
                signals.append(_risk_signal(row, "long", float(row["low"]) - candidate.params["tick_size"], float(candidate.params["rr"]), "ma_pullback_long"))
                emitted += 1
            elif down and float(row["high"]) >= float(row["ema20"]) and float(row["close"]) < float(prev["close"]):
                signals.append(_risk_signal(row, "short", float(row["high"]) + candidate.params["tick_size"], float(candidate.params["rr"]), "ma_pullback_short"))
                emitted += 1
    return signals


def _signals_compression(df: pd.DataFrame, candidate: Phase4ACandidate) -> list[dict[str, Any]]:
    signals = []
    for _, day in df.groupby("trading_session", sort=True):
        day = day.reset_index(drop=True)
        ranges = day["high"] - day["low"]
        for i in range(6, len(day)):
            row = day.iloc[i]
            if pd.Timestamp(row["bar_end"]).time() > time(14, 30):
                break
            window = day.iloc[i - 5 : i]
            high, low = float(window["high"].max()), float(window["low"].min())
            narrow = float((window["high"] - window["low"]).mean()) <= float(ranges.rolling(20, min_periods=6).mean().iloc[i]) * 0.75
            inside = all((window["high"] <= high) & (window["low"] >= low))
            if candidate.params["mode"] == "inside_bar":
                ok = inside
            elif candidate.params["mode"] == "low_realized_vol":
                ok = narrow
            else:
                ok = (high - low) <= float(ranges.rolling(20, min_periods=6).mean().iloc[i]) * 3.0
            if ok and float(row["close"]) > high:
                signals.append(_risk_signal(row, "long", low, float(candidate.params["rr"]), "compression_breakout_long"))
                break
            if ok and float(row["close"]) < low:
                signals.append(_risk_signal(row, "short", high, float(candidate.params["rr"]), "compression_breakout_short"))
                break
    return signals


def _signals_time_of_day(df: pd.DataFrame, candidate: Phase4ACandidate) -> list[dict[str, Any]]:
    start_text, end_text = candidate.params["window"].split("-")
    start_t = pd.Timestamp(start_text).time()
    end_t = pd.Timestamp(end_text).time()
    signals = []
    for _, day in df.groupby("trading_session", sort=True):
        day = day.reset_index(drop=True)
        window = day[(day["bar_start"].dt.time >= start_t) & (day["bar_end"].dt.time <= end_t)]
        if len(window) < 3:
            continue
        first = window.iloc[:2]
        high, low = float(first["high"].max()), float(first["low"].min())
        for _, row in window.iloc[2:].iterrows():
            if candidate.params["mode"] == "breakout":
                if float(row["close"]) > high:
                    signals.append(_risk_signal(row, "long", low, float(candidate.params["rr"]), "tod_breakout_long"))
                    break
                if float(row["close"]) < low:
                    signals.append(_risk_signal(row, "short", high, float(candidate.params["rr"]), "tod_breakout_short"))
                    break
            else:
                if float(row["high"]) > high and float(row["close"]) < high:
                    signals.append(_risk_signal(row, "short", float(row["high"]), float(candidate.params["rr"]), "tod_fade_short"))
                    break
                if float(row["low"]) < low and float(row["close"]) > low:
                    signals.append(_risk_signal(row, "long", float(row["low"]), float(candidate.params["rr"]), "tod_fade_long"))
                    break
    return signals


def _signal(row: pd.Series, side: str, stop: float, target: float, reason: str) -> dict[str, Any]:
    return {
        "timestamp": row["bar_start"],
        "available_time": row["bar_end"],
        "trading_session": row["trading_session"],
        "side": side,
        "stop": float(stop),
        "target": float(target),
        "reason": reason,
    }


def _fixed_signal(row: pd.Series, side: str, candidate: Phase4ACandidate, tick: float, reason: str) -> dict[str, Any]:
    close = float(row["close"])
    stop_ticks = float(candidate.params["stop_ticks"])
    target_ticks = float(candidate.params["target_ticks"])
    if side == "long":
        return _signal(row, side, close - stop_ticks * tick, close + target_ticks * tick, reason)
    return _signal(row, side, close + stop_ticks * tick, close - target_ticks * tick, reason)


def _risk_signal(row: pd.Series, side: str, stop: float, rr: float, reason: str) -> dict[str, Any]:
    close = float(row["close"])
    risk = max(abs(close - stop), 0.01)
    target = close + risk * rr if side == "long" else close - risk * rr
    return _signal(row, side, stop, target, reason)


def _target_from_r(close: float, stop: float, side: str, rng: float, target: str) -> float:
    if target == "range_extension":
        return close + rng if side == "long" else close - rng
    rr = float(target.replace("R", ""))
    risk = abs(close - stop)
    return close + risk * rr if side == "long" else close - risk * rr


def _signal_cap(candidate: Phase4ACandidate) -> int:
    return max(candidate.mode.max_trades_per_day * 4, 6)


def _empty_metrics() -> dict[str, Any]:
    return {
        "net_pnl": 0.0,
        "holdout_pnl": 0.0,
        "slippage_4_ticks_net_pnl": 0.0,
        "trades": 0,
        "trades_per_session": 0.0,
        "active_sessions": 0,
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
        "same_bar_stop_target_ambiguity_count": 0,
        "one_open_position_respected": True,
        "beats_phase3b_benchmark_net": False,
        "beats_phase3b_benchmark_slippage": False,
    }


def _phase4a_score(net_pnl: float, holdout_pnl: float, validation_pnl: float, strict_slippage: float, active_pct: float, trades: int, max_drawdown: float, day_conc: float, trade_conc: float) -> float:
    score = 0.0
    score += np.tanh(net_pnl / 1000.0) * 25
    score += np.tanh(holdout_pnl / 350.0) * 20
    score += np.tanh(validation_pnl / 350.0) * 10
    score += np.tanh(strict_slippage / 1000.0) * 15
    score += min(active_pct, 1.0) * 15
    score += min(trades / 80.0, 1.0) * 10
    score -= min(abs(max_drawdown) / 1500.0, 2.0) * 8
    score -= max(day_conc - 0.45, 0.0) * 25
    score -= max(trade_conc - 0.30, 0.0) * 25
    return round(float(score), 4)


def _phase4a_label(candidate: Phase4ACandidate, net_pnl: float, holdout_pnl: float, strict_slippage: float, active_pct: float, day_conc: float, trade_conc: float, max_exposure: int, trades: int, score: float) -> str:
    if trades < 10 or net_pnl <= 0 or max_exposure != 1:
        return "rejected"
    if candidate.discovery_role == "robustness_confirmation" and not (net_pnl > PHASE3B_BENCHMARK["net_pnl"] and strict_slippage > PHASE3B_BENCHMARK["slippage_4_ticks_net_pnl"]):
        return "watchlist" if strict_slippage > 0 else "interesting_but_needs_validation"
    if strict_slippage > 0 and active_pct >= 0.60 and day_conc <= 0.50 and trade_conc <= 0.35 and score >= 40 and holdout_pnl >= 0:
        return "paper_trade_candidate"
    if strict_slippage > 0 and net_pnl > 0:
        return "watchlist"
    return "interesting_but_needs_validation" if net_pnl > 0 else "rejected"


def _phase4a_risk_notes(net_pnl: float, holdout_pnl: float, strict_slippage: float, active_pct: float, day_conc: float, trade_conc: float, max_exposure: int, discovery_role: str) -> list[str]:
    notes = []
    if net_pnl <= 0:
        notes.append("negative net PnL")
    if holdout_pnl < 0:
        notes.append("negative holdout PnL")
    if strict_slippage < 0:
        notes.append("fails 4-tick slippage")
    if active_pct < 0.70:
        notes.append("active on less than 70% of sessions")
    if day_conc > 0.50:
        notes.append("one-day concentration risk")
    if trade_conc > 0.35:
        notes.append("one-trade concentration risk")
    if max_exposure != 1:
        notes.append("max exposure not exactly 1")
    if discovery_role == "robustness_confirmation":
        notes.append("opening-range-failure robustness confirmation, not independent discovery")
    return notes


def _profit_factor(wins: float, losses: float) -> float:
    if losses == 0:
        return float("inf") if wins > 0 else 0.0
    return float(wins / abs(losses))


def _concentration(value: float, net_pnl: float) -> float:
    return float(value / net_pnl) if net_pnl > 0 else 1.0


def _format_params(params: dict[str, Any]) -> str:
    return ";".join(f"{key}={value}" for key, value in sorted(params.items()))


def _safe_filename(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in value)


def _report_candidate_row(row: pd.Series) -> str:
    return (
        f"| `{row['candidate_id']}` | {row['strategy_family']} | {int(row['signal_timeframe'])}m | {row['label']} | "
        f"${row['net_pnl']:.2f} | ${row['holdout_pnl']:.2f} | ${row['slippage_4_ticks_net_pnl']:.2f} | "
        f"{int(row['trades'])} | {row['active_session_pct']:.1%} | {int(row['max_simultaneous_exposure'])} | {row['discovery_role']} | {row['risk_notes']} |"
    )


def _best_practical(top: pd.DataFrame, ranked: pd.DataFrame) -> pd.Series | None:
    practical = ranked[(ranked["label"] == "paper_trade_candidate") & (ranked["discovery_role"] == "new_candidate")]
    if practical.empty:
        practical = ranked[(ranked["label"].isin(["paper_trade_candidate", "watchlist"])) & (ranked["max_simultaneous_exposure"] == 1)]
    if practical.empty:
        return None
    return practical.sort_values(["label", "ranking_score"], ascending=[True, False]).iloc[0]


def _phase4b_recommendations(ranked: pd.DataFrame) -> str:
    candidates = ranked[
        (ranked["label"].isin(["paper_trade_candidate", "watchlist"]))
        & (ranked["max_simultaneous_exposure"] == 1)
        & (ranked["slippage_4_ticks_net_pnl"] > 0)
    ].sort_values("ranking_score", ascending=False)
    if candidates.empty:
        return PHASE3B_BENCHMARK["candidate_id"]
    return ", ".join(candidates.head(4)["candidate_id"].tolist())


def _ignore_list(overfit: pd.DataFrame) -> str:
    if overfit.empty:
        return "none flagged"
    return ", ".join(overfit.head(4)["candidate_id"].tolist())


def _phase4b_decision(beaters: pd.DataFrame, paper: pd.DataFrame) -> str:
    if not beaters.empty and not paper.empty:
        return "validate the strongest new candidate alongside the current MNQ opening-range-failure benchmark"
    return "continue with the current MNQ opening-range-failure paper test; use Phase 4A as exploratory context"
