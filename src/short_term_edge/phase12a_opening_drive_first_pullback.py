from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from .backtest import split_sessions
from .instruments import get_instrument
from .phase_common import (
    add_cost_waterfall,
    concentration_diagnostics,
    daily_pnl_summary,
    deterministic_json,
    fold_summary,
    grouped_trade_summary,
    positive_concentration,
    safe_divide,
    serialize_specs,
    standard_zero_metrics,
)

OD_WINDOWS: dict[str, tuple[str, str]] = {
    "OD15": ("09:30", "09:45"),
    "OD30": ("09:30", "10:00"),
    "OD60": ("09:30", "10:30"),
}

PARTIAL_SESSIONS = {"2026-07-03"}


@dataclass(frozen=True)
class Phase12AConfig:
    max_specs: int = 48
    recent_sessions: int = 252
    train_sessions: int = 75
    validation_sessions: int = 25
    test_sessions: int = 25
    step_sessions: int = 25
    min_trades: int = 60
    min_active_days: int = 35
    drawdown_limit: float = -6_000.0
    worst_fold_limit: float = -1_500.0
    concentration_limit: float = 0.15
    trade_concentration_limit: float = 0.08
    narrow_watch_miss: float = 0.05


@dataclass(frozen=True)
class Phase12ASpec:
    branch: str
    side: str
    od_window: str
    od_start: str
    od_end: str
    pullback_anchor: str
    confirmation_model: str
    exit_variant: str
    timeframe: int = 5
    atr_cap_multiple: float = 1.25
    buffer_ticks: int = 1
    time_stop_minutes: int = 30
    max_trades_per_day: int = 1

    @property
    def candidate_id(self) -> str:
        return (
            f"MNQ_12a_odpullback_{self.branch}_{self.od_window}_{self.pullback_anchor}_"
            f"{self.confirmation_model}_{self.exit_variant}"
        )

    def to_dict(self) -> dict[str, Any]:
        return {"candidate_id": self.candidate_id, "instrument": "MNQ", **self.__dict__}


def build_phase12a_specs(config: Phase12AConfig = Phase12AConfig()) -> list[Phase12ASpec]:
    specs: list[Phase12ASpec] = []
    for branch, side in (("long_first_pullback", "long"), ("short_first_pullback", "short")):
        for od_window, (od_start, od_end) in OD_WINDOWS.items():
            for pullback_anchor in ("drive_boundary_retest", "ema20_retest"):
                for confirmation in ("resume_close_fill_next_open", "two_bar_resume_fill_next_open"):
                    for exit_variant in ("hard_stop_time_exit", "structure_target_time_exit"):
                        specs.append(
                            Phase12ASpec(
                                branch=branch,
                                side=side,
                                od_window=od_window,
                                od_start=od_start,
                                od_end=od_end,
                                pullback_anchor=pullback_anchor,
                                confirmation_model=confirmation,
                                exit_variant=exit_variant,
                            )
                        )
    return specs[: max(int(config.max_specs), 0)]


def compute_opening_drive_levels(bars: pd.DataFrame, od_window: str) -> pd.DataFrame:
    if bars.empty:
        return pd.DataFrame()
    if od_window not in OD_WINDOWS:
        raise ValueError(f"unknown opening drive window: {od_window}")
    start_s, end_s = OD_WINDOWS[od_window]
    start = _hhmm(start_s)
    end = _hhmm(end_s)
    rth = bars[bars["session_segment"].eq("RTH")].sort_values("timestamp").copy()
    minutes = _minutes(rth["timestamp"])
    scoped = rth[(minutes >= start) & (minutes < end)]
    if scoped.empty:
        return pd.DataFrame()
    levels = scoped.groupby("trading_session").agg(
        opening_drive_open=("open", "first"),
        opening_drive_high=("high", "max"),
        opening_drive_low=("low", "min"),
        opening_drive_close=("close", "last"),
    )
    levels["opening_drive_midpoint"] = (levels["opening_drive_high"] + levels["opening_drive_low"]) / 2.0
    levels["opening_drive_width_points"] = levels["opening_drive_high"] - levels["opening_drive_low"]
    levels["opening_drive_close_position"] = levels.apply(
        lambda r: safe_divide(float(r["opening_drive_close"]) - float(r["opening_drive_low"]), float(r["opening_drive_width_points"])),
        axis=1,
    )
    levels["od_window"] = od_window
    levels["od_start"] = start_s
    levels["od_end"] = end_s
    return levels.reset_index()


def build_phase12a_feature_bars(bars: pd.DataFrame, spec: Phase12ASpec) -> pd.DataFrame:
    rth = bars[bars["session_segment"].eq("RTH")].sort_values("timestamp").copy()
    frames = []
    for _, day in rth.groupby("trading_session", sort=True):
        day = day.set_index("timestamp")
        res = (
            day.resample("5min", origin="start_day", offset="30min", label="left", closed="left")
            .agg(
                {
                    "symbol": "last",
                    "open": "first",
                    "high": "max",
                    "low": "min",
                    "close": "last",
                    "volume": "sum",
                    "trading_session": "last",
                    "session_segment": "last",
                }
            )
            .dropna(subset=["open", "high", "low", "close"])
            .reset_index()
        )
        frames.append(res)
    if not frames:
        return pd.DataFrame()
    out = pd.concat(frames, ignore_index=True)
    out = out.merge(compute_opening_drive_levels(bars, spec.od_window), on="trading_session", how="left")
    out = out.dropna(subset=["opening_drive_high", "opening_drive_low"]).sort_values(["trading_session", "timestamp"]).reset_index(drop=True)
    tr = (out["high"] - out["low"]).abs()
    out["atr"] = tr.groupby(out["trading_session"]).transform(lambda s: s.rolling(14, min_periods=3).mean()).fillna(tr)
    out["ema20"] = out.groupby("trading_session")["close"].transform(lambda s: s.ewm(span=20, adjust=False, min_periods=1).mean())
    out["opening_drive_width_bucket"] = pd.cut(
        out["opening_drive_width_points"],
        bins=[-float("inf"), 30.0, 60.0, float("inf")],
        labels=["narrow", "middle", "wide"],
    ).astype(str)
    out["opening_drive_close_position_bucket"] = pd.cut(
        out["opening_drive_close_position"],
        bins=[-float("inf"), 0.3, 0.7, float("inf")],
        labels=["bottom_30", "middle_40", "top_30"],
    ).astype(str)
    return out


def generate_phase12a_signals(features: pd.DataFrame, spec: Phase12ASpec) -> list[dict[str, Any]]:
    if features.empty:
        return []
    signals: list[dict[str, Any]] = []
    start = max(_hhmm(spec.od_end), 9 * 60 + 45)
    end = 13 * 60 + 30
    inst = get_instrument("MNQ")
    buffer = spec.buffer_ticks * inst.tick_size
    for _, day in features.groupby("trading_session", sort=True):
        day = day.sort_values("timestamp").reset_index(drop=True)
        if day.empty or not _trend_qualified(day.iloc[0], spec.side):
            continue
        od_high = float(day.iloc[0]["opening_drive_high"])
        od_low = float(day.iloc[0]["opening_drive_low"])
        od_mid = float(day.iloc[0]["opening_drive_midpoint"])
        extension_seen = False
        extension_high = od_high
        extension_low = od_low
        candidates: list[dict[str, Any]] = []
        for i in range(len(day) - 2):
            row = day.iloc[i]
            minute = _minute(row["timestamp"])
            if minute < _hhmm(spec.od_end):
                continue
            close = float(row["close"])
            high = float(row["high"])
            low = float(row["low"])
            if minute < start or minute >= end or not extension_seen:
                if spec.side == "long" and close > od_high:
                    extension_seen = True
                    extension_high = max(extension_high, high, close)
                elif spec.side == "short" and close < od_low:
                    extension_seen = True
                    extension_low = min(extension_low, low, close)
                continue
            ok = _pullback_ok(row, spec, od_high, od_low, od_mid, buffer)
            trend_close = close > float(row["open"]) if spec.side == "long" else close < float(row["open"])
            if not (ok and trend_close):
                if spec.side == "long" and close > od_high:
                    extension_high = max(extension_high, high, close)
                elif spec.side == "short" and close < od_low:
                    extension_low = min(extension_low, low, close)
                continue
            confirmation_time = row["timestamp"]
            entry_idx = i + 1
            if spec.confirmation_model == "two_bar_resume_fill_next_open":
                confirm = day.iloc[i + 1]
                confirm_trend = float(confirm["close"]) > float(confirm["open"]) if spec.side == "long" else float(confirm["close"]) < float(confirm["open"])
                if not confirm_trend:
                    continue
                confirmation_time = confirm["timestamp"]
                entry_idx = i + 2
            if entry_idx >= len(day):
                continue
            entry = day.iloc[entry_idx]
            entry_minute = _minute(entry["timestamp"])
            if entry_minute < start or entry_minute < 9 * 60 + 45 or entry_minute >= end:
                continue
            extension_distance = max(extension_high - od_high, 0.0) if spec.side == "long" else max(od_low - extension_low, 0.0)
            pullback_depth = max(extension_high - low, 0.0) if spec.side == "long" else max(high - extension_low, 0.0)
            candidates.append(
                {
                    "candidate_id": spec.candidate_id,
                    "signal_time": row["timestamp"],
                    "confirmation_time": confirmation_time,
                    "entry_time": entry["timestamp"],
                    "trading_session": str(row["trading_session"]),
                    "side": spec.side,
                    "branch": spec.branch,
                    "od_window": spec.od_window,
                    "pullback_anchor": spec.pullback_anchor,
                    "confirmation_model": spec.confirmation_model,
                    "exit_variant": spec.exit_variant,
                    "signal_close": close,
                    "opening_drive_high": od_high,
                    "opening_drive_low": od_low,
                    "opening_drive_midpoint": od_mid,
                    "opening_drive_width_points": float(row["opening_drive_width_points"]),
                    "opening_drive_width_bucket": str(row["opening_drive_width_bucket"]),
                    "opening_drive_close_position": float(row["opening_drive_close_position"]),
                    "opening_drive_close_position_bucket": str(row["opening_drive_close_position_bucket"]),
                    "ema20": float(row["ema20"]),
                    "atr": float(row.get("atr", 0.0) or 0.0),
                    "extension_high": extension_high,
                    "extension_low": extension_low,
                    "extension_extreme": extension_high if spec.side == "long" else extension_low,
                    "extension_distance_points": extension_distance,
                    "extension_distance_bucket": _distance_bucket(extension_distance),
                    "pullback_low": low,
                    "pullback_high": high,
                    "pullback_depth_points": pullback_depth,
                    "pullback_depth_bucket": _distance_bucket(pullback_depth),
                }
            )
        if candidates:
            first = dict(candidates[0])
            first["first_pullback_only"] = 1
            first["skipped_non_first_pullbacks"] = len(candidates) - 1
            signals.append(first)
    return signals


def run_phase12a_retest(bars: pd.DataFrame, config: Phase12AConfig = Phase12AConfig()) -> dict[str, pd.DataFrame]:
    specs = build_phase12a_specs(config)
    scoped = bars[~bars["trading_session"].astype(str).isin(PARTIAL_SESSIONS)].copy()
    sessions = sorted(scoped["trading_session"].dropna().astype(str).unique().tolist())
    split_map = split_sessions(sessions)
    rows = []
    trade_frames = []
    fold_frames = []
    invalid_rows = []
    feature_cache: dict[str, pd.DataFrame] = {}
    for spec in specs:
        if spec.od_window not in feature_cache:
            feature_cache[spec.od_window] = build_phase12a_feature_bars(scoped, spec)
        features = feature_cache[spec.od_window]
        signals = generate_phase12a_signals(features, spec)
        trades, invalid_count = simulate_phase12a_trades(features, signals, spec)
        if not trades.empty:
            trades["split"] = trades["trading_session"].astype(str).map(split_map)
            add_cost_waterfall(trades, instrument_symbol="MNQ", inplace=True)
            trade_frames.append(trades)
            fold_frames.append(_fold_rows(trades, spec, sessions, config))
        invalid_rows.append({"candidate_id": spec.candidate_id, "invalid_risk_skipped_count": invalid_count})
        rows.append(_candidate_row(spec, trades, invalid_count, signals, sessions, split_map, config))
    trade_logs = pd.concat(trade_frames, ignore_index=True) if trade_frames else pd.DataFrame()
    folds = pd.concat(fold_frames, ignore_index=True) if fold_frames else pd.DataFrame()
    candidates = pd.DataFrame(rows).sort_values(["phase12a_score", "stress_pnl"], ascending=[False, False]).reset_index(drop=True)
    candidates.insert(0, "phase12a_rank", range(1, len(candidates) + 1))
    return {
        "candidate_results": candidates,
        "trade_logs": trade_logs,
        "walk_forward_folds": folds,
        "daily_pnl": daily_pnl_summary(trade_logs),
        "concentration_diagnostics": concentration_diagnostics(trade_logs),
        "od_window_summary": _summary(trade_logs, "od_window"),
        "side_summary": _summary(trade_logs, "branch"),
        "pullback_anchor_summary": _summary(trade_logs, "pullback_anchor"),
        "confirmation_summary": _summary(trade_logs, "confirmation_model"),
        "exit_variant_summary": _summary(trade_logs, "exit_variant"),
        "exit_reason_summary": _summary(trade_logs, "exit_reason"),
        "opening_drive_width_summary": _summary(trade_logs, "opening_drive_width_bucket"),
        "opening_drive_close_position_summary": _summary(trade_logs, "opening_drive_close_position_bucket"),
        "extension_distance_summary": _summary(trade_logs, "extension_distance_bucket"),
        "pullback_depth_summary": _summary(trade_logs, "pullback_depth_bucket"),
        "mfe_mae_summary": _mfe_mae_summary(trade_logs),
        "invalid_risk_summary": pd.DataFrame(invalid_rows),
        "specs": pd.DataFrame([s.to_dict() for s in specs]),
    }


def simulate_phase12a_trades(features: pd.DataFrame, signals: list[dict[str, Any]], spec: Phase12ASpec) -> tuple[pd.DataFrame, int]:
    if features.empty or not signals:
        return pd.DataFrame(), 0
    inst = get_instrument("MNQ")
    day_map = {str(s): d.sort_values("timestamp").reset_index(drop=True) for s, d in features.groupby("trading_session", sort=True)}
    rows: list[dict[str, Any]] = []
    counts: dict[str, int] = {}
    invalid_count = 0
    for signal in sorted(signals, key=lambda x: x["entry_time"]):
        session = str(signal["trading_session"])
        if counts.get(session, 0) >= spec.max_trades_per_day:
            continue
        day = day_map.get(session)
        if day is None:
            continue
        matches = day.index[day["timestamp"].eq(pd.Timestamp(signal["entry_time"]))].tolist()
        if not matches:
            continue
        trade = _simulate_one(day, matches[0], signal, spec, inst)
        if trade is None:
            invalid_count += 1
            continue
        rows.append({**signal, **trade, **spec.to_dict()})
        counts[session] = counts.get(session, 0) + 1
    return pd.DataFrame(rows), invalid_count


def _simulate_one(day: pd.DataFrame, entry_pos: int, signal: dict[str, Any], spec: Phase12ASpec, inst) -> dict[str, Any] | None:
    entry = day.iloc[entry_pos]
    entry_price = float(entry["open"])
    buffer = spec.buffer_ticks * inst.tick_size
    atr = max(float(signal.get("atr", 0.0)), inst.tick_size * 8)
    if spec.side == "long":
        structural_stop = float(signal["pullback_low"]) - buffer
        atr_cap_stop = entry_price - atr * spec.atr_cap_multiple
        actual_stop = max(structural_stop, atr_cap_stop)
        if actual_stop >= entry_price:
            return None
        target = float(signal["extension_high"])
        if target <= entry_price:
            target = entry_price + inst.tick_size
    else:
        structural_stop = float(signal["pullback_high"]) + buffer
        atr_cap_stop = entry_price + atr * spec.atr_cap_multiple
        actual_stop = min(structural_stop, atr_cap_stop)
        if actual_stop <= entry_price:
            return None
        target = float(signal["extension_low"])
        if target >= entry_price:
            target = entry_price - inst.tick_size
    max_exit = pd.Timestamp(entry["timestamp"]) + pd.Timedelta(minutes=spec.time_stop_minutes)
    exit_price = float(entry["close"])
    exit_time = entry["timestamp"]
    exit_reason = "time_stop"
    mfe = mae = 0.0
    ambiguity = 0
    target_enabled = spec.exit_variant == "structure_target_time_exit"
    for pos in range(entry_pos, len(day)):
        row = day.iloc[pos]
        ts = pd.Timestamp(row["timestamp"])
        if spec.side == "long":
            fav = float(row["high"]) - entry_price
            adv = entry_price - float(row["low"])
            stop_hit = float(row["low"]) <= actual_stop
            target_hit = float(row["high"]) >= target if target_enabled else False
        else:
            fav = entry_price - float(row["low"])
            adv = float(row["high"]) - entry_price
            stop_hit = float(row["high"]) >= actual_stop
            target_hit = float(row["low"]) <= target if target_enabled else False
        mfe = max(mfe, fav * inst.point_value)
        mae = max(mae, adv * inst.point_value)
        if stop_hit:
            exit_price = actual_stop
            exit_time = ts
            exit_reason = "stop_same_bar_conservative" if target_hit else "stop"
            ambiguity = int(target_hit)
            break
        if target_hit:
            exit_price = target
            exit_time = ts
            exit_reason = "target"
            break
        if ts >= max_exit or _minute(ts) >= 15 * 60 + 45:
            exit_price = float(row["close"])
            exit_time = ts
            exit_reason = "session_flatten" if _minute(ts) >= 15 * 60 + 45 else "time_stop"
            break
    gross = (exit_price - entry_price) * (1 if spec.side == "long" else -1) * inst.point_value
    return {
        "entry_price": round(entry_price, 4),
        "exit_time": exit_time,
        "exit_price": round(exit_price, 4),
        "exit_reason": exit_reason,
        "structural_stop": round(structural_stop, 4),
        "atr_cap_stop": round(atr_cap_stop, 4),
        "actual_stop": round(actual_stop, 4),
        "target_price": round(target, 4),
        "gross_pnl": round(gross, 2),
        "net_pnl": round(gross - inst.base_cost, 2),
        "stress_pnl": round(gross - inst.stress_cost, 2),
        "mfe": round(mfe, 2),
        "mae": round(mae, 2),
        "same_bar_ambiguity": ambiguity,
        "stop_hit": int(exit_reason in {"stop", "stop_same_bar_conservative"}),
        "target_hit": int(exit_reason == "target"),
        "time_stop": int(exit_reason in {"time_stop", "session_flatten"}),
    }


def _candidate_row(spec: Phase12ASpec, trades: pd.DataFrame, invalid_count: int, signals: list[dict[str, Any]], sessions: list[str], split_map: dict[Any, str], config: Phase12AConfig) -> dict[str, Any]:
    row = spec.to_dict()
    first_count = len(signals)
    skipped_count = sum(int(s.get("skipped_non_first_pullbacks", 0)) for s in signals)
    if trades.empty:
        row.update(_zero_metrics())
    else:
        t = trades.copy()
        t["split"] = t["trading_session"].astype(str).map(split_map)
        add_cost_waterfall(t, instrument_symbol="MNQ", inplace=True)
        net = float(t["net_pnl"].sum())
        equity = t["net_pnl"].cumsum()
        daily = t.groupby("trading_session")["net_pnl"].sum()
        folds = _fold_rows(t, spec, sessions, config)
        row.update(
            {
                "trades": len(t),
                "active_days": int(t["trading_session"].nunique()),
                "trades_per_active_day": safe_divide(len(t), t["trading_session"].nunique()),
                "gross_pnl": round(float(t["gross_pnl"].sum()), 2),
                "fees_only_pnl": round(float(t["fees_only_pnl"].sum()), 2),
                "normal_slippage_pnl": round(float(t["normal_slippage_pnl"].sum()), 2),
                "net_pnl": round(net, 2),
                "stress_pnl": round(float(t["stress_pnl"].sum()), 2),
                "validation_pnl": round(float(t.loc[t["split"].eq("validation"), "net_pnl"].sum()), 2),
                "holdout_pnl": round(float(t.loc[t["split"].eq("holdout"), "net_pnl"].sum()), 2),
                "max_drawdown": round(float((equity - equity.cummax()).min()), 2),
                "best_day_concentration": positive_concentration(float(daily.max()), net),
                "best_trade_concentration": positive_concentration(float(t["net_pnl"].max()), net),
                "avg_mfe": round(float(t["mfe"].mean()), 2),
                "avg_mae": round(float(t["mae"].mean()), 2),
                "stop_hit_rate": safe_divide(int(t["stop_hit"].sum()), len(t)),
                "target_hit_rate": safe_divide(int(t["target_hit"].sum()), len(t)),
                "time_stop_rate": safe_divide(int(t["time_stop"].sum()), len(t)),
                **fold_summary(folds),
            }
        )
    row["invalid_risk_skipped_count"] = int(invalid_count)
    row["first_pullback_only_count"] = int(first_count)
    row["skipped_non_first_pullbacks"] = int(skipped_count)
    row["phase12a_label"] = _label(row, config)
    row["research_axis_status"] = _axis_status(row)
    row["phase12a_score"] = round(
        float(row.get("stress_pnl", 0))
        + float(row.get("walk_forward_stress_pnl", 0))
        - abs(float(row.get("max_drawdown", 0)))
        - 5000 * max(float(row.get("best_day_concentration", 1)) - config.concentration_limit, 0),
        4,
    )
    row["reject_reasons"] = _reasons(row, config)
    return row


def _label(r: dict[str, Any], c: Phase12AConfig) -> str:
    adequate_activity = r.get("trades", 0) >= c.min_trades and r.get("active_days", 0) >= c.min_active_days and 1 <= r.get("trades_per_active_day", 0) <= 3
    economics_positive = r.get("net_pnl", 0) > 0 and r.get("stress_pnl", 0) > 0 and r.get("validation_pnl", 0) > 0 and r.get("holdout_pnl", 0) > 0
    fold_ok = r.get("walk_forward_stress_pnl", 0) > 0 and r.get("positive_wf_test_folds_pct", 0) >= 0.9 and r.get("worst_wf_test_fold", 0) >= c.worst_fold_limit
    conc_ok = r.get("best_day_concentration", 1) <= c.concentration_limit and r.get("best_trade_concentration", 1) <= c.trade_concentration_limit
    drawdown_ok = r.get("max_drawdown", 0) >= c.drawdown_limit
    if adequate_activity and economics_positive and fold_ok and conc_ok and drawdown_ok:
        return "phase12a_candidate_for_paper_review"
    narrow_fold_miss = r.get("walk_forward_stress_pnl", 0) > 0 and r.get("positive_wf_test_folds_pct", 0) >= 0.75 and r.get("worst_wf_test_fold", 0) >= c.worst_fold_limit
    narrow_conc_miss = r.get("best_day_concentration", 1) <= c.concentration_limit + c.narrow_watch_miss and r.get("best_trade_concentration", 1) <= c.trade_concentration_limit + c.narrow_watch_miss
    if adequate_activity and economics_positive and drawdown_ok and (narrow_fold_miss or narrow_conc_miss):
        return "phase12a_watchlist_needs_more_history"
    if not adequate_activity:
        return "phase12a_rejected_low_activity"
    if r.get("net_pnl", 0) <= 0 or r.get("stress_pnl", 0) <= 0:
        return "phase12a_rejected_negative_stress"
    if r.get("validation_pnl", 0) <= 0:
        return "phase12a_rejected_negative_validation"
    if r.get("holdout_pnl", 0) <= 0:
        return "phase12a_rejected_negative_holdout"
    if not drawdown_ok:
        return "phase12a_rejected_drawdown"
    if not fold_ok:
        return "phase12a_rejected_fold_instability"
    if not conc_ok:
        return "phase12a_rejected_concentration"
    return "phase12a_rejected_fold_instability"


def _axis_status(r: dict[str, Any]) -> str:
    if r.get("phase12a_label") == "phase12a_candidate_for_paper_review":
        return "axis_review_packet_candidate"
    if r.get("phase12a_label") == "phase12a_watchlist_needs_more_history":
        return "axis_targeted_retest_candidate"
    if r.get("stress_pnl", 0) > 0 and r.get("validation_pnl", 0) > 0 and r.get("holdout_pnl", 0) > 0 and (r.get("best_day_concentration", 1) > 0.15 or r.get("best_trade_concentration", 1) > 0.08):
        return "axis_positive_but_concentrated"
    if r.get("gross_pnl", 0) > 0 and r.get("stress_pnl", 0) <= 0:
        return "axis_positive_but_cost_sensitive"
    if r.get("stress_pnl", 0) > 0:
        return "axis_positive_but_unstable"
    return "axis_failed"


def _reasons(r: dict[str, Any], c: Phase12AConfig) -> str:
    checks = [
        ("low activity", r.get("trades", 0) < c.min_trades or r.get("active_days", 0) < c.min_active_days or not (1 <= r.get("trades_per_active_day", 0) <= 3)),
        ("negative stress", r.get("net_pnl", 0) <= 0 or r.get("stress_pnl", 0) <= 0),
        ("negative validation", r.get("validation_pnl", 0) <= 0),
        ("negative holdout", r.get("holdout_pnl", 0) <= 0),
        ("drawdown", r.get("max_drawdown", 0) < c.drawdown_limit),
        ("fold instability", r.get("walk_forward_stress_pnl", 0) <= 0 or r.get("positive_wf_test_folds_pct", 0) < 0.9 or r.get("worst_wf_test_fold", 0) < c.worst_fold_limit),
        ("concentration", r.get("best_day_concentration", 1) > c.concentration_limit or r.get("best_trade_concentration", 1) > c.trade_concentration_limit),
    ]
    return "; ".join(name for name, bad in checks if bad) or "survived Phase 12A gates; review packet only"


def make_phase12a_recommendation(result: dict[str, pd.DataFrame]) -> dict[str, Any]:
    c = result["candidate_results"]
    if c.empty:
        return {"next_action": "framework_audit_b_before_more_strategy_families", "rationale": "No Phase 12A candidates were produced."}
    paper = c[c["phase12a_label"].eq("phase12a_candidate_for_paper_review")]
    if not paper.empty:
        return {"next_action": "phase12a_review_packet_only", "rationale": "At least one candidate passed Phase 12A gates; review only, not paper approval.", "top_candidate": paper.iloc[0].to_dict()}
    watch = c[c["phase12a_label"].eq("phase12a_watchlist_needs_more_history")]
    if not watch.empty:
        return {"next_action": "phase12b_targeted_opening_drive_pullback_diagnostic_retest", "rationale": "A positive opening-drive pullback axis narrowly missed one robustness gate.", "top_candidate": watch.iloc[0].to_dict()}
    positive_full = c[(c["stress_pnl"] > 0) & (c["validation_pnl"] > 0) & (c["holdout_pnl"] > 0)]
    if not positive_full.empty:
        return {"next_action": "park_opening_drive_pullback_as_research_signal", "rationale": "Phase 12A had positive axes but they remained concentrated or unstable.", "top_candidate": positive_full.iloc[0].to_dict()}
    positive_partial = c[(c["stress_pnl"] > 0) | ((c["validation_pnl"] > 0) & (c["holdout_pnl"] > 0))]
    if not positive_partial.empty:
        return {"next_action": "park_opening_drive_pullback_as_research_signal", "rationale": "Phase 12A found partial positive axes, but no branch survived stress, validation, and holdout together.", "top_candidate": positive_partial.iloc[0].to_dict()}
    return {"next_action": "framework_audit_b_before_more_strategy_families", "rationale": "No positive Phase 12A opening-drive pullback axis survived."}


def render_phase12a_report(result: dict[str, pd.DataFrame], recommendation: dict[str, Any], report_path: Path) -> str:
    c = result["candidate_results"]
    counts = c["phase12a_label"].value_counts().to_dict() if not c.empty else {}
    status = c["research_axis_status"].value_counts().to_dict() if not c.empty else {}
    lines = [
        "# Phase 12A Opening-Drive First Pullback Continuation",
        "",
        "Research/simulation only. No live trading, broker adapters, order routing, webhooks, credential storage, automated execution, or LLM-driven trade decisions.",
        "",
        "## Summary",
        "",
        f"- Specs evaluated: `{len(c)}`",
        f"- Trade rows: `{len(result['trade_logs'])}`",
        f"- Label counts: `{counts}`",
        f"- Research axis status counts: `{status}`",
        f"- Next action: `{recommendation.get('next_action')}`",
        f"- Rationale: {recommendation.get('rationale')}",
        "",
        "## Candidate Results",
        "",
        "| Candidate | Status | Label | Net | Stress | Val | Holdout | WF Stress | Notes |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for _, r in c.head(12).iterrows():
        lines.append(f"| `{r['candidate_id']}` | {r['research_axis_status']} | {r['phase12a_label']} | ${float(r['net_pnl']):.2f} | ${float(r['stress_pnl']):.2f} | ${float(r['validation_pnl']):.2f} | ${float(r['holdout_pnl']):.2f} | ${float(r['walk_forward_stress_pnl']):.2f} | {r['reject_reasons']} |")
    lines += [
        "",
        "## Outputs",
        "",
        "- `outputs/phase12a_candidate_results.csv`",
        "- `outputs/phase12a_trade_logs.csv`",
        "- `outputs/phase12a_walk_forward_folds.csv`",
        "- `outputs/phase12a_daily_pnl.csv`",
        "- `outputs/phase12a_concentration_diagnostics.csv`",
        "- `outputs/phase12a_od_window_summary.csv`",
        "- `outputs/phase12a_side_summary.csv`",
        "- `outputs/phase12a_pullback_anchor_summary.csv`",
        "- `outputs/phase12a_confirmation_summary.csv`",
        "- `outputs/phase12a_exit_reason_summary.csv`",
        "- `outputs/phase12a_opening_drive_width_summary.csv`",
        "- `outputs/phase12a_extension_distance_summary.csv`",
        "- `outputs/phase12a_pullback_depth_summary.csv`",
        "- `outputs/phase12a_mfe_mae_summary.csv`",
        "- `outputs/phase12a_strategy_specs.json`",
        "- `outputs/phase12a_next_action_recommendation.json`",
        f"- `{report_path.as_posix()}`",
    ]
    return "\n".join(lines) + "\n"


def _trend_qualified(row: pd.Series, side: str) -> bool:
    width = float(row["opening_drive_width_points"])
    if width <= 0:
        return False
    od_open = float(row["opening_drive_open"])
    od_close = float(row["opening_drive_close"])
    pos = float(row["opening_drive_close_position"])
    if side == "long":
        return od_close > od_open and pos >= 0.70
    return od_close < od_open and pos <= 0.30


def _pullback_ok(row: pd.Series, spec: Phase12ASpec, od_high: float, od_low: float, od_mid: float, buffer: float) -> bool:
    high = float(row["high"])
    low = float(row["low"])
    close = float(row["close"])
    ema = float(row["ema20"])
    if spec.pullback_anchor == "drive_boundary_retest":
        if spec.side == "long":
            return low <= od_high + buffer and close > od_high
        return high >= od_low - buffer and close < od_low
    if spec.side == "long":
        return low <= ema and close > ema and close > od_mid
    return high >= ema and close < ema and close < od_mid


def _fold_rows(trades: pd.DataFrame, spec: Phase12ASpec, sessions: list[str], c: Phase12AConfig) -> pd.DataFrame:
    rows = []
    window = c.train_sessions + c.validation_sessions + c.test_sessions
    start = 0
    fold = 1
    while start + window <= len(sessions):
        test = sessions[start + c.train_sessions + c.validation_sessions : start + window]
        seg = trades[trades["trading_session"].astype(str).isin(test)]
        rows.append({"candidate_id": spec.candidate_id, "fold": fold, "net_pnl": round(float(seg["net_pnl"].sum()), 2), "stress_pnl": round(float(seg["stress_pnl"].sum()), 2), "trades": len(seg)})
        start += c.step_sessions
        fold += 1
    return pd.DataFrame(rows)


def _zero_metrics() -> dict[str, Any]:
    metrics = standard_zero_metrics(include_gross_waterfall=True)
    metrics.update({"stop_hit_rate": 0.0, "target_hit_rate": 0.0, "time_stop_rate": 0.0})
    return metrics


def _summary(trades: pd.DataFrame, column: str) -> pd.DataFrame:
    return grouped_trade_summary(trades, column, include_gross=True)


def _mfe_mae_summary(trades: pd.DataFrame) -> pd.DataFrame:
    if trades.empty:
        return pd.DataFrame()
    out = trades.copy()
    out["mfe_mae_bucket"] = (out["mfe"] >= out["mae"]).map({True: "mfe_ge_mae", False: "mae_dominates"})
    return _summary(out, "mfe_mae_bucket")


def _distance_bucket(distance: float) -> str:
    if distance <= 5.0:
        return "small"
    if distance <= 15.0:
        return "medium"
    return "large"


def serialize_phase12a_specs(specs: list[Phase12ASpec]) -> str:
    return serialize_specs(specs)


def recommendation_to_json(rec: dict[str, Any]) -> str:
    return deterministic_json(rec)


def _hhmm(value: str) -> int:
    h, m = value.split(":")
    return int(h) * 60 + int(m)


def _minute(ts: Any) -> int:
    ts = pd.Timestamp(ts)
    return ts.hour * 60 + ts.minute


def _minutes(series: pd.Series) -> pd.Series:
    ts = pd.to_datetime(series)
    return ts.dt.hour * 60 + ts.dt.minute
