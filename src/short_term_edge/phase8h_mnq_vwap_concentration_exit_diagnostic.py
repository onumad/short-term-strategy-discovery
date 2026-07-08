from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from pathlib import Path
from typing import Any

import pandas as pd

from .phase8e_event_scout import _event_positions, _prepare_bars
from .phase8g_event_execution_calibration import CalibrationVariant, _simulate_calibration_trades


@dataclass(frozen=True)
class Phase8HConfig:
    target_instrument: str = "MNQ"
    target_families: tuple[str, ...] = ("vwap_pullback_continuation", "vwap_reclaim_rejection")
    target_entry_delay: str = "next_5m_close"
    baseline_time_stop: int = 15
    concentration_limit: float = 0.35
    min_trades: int = 250
    exit_shapes: tuple[str, ...] = ("horizon_close_10m", "horizon_close_15m", "horizon_close_20m", "trailing_time_stop", "session_bucket_flatten")


def select_phase8h_inputs(event_results: pd.DataFrame, phase8g_results: pd.DataFrame, config: Phase8HConfig = Phase8HConfig()) -> pd.DataFrame:
    """Select Phase 8G-positive MNQ VWAP rows that came from Phase 8E backtest candidates."""
    event_required = {"hypothesis_id", "instrument", "family", "phase8e_label"}
    phase8g_required = {
        "hypothesis_id",
        "instrument",
        "family",
        "entry_delay",
        "stop_model",
        "target_model",
        "time_stop",
        "net_pnl",
        "slippage_4_ticks_net_pnl",
    }
    _require_columns(event_results, event_required, "Phase 8E results")
    _require_columns(phase8g_results, phase8g_required, "Phase 8G results")

    eligible_events = event_results[
        event_results["phase8e_label"].eq("backtest_candidate")
        & event_results["instrument"].eq(config.target_instrument)
        & event_results["family"].isin(config.target_families)
    ].copy()
    if eligible_events.empty:
        return _empty_selection(event_results, phase8g_results)

    eligible_calibrations = phase8g_results[
        phase8g_results["instrument"].eq(config.target_instrument)
        & phase8g_results["family"].isin(config.target_families)
        & phase8g_results["entry_delay"].eq(config.target_entry_delay)
        & phase8g_results["stop_model"].eq("none")
        & phase8g_results["target_model"].eq("horizon_close")
        & phase8g_results["time_stop"].astype(int).eq(int(config.baseline_time_stop))
        & (phase8g_results["net_pnl"].astype(float) > 0.0)
        & (phase8g_results["slippage_4_ticks_net_pnl"].astype(float) > 0.0)
    ].copy()
    if eligible_calibrations.empty:
        return _empty_selection(event_results, phase8g_results)

    selected = eligible_events.merge(
        eligible_calibrations,
        on=["hypothesis_id", "instrument", "family"],
        how="inner",
        suffixes=("", "_phase8g"),
    )
    if "calibration_score" in selected.columns:
        selected = selected.sort_values(["calibration_score", "slippage_4_ticks_net_pnl", "net_pnl"], ascending=[False, False, False])
    return selected.reset_index(drop=True)


def replay_phase8h_trades(selected_inputs: pd.DataFrame, data_by_symbol: dict[str, pd.DataFrame], config: Phase8HConfig = Phase8HConfig()) -> pd.DataFrame:
    """Replay the baseline horizon-close trade path and keep trade-level diagnostics."""
    return _simulate_exit_shape_trades(selected_inputs, data_by_symbol, f"horizon_close_{config.baseline_time_stop}m", config)


def run_phase8h_exit_shape_grid(selected_inputs: pd.DataFrame, data_by_symbol: dict[str, pd.DataFrame], config: Phase8HConfig = Phase8HConfig()) -> pd.DataFrame:
    """Compare a narrow set of non-intrabar exit shapes for selected Phase 8H hypotheses."""
    rows: list[pd.DataFrame] = []
    for exit_shape in config.exit_shapes:
        trades = _simulate_exit_shape_trades(selected_inputs, data_by_symbol, exit_shape, config)
        summary = summarize_phase8h_concentration(trades, config)
        if summary.empty:
            continue
        hypothesis_rows = summary[summary["summary_scope"].eq("hypothesis")].copy()
        hypothesis_rows.insert(0, "exit_shape", exit_shape)
        rows.append(hypothesis_rows)
    if not rows:
        return pd.DataFrame(columns=_exit_shape_columns())
    result = pd.concat(rows, ignore_index=True)
    return result[_exit_shape_columns()]


def summarize_phase8h_concentration(trades: pd.DataFrame, config: Phase8HConfig = Phase8HConfig()) -> pd.DataFrame:
    """Summarize concentration by hypothesis, day, weekday, and RTH bucket."""
    if trades.empty:
        return pd.DataFrame(columns=_summary_columns())
    total_sessions = int(trades["trading_session"].nunique()) if "trading_session" in trades.columns else 0
    rows: list[dict[str, Any]] = [_summary_row(trades, "overall", "all", config, total_sessions=total_sessions)]
    for hypothesis_id, group in trades.groupby("hypothesis_id", sort=True):
        rows.append(_summary_row(group, "hypothesis", str(hypothesis_id), config, total_sessions=total_sessions))
    for session, group in trades.groupby("trading_session", sort=True):
        rows.append(_summary_row(group, "trading_session", str(session), config, total_sessions=1))
    for weekday, group in trades.groupby("weekday", sort=True):
        rows.append(_summary_row(group, "weekday", str(weekday), config, total_sessions=total_sessions))
    for bucket, group in trades.groupby("rth_bucket", sort=True):
        rows.append(_summary_row(group, "rth_bucket", str(bucket), config, total_sessions=total_sessions))
    return pd.DataFrame(rows)[_summary_columns()]


def summarize_phase8h_overlap(trades: pd.DataFrame) -> pd.DataFrame:
    """Measure event timestamp overlap between selected hypotheses."""
    if trades.empty or trades["hypothesis_id"].nunique() < 2:
        return pd.DataFrame(columns=_overlap_columns())
    rows: list[dict[str, Any]] = []
    for left_id, right_id in combinations(sorted(trades["hypothesis_id"].dropna().astype(str).unique()), 2):
        left = trades[trades["hypothesis_id"].astype(str).eq(left_id)]
        right = trades[trades["hypothesis_id"].astype(str).eq(right_id)]
        left_events = set(pd.to_datetime(left["event_time"]))
        right_events = set(pd.to_datetime(right["event_time"]))
        overlap = left_events & right_events
        union = left_events | right_events
        correlation = _shared_event_correlation(left, right)
        jaccard = len(overlap) / len(union) if union else 0.0
        rows.append(
            {
                "left_hypothesis_id": left_id,
                "right_hypothesis_id": right_id,
                "left_event_count": len(left_events),
                "right_event_count": len(right_events),
                "overlap_event_count": len(overlap),
                "event_jaccard_ratio": float(jaccard),
                "shared_pnl_correlation": round(float(correlation), 6) if correlation is not None else 0.0,
                "phase8h_overlap_label": "phase8h_duplicate_signal" if jaccard >= 0.75 else "distinct_signals",
            }
        )
    return pd.DataFrame(rows)[_overlap_columns()]


def render_phase8h_report(
    selected_inputs: pd.DataFrame,
    concentration_summary: pd.DataFrame,
    exit_shape_results: pd.DataFrame,
    overlap_summary: pd.DataFrame,
    config: Phase8HConfig,
    *,
    trade_log_path: Path,
    summary_path: Path,
    exit_shape_path: Path,
    report_path: Path,
    run_artifact_dir: Path | None = None,
) -> str:
    """Render the Phase 8H diagnostic report with a hard decision gate."""
    label_counts = concentration_summary["phase8h_label"].value_counts().to_dict() if not concentration_summary.empty else {}
    decision = _phase8h_decision(concentration_summary, exit_shape_results, overlap_summary)
    lines = [
        "# Phase 8H MNQ VWAP Concentration And Exit Diagnostic",
        "",
        "Generated by: `./.venv/Scripts/python.exe scripts/run_phase8h_mnq_vwap_concentration_exit_diagnostic.py`",
        "",
        "## Scope And Guardrails",
        "",
        "- Research/simulation only. No live trading, broker adapters, order routing, API-key storage, webhooks, or automated execution were added.",
        "- Phase 8H diagnoses Phase 8G MNQ VWAP concentration and exit shape; it is not a paper-trading promotion.",
        "- Exit-shape rows are deterministic diagnostics and avoid same-bar stop/target ordering assumptions.",
        "",
        "## Why Phase 8H Exists",
        "",
        "Phase 8G found positive MNQ VWAP horizon-close rows, but they were rejected as concentrated and fixed stop/target variants failed.",
        "Phase 8H checks whether the apparent edge survives leave-one-day-out, time-bucket, duplicate-signal, and simple non-intrabar exit diagnostics.",
        "",
        "## Selected Hypotheses",
        "",
        "| Hypothesis | Instrument | TF | Side | Family | Entry | Net PnL | 4-Tick Stress |",
        "| --- | --- | ---: | --- | --- | --- | ---: | ---: |",
    ]
    for _, row in selected_inputs.iterrows():
        lines.append(
            f"| `{row['hypothesis_id']}` | {row['instrument']} | {int(row['timeframe'])} | {row['side']} | {row['family']} | "
            f"{row.get('entry_delay', config.target_entry_delay)} | ${float(row.get('net_pnl', 0.0)):.2f} | ${float(row.get('slippage_4_ticks_net_pnl', 0.0)):.2f} |"
        )
    lines.extend(["", "## Baseline Concentration Summary", "", _summary_table(concentration_summary.head(20)), "", "## Duplicate / Overlap Summary", "", _overlap_table(overlap_summary), "", "## Exit-Shape Comparison", "", _exit_shape_table(exit_shape_results), "", "## Decision Rule", ""])
    lines.extend(
        [
            "- If leave-one-best-day-out stress PnL is still positive and concentration falls under `0.35`, the next milestone is narrow executable StrategySpec mapping.",
            "- If only a time bucket survives, implement a narrow pre-entry time/session filter diagnostic before StrategySpec mapping.",
            "- If excluding the best day makes stress PnL negative, park the MNQ VWAP event path as a concentration artifact and return to Phase 8D/8E queue expansion.",
            "- If VWAP hypotheses have high timestamp overlap, de-duplicate them and treat the better-scoring variant as one signal family.",
            "",
            f"Decision: `{decision}`",
            f"Label counts: `{label_counts}`",
            "",
            "## Outputs",
            "",
            f"- Trade log CSV: `{trade_log_path.as_posix()}`",
            f"- Concentration summary CSV: `{summary_path.as_posix()}`",
            f"- Exit-shape results CSV: `{exit_shape_path.as_posix()}`",
            f"- Report: `{report_path.as_posix()}`",
        ]
    )
    if run_artifact_dir is not None:
        lines.append(f"- Run-scoped artifacts: `{run_artifact_dir.as_posix()}`")
    lines.extend(["", "## Repro Command", "", "```bash", "./.venv/Scripts/python.exe scripts/run_phase8h_mnq_vwap_concentration_exit_diagnostic.py", "```", ""])
    return "\n".join(lines)


def _simulate_exit_shape_trades(selected_inputs: pd.DataFrame, data_by_symbol: dict[str, pd.DataFrame], exit_shape: str, config: Phase8HConfig) -> pd.DataFrame:
    if selected_inputs.empty:
        return pd.DataFrame(columns=_trade_columns())
    rows: list[pd.DataFrame] = []
    for _, candidate in selected_inputs.iterrows():
        hypothesis = candidate.to_dict()
        symbol = str(hypothesis["instrument"])
        bars = data_by_symbol.get(symbol, pd.DataFrame())
        if bars.empty:
            continue
        prepared = _prepare_bars(bars)
        event_positions = _event_positions(prepared, hypothesis)
        entry_delay = str(hypothesis.get("entry_delay", config.target_entry_delay))
        trades = _trades_for_exit_shape(prepared, hypothesis, event_positions, entry_delay, exit_shape, config)
        if trades.empty:
            continue
        rows.append(_with_trade_metadata(trades, hypothesis, entry_delay, exit_shape))
    if not rows:
        return pd.DataFrame(columns=_trade_columns())
    return pd.concat(rows, ignore_index=True)[_trade_columns()]


def _trades_for_exit_shape(
    prepared: pd.DataFrame,
    hypothesis: dict[str, Any],
    event_positions: list[int],
    entry_delay: str,
    exit_shape: str,
    config: Phase8HConfig,
) -> pd.DataFrame:
    if exit_shape.startswith("horizon_close_"):
        minutes = int(exit_shape.removeprefix("horizon_close_").removesuffix("m"))
        return _simulate_calibration_trades(prepared, hypothesis, event_positions, entry_delay, CalibrationVariant("none", "horizon_close", minutes))
    if exit_shape == "trailing_time_stop":
        ten = _simulate_calibration_trades(prepared, hypothesis, event_positions, entry_delay, CalibrationVariant("none", "horizon_close", 10))
        twenty = _simulate_calibration_trades(prepared, hypothesis, event_positions, entry_delay, CalibrationVariant("none", "horizon_close", 20))
        return _trailing_time_stop_trades(ten, twenty)
    if exit_shape == "session_bucket_flatten":
        baseline = _simulate_calibration_trades(prepared, hypothesis, event_positions, entry_delay, CalibrationVariant("none", "horizon_close", config.baseline_time_stop))
        if baseline.empty:
            return baseline
        annotated = _with_trade_metadata(baseline, hypothesis, entry_delay, f"horizon_close_{config.baseline_time_stop}m")
        profitable = annotated.groupby("rth_bucket", sort=False)["net_pnl"].sum()
        profitable = profitable[profitable > 0]
        if profitable.empty:
            return baseline.copy()
        latest_bucket = max(profitable.index, key=_bucket_order)
        kept = annotated[annotated["rth_bucket"].map(_bucket_order).le(_bucket_order(latest_bucket))]
        return kept[[column for column in baseline.columns if column in kept.columns]].copy()
    raise ValueError(f"Unsupported Phase 8H exit shape: {exit_shape}")


def _trailing_time_stop_trades(ten_minute: pd.DataFrame, twenty_minute: pd.DataFrame) -> pd.DataFrame:
    if ten_minute.empty:
        return ten_minute.copy()
    if twenty_minute.empty:
        return ten_minute.copy()
    twenty_by_event = {pd.Timestamp(row.event_time): row._asdict() for row in twenty_minute.itertuples(index=False)}
    rows: list[dict[str, Any]] = []
    for row in ten_minute.itertuples(index=False):
        event_time = pd.Timestamp(row.event_time)
        if float(row.gross_pnl) > 0 and event_time in twenty_by_event:
            rows.append(twenty_by_event[event_time])
        else:
            rows.append(row._asdict())
    return pd.DataFrame(rows, columns=ten_minute.columns)


def _shared_event_correlation(left: pd.DataFrame, right: pd.DataFrame) -> float | None:
    merged = left[["event_time", "net_pnl"]].merge(right[["event_time", "net_pnl"]], on="event_time", how="inner", suffixes=("_left", "_right"))
    if len(merged) < 2:
        return None
    return float(merged["net_pnl_left"].corr(merged["net_pnl_right"]))


def _empty_selection(event_results: pd.DataFrame, phase8g_results: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame(columns=list(event_results.columns) + [column for column in phase8g_results.columns if column not in event_results.columns])


def _require_columns(frame: pd.DataFrame, required: set[str], name: str) -> None:
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"{name} missing required columns: {sorted(missing)}")


def _summary_row(trades: pd.DataFrame, scope: str, key: str, config: Phase8HConfig, *, total_sessions: int) -> dict[str, Any]:
    ordered = trades.sort_values("entry_time") if "entry_time" in trades.columns else trades.copy()
    daily_net = ordered.groupby("trading_session")["net_pnl"].sum() if "trading_session" in ordered.columns else pd.Series(dtype=float)
    daily_stress = ordered.groupby("trading_session")["stress_net_pnl"].sum() if "trading_session" in ordered.columns else pd.Series(dtype=float)
    total_net = float(ordered["net_pnl"].sum())
    total_stress = float(ordered["stress_net_pnl"].sum())
    best_day = str(daily_net.idxmax()) if not daily_net.empty else ""
    best_day_net = float(daily_net.max()) if not daily_net.empty else 0.0
    best_day_stress = float(daily_stress.get(best_day, 0.0)) if best_day else 0.0
    best_trade_net = float(ordered["net_pnl"].max()) if not ordered.empty else 0.0
    session_count = int(ordered["trading_session"].nunique()) if "trading_session" in ordered.columns else 0
    row = {
        "summary_scope": scope,
        "summary_key": key,
        "trade_count": int(len(ordered)),
        "session_count": session_count,
        "active_session_pct": round(float(session_count / max(total_sessions, 1)), 6),
        "net_pnl": round(total_net, 4),
        "stress_net_pnl": round(total_stress, 4),
        "max_drawdown": round(_max_drawdown(ordered), 4),
        "best_day": best_day,
        "best_day_net_pnl": round(best_day_net, 4),
        "best_day_concentration": round(max(best_day_net, 0.0) / total_net, 6) if total_net > 0 else 1.0,
        "best_trade_concentration": round(max(best_trade_net, 0.0) / total_net, 6) if total_net > 0 else 1.0,
        "net_excluding_best_day": round(total_net - best_day_net, 4),
        "stress_excluding_best_day": round(total_stress - best_day_stress, 4),
    }
    row["phase8h_label"] = _phase8h_label(row, config)
    row["phase8h_notes"] = _phase8h_notes(row, config)
    return row


def _phase8h_label(row: dict[str, Any], config: Phase8HConfig) -> str:
    if int(row["trade_count"]) < config.min_trades:
        return "rejected_cost_or_drawdown"
    if float(row["stress_net_pnl"]) <= 0:
        return "rejected_cost_or_drawdown"
    if float(row["net_excluding_best_day"]) <= 0 or float(row["stress_excluding_best_day"]) <= 0:
        return "rejected_concentration_artifact"
    if float(row["best_day_concentration"]) > config.concentration_limit or float(row["best_trade_concentration"]) > config.concentration_limit:
        return "rejected_concentration_artifact"
    return "phase8h_candidate_filter_design"


def _phase8h_notes(row: dict[str, Any], config: Phase8HConfig) -> str:
    notes: list[str] = []
    if int(row["trade_count"]) < config.min_trades:
        notes.append(f"only {int(row['trade_count'])} trades; minimum is {config.min_trades}")
    if float(row["stress_net_pnl"]) <= 0:
        notes.append("fails 4-tick stress")
    if float(row["net_excluding_best_day"]) <= 0 or float(row["stress_excluding_best_day"]) <= 0:
        notes.append("edge fails after excluding best day")
    if float(row["best_day_concentration"]) > config.concentration_limit:
        notes.append("one-day concentration risk")
    if float(row["best_trade_concentration"]) > config.concentration_limit:
        notes.append("one-trade concentration risk")
    return "; ".join(notes) if notes else "survives leave-one-day-out concentration diagnostic"


def _max_drawdown(trades: pd.DataFrame) -> float:
    if trades.empty:
        return 0.0
    curve = trades["net_pnl"].cumsum()
    drawdowns = curve - curve.cummax()
    return float(drawdowns.min()) if not drawdowns.empty else 0.0


def _with_trade_metadata(trades: pd.DataFrame, hypothesis: dict[str, Any], entry_delay: str, exit_shape: str) -> pd.DataFrame:
    out = trades.copy()
    out.insert(0, "hypothesis_id", str(hypothesis["hypothesis_id"]))
    out.insert(1, "instrument", str(hypothesis["instrument"]))
    out.insert(2, "family", str(hypothesis["family"]))
    out.insert(3, "side_filter", str(hypothesis["side"]))
    out.insert(4, "timeframe", int(hypothesis["timeframe"]))
    out.insert(5, "entry_delay", entry_delay)
    out.insert(6, "exit_shape", exit_shape)
    entry_time = pd.to_datetime(out["entry_time"])
    out["minute_of_day"] = entry_time.dt.hour * 60 + entry_time.dt.minute
    out["rth_bucket"] = out["minute_of_day"].map(_rth_bucket)
    out["weekday"] = entry_time.dt.day_name()
    return out


def _phase8h_decision(concentration_summary: pd.DataFrame, exit_shape_results: pd.DataFrame, overlap_summary: pd.DataFrame) -> str:
    if not overlap_summary.empty and overlap_summary["phase8h_overlap_label"].eq("phase8h_duplicate_signal").any():
        return "phase8h_duplicate_signal"
    if not concentration_summary.empty:
        overall = concentration_summary[concentration_summary["summary_scope"].eq("overall")]
        if not overall.empty:
            label = str(overall.iloc[0]["phase8h_label"])
            if label == "phase8h_candidate_filter_design":
                return label
            bucket_rows = concentration_summary[concentration_summary["summary_scope"].eq("rth_bucket")]
            if not bucket_rows.empty and bucket_rows["phase8h_label"].eq("phase8h_candidate_filter_design").any():
                return "phase8h_needs_time_filter"
            return label
    if not exit_shape_results.empty and exit_shape_results["phase8h_label"].eq("phase8h_candidate_filter_design").any():
        return "phase8h_candidate_filter_design"
    return "rejected_cost_or_drawdown"


def _summary_table(summary: pd.DataFrame) -> str:
    if summary.empty:
        return "No concentration rows."
    lines = ["| Scope | Key | Label | Net PnL | Stress | Trades | Best Day Conc. | Notes |", "| --- | --- | --- | ---: | ---: | ---: | ---: | --- |"]
    for _, row in summary.iterrows():
        lines.append(
            f"| {row['summary_scope']} | `{row['summary_key']}` | {row['phase8h_label']} | ${float(row['net_pnl']):.2f} | "
            f"${float(row['stress_net_pnl']):.2f} | {int(row['trade_count'])} | {float(row['best_day_concentration']):.3f} | {row['phase8h_notes']} |"
        )
    return "\n".join(lines)


def _overlap_table(overlap: pd.DataFrame) -> str:
    if overlap.empty:
        return "No duplicate-overlap pairs available."
    lines = ["| Left | Right | Overlap | Jaccard | Correlation | Label |", "| --- | --- | ---: | ---: | ---: | --- |"]
    for _, row in overlap.iterrows():
        lines.append(
            f"| `{row['left_hypothesis_id']}` | `{row['right_hypothesis_id']}` | {int(row['overlap_event_count'])} | "
            f"{float(row['event_jaccard_ratio']):.3f} | {float(row['shared_pnl_correlation']):.3f} | {row['phase8h_overlap_label']} |"
        )
    return "\n".join(lines)


def _exit_shape_table(exit_results: pd.DataFrame) -> str:
    if exit_results.empty:
        return "No exit-shape rows."
    lines = ["| Exit | Hypothesis | Label | Net PnL | Stress | Trades | Max DD | Notes |", "| --- | --- | --- | ---: | ---: | ---: | ---: | --- |"]
    for _, row in exit_results.iterrows():
        hypothesis = row["summary_key"] if "summary_key" in row else row.get("hypothesis_id", "")
        lines.append(
            f"| {row['exit_shape']} | `{hypothesis}` | {row['phase8h_label']} | ${float(row['net_pnl']):.2f} | "
            f"${float(row['stress_net_pnl']):.2f} | {int(row['trade_count'])} | ${float(row['max_drawdown']):.2f} | {row['phase8h_notes']} |"
        )
    return "\n".join(lines)


def _rth_bucket(minute_of_day: int) -> str:
    if minute_of_day < 10 * 60:
        return "09:30-10:00"
    if minute_of_day < 11 * 60:
        return "10:00-11:00"
    if minute_of_day < 12 * 60:
        return "11:00-12:00"
    if minute_of_day < 14 * 60:
        return "12:00-14:00"
    if minute_of_day < 15 * 60 + 30:
        return "14:00-15:30"
    return "15:30-16:00"


def _bucket_order(bucket: str) -> int:
    order = {
        "09:30-10:00": 0,
        "10:00-11:00": 1,
        "11:00-12:00": 2,
        "12:00-14:00": 3,
        "14:00-15:30": 4,
        "15:30-16:00": 5,
    }
    return order.get(str(bucket), 99)


def _trade_columns() -> list[str]:
    return [
        "hypothesis_id",
        "instrument",
        "family",
        "side_filter",
        "timeframe",
        "entry_delay",
        "exit_shape",
        "event_time",
        "entry_time",
        "exit_time",
        "trading_session",
        "side",
        "entry_price",
        "exit_price",
        "exit_reason",
        "gross_pnl",
        "net_pnl",
        "stress_net_pnl",
        "same_bar_ambiguity",
        "minute_of_day",
        "rth_bucket",
        "weekday",
    ]


def _summary_columns() -> list[str]:
    return [
        "summary_scope",
        "summary_key",
        "trade_count",
        "session_count",
        "active_session_pct",
        "net_pnl",
        "stress_net_pnl",
        "max_drawdown",
        "best_day",
        "best_day_net_pnl",
        "best_day_concentration",
        "best_trade_concentration",
        "net_excluding_best_day",
        "stress_excluding_best_day",
        "phase8h_label",
        "phase8h_notes",
    ]


def _exit_shape_columns() -> list[str]:
    return ["exit_shape", *_summary_columns()]


def _overlap_columns() -> list[str]:
    return [
        "left_hypothesis_id",
        "right_hypothesis_id",
        "left_event_count",
        "right_event_count",
        "overlap_event_count",
        "event_jaccard_ratio",
        "shared_pnl_correlation",
        "phase8h_overlap_label",
    ]
