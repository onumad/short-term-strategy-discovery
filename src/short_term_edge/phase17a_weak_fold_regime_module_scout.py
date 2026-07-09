from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from .backtest import split_sessions
from .instruments import get_instrument
from .phase_common import (
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

PARTIAL_SESSIONS = {"2026-07-03"}
RESEARCH_ONLY_GUARDRAIL = "Research/simulation only. No live trading, broker adapters, order routing, webhooks, credential storage, automated execution, or LLM-driven trade decisions."
MODULE_FAMILIES = (
    "weak_fold_midday_extreme_reversal",
    "weak_fold_midpoint_reclaim_or_reject",
    "weak_fold_afternoon_compression_resolution",
)
SIDES = ("long", "short")
REGIME_VARIANTS = ("broad_weak_fold_high_vol_mixed", "strict_weak_fold_high_vol_mixed")
CONFIRMATION_MODELS = ("close_confirm_fill_next_open", "two_bar_confirm_fill_next_open")
EXIT_VARIANTS = ("hard_stop_time_exit", "structure_target_time_exit")
FAMILY_META = {
    "weak_fold_midday_extreme_reversal": {"trade_start": "12:00", "trade_end": "15:30", "target_type": "morning_midpoint"},
    "weak_fold_midpoint_reclaim_or_reject": {"trade_start": "12:00", "trade_end": "15:30", "target_type": "morning_opposite_extreme"},
    "weak_fold_afternoon_compression_resolution": {"trade_start": "14:00", "trade_end": "15:30", "target_type": "fixed_1_5r"},
}
TARGET_GAP_FLAGS = (
    "high_vol_mixed_power_expand_days",
    "high_vol_mixed_no_power_expand_days",
    "weak_fold_days",
    "no_trade_large_intraday_movement_days",
)


@dataclass(frozen=True)
class Phase17AConfig:
    max_specs: int = 48
    recent_sessions: int = 252
    train_sessions: int = 75
    validation_sessions: int = 25
    test_sessions: int = 25
    step_sessions: int = 25
    min_prior_sessions_for_percentile: int = 20
    min_trades: int = 60
    min_active_days: int = 35
    drawdown_limit: float = -6_000.0
    worst_fold_limit: float = -1_500.0
    concentration_limit: float = 0.15
    trade_concentration_limit: float = 0.08
    registry_avg_corr_limit: float = 0.35
    registry_max_corr_limit: float = 0.60
    module_fold_min_active_days: int = 10
    module_fold_min_trades: int = 10


@dataclass(frozen=True)
class Phase17ASpec:
    module_family: str
    side: str
    regime_variant: str
    confirmation_model: str
    exit_variant: str
    timeframe: int = 5
    atr_cap_multiple: float = 1.25
    buffer_ticks: int = 1
    time_stop_minutes: int = 30
    max_trades_per_day: int = 1
    flatten_time: str = "15:45"

    @property
    def candidate_id(self) -> str:
        return f"MNQ_17a_{self.module_family}_{self.side}_{self.regime_variant}_{self.confirmation_model}_{self.exit_variant}"

    def to_dict(self) -> dict[str, Any]:
        meta = FAMILY_META[self.module_family]
        return {
            "candidate_id": self.candidate_id,
            "instrument": "MNQ",
            "module_family": self.module_family,
            "side": self.side,
            "regime_variant": self.regime_variant,
            "confirmation_model": self.confirmation_model,
            "exit_variant": self.exit_variant,
            "timeframe": self.timeframe,
            "atr_cap_multiple": self.atr_cap_multiple,
            "buffer_ticks": self.buffer_ticks,
            "time_stop_minutes": self.time_stop_minutes,
            "max_trades_per_day": self.max_trades_per_day,
            "regime_build_start": "09:30",
            "regime_build_end": "12:00",
            "compression_build_start": "12:00" if self.module_family == "weak_fold_afternoon_compression_resolution" else None,
            "compression_build_end": "14:00" if self.module_family == "weak_fold_afternoon_compression_resolution" else None,
            "trade_start": meta["trade_start"],
            "trade_end": meta["trade_end"],
            "entry_rule": "later_bar_open",
            "target_type": meta["target_type"],
            "paper_trading_approved": False,
        }


def build_phase17a_specs(config: Phase17AConfig = Phase17AConfig()) -> list[Phase17ASpec]:
    specs: list[Phase17ASpec] = []
    for family in MODULE_FAMILIES:
        for side in SIDES:
            for regime in REGIME_VARIANTS:
                for confirm in CONFIRMATION_MODELS:
                    for exit_variant in EXIT_VARIANTS:
                        specs.append(Phase17ASpec(family, side, regime, confirm, exit_variant))
    return specs[: max(int(config.max_specs), 0)]


def resample_rth_5m(bars: pd.DataFrame) -> pd.DataFrame:
    rth = bars[bars["session_segment"].eq("RTH")].sort_values("timestamp").copy()
    frames = []
    for _, day in rth.groupby("trading_session", sort=True):
        res = (
            day.set_index("timestamp")
            .resample("5min", origin="start_day", offset="30min", label="left", closed="left")
            .agg({"symbol": "last", "open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum", "trading_session": "last", "session_segment": "last"})
            .dropna(subset=["open", "high", "low", "close"])
            .reset_index()
        )
        frames.append(res)
    if not frames:
        return pd.DataFrame()
    out = pd.concat(frames, ignore_index=True).sort_values(["trading_session", "timestamp"]).reset_index(drop=True)
    tr = (out["high"] - out["low"]).abs()
    out["atr"] = tr.groupby(out["trading_session"]).transform(lambda s: s.rolling(14, min_periods=3).mean()).fillna(tr)
    return out


def compute_phase17a_frozen_levels(bars5: pd.DataFrame, config: Phase17AConfig = Phase17AConfig()) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    prior_morning_ranges: list[float] = []
    prior_compression_ranges: list[float] = []
    for session, day in bars5.groupby("trading_session", sort=True):
        day = day.sort_values("timestamp")
        morning = _between(day, "09:30", "12:00")
        compression = _between(day, "12:00", "14:00")
        row: dict[str, Any] = {
            "trading_session": session,
            "prior_morning_range_sessions_used": len(prior_morning_ranges),
            "prior_compression_range_sessions_used": len(prior_compression_ranges),
            "morning_range_p65": _prior_percentile(prior_morning_ranges, 0.65) if len(prior_morning_ranges) >= config.min_prior_sessions_for_percentile else None,
            "morning_range_p75": _prior_percentile(prior_morning_ranges, 0.75) if len(prior_morning_ranges) >= config.min_prior_sessions_for_percentile else None,
            "compression_range_p60": _prior_percentile(prior_compression_ranges, 0.60) if len(prior_compression_ranges) >= config.min_prior_sessions_for_percentile else None,
        }
        if not morning.empty:
            mh = float(morning["high"].max()); ml = float(morning["low"].min())
            mo = float(morning.iloc[0]["open"]); mc = float(morning.iloc[-1]["close"]); mr = mh - ml
            first30 = _between(day, "09:30", "10:00")
            first60 = _between(day, "09:30", "10:30")
            post60 = _between(day, "10:30", "12:00")
            first30_dir = _direction(float(first30.iloc[0]["open"]), float(first30.iloc[-1]["close"])) if not first30.empty else "flat"
            first60_dir = _direction(float(first60.iloc[0]["open"]), float(first60.iloc[-1]["close"])) if not first60.empty else "flat"
            post_dir = _direction(float(post60.iloc[0]["open"]), float(post60.iloc[-1]["close"])) if not post60.empty else "flat"
            flip = first60_dir != "flat" and post_dir != "flat" and first60_dir != post_dir
            close_pos = safe_divide(mc - ml, mr)
            p65 = row["morning_range_p65"]; p75 = row["morning_range_p75"]
            broad = bool(p65 is not None and mr >= float(p65) and (0.20 <= close_pos <= 0.80 or flip))
            strict = bool(p75 is not None and mr >= float(p75) and 0.30 <= close_pos <= 0.70 and flip)
            expansion_ratio = safe_divide(mr, float(p65)) if p65 not in (None, 0) else 0.0
            row.update({
                "morning_high": mh, "morning_low": ml, "morning_midpoint": (mh + ml) / 2.0,
                "morning_open": mo, "morning_close": mc, "morning_range": mr,
                "morning_close_position": close_pos,
                "first_30m_direction": first30_dir, "first_60m_direction": first60_dir,
                "post_60m_to_1200_direction": post_dir, "direction_flip_flag": flip,
                "morning_expansion_ratio": expansion_ratio,
                "broad_weak_fold_high_vol_mixed": broad,
                "strict_weak_fold_high_vol_mixed": strict,
                "morning_build_bar_count": len(morning),
            })
            prior_morning_ranges.append(mr)
        else:
            row.update({"broad_weak_fold_high_vol_mixed": False, "strict_weak_fold_high_vol_mixed": False, "morning_build_bar_count": 0})
        if not compression.empty:
            ch = float(compression["high"].max()); cl = float(compression["low"].min()); cr = ch - cl
            p60 = row["compression_range_p60"]
            row.update({"compression_high": ch, "compression_low": cl, "compression_midpoint": (ch + cl) / 2.0, "compression_range": cr, "compression_qualified": bool(p60 is not None and cr <= float(p60)), "compression_build_bar_count": len(compression)})
            prior_compression_ranges.append(cr)
        else:
            row.update({"compression_qualified": False, "compression_build_bar_count": 0})
        rows.append(row)
    return pd.DataFrame(rows)

def build_phase17a_feature_bars(bars: pd.DataFrame, config: Phase17AConfig = Phase17AConfig()) -> pd.DataFrame:
    bars5 = resample_rth_5m(bars)
    if bars5.empty:
        return pd.DataFrame()
    levels = compute_phase17a_frozen_levels(bars5, config)
    out = bars5.merge(levels, on="trading_session", how="left")
    return out.sort_values(["trading_session", "timestamp"]).reset_index(drop=True)


def generate_phase17a_signals(features: pd.DataFrame, spec: Phase17ASpec) -> list[dict[str, Any]]:
    if features.empty:
        return []
    meta = FAMILY_META[spec.module_family]
    start = _hhmm(str(meta["trade_start"])); end = _hhmm(str(meta["trade_end"]))
    signals: list[dict[str, Any]] = []
    for _, day in features.groupby("trading_session", sort=True):
        day = day.sort_values("timestamp").reset_index(drop=True)
        candidates: list[dict[str, Any]] = []
        for i in range(len(day) - 2):
            row = day.iloc[i]
            minute = _minute(row["timestamp"])
            if minute < start or minute >= end:
                continue
            if not bool(row.get(spec.regime_variant, False)):
                continue
            ok = _signal_condition(row, spec)
            if not ok:
                continue
            confirmation_time = row["timestamp"]
            signal_row = row
            pullback_low = float(row["low"])
            pullback_high = float(row["high"])
            entry_idx = i + 1
            if spec.confirmation_model == "two_bar_confirm_fill_next_open":
                confirm = day.iloc[i + 1]
                if not _confirm_bar_ok(confirm, spec):
                    continue
                confirmation_time = confirm["timestamp"]
                signal_row = confirm
                pullback_low = min(pullback_low, float(confirm["low"]))
                pullback_high = max(pullback_high, float(confirm["high"]))
                entry_idx = i + 2
            if entry_idx >= len(day):
                continue
            entry = day.iloc[entry_idx]
            entry_minute = _minute(entry["timestamp"])
            if entry_minute < start or entry_minute >= end or entry_minute >= _hhmm(spec.flatten_time):
                continue
            candidates.append(_signal_dict(spec, row, signal_row, entry, confirmation_time, pullback_low, pullback_high))
        if candidates:
            first = dict(candidates[0])
            first["skipped_extra_signals_same_day"] = len(candidates) - 1
            signals.append(first)
    return signals


def _signal_condition(row: pd.Series, spec: Phase17ASpec) -> bool:
    if pd.isna(row.get("morning_high")) or pd.isna(row.get("morning_low")) or pd.isna(row.get("morning_midpoint")):
        return False
    high = float(row["high"]); low = float(row["low"]); close = float(row["close"])
    mh = float(row["morning_high"]); ml = float(row["morning_low"]); mid = float(row["morning_midpoint"])
    if spec.module_family == "weak_fold_midday_extreme_reversal":
        return (low < ml and close > ml) if spec.side == "long" else (high > mh and close < mh)
    if spec.module_family == "weak_fold_midpoint_reclaim_or_reject":
        return (low < mid and close > mid) if spec.side == "long" else (high > mid and close < mid)
    if pd.isna(row.get("compression_high")) or pd.isna(row.get("compression_low")) or not bool(row.get("compression_qualified", False)):
        return False
    return close > float(row["compression_high"]) if spec.side == "long" else close < float(row["compression_low"])


def _confirm_bar_ok(row: pd.Series, spec: Phase17ASpec) -> bool:
    if spec.module_family == "weak_fold_midday_extreme_reversal":
        level = float(row["morning_low"] if spec.side == "long" else row["morning_high"])
        return float(row["close"]) > level if spec.side == "long" else float(row["close"]) < level
    if spec.module_family == "weak_fold_midpoint_reclaim_or_reject":
        level = float(row["morning_midpoint"])
        return float(row["close"]) > level if spec.side == "long" else float(row["close"]) < level
    level = float(row["compression_high"] if spec.side == "long" else row["compression_low"])
    return float(row["close"]) > level if spec.side == "long" else float(row["close"]) < level


def _signal_dict(spec: Phase17ASpec, trigger_row: pd.Series, signal_row: pd.Series, entry: pd.Series, confirmation_time: Any, pullback_low: float, pullback_high: float) -> dict[str, Any]:
    return {
        "candidate_id": spec.candidate_id,
        "signal_time": trigger_row["timestamp"],
        "confirmation_time": confirmation_time,
        "entry_time": entry["timestamp"],
        "trading_session": str(trigger_row["trading_session"]),
        "module_family": spec.module_family,
        "side": spec.side,
        "regime_variant": spec.regime_variant,
        "confirmation_model": spec.confirmation_model,
        "exit_variant": spec.exit_variant,
        "signal_open": float(signal_row["open"]),
        "signal_high": float(signal_row["high"]),
        "signal_low": float(signal_row["low"]),
        "signal_close": float(signal_row["close"]),
        "pullback_low": float(pullback_low),
        "pullback_high": float(pullback_high),
        "atr": float(signal_row.get("atr", 0.0) or 0.0),
        "morning_high": _float_or_none(signal_row.get("morning_high")),
        "morning_low": _float_or_none(signal_row.get("morning_low")),
        "morning_midpoint": _float_or_none(signal_row.get("morning_midpoint")),
        "morning_range": _float_or_none(signal_row.get("morning_range")),
        "morning_close_position": _float_or_none(signal_row.get("morning_close_position")),
        "direction_flip_flag": bool(signal_row.get("direction_flip_flag", False)),
        "compression_high": _float_or_none(signal_row.get("compression_high")),
        "compression_low": _float_or_none(signal_row.get("compression_low")),
        "compression_midpoint": _float_or_none(signal_row.get("compression_midpoint")),
        "prior_morning_range_sessions_used": int(signal_row.get("prior_morning_range_sessions_used", 0) or 0),
    }


def simulate_phase17a_trades(features: pd.DataFrame, signals: list[dict[str, Any]], spec: Phase17ASpec) -> tuple[pd.DataFrame, int]:
    if features.empty or not signals:
        return pd.DataFrame(), 0
    inst = get_instrument("MNQ")
    day_map = {str(s): d.sort_values("timestamp").reset_index(drop=True) for s, d in features.groupby("trading_session", sort=True)}
    rows: list[dict[str, Any]] = []
    counts: dict[str, int] = {}
    invalid = 0
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
            invalid += 1
            continue
        rows.append({**signal, **trade, **spec.to_dict()})
        counts[session] = counts.get(session, 0) + 1
    return pd.DataFrame(rows), invalid


def _simulate_one(day: pd.DataFrame, entry_pos: int, signal: dict[str, Any], spec: Phase17ASpec, inst) -> dict[str, Any] | None:
    entry = day.iloc[entry_pos]
    entry_price = float(entry["open"])
    tick = inst.tick_size * spec.buffer_ticks
    atr = max(float(signal.get("atr", 0.0)), get_instrument("MNQ").tick_size * 8)
    risk_cap = atr * spec.atr_cap_multiple
    if spec.side == "long":
        structural_stop = float(signal["pullback_low"]) - tick
        atr_cap_stop = entry_price - risk_cap
        actual_stop = max(structural_stop, atr_cap_stop)
        if actual_stop >= entry_price:
            return None
        risk = entry_price - actual_stop
        target = _target_price(signal, spec, entry_price, risk)
    else:
        structural_stop = float(signal["pullback_high"]) + tick
        atr_cap_stop = entry_price + risk_cap
        actual_stop = min(structural_stop, atr_cap_stop)
        if actual_stop <= entry_price:
            return None
        risk = actual_stop - entry_price
        target = _target_price(signal, spec, entry_price, risk)
    max_exit = pd.Timestamp(entry["timestamp"]) + pd.Timedelta(minutes=spec.time_stop_minutes)
    flatten_minute = _hhmm(spec.flatten_time)
    exit_price = float(entry["close"]); exit_time = entry["timestamp"]; exit_reason = "time_stop"
    mfe = mae = 0.0; ambiguity = 0
    target_enabled = spec.exit_variant == "structure_target_time_exit"
    for pos in range(entry_pos, len(day)):
        row = day.iloc[pos]; ts = pd.Timestamp(row["timestamp"])
        if spec.side == "long":
            fav = float(row["high"]) - entry_price; adv = entry_price - float(row["low"])
            stop_hit = float(row["low"]) <= actual_stop; target_hit = float(row["high"]) >= target if target_enabled else False
        else:
            fav = entry_price - float(row["low"]); adv = float(row["high"]) - entry_price
            stop_hit = float(row["high"]) >= actual_stop; target_hit = float(row["low"]) <= target if target_enabled else False
        mfe = max(mfe, fav * inst.point_value); mae = max(mae, adv * inst.point_value)
        if stop_hit:
            exit_price = actual_stop; exit_time = ts; exit_reason = "stop_same_bar_conservative" if target_hit else "stop"; ambiguity = int(target_hit); break
        if target_hit:
            exit_price = target; exit_time = ts; exit_reason = "target"; break
        if ts >= max_exit or _minute(ts) >= flatten_minute:
            exit_price = float(row["close"]); exit_time = ts; exit_reason = "session_flatten" if _minute(ts) >= flatten_minute else "time_stop"; break
    gross = (exit_price - entry_price) * (1 if spec.side == "long" else -1) * inst.point_value
    return {"entry_price": round(entry_price, 4), "exit_time": exit_time, "exit_price": round(exit_price, 4), "exit_reason": exit_reason, "structural_stop": round(structural_stop, 4), "atr_cap_stop": round(atr_cap_stop, 4), "actual_stop": round(actual_stop, 4), "target_price": round(target, 4), "gross_pnl": round(gross, 2), "net_pnl": round(gross - inst.base_cost, 2), "stress_pnl": round(gross - inst.stress_cost, 2), "mfe": round(mfe, 2), "mae": round(mae, 2), "same_bar_ambiguity": ambiguity, "stop_hit": int(exit_reason in {"stop", "stop_same_bar_conservative"}), "target_hit": int(exit_reason == "target"), "time_stop": int(exit_reason in {"time_stop", "session_flatten"})}


def _target_price(signal: dict[str, Any], spec: Phase17ASpec, entry_price: float, risk: float) -> float:
    if spec.module_family == "weak_fold_midday_extreme_reversal":
        return float(signal["morning_midpoint"])
    if spec.module_family == "weak_fold_midpoint_reclaim_or_reject":
        return float(signal["morning_high"] if spec.side == "long" else signal["morning_low"])
    return entry_price + 1.5 * risk if spec.side == "long" else entry_price - 1.5 * risk


def run_phase17a_scout(bars: pd.DataFrame, registry_matrix: pd.DataFrame, playbook_daily: pd.DataFrame, scheduler_daily: pd.DataFrame, gap_features: pd.DataFrame, validation_policy: dict[str, Any] | None = None, config: Phase17AConfig = Phase17AConfig()) -> dict[str, pd.DataFrame]:
    config = _config_with_policy(config, validation_policy or {})
    specs = build_phase17a_specs(config)
    scoped = bars[~bars["trading_session"].astype(str).isin(PARTIAL_SESSIONS)].copy()
    sessions = sorted(scoped["trading_session"].dropna().astype(str).unique().tolist())
    split_map = split_sessions(sessions)
    features = build_phase17a_feature_bars(scoped, config) if specs else pd.DataFrame()
    gap_sets = _gap_session_sets(gap_features, playbook_daily, scheduler_daily)
    current_covered = _covered_sessions(playbook_daily) | _covered_sessions(scheduler_daily)
    rows: list[dict[str, Any]] = []
    trade_frames: list[pd.DataFrame] = []
    fold_frames: list[pd.DataFrame] = []
    adequacy_frames: list[pd.DataFrame] = []
    for spec in specs:
        signals = generate_phase17a_signals(features, spec)
        trades, invalid = simulate_phase17a_trades(features, signals, spec)
        folds = _fold_rows(trades, spec, sessions, config) if not trades.empty else _fold_rows(pd.DataFrame(columns=["trading_session", "net_pnl", "stress_pnl"]), spec, sessions, config)
        adequacy = _fold_adequacy_rows(folds, spec, config)
        fold_frames.append(folds)
        adequacy_frames.append(adequacy)
        if not trades.empty:
            trades["split"] = trades["trading_session"].astype(str).map(split_map)
            trade_frames.append(trades)
        rows.append(_candidate_row(spec, trades, invalid, signals, sessions, split_map, registry_matrix, playbook_daily, scheduler_daily, gap_sets, current_covered, folds, adequacy, config))
    trade_logs = pd.concat(trade_frames, ignore_index=True) if trade_frames else pd.DataFrame()
    folds_all = pd.concat(fold_frames, ignore_index=True) if fold_frames else pd.DataFrame()
    adequacy_all = pd.concat(adequacy_frames, ignore_index=True) if adequacy_frames else pd.DataFrame()
    candidates = pd.DataFrame(rows).sort_values(["phase17a_score", "stress_pnl"], ascending=[False, False]).reset_index(drop=True)
    candidates.insert(0, "phase17a_rank", range(1, len(candidates) + 1))
    return {
        "candidate_results": candidates,
        "trade_logs": trade_logs,
        "daily_pnl": daily_pnl_summary(trade_logs),
        "walk_forward_folds": folds_all,
        "concentration_diagnostics": concentration_diagnostics(trade_logs),
        "family_summary": grouped_trade_summary(trade_logs, "module_family", include_gross=True),
        "side_summary": grouped_trade_summary(trade_logs, "side", include_gross=True),
        "regime_variant_summary": grouped_trade_summary(trade_logs, "regime_variant", include_gross=True),
        "confirmation_summary": grouped_trade_summary(trade_logs, "confirmation_model", include_gross=True),
        "exit_variant_summary": grouped_trade_summary(trade_logs, "exit_variant", include_gross=True),
        "correlation_to_registry": _correlation_rows(candidates, "registry"),
        "correlation_to_playbook": _correlation_rows(candidates, "playbook"),
        "gap_coverage_summary": _gap_coverage_summary(candidates),
        "fold_view_summary": _fold_view_summary(folds_all),
        "module_fold_adequacy": adequacy_all,
        "specs": pd.DataFrame([s.to_dict() for s in specs]),
    }


def _candidate_row(spec: Phase17ASpec, trades: pd.DataFrame, invalid: int, signals: list[dict[str, Any]], sessions: list[str], split_map: dict[Any, str], registry_matrix: pd.DataFrame, playbook_daily: pd.DataFrame, scheduler_daily: pd.DataFrame, gap_sets: dict[str, set[str]], current_covered: set[str], folds: pd.DataFrame, adequacy: pd.DataFrame, config: Phase17AConfig) -> dict[str, Any]:
    row = spec.to_dict()
    daily = pd.DataFrame(columns=["trading_session", "net_pnl"])
    if trades.empty:
        row.update(_zero_metrics())
    else:
        t = trades.copy(); t["split"] = t["trading_session"].astype(str).map(split_map)
        net = float(t["net_pnl"].sum()); equity = t["net_pnl"].cumsum()
        daily = t.groupby("trading_session", as_index=False)["net_pnl"].sum(); daily_series = daily.set_index("trading_session")["net_pnl"]
        existing = folds[folds["fold_view"].eq("existing_project_folds")]
        row.update({"trades": len(t), "active_days": int(t["trading_session"].nunique()), "trades_per_active_day": safe_divide(len(t), t["trading_session"].nunique()), "gross_pnl": round(float(t["gross_pnl"].sum()), 2), "net_pnl": round(net, 2), "stress_pnl": round(float(t["stress_pnl"].sum()), 2), "validation_pnl": round(float(t.loc[t["split"].eq("validation"), "net_pnl"].sum()), 2), "holdout_pnl": round(float(t.loc[t["split"].eq("holdout"), "net_pnl"].sum()), 2), "max_drawdown": round(float((equity - equity.cummax()).min()), 2), "best_day_concentration": positive_concentration(float(daily_series.max()), net), "best_trade_concentration": positive_concentration(float(t["net_pnl"].max()), net), "avg_mfe": round(float(t["mfe"].mean()), 2), "avg_mae": round(float(t["mae"].mean()), 2), **fold_summary(existing)})
    reg = daily_correlation_to_matrix(daily, registry_matrix)
    play = daily_correlation_to_matrix(daily, _combined_playbook_matrix(playbook_daily, scheduler_daily))
    trade_sessions = set(trades["trading_session"].astype(str)) if not trades.empty else set()
    target_gap = set().union(
        gap_sets.get("high_vol_mixed_power_expand_days", set()),
        gap_sets.get("high_vol_mixed_no_power_expand_days", set()),
        gap_sets.get("weak_fold_days", set()),
        gap_sets.get("no_trade_large_intraday_movement_days", set()),
    )
    folds_below = int(adequacy["below_min_activity"].sum()) if not adequacy.empty else 0
    total_folds = len(adequacy) if not adequacy.empty else 0
    row.update({"average_correlation_to_registry": reg["average_abs_correlation"], "max_correlation_to_registry": reg["max_abs_correlation"], "average_correlation_to_playbook": play["average_abs_correlation"], "max_correlation_to_playbook": play["max_abs_correlation"], "gap_days_covered": len(trade_sessions & target_gap), "incremental_gap_days_covered": len((trade_sessions & target_gap) - current_covered), "invalid_risk_skipped_count": int(invalid), "signals_found": len(signals), "paper_trading_approved": False, "official_gates_passed": False, "validation_level": "module_level_validation", "primary_fold_view": "existing_project_folds", "companion_fold_views": "half_year_folds|rolling_6_month_test_folds|quarterly_folds", "fold_adequacy_status": "interpretable" if folds_below == 0 and total_folds > 0 else "low_activity_not_fully_interpretable", "folds_below_min_activity": folds_below, "rare_module_track_enabled": False, "default_scheduler_eligible": False})
    for gap_name, sessions_set in gap_sets.items():
        row[f"{gap_name}_covered"] = len(trade_sessions & sessions_set)
    row["rare_module_track_enabled"] = _is_rare_module(row, config)
    row["phase17a_label"] = _label(row, config)
    row["default_scheduler_eligible"] = _default_scheduler_eligible(row, config)
    row["signal_evidence_status"] = _signal_evidence(row)
    row["tradability_status"] = _tradability(row, config)
    row["research_track"] = _research_track(row)
    row["portfolio_role"] = _portfolio_role(row)
    row["reject_reasons"] = _reasons(row, config)
    row["phase17a_score"] = round(float(row.get("stress_pnl", 0)) + float(row.get("walk_forward_stress_pnl", 0)) + 25 * float(row.get("incremental_gap_days_covered", 0)) - abs(float(row.get("max_drawdown", 0))) - 1000 * max(float(row.get("average_correlation_to_registry", 1)) - config.registry_avg_corr_limit, 0), 4)
    return row


def daily_correlation_to_matrix(candidate_daily: pd.DataFrame, matrix: pd.DataFrame) -> dict[str, float]:
    if candidate_daily.empty or matrix.empty:
        return {"average_abs_correlation": 0.0, "max_abs_correlation": 0.0}
    base = matrix.copy()
    cand = candidate_daily.groupby("trading_session", as_index=False)["net_pnl"].sum().rename(columns={"net_pnl": "candidate_net_pnl"})
    merged = base.merge(cand, on="trading_session", how="outer").fillna(0.0)
    vals = [abs(_corr(merged["candidate_net_pnl"], merged[col])) for col in merged.columns if col not in {"trading_session", "candidate_net_pnl"}]
    return {"average_abs_correlation": round(sum(vals) / len(vals), 6) if vals else 0.0, "max_abs_correlation": round(max(vals), 6) if vals else 0.0}


def make_phase17a_recommendation(result: dict[str, pd.DataFrame]) -> dict[str, Any]:
    c = result["candidate_results"]
    base = {"official_gates_changed": False, "paper_trading_approved": False, "live_trading_approved": False, "candidates_promoted": False, "rare_modules_default_scheduler_included": False}
    if c.empty:
        return {**base, "next_action": "phase17b_next_gap_or_manual_review", "rationale": "No Phase 17A candidates were produced."}
    paper = c[c["phase17a_label"].eq("phase17a_candidate_for_paper_review")]
    if not paper.empty:
        return {**base, "next_action": "phase17a_review_packet_only", "rationale": "A candidate reached review-packet diagnostics only; paper trading remains false.", "top_candidate": paper.iloc[0].to_dict()}
    rare_uncorr = c[c["phase17a_label"].eq("phase17a_rare_positive_research_signal")]
    if not rare_uncorr.empty:
        return {**base, "next_action": "rare_module_validation_track_review_phase17a", "rationale": "A positive uncorrelated Phase 17A signal was rare/research-only and excluded from default scheduler inclusion.", "top_candidate": rare_uncorr.iloc[0].to_dict()}
    uncorr_sched = c[c["phase17a_label"].eq("phase17a_positive_uncorrelated_research_signal") & c["default_scheduler_eligible"].astype(bool)]
    if not uncorr_sched.empty:
        return {**base, "next_action": "add_to_registry_and_run_portfolio_audit_f", "rationale": "A positive uncorrelated weak-fold axis was default-scheduler eligible under unchanged policy.", "top_candidate": uncorr_sched.iloc[0].to_dict()}
    if (c["fold_adequacy_status"].astype(str).eq("low_activity_not_fully_interpretable")).all():
        return {**base, "next_action": "rare_module_validation_track_review_phase17a", "rationale": "Fold adequacy is too sparse under standardized policy.", "top_candidate": c.iloc[0].to_dict()}
    narrow = c[(c["incremental_gap_days_covered"] > 0) & (c["stress_pnl"] > 0)]
    if not narrow.empty:
        return {**base, "next_action": "phase17b_targeted_weak_fold_module_diagnostic", "rationale": "A candidate improved gap coverage and narrowly missed at least one tradability gate.", "top_candidate": narrow.iloc[0].to_dict()}
    positive = c[(c["stress_pnl"] > 0) & (c["validation_pnl"] > 0) & (c["holdout_pnl"] > 0)]
    if not positive.empty:
        return {**base, "next_action": "add_to_registry_as_parked_weak_fold_signal", "rationale": "Positive weak-fold axes remained correlated, concentrated, rare, or unstable.", "top_candidate": positive.iloc[0].to_dict()}
    return {**base, "next_action": "phase17b_next_gap_or_manual_review", "rationale": "No positive specialized/uncorrelated weak-fold axis survived stress/validation/holdout diagnostics."}

def render_phase17a_report(result: dict[str, pd.DataFrame], recommendation: dict[str, Any], report_path: Path) -> str:
    c = result["candidate_results"]
    counts = c["phase17a_label"].value_counts().to_dict() if not c.empty else {}
    lines = ["# Phase 17A — Weak-Fold Regime Module Scout Without Rare Scheduler Inclusion", "", RESEARCH_ONLY_GUARDRAIL, "", "Bounded 48-spec MNQ-only weak-fold regime scout. Rare modules are registry-only/research-only by default and are not included as default active scheduler candidates. No MGC, no prior-RTH high/low breakout, no prior-RTH close/midpoint reaction, no Phase 15A trend/power continuation, no Phase 16A high-vol mixed late-resolution breakout, no overnight high/low/midpoint, no opening range fade, opening-drive first pullback, VWAP, or banned volatility-compression setup logic, no official gate changes, no promotions, and no paper trading approval.", "", "## Summary", "", f"- Specs evaluated: `{len(c)}`", f"- Trade rows: `{len(result['trade_logs'])}`", f"- Label counts: `{counts}`", f"- Next action: `{recommendation.get('next_action')}`", f"- Rationale: {recommendation.get('rationale')}", "- Paper trading approved: `false`", "", "## Top Candidates", "", "| Candidate | Label | Net | Stress | Val | Holdout | WF Stress | Avg reg corr | Avg playbook corr | Gap days | Incremental gap days | Fold adequacy | Reasons |", "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |"]
    for _, r in c.head(12).iterrows():
        lines.append(f"| `{r['candidate_id']}` | {r['phase17a_label']} | {float(r['net_pnl']):.2f} | {float(r['stress_pnl']):.2f} | {float(r['validation_pnl']):.2f} | {float(r['holdout_pnl']):.2f} | {float(r['walk_forward_stress_pnl']):.2f} | {float(r['average_correlation_to_registry']):.3f} | {float(r['average_correlation_to_playbook']):.3f} | {int(r['gap_days_covered'])} | {int(r['incremental_gap_days_covered'])} | {r['fold_adequacy_status']} | {r['reject_reasons']} |")
    lines += ["", "## Fold Views", "", "Required fold views reported: existing_project_folds, half_year_folds, rolling_6_month_test_folds, quarterly_folds. Alternative folds are diagnostic companions only; official gates unchanged.", "", "## Outputs", "", f"- `{report_path.as_posix()}`", "- `outputs/phase17a_candidate_results.csv`", "- `outputs/phase17a_trade_logs.csv`", "- `outputs/phase17a_gap_coverage_summary.csv`", "- `outputs/phase17a_fold_view_summary.csv`", "- `outputs/phase17a_module_fold_adequacy.csv`", "- `outputs/phase17a_next_action_recommendation.json`"]
    return "\n".join(lines) + "\n"


def _is_rare_module(r: dict[str, Any], c: Phase17AConfig) -> bool:
    return bool(r.get("trades", 0) < c.min_trades or r.get("active_days", 0) < c.min_active_days or r.get("fold_adequacy_status") == "low_activity_not_fully_interpretable")


def _default_scheduler_eligible(r: dict[str, Any], c: Phase17AConfig) -> bool:
    adequate = r.get("trades", 0) >= c.min_trades and r.get("active_days", 0) >= c.min_active_days
    return bool((not _is_rare_module(r, c)) and adequate and r.get("fold_adequacy_status") == "interpretable" and not bool(r.get("paper_trading_approved", False)))

def _label(r: dict[str, Any], c: Phase17AConfig) -> str:
    adequate = r.get("trades", 0) >= c.min_trades and r.get("active_days", 0) >= c.min_active_days and 1 <= r.get("trades_per_active_day", 0) <= 3
    econ = r.get("net_pnl", 0) > 0 and r.get("stress_pnl", 0) > 0 and r.get("validation_pnl", 0) > 0 and r.get("holdout_pnl", 0) > 0 and r.get("walk_forward_stress_pnl", 0) > 0
    fold_ok = r.get("positive_wf_test_folds_pct", 0) >= 0.9 and r.get("worst_wf_test_fold", 0) >= c.worst_fold_limit
    conc_ok = r.get("best_day_concentration", 1) <= c.concentration_limit and r.get("best_trade_concentration", 1) <= c.trade_concentration_limit
    corr_ok = r.get("average_correlation_to_registry", 1) <= c.registry_avg_corr_limit and r.get("max_correlation_to_registry", 1) <= c.registry_max_corr_limit
    if adequate and econ and fold_ok and conc_ok:
        return "phase17a_candidate_for_paper_review"
    if econ and corr_ok and _is_rare_module(r, c):
        return "phase17a_rare_positive_research_signal"
    if econ and corr_ok:
        return "phase17a_positive_uncorrelated_research_signal"
    if econ:
        return "phase17a_positive_specialized_research_signal"
    if r.get("stress_pnl", 0) > 0 and r.get("gap_days_covered", 0) > 0:
        return "phase17a_watchlist_needs_more_history"
    if r.get("net_pnl", 0) <= 0 or r.get("stress_pnl", 0) <= 0:
        return "phase17a_rejected_negative_stress"
    if r.get("validation_pnl", 0) <= 0:
        return "phase17a_rejected_negative_validation"
    if r.get("holdout_pnl", 0) <= 0:
        return "phase17a_rejected_negative_holdout"
    if not corr_ok:
        return "phase17a_rejected_high_correlation"
    if not adequate:
        return "phase17a_rejected_low_activity"
    if not fold_ok:
        return "phase17a_rejected_fold_instability"
    if not conc_ok:
        return "phase17a_rejected_concentration"
    return "phase17a_rejected_fold_instability"


def _signal_evidence(r: dict[str, Any]) -> str:
    label = str(r.get("phase17a_label"))
    if label in {"phase17a_candidate_for_paper_review", "phase17a_positive_uncorrelated_research_signal", "phase17a_positive_specialized_research_signal", "phase17a_rare_positive_research_signal"}:
        return "positive_research_signal"
    if label == "phase17a_watchlist_needs_more_history" or r.get("stress_pnl", 0) > 0:
        return "weak_research_signal"
    if r.get("net_pnl", 0) > 0:
        return "real_but_nontradable_signal"
    return "no_signal"


def _tradability(r: dict[str, Any], c: Phase17AConfig) -> str:
    label = str(r.get("phase17a_label"))
    if label == "phase17a_candidate_for_paper_review":
        return "review_packet_candidate"
    if label == "phase17a_watchlist_needs_more_history":
        return "watchlist_needs_more_history"
    if r.get("net_pnl", 0) <= 0 or r.get("stress_pnl", 0) <= 0:
        return "not_tradable_negative"
    if r.get("trades", 0) < c.min_trades or r.get("active_days", 0) < c.min_active_days:
        return "not_tradable_low_activity"
    if r.get("best_day_concentration", 1) > c.concentration_limit or r.get("best_trade_concentration", 1) > c.trade_concentration_limit:
        return "not_tradable_concentrated"
    return "not_tradable_fold_unstable"


def _research_track(r: dict[str, Any]) -> str:
    if bool(r.get("rare_module_track_enabled", False)):
        return "rare_setup_research_signal"
    if r.get("phase17a_label") in {"phase17a_candidate_for_paper_review", "phase17a_watchlist_needs_more_history", "phase17a_positive_uncorrelated_research_signal"}:
        return "priority_research_signal_for_more_data"
    if r.get("trades", 0) < 60:
        return "rare_setup_research_signal"
    return "parked_research_signal"


def _portfolio_role(r: dict[str, Any]) -> str:
    if r.get("phase17a_label") == "phase17a_positive_uncorrelated_research_signal":
        return "diversifier_module"
    if r.get("phase17a_label") == "phase17a_candidate_for_paper_review":
        return "candidate_for_more_data"
    if r.get("trades", 0) < 60:
        return "rare_setup_module"
    return "parked_module"


def _reasons(r: dict[str, Any], c: Phase17AConfig) -> str:
    checks = [("negative stress", r.get("net_pnl", 0) <= 0 or r.get("stress_pnl", 0) <= 0), ("negative validation", r.get("validation_pnl", 0) <= 0), ("negative holdout", r.get("holdout_pnl", 0) <= 0), ("high correlation", r.get("average_correlation_to_registry", 1) > c.registry_avg_corr_limit or r.get("max_correlation_to_registry", 1) > c.registry_max_corr_limit), ("low activity", r.get("trades", 0) < c.min_trades or r.get("active_days", 0) < c.min_active_days or not (1 <= r.get("trades_per_active_day", 0) <= 3)), ("fold instability", r.get("walk_forward_stress_pnl", 0) <= 0 or r.get("positive_wf_test_folds_pct", 0) < 0.9 or r.get("worst_wf_test_fold", 0) < c.worst_fold_limit), ("concentration", r.get("best_day_concentration", 1) > c.concentration_limit or r.get("best_trade_concentration", 1) > c.trade_concentration_limit), ("fold adequacy", r.get("fold_adequacy_status") != "interpretable")]
    return "; ".join(name for name, bad in checks if bad) or "survived Phase 17A diagnostic gates; review packet only"


def _fold_rows(trades: pd.DataFrame, spec: Phase17ASpec, sessions: list[str], c: Phase17AConfig) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    rows += _rolling_fold_rows(trades, spec, sessions, c.train_sessions + c.validation_sessions + c.test_sessions, c.train_sessions + c.validation_sessions, c.step_sessions, "existing_project_folds")
    rows += _block_fold_rows(trades, spec, sessions, 126, "half_year_folds")
    rows += _rolling_fold_rows(trades, spec, sessions, 126, 0, 63, "rolling_6_month_test_folds")
    rows += _block_fold_rows(trades, spec, sessions, 63, "quarterly_folds")
    return pd.DataFrame(rows)


def _rolling_fold_rows(trades: pd.DataFrame, spec: Phase17ASpec, sessions: list[str], window: int, test_offset: int, step: int, view: str) -> list[dict[str, Any]]:
    rows = []
    start = 0; fold = 1
    while start + window <= len(sessions):
        test = sessions[start + test_offset : start + window]
        seg = _trade_segment(trades, test)
        rows.append(_fold_row(spec, view, fold, test, seg))
        start += step; fold += 1
    if not rows and sessions:
        test = sessions[min(test_offset, len(sessions) - 1) :]
        seg = _trade_segment(trades, test)
        rows.append(_fold_row(spec, view, fold, test, seg))
    return rows


def _block_fold_rows(trades: pd.DataFrame, spec: Phase17ASpec, sessions: list[str], block: int, view: str) -> list[dict[str, Any]]:
    rows = []
    fold = 1
    for start in range(0, len(sessions), block):
        test = sessions[start : start + block]
        if not test:
            continue
        seg = _trade_segment(trades, test)
        rows.append(_fold_row(spec, view, fold, test, seg))
        fold += 1
    return rows


def _trade_segment(trades: pd.DataFrame, test_sessions: list[str]) -> pd.DataFrame:
    if trades.empty or "trading_session" not in trades:
        return pd.DataFrame(columns=list(trades.columns) if not trades.empty else ["trading_session", "net_pnl", "stress_pnl"])
    return trades[trades["trading_session"].astype(str).isin(test_sessions)]


def _fold_row(spec: Phase17ASpec, view: str, fold: int, test_sessions: list[str], seg: pd.DataFrame) -> dict[str, Any]:
    active_days = int(seg["trading_session"].nunique()) if not seg.empty else 0
    return {"candidate_id": spec.candidate_id, "module_family": spec.module_family, "side": spec.side, "regime_variant": spec.regime_variant, "confirmation_model": spec.confirmation_model, "exit_variant": spec.exit_variant, "fold_view": view, "fold": fold, "start_session": test_sessions[0], "end_session": test_sessions[-1], "net_pnl": round(float(seg["net_pnl"].sum()), 2) if not seg.empty else 0.0, "stress_pnl": round(float(seg["stress_pnl"].sum()), 2) if not seg.empty else 0.0, "trades": len(seg), "active_days": active_days}


def _fold_adequacy_rows(folds: pd.DataFrame, spec: Phase17ASpec, c: Phase17AConfig) -> pd.DataFrame:
    if folds.empty:
        return pd.DataFrame()
    out = folds.copy()
    out["min_active_days"] = c.module_fold_min_active_days
    out["min_trades"] = c.module_fold_min_trades
    out["below_min_activity"] = (out["active_days"] < c.module_fold_min_active_days) | (out["trades"] < c.module_fold_min_trades)
    out["fold_result_interpretable"] = ~out["below_min_activity"]
    return out[["candidate_id", "module_family", "side", "regime_variant", "fold_view", "fold", "active_days", "trades", "min_active_days", "min_trades", "below_min_activity", "fold_result_interpretable"]]


def _gap_session_sets(gap_features: pd.DataFrame, playbook_daily: pd.DataFrame, scheduler_daily: pd.DataFrame) -> dict[str, set[str]]:
    if gap_features.empty:
        return {k: set() for k in TARGET_GAP_FLAGS}
    gf = gap_features.copy()
    sessions = gf["trading_session"].astype(str)
    covered = _covered_sessions(playbook_daily) | _covered_sessions(scheduler_daily)
    high = gf.get("high_volatility_bucket", False).astype(bool) if "high_volatility_bucket" in gf else gf.get("volatility_bucket", "").astype(str).str.lower().eq("high")
    mixed = ~(gf.get("full_day_trend_proxy", False).astype(bool) if "full_day_trend_proxy" in gf else pd.Series(False, index=gf.index))
    power = gf.get("power_hour_expansion", False).astype(bool) if "power_hour_expansion" in gf else pd.Series(False, index=gf.index)
    weak_fold = gf.get("weak_fold_day", False).astype(bool) if "weak_fold_day" in gf else pd.Series(False, index=gf.index)
    if not weak_fold.any():
        weak_fold = high & mixed
    no_trade = gf.get("large_intraday_movement", False).astype(bool) if "large_intraday_movement" in gf else pd.Series(False, index=gf.index)
    return {
        "high_vol_mixed_power_expand_days": set(sessions[high & mixed & power]),
        "high_vol_mixed_no_power_expand_days": set(sessions[high & mixed & ~power]),
        "weak_fold_days": set(sessions[weak_fold]),
        "no_trade_large_intraday_movement_days": set(sessions[no_trade & ~sessions.isin(covered)]),
    }


def _gap_coverage_summary(candidates: pd.DataFrame) -> pd.DataFrame:
    if candidates.empty:
        return pd.DataFrame()
    cols = ["gap_days_covered", "incremental_gap_days_covered"] + [f"{g}_covered" for g in TARGET_GAP_FLAGS if f"{g}_covered" in candidates]
    return candidates.groupby(["module_family", "regime_variant", "side"], as_index=False).agg(candidates=("candidate_id", "count"), **{f"total_{col}": (col, "sum") for col in cols}, best_stress_pnl=("stress_pnl", "max"))


def _fold_view_summary(folds: pd.DataFrame) -> pd.DataFrame:
    if folds.empty:
        return pd.DataFrame()
    return folds.groupby("fold_view", as_index=False).agg(folds=("fold", "count"), total_trades=("trades", "sum"), total_active_days=("active_days", "sum"), total_net_pnl=("net_pnl", "sum"), total_stress_pnl=("stress_pnl", "sum"), positive_folds=("stress_pnl", lambda s: int((s > 0).sum())))


def _correlation_rows(candidates: pd.DataFrame, target: str) -> pd.DataFrame:
    avg = "average_correlation_to_registry" if target == "registry" else "average_correlation_to_playbook"
    mx = "max_correlation_to_registry" if target == "registry" else "max_correlation_to_playbook"
    return candidates[["candidate_id", "module_family", "regime_variant", "side", avg, mx]].copy() if not candidates.empty else pd.DataFrame(columns=["candidate_id", avg, mx])


def _combined_playbook_matrix(portfolio_daily: pd.DataFrame, scheduler_daily: pd.DataFrame) -> pd.DataFrame:
    pieces = []
    if not portfolio_daily.empty:
        pieces.append(_pivot_daily(portfolio_daily, [c for c in ["portfolio_set", "portfolio_mode"] if c in portfolio_daily.columns], "portfolio"))
    if not scheduler_daily.empty:
        pieces.append(_pivot_daily(scheduler_daily, [c for c in ["pruning_variant", "priority_policy", "portfolio_mode"] if c in scheduler_daily.columns], "scheduler"))
    if not pieces:
        return pd.DataFrame()
    matrix = pieces[0]
    for piece in pieces[1:]:
        matrix = matrix.merge(piece, on="trading_session", how="outer")
    return matrix.fillna(0.0)


def _pivot_daily(daily: pd.DataFrame, columns: list[str], prefix: str) -> pd.DataFrame:
    if daily.empty or "net_pnl" not in daily or "trading_session" not in daily:
        return pd.DataFrame()
    if not columns:
        return daily.groupby("trading_session", as_index=False)["net_pnl"].sum().rename(columns={"net_pnl": prefix})
    pivot = daily.pivot_table(index="trading_session", columns=columns, values="net_pnl", aggfunc="sum", fill_value=0.0).reset_index()
    pivot.columns = ["trading_session" if c == "trading_session" or (isinstance(c, tuple) and c[0] == "trading_session") else f"{prefix}::" + "::".join(map(str, c if isinstance(c, tuple) else (c,))) for c in pivot.columns]
    return pivot


def _covered_sessions(daily: pd.DataFrame) -> set[str]:
    if daily.empty or "trading_session" not in daily or "net_pnl" not in daily:
        return set()
    return set(daily[daily["net_pnl"].ne(0.0)]["trading_session"].astype(str))


def _config_with_policy(config: Phase17AConfig, policy: dict[str, Any]) -> Phase17AConfig:
    defaults = policy.get("fold_adequacy_defaults", {}) if isinstance(policy, dict) else {}
    return Phase17AConfig(**{**config.__dict__, "module_fold_min_active_days": int(defaults.get("module_fold_min_active_days", config.module_fold_min_active_days)), "module_fold_min_trades": int(defaults.get("module_fold_min_trades", config.module_fold_min_trades))})


def _zero_metrics() -> dict[str, Any]:
    metrics = standard_zero_metrics(include_gross_waterfall=False)
    metrics.update({"gross_pnl": 0.0, "walk_forward_test_pnl": 0.0, "avg_mfe": 0.0, "avg_mae": 0.0})
    return metrics


def _corr(a: pd.Series, b: pd.Series) -> float:
    if len(a) < 2 or float(a.std()) == 0.0 or float(b.std()) == 0.0:
        return 0.0
    value = a.corr(b)
    return 0.0 if pd.isna(value) else float(value)


def serialize_phase17a_specs(specs: list[Phase17ASpec]) -> str:
    return serialize_specs(specs)


def recommendation_to_json(rec: dict[str, Any]) -> str:
    return deterministic_json(rec)


def load_validation_policy(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def _between(df: pd.DataFrame, start: str, end: str) -> pd.DataFrame:
    minutes = _minutes(df["timestamp"])
    return df[(minutes >= _hhmm(start)) & (minutes < _hhmm(end))].copy()


def _prior_percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    return float(pd.Series(values, dtype="float64").quantile(q, interpolation="linear"))


def _direction(open_: float, close: float) -> str:
    if close > open_:
        return "up"
    if close < open_:
        return "down"
    return "flat"


def _hhmm(value: str) -> int:
    h, m = value.split(":")
    return int(h) * 60 + int(m)


def _minute(ts: Any) -> int:
    ts = pd.Timestamp(ts)
    return ts.hour * 60 + ts.minute


def _minutes(series: pd.Series) -> pd.Series:
    ts = pd.to_datetime(series)
    return ts.dt.hour * 60 + ts.dt.minute


def _float_or_none(value: Any) -> float | None:
    if value is None or pd.isna(value):
        return None
    return float(value)


def load_scheduler_policy(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def load_rare_module_policy(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
