from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from .backtest import split_sessions
from .instruments import get_instrument
from .phase9a_volatility_compression_breakout import Phase9ASpec, compute_compression_features, generate_phase9a_signals


@dataclass(frozen=True)
class Phase9BConfig:
    max_specs: int = 48
    recent_sessions: int = 252
    timeframes: tuple[int, ...] = (5, 15)
    compression_methods: tuple[str, ...] = ("range_percentile", "atr_percentile", "realized_vol_percentile")
    lookbacks: tuple[int, ...] = (8, 12)
    directions: tuple[str, ...] = ("long_only", "short_only")
    entry_models: tuple[str, ...] = ("next_bar_open", "next_bar_close")
    min_minutes_between_entries: int = 30
    max_trades_per_day: int = 2
    avoid_first_minutes: int = 10
    time_stop_minutes: int = 45
    train_sessions: int = 75
    validation_sessions: int = 25
    test_sessions: int = 25
    step_sessions: int = 25
    min_folds: int = 3


def build_phase9b_specs(config: Phase9BConfig = Phase9BConfig()) -> list[Phase9ASpec]:
    specs: list[Phase9ASpec] = []
    for timeframe in config.timeframes:
        for method in config.compression_methods:
            for lookback in config.lookbacks:
                for direction in config.directions:
                    for entry_model in config.entry_models:
                        threshold = 0.25 if method == "range_percentile" else 0.20
                        target_r = 1.5 if lookback == config.lookbacks[0] else 2.0
                        gap = config.min_minutes_between_entries if timeframe == 5 else 60
                        specs.append(
                            Phase9ASpec(
                                timeframe=timeframe,
                                compression_method=method,
                                compression_lookback=lookback,
                                compression_threshold=threshold,
                                direction_mode=direction,
                                entry_model=entry_model,
                                stop_model="opposite_box_edge",
                                target_model="r_multiple_or_time_stop",
                                target_r=target_r,
                                time_stop_minutes=config.time_stop_minutes,
                                max_trades_per_day=config.max_trades_per_day,
                                min_minutes_between_entries=gap,
                                avoid_first_minutes=config.avoid_first_minutes,
                                avoid_10_00_10_30=False,
                            )
                        )
    return specs[: max(int(config.max_specs), 0)]


def assign_phase9b_time_bucket(ts: Any) -> str:
    minutes = _minute_of_day(pd.Timestamp(ts))
    if minutes < 10 * 60:
        return "09:30-10:00"
    if minutes < 10 * 60 + 30:
        return "10:00-10:30"
    if minutes < 11 * 60 + 30:
        return "10:30-11:30"
    if minutes < 13 * 60 + 30:
        return "11:30-13:30"
    return "13:30-15:45"


def compute_phase9b_trade_attribution(bars: pd.DataFrame, specs: list[Phase9ASpec], config: Phase9BConfig = Phase9BConfig()) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    sessions = sorted(bars["trading_session"].dropna().astype(str).unique().tolist())
    split_map = split_sessions(sessions)
    cache: dict[tuple[int, str, int, float], pd.DataFrame] = {}
    trade_frames: list[pd.DataFrame] = []
    fold_frames: list[pd.DataFrame] = []
    result_rows: list[dict[str, Any]] = []
    for spec in specs:
        key = (spec.timeframe, spec.compression_method, spec.compression_lookback, spec.compression_threshold)
        if key not in cache:
            cache[key] = compute_compression_features(bars, timeframe=spec.timeframe, method=spec.compression_method, lookback=spec.compression_lookback, threshold=spec.compression_threshold)
        featured = cache[key]
        signals = generate_phase9a_signals(featured, spec)
        trades = _simulate_attribution_trades(featured, signals, spec)
        if not trades.empty:
            trades["split"] = trades["trading_session"].astype(str).map(split_map)
            trade_frames.append(trades)
            fold_frames.append(_fold_rows(trades, spec, sessions, config))
        result_rows.append(_candidate_row(trades, spec, split_map))
    all_trades = pd.concat(trade_frames, ignore_index=True) if trade_frames else pd.DataFrame()
    all_folds = pd.concat(fold_frames, ignore_index=True) if fold_frames else pd.DataFrame()
    return all_trades, pd.DataFrame(result_rows), all_folds, pd.DataFrame([s.to_dict() for s in specs])


def run_phase9b_diagnostic(bars: pd.DataFrame, config: Phase9BConfig = Phase9BConfig()) -> dict[str, pd.DataFrame]:
    specs = build_phase9b_specs(config)
    trades, candidate_results, folds, spec_frame = compute_phase9b_trade_attribution(bars, specs, config)
    return {
        "trades": trades,
        "candidate_results": candidate_results,
        "folds": folds,
        "specs": spec_frame,
        "side_summary": group_phase9b_summary(trades, folds, "direction_mode"),
        "time_bucket_summary": group_phase9b_summary(trades, folds, "time_bucket"),
        "exit_reason_summary": group_phase9b_summary(trades, folds, "exit_reason"),
        "session_loss_summary": _session_loss_summary(trades),
        "mfe_mae_summary": group_phase9b_summary(trades, folds, "mfe_mae_bucket"),
        "entry_timing_diagnostic": group_phase9b_summary(trades, folds, "entry_model"),
        "stop_target_diagnostic": group_phase9b_summary(trades, folds, "stop_target_bucket"),
    }


def group_phase9b_summary(trades: pd.DataFrame, folds: pd.DataFrame, group_col: str) -> pd.DataFrame:
    if trades.empty or group_col not in trades.columns:
        return pd.DataFrame(columns=["group", "trades", "net_pnl", "stress_pnl"])
    rows = []
    for group, data in trades.groupby(group_col, dropna=False):
        rows.append({"group": str(group), **_metrics(data), **_fold_metrics(data)})
    return pd.DataFrame(rows).sort_values(["stress_pnl", "net_pnl"], ascending=[False, False]).reset_index(drop=True)


def make_phase9b_recommendation(result: dict[str, pd.DataFrame]) -> dict[str, Any]:
    candidates = result["candidate_results"]
    trades = result["trades"]
    if trades.empty or candidates.empty:
        return {"next_action": "kill_compression_and_pivot", "rationale": "Phase 9B produced no diagnostic trades."}
    best_stress = float(candidates["stress_pnl"].max())
    best_net = float(candidates["net_pnl"].max())
    side = result["side_summary"]
    time_buckets = result["time_bucket_summary"]
    side_edge = not side.empty and float(side.iloc[0]["stress_pnl"]) > -250.0
    localized_time = not time_buckets.empty and len(time_buckets) > 1 and float(time_buckets.iloc[-1]["stress_pnl"]) < 0 < float(time_buckets.iloc[0]["stress_pnl"])
    if best_stress > 0 or best_net > 0 or side_edge or localized_time:
        return {
            "next_action": "phase9c_targeted_retest_only",
            "rationale": "Phase 9B found at least one bounded diagnostic axis that is less-bad/positive; retest only that axis, not a broad expansion.",
            "best_net": round(best_net, 2),
            "best_stress": round(best_stress, 2),
            "top_side_bucket": side.iloc[0].to_dict() if not side.empty else {},
        }
    return {
        "next_action": "kill_compression_and_pivot_to_phase10a_overnight_range",
        "rationale": "No positive/near-positive side, timing, or geometry bucket survived diagnostic attribution; compression appears structurally weak in this implementation family.",
        "best_net": round(best_net, 2),
        "best_stress": round(best_stress, 2),
    }


def render_phase9b_report(result: dict[str, pd.DataFrame], recommendation: dict[str, Any], report_path: Path) -> str:
    candidates = result["candidate_results"]
    trades = result["trades"]
    lines = [
        "# Phase 9B MNQ VCB Failure Attribution",
        "",
        "Diagnostic only. No live trading, broker adapters, order routing, API-key storage, webhooks, automated execution, or candidate promotion.",
        "",
        "## Summary",
        "",
        f"- Specs evaluated: `{len(candidates)}`",
        f"- Trade rows: `{len(trades)}`",
        f"- Next action recommendation: `{recommendation.get('next_action')}`",
        f"- Rationale: {recommendation.get('rationale')}",
        "",
        "## Candidate Snapshot",
        "",
        "| Candidate | TF | Method | Direction | Entry | Trades | Net | Stress | Holdout | Avg MFE | Avg MAE | Stop % | Target % |",
        "| --- | ---: | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    if not candidates.empty:
        for _, row in candidates.sort_values(["stress_pnl", "net_pnl"], ascending=[False, False]).head(12).iterrows():
            lines.append(f"| `{row['candidate_id']}` | {int(row['timeframe'])} | {row['compression_method']} | {row['direction_mode']} | {row['entry_model']} | {int(row['trades'])} | ${float(row['net_pnl']):.2f} | ${float(row['stress_pnl']):.2f} | ${float(row['holdout_pnl']):.2f} | ${float(row['avg_mfe']):.2f} | ${float(row['avg_mae']):.2f} | {float(row['stop_hit_rate']) * 100:.1f}% | {float(row['target_hit_rate']) * 100:.1f}% |")
    for title, key in [("Side", "side_summary"), ("Time Bucket", "time_bucket_summary"), ("Exit Reason", "exit_reason_summary"), ("Entry Timing", "entry_timing_diagnostic"), ("Stop/Target Geometry", "stop_target_diagnostic")]:
        lines.extend(["", f"## {title} Attribution", "", _summary_table(result[key])])
    lines.extend([
        "",
        "## Outputs",
        "",
        "- `outputs/phase9b_trade_attribution.csv`",
        "- `outputs/phase9b_side_summary.csv`",
        "- `outputs/phase9b_time_bucket_summary.csv`",
        "- `outputs/phase9b_exit_reason_summary.csv`",
        "- `outputs/phase9b_session_loss_summary.csv`",
        "- `outputs/phase9b_mfe_mae_summary.csv`",
        "- `outputs/phase9b_entry_timing_diagnostic.csv`",
        "- `outputs/phase9b_stop_target_diagnostic.csv`",
        "- `outputs/phase9b_next_action_recommendation.json`",
        f"- `{report_path.as_posix()}`",
    ])
    return "\n".join(lines) + "\n"


def _simulate_attribution_trades(featured: pd.DataFrame, signals: list[dict[str, Any]], spec: Phase9ASpec) -> pd.DataFrame:
    if featured.empty or not signals:
        return pd.DataFrame()
    instrument = get_instrument("MNQ")
    day_map = {str(s): d.sort_values("timestamp").reset_index(drop=True) for s, d in featured.groupby("trading_session", sort=True)}
    rows: list[dict[str, Any]] = []
    counts: dict[str, int] = {}
    last_entry: dict[str, pd.Timestamp] = {}
    for signal in sorted(signals, key=lambda item: item["entry_time"]):
        session = str(signal["trading_session"])
        if counts.get(session, 0) >= spec.max_trades_per_day:
            continue
        entry_time = pd.Timestamp(signal["entry_time"])
        if session in last_entry and (entry_time - last_entry[session]).total_seconds() / 60.0 < spec.min_minutes_between_entries:
            continue
        day = day_map.get(session)
        if day is None:
            continue
        matches = day.index[day["timestamp"].eq(entry_time)].tolist()
        if not matches:
            continue
        trade = _simulate_one(day, matches[0], signal, spec, instrument)
        if trade is None:
            continue
        rows.append({**signal, **trade, **spec.to_dict()})
        counts[session] = counts.get(session, 0) + 1
        last_entry[session] = entry_time
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    out["time_bucket"] = out["entry_time"].map(assign_phase9b_time_bucket)
    out["mfe_mae_bucket"] = out["mfe_to_mae_ratio"].map(lambda v: "mfe_ge_mae" if float(v) >= 1 else "mae_dominates")
    out["stop_target_bucket"] = out.apply(_stop_target_bucket, axis=1)
    return out


def _simulate_one(day: pd.DataFrame, entry_pos: int, signal: dict[str, Any], spec: Phase9ASpec, instrument) -> dict[str, Any] | None:
    entry = day.iloc[entry_pos]
    entry_price = float(entry["close"] if spec.entry_model == "next_bar_close" else entry["open"])
    side = str(signal["side"])
    mult = 1 if side == "long" else -1
    stop = float(signal["box_low"] if side == "long" else signal["box_high"])
    raw_risk = (entry_price - stop) if side == "long" else (stop - entry_price)
    risk_points = max(raw_risk, instrument.tick_size * 8)
    target = entry_price + mult * risk_points * spec.target_r
    signal_close = _price_at(day, pd.Timestamp(signal["signal_time"]), "close")
    next_close = float(entry["close"])
    max_exit_time = pd.Timestamp(entry["timestamp"]) + pd.Timedelta(minutes=spec.time_stop_minutes)
    exit_price = float(entry["close"])
    exit_time = entry["timestamp"]
    exit_reason = "time_stop"
    ambiguity = 0
    mfe = 0.0
    mae = 0.0
    for pos in range(entry_pos, len(day)):
        row = day.iloc[pos]
        ts = pd.Timestamp(row["timestamp"])
        favorable = (float(row["high"]) - entry_price) if side == "long" else (entry_price - float(row["low"]))
        adverse = (entry_price - float(row["low"])) if side == "long" else (float(row["high"]) - entry_price)
        mfe = max(mfe, favorable * instrument.point_value)
        mae = max(mae, adverse * instrument.point_value)
        if ts >= max_exit_time or _minute_of_day(ts) >= 15 * 60 + 45:
            exit_price = float(row["close"])
            exit_time = ts
            exit_reason = "session_flatten" if _minute_of_day(ts) >= 15 * 60 + 45 else "time_stop"
            break
        stop_hit = float(row["low"]) <= stop if side == "long" else float(row["high"]) >= stop
        target_hit = float(row["high"]) >= target if side == "long" else float(row["low"]) <= target
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
    gross = (exit_price - entry_price) * mult * instrument.point_value
    return {
        "entry_price": round(entry_price, 4),
        "signal_close": round(signal_close, 4),
        "next_bar_close": round(next_close, 4),
        "entry_slippage_from_signal_close": round((entry_price - signal_close) * mult * instrument.point_value, 2),
        "next_close_slippage_from_signal_close": round((next_close - signal_close) * mult * instrument.point_value, 2),
        "exit_time": exit_time,
        "exit_price": round(exit_price, 4),
        "exit_reason": exit_reason,
        "stop_price": round(stop, 4),
        "target_price": round(target, 4),
        "risk_dollars": round(risk_points * instrument.point_value, 2),
        "gross_pnl": round(gross, 2),
        "net_pnl": round(gross - instrument.base_cost, 2),
        "stress_pnl": round(gross - instrument.stress_cost, 2),
        "mfe": round(mfe, 2),
        "mae": round(mae, 2),
        "mfe_to_mae_ratio": round(mfe / mae, 6) if mae else 999.0,
        "r_multiple": round(gross / (risk_points * instrument.point_value), 6) if risk_points else 0.0,
        "target_hit": int(exit_reason == "target"),
        "stop_hit": int(exit_reason in {"stop", "stop_same_bar_conservative"}),
        "time_stop": int(exit_reason in {"time_stop", "session_flatten"}),
        "same_bar_ambiguity": ambiguity,
    }


def _candidate_row(trades: pd.DataFrame, spec: Phase9ASpec, split_map: dict[Any, str]) -> dict[str, Any]:
    row = spec.to_dict()
    if trades.empty:
        row.update({"trades": 0, "net_pnl": 0.0, "stress_pnl": 0.0, "validation_pnl": 0.0, "holdout_pnl": 0.0, "avg_mfe": 0.0, "avg_mae": 0.0, "target_hit_rate": 0.0, "stop_hit_rate": 0.0})
        return row
    data = trades.copy()
    data["split"] = data["trading_session"].astype(str).map(split_map)
    metrics = _metrics(data)
    row.update({k: metrics[k] for k in ["trades", "net_pnl", "stress_pnl", "avg_mfe", "avg_mae", "target_hit_rate", "stop_hit_rate"]})
    row["validation_pnl"] = round(float(data.loc[data["split"].eq("validation"), "net_pnl"].sum()), 2)
    row["holdout_pnl"] = round(float(data.loc[data["split"].eq("holdout"), "net_pnl"].sum()), 2)
    return row


def _metrics(data: pd.DataFrame) -> dict[str, Any]:
    net = float(data["net_pnl"].sum()) if not data.empty else 0.0
    wins = data[data["net_pnl"] > 0]
    losses = data[data["net_pnl"] < 0]
    equity = data["net_pnl"].cumsum() if not data.empty else pd.Series(dtype=float)
    daily = data.groupby("trading_session")["net_pnl"].sum() if not data.empty else pd.Series(dtype=float)
    gross_profit = float(wins["net_pnl"].sum()) if not wins.empty else 0.0
    gross_loss = abs(float(losses["net_pnl"].sum())) if not losses.empty else 0.0
    return {
        "trades": int(len(data)),
        "net_pnl": round(net, 2),
        "stress_pnl": round(float(data["stress_pnl"].sum()) if not data.empty else 0.0, 2),
        "avg_pnl": round(float(data["net_pnl"].mean()) if not data.empty else 0.0, 2),
        "median_pnl": round(float(data["net_pnl"].median()) if not data.empty else 0.0, 2),
        "win_rate": round(float((data["net_pnl"] > 0).mean()) if not data.empty else 0.0, 6),
        "profit_factor": round(gross_profit / gross_loss, 6) if gross_loss else (999.0 if gross_profit else 0.0),
        "avg_win": round(float(wins["net_pnl"].mean()) if not wins.empty else 0.0, 2),
        "avg_loss": round(float(losses["net_pnl"].mean()) if not losses.empty else 0.0, 2),
        "max_drawdown": round(float((equity - equity.cummax()).min()) if not equity.empty else 0.0, 2),
        "validation_pnl": round(float(data.loc[data.get("split", pd.Series(index=data.index)).eq("validation"), "net_pnl"].sum()) if "split" in data else 0.0, 2),
        "holdout_pnl": round(float(data.loc[data.get("split", pd.Series(index=data.index)).eq("holdout"), "net_pnl"].sum()) if "split" in data else 0.0, 2),
        "best_day_concentration": round(_concentration(float(daily.max()) if not daily.empty else 0.0, net), 6),
        "best_trade_concentration": round(_concentration(float(data["net_pnl"].max()) if not data.empty else 0.0, net), 6),
        "avg_mfe": round(float(data["mfe"].mean()) if "mfe" in data and not data.empty else 0.0, 2),
        "avg_mae": round(float(data["mae"].mean()) if "mae" in data and not data.empty else 0.0, 2),
        "mfe_to_mae_ratio": round(float(data["mfe"].mean() / data["mae"].mean()) if "mfe" in data and data["mae"].mean() else 0.0, 6),
        "target_hit_rate": round(float(data["target_hit"].mean()) if "target_hit" in data and not data.empty else 0.0, 6),
        "stop_hit_rate": round(float(data["stop_hit"].mean()) if "stop_hit" in data and not data.empty else 0.0, 6),
        "time_stop_rate": round(float(data["time_stop"].mean()) if "time_stop" in data and not data.empty else 0.0, 6),
        "same_bar_ambiguity_rate": round(float(data["same_bar_ambiguity"].mean()) if "same_bar_ambiguity" in data and not data.empty else 0.0, 6),
    }


def _fold_metrics(data: pd.DataFrame) -> dict[str, Any]:
    if data.empty or "fold" not in data.columns:
        return {"walk_forward_stress_pnl": round(float(data["stress_pnl"].sum()) if "stress_pnl" in data else 0.0, 2), "positive_wf_folds_pct": 0.0}
    folds = data.groupby("fold")["stress_pnl"].sum()
    return {"walk_forward_stress_pnl": round(float(folds.sum()), 2), "positive_wf_folds_pct": round(float((folds > 0).mean()), 6)}


def _fold_rows(trades: pd.DataFrame, spec: Phase9ASpec, sessions: list[str], config: Phase9BConfig) -> pd.DataFrame:
    rows = []
    window = config.train_sessions + config.validation_sessions + config.test_sessions
    start = 0
    fold = 1
    while start + window <= len(sessions):
        test_sessions = sessions[start + config.train_sessions + config.validation_sessions : start + window]
        seg = trades[trades["trading_session"].astype(str).isin(test_sessions)].copy()
        if not seg.empty:
            seg["fold"] = fold
            rows.append(seg)
        fold += 1
        start += config.step_sessions
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


def _session_loss_summary(trades: pd.DataFrame) -> pd.DataFrame:
    if trades.empty:
        return pd.DataFrame()
    daily = trades.groupby("trading_session").agg(trades=("net_pnl", "size"), net_pnl=("net_pnl", "sum"), stress_pnl=("stress_pnl", "sum"), avg_mfe=("mfe", "mean"), avg_mae=("mae", "mean")).reset_index()
    return daily.sort_values("stress_pnl", ascending=True).head(25).reset_index(drop=True)


def _summary_table(df: pd.DataFrame) -> str:
    if df.empty:
        return "No rows."
    cols = [c for c in ["group", "trades", "net_pnl", "stress_pnl", "win_rate", "profit_factor", "avg_mfe", "avg_mae", "target_hit_rate", "stop_hit_rate", "same_bar_ambiguity_rate"] if c in df.columns]
    lines = ["| " + " | ".join(cols) + " |", "| " + " | ".join(["---"] * len(cols)) + " |"]
    for _, row in df[cols].head(12).iterrows():
        lines.append("| " + " | ".join(_fmt(row[c]) for c in cols) + " |")
    return "\n".join(lines)


def _stop_target_bucket(row: pd.Series) -> str:
    if int(row.get("target_hit", 0)):
        return "target_hit"
    if int(row.get("stop_hit", 0)) and float(row.get("mfe_to_mae_ratio", 0.0)) >= 1:
        return "stopped_after_favorable_move"
    if int(row.get("stop_hit", 0)):
        return "quick_or_adverse_stop"
    return "time_or_flatten"


def _price_at(day: pd.DataFrame, ts: pd.Timestamp, column: str) -> float:
    matches = day.index[day["timestamp"].eq(ts)].tolist()
    return float(day.iloc[matches[0]][column]) if matches else float(day.iloc[0][column])


def _minute_of_day(ts: pd.Timestamp) -> int:
    ts = pd.Timestamp(ts)
    return ts.hour * 60 + ts.minute


def _concentration(best: float, total: float) -> float:
    return float(max(best, 0.0) / total) if total > 0 else 1.0


def _fmt(value: Any) -> str:
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value)


def recommendation_to_json(recommendation: dict[str, Any]) -> str:
    return json.dumps(recommendation, indent=2, sort_keys=True, default=str)
