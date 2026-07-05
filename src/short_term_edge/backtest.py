from __future__ import annotations

from dataclasses import dataclass
from datetime import time
from typing import Any

import numpy as np
import pandas as pd

from .instruments import InstrumentSpec


FLATTEN_TIME = time(15, 55)


@dataclass(frozen=True)
class Candidate:
    candidate_id: str
    instrument: str
    family: str
    variant: str
    params: dict[str, Any]


def prepare_indicators(df: pd.DataFrame) -> pd.DataFrame:
    out = df.sort_values("timestamp").copy()
    out = out[out["session_segment"] == "RTH"].copy()
    out["date"] = pd.to_datetime(out["trading_session"]).dt.date
    typical = (out["high"] + out["low"] + out["close"]) / 3.0
    pv = typical * out["volume"]
    out["vwap"] = pv.groupby(out["trading_session"]).cumsum() / out["volume"].groupby(out["trading_session"]).cumsum()
    out["bar_index"] = out.groupby("trading_session").cumcount()
    out["sma9"] = out.groupby("trading_session")["close"].transform(lambda s: s.rolling(9, min_periods=5).mean())
    out["sma20"] = out.groupby("trading_session")["close"].transform(lambda s: s.rolling(20, min_periods=10).mean())
    out["minute"] = out["timestamp"].dt.strftime("%H:%M")

    daily = out.groupby("trading_session").agg(
        session_high=("high", "max"),
        session_low=("low", "min"),
        session_close=("close", "last"),
    )
    out["prior_high"] = out["trading_session"].map(daily["session_high"].shift(1))
    out["prior_low"] = out["trading_session"].map(daily["session_low"].shift(1))
    out["prior_close"] = out["trading_session"].map(daily["session_close"].shift(1))
    return out


def overnight_levels(full_df: pd.DataFrame) -> pd.DataFrame:
    eth = full_df[full_df["session_segment"] == "ETH"].copy()
    levels = eth.groupby("trading_session").agg(
        overnight_high=("high", "max"),
        overnight_low=("low", "min"),
    )
    return levels


def simulate_candidate(
    df: pd.DataFrame,
    full_df: pd.DataFrame,
    candidate: Candidate,
    spec: InstrumentSpec,
    complete_sessions: list[Any],
) -> pd.DataFrame:
    signals = generate_signals(df, full_df, candidate)
    if not signals:
        return pd.DataFrame()

    rows: list[dict[str, Any]] = []
    by_session = {session: g.reset_index(drop=True) for session, g in df.groupby("trading_session", sort=True)}
    for signal in signals:
        session = signal["trading_session"]
        day = by_session.get(session)
        if day is None:
            continue
        signal_pos = int(signal["row_pos"])
        entry_pos = signal_pos + 1
        if entry_pos >= len(day):
            continue
        entry_row = day.iloc[entry_pos]
        if entry_row["timestamp"].time() >= FLATTEN_TIME:
            continue
        trade = _simulate_trade(day, entry_pos, signal["side"], signal["stop"], signal["target"], spec)
        if trade is None:
            continue
        rows.append(
            {
                **trade,
                "candidate_id": candidate.candidate_id,
                "instrument": candidate.instrument,
                "family": candidate.family,
                "variant": candidate.variant,
                "params": _format_params(candidate.params),
                "signal_time": signal["timestamp"],
                "trading_session": session,
                "side": signal["side"],
                "reason": signal["reason"],
                "base_cost": spec.base_cost,
                "stress_cost": spec.stress_cost,
                "net_pnl": trade["gross_pnl"] - spec.base_cost,
                "stress_net_pnl": trade["gross_pnl"] - spec.stress_cost,
            }
        )
    result = pd.DataFrame(rows)
    if result.empty:
        return result
    result["split"] = result["trading_session"].map(split_sessions(complete_sessions))
    result["entry_hour"] = pd.to_datetime(result["entry_time"]).dt.strftime("%H:%M")
    return result


def generate_signals(df: pd.DataFrame, full_df: pd.DataFrame, candidate: Candidate) -> list[dict[str, Any]]:
    family = candidate.family
    if family == "opening_range_breakout":
        return _opening_range_breakout(df, candidate)
    if family == "opening_range_failure":
        return _opening_range_failure(df, candidate)
    if family == "vwap_reclaim_rejection":
        return _vwap_reclaim_rejection(df, candidate)
    if family == "vwap_pullback_trend":
        return _vwap_pullback_trend(df, candidate)
    if family == "prior_session_levels":
        return _prior_session_levels(df, candidate)
    if family == "overnight_levels":
        return _overnight_levels(df, full_df, candidate)
    if family == "first_hour_continuation":
        return _first_hour_continuation(df, candidate)
    if family == "power_hour":
        return _power_hour(df, candidate)
    raise ValueError(f"Unknown strategy family: {family}")


def split_sessions(sessions: list[Any]) -> dict[Any, str]:
    n = len(sessions)
    discovery_end = int(np.floor(n * 0.60))
    validation_end = int(np.floor(n * 0.80))
    mapping: dict[Any, str] = {}
    for idx, session in enumerate(sessions):
        if idx < discovery_end:
            mapping[session] = "discovery"
        elif idx < validation_end:
            mapping[session] = "validation"
        else:
            mapping[session] = "holdout"
    return mapping


def _simulate_trade(
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

    for pos in range(entry_pos, len(day)):
        row = day.iloc[pos]
        if row["timestamp"].time() >= FLATTEN_TIME:
            exit_price = float(row["open"])
            exit_time = row["timestamp"]
            exit_reason = "time_flatten"
            break
        high = float(row["high"])
        low = float(row["low"])
        if side == "long":
            stop_hit = low <= stop
            target_hit = high >= target
            if stop_hit:
                exit_price = stop
                exit_time = row["timestamp"]
                exit_reason = "stop"
                break
            if target_hit:
                exit_price = target
                exit_time = row["timestamp"]
                exit_reason = "target"
                break
        else:
            stop_hit = high >= stop
            target_hit = low <= target
            if stop_hit:
                exit_price = stop
                exit_time = row["timestamp"]
                exit_reason = "stop"
                break
            if target_hit:
                exit_price = target
                exit_time = row["timestamp"]
                exit_reason = "target"
                break

    gross_pnl = (exit_price - entry_price) * side_mult * spec.point_value
    return {
        "entry_time": entry_row["timestamp"],
        "entry_price": entry_price,
        "exit_time": exit_time,
        "exit_price": exit_price,
        "exit_reason": exit_reason,
        "stop_price": stop,
        "target_price": target,
        "gross_pnl": gross_pnl,
        "holding_minutes": int((exit_time - entry_row["timestamp"]).total_seconds() / 60),
    }


def _opening_range_breakout(df: pd.DataFrame, candidate: Candidate) -> list[dict[str, Any]]:
    minutes = candidate.params["or_minutes"]
    rr = candidate.params["rr"]
    side_filter = candidate.params["side"]
    signals: list[dict[str, Any]] = []
    for _, day in df.groupby("trading_session", sort=True):
        day = day.reset_index(drop=True)
        if len(day) <= minutes + 1:
            continue
        opening = day.iloc[:minutes]
        or_high = float(opening["high"].max())
        or_low = float(opening["low"].min())
        rng = max(or_high - or_low, candidate.params["min_range"])
        used = 0
        for i in range(minutes, len(day) - 1):
            row = day.iloc[i]
            if row["timestamp"].time() >= time(11, 30) or used >= candidate.params["max_trades"]:
                break
            bias_ok_long = candidate.params["filter"] == "none" or row["close"] > row["vwap"]
            bias_ok_short = candidate.params["filter"] == "none" or row["close"] < row["vwap"]
            if side_filter in ("both", "long") and row["close"] > or_high and bias_ok_long:
                signals.append(_signal(row, i, "long", or_high - rng * 0.50, or_high + rng * rr, "or_breakout_long"))
                used += 1
            elif side_filter in ("both", "short") and row["close"] < or_low and bias_ok_short:
                signals.append(_signal(row, i, "short", or_low + rng * 0.50, or_low - rng * rr, "or_breakout_short"))
                used += 1
    return signals


def _opening_range_failure(df: pd.DataFrame, candidate: Candidate) -> list[dict[str, Any]]:
    minutes = candidate.params["or_minutes"]
    signals: list[dict[str, Any]] = []
    for _, day in df.groupby("trading_session", sort=True):
        day = day.reset_index(drop=True)
        if len(day) <= minutes + 1:
            continue
        opening = day.iloc[:minutes]
        or_high = float(opening["high"].max())
        or_low = float(opening["low"].min())
        mid = (or_high + or_low) / 2
        rng = max(or_high - or_low, candidate.params["min_range"])
        broke_high = False
        broke_low = False
        used = 0
        for i in range(minutes, len(day) - 1):
            row = day.iloc[i]
            if row["timestamp"].time() >= time(12, 0) or used >= candidate.params["max_trades"]:
                break
            broke_high = broke_high or row["high"] > or_high
            broke_low = broke_low or row["low"] < or_low
            if broke_high and row["close"] < or_high:
                target = mid if candidate.params["target"] == "mid" else or_low
                signals.append(_signal(row, i, "short", or_high + rng * 0.35, target, "or_failure_short"))
                used += 1
                broke_high = False
            elif broke_low and row["close"] > or_low:
                target = mid if candidate.params["target"] == "mid" else or_high
                signals.append(_signal(row, i, "long", or_low - rng * 0.35, target, "or_failure_long"))
                used += 1
                broke_low = False
    return signals


def _vwap_reclaim_rejection(df: pd.DataFrame, candidate: Candidate) -> list[dict[str, Any]]:
    mode = candidate.params["mode"]
    stop_ticks = candidate.params["stop_ticks"]
    target_ticks = candidate.params["target_ticks"]
    tick = candidate.params["tick_size"]
    signals: list[dict[str, Any]] = []
    for _, day in df.groupby("trading_session", sort=True):
        day = day.reset_index(drop=True)
        used = 0
        for i in range(10, len(day) - 1):
            row = day.iloc[i]
            prev = day.iloc[i - 1]
            if row["timestamp"].time() < time(9, 45) or row["timestamp"].time() >= time(15, 0):
                continue
            if used >= candidate.params["max_trades"]:
                break
            if mode == "reclaim" and prev["close"] <= prev["vwap"] and row["close"] > row["vwap"]:
                signals.append(_fixed_signal(row, i, "long", stop_ticks, target_ticks, tick, "vwap_reclaim_long"))
                used += 1
            elif mode == "failure" and prev["close"] >= prev["vwap"] and row["close"] < row["vwap"]:
                signals.append(_fixed_signal(row, i, "short", stop_ticks, target_ticks, tick, "vwap_failure_short"))
                used += 1
            elif mode == "both":
                if prev["close"] <= prev["vwap"] and row["close"] > row["vwap"]:
                    signals.append(_fixed_signal(row, i, "long", stop_ticks, target_ticks, tick, "vwap_reclaim_long"))
                    used += 1
                elif prev["close"] >= prev["vwap"] and row["close"] < row["vwap"]:
                    signals.append(_fixed_signal(row, i, "short", stop_ticks, target_ticks, tick, "vwap_failure_short"))
                    used += 1
    return signals


def _vwap_pullback_trend(df: pd.DataFrame, candidate: Candidate) -> list[dict[str, Any]]:
    tick = candidate.params["tick_size"]
    tol = candidate.params["pullback_ticks"] * tick
    signals: list[dict[str, Any]] = []
    for _, day in df.groupby("trading_session", sort=True):
        day = day.reset_index(drop=True)
        used = 0
        for i in range(30, len(day) - 1):
            row = day.iloc[i]
            prev = day.iloc[i - 1]
            if row["timestamp"].time() >= time(14, 30) or used >= candidate.params["max_trades"]:
                break
            uptrend = row["close"] > row["vwap"] and row["sma9"] > row["sma20"]
            downtrend = row["close"] < row["vwap"] and row["sma9"] < row["sma20"]
            if uptrend and abs(row["low"] - row["vwap"]) <= tol and row["close"] > prev["close"]:
                signals.append(_fixed_signal(row, i, "long", candidate.params["stop_ticks"], candidate.params["target_ticks"], tick, "vwap_pullback_long"))
                used += 1
            elif downtrend and abs(row["high"] - row["vwap"]) <= tol and row["close"] < prev["close"]:
                signals.append(_fixed_signal(row, i, "short", candidate.params["stop_ticks"], candidate.params["target_ticks"], tick, "vwap_pullback_short"))
                used += 1
    return signals


def _prior_session_levels(df: pd.DataFrame, candidate: Candidate) -> list[dict[str, Any]]:
    mode = candidate.params["mode"]
    tick = candidate.params["tick_size"]
    signals: list[dict[str, Any]] = []
    for _, day in df.groupby("trading_session", sort=True):
        day = day.reset_index(drop=True)
        if pd.isna(day.iloc[0]["prior_high"]):
            continue
        used = 0
        for i in range(5, len(day) - 1):
            row = day.iloc[i]
            if row["timestamp"].time() >= time(14, 30) or used >= candidate.params["max_trades"]:
                break
            ph = float(row["prior_high"])
            pl = float(row["prior_low"])
            pc = float(row["prior_close"])
            if mode == "break_hold":
                if row["close"] > ph:
                    signals.append(_fixed_signal(row, i, "long", candidate.params["stop_ticks"], candidate.params["target_ticks"], tick, "prior_high_break_hold"))
                    used += 1
                elif row["close"] < pl:
                    signals.append(_fixed_signal(row, i, "short", candidate.params["stop_ticks"], candidate.params["target_ticks"], tick, "prior_low_break_hold"))
                    used += 1
            elif mode == "sweep_reverse":
                if row["high"] > ph and row["close"] < ph:
                    signals.append(_signal(row, i, "short", ph + candidate.params["stop_ticks"] * tick, pc, "prior_high_sweep_reverse"))
                    used += 1
                elif row["low"] < pl and row["close"] > pl:
                    signals.append(_signal(row, i, "long", pl - candidate.params["stop_ticks"] * tick, pc, "prior_low_sweep_reverse"))
                    used += 1
            elif mode == "prior_close_reclaim":
                prev = day.iloc[i - 1]
                if prev["close"] <= pc < row["close"]:
                    signals.append(_fixed_signal(row, i, "long", candidate.params["stop_ticks"], candidate.params["target_ticks"], tick, "prior_close_reclaim"))
                    used += 1
                elif prev["close"] >= pc > row["close"]:
                    signals.append(_fixed_signal(row, i, "short", candidate.params["stop_ticks"], candidate.params["target_ticks"], tick, "prior_close_failure"))
                    used += 1
    return signals


def _overnight_levels(df: pd.DataFrame, full_df: pd.DataFrame, candidate: Candidate) -> list[dict[str, Any]]:
    levels = overnight_levels(full_df)
    merged = df.merge(levels, left_on="trading_session", right_index=True, how="left")
    mode = candidate.params["mode"]
    tick = candidate.params["tick_size"]
    signals: list[dict[str, Any]] = []
    for _, day in merged.groupby("trading_session", sort=True):
        day = day.reset_index(drop=True)
        if pd.isna(day.iloc[0]["overnight_high"]):
            continue
        used = 0
        for i in range(5, len(day) - 1):
            row = day.iloc[i]
            if row["timestamp"].time() >= time(13, 0) or used >= candidate.params["max_trades"]:
                break
            oh = float(row["overnight_high"])
            ol = float(row["overnight_low"])
            if mode == "break_hold":
                if row["close"] > oh:
                    signals.append(_fixed_signal(row, i, "long", candidate.params["stop_ticks"], candidate.params["target_ticks"], tick, "overnight_high_break"))
                    used += 1
                elif row["close"] < ol:
                    signals.append(_fixed_signal(row, i, "short", candidate.params["stop_ticks"], candidate.params["target_ticks"], tick, "overnight_low_break"))
                    used += 1
            elif mode == "sweep_reverse":
                mid = (oh + ol) / 2
                if row["high"] > oh and row["close"] < oh:
                    signals.append(_signal(row, i, "short", oh + candidate.params["stop_ticks"] * tick, mid, "overnight_high_sweep"))
                    used += 1
                elif row["low"] < ol and row["close"] > ol:
                    signals.append(_signal(row, i, "long", ol - candidate.params["stop_ticks"] * tick, mid, "overnight_low_sweep"))
                    used += 1
    return signals


def _first_hour_continuation(df: pd.DataFrame, candidate: Candidate) -> list[dict[str, Any]]:
    tick = candidate.params["tick_size"]
    signals: list[dict[str, Any]] = []
    for _, day in df.groupby("trading_session", sort=True):
        day = day.reset_index(drop=True)
        if len(day) < 75:
            continue
        first_hour = day.iloc[:60]
        high = float(first_hour["high"].max())
        low = float(first_hour["low"].min())
        direction = "long" if first_hour.iloc[-1]["close"] > first_hour.iloc[0]["open"] else "short"
        used = 0
        for i in range(60, len(day) - 1):
            row = day.iloc[i]
            if row["timestamp"].time() >= time(12, 30) or used >= candidate.params["max_trades"]:
                break
            if direction == "long" and row["close"] > high and row["close"] > row["vwap"]:
                signals.append(_fixed_signal(row, i, "long", candidate.params["stop_ticks"], candidate.params["target_ticks"], tick, "first_hour_up_continuation"))
                used += 1
            elif direction == "short" and row["close"] < low and row["close"] < row["vwap"]:
                signals.append(_fixed_signal(row, i, "short", candidate.params["stop_ticks"], candidate.params["target_ticks"], tick, "first_hour_down_continuation"))
                used += 1
    return signals


def _power_hour(df: pd.DataFrame, candidate: Candidate) -> list[dict[str, Any]]:
    tick = candidate.params["tick_size"]
    mode = candidate.params["mode"]
    signals: list[dict[str, Any]] = []
    for _, day in df.groupby("trading_session", sort=True):
        day = day.reset_index(drop=True)
        pre = day[day["timestamp"].dt.time < time(15, 0)]
        late = day[day["timestamp"].dt.time >= time(15, 0)].reset_index()
        if pre.empty or late.empty:
            continue
        pre_high = float(pre["high"].max())
        pre_low = float(pre["low"].min())
        day_open = float(day.iloc[0]["open"])
        used = 0
        for _, late_row in late.iterrows():
            i = int(late_row["index"])
            row = day.iloc[i]
            if row["timestamp"].time() >= time(15, 45) or used >= candidate.params["max_trades"]:
                break
            trend_up = row["close"] > day_open
            if mode == "continuation":
                if trend_up and row["close"] > pre_high:
                    signals.append(_fixed_signal(row, i, "long", candidate.params["stop_ticks"], candidate.params["target_ticks"], tick, "power_hour_continuation_long"))
                    used += 1
                elif not trend_up and row["close"] < pre_low:
                    signals.append(_fixed_signal(row, i, "short", candidate.params["stop_ticks"], candidate.params["target_ticks"], tick, "power_hour_continuation_short"))
                    used += 1
            elif mode == "reversal":
                if row["high"] > pre_high and row["close"] < pre_high:
                    signals.append(_fixed_signal(row, i, "short", candidate.params["stop_ticks"], candidate.params["target_ticks"], tick, "power_hour_reversal_short"))
                    used += 1
                elif row["low"] < pre_low and row["close"] > pre_low:
                    signals.append(_fixed_signal(row, i, "long", candidate.params["stop_ticks"], candidate.params["target_ticks"], tick, "power_hour_reversal_long"))
                    used += 1
    return signals


def _fixed_signal(row: pd.Series, pos: int, side: str, stop_ticks: float, target_ticks: float, tick: float, reason: str) -> dict[str, Any]:
    close = float(row["close"])
    if side == "long":
        return _signal(row, pos, side, close - stop_ticks * tick, close + target_ticks * tick, reason)
    return _signal(row, pos, side, close + stop_ticks * tick, close - target_ticks * tick, reason)


def _signal(row: pd.Series, pos: int, side: str, stop: float, target: float, reason: str) -> dict[str, Any]:
    return {
        "timestamp": row["timestamp"],
        "trading_session": row["trading_session"],
        "row_pos": pos,
        "side": side,
        "stop": float(stop),
        "target": float(target),
        "reason": reason,
    }


def _format_params(params: dict[str, Any]) -> str:
    return ";".join(f"{key}={value}" for key, value in sorted(params.items()))

