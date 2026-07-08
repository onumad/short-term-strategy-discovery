from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from .backtest import split_sessions
from .instruments import get_instrument
from .phase4a import resample_signal_bars


@dataclass(frozen=True)
class Phase9AConfig:
    max_specs: int = 24
    recent_sessions: int = 252
    timeframes: tuple[int, ...] = (5, 15)
    compression_methods: tuple[str, ...] = ("range_percentile", "atr_percentile", "realized_vol_percentile")
    compression_lookbacks: tuple[int, ...] = (8, 12)
    compression_thresholds: tuple[float, ...] = (0.25,)
    direction_modes: tuple[str, ...] = ("long_only", "short_only", "both_sides")
    target_rs: tuple[float, ...] = (1.5, 2.0)
    max_trades_per_day_values: tuple[int, ...] = (1, 2)
    min_minutes_between_entries: int = 30
    avoid_first_minutes_values: tuple[int, ...] = (10,)
    avoid_10_00_10_30_values: tuple[bool, ...] = (False, True)
    time_stop_minutes: int = 45
    train_sessions: int = 75
    validation_sessions: int = 25
    test_sessions: int = 25
    step_sessions: int = 25
    min_folds: int = 3
    min_trades: int = 120
    min_active_session_pct: float = 0.35
    concentration_limit: float = 0.15
    trade_concentration_limit: float = 0.08
    drawdown_limit: float = -6_000.0
    worst_fold_limit: float = -1_500.0
    flatten_time: str = "15:45"


@dataclass(frozen=True)
class Phase9ASpec:
    timeframe: int
    compression_method: str
    compression_lookback: int
    compression_threshold: float
    direction_mode: str
    entry_model: str
    stop_model: str
    target_model: str
    target_r: float
    time_stop_minutes: int
    max_trades_per_day: int
    min_minutes_between_entries: int
    avoid_first_minutes: int
    avoid_10_00_10_30: bool

    @property
    def candidate_id(self) -> str:
        macro = "avoid1000" if self.avoid_10_00_10_30 else "keep1000"
        return (
            f"MNQ_vcb_tf{self.timeframe}_{self.compression_method}_lb{self.compression_lookback}_q{str(self.compression_threshold).replace('.', '')}_"
            f"{self.direction_mode}_target{str(self.target_r).replace('.', '')}R_mt{self.max_trades_per_day}_gap{self.min_minutes_between_entries}_first{self.avoid_first_minutes}_{macro}"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "instrument": "MNQ",
            "family": "volatility_compression_breakout",
            "timeframe": self.timeframe,
            "compression_method": self.compression_method,
            "compression_lookback": self.compression_lookback,
            "compression_threshold": self.compression_threshold,
            "direction_mode": self.direction_mode,
            "entry_model": self.entry_model,
            "stop_model": self.stop_model,
            "target_model": self.target_model,
            "target_r": self.target_r,
            "time_stop_minutes": self.time_stop_minutes,
            "max_trades_per_day": self.max_trades_per_day,
            "min_minutes_between_entries": self.min_minutes_between_entries,
            "avoid_first_minutes": self.avoid_first_minutes,
            "avoid_10_00_10_30": self.avoid_10_00_10_30,
            "notes": "Phase 9A research-only deterministic MNQ volatility compression breakout spec; no paper/live promotion.",
        }


def build_phase9a_specs(config: Phase9AConfig = Phase9AConfig()) -> list[Phase9ASpec]:
    specs: list[Phase9ASpec] = []
    for timeframe in config.timeframes:
        for method in config.compression_methods:
            for lookback in config.compression_lookbacks:
                for threshold in config.compression_thresholds:
                    for direction in config.direction_modes:
                        for target_r in config.target_rs:
                            for max_trades in config.max_trades_per_day_values:
                                for avoid_first in config.avoid_first_minutes_values:
                                    for avoid_macro in config.avoid_10_00_10_30_values:
                                        specs.append(
                                            Phase9ASpec(
                                                timeframe=timeframe,
                                                compression_method=method,
                                                compression_lookback=lookback,
                                                compression_threshold=threshold,
                                                direction_mode=direction,
                                                entry_model="next_bar_open",
                                                stop_model="opposite_box_edge",
                                                target_model="r_multiple_or_time_stop",
                                                target_r=target_r,
                                                time_stop_minutes=config.time_stop_minutes,
                                                max_trades_per_day=max_trades,
                                                min_minutes_between_entries=config.min_minutes_between_entries,
                                                avoid_first_minutes=avoid_first,
                                                avoid_10_00_10_30=avoid_macro,
                                            )
                                        )
    return specs[: max(int(config.max_specs), 0)]


def compute_compression_features(bars: pd.DataFrame, *, timeframe: int, method: str, lookback: int, threshold: float) -> pd.DataFrame:
    rth = bars[bars.get("session_segment", "RTH").eq("RTH") if "session_segment" in bars.columns else pd.Series(True, index=bars.index)].copy()
    rth["timestamp"] = pd.to_datetime(rth["timestamp"], utc=True).dt.tz_convert("America/New_York")
    signal = resample_signal_bars(rth.sort_values(["trading_session", "timestamp"]), timeframe)
    if signal.empty:
        return signal
    out = signal.sort_values(["trading_session", "timestamp"]).copy()
    out["bar_range"] = out["high"].astype(float) - out["low"].astype(float)
    prior_close = out.groupby("trading_session")["close"].shift(1)
    tr = pd.concat([(out["high"] - out["low"]).abs(), (out["high"] - prior_close).abs(), (out["low"] - prior_close).abs()], axis=1).max(axis=1)
    out["atr"] = tr.groupby(out["trading_session"]).transform(lambda s: s.rolling(lookback, min_periods=max(3, lookback // 2)).mean())
    returns = out.groupby("trading_session")["close"].pct_change()
    out["realized_vol"] = returns.groupby(out["trading_session"]).transform(lambda s: s.rolling(lookback, min_periods=max(3, lookback // 2)).std())
    metric = {"range_percentile": "bar_range", "atr_percentile": "atr", "realized_vol_percentile": "realized_vol"}[method]
    out["compression_metric"] = out[metric]
    out["compression_cutoff"] = out.groupby("trading_session")["compression_metric"].transform(lambda s: s.shift(1).rolling(lookback, min_periods=max(3, lookback // 2)).quantile(threshold))
    out["is_compressed"] = out["compression_metric"].shift(1).lt(out["compression_cutoff"])
    box_min_periods = max(3, lookback // 2)
    out["box_high"] = out.groupby("trading_session")["high"].transform(lambda s: s.shift(1).rolling(lookback, min_periods=box_min_periods).max())
    out["box_low"] = out.groupby("trading_session")["low"].transform(lambda s: s.shift(1).rolling(lookback, min_periods=box_min_periods).min())
    opening = out[out["bar_index"] < max(1, 30 // timeframe)].groupby("trading_session").agg(opening_high=("high", "max"), opening_low=("low", "min"))
    out["opening_midpoint"] = out["trading_session"].map((opening["opening_high"] + opening["opening_low"]) / 2.0)
    return out.reset_index(drop=True)


def generate_phase9a_signals(featured: pd.DataFrame, spec: Phase9ASpec) -> list[dict[str, Any]]:
    if featured.empty:
        return []
    signals: list[dict[str, Any]] = []
    for _, day in featured.groupby("trading_session", sort=True):
        day = day.sort_values("timestamp").reset_index(drop=True)
        for i in range(1, len(day) - 1):
            row = day.iloc[i]
            minutes = _minute_of_day(row["timestamp"])
            if minutes < 9 * 60 + 30 + spec.avoid_first_minutes:
                continue
            if spec.avoid_10_00_10_30 and 10 * 60 <= minutes < 10 * 60 + 30:
                continue
            if not bool(row.get("is_compressed", False)) or pd.isna(row.get("box_high")) or pd.isna(row.get("box_low")):
                continue
            box_high = float(row["box_high"])
            box_low = float(row["box_low"])
            if box_high <= box_low:
                continue
            close = float(row["close"])
            vwap = float(row.get("vwap", close))
            midpoint = float(row.get("opening_midpoint", close)) if not pd.isna(row.get("opening_midpoint", close)) else close
            next_row = day.iloc[i + 1]
            if spec.direction_mode in {"long_only", "both_sides"} and close > box_high and close >= vwap and close >= midpoint:
                signals.append(_signal(row, next_row, spec, "long", box_high, box_low))
            if spec.direction_mode in {"short_only", "both_sides"} and close < box_low and close <= vwap and close <= midpoint:
                signals.append(_signal(row, next_row, spec, "short", box_high, box_low))
    return signals


def simulate_phase9a_trades(featured: pd.DataFrame, signals: list[dict[str, Any]], spec: Phase9ASpec) -> pd.DataFrame:
    if not signals or featured.empty:
        return pd.DataFrame()
    instrument = get_instrument("MNQ")
    by_session = {str(session): day.sort_values("timestamp").reset_index(drop=True) for session, day in featured.groupby("trading_session", sort=True)}
    rows: list[dict[str, Any]] = []
    last_entry_by_session: dict[str, pd.Timestamp] = {}
    counts: dict[str, int] = {}
    for signal in sorted(signals, key=lambda item: item["entry_time"]):
        session = str(signal["trading_session"])
        if counts.get(session, 0) >= spec.max_trades_per_day:
            continue
        last_entry = last_entry_by_session.get(session)
        entry_time = pd.Timestamp(signal["entry_time"])
        if last_entry is not None and (entry_time - last_entry).total_seconds() / 60.0 < spec.min_minutes_between_entries:
            continue
        day = by_session.get(session)
        if day is None:
            continue
        matches = day.index[day["timestamp"].eq(entry_time)].tolist()
        if not matches:
            continue
        trade = _simulate_trade(day, matches[0], signal, spec, instrument)
        if trade is None:
            continue
        rows.append({**signal, **trade, "candidate_id": spec.candidate_id})
        counts[session] = counts.get(session, 0) + 1
        last_entry_by_session[session] = entry_time
    return pd.DataFrame(rows)


def evaluate_phase9a_candidates(bars: pd.DataFrame, specs: list[Phase9ASpec], config: Phase9AConfig = Phase9AConfig()) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    if bars.empty:
        raise ValueError("Phase 9A requires non-empty MNQ bars")
    sessions = sorted(bars["trading_session"].dropna().astype(str).unique().tolist())
    split_map = split_sessions(sessions)
    features_cache: dict[tuple[int, str, int, float], pd.DataFrame] = {}
    results: list[dict[str, Any]] = []
    logs: list[pd.DataFrame] = []
    folds: list[pd.DataFrame] = []
    daily: list[pd.DataFrame] = []
    concentration_rows: list[dict[str, Any]] = []
    for spec in specs:
        key = (spec.timeframe, spec.compression_method, spec.compression_lookback, spec.compression_threshold)
        if key not in features_cache:
            features_cache[key] = compute_compression_features(bars, timeframe=spec.timeframe, method=spec.compression_method, lookback=spec.compression_lookback, threshold=spec.compression_threshold)
        trades = simulate_phase9a_trades(features_cache[key], generate_phase9a_signals(features_cache[key], spec), spec)
        results.append(_summarize_spec(spec, trades, sessions, split_map, config))
        if not trades.empty:
            logs.append(trades)
            folds.append(_fold_rows(spec, trades, sessions, config))
            daily.append(_daily_rows(spec, trades))
            concentration_rows.extend(_concentration_rows(spec, trades))
    result_frame = pd.DataFrame(results)
    if not result_frame.empty:
        result_frame["_priority"] = result_frame["phase9a_label"].map(_label_priority).fillna(0)
        result_frame = result_frame.sort_values(["_priority", "phase9a_score", "walk_forward_stress_pnl", "holdout_pnl"], ascending=[False, False, False, False]).drop(columns=["_priority"]).reset_index(drop=True)
        result_frame.insert(0, "phase9a_rank", range(1, len(result_frame) + 1))
    return (
        result_frame,
        pd.concat(logs, ignore_index=True) if logs else pd.DataFrame(),
        pd.concat(folds, ignore_index=True) if folds else pd.DataFrame(),
        pd.concat(daily, ignore_index=True) if daily else pd.DataFrame(),
        pd.DataFrame(concentration_rows),
    )


def render_phase9a_report(results: pd.DataFrame, config: Phase9AConfig, *, results_path: Path, trade_logs_path: Path, folds_path: Path, daily_path: Path, concentration_path: Path, specs_path: Path, report_path: Path, run_artifact_dir: Path | None = None) -> str:
    label_counts = results["phase9a_label"].value_counts().to_dict() if not results.empty else {}
    lines = [
        "# Phase 9A MNQ Volatility Compression Breakout",
        "",
        "Generated by: `./.venv/Scripts/python.exe scripts/run_phase9a_mnq_volatility_compression_breakout.py`",
        "",
        "## Scope And Guardrails",
        "",
        "- Research/simulation only. No live trading, broker adapters, order routing, API-key storage, webhooks, or automated execution were added.",
        "- Phase 9A tests a bounded deterministic MNQ volatility-compression breakout family after the Phase 8M VWAP branch failed.",
        "- Candidate labels are research labels only; no paper-trading promotion is made here.",
        "",
        "## Summary",
        "",
        f"- Specs evaluated: `{len(results)}`",
        f"- Label counts: `{label_counts}`",
        "",
        "| Rank | Candidate | Label | Score | TF | Method | Direction | Trades | Active % | Net | Stress | Val | Holdout | WF Stress | Pos Folds | DD | Day Conc. | Trade Conc. | Notes |",
        "| ---: | --- | --- | ---: | ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for _, row in results.head(20).iterrows():
        lines.append(f"| {int(row['phase9a_rank'])} | `{row['candidate_id']}` | {row['phase9a_label']} | {float(row['phase9a_score']):.2f} | {int(row['timeframe'])} | {row['compression_method']} | {row['direction_mode']} | {int(row['trades'])} | {float(row['active_days_pct']) * 100:.1f}% | ${float(row['net_pnl']):.2f} | ${float(row['stress_pnl']):.2f} | ${float(row['validation_pnl']):.2f} | ${float(row['holdout_pnl']):.2f} | ${float(row['walk_forward_stress_pnl']):.2f} | {float(row['positive_wf_test_folds_pct']) * 100:.1f}% | ${float(row['max_drawdown']):.2f} | {float(row['best_day_concentration']) * 100:.1f}% | {float(row['best_trade_concentration']) * 100:.1f}% | {row['reject_reasons']} |")
    lines.extend([
        "",
        "## Decision Rule",
        "",
        "- `phase9a_candidate_for_paper_review` means a row survived this bounded diagnostic; it still is not paper/live approval.",
        "- `phase9a_watchlist_needs_more_history` means aggregate behavior is positive but at least one robustness gate remains weak.",
        "- Rejected labels identify the dominant failure class: negative stress, fold instability, concentration, low activity, or drawdown.",
        "",
        "## Outputs",
        "",
        f"- Results CSV: `{results_path.as_posix()}`",
        f"- Trade logs CSV: `{trade_logs_path.as_posix()}`",
        f"- Walk-forward folds CSV: `{folds_path.as_posix()}`",
        f"- Daily PnL CSV: `{daily_path.as_posix()}`",
        f"- Concentration diagnostics CSV: `{concentration_path.as_posix()}`",
        f"- Strategy specs JSON: `{specs_path.as_posix()}`",
        f"- Report: `{report_path.as_posix()}`",
    ])
    if run_artifact_dir is not None:
        lines.append(f"- Run-scoped artifacts: `{run_artifact_dir.as_posix()}`")
    lines.extend(["", "## Repro Command", "", "```bash", "./.venv/Scripts/python.exe scripts/run_phase9a_mnq_volatility_compression_breakout.py", "```", ""])
    return "\n".join(lines)


def _signal(row: pd.Series, next_row: pd.Series, spec: Phase9ASpec, side: str, box_high: float, box_low: float) -> dict[str, Any]:
    return {"signal_time": row["timestamp"], "entry_time": next_row["timestamp"], "trading_session": str(row["trading_session"]), "side": side, "box_high": box_high, "box_low": box_low, "entry_model": spec.entry_model, "timeframe": spec.timeframe, "compression_method": spec.compression_method, "direction_mode": spec.direction_mode}


def _simulate_trade(day: pd.DataFrame, entry_pos: int, signal: dict[str, Any], spec: Phase9ASpec, instrument) -> dict[str, Any] | None:
    if entry_pos >= len(day):
        return None
    entry = day.iloc[entry_pos]
    entry_price = float(entry["open"])
    side = str(signal["side"])
    side_mult = 1 if side == "long" else -1
    box_high = float(signal["box_high"])
    box_low = float(signal["box_low"])
    if side == "long":
        stop = box_low
        risk_points = max(entry_price - stop, instrument.tick_size * 8)
        target = entry_price + risk_points * spec.target_r
    else:
        stop = box_high
        risk_points = max(stop - entry_price, instrument.tick_size * 8)
        target = entry_price - risk_points * spec.target_r
    max_exit_time = pd.Timestamp(entry["timestamp"]) + pd.Timedelta(minutes=spec.time_stop_minutes)
    flatten_minutes = _hhmm_to_minutes("15:45")
    exit_price = float(entry["close"])
    exit_time = entry["timestamp"]
    exit_reason = "time_stop"
    ambiguity = 0
    for pos in range(entry_pos, len(day)):
        row = day.iloc[pos]
        ts = pd.Timestamp(row["timestamp"])
        if ts >= max_exit_time or _minute_of_day(ts) >= flatten_minutes:
            exit_price = float(row["close"])
            exit_time = ts
            exit_reason = "time_stop"
            break
        if side == "long":
            stop_hit = float(row["low"]) <= stop
            target_hit = float(row["high"]) >= target
        else:
            stop_hit = float(row["high"]) >= stop
            target_hit = float(row["low"]) <= target
        if stop_hit:
            exit_price = stop
            exit_time = ts
            exit_reason = "stop_same_bar_conservative" if target_hit else "stop"
            ambiguity = int(target_hit)
            break
        if target_hit:
            exit_price = target
            exit_time = ts
            exit_reason = "target"
            break
    gross = (exit_price - entry_price) * side_mult * instrument.point_value
    return {"entry_price": entry_price, "exit_time": exit_time, "exit_price": round(exit_price, 4), "exit_reason": exit_reason, "stop_price": round(stop, 4), "target_price": round(target, 4), "gross_pnl": round(gross, 2), "net_pnl": round(gross - instrument.base_cost, 2), "stress_pnl": round(gross - instrument.stress_cost, 2), "risk_dollars": round(risk_points * instrument.point_value, 2), "same_bar_ambiguity": ambiguity}


def _summarize_spec(spec: Phase9ASpec, trades: pd.DataFrame, sessions: list[str], split_map: dict[Any, str], config: Phase9AConfig) -> dict[str, Any]:
    row = spec.to_dict()
    if trades.empty:
        row.update(_zero_metrics())
    else:
        ordered = trades.sort_values("entry_time").copy()
        ordered["split"] = ordered["trading_session"].map(split_map)
        net = float(ordered["net_pnl"].sum())
        daily = ordered.groupby("trading_session")["net_pnl"].sum()
        equity = ordered["net_pnl"].cumsum()
        fold_summary = _fold_summary(_fold_rows(spec, ordered, sessions, config))
        row.update({"trades": int(len(ordered)), "active_days": int(ordered["trading_session"].nunique()), "active_days_pct": round(_safe_div(ordered["trading_session"].nunique(), len(sessions)), 6), "trades_per_active_day": round(_safe_div(len(ordered), ordered["trading_session"].nunique()), 6), "net_pnl": round(net, 2), "stress_pnl": round(float(ordered["stress_pnl"].sum()), 2), "validation_pnl": round(float(ordered.loc[ordered["split"].eq("validation"), "net_pnl"].sum()), 2), "holdout_pnl": round(float(ordered.loc[ordered["split"].eq("holdout"), "net_pnl"].sum()), 2), "max_drawdown": round(float((equity - equity.cummax()).min()), 2), "best_day_concentration": round(_concentration(float(daily.max()), net), 6), "best_trade_concentration": round(_concentration(float(ordered["net_pnl"].max()), net), 6), **fold_summary})
    row["phase9a_score"] = round(_score(row), 4)
    row["phase9a_label"] = _label(row, config)
    row["reject_reasons"] = _notes(row, config)
    return row


def _fold_rows(spec: Phase9ASpec, trades: pd.DataFrame, sessions: list[str], config: Phase9AConfig) -> pd.DataFrame:
    rows = []
    window = config.train_sessions + config.validation_sessions + config.test_sessions
    start = 0
    fold = 1
    while start + window <= len(sessions):
        test_sessions = sessions[start + config.train_sessions + config.validation_sessions : start + window]
        seg = trades[trades["trading_session"].astype(str).isin(test_sessions)] if not trades.empty else trades
        rows.append({"candidate_id": spec.candidate_id, "fold": fold, "segment_start": test_sessions[0], "segment_end": test_sessions[-1], **_segment_score(seg)})
        fold += 1
        start += config.step_sessions
    return pd.DataFrame(rows)


def _segment_score(trades: pd.DataFrame) -> dict[str, Any]:
    if trades.empty:
        return {"trades": 0, "net_pnl": 0.0, "stress_pnl": 0.0, "max_drawdown": 0.0, "best_day_concentration": 0.0, "best_trade_concentration": 0.0}
    net = float(trades["net_pnl"].sum())
    equity = trades["net_pnl"].cumsum()
    daily = trades.groupby("trading_session")["net_pnl"].sum()
    return {"trades": int(len(trades)), "net_pnl": round(net, 2), "stress_pnl": round(float(trades["stress_pnl"].sum()), 2), "max_drawdown": round(float((equity - equity.cummax()).min()), 2), "best_day_concentration": round(_concentration(float(daily.max()), net), 6), "best_trade_concentration": round(_concentration(float(trades["net_pnl"].max()), net), 6)}


def _fold_summary(folds: pd.DataFrame) -> dict[str, Any]:
    if folds.empty:
        return {"walk_forward_test_pnl": 0.0, "walk_forward_stress_pnl": 0.0, "positive_wf_test_folds_pct": 0.0, "worst_wf_test_fold": 0.0, "walk_forward_folds": 0}
    positive = int((folds["net_pnl"] > 0).sum())
    return {"walk_forward_test_pnl": round(float(folds["net_pnl"].sum()), 2), "walk_forward_stress_pnl": round(float(folds["stress_pnl"].sum()), 2), "positive_wf_test_folds_pct": round(_safe_div(positive, len(folds)), 6), "worst_wf_test_fold": round(float(folds["net_pnl"].min()), 2), "walk_forward_folds": int(len(folds))}


def _daily_rows(spec: Phase9ASpec, trades: pd.DataFrame) -> pd.DataFrame:
    return trades.groupby("trading_session").agg(candidate_id=("candidate_id", "first"), trades=("net_pnl", "size"), net_pnl=("net_pnl", "sum"), stress_pnl=("stress_pnl", "sum")).reset_index().rename(columns={"trading_session": "session_date"})


def _concentration_rows(spec: Phase9ASpec, trades: pd.DataFrame) -> list[dict[str, Any]]:
    net = float(trades["net_pnl"].sum())
    rows = []
    for scope, col in [("day", "trading_session"), ("side", "side"), ("exit_reason", "exit_reason")]:
        for key, group in trades.groupby(col):
            rows.append({"candidate_id": spec.candidate_id, "scope": scope, "bucket": str(key), "pnl": round(float(group["net_pnl"].sum()), 2), "trades": int(len(group)), "concentration": round(_concentration(float(group["net_pnl"].sum()), net), 6)})
    return rows


def _score(row: dict[str, Any]) -> float:
    return float(row.get("stress_pnl", 0.0)) / 100.0 + float(row.get("walk_forward_stress_pnl", 0.0)) / 100.0 + float(row.get("positive_wf_test_folds_pct", 0.0)) * 20.0 - max(float(row.get("best_day_concentration", 1.0)) - 0.15, 0.0) * 100.0 - max(float(row.get("best_trade_concentration", 1.0)) - 0.08, 0.0) * 100.0


def _label(row: dict[str, Any], config: Phase9AConfig) -> str:
    if int(row.get("trades", 0)) < config.min_trades or float(row.get("active_days_pct", 0.0)) < config.min_active_session_pct:
        return "phase9a_rejected_low_activity"
    if float(row.get("net_pnl", 0.0)) <= 0 or float(row.get("stress_pnl", 0.0)) <= 0:
        return "phase9a_rejected_negative_stress"
    if float(row.get("max_drawdown", 0.0)) < config.drawdown_limit:
        return "phase9a_rejected_drawdown"
    if int(row.get("walk_forward_folds", 0)) < config.min_folds or float(row.get("walk_forward_stress_pnl", 0.0)) <= 0 or float(row.get("positive_wf_test_folds_pct", 0.0)) < 1.0 or float(row.get("worst_wf_test_fold", 0.0)) < config.worst_fold_limit:
        return "phase9a_rejected_fold_instability"
    if float(row.get("best_day_concentration", 1.0)) > config.concentration_limit or float(row.get("best_trade_concentration", 1.0)) > config.trade_concentration_limit:
        return "phase9a_rejected_concentration"
    return "phase9a_candidate_for_paper_review"


def _notes(row: dict[str, Any], config: Phase9AConfig) -> str:
    notes = []
    if int(row.get("trades", 0)) < config.min_trades: notes.append("low activity")
    if float(row.get("active_days_pct", 0.0)) < config.min_active_session_pct: notes.append("low active-day coverage")
    if float(row.get("net_pnl", 0.0)) <= 0: notes.append("negative net PnL")
    if float(row.get("stress_pnl", 0.0)) <= 0: notes.append("negative stress PnL")
    if float(row.get("validation_pnl", 0.0)) <= 0: notes.append("negative validation split")
    if float(row.get("holdout_pnl", 0.0)) <= 0: notes.append("negative holdout split")
    if float(row.get("positive_wf_test_folds_pct", 0.0)) < 1.0: notes.append("not every walk-forward test fold is positive")
    if float(row.get("best_day_concentration", 1.0)) > config.concentration_limit: notes.append("one-day concentration risk")
    if float(row.get("best_trade_concentration", 1.0)) > config.trade_concentration_limit: notes.append("one-trade concentration risk")
    return "; ".join(notes) if notes else "survives bounded Phase 9A diagnostic; not paper/live approval"


def _zero_metrics() -> dict[str, Any]:
    return {"trades": 0, "active_days": 0, "active_days_pct": 0.0, "trades_per_active_day": 0.0, "net_pnl": 0.0, "stress_pnl": 0.0, "validation_pnl": 0.0, "holdout_pnl": 0.0, "max_drawdown": 0.0, "best_day_concentration": 0.0, "best_trade_concentration": 0.0, **_fold_summary(pd.DataFrame())}


def _label_priority(label: str) -> int:
    return {"phase9a_candidate_for_paper_review": 4, "phase9a_watchlist_needs_more_history": 3, "phase9a_rejected_concentration": 2, "phase9a_rejected_fold_instability": 1}.get(str(label), 0)


def _minute_of_day(ts: Any) -> int:
    t = pd.Timestamp(ts)
    return t.hour * 60 + t.minute


def _hhmm_to_minutes(value: str) -> int:
    hour, minute = value.split(":")
    return int(hour) * 60 + int(minute)


def _concentration(best: float, total: float) -> float:
    if total <= 0:
        return 1.0
    return float(max(best, 0.0) / total)


def _safe_div(numerator: float, denominator: float) -> float:
    return float(numerator / denominator) if denominator else 0.0


def specs_to_json(specs: list[Phase9ASpec]) -> str:
    return json.dumps([spec.to_dict() for spec in specs], indent=2, sort_keys=True)
