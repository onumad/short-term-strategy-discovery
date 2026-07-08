from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from .backtest import split_sessions


@dataclass(frozen=True)
class Phase8IConfig:
    min_trades: int = 250
    concentration_limit: float = 0.35
    drawdown_limit: float = -6_000.0


@dataclass(frozen=True)
class Phase8IFilterSpec:
    filter_id: str
    filter_family: str
    params: dict[str, Any]
    description: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "filter_id": self.filter_id,
            "filter_family": self.filter_family,
            "params": dict(self.params),
            "description": self.description,
        }


def build_phase8i_filter_specs() -> list[Phase8IFilterSpec]:
    """Build deterministic pre-entry filters for the de-duplicated MNQ VWAP signal."""
    return [
        Phase8IFilterSpec("baseline_all", "all", {}, "Keep every de-duplicated baseline trade."),
        Phase8IFilterSpec("time_window:first_30", "time_window", {"start": "09:30", "end": "10:00"}, "Only entries in the first RTH half-hour."),
        Phase8IFilterSpec("time_window:first_90", "time_window", {"start": "09:30", "end": "11:00"}, "Only entries before 11:00 ET."),
        Phase8IFilterSpec("time_window:morning", "time_window", {"start": "09:30", "end": "12:00"}, "Only entries before noon ET."),
        Phase8IFilterSpec("time_window:pre_14_00", "time_window", {"start": "09:30", "end": "14:00"}, "Only entries before 14:00 ET."),
        Phase8IFilterSpec("time_window:midday_12_14", "time_window", {"start": "12:00", "end": "14:00"}, "Only midday continuation entries."),
        Phase8IFilterSpec("exclude_window:late_after_14", "exclude_time_window", {"exclude_start": "14:00", "exclude_end": "16:00"}, "Exclude entries at/after 14:00 ET."),
        Phase8IFilterSpec("weekday:mon_thu_fri", "weekday", {"days": [0, 3, 4]}, "Keep Monday/Thursday/Friday entries."),
        Phase8IFilterSpec("weekday:exclude_tue_wed", "weekday", {"exclude_days": [1, 2]}, "Exclude Tuesday/Wednesday entries."),
    ]


def select_phase8i_source_trades(trades: pd.DataFrame, overlap_summary: pd.DataFrame, config: Phase8IConfig = Phase8IConfig()) -> pd.DataFrame:
    """Select one canonical hypothesis from duplicate Phase 8H trade rows."""
    del config
    if trades.empty:
        return trades.copy()
    out = trades.copy()
    keep_ids: set[str] | None = None
    if not overlap_summary.empty and "phase8h_overlap_label" in overlap_summary.columns:
        duplicate_rows = overlap_summary[overlap_summary["phase8h_overlap_label"].eq("phase8h_duplicate_signal")]
        if not duplicate_rows.empty:
            keep_ids = {str(duplicate_rows.iloc[0]["left_hypothesis_id"])}
    if keep_ids is None:
        keep_ids = {str(out["hypothesis_id"].dropna().astype(str).iloc[0])}
    selected = out[out["hypothesis_id"].astype(str).isin(keep_ids)].copy().reset_index(drop=True)
    selected["phase8i_source_note"] = "de-duplicated Phase 8H duplicate signal to one canonical hypothesis"
    return selected


def apply_phase8i_filter(trades: pd.DataFrame, spec: Phase8IFilterSpec) -> pd.DataFrame:
    """Apply a no-lookahead filter using only pre-entry timestamp/session metadata."""
    if trades.empty:
        return trades.copy()
    out = trades.copy()
    out["entry_time"] = _parse_entry_time(out["entry_time"])
    if spec.filter_family == "all":
        return out.reset_index(drop=True)
    if spec.filter_family == "time_window":
        minutes = _entry_minutes(out)
        start = _hhmm_to_minutes(str(spec.params["start"]))
        end = _hhmm_to_minutes(str(spec.params["end"]))
        out = out[(minutes >= start) & (minutes < end)]
    elif spec.filter_family == "exclude_time_window":
        minutes = _entry_minutes(out)
        start = _hhmm_to_minutes(str(spec.params["exclude_start"]))
        end = _hhmm_to_minutes(str(spec.params["exclude_end"]))
        out = out[(minutes < start) | (minutes >= end)]
    elif spec.filter_family == "weekday":
        dayofweek = out["entry_time"].dt.dayofweek
        if "days" in spec.params:
            days = {int(day) for day in spec.params["days"]}
            out = out[dayofweek.isin(days)]
        elif "exclude_days" in spec.params:
            days = {int(day) for day in spec.params["exclude_days"]}
            out = out[~dayofweek.isin(days)]
        else:
            raise ValueError(f"Unsupported Phase 8I weekday params: {spec.params}")
    else:
        raise ValueError(f"Unsupported Phase 8I filter family: {spec.filter_family}")
    return out.reset_index(drop=True)


def evaluate_phase8i_filters(trades: pd.DataFrame, filter_specs: list[Phase8IFilterSpec], config: Phase8IConfig = Phase8IConfig()) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    complete_sessions = sorted(trades["trading_session"].dropna().unique().tolist()) if not trades.empty else []
    split_map = split_sessions(complete_sessions)
    for spec in filter_specs:
        kept = apply_phase8i_filter(trades, spec)
        rows.append(_summarize_filter(spec, kept, complete_sessions, split_map, config))
    if not rows:
        return pd.DataFrame(columns=_result_columns())
    results = pd.DataFrame(rows)
    results["_label_priority"] = results["phase8i_label"].map(_label_priority)
    results = results.sort_values(
        ["_label_priority", "phase8i_score", "holdout_pnl", "stress_net_pnl"],
        ascending=[False, False, False, False],
    ).drop(columns=["_label_priority"]).reset_index(drop=True)
    results.insert(0, "phase8i_rank", range(1, len(results) + 1))
    return results[["phase8i_rank", *_result_columns()]]


def render_phase8i_report(
    results: pd.DataFrame,
    config: Phase8IConfig,
    *,
    source_trade_count: int,
    deduped_trade_count: int,
    results_path: Path,
    report_path: Path,
    run_artifact_dir: Path | None = None,
) -> str:
    label_counts = results["phase8i_label"].value_counts().to_dict() if not results.empty and "phase8i_label" in results.columns else {}
    lines = [
        "# Phase 8I No-Lookahead Time/Session Filter",
        "",
        "Generated by: `./.venv/Scripts/python.exe scripts/run_phase8i_no_lookahead_filter.py`",
        "",
        "## Scope And Guardrails",
        "",
        "- Research/simulation only. No live trading, broker adapters, order routing, API-key storage, webhooks, or automated execution were added.",
        "- Phase 8I applies fixed pre-entry time/session filters to a de-duplicated Phase 8H MNQ VWAP trade log.",
        "- Filters may use entry timestamp, weekday, and session metadata only; labels are diagnostic and not paper-trading promotion.",
        "",
        "## Inputs",
        "",
        f"- Source Phase 8H trade rows: `{source_trade_count}`",
        f"- De-duplicated Phase 8I trade rows: `{deduped_trade_count}`",
        f"- Minimum kept trades: `{config.min_trades}`",
        f"- Concentration limit: `{config.concentration_limit}`",
        "",
        "## Label Counts",
        "",
        f"- `{label_counts}`",
        "",
        "## Ranked Filters",
        "",
        "| Rank | Filter | Label | Score | Trades | Active % | Net PnL | Stress | Disc. | Val. | Holdout | DD | Day Conc. | Trade Conc. | Notes |",
        "| ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for _, row in results.head(12).iterrows():
        lines.append(
            f"| {int(row['phase8i_rank'])} | `{row['filter_id']}` | {row['phase8i_label']} | {float(row['phase8i_score']):.2f} | "
            f"{int(row['kept_trade_count'])} | {float(row['active_session_pct']) * 100:.1f}% | ${float(row['net_pnl']):.2f} | ${float(row['stress_net_pnl']):.2f} | "
            f"${float(row['discovery_pnl']):.2f} | ${float(row['validation_pnl']):.2f} | ${float(row['holdout_pnl']):.2f} | ${float(row['max_drawdown']):.2f} | "
            f"{float(row['best_day_concentration']) * 100:.1f}% | {float(row['best_trade_concentration']) * 100:.1f}% | {row['phase8i_notes']} |"
        )
    lines.extend(
        [
            "",
            "## Decision Rule",
            "",
            "- `phase8i_filter_candidate` means a fixed no-lookahead filter survived stress, split, drawdown, and concentration gates and deserves later walk-forward-aware StrategySpec mapping.",
            "- `phase8i_watchlist_needs_validation` means the filter is positive but failed at least one split or concentration gate.",
            "- `rejected` or `insufficient_activity` means the filter should not be deepened without new evidence.",
            "- No Phase 8I result is a paper-trading or live-trading promotion.",
            "",
            "## Outputs",
            "",
            f"- Results CSV: `{results_path.as_posix()}`",
            f"- Report: `{report_path.as_posix()}`",
        ]
    )
    if run_artifact_dir is not None:
        lines.append(f"- Run-scoped artifacts: `{run_artifact_dir.as_posix()}`")
    lines.extend(["", "## Repro Command", "", "```bash", "./.venv/Scripts/python.exe scripts/run_phase8i_no_lookahead_filter.py", "```", ""])
    return "\n".join(lines)


def _summarize_filter(
    spec: Phase8IFilterSpec,
    trades: pd.DataFrame,
    complete_sessions: list[Any],
    split_map: dict[Any, str],
    config: Phase8IConfig,
) -> dict[str, Any]:
    base = {
        "filter_id": spec.filter_id,
        "filter_family": spec.filter_family,
        "filter_params_json": json.dumps(spec.params, sort_keys=True),
        "description": spec.description,
    }
    if trades.empty:
        out = {
            **base,
            "kept_trade_count": 0,
            "kept_active_sessions": 0,
            "active_session_pct": 0.0,
            "net_pnl": 0.0,
            "stress_net_pnl": 0.0,
            "discovery_pnl": 0.0,
            "validation_pnl": 0.0,
            "holdout_pnl": 0.0,
            "max_drawdown": 0.0,
            "best_day_concentration": 0.0,
            "best_trade_concentration": 0.0,
        }
        out["phase8i_score"] = -999.0
        out["phase8i_label"] = "insufficient_activity"
        out["phase8i_notes"] = "filter kept no trades"
        return out

    ordered = trades.sort_values(["entry_time", "exit_time"]).copy()
    ordered["split"] = ordered["trading_session"].map(split_map).fillna("unknown")
    net = float(ordered["net_pnl"].sum())
    stress = float(ordered["stress_net_pnl"].sum())
    discovery = float(ordered.loc[ordered["split"].eq("discovery"), "net_pnl"].sum())
    validation = float(ordered.loc[ordered["split"].eq("validation"), "net_pnl"].sum())
    holdout = float(ordered.loc[ordered["split"].eq("holdout"), "net_pnl"].sum())
    equity = ordered["net_pnl"].cumsum()
    drawdown = float((equity - equity.cummax()).min()) if not equity.empty else 0.0
    daily = ordered.groupby("trading_session")["net_pnl"].sum()
    active_sessions = int(ordered["trading_session"].nunique())
    active_pct = active_sessions / len(complete_sessions) if complete_sessions else 0.0
    best_day_conc = _concentration(float(daily.max()) if not daily.empty else 0.0, net)
    best_trade_conc = _concentration(float(ordered["net_pnl"].max()), net)
    out = {
        **base,
        "kept_trade_count": int(len(ordered)),
        "kept_active_sessions": active_sessions,
        "active_session_pct": round(float(active_pct), 6),
        "net_pnl": round(net, 2),
        "stress_net_pnl": round(stress, 2),
        "discovery_pnl": round(discovery, 2),
        "validation_pnl": round(validation, 2),
        "holdout_pnl": round(holdout, 2),
        "max_drawdown": round(drawdown, 2),
        "best_day_concentration": round(best_day_conc, 6),
        "best_trade_concentration": round(best_trade_conc, 6),
    }
    out["phase8i_score"] = round(_phase8i_score(out), 4)
    out["phase8i_label"] = _phase8i_label(out, config)
    out["phase8i_notes"] = _phase8i_notes(out, config)
    return out


def _phase8i_score(row: dict[str, Any]) -> float:
    score = 0.0
    score += max(min(float(row["stress_net_pnl"]) / 4_000.0, 2.0), -2.0) * 30.0
    score += max(min(float(row["holdout_pnl"]) / 1_500.0, 2.0), -2.0) * 18.0
    score += max(min(float(row["validation_pnl"]) / 1_500.0, 2.0), -2.0) * 12.0
    score += min(float(row["active_session_pct"]), 0.50) * 10.0
    score += min(float(row["kept_trade_count"]) / 500.0, 1.0) * 8.0
    score -= min(abs(float(row["max_drawdown"])) / 6_000.0, 2.0) * 14.0
    score -= max(float(row["best_day_concentration"]) - 0.35, 0.0) * 140.0
    score -= max(float(row["best_trade_concentration"]) - 0.35, 0.0) * 120.0
    return float(score)


def _phase8i_label(row: dict[str, Any], config: Phase8IConfig) -> str:
    if int(row["kept_trade_count"]) < config.min_trades:
        return "insufficient_activity"
    if float(row["net_pnl"]) <= 0 or float(row["stress_net_pnl"]) <= 0:
        return "rejected"
    hard_fail = (
        float(row["discovery_pnl"]) <= 0
        or float(row["validation_pnl"]) <= 0
        or float(row["holdout_pnl"]) <= 0
        or float(row["max_drawdown"]) < config.drawdown_limit
    )
    concentration_fail = float(row["best_day_concentration"]) > config.concentration_limit or float(row["best_trade_concentration"]) > config.concentration_limit
    if hard_fail or concentration_fail:
        return "phase8i_watchlist_needs_validation"
    return "phase8i_filter_candidate"


def _phase8i_notes(row: dict[str, Any], config: Phase8IConfig) -> str:
    notes: list[str] = []
    if int(row["kept_trade_count"]) < config.min_trades:
        notes.append(f"only {int(row['kept_trade_count'])} trades; minimum is {config.min_trades}")
    if float(row["net_pnl"]) <= 0:
        notes.append("negative net PnL")
    if float(row["stress_net_pnl"]) <= 0:
        notes.append("fails 4-tick stress")
    for split in ("discovery", "validation", "holdout"):
        if float(row[f"{split}_pnl"]) <= 0:
            notes.append(f"negative {split} split")
    if float(row["max_drawdown"]) < config.drawdown_limit:
        notes.append("drawdown beyond limit")
    if float(row["best_day_concentration"]) > config.concentration_limit:
        notes.append("one-day concentration risk")
    if float(row["best_trade_concentration"]) > config.concentration_limit:
        notes.append("one-trade concentration risk")
    return "; ".join(notes) if notes else "survives split-aware no-lookahead filter diagnostic"


def _label_priority(label: str) -> int:
    return {
        "phase8i_filter_candidate": 3,
        "phase8i_watchlist_needs_validation": 2,
        "rejected": 1,
        "insufficient_activity": 0,
    }.get(str(label), 0)


def _entry_minutes(trades: pd.DataFrame) -> pd.Series:
    return trades["entry_time"].dt.hour * 60 + trades["entry_time"].dt.minute


def _parse_entry_time(values: pd.Series) -> pd.Series:
    return pd.to_datetime(values, utc=True).dt.tz_convert("America/New_York")


def _hhmm_to_minutes(value: str) -> int:
    hour, minute = value.split(":")
    return int(hour) * 60 + int(minute)


def _concentration(best: float, total: float) -> float:
    if total <= 0:
        return 1.0
    return float(max(best, 0.0) / total)


def _result_columns() -> list[str]:
    return [
        "filter_id",
        "filter_family",
        "filter_params_json",
        "description",
        "kept_trade_count",
        "kept_active_sessions",
        "active_session_pct",
        "net_pnl",
        "stress_net_pnl",
        "discovery_pnl",
        "validation_pnl",
        "holdout_pnl",
        "max_drawdown",
        "best_day_concentration",
        "best_trade_concentration",
        "phase8i_score",
        "phase8i_label",
        "phase8i_notes",
    ]
