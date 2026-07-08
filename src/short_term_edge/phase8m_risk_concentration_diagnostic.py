from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from .backtest import split_sessions
from .instruments import get_instrument


@dataclass(frozen=True)
class Phase8MConfig:
    exit_models: tuple[str, ...] = ("horizon_close_15m", "fixed_r_1_5_time30", "vwap_failure_1_5_time30")
    max_specs: int = 192
    min_trades: int = 250
    min_active_session_pct: float = 0.50
    train_sessions: int = 75
    validation_sessions: int = 25
    test_sessions: int = 25
    step_sessions: int = 25
    min_folds: int = 3
    concentration_limit: float = 0.15
    trade_concentration_limit: float = 0.08
    hard_concentration_limit: float = 0.35
    hard_trade_concentration_limit: float = 0.20
    drawdown_limit: float = -6_000.0
    worst_fold_limit: float = -1_500.0
    flatten_time: str = "15:45"


@dataclass(frozen=True)
class Phase8MSpec:
    base_filter: str
    exit_model: str
    max_trades_per_day: int
    min_minutes_between_entries: int
    stop_after_loss: bool
    stop_after_win: bool
    daily_loss_lockout_r: str
    daily_profit_lockout_r: str
    diagnostic_only: bool = False

    @property
    def candidate_id(self) -> str:
        return (
            f"{self.base_filter}__{self.exit_model}__"
            f"mt{self.max_trades_per_day}_gap{self.min_minutes_between_entries}_"
            f"sal{int(self.stop_after_loss)}_saw{int(self.stop_after_win)}_"
            f"dl{self.daily_loss_lockout_r}_dp{self.daily_profit_lockout_r}"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "base_filter": self.base_filter,
            "exit_model": self.exit_model,
            "max_trades_per_day": self.max_trades_per_day,
            "min_minutes_between_entries": self.min_minutes_between_entries,
            "stop_after_loss": self.stop_after_loss,
            "stop_after_win": self.stop_after_win,
            "daily_loss_lockout_r": self.daily_loss_lockout_r,
            "daily_profit_lockout_r": self.daily_profit_lockout_r,
            "diagnostic_only": self.diagnostic_only,
            "notes": "Phase 8M research-only bounded MNQ VWAP risk/exit/concentration diagnostic; no paper/live promotion.",
        }


def build_phase8m_candidate_specs(config: Phase8MConfig = Phase8MConfig()) -> list[Phase8MSpec]:
    """Build a bounded candidate matrix around the Phase 8J/8L MNQ VWAP branch."""
    base_filters = [
        ("base_pre_14_00", False),
        ("exclude_10_00_10_30", False),
        ("exclude_wednesday", True),
        ("exclude_10_00_10_30_plus_no_wednesday", True),
    ]
    risk_profiles = [
        # Priority profile requested by the handoff: simple, defensible concentration throttle.
        (1, 30, True, False, "1.0", "none"),
        (1, 60, True, False, "1.0", "none"),
        (2, 30, True, False, "1.0", "none"),
        (2, 60, True, False, "1.0", "none"),
        (1, 15, False, False, "none", "none"),
        (2, 15, False, False, "none", "none"),
        (3, 15, False, False, "none", "none"),
        (1, 30, False, False, "1.5", "none"),
        (2, 30, False, False, "1.5", "none"),
        (3, 30, False, False, "1.5", "none"),
        (1, 60, False, False, "2.0", "none"),
        (2, 60, False, False, "2.0", "none"),
        (1, 30, False, True, "none", "1.0"),
        (2, 30, False, True, "none", "1.5"),
        (1, 60, True, True, "1.0", "1.0"),
        (3, 60, False, False, "2.0", "2.0"),
    ]
    specs: list[Phase8MSpec] = []
    for base_filter, diagnostic_only in base_filters:
        for exit_model in config.exit_models:
            for max_trades, gap, stop_loss, stop_win, loss_lockout, profit_lockout in risk_profiles:
                specs.append(
                    Phase8MSpec(
                        base_filter=base_filter,
                        exit_model=exit_model,
                        max_trades_per_day=max_trades,
                        min_minutes_between_entries=gap,
                        stop_after_loss=stop_loss,
                        stop_after_win=stop_win,
                        daily_loss_lockout_r=loss_lockout,
                        daily_profit_lockout_r=profit_lockout,
                        diagnostic_only=diagnostic_only,
                    )
                )
    return specs[: max(int(config.max_specs), 0)]


def remap_phase8m_exits(trades: pd.DataFrame, bars: pd.DataFrame, config: Phase8MConfig = Phase8MConfig()) -> pd.DataFrame:
    """Replay the Phase 8J entries under bounded executable exit variants."""
    prepared_trades = _prepare_trades(trades)
    if prepared_trades.empty:
        return prepared_trades
    prepared_bars = _prepare_bars(bars)
    bars_by_session = {
        str(session): group.reset_index(drop=True)
        for session, group in prepared_bars.groupby("trading_session", sort=False)
    }
    rows: list[dict[str, Any]] = []
    for _, trade in prepared_trades.iterrows():
        session_bars = bars_by_session.get(str(trade["trading_session"]), pd.DataFrame())
        for exit_model in config.exit_models:
            rows.append(_remap_trade_exit(trade, session_bars, exit_model, config))
    return pd.DataFrame(rows)


def apply_phase8m_risk_controls(trades: pd.DataFrame, spec: Phase8MSpec) -> pd.DataFrame:
    """Apply fixed pre-entry filters and sequential risk throttles using prior accepted trades only."""
    filtered = _apply_base_filter(_prepare_trades(trades), spec)
    if filtered.empty:
        return _annotate_empty(filtered, spec)
    accepted: list[dict[str, Any]] = []
    for session, group in filtered.sort_values(["entry_time", "exit_time"]).groupby("trading_session", sort=True):
        day_count = 0
        day_pnl = 0.0
        locked = False
        last_entry: pd.Timestamp | None = None
        notes: list[str] = []
        for _, row in group.iterrows():
            reject_reason = ""
            entry_time = row["entry_time"]
            if locked:
                reject_reason = "daily_lockout"
            elif day_count >= int(spec.max_trades_per_day):
                reject_reason = "max_trades_per_day"
            elif last_entry is not None and (entry_time - last_entry).total_seconds() / 60.0 < float(spec.min_minutes_between_entries):
                reject_reason = "min_minutes_between_entries"
            if reject_reason:
                notes.append(reject_reason)
                continue
            accepted_row = row.to_dict()
            accepted_row["phase8m_candidate_id"] = spec.candidate_id
            accepted_row["base_filter"] = spec.base_filter
            accepted_row["risk_model"] = _risk_model_name(spec)
            accepted_row["diagnostic_only"] = bool(spec.diagnostic_only)
            accepted_row["risk_control_notes"] = ";".join(sorted(set(notes))) if notes else "accepted"
            accepted.append(accepted_row)
            day_count += 1
            last_entry = entry_time
            pnl = float(row["net_pnl"])
            day_pnl += pnl
            risk_dollars = max(float(row.get("risk_dollars", 1.0)), 1.0)
            if spec.stop_after_loss and pnl < 0:
                locked = True
                notes.append("stop_after_loss")
            if spec.stop_after_win and pnl > 0:
                locked = True
                notes.append("stop_after_win")
            loss_multiple = _lockout_multiple(spec.daily_loss_lockout_r)
            profit_multiple = _lockout_multiple(spec.daily_profit_lockout_r)
            if loss_multiple is not None and day_pnl <= -loss_multiple * risk_dollars:
                locked = True
                notes.append("daily_loss_lockout")
            if profit_multiple is not None and day_pnl >= profit_multiple * risk_dollars:
                locked = True
                notes.append("daily_profit_lockout")
    if not accepted:
        return _annotate_empty(filtered.iloc[0:0].copy(), spec)
    return pd.DataFrame(accepted).sort_values(["entry_time", "exit_time"]).reset_index(drop=True)


def evaluate_phase8m_candidates(
    trades: pd.DataFrame,
    specs: list[Phase8MSpec],
    config: Phase8MConfig = Phase8MConfig(),
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    if trades.empty:
        raise ValueError("Phase 8M requires non-empty Phase 8J/exit-remapped trades")
    prepared = _prepare_trades(trades)
    complete_sessions = sorted(prepared["trading_session"].dropna().astype(str).unique().tolist())
    split_map = split_sessions(complete_sessions)
    result_rows: list[dict[str, Any]] = []
    log_frames: list[pd.DataFrame] = []
    fold_frames: list[pd.DataFrame] = []
    daily_frames: list[pd.DataFrame] = []
    concentration_rows: list[dict[str, Any]] = []
    outlier_frames: list[pd.DataFrame] = []
    for spec in specs:
        source = prepared[prepared["exit_model"].astype(str).eq(spec.exit_model)].copy() if "exit_model" in prepared.columns else prepared.copy()
        accepted = apply_phase8m_risk_controls(source, spec)
        result_rows.append(_summarize_phase8m_spec(spec, accepted, source, complete_sessions, split_map, config))
        if not accepted.empty:
            log_frames.append(accepted)
        folds = _phase8m_fold_rows(spec, accepted, complete_sessions, config)
        if not folds.empty:
            fold_frames.append(folds)
        daily = _phase8m_daily_rows(spec, accepted)
        if not daily.empty:
            daily_frames.append(daily)
        concentration_rows.extend(_phase8m_concentration_rows(spec, accepted))
        outliers = _phase8m_outlier_rows(spec, accepted)
        if not outliers.empty:
            outlier_frames.append(outliers)
    results = pd.DataFrame(result_rows)
    if results.empty:
        results = pd.DataFrame(columns=_result_columns())
    else:
        results["_label_priority"] = results["phase8m_label"].map(_label_priority).fillna(0)
        results = results.sort_values(
            ["_label_priority", "phase8m_score", "walk_forward_stress_pnl", "holdout_pnl", "candidate_id"],
            ascending=[False, False, False, False, True],
        ).drop(columns=["_label_priority"]).reset_index(drop=True)
        results.insert(0, "phase8m_rank", range(1, len(results) + 1))
    logs = pd.concat(log_frames, ignore_index=True) if log_frames else pd.DataFrame()
    folds = pd.concat(fold_frames, ignore_index=True) if fold_frames else pd.DataFrame(columns=_fold_columns())
    daily = pd.concat(daily_frames, ignore_index=True) if daily_frames else pd.DataFrame(columns=_daily_columns())
    concentration = pd.DataFrame(concentration_rows) if concentration_rows else pd.DataFrame(columns=_concentration_columns())
    outliers = pd.concat(outlier_frames, ignore_index=True) if outlier_frames else pd.DataFrame(columns=_outlier_columns())
    return results[["phase8m_rank", *_result_columns()]], logs, folds, daily, concentration, outliers


def render_phase8m_report(
    results: pd.DataFrame,
    folds: pd.DataFrame,
    concentration: pd.DataFrame,
    outliers: pd.DataFrame,
    config: Phase8MConfig,
    *,
    results_path: Path,
    filtered_trade_logs_path: Path,
    fold_results_path: Path,
    daily_pnl_path: Path,
    concentration_path: Path,
    outlier_path: Path,
    specs_path: Path,
    report_path: Path,
    run_artifact_dir: Path | None = None,
) -> str:
    label_counts = results["phase8m_label"].value_counts().to_dict() if not results.empty and "phase8m_label" in results.columns else {}
    lines = [
        "# Phase 8M MNQ VWAP Risk / Exit / Concentration Diagnostic",
        "",
        "Generated by: `./.venv/Scripts/python.exe scripts/run_phase8m_risk_concentration_diagnostic.py`",
        "",
        "## Scope And Guardrails",
        "",
        "- Research/simulation only. No live trading, broker adapters, order routing, API-key storage, webhooks, or automated execution were added.",
        "- Phase 8M gives the MNQ VWAP long-only pre-14:00 branch one bounded risk/exit/concentration remediation pass.",
        "- No paper-trading promotion: `phase8m_candidate_for_paper_review` only means a candidate deserves separate human paper-review planning.",
        "",
        "## Summary",
        "",
        f"- Label counts: `{label_counts}`",
        f"- Specs evaluated: `{len(results)}`",
        f"- Exit models: `{list(config.exit_models)}`",
        f"- Walk-forward window: `{config.train_sessions}/{config.validation_sessions}/{config.test_sessions}` sessions, step `{config.step_sessions}`",
        "",
        "| Rank | Candidate | Label | Score | Base Filter | Exit | Risk | Trades | Active % | Net | Stress | Disc. | Val. | Holdout | WF Test | WF Stress | Pos Folds | Worst Fold | DD | Day Conc. | Trade Conc. | Notes |",
        "| ---: | --- | --- | ---: | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for _, row in results.head(20).iterrows():
        lines.append(
            f"| {int(row['phase8m_rank'])} | `{row['candidate_id']}` | {row['phase8m_label']} | {float(row['phase8m_score']):.2f} | "
            f"{row['base_filter']} | {row['exit_model']} | {row['risk_model']} | {int(row['trades'])} | {float(row['active_days_pct']) * 100:.1f}% | "
            f"${float(row['net_pnl']):.2f} | ${float(row['stress_pnl']):.2f} | ${float(row['discovery_pnl']):.2f} | ${float(row['validation_pnl']):.2f} | "
            f"${float(row['holdout_pnl']):.2f} | ${float(row['walk_forward_test_pnl']):.2f} | ${float(row['walk_forward_stress_pnl']):.2f} | "
            f"{float(row['positive_wf_test_folds_pct']) * 100:.1f}% | ${float(row['worst_wf_test_fold']):.2f} | ${float(row['max_drawdown']):.2f} | "
            f"{float(row['best_day_concentration']) * 100:.1f}% | {float(row['best_trade_concentration']) * 100:.1f}% | {row['reject_reasons']} |"
        )
    top_outliers = outliers.head(10) if not outliers.empty else pd.DataFrame()
    lines.extend([
        "",
        "## Outlier Session Diagnostics",
        "",
        "These rows are forensic diagnostics, not deletion rules. A session should only become a no-trade rule if the condition is knowable before or at entry time.",
        "",
        "| Candidate | Session | PnL | Trades | Weekday | Signal Density | Best Trade | Worst Trade |",
        "| --- | --- | ---: | ---: | --- | ---: | ---: | ---: |",
    ])
    for _, row in top_outliers.iterrows():
        lines.append(
            f"| `{row['candidate_id']}` | {row['session_date']} | ${float(row['session_pnl']):.2f} | {int(row['session_trades'])} | "
            f"{row.get('weekday', '')} | {int(row.get('signal_density', 0))} | ${float(row.get('best_trade_pnl', 0.0)):.2f} | ${float(row.get('worst_trade_pnl', 0.0)):.2f} |"
        )
    lines.extend(
        [
            "",
            "## Decision Rule",
            "",
            "- `phase8m_candidate_for_paper_review` means the row survived this bounded diagnostic; it is still not paper/live approval.",
            "- `phase8m_watchlist_needs_more_history` means aggregate behavior is positive but fold, activity, concentration, or diagnostic-only evidence remains weak.",
            "- Rejected labels identify the first dominant hard-fail class: negative stress, fold instability, concentration, or low activity.",
            "",
            "## When To Abandon This Branch",
            "",
            "Abandon the MNQ VWAP branch if concentration remains high after max-trades/day and entry-gap throttles, stress PnL turns negative under executable exits, only weekday-style exclusions rescue the system, or fold stability remains weak.",
            "",
            "## Outputs",
            "",
            f"- Results CSV: `{results_path.as_posix()}`",
            f"- Filtered trade logs CSV: `{filtered_trade_logs_path.as_posix()}`",
            f"- Walk-forward folds CSV: `{fold_results_path.as_posix()}`",
            f"- Daily PnL CSV: `{daily_pnl_path.as_posix()}`",
            f"- Concentration diagnostics CSV: `{concentration_path.as_posix()}`",
            f"- Outlier session diagnostics CSV: `{outlier_path.as_posix()}`",
            f"- Strategy specs JSON: `{specs_path.as_posix()}`",
            f"- Report: `{report_path.as_posix()}`",
        ]
    )
    if run_artifact_dir is not None:
        lines.append(f"- Run-scoped artifacts: `{run_artifact_dir.as_posix()}`")
    lines.extend(["", "## Repro Command", "", "```bash", "./.venv/Scripts/python.exe scripts/run_phase8m_risk_concentration_diagnostic.py", "```", ""])
    return "\n".join(lines)


def _prepare_trades(trades: pd.DataFrame) -> pd.DataFrame:
    out = trades.copy()
    if out.empty:
        return out
    out["entry_time"] = pd.to_datetime(out["entry_time"], utc=True).dt.tz_convert("America/New_York")
    if "exit_time" in out.columns:
        out["exit_time"] = pd.to_datetime(out["exit_time"], utc=True).dt.tz_convert("America/New_York")
    else:
        out["exit_time"] = out["entry_time"]
    if "event_time" in out.columns:
        out["event_time"] = pd.to_datetime(out["event_time"], utc=True).dt.tz_convert("America/New_York")
    else:
        out["event_time"] = out["entry_time"]
    out["trading_session"] = out["trading_session"].astype(str)
    if "weekday" not in out.columns:
        out["weekday"] = out["entry_time"].dt.day_name()
    minutes = out["entry_time"].dt.hour * 60 + out["entry_time"].dt.minute
    out["minute_bucket"] = minutes.map(_minute_bucket)
    if "rth_bucket" not in out.columns:
        out["rth_bucket"] = out["minute_bucket"]
    if "stress_net_pnl" not in out.columns:
        out["stress_net_pnl"] = out["net_pnl"]
    if "risk_dollars" not in out.columns:
        out["risk_dollars"] = out["net_pnl"].abs().clip(lower=50.0)
    if "exit_model" not in out.columns:
        out["exit_model"] = out.get("exit_shape", "horizon_close_15m")
    return out


def _prepare_bars(bars: pd.DataFrame) -> pd.DataFrame:
    out = bars.copy()
    if out.empty:
        return out
    out["timestamp"] = pd.to_datetime(out["timestamp"], utc=True).dt.tz_convert("America/New_York")
    if "trading_session" not in out.columns:
        raise ValueError("Phase 8M bars require trading_session")
    if "session_segment" in out.columns:
        out = out[out["session_segment"].astype(str).eq("RTH")].copy()
    out = out.sort_values(["trading_session", "timestamp"]).reset_index(drop=True)
    typical = (out["high"].astype(float) + out["low"].astype(float) + out["close"].astype(float)) / 3.0
    pv = typical * out["volume"].astype(float)
    out["vwap"] = pv.groupby(out["trading_session"]).cumsum() / out["volume"].astype(float).groupby(out["trading_session"]).cumsum()
    return out


def _remap_trade_exit(trade: pd.Series, session_bars: pd.DataFrame, exit_model: str, config: Phase8MConfig) -> dict[str, Any]:
    base = trade.to_dict()
    if exit_model == "horizon_close_15m" or session_bars.empty:
        base["exit_model"] = exit_model
        base["risk_dollars"] = max(float(base.get("risk_dollars", abs(float(base.get("net_pnl", 50.0))))), 50.0)
        return base
    entry_time = trade["entry_time"]
    future = session_bars[session_bars["timestamp"] > entry_time].copy()
    if future.empty:
        base["exit_model"] = exit_model
        return base
    entry_price = float(trade["entry_price"])
    side = str(trade.get("side", "long"))
    point_value = get_instrument(str(trade.get("instrument", "MNQ"))).point_value
    spec = get_instrument(str(trade.get("instrument", "MNQ")))
    event_bar = session_bars[session_bars["timestamp"].le(trade["event_time"])].tail(1)
    event_low = float(event_bar["low"].iloc[0]) if not event_bar.empty else entry_price - 10.0
    event_vwap = float(event_bar["vwap"].iloc[0]) if not event_bar.empty else entry_price
    buffer = spec.tick_size * 2.0
    if exit_model == "fixed_r_1_5_time30":
        stop = min(entry_price - spec.tick_size, event_low - buffer)
        risk_points = max(entry_price - stop, spec.tick_size * 8.0)
        target = entry_price + risk_points * 1.5
        exit_row = _scan_intrabar_long(future, entry_price, stop, target, 30, config)
    elif exit_model == "vwap_failure_1_5_time30":
        stop = min(entry_price - spec.tick_size, event_vwap - buffer)
        risk_points = max(entry_price - stop, spec.tick_size * 8.0)
        target = entry_price + risk_points * 1.5
        exit_row = _scan_vwap_failure_long(future, entry_price, stop, target, 30, config)
    else:
        raise ValueError(f"Unsupported Phase 8M exit model: {exit_model}")
    gross = (float(exit_row["exit_price"]) - entry_price) * (1 if side == "long" else -1) * point_value
    base.update(
        {
            "exit_model": exit_model,
            "exit_time": exit_row["exit_time"],
            "exit_price": round(float(exit_row["exit_price"]), 4),
            "exit_reason": exit_row["exit_reason"],
            "stop_price": round(float(stop), 4),
            "target_price": round(float(target), 4),
            "gross_pnl": round(gross, 2),
            "net_pnl": round(gross - spec.base_cost, 2),
            "stress_net_pnl": round(gross - spec.stress_cost, 2),
            "risk_dollars": round(risk_points * point_value, 2),
            "same_bar_ambiguity": int(exit_row.get("same_bar_ambiguity", 0)),
        }
    )
    return base


def _scan_intrabar_long(future: pd.DataFrame, entry_price: float, stop: float, target: float, time_stop_minutes: int, config: Phase8MConfig) -> dict[str, Any]:
    max_exit_time = future["timestamp"].iloc[0] + pd.Timedelta(minutes=time_stop_minutes)
    flatten_minutes = _hhmm_to_minutes(config.flatten_time)
    for _, row in future.iterrows():
        ts = row["timestamp"]
        if ts.hour * 60 + ts.minute >= flatten_minutes or ts >= max_exit_time:
            return {"exit_time": ts, "exit_price": float(row["close"]), "exit_reason": "time_stop", "same_bar_ambiguity": 0}
        stop_hit = float(row["low"]) <= stop
        target_hit = float(row["high"]) >= target
        if stop_hit:
            return {"exit_time": ts, "exit_price": stop, "exit_reason": "stop" if not target_hit else "stop_same_bar_conservative", "same_bar_ambiguity": int(target_hit)}
        if target_hit:
            return {"exit_time": ts, "exit_price": target, "exit_reason": "target", "same_bar_ambiguity": 0}
    last = future.iloc[-1]
    return {"exit_time": last["timestamp"], "exit_price": float(last["close"]), "exit_reason": "data_end", "same_bar_ambiguity": 0}


def _scan_vwap_failure_long(future: pd.DataFrame, entry_price: float, stop: float, target: float, time_stop_minutes: int, config: Phase8MConfig) -> dict[str, Any]:
    max_exit_time = future["timestamp"].iloc[0] + pd.Timedelta(minutes=time_stop_minutes)
    flatten_minutes = _hhmm_to_minutes(config.flatten_time)
    for _, row in future.iterrows():
        ts = row["timestamp"]
        if ts.hour * 60 + ts.minute >= flatten_minutes or ts >= max_exit_time:
            return {"exit_time": ts, "exit_price": float(row["close"]), "exit_reason": "time_stop", "same_bar_ambiguity": 0}
        stop_hit = float(row["low"]) <= stop
        target_hit = float(row["high"]) >= target
        if stop_hit:
            return {"exit_time": ts, "exit_price": stop, "exit_reason": "stop" if not target_hit else "stop_same_bar_conservative", "same_bar_ambiguity": int(target_hit)}
        if float(row["close"]) < float(row["vwap"]):
            return {"exit_time": ts, "exit_price": float(row["close"]), "exit_reason": "vwap_failure", "same_bar_ambiguity": 0}
        if target_hit:
            return {"exit_time": ts, "exit_price": target, "exit_reason": "target", "same_bar_ambiguity": 0}
    last = future.iloc[-1]
    return {"exit_time": last["timestamp"], "exit_price": float(last["close"]), "exit_reason": "data_end", "same_bar_ambiguity": 0}


def _apply_base_filter(trades: pd.DataFrame, spec: Phase8MSpec) -> pd.DataFrame:
    out = trades.copy()
    if spec.base_filter == "base_pre_14_00":
        return out
    if spec.base_filter in {"exclude_10_00_10_30", "exclude_10_00_10_30_plus_no_wednesday"}:
        out = out[~out["minute_bucket"].astype(str).eq("10:00-10:30")].copy()
    if spec.base_filter in {"exclude_wednesday", "exclude_10_00_10_30_plus_no_wednesday"}:
        out = out[~out["weekday"].astype(str).eq("Wednesday")].copy()
    return out


def _summarize_phase8m_spec(spec: Phase8MSpec, trades: pd.DataFrame, source: pd.DataFrame, sessions: list[str], split_map: dict[Any, str], config: Phase8MConfig) -> dict[str, Any]:
    base = {**spec.to_dict(), "risk_model": _risk_model_name(spec)}
    if trades.empty:
        row = {**base, **_zero_result_metrics(), "source_trades": int(len(source)), "trades": 0, "removed_trades": int(len(source))}
    else:
        ordered = trades.sort_values(["entry_time", "exit_time"]).copy()
        ordered["split"] = ordered["trading_session"].map(split_map).fillna("unknown")
        net = float(ordered["net_pnl"].sum())
        stress = float(ordered["stress_net_pnl"].sum())
        daily = ordered.groupby("trading_session")["net_pnl"].sum()
        equity = ordered["net_pnl"].cumsum()
        fold_summary = _fold_summary(_phase8m_fold_rows(spec, ordered, sessions, config))
        row = {
            **base,
            "source_trades": int(len(source)),
            "trades": int(len(ordered)),
            "removed_trades": int(len(source) - len(ordered)),
            "active_days": int(ordered["trading_session"].nunique()),
            "active_days_pct": round(_safe_div(float(ordered["trading_session"].nunique()), float(len(sessions))), 6),
            "trades_per_active_day": round(_safe_div(float(len(ordered)), float(ordered["trading_session"].nunique())), 6),
            "net_pnl": round(net, 2),
            "stress_pnl": round(stress, 2),
            "discovery_pnl": round(float(ordered.loc[ordered["split"].eq("discovery"), "net_pnl"].sum()), 2),
            "validation_pnl": round(float(ordered.loc[ordered["split"].eq("validation"), "net_pnl"].sum()), 2),
            "holdout_pnl": round(float(ordered.loc[ordered["split"].eq("holdout"), "net_pnl"].sum()), 2),
            "max_drawdown": round(float((equity - equity.cummax()).min()), 2),
            "best_day_pnl": round(float(daily.max()) if not daily.empty else 0.0, 2),
            "best_day_concentration": round(_concentration(float(daily.max()) if not daily.empty else 0.0, net), 6),
            "best_trade_pnl": round(float(ordered["net_pnl"].max()), 2),
            "best_trade_concentration": round(_concentration(float(ordered["net_pnl"].max()), net), 6),
            **fold_summary,
        }
    row["phase8m_score"] = round(_phase8m_score(row), 4)
    row["phase8m_label"] = _phase8m_label(row, config)
    row["reject_reasons"] = _phase8m_notes(row, config)
    return row


def _phase8m_fold_rows(spec: Phase8MSpec, trades: pd.DataFrame, sessions: list[str], config: Phase8MConfig) -> pd.DataFrame:
    folds = _generate_folds(sessions, config)
    rows = []
    for fold in folds:
        test_sessions = set(fold["test_sessions"])
        segment = trades[trades["trading_session"].astype(str).isin(test_sessions)].copy() if not trades.empty else trades
        score = _score_segment(segment, fold["test_sessions"])
        rows.append({"candidate_id": spec.candidate_id, "base_filter": spec.base_filter, "exit_model": spec.exit_model, "risk_model": _risk_model_name(spec), "fold": fold["fold"], "segment": "test", "segment_start": fold["test_sessions"][0], "segment_end": fold["test_sessions"][-1], **score})
    return pd.DataFrame(rows, columns=_fold_columns()) if rows else pd.DataFrame(columns=_fold_columns())


def _phase8m_daily_rows(spec: Phase8MSpec, trades: pd.DataFrame) -> pd.DataFrame:
    if trades.empty:
        return pd.DataFrame(columns=_daily_columns())
    rows = []
    for session, group in trades.groupby("trading_session", sort=True):
        rows.append({"candidate_id": spec.candidate_id, "session_date": str(session), "base_filter": spec.base_filter, "exit_model": spec.exit_model, "risk_model": _risk_model_name(spec), "trades": int(len(group)), "net_pnl": round(float(group["net_pnl"].sum()), 2), "stress_pnl": round(float(group["stress_net_pnl"].sum()), 2), "weekday": str(group["weekday"].iloc[0])})
    return pd.DataFrame(rows)[_daily_columns()]


def _phase8m_concentration_rows(spec: Phase8MSpec, trades: pd.DataFrame) -> list[dict[str, Any]]:
    if trades.empty:
        return []
    net = float(trades["net_pnl"].sum())
    rows = []
    for scope, column in [("day", "trading_session"), ("weekday", "weekday"), ("minute_bucket", "minute_bucket"), ("exit_reason", "exit_reason")]:
        grouped = trades.groupby(column)["net_pnl"].agg(["sum", "count"]).reset_index()
        for _, row in grouped.iterrows():
            rows.append({"candidate_id": spec.candidate_id, "scope": scope, "bucket": str(row[column]), "pnl": round(float(row["sum"]), 2), "trades": int(row["count"]), "concentration": round(_concentration(float(row["sum"]), net), 6)})
    return rows


def _phase8m_outlier_rows(spec: Phase8MSpec, trades: pd.DataFrame, limit: int = 3) -> pd.DataFrame:
    if trades.empty:
        return pd.DataFrame(columns=_outlier_columns())
    rows = []
    daily = trades.groupby("trading_session", sort=True)
    for session, group in daily:
        rows.append({"candidate_id": spec.candidate_id, "session_date": str(session), "session_pnl": round(float(group["net_pnl"].sum()), 2), "session_trades": int(len(group)), "weekday": str(group["weekday"].iloc[0]), "signal_density": int(len(group)), "best_trade_pnl": round(float(group["net_pnl"].max()), 2), "worst_trade_pnl": round(float(group["net_pnl"].min()), 2), "first_entry_time": str(group["entry_time"].min()), "last_entry_time": str(group["entry_time"].max())})
    frame = pd.DataFrame(rows)
    frame["abs_session_pnl"] = frame["session_pnl"].abs()
    return frame.sort_values(["abs_session_pnl", "session_trades"], ascending=[False, False]).drop(columns=["abs_session_pnl"]).head(limit)[_outlier_columns()]


def _generate_folds(sessions: list[str], config: Phase8MConfig) -> list[dict[str, Any]]:
    window = config.train_sessions + config.validation_sessions + config.test_sessions
    if len(sessions) < window:
        return []
    folds: list[dict[str, Any]] = []
    start = 0
    fold = 1
    while start + window <= len(sessions):
        test_start = start + config.train_sessions + config.validation_sessions
        test_end = test_start + config.test_sessions
        folds.append({"fold": fold, "test_sessions": sessions[test_start:test_end]})
        fold += 1
        start += config.step_sessions
    return folds


def _score_segment(trades: pd.DataFrame, segment_sessions: list[str]) -> dict[str, Any]:
    if trades.empty:
        return {"trades": 0, "active_days": 0, "active_days_pct": 0.0, "net_pnl": 0.0, "stress_pnl": 0.0, "max_drawdown": 0.0, "best_day_concentration": 0.0, "best_trade_concentration": 0.0}
    ordered = trades.sort_values(["entry_time", "exit_time"]).copy()
    net = float(ordered["net_pnl"].sum())
    equity = ordered["net_pnl"].cumsum()
    daily = ordered.groupby("trading_session")["net_pnl"].sum()
    return {"trades": int(len(ordered)), "active_days": int(ordered["trading_session"].nunique()), "active_days_pct": round(_safe_div(float(ordered["trading_session"].nunique()), float(len(segment_sessions))), 6), "net_pnl": round(net, 2), "stress_pnl": round(float(ordered["stress_net_pnl"].sum()), 2), "max_drawdown": round(float((equity - equity.cummax()).min()), 2), "best_day_concentration": round(_concentration(float(daily.max()) if not daily.empty else 0.0, net), 6), "best_trade_concentration": round(_concentration(float(ordered["net_pnl"].max()), net), 6)}


def _fold_summary(folds: pd.DataFrame) -> dict[str, Any]:
    if folds.empty:
        return {"walk_forward_folds": 0, "walk_forward_test_trades": 0, "walk_forward_test_pnl": 0.0, "walk_forward_stress_pnl": 0.0, "positive_wf_test_folds": 0, "positive_wf_test_folds_pct": 0.0, "worst_wf_test_fold": 0.0, "walk_forward_max_drawdown": 0.0, "walk_forward_day_concentration": 0.0, "walk_forward_trade_concentration": 0.0}
    positive = int((folds["net_pnl"] > 0).sum())
    return {"walk_forward_folds": int(len(folds)), "walk_forward_test_trades": int(folds["trades"].sum()), "walk_forward_test_pnl": round(float(folds["net_pnl"].sum()), 2), "walk_forward_stress_pnl": round(float(folds["stress_pnl"].sum()), 2), "positive_wf_test_folds": positive, "positive_wf_test_folds_pct": round(_safe_div(float(positive), float(len(folds))), 6), "worst_wf_test_fold": round(float(folds["net_pnl"].min()), 2), "walk_forward_max_drawdown": round(float(folds["max_drawdown"].min()), 2), "walk_forward_day_concentration": round(float(folds["best_day_concentration"].max()), 6), "walk_forward_trade_concentration": round(float(folds["best_trade_concentration"].max()), 6)}


def _phase8m_score(row: dict[str, Any]) -> float:
    score = max(min(float(row.get("stress_pnl", 0.0)) / 8_000.0, 2.0), -2.0) * 24.0
    score += max(min(float(row.get("walk_forward_stress_pnl", 0.0)) / 6_000.0, 2.0), -2.0) * 20.0
    score += float(row.get("positive_wf_test_folds_pct", 0.0)) * 24.0
    score += max(min(float(row.get("holdout_pnl", 0.0)) / 4_000.0, 2.0), -2.0) * 12.0
    score += min(float(row.get("trades", 0.0)) / 700.0, 1.0) * 6.0
    score -= min(abs(float(row.get("max_drawdown", 0.0))) / 6_000.0, 2.0) * 16.0
    score -= max(float(row.get("best_day_concentration", 1.0)) - 0.15, 0.0) * 140.0
    score -= max(float(row.get("best_trade_concentration", 1.0)) - 0.08, 0.0) * 110.0
    if bool(row.get("diagnostic_only", False)):
        score -= 10.0
    return float(score)


def _phase8m_label(row: dict[str, Any], config: Phase8MConfig) -> str:
    if int(row.get("trades", 0)) < config.min_trades or float(row.get("active_days_pct", 0.0)) < config.min_active_session_pct:
        return "phase8m_rejected_low_activity"
    if float(row.get("net_pnl", 0.0)) <= 0 or float(row.get("stress_pnl", 0.0)) <= 0:
        return "phase8m_rejected_negative_stress"
    if int(row.get("walk_forward_folds", 0)) < config.min_folds or float(row.get("walk_forward_stress_pnl", 0.0)) <= 0 or float(row.get("positive_wf_test_folds_pct", 0.0)) < 1.0 or float(row.get("worst_wf_test_fold", 0.0)) < config.worst_fold_limit:
        return "phase8m_rejected_fold_instability"
    if float(row.get("best_day_concentration", 1.0)) > config.hard_concentration_limit or float(row.get("best_trade_concentration", 1.0)) > config.hard_trade_concentration_limit or float(row.get("walk_forward_day_concentration", 1.0)) > config.hard_concentration_limit or float(row.get("walk_forward_trade_concentration", 1.0)) > config.hard_trade_concentration_limit:
        return "phase8m_rejected_concentration"
    if bool(row.get("diagnostic_only", False)) or float(row.get("best_day_concentration", 1.0)) > config.concentration_limit or float(row.get("best_trade_concentration", 1.0)) > config.trade_concentration_limit or float(row.get("max_drawdown", 0.0)) < config.drawdown_limit:
        return "phase8m_watchlist_needs_more_history"
    return "phase8m_candidate_for_paper_review"


def _phase8m_notes(row: dict[str, Any], config: Phase8MConfig) -> str:
    notes: list[str] = []
    if bool(row.get("diagnostic_only", False)):
        notes.append("diagnostic-only weekday-style filter")
    if int(row.get("trades", 0)) < config.min_trades:
        notes.append("low trade count")
    if float(row.get("active_days_pct", 0.0)) < config.min_active_session_pct:
        notes.append("low active-day coverage")
    if float(row.get("net_pnl", 0.0)) <= 0:
        notes.append("negative net PnL")
    if float(row.get("stress_pnl", 0.0)) <= 0:
        notes.append("negative stress PnL")
    for split in ("discovery", "validation", "holdout"):
        if float(row.get(f"{split}_pnl", 0.0)) <= 0:
            notes.append(f"negative {split} split")
    if int(row.get("walk_forward_folds", 0)) < config.min_folds:
        notes.append("too few walk-forward folds")
    if float(row.get("positive_wf_test_folds_pct", 0.0)) < 1.0:
        notes.append("not every walk-forward test fold is positive")
    if float(row.get("worst_wf_test_fold", 0.0)) < config.worst_fold_limit:
        notes.append("worst fold below limit")
    if float(row.get("best_day_concentration", 1.0)) > config.concentration_limit:
        notes.append("one-day concentration risk")
    if float(row.get("best_trade_concentration", 1.0)) > config.trade_concentration_limit:
        notes.append("one-trade concentration risk")
    if float(row.get("walk_forward_day_concentration", 1.0)) > config.concentration_limit:
        notes.append("walk-forward day concentration risk")
    if float(row.get("walk_forward_trade_concentration", 1.0)) > config.trade_concentration_limit:
        notes.append("walk-forward trade concentration risk")
    if float(row.get("max_drawdown", 0.0)) < config.drawdown_limit:
        notes.append("drawdown beyond limit")
    return "; ".join(notes) if notes else "survives bounded Phase 8M diagnostic; still requires separate paper-review checklist"


def _zero_result_metrics() -> dict[str, Any]:
    return {"active_days": 0, "active_days_pct": 0.0, "trades_per_active_day": 0.0, "net_pnl": 0.0, "stress_pnl": 0.0, "discovery_pnl": 0.0, "validation_pnl": 0.0, "holdout_pnl": 0.0, "max_drawdown": 0.0, "best_day_pnl": 0.0, "best_day_concentration": 0.0, "best_trade_pnl": 0.0, "best_trade_concentration": 0.0, **_fold_summary(pd.DataFrame())}


def _annotate_empty(trades: pd.DataFrame, spec: Phase8MSpec) -> pd.DataFrame:
    out = trades.copy()
    out["phase8m_candidate_id"] = spec.candidate_id
    return out


def _risk_model_name(spec: Phase8MSpec) -> str:
    return f"mt{spec.max_trades_per_day}_gap{spec.min_minutes_between_entries}_sal{int(spec.stop_after_loss)}_saw{int(spec.stop_after_win)}_dl{spec.daily_loss_lockout_r}_dp{spec.daily_profit_lockout_r}"


def _lockout_multiple(value: str) -> float | None:
    if str(value) == "none":
        return None
    return float(value)


def _minute_bucket(minute_of_day: int) -> str:
    width = 30
    start = int(minute_of_day // width * width)
    end = start + width
    return f"{start // 60:02d}:{start % 60:02d}-{end // 60:02d}:{end % 60:02d}"


def _hhmm_to_minutes(value: str) -> int:
    hour, minute = value.split(":")
    return int(hour) * 60 + int(minute)


def _concentration(best: float, total: float) -> float:
    if total <= 0:
        return 1.0
    return float(max(best, 0.0) / total)


def _safe_div(numerator: float, denominator: float) -> float:
    return float(numerator / denominator) if denominator else 0.0


def _label_priority(label: str) -> int:
    return {"phase8m_candidate_for_paper_review": 4, "phase8m_watchlist_needs_more_history": 3, "phase8m_rejected_concentration": 2, "phase8m_rejected_fold_instability": 1, "phase8m_rejected_negative_stress": 0, "phase8m_rejected_low_activity": 0}.get(str(label), 0)


def _result_columns() -> list[str]:
    return ["candidate_id", "base_filter", "exit_model", "risk_model", "max_trades_per_day", "min_minutes_between_entries", "stop_after_loss", "stop_after_win", "daily_loss_lockout_r", "daily_profit_lockout_r", "diagnostic_only", "source_trades", "trades", "removed_trades", "active_days", "active_days_pct", "trades_per_active_day", "net_pnl", "stress_pnl", "discovery_pnl", "validation_pnl", "holdout_pnl", "walk_forward_test_pnl", "walk_forward_stress_pnl", "walk_forward_test_trades", "positive_wf_test_folds", "positive_wf_test_folds_pct", "worst_wf_test_fold", "walk_forward_folds", "max_drawdown", "walk_forward_max_drawdown", "best_day_pnl", "best_day_concentration", "best_trade_pnl", "best_trade_concentration", "walk_forward_day_concentration", "walk_forward_trade_concentration", "phase8m_score", "phase8m_label", "reject_reasons"]


def _fold_columns() -> list[str]:
    return ["candidate_id", "base_filter", "exit_model", "risk_model", "fold", "segment", "segment_start", "segment_end", "trades", "active_days", "active_days_pct", "net_pnl", "stress_pnl", "max_drawdown", "best_day_concentration", "best_trade_concentration"]


def _daily_columns() -> list[str]:
    return ["candidate_id", "session_date", "base_filter", "exit_model", "risk_model", "trades", "net_pnl", "stress_pnl", "weekday"]


def _concentration_columns() -> list[str]:
    return ["candidate_id", "scope", "bucket", "pnl", "trades", "concentration"]


def _outlier_columns() -> list[str]:
    return ["candidate_id", "session_date", "session_pnl", "session_trades", "weekday", "signal_density", "best_trade_pnl", "worst_trade_pnl", "first_entry_time", "last_entry_time"]
