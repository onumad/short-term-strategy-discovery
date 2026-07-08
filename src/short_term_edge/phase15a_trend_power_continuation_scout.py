from __future__ import annotations

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
MODULE_FAMILIES = ("trend_day_late_pullback_continuation", "power_hour_continuation", "low_volatility_late_expansion")
SIDES = ("long", "short")
TRIGGER_MODELS = {
    "trend_day_late_pullback_continuation": ("ema20_pullback_resume", "morning_midpoint_retest_resume"),
    "power_hour_continuation": ("power_range_breakout_continuation", "power_range_edge_retest_resume"),
    "low_volatility_late_expansion": ("lunch_expansion_breakout", "lunch_expansion_retest_resume"),
}
CONFIRMATION_MODELS = ("close_confirm_fill_next_open", "two_bar_confirm_fill_next_open")
EXIT_VARIANTS = ("hard_stop_time_exit", "structure_target_time_exit")

FAMILY_META = {
    "trend_day_late_pullback_continuation": {"build_start": "09:30", "build_end": "11:30", "trade_start": "13:00", "trade_end": "15:30"},
    "power_hour_continuation": {"build_start": "13:30", "build_end": "14:30", "trade_start": "14:30", "trade_end": "15:45"},
    "low_volatility_late_expansion": {"build_start": "11:30", "build_end": "13:30", "trade_start": "13:30", "trade_end": "15:30"},
}
TARGET_GAP_FLAGS = (
    "trend_days_with_no_module",
    "power_hour_expansion_days_with_no_module",
    "low_volatility_expansion_days_with_no_module",
    "no_trade_large_intraday_movement_days",
)


@dataclass(frozen=True)
class Phase15AConfig:
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
    registry_avg_corr_limit: float = 0.35
    registry_max_corr_limit: float = 0.60


@dataclass(frozen=True)
class Phase15ASpec:
    module_family: str
    side: str
    trigger_model: str
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
        return f"MNQ_15a_{self.module_family}_{self.side}_{self.trigger_model}_{self.confirmation_model}_{self.exit_variant}"

    def to_dict(self) -> dict[str, Any]:
        meta = FAMILY_META[self.module_family]
        return {
            "candidate_id": self.candidate_id,
            "instrument": "MNQ",
            "module_family": self.module_family,
            "side": self.side,
            "trigger_model": self.trigger_model,
            "confirmation_model": self.confirmation_model,
            "exit_variant": self.exit_variant,
            "timeframe": self.timeframe,
            "atr_cap_multiple": self.atr_cap_multiple,
            "buffer_ticks": self.buffer_ticks,
            "time_stop_minutes": self.time_stop_minutes,
            "max_trades_per_day": self.max_trades_per_day,
            "build_start": meta["build_start"],
            "build_end": meta["build_end"],
            "trade_start": meta["trade_start"],
            "trade_end": meta["trade_end"],
            "entry_rule": "later_bar_open",
            "paper_trading_approved": False,
        }


def build_phase15a_specs(config: Phase15AConfig = Phase15AConfig()) -> list[Phase15ASpec]:
    specs: list[Phase15ASpec] = []
    for family in MODULE_FAMILIES:
        for side in SIDES:
            for trigger in TRIGGER_MODELS[family]:
                for confirm in CONFIRMATION_MODELS:
                    for exit_variant in EXIT_VARIANTS:
                        specs.append(Phase15ASpec(family, side, trigger, confirm, exit_variant))
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
    out["ema20"] = out.groupby("trading_session")["close"].transform(lambda s: s.ewm(span=20, adjust=False, min_periods=3).mean())
    return out


def compute_phase15a_frozen_levels(bars5: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    lunch_ranges: list[float] = []
    for session, day in bars5.groupby("trading_session", sort=True):
        day = day.sort_values("timestamp")
        morning = _between(day, "09:30", "11:30")
        power = _between(day, "13:30", "14:30")
        context = _between(day, "09:30", "14:30")
        lunch = _between(day, "11:30", "13:30")
        row: dict[str, Any] = {"trading_session": session}
        if not morning.empty:
            mh = float(morning["high"].max()); ml = float(morning["low"].min())
            mo = float(morning.iloc[0]["open"]); mc = float(morning.iloc[-1]["close"]); mr = mh - ml
            row.update({"morning_high": mh, "morning_low": ml, "morning_midpoint": (mh + ml) / 2.0, "morning_open": mo, "morning_close": mc, "morning_range": mr, "morning_close_position": safe_divide(mc - ml, mr), "morning_build_bar_count": len(morning)})
        if not power.empty:
            ph = float(power["high"].max()); pl = float(power["low"].min())
            row.update({"power_range_high": ph, "power_range_low": pl, "power_range_midpoint": (ph + pl) / 2.0, "power_range_width": ph - pl, "power_build_bar_count": len(power)})
        if not context.empty:
            ch = float(context["high"].max()); cl = float(context["low"].min()); cr = ch - cl
            copen = float(context.iloc[0]["open"]); cclose = float(context.iloc[-1]["close"])
            row.update({"context_0930_1430_open": copen, "context_1430_close": cclose, "context_0930_1430_close_position": safe_divide(cclose - cl, cr)})
        if not lunch.empty:
            lh = float(lunch["high"].max()); ll = float(lunch["low"].min()); lr = lh - ll
            threshold = _prior_percentile(lunch_ranges, 0.40)
            row.update({"lunch_high": lh, "lunch_low": ll, "lunch_midpoint": (lh + ll) / 2.0, "lunch_range": lr, "lunch_low_vol_threshold": threshold, "lunch_low_vol_qualified": bool(threshold is not None and lr <= threshold), "lunch_prior_sessions_used": len(lunch_ranges), "lunch_build_bar_count": len(lunch)})
            lunch_ranges.append(lr)
        else:
            row.update({"lunch_low_vol_threshold": None, "lunch_low_vol_qualified": False, "lunch_prior_sessions_used": len(lunch_ranges)})
        rows.append(row)
    return pd.DataFrame(rows)


def build_phase15a_feature_bars(bars: pd.DataFrame, spec: Phase15ASpec) -> pd.DataFrame:
    bars5 = resample_rth_5m(bars)
    if bars5.empty:
        return pd.DataFrame()
    levels = compute_phase15a_frozen_levels(bars5)
    out = bars5.merge(levels, on="trading_session", how="left")
    return out.sort_values(["trading_session", "timestamp"]).reset_index(drop=True)


def generate_phase15a_signals(features: pd.DataFrame, spec: Phase15ASpec) -> list[dict[str, Any]]:
    if features.empty:
        return []
    meta = FAMILY_META[spec.module_family]
    start = _hhmm(str(meta["trade_start"])); end = _hhmm(str(meta["trade_end"]))
    tick = get_instrument("MNQ").tick_size
    signals: list[dict[str, Any]] = []
    for _, day in features.groupby("trading_session", sort=True):
        day = day.sort_values("timestamp").reset_index(drop=True)
        candidates: list[dict[str, Any]] = []
        breakout_seen = False
        for i in range(len(day) - 2):
            row = day.iloc[i]
            minute = _minute(row["timestamp"])
            if minute < start or minute >= end:
                continue
            ok = False
            trigger_level = None
            if spec.module_family == "trend_day_late_pullback_continuation":
                if pd.isna(row.get("morning_range")) or float(row.get("morning_range", 0.0)) <= 0:
                    continue
                mopen = float(row["morning_open"]); mclose = float(row["morning_close"]); mpos = float(row["morning_close_position"]); mid = float(row["morning_midpoint"])
                if spec.side == "long" and not (mclose > mopen and mpos >= 0.70):
                    continue
                if spec.side == "short" and not (mclose < mopen and mpos <= 0.30):
                    continue
                if spec.trigger_model == "ema20_pullback_resume":
                    ema = float(row["ema20"])
                    ok = (float(row["low"]) <= ema and float(row["close"]) > ema and float(row["close"]) > mid) if spec.side == "long" else (float(row["high"]) >= ema and float(row["close"]) < ema and float(row["close"]) < mid)
                    trigger_level = ema
                else:
                    ok = (float(row["low"]) <= mid + tick and float(row["close"]) > mid) if spec.side == "long" else (float(row["high"]) >= mid - tick and float(row["close"]) < mid)
                    trigger_level = mid
            elif spec.module_family == "power_hour_continuation":
                if pd.isna(row.get("power_range_high")) or pd.isna(row.get("context_0930_1430_open")):
                    continue
                ph = float(row["power_range_high"]); pl = float(row["power_range_low"])
                copen = float(row["context_0930_1430_open"]); cclose = float(row["context_1430_close"]); cpos = float(row["context_0930_1430_close_position"])
                context_ok = (cclose > copen and cpos >= 0.60) if spec.side == "long" else (cclose < copen and cpos <= 0.40)
                if not context_ok:
                    continue
                if spec.trigger_model == "power_range_breakout_continuation":
                    ok = float(row["close"]) > ph if spec.side == "long" else float(row["close"]) < pl
                    trigger_level = ph if spec.side == "long" else pl
                else:
                    breakout_seen = breakout_seen or (float(row["close"]) > ph if spec.side == "long" else float(row["close"]) < pl)
                    ok = breakout_seen and ((float(row["low"]) <= ph + tick and float(row["close"]) > ph) if spec.side == "long" else (float(row["high"]) >= pl - tick and float(row["close"]) < pl))
                    trigger_level = ph if spec.side == "long" else pl
            else:
                if not bool(row.get("lunch_low_vol_qualified", False)) or pd.isna(row.get("lunch_high")):
                    continue
                lh = float(row["lunch_high"]); ll = float(row["lunch_low"])
                if spec.trigger_model == "lunch_expansion_breakout":
                    ok = float(row["close"]) > lh if spec.side == "long" else float(row["close"]) < ll
                    trigger_level = lh if spec.side == "long" else ll
                else:
                    breakout_seen = breakout_seen or (float(row["close"]) > lh if spec.side == "long" else float(row["close"]) < ll)
                    ok = breakout_seen and ((float(row["low"]) <= lh + tick and float(row["close"]) > lh) if spec.side == "long" else (float(row["high"]) >= ll - tick and float(row["close"]) < ll))
                    trigger_level = lh if spec.side == "long" else ll
            if not ok:
                continue
            confirmation_time = row["timestamp"]
            signal_row = row
            entry_idx = i + 1
            if spec.confirmation_model == "two_bar_confirm_fill_next_open":
                confirm = day.iloc[i + 1]
                confirm_ok = _confirm_bar_ok(confirm, spec, float(trigger_level))
                if not confirm_ok:
                    continue
                confirmation_time = confirm["timestamp"]
                signal_row = confirm
                entry_idx = i + 2
            if entry_idx >= len(day):
                continue
            entry = day.iloc[entry_idx]
            entry_minute = _minute(entry["timestamp"])
            if entry_minute < start or entry_minute >= end or entry_minute >= _hhmm(spec.flatten_time):
                continue
            candidates.append(_signal_dict(spec, row, signal_row, entry, confirmation_time, float(trigger_level)))
        if candidates:
            first = dict(candidates[0])
            first["skipped_extra_signals_same_day"] = len(candidates) - 1
            signals.append(first)
    return signals


def _confirm_bar_ok(row: pd.Series, spec: Phase15ASpec, trigger_level: float) -> bool:
    close = float(row["close"])
    if spec.side == "long":
        if spec.trigger_model == "ema20_pullback_resume":
            return close > float(row["ema20"]) and close > float(row["morning_midpoint"])
        return close > trigger_level
    if spec.trigger_model == "ema20_pullback_resume":
        return close < float(row["ema20"]) and close < float(row["morning_midpoint"])
    return close < trigger_level


def _signal_dict(spec: Phase15ASpec, trigger_row: pd.Series, signal_row: pd.Series, entry: pd.Series, confirmation_time: Any, trigger_level: float) -> dict[str, Any]:
    return {
        "candidate_id": spec.candidate_id,
        "signal_time": trigger_row["timestamp"],
        "confirmation_time": confirmation_time,
        "entry_time": entry["timestamp"],
        "trading_session": str(trigger_row["trading_session"]),
        "module_family": spec.module_family,
        "side": spec.side,
        "trigger_model": spec.trigger_model,
        "confirmation_model": spec.confirmation_model,
        "exit_variant": spec.exit_variant,
        "trigger_level": trigger_level,
        "signal_open": float(signal_row["open"]),
        "signal_high": float(signal_row["high"]),
        "signal_low": float(signal_row["low"]),
        "signal_close": float(signal_row["close"]),
        "atr": float(signal_row.get("atr", 0.0) or 0.0),
        "morning_high": _float_or_none(signal_row.get("morning_high")),
        "morning_low": _float_or_none(signal_row.get("morning_low")),
        "morning_midpoint": _float_or_none(signal_row.get("morning_midpoint")),
        "morning_range": _float_or_none(signal_row.get("morning_range")),
        "power_range_high": _float_or_none(signal_row.get("power_range_high")),
        "power_range_low": _float_or_none(signal_row.get("power_range_low")),
        "power_range_midpoint": _float_or_none(signal_row.get("power_range_midpoint")),
        "power_range_width": _float_or_none(signal_row.get("power_range_width")),
        "lunch_high": _float_or_none(signal_row.get("lunch_high")),
        "lunch_low": _float_or_none(signal_row.get("lunch_low")),
        "lunch_midpoint": _float_or_none(signal_row.get("lunch_midpoint")),
        "lunch_range": _float_or_none(signal_row.get("lunch_range")),
        "lunch_low_vol_threshold": _float_or_none(signal_row.get("lunch_low_vol_threshold")),
        "lunch_prior_sessions_used": int(signal_row.get("lunch_prior_sessions_used", 0) or 0),
    }


def simulate_phase15a_trades(features: pd.DataFrame, signals: list[dict[str, Any]], spec: Phase15ASpec) -> tuple[pd.DataFrame, int]:
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


def _simulate_one(day: pd.DataFrame, entry_pos: int, signal: dict[str, Any], spec: Phase15ASpec, inst) -> dict[str, Any] | None:
    entry = day.iloc[entry_pos]
    entry_price = float(entry["open"])
    tick = inst.tick_size
    atr = max(float(signal.get("atr", 0.0)), tick * 8)
    risk_cap = atr * spec.atr_cap_multiple
    if spec.side == "long":
        structural_stop = float(signal["signal_low"]) - tick
        atr_cap_stop = entry_price - risk_cap
        actual_stop = max(structural_stop, atr_cap_stop)
        if actual_stop >= entry_price:
            return None
        risk = entry_price - actual_stop
        target = entry_price + 1.5 * risk
    else:
        structural_stop = float(signal["signal_high"]) + tick
        atr_cap_stop = entry_price + risk_cap
        actual_stop = min(structural_stop, atr_cap_stop)
        if actual_stop <= entry_price:
            return None
        risk = actual_stop - entry_price
        target = entry_price - 1.5 * risk
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


def run_phase15a_scout(bars: pd.DataFrame, registry_matrix: pd.DataFrame, playbook_daily: pd.DataFrame, gap_features: pd.DataFrame, config: Phase15AConfig = Phase15AConfig()) -> dict[str, pd.DataFrame]:
    specs = build_phase15a_specs(config)
    scoped = bars[~bars["trading_session"].astype(str).isin(PARTIAL_SESSIONS)].copy()
    sessions = sorted(scoped["trading_session"].dropna().astype(str).unique().tolist())
    split_map = split_sessions(sessions)
    features = build_phase15a_feature_bars(scoped, specs[0]) if specs else pd.DataFrame()
    gap_sets = _gap_session_sets(gap_features, playbook_daily)
    current_covered = set(playbook_daily[playbook_daily["net_pnl"].ne(0.0)]["trading_session"].astype(str)) if not playbook_daily.empty and "net_pnl" in playbook_daily else set()
    rows: list[dict[str, Any]] = []
    trade_frames: list[pd.DataFrame] = []
    fold_frames: list[pd.DataFrame] = []
    for spec in specs:
        signals = generate_phase15a_signals(features, spec)
        trades, invalid = simulate_phase15a_trades(features, signals, spec)
        if not trades.empty:
            trades["split"] = trades["trading_session"].astype(str).map(split_map)
            trade_frames.append(trades)
            fold_frames.append(_fold_rows(trades, spec, sessions, config))
        rows.append(_candidate_row(spec, trades, invalid, signals, sessions, split_map, registry_matrix, playbook_daily, gap_sets, current_covered, config))
    trade_logs = pd.concat(trade_frames, ignore_index=True) if trade_frames else pd.DataFrame()
    folds = pd.concat(fold_frames, ignore_index=True) if fold_frames else pd.DataFrame()
    candidates = pd.DataFrame(rows).sort_values(["phase15a_score", "stress_pnl"], ascending=[False, False]).reset_index(drop=True)
    candidates.insert(0, "phase15a_rank", range(1, len(candidates) + 1))
    return {
        "candidate_results": candidates,
        "trade_logs": trade_logs,
        "daily_pnl": daily_pnl_summary(trade_logs),
        "walk_forward_folds": folds,
        "concentration_diagnostics": concentration_diagnostics(trade_logs),
        "family_summary": grouped_trade_summary(trade_logs, "module_family", include_gross=True),
        "side_summary": grouped_trade_summary(trade_logs, "side", include_gross=True),
        "trigger_model_summary": grouped_trade_summary(trade_logs, "trigger_model", include_gross=True),
        "confirmation_summary": grouped_trade_summary(trade_logs, "confirmation_model", include_gross=True),
        "exit_variant_summary": grouped_trade_summary(trade_logs, "exit_variant", include_gross=True),
        "correlation_to_registry": _correlation_rows(candidates, "registry"),
        "correlation_to_playbook": _correlation_rows(candidates, "playbook"),
        "gap_coverage_summary": _gap_coverage_summary(candidates),
        "specs": pd.DataFrame([s.to_dict() for s in specs]),
    }


def _candidate_row(spec: Phase15ASpec, trades: pd.DataFrame, invalid: int, signals: list[dict[str, Any]], sessions: list[str], split_map: dict[Any, str], registry_matrix: pd.DataFrame, playbook_daily: pd.DataFrame, gap_sets: dict[str, set[str]], current_covered: set[str], config: Phase15AConfig) -> dict[str, Any]:
    row = spec.to_dict()
    daily = pd.DataFrame(columns=["trading_session", "net_pnl"])
    if trades.empty:
        row.update(_zero_metrics())
    else:
        t = trades.copy(); t["split"] = t["trading_session"].astype(str).map(split_map)
        net = float(t["net_pnl"].sum()); equity = t["net_pnl"].cumsum()
        daily = t.groupby("trading_session", as_index=False)["net_pnl"].sum(); daily_series = daily.set_index("trading_session")["net_pnl"]
        folds = _fold_rows(t, spec, sessions, config)
        row.update({"trades": len(t), "active_days": int(t["trading_session"].nunique()), "trades_per_active_day": safe_divide(len(t), t["trading_session"].nunique()), "gross_pnl": round(float(t["gross_pnl"].sum()), 2), "net_pnl": round(net, 2), "stress_pnl": round(float(t["stress_pnl"].sum()), 2), "validation_pnl": round(float(t.loc[t["split"].eq("validation"), "net_pnl"].sum()), 2), "holdout_pnl": round(float(t.loc[t["split"].eq("holdout"), "net_pnl"].sum()), 2), "max_drawdown": round(float((equity - equity.cummax()).min()), 2), "best_day_concentration": positive_concentration(float(daily_series.max()), net), "best_trade_concentration": positive_concentration(float(t["net_pnl"].max()), net), "avg_mfe": round(float(t["mfe"].mean()), 2), "avg_mae": round(float(t["mae"].mean()), 2), **fold_summary(folds)})
    reg = daily_correlation_to_matrix(daily, registry_matrix)
    play = daily_correlation_to_matrix(daily, _playbook_matrix(playbook_daily))
    trade_sessions = set(trades["trading_session"].astype(str)) if not trades.empty else set()
    target_gap = gap_sets.get(_family_gap_key(spec.module_family), set())
    any_gap = set().union(*gap_sets.values()) if gap_sets else set()
    row.update({"average_correlation_to_registry": reg["average_abs_correlation"], "max_correlation_to_registry": reg["max_abs_correlation"], "average_correlation_to_playbook": play["average_abs_correlation"], "max_correlation_to_playbook": play["max_abs_correlation"], "gap_days_covered": len(trade_sessions & target_gap), "incremental_gap_days_covered": len((trade_sessions & target_gap) - current_covered), "any_target_gap_days_covered": len(trade_sessions & any_gap), "invalid_risk_skipped_count": int(invalid), "signals_found": len(signals), "paper_trading_approved": False, "official_gates_passed": False})
    for gap_name, sessions_set in gap_sets.items():
        row[f"{gap_name}_covered"] = len(trade_sessions & sessions_set)
    row["phase15a_label"] = _label(row, config)
    row["signal_evidence_status"] = _signal_evidence(row)
    row["tradability_status"] = _tradability(row, config)
    row["research_track"] = _research_track(row)
    row["portfolio_role"] = _portfolio_role(row)
    row["reject_reasons"] = _reasons(row, config)
    row["phase15a_score"] = round(float(row.get("stress_pnl", 0)) + float(row.get("walk_forward_stress_pnl", 0)) + 25 * float(row.get("incremental_gap_days_covered", 0)) - abs(float(row.get("max_drawdown", 0))) - 1000 * max(float(row.get("average_correlation_to_registry", 1)) - config.registry_avg_corr_limit, 0), 4)
    return row


def daily_correlation_to_matrix(candidate_daily: pd.DataFrame, matrix: pd.DataFrame) -> dict[str, float]:
    if candidate_daily.empty or matrix.empty:
        return {"average_abs_correlation": 0.0, "max_abs_correlation": 0.0}
    base = matrix.copy()
    cand = candidate_daily.groupby("trading_session", as_index=False)["net_pnl"].sum().rename(columns={"net_pnl": "candidate_net_pnl"})
    merged = base.merge(cand, on="trading_session", how="outer").fillna(0.0)
    vals = [abs(_corr(merged["candidate_net_pnl"], merged[col])) for col in merged.columns if col not in {"trading_session", "candidate_net_pnl"}]
    return {"average_abs_correlation": round(sum(vals) / len(vals), 6) if vals else 0.0, "max_abs_correlation": round(max(vals), 6) if vals else 0.0}


def make_phase15a_recommendation(result: dict[str, pd.DataFrame]) -> dict[str, Any]:
    c = result["candidate_results"]
    if c.empty:
        return {"next_action": "phase15b_target_next_gap_or_scheduler_overlap_audit", "official_gates_changed": False, "paper_trading_approved": False, "rationale": "No Phase 15A candidates were produced."}
    paper = c[c["phase15a_label"].eq("phase15a_candidate_for_paper_review")]
    if not paper.empty:
        return {"next_action": "phase15a_review_packet_only", "official_gates_changed": False, "paper_trading_approved": False, "rationale": "A candidate reached review-packet diagnostics only; paper trading remains false.", "top_candidate": paper.iloc[0].to_dict()}
    uncorr = c[c["phase15a_label"].eq("phase15a_positive_uncorrelated_research_signal")]
    if not uncorr.empty:
        return {"next_action": "add_to_registry_and_run_portfolio_audit_d", "official_gates_changed": False, "paper_trading_approved": False, "rationale": "A positive trend/power continuation axis was uncorrelated to existing registry/playbook diagnostics.", "top_candidate": uncorr.iloc[0].to_dict()}
    near = c[(c["gap_days_covered"] > 0) & (c["stress_pnl"] > 0)]
    if not near.empty:
        return {"next_action": "phase15b_targeted_trend_power_diagnostic", "official_gates_changed": False, "paper_trading_approved": False, "rationale": "At least one candidate improved target gap coverage but missed tradability gates.", "top_candidate": near.iloc[0].to_dict()}
    positive = c[(c["stress_pnl"] > 0) & (c["validation_pnl"] > 0) & (c["holdout_pnl"] > 0)]
    if not positive.empty:
        return {"next_action": "add_to_registry_as_parked_trend_power_signal", "official_gates_changed": False, "paper_trading_approved": False, "rationale": "Positive axes remained correlated, concentrated, or unstable.", "top_candidate": positive.iloc[0].to_dict()}
    return {"next_action": "phase15b_target_next_gap_or_scheduler_overlap_audit", "official_gates_changed": False, "paper_trading_approved": False, "rationale": "No positive specialized/uncorrelated trend-power continuation axis survived diagnostics."}


def render_phase15a_report(result: dict[str, pd.DataFrame], recommendation: dict[str, Any], report_path: Path) -> str:
    c = result["candidate_results"]
    counts = c["phase15a_label"].value_counts().to_dict() if not c.empty else {}
    lines = ["# Phase 15A — Trend Day / Power Hour Continuation Scout", "", RESEARCH_ONLY_GUARDRAIL, "", "Bounded 48-spec MNQ-only late-session continuation scout. No MGC, no prior-RTH high/low breakout, no prior-RTH close/midpoint reaction, no overnight levels, no opening range/opening-drive/VWAP/compression logic, no gate changes, no promotions, and no paper trading approval.", "", "## Summary", "", f"- Specs evaluated: `{len(c)}`", f"- Trade rows: `{len(result['trade_logs'])}`", f"- Label counts: `{counts}`", f"- Next action: `{recommendation.get('next_action')}`", f"- Rationale: {recommendation.get('rationale')}", "- Paper trading approved: `false`", "", "## Top Candidates", "", "| Candidate | Label | Net | Stress | Val | Holdout | WF Stress | Avg reg corr | Avg playbook corr | Gap days | Incremental gap days | Reasons |", "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |"]
    for _, r in c.head(12).iterrows():
        lines.append(f"| `{r['candidate_id']}` | {r['phase15a_label']} | {float(r['net_pnl']):.2f} | {float(r['stress_pnl']):.2f} | {float(r['validation_pnl']):.2f} | {float(r['holdout_pnl']):.2f} | {float(r['walk_forward_stress_pnl']):.2f} | {float(r['average_correlation_to_registry']):.3f} | {float(r['average_correlation_to_playbook']):.3f} | {int(r['gap_days_covered'])} | {int(r['incremental_gap_days_covered'])} | {r['reject_reasons']} |")
    lines += ["", "## Outputs", "", f"- `{report_path.as_posix()}`", "- `outputs/phase15a_candidate_results.csv`", "- `outputs/phase15a_trade_logs.csv`", "- `outputs/phase15a_gap_coverage_summary.csv`", "- `outputs/phase15a_next_action_recommendation.json`"]
    return "\n".join(lines) + "\n"


def _label(r: dict[str, Any], c: Phase15AConfig) -> str:
    adequate = r.get("trades", 0) >= c.min_trades and r.get("active_days", 0) >= c.min_active_days and 1 <= r.get("trades_per_active_day", 0) <= 3
    econ = r.get("net_pnl", 0) > 0 and r.get("stress_pnl", 0) > 0 and r.get("validation_pnl", 0) > 0 and r.get("holdout_pnl", 0) > 0 and r.get("walk_forward_stress_pnl", 0) > 0
    fold_ok = r.get("positive_wf_test_folds_pct", 0) >= 0.9 and r.get("worst_wf_test_fold", 0) >= c.worst_fold_limit
    conc_ok = r.get("best_day_concentration", 1) <= c.concentration_limit and r.get("best_trade_concentration", 1) <= c.trade_concentration_limit
    corr_ok = r.get("average_correlation_to_registry", 1) <= c.registry_avg_corr_limit and r.get("max_correlation_to_registry", 1) <= c.registry_max_corr_limit
    if adequate and econ and fold_ok and conc_ok:
        return "phase15a_candidate_for_paper_review"
    if econ and corr_ok:
        return "phase15a_positive_uncorrelated_research_signal"
    if econ:
        return "phase15a_positive_specialized_research_signal"
    if r.get("stress_pnl", 0) > 0 and r.get("gap_days_covered", 0) > 0:
        return "phase15a_watchlist_needs_more_history"
    if r.get("net_pnl", 0) <= 0 or r.get("stress_pnl", 0) <= 0:
        return "phase15a_rejected_negative_stress"
    if r.get("validation_pnl", 0) <= 0:
        return "phase15a_rejected_negative_validation"
    if r.get("holdout_pnl", 0) <= 0:
        return "phase15a_rejected_negative_holdout"
    if not corr_ok:
        return "phase15a_rejected_high_correlation"
    if not adequate:
        return "phase15a_rejected_low_activity"
    if not fold_ok:
        return "phase15a_rejected_fold_instability"
    if not conc_ok:
        return "phase15a_rejected_concentration"
    return "phase15a_rejected_fold_instability"


def _signal_evidence(r: dict[str, Any]) -> str:
    label = str(r.get("phase15a_label"))
    if label in {"phase15a_candidate_for_paper_review", "phase15a_positive_uncorrelated_research_signal", "phase15a_positive_specialized_research_signal"}:
        return "positive_research_signal"
    if label == "phase15a_watchlist_needs_more_history" or r.get("stress_pnl", 0) > 0:
        return "weak_research_signal"
    if r.get("net_pnl", 0) > 0:
        return "real_but_nontradable_signal"
    return "no_signal"


def _tradability(r: dict[str, Any], c: Phase15AConfig) -> str:
    label = str(r.get("phase15a_label"))
    if label == "phase15a_candidate_for_paper_review":
        return "review_packet_candidate"
    if label == "phase15a_watchlist_needs_more_history":
        return "watchlist_needs_more_history"
    if r.get("net_pnl", 0) <= 0 or r.get("stress_pnl", 0) <= 0:
        return "not_tradable_negative"
    if r.get("trades", 0) < c.min_trades or r.get("active_days", 0) < c.min_active_days:
        return "not_tradable_low_activity"
    if r.get("best_day_concentration", 1) > c.concentration_limit or r.get("best_trade_concentration", 1) > c.trade_concentration_limit:
        return "not_tradable_concentrated"
    return "not_tradable_fold_unstable"


def _research_track(r: dict[str, Any]) -> str:
    if r.get("phase15a_label") in {"phase15a_candidate_for_paper_review", "phase15a_watchlist_needs_more_history"}:
        return "priority_research_signal_for_more_data"
    if r.get("trades", 0) < 60:
        return "rare_setup_research_signal"
    return "parked_research_signal"


def _portfolio_role(r: dict[str, Any]) -> str:
    if r.get("phase15a_label") == "phase15a_positive_uncorrelated_research_signal":
        return "diversifier_module"
    if r.get("phase15a_label") == "phase15a_candidate_for_paper_review":
        return "candidate_for_more_data"
    if r.get("trades", 0) < 60:
        return "rare_setup_module"
    return "parked_module"


def _reasons(r: dict[str, Any], c: Phase15AConfig) -> str:
    checks = [("negative stress", r.get("net_pnl", 0) <= 0 or r.get("stress_pnl", 0) <= 0), ("negative validation", r.get("validation_pnl", 0) <= 0), ("negative holdout", r.get("holdout_pnl", 0) <= 0), ("high correlation", r.get("average_correlation_to_registry", 1) > c.registry_avg_corr_limit or r.get("max_correlation_to_registry", 1) > c.registry_max_corr_limit), ("low activity", r.get("trades", 0) < c.min_trades or r.get("active_days", 0) < c.min_active_days or not (1 <= r.get("trades_per_active_day", 0) <= 3)), ("fold instability", r.get("walk_forward_stress_pnl", 0) <= 0 or r.get("positive_wf_test_folds_pct", 0) < 0.9 or r.get("worst_wf_test_fold", 0) < c.worst_fold_limit), ("concentration", r.get("best_day_concentration", 1) > c.concentration_limit or r.get("best_trade_concentration", 1) > c.trade_concentration_limit)]
    return "; ".join(name for name, bad in checks if bad) or "survived Phase 15A diagnostic gates; review packet only"


def _fold_rows(trades: pd.DataFrame, spec: Phase15ASpec, sessions: list[str], c: Phase15AConfig) -> pd.DataFrame:
    rows = []
    window = c.train_sessions + c.validation_sessions + c.test_sessions
    start = 0; fold = 1
    while start + window <= len(sessions):
        test = sessions[start + c.train_sessions + c.validation_sessions : start + window]
        seg = trades[trades["trading_session"].astype(str).isin(test)]
        rows.append({"candidate_id": spec.candidate_id, "fold": fold, "net_pnl": round(float(seg["net_pnl"].sum()), 2), "stress_pnl": round(float(seg["stress_pnl"].sum()), 2), "trades": len(seg)})
        start += c.step_sessions; fold += 1
    return pd.DataFrame(rows)


def _gap_session_sets(gap_features: pd.DataFrame, playbook_daily: pd.DataFrame) -> dict[str, set[str]]:
    if gap_features.empty:
        return {k: set() for k in TARGET_GAP_FLAGS}
    gf = gap_features.copy()
    covered = set(playbook_daily[playbook_daily["net_pnl"].ne(0.0)]["trading_session"].astype(str)) if not playbook_daily.empty and "net_pnl" in playbook_daily else set()
    sessions = gf["trading_session"].astype(str)
    out: dict[str, set[str]] = {}
    out["trend_days_with_no_module"] = set(sessions[gf.get("rth_trend_day_proxy", False).astype(bool) & ~sessions.isin(covered)])
    out["power_hour_expansion_days_with_no_module"] = set(sessions[gf.get("power_hour_expansion", False).astype(bool) & ~sessions.isin(covered)])
    low_flag = gf.get("lunch_range_expansion", False).astype(bool) if "lunch_range_expansion" in gf else pd.Series(False, index=gf.index)
    if "volatility_bucket" in gf:
        low_flag = low_flag & gf["volatility_bucket"].astype(str).str.lower().eq("low")
    out["low_volatility_expansion_days_with_no_module"] = set(sessions[low_flag & ~sessions.isin(covered)])
    out["no_trade_large_intraday_movement_days"] = set(sessions[gf.get("large_intraday_movement", False).astype(bool) & ~sessions.isin(covered)])
    return out


def _family_gap_key(family: str) -> str:
    return {"trend_day_late_pullback_continuation": "trend_days_with_no_module", "power_hour_continuation": "power_hour_expansion_days_with_no_module", "low_volatility_late_expansion": "low_volatility_expansion_days_with_no_module"}[family]


def _gap_coverage_summary(candidates: pd.DataFrame) -> pd.DataFrame:
    if candidates.empty:
        return pd.DataFrame()
    cols = ["gap_days_covered", "incremental_gap_days_covered", "any_target_gap_days_covered"] + [f"{g}_covered" for g in TARGET_GAP_FLAGS if f"{g}_covered" in candidates]
    return candidates.groupby(["module_family", "trigger_model", "side"], as_index=False).agg(candidates=("candidate_id", "count"), **{f"total_{c}": (c, "sum") for c in cols}, best_stress_pnl=("stress_pnl", "max"))


def _correlation_rows(candidates: pd.DataFrame, target: str) -> pd.DataFrame:
    avg = "average_correlation_to_registry" if target == "registry" else "average_correlation_to_playbook"
    mx = "max_correlation_to_registry" if target == "registry" else "max_correlation_to_playbook"
    return candidates[["candidate_id", "module_family", "trigger_model", "side", avg, mx]].copy() if not candidates.empty else pd.DataFrame(columns=["candidate_id", avg, mx])


def _playbook_matrix(portfolio_daily: pd.DataFrame) -> pd.DataFrame:
    if portfolio_daily.empty:
        return pd.DataFrame()
    if {"portfolio_set", "portfolio_mode", "net_pnl"} <= set(portfolio_daily.columns):
        pivot = portfolio_daily.pivot_table(index="trading_session", columns=["portfolio_set", "portfolio_mode"], values="net_pnl", aggfunc="sum", fill_value=0.0).reset_index()
        pivot.columns = ["trading_session" if c == ("trading_session", "") or c == "trading_session" else "::".join(map(str, c)) for c in pivot.columns]
        return pivot
    return portfolio_daily


def _zero_metrics() -> dict[str, Any]:
    metrics = standard_zero_metrics(include_gross_waterfall=False)
    metrics.update({"gross_pnl": 0.0, "walk_forward_test_pnl": 0.0, "avg_mfe": 0.0, "avg_mae": 0.0})
    return metrics


def _corr(a: pd.Series, b: pd.Series) -> float:
    if len(a) < 2 or float(a.std()) == 0.0 or float(b.std()) == 0.0:
        return 0.0
    value = a.corr(b)
    return 0.0 if pd.isna(value) else float(value)


def serialize_phase15a_specs(specs: list[Phase15ASpec]) -> str:
    return serialize_specs(specs)


def recommendation_to_json(rec: dict[str, Any]) -> str:
    return deterministic_json(rec)


def _between(df: pd.DataFrame, start: str, end: str) -> pd.DataFrame:
    minutes = _minutes(df["timestamp"])
    return df[(minutes >= _hhmm(start)) & (minutes < _hhmm(end))].copy()


def _prior_percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    return float(pd.Series(values, dtype="float64").quantile(q, interpolation="linear"))


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
