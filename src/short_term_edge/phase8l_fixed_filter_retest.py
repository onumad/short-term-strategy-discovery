from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from .backtest import split_sessions


@dataclass(frozen=True)
class Phase8LConfig:
    max_action_specs: int = 8
    min_trades: int = 250
    train_sessions: int = 75
    validation_sessions: int = 25
    test_sessions: int = 25
    step_sessions: int = 25
    min_folds: int = 3
    concentration_limit: float = 0.35
    trade_concentration_limit: float = 0.20
    drawdown_limit: float = -6_000.0


@dataclass(frozen=True)
class Phase8LFilterSpec:
    filter_id: str
    filter_family: str
    axis: str
    bucket: str
    source_action_id: str
    source_action_rank: int
    action_rule: str
    evidence: str
    promotion_allowed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "filter_id": self.filter_id,
            "filter_family": self.filter_family,
            "axis": self.axis,
            "bucket": self.bucket,
            "source_action_id": self.source_action_id,
            "source_action_rank": self.source_action_rank,
            "action_rule": self.action_rule,
            "evidence": self.evidence,
            "promotion_allowed": self.promotion_allowed,
        }


def build_phase8l_filter_specs(candidate_actions: pd.DataFrame, config: Phase8LConfig = Phase8LConfig()) -> list[Phase8LFilterSpec]:
    """Convert Phase 8K diagnostic-only fixed filter actions into fixed retest specs."""
    specs = [
        Phase8LFilterSpec(
            filter_id="baseline_phase8j",
            filter_family="baseline",
            axis="all",
            bucket="all",
            source_action_id="baseline_phase8j",
            source_action_rank=0,
            action_rule="keep all Phase 8J filtered trades",
            evidence="Phase 8J pre-14 baseline for Phase 8L comparison",
        )
    ]
    if candidate_actions.empty:
        return specs
    actions = candidate_actions[candidate_actions["action_type"].astype(str).eq("fixed_filter_retest")].copy()
    actions = actions.sort_values("phase8k_action_rank").head(config.max_action_specs)
    for _, row in actions.iterrows():
        axis = str(row["source_axis"])
        bucket = str(row["source_bucket"])
        specs.append(
            Phase8LFilterSpec(
                filter_id=f"exclude:{axis}:{bucket}",
                filter_family="exclude_bucket",
                axis=axis,
                bucket=bucket,
                source_action_id=str(row["candidate_action_id"]),
                source_action_rank=int(row["phase8k_action_rank"]),
                action_rule=str(row["action_rule"]),
                evidence=str(row.get("evidence", "")),
                promotion_allowed=False,
            )
        )
    return specs


def apply_phase8l_filter(trades: pd.DataFrame, spec: Phase8LFilterSpec) -> pd.DataFrame:
    """Apply a fixed no-lookahead Phase 8L filter using entry/session metadata."""
    if trades.empty:
        return trades.copy()
    out = _prepare_trades(trades)
    if spec.filter_family == "baseline":
        kept = out.copy()
    elif spec.filter_family == "exclude_bucket":
        if spec.axis not in kept_axes():
            raise ValueError(f"Unsupported Phase 8L filter axis: {spec.axis}")
        if spec.axis not in out.columns:
            raise ValueError(f"Phase 8L trades are missing required axis column: {spec.axis}")
        kept = out[~out[spec.axis].astype(str).eq(spec.bucket)].copy()
    else:
        raise ValueError(f"Unsupported Phase 8L filter family: {spec.filter_family}")
    kept["filter_id"] = spec.filter_id
    kept["phase8l_filter_id"] = spec.filter_id
    kept["phase8l_action_rule"] = spec.action_rule
    kept["phase8l_source_action_id"] = spec.source_action_id
    kept["promotion_allowed"] = spec.promotion_allowed
    return kept.sort_values(["entry_time", "exit_time"]).reset_index(drop=True)


def evaluate_phase8l_filters(trades: pd.DataFrame, specs: list[Phase8LFilterSpec], config: Phase8LConfig = Phase8LConfig()) -> tuple[pd.DataFrame, pd.DataFrame]:
    if trades.empty:
        raise ValueError("Phase 8L requires non-empty Phase 8J filtered trades")
    prepared = _prepare_trades(trades)
    complete_sessions = sorted(prepared["trading_session"].dropna().astype(str).unique().tolist())
    split_map = split_sessions(complete_sessions)
    rows: list[dict[str, Any]] = []
    logs: list[pd.DataFrame] = []
    for spec in specs:
        filtered = apply_phase8l_filter(prepared, spec)
        logs.append(filtered)
        rows.append(_summarize_spec(spec, filtered, prepared, complete_sessions, split_map, config))
    if not rows:
        return pd.DataFrame(columns=_result_columns()), pd.DataFrame()
    results = pd.DataFrame(rows)
    results["_label_priority"] = results["phase8l_label"].map(_label_priority).fillna(0)
    results = results.sort_values(
        ["_label_priority", "phase8l_score", "walk_forward_test_stress_net_pnl", "holdout_pnl", "source_action_rank"],
        ascending=[False, False, False, False, True],
    ).drop(columns=["_label_priority"]).reset_index(drop=True)
    results.insert(0, "phase8l_filter_rank", range(1, len(results) + 1))
    if logs:
        filtered_logs = pd.concat(logs, ignore_index=True)
    else:
        filtered_logs = pd.DataFrame()
    return results[["phase8l_filter_rank", *_result_columns()]], filtered_logs


def render_phase8l_report(
    results: pd.DataFrame,
    config: Phase8LConfig,
    *,
    results_path: Path,
    specs_path: Path,
    filtered_trade_logs_path: Path,
    report_path: Path,
    run_artifact_dir: Path | None = None,
) -> str:
    label_counts = results["phase8l_label"].value_counts().to_dict() if not results.empty and "phase8l_label" in results.columns else {}
    lines = [
        "# Phase 8L Fixed No-Lookahead Filter Retest",
        "",
        "Generated by: `./.venv/Scripts/python.exe scripts/run_phase8l_fixed_filter_retest.py`",
        "",
        "## Scope And Guardrails",
        "",
        "- Research/simulation only. No live trading, broker adapters, order routing, API-key storage, webhooks, or automated execution were added.",
        "- Phase 8L retests Phase 8K diagnostic buckets as fixed no-lookahead filters on the Phase 8J trade log.",
        "- No paper-trading promotion: a Phase 8L candidate only earns a later StrategySpec remap/stress test.",
        "",
        "## Summary",
        "",
        f"- Label counts: `{label_counts}`",
        f"- Minimum trades: `{config.min_trades}`",
        f"- Walk-forward window: `{config.train_sessions}/{config.validation_sessions}/{config.test_sessions}` sessions, step `{config.step_sessions}`",
        "",
        "| Rank | Filter | Label | Score | Trades | Removed | Net | Stress | Disc. | Val. | Holdout | WF Test | WF Stress | Positive Folds | DD | Day Conc. | Notes |",
        "| ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for _, row in results.head(12).iterrows():
        lines.append(
            f"| {int(row['phase8l_filter_rank'])} | `{row['filter_id']}` | {row['phase8l_label']} | {float(row['phase8l_score']):.2f} | "
            f"{int(row['kept_trade_count'])} | {int(row['removed_trade_count'])} | ${float(row['net_pnl']):.2f} | ${float(row['stress_net_pnl']):.2f} | "
            f"${float(row['discovery_pnl']):.2f} | ${float(row['validation_pnl']):.2f} | ${float(row['holdout_pnl']):.2f} | "
            f"${float(row['walk_forward_test_net_pnl']):.2f} | ${float(row['walk_forward_test_stress_net_pnl']):.2f} | "
            f"{float(row['walk_forward_test_positive_fold_pct']) * 100:.1f}% | ${float(row['max_drawdown']):.2f} | "
            f"{float(row['best_day_concentration']) * 100:.1f}% | {row['phase8l_notes']} |"
        )
    lines.extend(
        [
            "",
            "## Decision Rule",
            "",
            "- `phase8l_fixed_filter_candidate` means a fixed diagnostic filter survived split, stress, walk-forward, drawdown, and concentration gates; it still is not paper/live approval.",
            "- `phase8l_watchlist_needs_strategy_remap` means aggregate behavior improved but at least one independent gate remains weak.",
            "- `rejected` or `insufficient_activity` means the rule should not be deepened without new evidence.",
            "",
            "## Outputs",
            "",
            f"- Results CSV: `{results_path.as_posix()}`",
            f"- Specs JSON: `{specs_path.as_posix()}`",
            f"- Filtered trade logs CSV: `{filtered_trade_logs_path.as_posix()}`",
            f"- Report: `{report_path.as_posix()}`",
        ]
    )
    if run_artifact_dir is not None:
        lines.append(f"- Run-scoped artifacts: `{run_artifact_dir.as_posix()}`")
    lines.extend(["", "## Repro Command", "", "```bash", "./.venv/Scripts/python.exe scripts/run_phase8l_fixed_filter_retest.py", "```", ""])
    return "\n".join(lines)


def kept_axes() -> set[str]:
    return {"weekday", "minute_bucket", "rth_bucket"}


def _prepare_trades(trades: pd.DataFrame) -> pd.DataFrame:
    out = trades.copy()
    out["entry_time"] = pd.to_datetime(out["entry_time"], utc=True).dt.tz_convert("America/New_York")
    if "exit_time" in out.columns:
        out["exit_time"] = pd.to_datetime(out["exit_time"], utc=True).dt.tz_convert("America/New_York")
    else:
        out["exit_time"] = out["entry_time"]
    out["trading_session"] = out["trading_session"].astype(str)
    if "stress_net_pnl" not in out.columns:
        out["stress_net_pnl"] = out["net_pnl"]
    minutes = out["entry_time"].dt.hour * 60 + out["entry_time"].dt.minute
    out["minute_bucket"] = minutes.map(_minute_bucket)
    if "weekday" not in out.columns:
        out["weekday"] = out["entry_time"].dt.day_name()
    if "rth_bucket" not in out.columns:
        out["rth_bucket"] = out["minute_bucket"]
    return out


def _summarize_spec(
    spec: Phase8LFilterSpec,
    filtered: pd.DataFrame,
    source: pd.DataFrame,
    complete_sessions: list[Any],
    split_map: dict[Any, str],
    config: Phase8LConfig,
) -> dict[str, Any]:
    base = {
        "filter_id": spec.filter_id,
        "filter_family": spec.filter_family,
        "axis": spec.axis,
        "bucket": spec.bucket,
        "source_action_id": spec.source_action_id,
        "source_action_rank": spec.source_action_rank,
        "action_rule": spec.action_rule,
        "evidence": spec.evidence,
        "promotion_allowed": bool(spec.promotion_allowed),
    }
    if filtered.empty:
        row = {
            **base,
            "kept_trade_count": 0,
            "removed_trade_count": int(len(source)),
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
            **_empty_walk_forward_summary(),
        }
        row["phase8l_score"] = -999.0
        row["phase8l_label"] = "insufficient_activity"
        row["phase8l_notes"] = "filter kept no trades"
        return row

    ordered = filtered.sort_values(["entry_time", "exit_time"]).copy()
    ordered["split"] = ordered["trading_session"].map(split_map).fillna("unknown")
    net = float(ordered["net_pnl"].sum())
    stress = float(ordered["stress_net_pnl"].sum())
    equity = ordered["net_pnl"].cumsum()
    drawdown = float((equity - equity.cummax()).min()) if not equity.empty else 0.0
    daily = ordered.groupby("trading_session")["net_pnl"].sum()
    row = {
        **base,
        "kept_trade_count": int(len(ordered)),
        "removed_trade_count": int(len(source) - len(ordered)),
        "kept_active_sessions": int(ordered["trading_session"].nunique()),
        "active_session_pct": round(_safe_div(float(ordered["trading_session"].nunique()), float(len(complete_sessions))), 6),
        "net_pnl": round(net, 2),
        "stress_net_pnl": round(stress, 2),
        "discovery_pnl": round(float(ordered.loc[ordered["split"].eq("discovery"), "net_pnl"].sum()), 2),
        "validation_pnl": round(float(ordered.loc[ordered["split"].eq("validation"), "net_pnl"].sum()), 2),
        "holdout_pnl": round(float(ordered.loc[ordered["split"].eq("holdout"), "net_pnl"].sum()), 2),
        "max_drawdown": round(drawdown, 2),
        "best_day_concentration": round(_concentration(float(daily.max()) if not daily.empty else 0.0, net), 6),
        "best_trade_concentration": round(_concentration(float(ordered["net_pnl"].max()), net), 6),
        **_walk_forward_summary(ordered, complete_sessions, config),
    }
    row["phase8l_score"] = round(_phase8l_score(row), 4)
    row["phase8l_label"] = _phase8l_label(row, config)
    row["phase8l_notes"] = _phase8l_notes(row, config)
    return row


def _walk_forward_summary(trades: pd.DataFrame, complete_sessions: list[Any], config: Phase8LConfig) -> dict[str, Any]:
    folds = _generate_folds(complete_sessions, config)
    test_rows: list[dict[str, Any]] = []
    for fold in folds:
        segment_sessions = fold["test_sessions"]
        segment = trades[trades["trading_session"].astype(str).isin([str(session) for session in segment_sessions])].copy()
        test_rows.append(_score_test_fold(segment, fold["fold"], segment_sessions))
    if not test_rows:
        return _empty_walk_forward_summary()
    frame = pd.DataFrame(test_rows)
    fold_count = int(len(frame))
    positive = int((frame["net_pnl"] > 0).sum())
    return {
        "walk_forward_folds": fold_count,
        "walk_forward_test_trades": int(frame["trades"].sum()),
        "walk_forward_test_net_pnl": round(float(frame["net_pnl"].sum()), 2),
        "walk_forward_test_stress_net_pnl": round(float(frame["stress_net_pnl"].sum()), 2),
        "walk_forward_test_positive_folds": positive,
        "walk_forward_test_positive_fold_pct": round(_safe_div(float(positive), float(fold_count)), 6),
        "walk_forward_worst_test_fold_pnl": round(float(frame["net_pnl"].min()), 2),
        "walk_forward_max_test_drawdown": round(float(frame["max_drawdown"].min()), 2),
        "walk_forward_test_best_day_concentration": round(float(frame["best_day_concentration"].max()), 6),
        "walk_forward_test_best_trade_concentration": round(float(frame["best_trade_concentration"].max()), 6),
    }


def _generate_folds(sessions: list[Any], config: Phase8LConfig) -> list[dict[str, Any]]:
    ordered = [str(session) for session in sessions]
    window = config.train_sessions + config.validation_sessions + config.test_sessions
    if len(ordered) < window:
        return []
    folds: list[dict[str, Any]] = []
    start = 0
    fold = 1
    while start + window <= len(ordered):
        train_end = start + config.train_sessions
        validation_end = train_end + config.validation_sessions
        test_end = validation_end + config.test_sessions
        folds.append(
            {
                "fold": fold,
                "train_sessions": ordered[start:train_end],
                "validation_sessions": ordered[train_end:validation_end],
                "test_sessions": ordered[validation_end:test_end],
            }
        )
        fold += 1
        start += config.step_sessions
    return folds


def _score_test_fold(trades: pd.DataFrame, fold: int, segment_sessions: list[Any]) -> dict[str, Any]:
    if trades.empty:
        return {
            "fold": fold,
            "trades": 0,
            "net_pnl": 0.0,
            "stress_net_pnl": 0.0,
            "max_drawdown": 0.0,
            "best_day_concentration": 0.0,
            "best_trade_concentration": 0.0,
        }
    ordered = trades.sort_values(["entry_time", "exit_time"]).copy()
    net = float(ordered["net_pnl"].sum())
    stress = float(ordered["stress_net_pnl"].sum())
    equity = ordered["net_pnl"].cumsum()
    drawdown = equity - equity.cummax()
    day_pnl = ordered.groupby("trading_session")["net_pnl"].sum()
    return {
        "fold": fold,
        "trades": int(len(ordered)),
        "net_pnl": round(net, 2),
        "stress_net_pnl": round(stress, 2),
        "max_drawdown": round(float(drawdown.min()), 2),
        "best_day_concentration": round(_concentration(float(day_pnl.max()) if not day_pnl.empty else 0.0, net), 6),
        "best_trade_concentration": round(_concentration(float(ordered["net_pnl"].max()), net), 6),
    }


def _empty_walk_forward_summary() -> dict[str, Any]:
    return {
        "walk_forward_folds": 0,
        "walk_forward_test_trades": 0,
        "walk_forward_test_net_pnl": 0.0,
        "walk_forward_test_stress_net_pnl": 0.0,
        "walk_forward_test_positive_folds": 0,
        "walk_forward_test_positive_fold_pct": 0.0,
        "walk_forward_worst_test_fold_pnl": 0.0,
        "walk_forward_max_test_drawdown": 0.0,
        "walk_forward_test_best_day_concentration": 0.0,
        "walk_forward_test_best_trade_concentration": 0.0,
    }


def _phase8l_score(row: dict[str, Any]) -> float:
    score = 0.0
    score += max(min(float(row["stress_net_pnl"]) / 6_000.0, 2.0), -2.0) * 20.0
    score += max(min(float(row["holdout_pnl"]) / 2_000.0, 2.0), -2.0) * 16.0
    score += max(min(float(row["validation_pnl"]) / 1_500.0, 2.0), -2.0) * 12.0
    score += max(min(float(row["walk_forward_test_stress_net_pnl"]) / 4_000.0, 2.0), -2.0) * 18.0
    score += float(row["walk_forward_test_positive_fold_pct"]) * 20.0
    score += min(float(row["kept_trade_count"]) / 600.0, 1.0) * 6.0
    score -= min(abs(float(row["max_drawdown"])) / 6_000.0, 2.0) * 12.0
    score -= max(float(row["best_day_concentration"]) - 0.35, 0.0) * 100.0
    score -= max(float(row["walk_forward_test_best_day_concentration"]) - 0.35, 0.0) * 90.0
    score -= max(float(row["best_trade_concentration"]) - 0.20, 0.0) * 80.0
    score -= int(row["source_action_rank"]) * 0.1
    return float(score)


def _phase8l_label(row: dict[str, Any], config: Phase8LConfig) -> str:
    if int(row["kept_trade_count"]) < config.min_trades:
        return "insufficient_activity"
    if float(row["net_pnl"]) <= 0 or float(row["stress_net_pnl"]) <= 0:
        return "rejected"
    hard_fail = (
        float(row["discovery_pnl"]) <= 0
        or float(row["validation_pnl"]) <= 0
        or float(row["holdout_pnl"]) <= 0
        or float(row["walk_forward_test_net_pnl"]) <= 0
        or float(row["walk_forward_test_stress_net_pnl"]) <= 0
        or int(row["walk_forward_folds"]) < config.min_folds
    )
    if hard_fail:
        return "phase8l_watchlist_needs_strategy_remap"
    weak_gate = (
        float(row["walk_forward_test_positive_fold_pct"]) < 1.0
        or float(row["max_drawdown"]) < config.drawdown_limit
        or float(row["best_day_concentration"]) > config.concentration_limit
        or float(row["best_trade_concentration"]) > config.trade_concentration_limit
        or float(row["walk_forward_test_best_day_concentration"]) > config.concentration_limit
        or float(row["walk_forward_test_best_trade_concentration"]) > config.trade_concentration_limit
    )
    if weak_gate:
        return "phase8l_watchlist_needs_strategy_remap"
    return "phase8l_fixed_filter_candidate"


def _phase8l_notes(row: dict[str, Any], config: Phase8LConfig) -> str:
    notes: list[str] = []
    if int(row["kept_trade_count"]) < config.min_trades:
        notes.append(f"only {int(row['kept_trade_count'])} trades; minimum is {config.min_trades}")
    if float(row["net_pnl"]) <= 0:
        notes.append("negative net PnL")
    if float(row["stress_net_pnl"]) <= 0:
        notes.append("fails stress PnL")
    for split in ("discovery", "validation", "holdout"):
        if float(row[f"{split}_pnl"]) <= 0:
            notes.append(f"negative {split} split")
    if int(row["walk_forward_folds"]) < config.min_folds:
        notes.append("too few walk-forward folds")
    if float(row["walk_forward_test_net_pnl"]) <= 0:
        notes.append("negative walk-forward test PnL")
    if float(row["walk_forward_test_stress_net_pnl"]) <= 0:
        notes.append("negative walk-forward stress PnL")
    if float(row["walk_forward_test_positive_fold_pct"]) < 1.0:
        notes.append("not every walk-forward test fold is positive")
    if float(row["max_drawdown"]) < config.drawdown_limit:
        notes.append("drawdown beyond limit")
    if float(row["best_day_concentration"]) > config.concentration_limit:
        notes.append("one-day concentration risk")
    if float(row["best_trade_concentration"]) > config.trade_concentration_limit:
        notes.append("one-trade concentration risk")
    if float(row["walk_forward_test_best_day_concentration"]) > config.concentration_limit:
        notes.append("walk-forward day concentration risk")
    if float(row["walk_forward_test_best_trade_concentration"]) > config.trade_concentration_limit:
        notes.append("walk-forward trade concentration risk")
    return "; ".join(notes) if notes else "survives fixed no-lookahead retest; requires later StrategySpec remap, not promotion"


def _label_priority(label: str) -> int:
    return {
        "phase8l_fixed_filter_candidate": 3,
        "phase8l_watchlist_needs_strategy_remap": 2,
        "rejected": 1,
        "insufficient_activity": 0,
    }.get(str(label), 0)


def _minute_bucket(minute_of_day: int) -> str:
    width = 30
    start = int(minute_of_day // width * width)
    end = start + width
    return f"{start // 60:02d}:{start % 60:02d}-{end // 60:02d}:{end % 60:02d}"


def _concentration(best: float, total: float) -> float:
    if total <= 0:
        return 1.0
    return float(max(best, 0.0) / total)


def _safe_div(numerator: float, denominator: float) -> float:
    return float(numerator / denominator) if denominator else 0.0


def _result_columns() -> list[str]:
    return [
        "filter_id",
        "filter_family",
        "axis",
        "bucket",
        "source_action_id",
        "source_action_rank",
        "action_rule",
        "evidence",
        "promotion_allowed",
        "kept_trade_count",
        "removed_trade_count",
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
        "walk_forward_folds",
        "walk_forward_test_trades",
        "walk_forward_test_net_pnl",
        "walk_forward_test_stress_net_pnl",
        "walk_forward_test_positive_folds",
        "walk_forward_test_positive_fold_pct",
        "walk_forward_worst_test_fold_pnl",
        "walk_forward_max_test_drawdown",
        "walk_forward_test_best_day_concentration",
        "walk_forward_test_best_trade_concentration",
        "phase8l_score",
        "phase8l_label",
        "phase8l_notes",
    ]
