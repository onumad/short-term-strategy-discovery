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

OR_WINDOWS: dict[str, tuple[str, str]] = {
    "OR5": ("09:30", "09:35"),
    "OR15": ("09:30", "09:45"),
    "OR30": ("09:30", "10:00"),
}

ENTRY_WINDOWS: dict[str, tuple[str, str]] = {
    "opening_response": ("09:35", "10:30"),
    "midday_response": ("10:30", "13:30"),
}

PARTIAL_SESSIONS = {"2026-07-03"}


@dataclass(frozen=True)
class Phase11AConfig:
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
class Phase11ASpec:
    branch: str
    side: str
    or_window: str
    or_start: str
    or_end: str
    entry_window: str
    entry_start: str
    entry_end: str
    confirmation_model: str
    exit_variant: str
    timeframe: int = 5
    atr_cap_multiple: float = 1.25
    buffer_ticks: int = 1
    time_stop_minutes: int = 30
    max_trades_per_day: int = 2
    min_minutes_between_entries: int = 30

    @property
    def candidate_id(self) -> str:
        return (
            f"MNQ_11a_orfade_{self.branch}_{self.or_window}_{self.entry_window}_"
            f"{self.confirmation_model}_{self.exit_variant}"
        )

    def to_dict(self) -> dict[str, Any]:
        return {"candidate_id": self.candidate_id, "instrument": "MNQ", **self.__dict__}


def build_phase11a_specs(config: Phase11AConfig = Phase11AConfig()) -> list[Phase11ASpec]:
    specs: list[Phase11ASpec] = []
    for branch, side in (("short_high_fade", "short"), ("long_low_fade", "long")):
        for or_window, (or_start, or_end) in OR_WINDOWS.items():
            for entry_window, (entry_start, entry_end) in ENTRY_WINDOWS.items():
                for confirmation in ("close_back_inside_fill_next_open", "two_bar_inside_fill_next_open"):
                    for exit_variant in ("hard_stop_time_exit", "midpoint_target_time_exit"):
                        specs.append(
                            Phase11ASpec(
                                branch=branch,
                                side=side,
                                or_window=or_window,
                                or_start=or_start,
                                or_end=or_end,
                                entry_window=entry_window,
                                entry_start=entry_start,
                                entry_end=entry_end,
                                confirmation_model=confirmation,
                                exit_variant=exit_variant,
                            )
                        )
    return specs[: max(int(config.max_specs), 0)]


def compute_opening_range_levels(bars: pd.DataFrame, or_window: str) -> pd.DataFrame:
    if bars.empty:
        return pd.DataFrame()
    if or_window not in OR_WINDOWS:
        raise ValueError(f"unknown opening range window: {or_window}")
    start_s, end_s = OR_WINDOWS[or_window]
    start = _hhmm(start_s)
    end = _hhmm(end_s)
    rth = bars[bars["session_segment"].eq("RTH")].sort_values("timestamp").copy()
    minutes = _minutes(rth["timestamp"])
    scoped = rth[(minutes >= start) & (minutes < end)]
    if scoped.empty:
        return pd.DataFrame()
    levels = scoped.groupby("trading_session").agg(
        opening_range_high=("high", "max"),
        opening_range_low=("low", "min"),
    )
    levels["opening_range_midpoint"] = (levels["opening_range_high"] + levels["opening_range_low"]) / 2.0
    levels["opening_range_width_points"] = levels["opening_range_high"] - levels["opening_range_low"]
    levels["or_window"] = or_window
    levels["or_start"] = start_s
    levels["or_end"] = end_s
    return levels.reset_index()


def build_phase11a_feature_bars(bars: pd.DataFrame, spec: Phase11ASpec) -> pd.DataFrame:
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
    levels = compute_opening_range_levels(bars, spec.or_window)
    out = out.merge(levels, on="trading_session", how="left")
    out = out.dropna(subset=["opening_range_high", "opening_range_low"]).sort_values(["trading_session", "timestamp"]).reset_index(drop=True)
    tr = (out["high"] - out["low"]).abs()
    out["atr"] = tr.groupby(out["trading_session"]).transform(lambda s: s.rolling(14, min_periods=3).mean()).fillna(tr)
    out["opening_range_width_bucket"] = pd.cut(
        out["opening_range_width_points"],
        bins=[-float("inf"), 30.0, 60.0, float("inf")],
        labels=["narrow", "middle", "wide"],
    ).astype(str)
    return out


def generate_phase11a_signals(features: pd.DataFrame, spec: Phase11ASpec) -> list[dict[str, Any]]:
    if features.empty:
        return []
    signals: list[dict[str, Any]] = []
    start = max(_hhmm(spec.entry_start), _hhmm(spec.or_end), 9 * 60 + 35)
    end = min(_hhmm(spec.entry_end), 13 * 60 + 30)
    for _, day in features.groupby("trading_session", sort=True):
        day = day.sort_values("timestamp").reset_index(drop=True)
        touch_count = 0
        for i in range(len(day) - 2):
            row = day.iloc[i]
            minute = _minute(row["timestamp"])
            high = float(row["high"])
            low = float(row["low"])
            close = float(row["close"])
            or_high = float(row["opening_range_high"])
            or_low = float(row["opening_range_low"])
            if spec.branch == "short_high_fade":
                breached = high > or_high
                inside = close < or_high and close >= or_low
                sweep_extreme = high
                sweep_distance = max(high - or_high, 0.0)
            else:
                breached = low < or_low
                inside = close > or_low and close <= or_high
                sweep_extreme = low
                sweep_distance = max(or_low - low, 0.0)
            if breached:
                touch_count += 1
            if minute < start or minute >= end:
                continue
            if not (breached and inside):
                continue
            confirmation_time = row["timestamp"]
            entry_idx = i + 1
            if spec.confirmation_model == "two_bar_inside_fill_next_open":
                confirm = day.iloc[i + 1]
                c_close = float(confirm["close"])
                if not (c_close >= or_low and c_close <= or_high):
                    continue
                confirmation_time = confirm["timestamp"]
                entry_idx = i + 2
            if entry_idx >= len(day):
                continue
            entry = day.iloc[entry_idx]
            entry_minute = _minute(entry["timestamp"])
            if entry_minute < start or entry_minute >= end or entry_minute < 9 * 60 + 35 or entry_minute >= 13 * 60 + 30:
                continue
            signals.append(
                {
                    "candidate_id": spec.candidate_id,
                    "signal_time": row["timestamp"],
                    "confirmation_time": confirmation_time,
                    "entry_time": entry["timestamp"],
                    "trading_session": str(row["trading_session"]),
                    "side": spec.side,
                    "branch": spec.branch,
                    "or_window": spec.or_window,
                    "entry_window": spec.entry_window,
                    "confirmation_model": spec.confirmation_model,
                    "exit_variant": spec.exit_variant,
                    "signal_close": close,
                    "opening_range_high": or_high,
                    "opening_range_low": or_low,
                    "opening_range_midpoint": float(row["opening_range_midpoint"]),
                    "opening_range_width_points": float(row["opening_range_width_points"]),
                    "opening_range_width_bucket": str(row["opening_range_width_bucket"]),
                    "atr": float(row.get("atr", 0.0) or 0.0),
                    "sweep_extreme": sweep_extreme,
                    "sweep_distance_points": sweep_distance,
                    "sweep_distance_bucket": _sweep_distance_bucket(sweep_distance),
                    "first_touch": int(touch_count == 1),
                    "touch_sequence": "first_touch" if touch_count == 1 else "later_touch",
                }
            )
    return signals


def run_phase11a_retest(bars: pd.DataFrame, config: Phase11AConfig = Phase11AConfig()) -> dict[str, pd.DataFrame]:
    specs = build_phase11a_specs(config)
    scoped = bars[~bars["trading_session"].astype(str).isin(PARTIAL_SESSIONS)].copy()
    sessions = sorted(scoped["trading_session"].dropna().astype(str).unique().tolist())
    split_map = split_sessions(sessions)
    rows = []
    trade_frames = []
    fold_frames = []
    invalid_rows = []
    feature_cache: dict[str, pd.DataFrame] = {}
    for spec in specs:
        if spec.or_window not in feature_cache:
            feature_cache[spec.or_window] = build_phase11a_feature_bars(scoped, spec)
        features = feature_cache[spec.or_window]
        signals = generate_phase11a_signals(features, spec)
        trades, invalid_count = simulate_phase11a_trades(features, signals, spec)
        if not trades.empty:
            trades["split"] = trades["trading_session"].astype(str).map(split_map)
            add_cost_waterfall(trades, instrument_symbol="MNQ", inplace=True)
            trade_frames.append(trades)
            fold_frames.append(_fold_rows(trades, spec, sessions, config))
        invalid_rows.append({"candidate_id": spec.candidate_id, "invalid_risk_skipped_count": invalid_count})
        rows.append(_candidate_row(spec, trades, invalid_count, sessions, split_map, config))
    trade_logs = pd.concat(trade_frames, ignore_index=True) if trade_frames else pd.DataFrame()
    folds = pd.concat(fold_frames, ignore_index=True) if fold_frames else pd.DataFrame()
    candidates = pd.DataFrame(rows).sort_values(["phase11a_score", "stress_pnl"], ascending=[False, False]).reset_index(drop=True)
    candidates.insert(0, "phase11a_rank", range(1, len(candidates) + 1))
    return {
        "candidate_results": candidates,
        "trade_logs": trade_logs,
        "walk_forward_folds": folds,
        "daily_pnl": daily_pnl_summary(trade_logs),
        "concentration_diagnostics": concentration_diagnostics(trade_logs),
        "or_window_summary": _summary(trade_logs, "or_window"),
        "side_summary": _summary(trade_logs, "branch"),
        "entry_window_summary": _summary(trade_logs, "entry_window"),
        "confirmation_summary": _summary(trade_logs, "confirmation_model"),
        "exit_variant_summary": _summary(trade_logs, "exit_variant"),
        "exit_reason_summary": _summary(trade_logs, "exit_reason"),
        "touch_sequence_summary": _summary(trade_logs, "touch_sequence"),
        "opening_range_width_summary": _summary(trade_logs, "opening_range_width_bucket"),
        "sweep_distance_summary": _summary(trade_logs, "sweep_distance_bucket"),
        "mfe_mae_summary": _mfe_mae_summary(trade_logs),
        "invalid_risk_summary": pd.DataFrame(invalid_rows),
        "specs": pd.DataFrame([s.to_dict() for s in specs]),
    }


def simulate_phase11a_trades(features: pd.DataFrame, signals: list[dict[str, Any]], spec: Phase11ASpec) -> tuple[pd.DataFrame, int]:
    if features.empty or not signals:
        return pd.DataFrame(), 0
    inst = get_instrument("MNQ")
    day_map = {str(s): d.sort_values("timestamp").reset_index(drop=True) for s, d in features.groupby("trading_session", sort=True)}
    rows: list[dict[str, Any]] = []
    counts: dict[str, int] = {}
    last_entry: dict[str, pd.Timestamp] = {}
    invalid_count = 0
    for signal in sorted(signals, key=lambda x: x["entry_time"]):
        session = str(signal["trading_session"])
        entry_time = pd.Timestamp(signal["entry_time"])
        if counts.get(session, 0) >= spec.max_trades_per_day:
            continue
        if session in last_entry and (entry_time - last_entry[session]).total_seconds() / 60 < spec.min_minutes_between_entries:
            continue
        day = day_map.get(session)
        if day is None:
            continue
        matches = day.index[day["timestamp"].eq(entry_time)].tolist()
        if not matches:
            continue
        trade = _simulate_one(day, matches[0], signal, spec, inst)
        if trade is None:
            invalid_count += 1
            continue
        rows.append({**signal, **trade, **spec.to_dict()})
        counts[session] = counts.get(session, 0) + 1
        last_entry[session] = entry_time
    return pd.DataFrame(rows), invalid_count


def _simulate_one(day: pd.DataFrame, entry_pos: int, signal: dict[str, Any], spec: Phase11ASpec, inst) -> dict[str, Any] | None:
    entry = day.iloc[entry_pos]
    entry_price = float(entry["open"])
    buffer = spec.buffer_ticks * inst.tick_size
    atr = max(float(signal.get("atr", 0.0)), inst.tick_size * 8)
    midpoint = float(signal["opening_range_midpoint"])
    if spec.side == "short":
        structural_stop = float(signal["sweep_extreme"]) + buffer
        atr_cap_stop = entry_price + atr * spec.atr_cap_multiple
        actual_stop = min(structural_stop, atr_cap_stop)
        if actual_stop <= entry_price:
            return None
        target = midpoint
        if target >= entry_price:
            target = entry_price - inst.tick_size
    else:
        structural_stop = float(signal["sweep_extreme"]) - buffer
        atr_cap_stop = entry_price - atr * spec.atr_cap_multiple
        actual_stop = max(structural_stop, atr_cap_stop)
        if actual_stop >= entry_price:
            return None
        target = midpoint
        if target <= entry_price:
            target = entry_price + inst.tick_size
    max_exit = pd.Timestamp(entry["timestamp"]) + pd.Timedelta(minutes=spec.time_stop_minutes)
    exit_price = float(entry["close"])
    exit_time = entry["timestamp"]
    exit_reason = "time_stop"
    mfe = mae = 0.0
    ambiguity = 0
    target_enabled = spec.exit_variant == "midpoint_target_time_exit"
    for pos in range(entry_pos, len(day)):
        row = day.iloc[pos]
        ts = pd.Timestamp(row["timestamp"])
        if spec.side == "short":
            fav = entry_price - float(row["low"])
            adv = float(row["high"]) - entry_price
            stop_hit = float(row["high"]) >= actual_stop
            target_hit = float(row["low"]) <= target if target_enabled else False
        else:
            fav = float(row["high"]) - entry_price
            adv = entry_price - float(row["low"])
            stop_hit = float(row["low"]) <= actual_stop
            target_hit = float(row["high"]) >= target if target_enabled else False
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


def _candidate_row(spec: Phase11ASpec, trades: pd.DataFrame, invalid_count: int, sessions: list[str], split_map: dict[Any, str], config: Phase11AConfig) -> dict[str, Any]:
    row = spec.to_dict()
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
    row["phase11a_label"] = _label(row, config)
    row["research_axis_status"] = _axis_status(row)
    row["phase11a_score"] = round(
        float(row.get("stress_pnl", 0))
        + float(row.get("walk_forward_stress_pnl", 0))
        - abs(float(row.get("max_drawdown", 0)))
        - 5000 * max(float(row.get("best_day_concentration", 1)) - config.concentration_limit, 0),
        4,
    )
    row["reject_reasons"] = _reasons(row, config)
    return row


def _label(r: dict[str, Any], c: Phase11AConfig) -> str:
    adequate_activity = r.get("trades", 0) >= c.min_trades and r.get("active_days", 0) >= c.min_active_days and 1 <= r.get("trades_per_active_day", 0) <= 3
    economics_positive = r.get("net_pnl", 0) > 0 and r.get("stress_pnl", 0) > 0 and r.get("validation_pnl", 0) > 0 and r.get("holdout_pnl", 0) > 0
    fold_ok = r.get("walk_forward_stress_pnl", 0) > 0 and r.get("positive_wf_test_folds_pct", 0) >= 0.9 and r.get("worst_wf_test_fold", 0) >= c.worst_fold_limit
    conc_ok = r.get("best_day_concentration", 1) <= c.concentration_limit and r.get("best_trade_concentration", 1) <= c.trade_concentration_limit
    drawdown_ok = r.get("max_drawdown", 0) >= c.drawdown_limit
    if adequate_activity and economics_positive and fold_ok and conc_ok and drawdown_ok:
        return "phase11a_candidate_for_paper_review"
    narrow_fold_miss = r.get("walk_forward_stress_pnl", 0) > 0 and r.get("positive_wf_test_folds_pct", 0) >= 0.75 and r.get("worst_wf_test_fold", 0) >= c.worst_fold_limit
    narrow_conc_miss = r.get("best_day_concentration", 1) <= c.concentration_limit + c.narrow_watch_miss and r.get("best_trade_concentration", 1) <= c.trade_concentration_limit + c.narrow_watch_miss
    if adequate_activity and economics_positive and drawdown_ok and (narrow_fold_miss or narrow_conc_miss):
        return "phase11a_watchlist_needs_more_history"
    if not adequate_activity:
        return "phase11a_rejected_low_activity"
    if r.get("net_pnl", 0) <= 0 or r.get("stress_pnl", 0) <= 0:
        return "phase11a_rejected_negative_stress"
    if r.get("validation_pnl", 0) <= 0:
        return "phase11a_rejected_negative_validation"
    if r.get("holdout_pnl", 0) <= 0:
        return "phase11a_rejected_negative_holdout"
    if not drawdown_ok:
        return "phase11a_rejected_drawdown"
    if not fold_ok:
        return "phase11a_rejected_fold_instability"
    if not conc_ok:
        return "phase11a_rejected_concentration"
    return "phase11a_rejected_fold_instability"


def _axis_status(r: dict[str, Any]) -> str:
    if r.get("phase11a_label") == "phase11a_candidate_for_paper_review":
        return "axis_review_packet_candidate"
    if r.get("phase11a_label") == "phase11a_watchlist_needs_more_history":
        return "axis_targeted_retest_candidate"
    if r.get("stress_pnl", 0) > 0 and r.get("holdout_pnl", 0) > 0 and (r.get("best_day_concentration", 1) > 0.15 or r.get("best_trade_concentration", 1) > 0.08):
        return "axis_positive_but_concentrated"
    if r.get("gross_pnl", 0) > 0 and r.get("stress_pnl", 0) <= 0:
        return "axis_positive_but_cost_sensitive"
    if r.get("stress_pnl", 0) > 0:
        return "axis_positive_but_unstable"
    return "axis_failed"


def _reasons(r: dict[str, Any], c: Phase11AConfig) -> str:
    checks = [
        ("low activity", r.get("trades", 0) < c.min_trades or r.get("active_days", 0) < c.min_active_days or not (1 <= r.get("trades_per_active_day", 0) <= 3)),
        ("negative stress", r.get("net_pnl", 0) <= 0 or r.get("stress_pnl", 0) <= 0),
        ("negative validation", r.get("validation_pnl", 0) <= 0),
        ("negative holdout", r.get("holdout_pnl", 0) <= 0),
        ("drawdown", r.get("max_drawdown", 0) < c.drawdown_limit),
        ("fold instability", r.get("walk_forward_stress_pnl", 0) <= 0 or r.get("positive_wf_test_folds_pct", 0) < 0.9 or r.get("worst_wf_test_fold", 0) < c.worst_fold_limit),
        ("concentration", r.get("best_day_concentration", 1) > c.concentration_limit or r.get("best_trade_concentration", 1) > c.trade_concentration_limit),
    ]
    return "; ".join(name for name, bad in checks if bad) or "survived Phase 11A gates; review packet only"


def make_phase11a_recommendation(result: dict[str, pd.DataFrame]) -> dict[str, Any]:
    c = result["candidate_results"]
    if c.empty:
        return {"next_action": "phase12a_first_pullback_after_trend_day_open", "rationale": "No Phase 11A candidates were produced."}
    paper = c[c["phase11a_label"].eq("phase11a_candidate_for_paper_review")]
    if not paper.empty:
        return {"next_action": "phase11a_review_packet_only", "rationale": "At least one candidate passed Phase 11A gates; review only, not paper approval.", "top_candidate": paper.iloc[0].to_dict()}
    watch = c[c["phase11a_label"].eq("phase11a_watchlist_needs_more_history")]
    if not watch.empty:
        return {"next_action": "phase11b_targeted_opening_range_fade_diagnostic_retest", "rationale": "A positive opening-range fade axis narrowly missed one robustness gate.", "top_candidate": watch.iloc[0].to_dict()}
    positive = c[(c["stress_pnl"] > 0) & (c["validation_pnl"] > 0) & (c["holdout_pnl"] > 0)]
    if not positive.empty:
        return {"next_action": "park_opening_range_fade_as_research_signal", "rationale": "Phase 11A had positive axes but they remained concentrated or unstable.", "top_candidate": positive.iloc[0].to_dict()}
    return {"next_action": "phase12a_first_pullback_after_trend_day_open", "rationale": "No positive Phase 11A opening-range fade axis survived validation, holdout, and stress."}


def render_phase11a_report(result: dict[str, pd.DataFrame], recommendation: dict[str, Any], report_path: Path) -> str:
    c = result["candidate_results"]
    counts = c["phase11a_label"].value_counts().to_dict() if not c.empty else {}
    status = c["research_axis_status"].value_counts().to_dict() if not c.empty else {}
    lines = [
        "# Phase 11A Opening Range Fade With Stricter Confirmation",
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
        lines.append(f"| `{r['candidate_id']}` | {r['research_axis_status']} | {r['phase11a_label']} | ${float(r['net_pnl']):.2f} | ${float(r['stress_pnl']):.2f} | ${float(r['validation_pnl']):.2f} | ${float(r['holdout_pnl']):.2f} | ${float(r['walk_forward_stress_pnl']):.2f} | {r['reject_reasons']} |")
    lines += [
        "",
        "## Outputs",
        "",
        "- `outputs/phase11a_candidate_results.csv`",
        "- `outputs/phase11a_trade_logs.csv`",
        "- `outputs/phase11a_walk_forward_folds.csv`",
        "- `outputs/phase11a_daily_pnl.csv`",
        "- `outputs/phase11a_concentration_diagnostics.csv`",
        "- `outputs/phase11a_or_window_summary.csv`",
        "- `outputs/phase11a_side_summary.csv`",
        "- `outputs/phase11a_entry_window_summary.csv`",
        "- `outputs/phase11a_confirmation_summary.csv`",
        "- `outputs/phase11a_exit_reason_summary.csv`",
        "- `outputs/phase11a_touch_sequence_summary.csv`",
        "- `outputs/phase11a_opening_range_width_summary.csv`",
        "- `outputs/phase11a_sweep_distance_summary.csv`",
        "- `outputs/phase11a_mfe_mae_summary.csv`",
        "- `outputs/phase11a_strategy_specs.json`",
        "- `outputs/phase11a_next_action_recommendation.json`",
        f"- `{report_path.as_posix()}`",
    ]
    return "\n".join(lines) + "\n"


def _fold_rows(trades: pd.DataFrame, spec: Phase11ASpec, sessions: list[str], c: Phase11AConfig) -> pd.DataFrame:
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


def _sweep_distance_bucket(distance: float) -> str:
    if distance <= 5.0:
        return "small_sweep"
    if distance <= 15.0:
        return "medium_sweep"
    return "large_sweep"


def serialize_phase11a_specs(specs: list[Phase11ASpec]) -> str:
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
