from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from .backtest import split_sessions
from .instruments import get_instrument
from .phase9a_volatility_compression_breakout import compute_compression_features


@dataclass(frozen=True)
class Phase9CConfig:
    max_specs: int = 48
    recent_sessions: int = 252
    timeframes: tuple[int, ...] = (5, 15)
    compression_methods: tuple[str, ...] = ("range_percentile", "atr_percentile", "realized_vol_percentile")
    time_windows: tuple[str, ...] = ("core_midday", "extended_midday")
    entry_models: tuple[str, ...] = ("next_bar_open", "close_confirm_fill_next_open")
    exit_models: tuple[str, ...] = ("capped_opposite_box_stop_time_exit", "close_back_inside_box_invalidation_with_hard_cap")
    compression_threshold: float = 0.20
    target_r: float = 2.0
    atr_cap_multiple: float = 1.0
    buffer_ticks: int = 2
    max_trades_per_day: int = 2
    train_sessions: int = 75
    validation_sessions: int = 25
    test_sessions: int = 25
    step_sessions: int = 25
    min_trades: int = 80
    min_active_days: int = 40
    drawdown_limit: float = -6_000.0
    worst_fold_limit: float = -1_500.0
    concentration_limit: float = 0.15
    trade_concentration_limit: float = 0.08
    quick_stop_baseline_rate: float = 0.12


@dataclass(frozen=True)
class Phase9CSpec:
    timeframe: int
    compression_method: str
    compression_lookback: int
    compression_threshold: float
    time_window: str
    entry_start: str
    entry_end: str
    is_primary_eligible: bool
    entry_model: str
    exit_model: str
    direction_mode: str = "short_only"
    target_r: float = 2.0
    atr_cap_multiple: float = 1.0
    buffer_ticks: int = 2
    max_trades_per_day: int = 2
    min_minutes_between_entries: int = 30
    time_stop_minutes: int = 30

    @property
    def candidate_id(self) -> str:
        return (
            f"MNQ_9c_vcb_tf{self.timeframe}_{self.compression_method}_lb{self.compression_lookback}_q02_"
            f"short_{self.time_window}_{self.entry_model}_{self.exit_model}"
        )

    def to_dict(self) -> dict[str, Any]:
        return {"candidate_id": self.candidate_id, **self.__dict__, "instrument": "MNQ", "family": "volatility_compression_breakout"}


def build_phase9c_specs(config: Phase9CConfig = Phase9CConfig()) -> list[Phase9CSpec]:
    specs: list[Phase9CSpec] = []
    for timeframe in config.timeframes:
        lookback = 8 if timeframe == 5 else 12
        gap = 30 if timeframe == 5 else 60
        time_stop = 30 if timeframe == 5 else 45
        for method in config.compression_methods:
            for window in config.time_windows:
                start, end = ("10:30", "13:30") if window == "core_midday" else ("10:00", "13:30")
                for entry_model in config.entry_models:
                    for exit_model in config.exit_models:
                        specs.append(
                            Phase9CSpec(
                                timeframe=timeframe,
                                compression_method=method,
                                compression_lookback=lookback,
                                compression_threshold=config.compression_threshold,
                                time_window=window,
                                entry_start=start,
                                entry_end=end,
                                is_primary_eligible=window == "core_midday",
                                entry_model=entry_model,
                                exit_model=exit_model,
                                target_r=config.target_r,
                                atr_cap_multiple=config.atr_cap_multiple,
                                buffer_ticks=config.buffer_ticks,
                                max_trades_per_day=config.max_trades_per_day,
                                min_minutes_between_entries=gap,
                                time_stop_minutes=time_stop,
                            )
                        )
    return specs[: max(int(config.max_specs), 0)]


def compute_phase9c_features(bars: pd.DataFrame, spec: Phase9CSpec) -> pd.DataFrame:
    return compute_compression_features(bars, timeframe=spec.timeframe, method=spec.compression_method, lookback=spec.compression_lookback, threshold=spec.compression_threshold)


def generate_phase9c_signals(features: pd.DataFrame, spec: Phase9CSpec) -> list[dict[str, Any]]:
    if features.empty:
        return []
    signals: list[dict[str, Any]] = []
    start = _hhmm(spec.entry_start)
    end = _hhmm(spec.entry_end)
    for _, day in features.groupby("trading_session", sort=True):
        day = day.sort_values("timestamp").reset_index(drop=True)
        for i in range(1, len(day) - 2):
            row = day.iloc[i]
            minute = _minute(row["timestamp"])
            if minute < start or minute >= end:
                continue
            if not bool(row.get("is_compressed", False)) or pd.isna(row.get("box_low")) or pd.isna(row.get("box_high")):
                continue
            if float(row["box_high"]) <= float(row["box_low"]):
                continue
            if float(row["close"]) >= float(row["box_low"]):
                continue
            entry_idx = i + 1
            confirmation_time = row["timestamp"]
            if spec.entry_model == "close_confirm_fill_next_open":
                confirm = day.iloc[i + 1]
                if float(confirm["close"]) >= float(row["box_low"]):
                    continue
                confirmation_time = confirm["timestamp"]
                entry_idx = i + 2
            if entry_idx >= len(day):
                continue
            entry_row = day.iloc[entry_idx]
            signals.append({"signal_time": row["timestamp"], "confirmation_time": confirmation_time, "entry_time": entry_row["timestamp"], "trading_session": str(row["trading_session"]), "side": "short", "box_high": float(row["box_high"]), "box_low": float(row["box_low"]), "atr": float(row.get("atr", 0.0) or 0.0), "timeframe": spec.timeframe, "compression_method": spec.compression_method, "time_window": spec.time_window})
    return signals


def run_phase9c_retest(bars: pd.DataFrame, config: Phase9CConfig = Phase9CConfig()) -> dict[str, pd.DataFrame]:
    specs = build_phase9c_specs(config)
    sessions = sorted(bars["trading_session"].dropna().astype(str).unique().tolist())
    split_map = split_sessions(sessions)
    cache: dict[tuple[int, str, int, float], pd.DataFrame] = {}
    trades_all: list[pd.DataFrame] = []
    fold_all: list[pd.DataFrame] = []
    rows: list[dict[str, Any]] = []
    for spec in specs:
        key = (spec.timeframe, spec.compression_method, spec.compression_lookback, spec.compression_threshold)
        if key not in cache:
            cache[key] = compute_phase9c_features(bars, spec)
        features = cache[key]
        trades = _simulate_trades(features, generate_phase9c_signals(features, spec), spec)
        if not trades.empty:
            trades["split"] = trades["trading_session"].astype(str).map(split_map)
            trades_all.append(trades)
            fold_all.append(_fold_rows(trades, spec, sessions, config))
        rows.append(_candidate_row(spec, trades, sessions, split_map, config))
    trade_logs = pd.concat(trades_all, ignore_index=True) if trades_all else pd.DataFrame()
    folds = pd.concat(fold_all, ignore_index=True) if fold_all else pd.DataFrame()
    candidates = pd.DataFrame(rows).sort_values(["is_primary_eligible", "phase9c_score", "stress_pnl"], ascending=[False, False, False]).reset_index(drop=True)
    candidates.insert(0, "phase9c_rank", range(1, len(candidates) + 1))
    return {
        "candidate_results": candidates,
        "trade_logs": trade_logs,
        "walk_forward_folds": folds,
        "daily_pnl": _daily_pnl(trade_logs),
        "concentration_diagnostics": _concentration(trade_logs),
        "exit_reason_summary": _summary(trade_logs, "exit_reason"),
        "stop_failure_summary": _summary(trade_logs, "stop_failure_bucket"),
        "time_window_summary": _summary(trade_logs, "time_window"),
        "specs": pd.DataFrame([s.to_dict() for s in specs]),
    }


def render_phase9c_report(result: dict[str, pd.DataFrame], recommendation: dict[str, Any], report_path: Path) -> str:
    c = result["candidate_results"]
    label_counts = c["phase9c_label"].value_counts().to_dict() if not c.empty else {}
    lines = ["# Phase 9C MNQ Short-Only VCB Targeted Retest", "", "Research/simulation only. No live trading, broker adapters, order routing, webhooks, API-key storage, automated execution, or automatic paper-trading approval.", "", "## Summary", "", f"- Specs evaluated: `{len(c)}`", f"- Label counts: `{label_counts}`", f"- Next action: `{recommendation.get('next_action')}`", f"- Rationale: {recommendation.get('rationale')}", "", "## Primary Eligible Branch: 10:30-13:30", ""]
    lines.append(_candidate_table(c[c["is_primary_eligible"].eq(True)].head(12)))
    lines.extend(["", "## Diagnostic Branch: 10:00-13:30", "", _candidate_table(c[c["is_primary_eligible"].eq(False)].head(12)), "", "## Outputs", "", "- `outputs/phase9c_candidate_results.csv`", "- `outputs/phase9c_trade_logs.csv`", "- `outputs/phase9c_walk_forward_folds.csv`", "- `outputs/phase9c_daily_pnl.csv`", "- `outputs/phase9c_concentration_diagnostics.csv`", "- `outputs/phase9c_exit_reason_summary.csv`", "- `outputs/phase9c_stop_failure_summary.csv`", "- `outputs/phase9c_time_window_summary.csv`", "- `outputs/phase9c_strategy_specs.json`", "- `outputs/phase9c_next_action_recommendation.json`", f"- `{report_path.as_posix()}`"])
    return "\n".join(lines) + "\n"


def make_phase9c_recommendation(result: dict[str, pd.DataFrame]) -> dict[str, Any]:
    c = result["candidate_results"]
    if c.empty:
        return {"next_action": "phase10a_overnight_range_breakout_fade", "rationale": "No Phase 9C candidates were produced."}
    paper = c[c["phase9c_label"].eq("phase9c_candidate_for_paper_review")]
    watch = c[c["phase9c_label"].eq("phase9c_watchlist_needs_more_history")]
    if not paper.empty:
        return {"next_action": "prepare_phase9c_review_packet", "rationale": "At least one candidate passed all Phase 9C gates; this is review-only, not paper approval.", "top_candidate": paper.iloc[0].to_dict()}
    if not watch.empty:
        return {"next_action": "watchlist_more_history_or_review", "rationale": "At least one candidate survived economics but still needs more robustness/history.", "top_candidate": watch.iloc[0].to_dict()}
    return {"next_action": "phase10a_overnight_range_breakout_fade", "rationale": "Phase 9C failed validation/holdout/fold/concentration gates; kill compression breakout and pivot."}


def _simulate_trades(features: pd.DataFrame, signals: list[dict[str, Any]], spec: Phase9CSpec) -> pd.DataFrame:
    if features.empty or not signals:
        return pd.DataFrame()
    inst = get_instrument("MNQ")
    day_map = {str(s): d.sort_values("timestamp").reset_index(drop=True) for s, d in features.groupby("trading_session", sort=True)}
    rows: list[dict[str, Any]] = []
    counts: dict[str, int] = {}
    last_entry: dict[str, pd.Timestamp] = {}
    for signal in sorted(signals, key=lambda x: x["entry_time"]):
        session = str(signal["trading_session"])
        if counts.get(session, 0) >= spec.max_trades_per_day:
            continue
        entry_time = pd.Timestamp(signal["entry_time"])
        if session in last_entry and (entry_time - last_entry[session]).total_seconds() / 60 < spec.min_minutes_between_entries:
            continue
        day = day_map.get(session)
        if day is None:
            continue
        matches = day.index[day["timestamp"].eq(entry_time)].tolist()
        if not matches:
            continue
        trade = _simulate_one(day, matches[0], signal, spec, inst)
        if trade:
            rows.append({**signal, **trade, **spec.to_dict()})
            counts[session] = counts.get(session, 0) + 1
            last_entry[session] = entry_time
    return pd.DataFrame(rows)


def _simulate_one(day: pd.DataFrame, entry_pos: int, signal: dict[str, Any], spec: Phase9CSpec, inst) -> dict[str, Any]:
    entry = day.iloc[entry_pos]
    entry_price = float(entry["open"])
    buffer = spec.buffer_ticks * inst.tick_size
    opposite_stop = float(signal["box_high"]) + buffer
    atr = max(float(signal.get("atr", 0.0)), inst.tick_size * 8)
    hard_cap_stop = entry_price + atr * spec.atr_cap_multiple
    stop = min(opposite_stop, hard_cap_stop)
    risk_points = max(stop - entry_price, inst.tick_size * 8)
    target = entry_price - risk_points * spec.target_r
    max_exit = pd.Timestamp(entry["timestamp"]) + pd.Timedelta(minutes=spec.time_stop_minutes)
    exit_price, exit_time, exit_reason = float(entry["close"]), entry["timestamp"], "time_stop"
    invalidation_time = pd.NaT
    mfe = mae = 0.0
    ambiguity = 0
    for pos in range(entry_pos, len(day)):
        row = day.iloc[pos]
        ts = pd.Timestamp(row["timestamp"])
        mfe = max(mfe, (entry_price - float(row["low"])) * inst.point_value)
        mae = max(mae, (float(row["high"]) - entry_price) * inst.point_value)
        stop_hit = float(row["high"]) >= stop
        target_hit = float(row["low"]) <= target
        if stop_hit:
            exit_price, exit_time = stop, ts
            exit_reason = "stop_same_bar_conservative" if target_hit else "stop"
            ambiguity = int(target_hit)
            break
        if target_hit:
            exit_price, exit_time, exit_reason = target, ts, "target"
            break
        if spec.exit_model == "close_back_inside_box_invalidation_with_hard_cap" and float(row["close"]) > float(signal["box_low"]):
            next_pos = min(pos + 1, len(day) - 1)
            next_row = day.iloc[next_pos]
            exit_price, exit_time = float(next_row["open"]), next_row["timestamp"]
            exit_reason = "invalidation_exit"
            invalidation_time = ts
            break
        if ts >= max_exit or _minute(ts) >= 15 * 60 + 45:
            exit_price, exit_time = float(row["close"]), ts
            exit_reason = "session_flatten" if _minute(ts) >= 15 * 60 + 45 else "time_stop"
            break
    gross = (entry_price - exit_price) * inst.point_value
    stop_bucket = "quick_or_adverse_stop" if exit_reason in {"stop", "stop_same_bar_conservative"} and mfe <= mae else ("stopped_after_favorable_move" if exit_reason in {"stop", "stop_same_bar_conservative"} else "not_stop")
    return {"entry_price": round(entry_price, 4), "exit_time": exit_time, "exit_price": round(exit_price, 4), "exit_reason": exit_reason, "invalidation_time": invalidation_time, "opposite_box_stop": round(opposite_stop, 4), "hard_cap_stop": round(hard_cap_stop, 4), "stop_price": round(stop, 4), "target_price": round(target, 4), "gross_pnl": round(gross, 2), "net_pnl": round(gross - inst.base_cost, 2), "stress_pnl": round(gross - inst.stress_cost, 2), "risk_dollars": round(risk_points * inst.point_value, 2), "mfe": round(mfe, 2), "mae": round(mae, 2), "same_bar_ambiguity": ambiguity, "target_hit": int(exit_reason == "target"), "stop_hit": int(exit_reason in {"stop", "stop_same_bar_conservative"}), "time_stop": int(exit_reason in {"time_stop", "session_flatten"}), "stop_failure_bucket": stop_bucket}


def _candidate_row(spec: Phase9CSpec, trades: pd.DataFrame, sessions: list[str], split_map: dict[Any, str], config: Phase9CConfig) -> dict[str, Any]:
    row = spec.to_dict()
    if trades.empty:
        row.update(_zero_metrics())
    else:
        t = trades.copy()
        t["split"] = t["trading_session"].astype(str).map(split_map)
        net = float(t["net_pnl"].sum())
        equity = t["net_pnl"].cumsum()
        daily = t.groupby("trading_session")["net_pnl"].sum()
        folds = _fold_rows(t, spec, sessions, config)
        quick = t[t["stop_failure_bucket"].eq("quick_or_adverse_stop")]
        row.update({"trades": len(t), "active_days": int(t["trading_session"].nunique()), "trades_per_active_day": _div(len(t), t["trading_session"].nunique()), "net_pnl": round(net, 2), "stress_pnl": round(float(t["stress_pnl"].sum()), 2), "validation_pnl": round(float(t.loc[t["split"].eq("validation"), "net_pnl"].sum()), 2), "holdout_pnl": round(float(t.loc[t["split"].eq("holdout"), "net_pnl"].sum()), 2), "max_drawdown": round(float((equity - equity.cummax()).min()), 2), "best_day_concentration": _conc(float(daily.max()), net), "best_trade_concentration": _conc(float(t["net_pnl"].max()), net), "quick_or_adverse_stop_count": len(quick), "quick_or_adverse_stop_rate": _div(len(quick), len(t)), "quick_or_adverse_stop_net": round(float(quick["net_pnl"].sum()) if not quick.empty else 0.0, 2), "quick_or_adverse_stop_avg_mfe": round(float(quick["mfe"].mean()) if not quick.empty else 0.0, 2), "quick_or_adverse_stop_avg_mae": round(float(quick["mae"].mean()) if not quick.empty else 0.0, 2), **_exit_pnls(t), **_fold_summary(folds)})
    row["phase9c_label"] = _label(row, config)
    row["phase9c_score"] = round(float(row.get("stress_pnl", 0)) + float(row.get("walk_forward_stress_pnl", 0)) - abs(float(row.get("max_drawdown", 0))) - 5000 * max(float(row.get("best_day_concentration", 1)) - .15, 0), 4)
    row["reject_reasons"] = _reasons(row, config)
    return row


def _label(row: dict[str, Any], c: Phase9CConfig) -> str:
    if row.get("trades", 0) < c.min_trades or row.get("active_days", 0) < c.min_active_days or not (1 <= row.get("trades_per_active_day", 0) <= 3): return "phase9c_rejected_low_activity"
    if row.get("net_pnl", 0) <= 0 or row.get("stress_pnl", 0) <= 0: return "phase9c_rejected_negative_stress"
    if row.get("validation_pnl", 0) <= 0: return "phase9c_rejected_negative_validation"
    if row.get("holdout_pnl", 0) <= 0: return "phase9c_rejected_negative_holdout"
    if row.get("max_drawdown", 0) < c.drawdown_limit: return "phase9c_rejected_drawdown"
    if row.get("walk_forward_stress_pnl", 0) <= 0 or row.get("positive_wf_test_folds_pct", 0) < .9 or row.get("worst_wf_test_fold", 0) < c.worst_fold_limit: return "phase9c_rejected_fold_instability"
    if row.get("best_day_concentration", 1) > c.concentration_limit or row.get("best_trade_concentration", 1) > c.trade_concentration_limit or row.get("quick_or_adverse_stop_rate", 1) >= c.quick_stop_baseline_rate: return "phase9c_rejected_concentration"
    return "phase9c_candidate_for_paper_review" if row.get("is_primary_eligible") else "phase9c_watchlist_needs_more_history"


def _reasons(row: dict[str, Any], c: Phase9CConfig) -> str:
    checks = [("low activity", row.get("trades", 0) < c.min_trades), ("negative stress", row.get("stress_pnl", 0) <= 0), ("negative validation", row.get("validation_pnl", 0) <= 0), ("negative holdout", row.get("holdout_pnl", 0) <= 0), ("fold instability", row.get("positive_wf_test_folds_pct", 0) < .9), ("concentration", row.get("best_day_concentration", 1) > c.concentration_limit or row.get("best_trade_concentration", 1) > c.trade_concentration_limit), ("quick/adverse stops not reduced", row.get("quick_or_adverse_stop_rate", 1) >= c.quick_stop_baseline_rate)]
    return "; ".join(name for name, bad in checks if bad) or "survived Phase 9C gates; review only"


def _fold_rows(trades: pd.DataFrame, spec: Phase9CSpec, sessions: list[str], c: Phase9CConfig) -> pd.DataFrame:
    rows=[]; window=c.train_sessions+c.validation_sessions+c.test_sessions; start=0; fold=1
    while start+window <= len(sessions):
        test=sessions[start+c.train_sessions+c.validation_sessions:start+window]
        seg=trades[trades["trading_session"].astype(str).isin(test)]
        rows.append({"candidate_id": spec.candidate_id, "fold": fold, "net_pnl": round(float(seg["net_pnl"].sum()),2), "stress_pnl": round(float(seg["stress_pnl"].sum()),2), "trades": len(seg)})
        start += c.step_sessions; fold += 1
    return pd.DataFrame(rows)


def _fold_summary(folds: pd.DataFrame) -> dict[str, Any]:
    if folds.empty: return {"walk_forward_test_pnl":0.0,"walk_forward_stress_pnl":0.0,"positive_wf_test_folds_pct":0.0,"worst_wf_test_fold":0.0}
    return {"walk_forward_test_pnl": round(float(folds["net_pnl"].sum()),2), "walk_forward_stress_pnl": round(float(folds["stress_pnl"].sum()),2), "positive_wf_test_folds_pct": _div(int((folds["stress_pnl"]>0).sum()), len(folds)), "worst_wf_test_fold": round(float(folds["stress_pnl"].min()),2)}


def _exit_pnls(t: pd.DataFrame) -> dict[str, float]:
    return {f"{k}_pnl": round(float(t.loc[t["exit_reason"].eq(k), "net_pnl"].sum()),2) for k in ["time_stop","target","stop","invalidation_exit","session_flatten"]}

def _daily_pnl(t: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame() if t.empty else t.groupby(["candidate_id","trading_session"]).agg(trades=("net_pnl","size"), net_pnl=("net_pnl","sum"), stress_pnl=("stress_pnl","sum")).reset_index()

def _concentration(t: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame() if t.empty else t.groupby(["candidate_id","trading_session"]).agg(pnl=("net_pnl","sum"), trades=("net_pnl","size")).reset_index().sort_values("pnl", ascending=False)

def _summary(t: pd.DataFrame, col: str) -> pd.DataFrame:
    if t.empty or col not in t: return pd.DataFrame()
    return t.groupby(col).agg(trades=("net_pnl","size"), net_pnl=("net_pnl","sum"), stress_pnl=("stress_pnl","sum"), avg_mfe=("mfe","mean"), avg_mae=("mae","mean")).reset_index().rename(columns={col:"group"}).sort_values("stress_pnl", ascending=False)

def _candidate_table(df: pd.DataFrame) -> str:
    if df.empty: return "No rows."
    lines=["| Candidate | Label | Net | Stress | Val | Holdout | WF Stress | Quick Stop % | Notes |", "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |"]
    for _,r in df.iterrows(): lines.append(f"| `{r['candidate_id']}` | {r['phase9c_label']} | ${float(r['net_pnl']):.2f} | ${float(r['stress_pnl']):.2f} | ${float(r['validation_pnl']):.2f} | ${float(r['holdout_pnl']):.2f} | ${float(r['walk_forward_stress_pnl']):.2f} | {float(r['quick_or_adverse_stop_rate'])*100:.1f}% | {r['reject_reasons']} |")
    return "\n".join(lines)

def _zero_metrics() -> dict[str, Any]:
    d={"trades":0,"active_days":0,"trades_per_active_day":0.0,"net_pnl":0.0,"stress_pnl":0.0,"validation_pnl":0.0,"holdout_pnl":0.0,"max_drawdown":0.0,"best_day_concentration":1.0,"best_trade_concentration":1.0,"quick_or_adverse_stop_count":0,"quick_or_adverse_stop_rate":1.0,"quick_or_adverse_stop_net":0.0,"quick_or_adverse_stop_avg_mfe":0.0,"quick_or_adverse_stop_avg_mae":0.0,**_fold_summary(pd.DataFrame())}
    d.update({"time_stop_pnl":0.0,"target_pnl":0.0,"stop_pnl":0.0,"invalidation_exit_pnl":0.0,"session_flatten_pnl":0.0}); return d

def _hhmm(s: str) -> int:
    h,m=s.split(":"); return int(h)*60+int(m)
def _minute(ts: Any) -> int:
    ts=pd.Timestamp(ts); return ts.hour*60+ts.minute
def _div(a: float, b: float) -> float:
    return round(float(a/b), 6) if b else 0.0
def _conc(best: float, total: float) -> float:
    return _div(max(best,0.0), total) if total>0 else 1.0
def serialize_phase9c_specs(specs: list[Phase9CSpec]) -> str:
    return json.dumps([s.to_dict() for s in specs], indent=2, sort_keys=True, default=str)
def recommendation_to_json(rec: dict[str, Any]) -> str:
    return json.dumps(rec, indent=2, sort_keys=True, default=str)
