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

FAMILY_WINDOWS: dict[str, dict[str, str | None]] = {
    "lunch_range_breakout": {"level_source": "intraday_range", "build_start": "11:30", "build_end": "13:00", "trade_start": "13:00", "trade_end": "15:30", "behavior": "breakout"},
    "lunch_range_fade": {"level_source": "intraday_range", "build_start": "11:30", "build_end": "13:00", "trade_start": "13:00", "trade_end": "15:30", "behavior": "fade"},
    "power_hour_range_breakout": {"level_source": "intraday_range", "build_start": "13:30", "build_end": "14:30", "trade_start": "14:30", "trade_end": "15:45", "behavior": "breakout"},
    "power_hour_range_fade": {"level_source": "intraday_range", "build_start": "13:30", "build_end": "14:30", "trade_start": "14:30", "trade_end": "15:45", "behavior": "fade"},
    "prior_rth_high_low_breakout": {"level_source": "prior_rth", "build_start": None, "build_end": None, "trade_start": "10:00", "trade_end": "13:30", "behavior": "breakout"},
    "prior_rth_high_low_sweep_fade": {"level_source": "prior_rth", "build_start": None, "build_end": None, "trade_start": "10:00", "trade_end": "13:30", "behavior": "fade"},
}


@dataclass(frozen=True)
class Phase13AConfig:
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
    narrow_watch_miss: float = 0.05


@dataclass(frozen=True)
class Phase13ASpec:
    family: str
    side: str
    entry_model: str
    exit_variant: str
    timeframe: int = 5
    atr_cap_multiple: float = 1.25
    buffer_ticks: int = 1
    time_stop_minutes: int = 30
    max_trades_per_day: int = 1

    @property
    def candidate_id(self) -> str:
        return f"MNQ_13a_{self.family}_{self.side}_{self.entry_model}_{self.exit_variant}"

    @property
    def branch(self) -> str:
        return f"{self.family}_{self.side}"

    def to_dict(self) -> dict[str, Any]:
        meta = FAMILY_WINDOWS[self.family]
        return {
            "candidate_id": self.candidate_id,
            "instrument": "MNQ",
            "family": self.family,
            "branch": self.branch,
            "side": self.side,
            "entry_model": self.entry_model,
            "exit_variant": self.exit_variant,
            "timeframe": self.timeframe,
            "atr_cap_multiple": self.atr_cap_multiple,
            "buffer_ticks": self.buffer_ticks,
            "time_stop_minutes": self.time_stop_minutes,
            "max_trades_per_day": self.max_trades_per_day,
            "level_source": meta["level_source"],
            "build_start": meta["build_start"],
            "build_end": meta["build_end"],
            "trade_start": meta["trade_start"],
            "trade_end": meta["trade_end"],
            "behavior": meta["behavior"],
        }


def build_phase13a_specs(config: Phase13AConfig = Phase13AConfig()) -> list[Phase13ASpec]:
    specs: list[Phase13ASpec] = []
    for family in FAMILY_WINDOWS:
        for side in ("long", "short"):
            for entry_model in ("close_confirm_fill_next_open", "two_bar_confirm_fill_next_open"):
                for exit_variant in ("hard_stop_time_exit", "structure_target_time_exit"):
                    specs.append(Phase13ASpec(family=family, side=side, entry_model=entry_model, exit_variant=exit_variant))
    return specs[: max(int(config.max_specs), 0)]


def compute_intraday_range_levels(bars: pd.DataFrame, family: str) -> pd.DataFrame:
    meta = FAMILY_WINDOWS[family]
    if meta["level_source"] != "intraday_range":
        raise ValueError(f"{family} does not use intraday range levels")
    rth = bars[bars["session_segment"].eq("RTH")].sort_values("timestamp").copy()
    minutes = _minutes(rth["timestamp"])
    scoped = rth[(minutes >= _hhmm(str(meta["build_start"]))) & (minutes < _hhmm(str(meta["build_end"])))]
    if scoped.empty:
        return pd.DataFrame()
    out = scoped.groupby("trading_session").agg(level_high=("high", "max"), level_low=("low", "min"), level_open=("open", "first"), level_close=("close", "last")).reset_index()
    out["level_midpoint"] = (out["level_high"] + out["level_low"]) / 2.0
    out["level_width_points"] = out["level_high"] - out["level_low"]
    out["level_family"] = family
    out["level_source"] = "intraday_range"
    out["build_start"] = meta["build_start"]
    out["build_end"] = meta["build_end"]
    return out


def compute_prior_rth_levels(bars: pd.DataFrame) -> pd.DataFrame:
    rth = bars[bars["session_segment"].eq("RTH")].sort_values("timestamp").copy()
    if rth.empty:
        return pd.DataFrame()
    levels = rth.groupby("trading_session").agg(prior_source_high=("high", "max"), prior_source_low=("low", "min"), prior_source_close=("close", "last")).reset_index()
    levels["level_high"] = levels["prior_source_high"].shift(1)
    levels["level_low"] = levels["prior_source_low"].shift(1)
    levels["level_midpoint"] = (levels["level_high"] + levels["level_low"]) / 2.0
    levels["level_width_points"] = levels["level_high"] - levels["level_low"]
    levels["prior_rth_session"] = levels["trading_session"].shift(1)
    levels["level_source"] = "prior_rth"
    return levels.dropna(subset=["level_high", "level_low"]).reset_index(drop=True)


def build_phase13a_feature_bars(bars: pd.DataFrame, spec: Phase13ASpec) -> pd.DataFrame:
    rth = bars[bars["session_segment"].eq("RTH")].sort_values("timestamp").copy()
    frames = []
    for _, day in rth.groupby("trading_session", sort=True):
        day = day.set_index("timestamp")
        res = (
            day.resample("5min", origin="start_day", offset="30min", label="left", closed="left")
            .agg({"symbol": "last", "open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum", "trading_session": "last", "session_segment": "last"})
            .dropna(subset=["open", "high", "low", "close"])
            .reset_index()
        )
        frames.append(res)
    if not frames:
        return pd.DataFrame()
    out = pd.concat(frames, ignore_index=True)
    if FAMILY_WINDOWS[spec.family]["level_source"] == "prior_rth":
        levels = compute_prior_rth_levels(bars)
    else:
        levels = compute_intraday_range_levels(bars, spec.family)
    out = out.merge(levels, on="trading_session", how="left")
    out = out.dropna(subset=["level_high", "level_low"]).sort_values(["trading_session", "timestamp"]).reset_index(drop=True)
    tr = (out["high"] - out["low"]).abs()
    out["atr"] = tr.groupby(out["trading_session"]).transform(lambda s: s.rolling(14, min_periods=3).mean()).fillna(tr)
    out["level_width_bucket"] = pd.cut(out["level_width_points"], bins=[-float("inf"), 20.0, 50.0, float("inf")], labels=["narrow", "middle", "wide"]).astype(str)
    return out


def generate_phase13a_signals(features: pd.DataFrame, spec: Phase13ASpec) -> list[dict[str, Any]]:
    if features.empty:
        return []
    meta = FAMILY_WINDOWS[spec.family]
    start = _hhmm(str(meta["trade_start"]))
    end = _hhmm(str(meta["trade_end"]))
    inst = get_instrument("MNQ")
    buffer = spec.buffer_ticks * inst.tick_size
    signals: list[dict[str, Any]] = []
    for _, day in features.groupby("trading_session", sort=True):
        day = day.sort_values("timestamp").reset_index(drop=True)
        candidates: list[dict[str, Any]] = []
        sweep_seen = False
        for i in range(len(day) - 2):
            row = day.iloc[i]
            minute = _minute(row["timestamp"])
            if minute < start or minute >= end:
                continue
            high = float(row["high"])
            low = float(row["low"])
            close = float(row["close"])
            level_high = float(row["level_high"])
            level_low = float(row["level_low"])
            behavior = str(meta["behavior"])
            if behavior == "breakout":
                ok = (close > level_high + buffer) if spec.side == "long" else (close < level_low - buffer)
            else:
                if spec.side == "long":
                    sweep_seen = sweep_seen or low < level_low - buffer
                    ok = sweep_seen and close > level_low
                else:
                    sweep_seen = sweep_seen or high > level_high + buffer
                    ok = sweep_seen and close < level_high
            if not ok:
                continue
            confirmation_time = row["timestamp"]
            entry_idx = i + 1
            if spec.entry_model == "two_bar_confirm_fill_next_open":
                confirm = day.iloc[i + 1]
                confirm_close = float(confirm["close"])
                if behavior == "breakout":
                    confirm_ok = (confirm_close > level_high + buffer) if spec.side == "long" else (confirm_close < level_low - buffer)
                else:
                    confirm_ok = (confirm_close > level_low) if spec.side == "long" else (confirm_close < level_high)
                if not confirm_ok:
                    continue
                confirmation_time = confirm["timestamp"]
                entry_idx = i + 2
            if entry_idx >= len(day):
                continue
            entry = day.iloc[entry_idx]
            entry_minute = _minute(entry["timestamp"])
            if entry_minute < start or entry_minute >= end:
                continue
            candidates.append(
                {
                    "candidate_id": spec.candidate_id,
                    "signal_time": row["timestamp"],
                    "confirmation_time": confirmation_time,
                    "entry_time": entry["timestamp"],
                    "trading_session": str(row["trading_session"]),
                    "family": spec.family,
                    "branch": spec.branch,
                    "side": spec.side,
                    "entry_model": spec.entry_model,
                    "exit_variant": spec.exit_variant,
                    "behavior": behavior,
                    "level_source": meta["level_source"],
                    "trade_start": meta["trade_start"],
                    "trade_end": meta["trade_end"],
                    "level_high": level_high,
                    "level_low": level_low,
                    "level_midpoint": float(row["level_midpoint"]),
                    "level_width_points": float(row["level_width_points"]),
                    "level_width_bucket": str(row["level_width_bucket"]),
                    "signal_close": close,
                    "signal_high": high,
                    "signal_low": low,
                    "atr": float(row.get("atr", 0.0) or 0.0),
                }
            )
        if candidates:
            first = dict(candidates[0])
            first["skipped_extra_signals_same_day"] = len(candidates) - 1
            signals.append(first)
    return signals


def run_phase13a_scout(bars: pd.DataFrame, registry_matrix: pd.DataFrame, portfolio_daily: pd.DataFrame, config: Phase13AConfig = Phase13AConfig()) -> dict[str, pd.DataFrame]:
    specs = build_phase13a_specs(config)
    scoped = bars[~bars["trading_session"].astype(str).isin(PARTIAL_SESSIONS)].copy()
    sessions = sorted(scoped["trading_session"].dropna().astype(str).unique().tolist())
    split_map = split_sessions(sessions)
    rows: list[dict[str, Any]] = []
    trade_frames = []
    fold_frames = []
    feature_cache: dict[str, pd.DataFrame] = {}
    for spec in specs:
        if spec.family not in feature_cache:
            feature_cache[spec.family] = build_phase13a_feature_bars(scoped, spec)
        features = feature_cache[spec.family]
        signals = generate_phase13a_signals(features, spec)
        trades, invalid = simulate_phase13a_trades(features, signals, spec)
        if not trades.empty:
            trades["split"] = trades["trading_session"].astype(str).map(split_map)
            trade_frames.append(trades)
            fold_frames.append(_fold_rows(trades, spec, sessions, config))
        rows.append(_candidate_row(spec, trades, invalid, signals, sessions, split_map, registry_matrix, portfolio_daily, config))
    trade_logs = pd.concat(trade_frames, ignore_index=True) if trade_frames else pd.DataFrame()
    folds = pd.concat(fold_frames, ignore_index=True) if fold_frames else pd.DataFrame()
    candidates = pd.DataFrame(rows).sort_values(["phase13a_score", "stress_pnl"], ascending=[False, False]).reset_index(drop=True)
    candidates.insert(0, "phase13a_rank", range(1, len(candidates) + 1))
    daily = daily_pnl_summary(trade_logs)
    return {
        "candidate_results": candidates,
        "trade_logs": trade_logs,
        "daily_pnl": daily,
        "walk_forward_folds": folds,
        "concentration_diagnostics": concentration_diagnostics(trade_logs),
        "family_summary": grouped_trade_summary(trade_logs, "family", include_gross=True),
        "side_summary": grouped_trade_summary(trade_logs, "side", include_gross=True),
        "entry_model_summary": grouped_trade_summary(trade_logs, "entry_model", include_gross=True),
        "exit_variant_summary": grouped_trade_summary(trade_logs, "exit_variant", include_gross=True),
        "correlation_to_registry": _correlation_rows(candidates, "registry"),
        "correlation_to_portfolios": _correlation_rows(candidates, "portfolio"),
        "specs": pd.DataFrame([s.to_dict() for s in specs]),
    }


def simulate_phase13a_trades(features: pd.DataFrame, signals: list[dict[str, Any]], spec: Phase13ASpec) -> tuple[pd.DataFrame, int]:
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


def _simulate_one(day: pd.DataFrame, entry_pos: int, signal: dict[str, Any], spec: Phase13ASpec, inst) -> dict[str, Any] | None:
    entry = day.iloc[entry_pos]
    entry_price = float(entry["open"])
    buffer = spec.buffer_ticks * inst.tick_size
    atr = max(float(signal.get("atr", 0.0)), inst.tick_size * 8)
    level_high = float(signal["level_high"])
    level_low = float(signal["level_low"])
    midpoint = float(signal["level_midpoint"])
    behavior = str(signal["behavior"])
    if spec.side == "long":
        structural_stop = (level_low - buffer) if behavior == "breakout" else (float(signal["signal_low"]) - buffer)
        atr_cap_stop = entry_price - atr * spec.atr_cap_multiple
        actual_stop = max(structural_stop, atr_cap_stop)
        if actual_stop >= entry_price:
            return None
        target = (entry_price + max(level_high - level_low, inst.tick_size)) if behavior == "breakout" else midpoint
        if target <= entry_price:
            target = entry_price + inst.tick_size
    else:
        structural_stop = (level_high + buffer) if behavior == "breakout" else (float(signal["signal_high"]) + buffer)
        atr_cap_stop = entry_price + atr * spec.atr_cap_multiple
        actual_stop = min(structural_stop, atr_cap_stop)
        if actual_stop <= entry_price:
            return None
        target = (entry_price - max(level_high - level_low, inst.tick_size)) if behavior == "breakout" else midpoint
        if target >= entry_price:
            target = entry_price - inst.tick_size
    flatten_minute = min(_hhmm(str(FAMILY_WINDOWS[spec.family]["trade_end"])), 15 * 60 + 45)
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
        if ts >= max_exit or _minute(ts) >= flatten_minute:
            exit_price = float(row["close"])
            exit_time = ts
            exit_reason = "session_flatten" if _minute(ts) >= flatten_minute else "time_stop"
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


def _candidate_row(spec: Phase13ASpec, trades: pd.DataFrame, invalid: int, signals: list[dict[str, Any]], sessions: list[str], split_map: dict[Any, str], registry_matrix: pd.DataFrame, portfolio_daily: pd.DataFrame, config: Phase13AConfig) -> dict[str, Any]:
    row = spec.to_dict()
    if trades.empty:
        row.update(_zero_metrics())
        daily = pd.DataFrame(columns=["trading_session", "net_pnl"])
        folds = pd.DataFrame()
    else:
        t = trades.copy()
        t["split"] = t["trading_session"].astype(str).map(split_map)
        net = float(t["net_pnl"].sum())
        equity = t["net_pnl"].cumsum()
        daily = t.groupby("trading_session", as_index=False)["net_pnl"].sum()
        daily_series = daily.set_index("trading_session")["net_pnl"]
        folds = _fold_rows(t, spec, sessions, config)
        row.update(
            {
                "trades": len(t),
                "active_days": int(t["trading_session"].nunique()),
                "trades_per_active_day": safe_divide(len(t), t["trading_session"].nunique()),
                "gross_pnl": round(float(t["gross_pnl"].sum()), 2),
                "net_pnl": round(net, 2),
                "stress_pnl": round(float(t["stress_pnl"].sum()), 2),
                "validation_pnl": round(float(t.loc[t["split"].eq("validation"), "net_pnl"].sum()), 2),
                "holdout_pnl": round(float(t.loc[t["split"].eq("holdout"), "net_pnl"].sum()), 2),
                "max_drawdown": round(float((equity - equity.cummax()).min()), 2),
                "best_day_concentration": positive_concentration(float(daily_series.max()), net),
                "best_trade_concentration": positive_concentration(float(t["net_pnl"].max()), net),
                "avg_mfe": round(float(t["mfe"].mean()), 2),
                "avg_mae": round(float(t["mae"].mean()), 2),
                "stop_hit_rate": safe_divide(int(t["stop_hit"].sum()), len(t)),
                "target_hit_rate": safe_divide(int(t["target_hit"].sum()), len(t)),
                "time_stop_rate": safe_divide(int(t["time_stop"].sum()), len(t)),
                **fold_summary(folds),
            }
        )
    reg_corr = daily_correlation_to_matrix(daily, registry_matrix)
    port_corr = daily_correlation_to_portfolios(daily, portfolio_daily)
    row.update(
        {
            "average_correlation_to_registry": reg_corr["average_abs_correlation"],
            "max_correlation_to_registry": reg_corr["max_abs_correlation"],
            "average_correlation_to_portfolio_audit": port_corr["average_abs_correlation"],
            "max_correlation_to_portfolio_audit": port_corr["max_abs_correlation"],
            "invalid_risk_skipped_count": int(invalid),
            "signals_found": len(signals),
            "skipped_extra_signals_same_day": sum(int(s.get("skipped_extra_signals_same_day", 0)) for s in signals),
        }
    )
    row["phase13a_label"] = _label(row, config)
    row["signal_evidence_status"] = _signal_evidence(row)
    row["tradability_status"] = _tradability(row)
    row["research_track"] = _research_track(row)
    row["reject_reasons"] = _reasons(row, config)
    row["paper_trading_approved"] = False
    row["phase13a_score"] = round(float(row.get("stress_pnl", 0)) + float(row.get("walk_forward_stress_pnl", 0)) - abs(float(row.get("max_drawdown", 0))) - 1000 * max(float(row.get("average_correlation_to_registry", 1)) - config.registry_avg_corr_limit, 0), 4)
    return row


def daily_correlation_to_matrix(candidate_daily: pd.DataFrame, matrix: pd.DataFrame) -> dict[str, float]:
    if candidate_daily.empty or matrix.empty:
        return {"average_abs_correlation": 0.0, "max_abs_correlation": 0.0}
    base = matrix.copy()
    cand = candidate_daily.groupby("trading_session", as_index=False)["net_pnl"].sum().rename(columns={"net_pnl": "candidate_net_pnl"})
    merged = base.merge(cand, on="trading_session", how="outer").fillna(0.0)
    vals = []
    for col in [c for c in merged.columns if c not in {"trading_session", "candidate_net_pnl"}]:
        vals.append(abs(_corr(merged["candidate_net_pnl"], merged[col])))
    return {"average_abs_correlation": round(sum(vals) / len(vals), 6) if vals else 0.0, "max_abs_correlation": round(max(vals), 6) if vals else 0.0}


def daily_correlation_to_portfolios(candidate_daily: pd.DataFrame, portfolio_daily: pd.DataFrame) -> dict[str, float]:
    if portfolio_daily.empty:
        return {"average_abs_correlation": 0.0, "max_abs_correlation": 0.0}
    pivot = portfolio_daily.pivot_table(index="trading_session", columns=["portfolio_set", "portfolio_mode"], values="net_pnl", aggfunc="sum", fill_value=0.0).reset_index()
    pivot.columns = ["trading_session" if c == ("trading_session", "") or c == "trading_session" else "::".join(map(str, c)) for c in pivot.columns]
    return daily_correlation_to_matrix(candidate_daily, pivot)


def make_phase13a_recommendation(result: dict[str, pd.DataFrame]) -> dict[str, Any]:
    c = result["candidate_results"]
    if c.empty:
        return {"next_action": "framework_checkpoint_before_more_strategy_search", "paper_trading_approved": False, "rationale": "No Phase 13A candidates were produced."}
    paper = c[c["phase13a_label"].eq("phase13a_candidate_for_paper_review")]
    if not paper.empty:
        return {"next_action": "phase13a_review_packet_only", "paper_trading_approved": False, "rationale": "A diagnostic candidate passed gates; review packet only, no paper approval.", "top_candidate": paper.iloc[0].to_dict()}
    watch = c[c["phase13a_label"].eq("phase13a_watchlist_needs_more_history")]
    if not watch.empty:
        return {"next_action": "phase13b_targeted_uncorrelated_family_diagnostic", "paper_trading_approved": False, "rationale": "One axis improved correlation/activity but still missed robustness gates.", "top_candidate": watch.iloc[0].to_dict()}
    positive = c[c["phase13a_label"].eq("phase13a_positive_uncorrelated_research_signal")]
    if not positive.empty:
        return {"next_action": "add_to_research_signal_registry_and_run_portfolio_audit_b", "paper_trading_approved": False, "rationale": "A positive but nontradable uncorrelated axis appeared.", "top_candidate": positive.iloc[0].to_dict()}
    return {"next_action": "framework_checkpoint_before_more_strategy_search", "paper_trading_approved": False, "rationale": "No positive uncorrelated Phase 13A axis survived."}


def render_phase13a_report(result: dict[str, pd.DataFrame], recommendation: dict[str, Any], report_path: Path) -> str:
    c = result["candidate_results"]
    counts = c["phase13a_label"].value_counts().to_dict() if not c.empty else {}
    lines = [
        "# Phase 13A — Uncorrelated Family Scout",
        "",
        RESEARCH_ONLY_GUARDRAIL,
        "",
        "## Summary",
        "",
        f"- Specs evaluated: `{len(c)}`",
        f"- Trade rows: `{len(result['trade_logs'])}`",
        f"- Label counts: `{counts}`",
        f"- Next action: `{recommendation.get('next_action')}`",
        f"- Rationale: {recommendation.get('rationale')}",
        "- Paper trading approved: `false`",
        "",
        "## Top Candidates",
        "",
        "| Candidate | Label | Net | Stress | Val | Holdout | WF Stress | Avg registry corr | Max registry corr | Reasons |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for _, r in c.head(12).iterrows():
        lines.append(f"| `{r['candidate_id']}` | {r['phase13a_label']} | {float(r['net_pnl']):.2f} | {float(r['stress_pnl']):.2f} | {float(r['validation_pnl']):.2f} | {float(r['holdout_pnl']):.2f} | {float(r['walk_forward_stress_pnl']):.2f} | {float(r['average_correlation_to_registry']):.3f} | {float(r['max_correlation_to_registry']):.3f} | {r['reject_reasons']} |")
    lines += ["", "## Outputs", "", "- `outputs/phase13a_candidate_results.csv`", "- `outputs/phase13a_trade_logs.csv`", "- `outputs/phase13a_daily_pnl.csv`", "- `outputs/phase13a_walk_forward_folds.csv`", "- `outputs/phase13a_correlation_to_registry.csv`", "- `outputs/phase13a_correlation_to_portfolios.csv`", f"- `{report_path.as_posix()}`"]
    return "\n".join(lines) + "\n"


def _label(r: dict[str, Any], c: Phase13AConfig) -> str:
    adequate_activity = r.get("trades", 0) >= c.min_trades and r.get("active_days", 0) >= c.min_active_days and 1 <= r.get("trades_per_active_day", 0) <= 3
    economics_positive = r.get("net_pnl", 0) > 0 and r.get("stress_pnl", 0) > 0 and r.get("validation_pnl", 0) > 0 and r.get("holdout_pnl", 0) > 0 and r.get("walk_forward_stress_pnl", 0) > 0
    fold_ok = r.get("positive_wf_test_folds_pct", 0) >= 0.9 and r.get("worst_wf_test_fold", 0) >= c.worst_fold_limit
    conc_ok = r.get("best_day_concentration", 1) <= c.concentration_limit and r.get("best_trade_concentration", 1) <= c.trade_concentration_limit
    corr_ok = r.get("average_correlation_to_registry", 1) <= c.registry_avg_corr_limit and r.get("max_correlation_to_registry", 1) <= c.registry_max_corr_limit
    drawdown_ok = r.get("max_drawdown", 0) >= c.drawdown_limit
    if adequate_activity and economics_positive and fold_ok and conc_ok and corr_ok and drawdown_ok:
        return "phase13a_candidate_for_paper_review"
    if economics_positive and corr_ok:
        if adequate_activity and drawdown_ok and (r.get("positive_wf_test_folds_pct", 0) >= 0.75 or r.get("best_day_concentration", 1) <= c.concentration_limit + c.narrow_watch_miss):
            return "phase13a_watchlist_needs_more_history"
        return "phase13a_positive_uncorrelated_research_signal"
    if r.get("net_pnl", 0) <= 0 or r.get("stress_pnl", 0) <= 0:
        return "phase13a_rejected_negative_stress"
    if r.get("validation_pnl", 0) <= 0:
        return "phase13a_rejected_negative_validation"
    if r.get("holdout_pnl", 0) <= 0:
        return "phase13a_rejected_negative_holdout"
    if not corr_ok:
        return "phase13a_rejected_high_correlation"
    if not adequate_activity:
        return "phase13a_rejected_low_activity"
    if not fold_ok:
        return "phase13a_rejected_fold_instability"
    if not conc_ok:
        return "phase13a_rejected_concentration"
    return "phase13a_rejected_fold_instability"


def _signal_evidence(r: dict[str, Any]) -> str:
    label = str(r.get("phase13a_label"))
    if label == "phase13a_candidate_for_paper_review":
        return "priority_research_signal_for_more_data"
    if label == "phase13a_watchlist_needs_more_history":
        return "priority_research_signal_for_more_data"
    if label == "phase13a_positive_uncorrelated_research_signal":
        return "positive_research_signal"
    if r.get("stress_pnl", 0) > 0:
        return "weak_research_signal"
    return "no_signal"


def _tradability(r: dict[str, Any]) -> str:
    label = str(r.get("phase13a_label"))
    if label == "phase13a_candidate_for_paper_review":
        return "review_packet_candidate"
    if label == "phase13a_watchlist_needs_more_history":
        return "watchlist_needs_more_history"
    if r.get("net_pnl", 0) <= 0 or r.get("stress_pnl", 0) <= 0:
        return "not_tradable_negative"
    if r.get("trades", 0) < 60 or r.get("active_days", 0) < 35:
        return "not_tradable_low_activity"
    if r.get("best_day_concentration", 1) > 0.15 or r.get("best_trade_concentration", 1) > 0.08:
        return "not_tradable_concentrated"
    return "not_tradable_fold_unstable"


def _research_track(r: dict[str, Any]) -> str:
    if r.get("phase13a_label") in {"phase13a_candidate_for_paper_review", "phase13a_watchlist_needs_more_history"}:
        return "priority_research_signal_for_more_data"
    if r.get("phase13a_label") == "phase13a_positive_uncorrelated_research_signal":
        return "parked_research_signal"
    return "parked_research_signal"


def _reasons(r: dict[str, Any], c: Phase13AConfig) -> str:
    checks = [
        ("negative stress", r.get("net_pnl", 0) <= 0 or r.get("stress_pnl", 0) <= 0),
        ("negative validation", r.get("validation_pnl", 0) <= 0),
        ("negative holdout", r.get("holdout_pnl", 0) <= 0),
        ("high correlation", r.get("average_correlation_to_registry", 1) > c.registry_avg_corr_limit or r.get("max_correlation_to_registry", 1) > c.registry_max_corr_limit),
        ("low activity", r.get("trades", 0) < c.min_trades or r.get("active_days", 0) < c.min_active_days or not (1 <= r.get("trades_per_active_day", 0) <= 3)),
        ("drawdown", r.get("max_drawdown", 0) < c.drawdown_limit),
        ("fold instability", r.get("walk_forward_stress_pnl", 0) <= 0 or r.get("positive_wf_test_folds_pct", 0) < 0.9 or r.get("worst_wf_test_fold", 0) < c.worst_fold_limit),
        ("concentration", r.get("best_day_concentration", 1) > c.concentration_limit or r.get("best_trade_concentration", 1) > c.trade_concentration_limit),
    ]
    return "; ".join(name for name, bad in checks if bad) or "survived Phase 13A diagnostic gates; review packet only"


def _fold_rows(trades: pd.DataFrame, spec: Phase13ASpec, sessions: list[str], c: Phase13AConfig) -> pd.DataFrame:
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


def _correlation_rows(candidates: pd.DataFrame, target: str) -> pd.DataFrame:
    avg_col = "average_correlation_to_registry" if target == "registry" else "average_correlation_to_portfolio_audit"
    max_col = "max_correlation_to_registry" if target == "registry" else "max_correlation_to_portfolio_audit"
    if candidates.empty:
        return pd.DataFrame(columns=["candidate_id", avg_col, max_col])
    return candidates[["candidate_id", "family", avg_col, max_col]].copy()


def _zero_metrics() -> dict[str, Any]:
    metrics = standard_zero_metrics(include_gross_waterfall=False)
    metrics.update({"gross_pnl": 0.0, "stop_hit_rate": 0.0, "target_hit_rate": 0.0, "time_stop_rate": 0.0, "walk_forward_test_pnl": 0.0})
    return metrics


def _corr(a: pd.Series, b: pd.Series) -> float:
    if len(a) < 2 or float(a.std()) == 0.0 or float(b.std()) == 0.0:
        return 0.0
    value = a.corr(b)
    return 0.0 if pd.isna(value) else float(value)


def serialize_phase13a_specs(specs: list[Phase13ASpec]) -> str:
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
