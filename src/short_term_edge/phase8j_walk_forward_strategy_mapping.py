from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from .strategy_spec import EntryRule, ExitRule, RiskRule, StrategySpec


@dataclass(frozen=True)
class Phase8JConfig:
    target_filter_id: str = "time_window:pre_14_00"
    train_sessions: int = 75
    validation_sessions: int = 25
    test_sessions: int = 25
    step_sessions: int = 25
    min_folds: int = 3
    min_test_trades: int = 150
    min_test_positive_fold_pct: float = 1.0
    concentration_limit: float = 0.35
    trade_concentration_limit: float = 0.20
    drawdown_limit: float = -6_000.0


def build_phase8j_strategy_spec(source_trades: pd.DataFrame, phase8i_results: pd.DataFrame, config: Phase8JConfig = Phase8JConfig()) -> StrategySpec:
    """Build a deterministic StrategySpec-style artifact for the Phase 8I winner."""
    if source_trades.empty:
        raise ValueError("Phase 8J requires non-empty de-duplicated Phase 8I trades")
    if phase8i_results.empty:
        raise ValueError("Phase 8J requires Phase 8I filter results")
    first = source_trades.sort_values("entry_time").iloc[0]
    filter_row = _select_filter_row(phase8i_results, config)
    filter_params = _filter_params(filter_row)
    start = str(filter_params.get("start", "09:30"))
    end = str(filter_params.get("end", filter_params.get("exclude_start", "14:00")))
    family = str(first["family"])
    side_filter = _side_filter(source_trades)
    entry = _entry_rule_for_family(family, first, filter_row, start, end, side_filter)
    time_stop = _time_stop_minutes(str(first.get("exit_shape", "horizon_close_15m")))
    return StrategySpec(
        instrument=str(first["instrument"]),
        family=family,
        timeframe=int(first["timeframe"]),
        entry=entry,
        exit=ExitRule("horizon_close", {"time_stop_minutes": time_stop, "entry_delay": str(first.get("entry_delay", "next_5m_close"))}),
        risk=RiskRule(
            "one_open_position",
            {
                "max_trades_per_day": 3,
                "side_filter": side_filter,
                "entry_filter_id": str(filter_row["filter_id"]),
                "entry_filter_family": str(filter_row.get("filter_family", "time_window")),
                "entry_filter_start": start,
                "entry_filter_end": end,
            },
        ),
        notes="Phase 8J research-only mapping from de-duplicated Phase 8H/8I MNQ VWAP event path; no paper/live promotion.",
    ).validate()


def apply_phase8j_strategy_spec(trades: pd.DataFrame, spec: StrategySpec) -> pd.DataFrame:
    """Apply the StrategySpec's fixed no-lookahead entry filter to replayed event trades."""
    spec.validate()
    if trades.empty:
        return trades.copy()
    out = trades.copy()
    out["entry_time"] = _parse_entry_time(out["entry_time"])
    start = _hhmm_to_minutes(str(spec.risk.params.get("entry_filter_start", "00:00")))
    end = _hhmm_to_minutes(str(spec.risk.params.get("entry_filter_end", "23:59")))
    minutes = out["entry_time"].dt.hour * 60 + out["entry_time"].dt.minute
    out = out[(minutes >= start) & (minutes < end)].copy()
    side_filter = str(spec.risk.params.get("side_filter", "both"))
    if side_filter in {"long", "short"} and "side" in out.columns:
        out = out[out["side"].astype(str).eq(side_filter)].copy()
    out["phase8j_candidate_id"] = spec.canonical_id()
    out["phase8j_entry_filter"] = str(spec.risk.params.get("entry_filter_id", "none"))
    out["spec_json"] = spec.to_json()
    sort_columns = [column for column in ("entry_time", "exit_time") if column in out.columns]
    return out.sort_values(sort_columns).reset_index(drop=True)


def generate_phase8j_folds(sessions: list[Any], config: Phase8JConfig = Phase8JConfig()) -> pd.DataFrame:
    ordered = list(sessions)
    window = config.train_sessions + config.validation_sessions + config.test_sessions
    if len(ordered) < window:
        raise ValueError(f"Need at least {window} sessions for Phase 8J walk-forward, got {len(ordered)}")
    rows: list[dict[str, Any]] = []
    start = 0
    fold = 1
    while start + window <= len(ordered):
        train_end = start + config.train_sessions
        validation_end = train_end + config.validation_sessions
        test_end = validation_end + config.test_sessions
        for segment, segment_sessions in [
            ("train", ordered[start:train_end]),
            ("validation", ordered[train_end:validation_end]),
            ("test", ordered[validation_end:test_end]),
        ]:
            rows.append(
                {
                    "fold": fold,
                    "segment": segment,
                    "segment_start": segment_sessions[0],
                    "segment_end": segment_sessions[-1],
                    "segment_session_count": len(segment_sessions),
                    "sessions_json": json.dumps([str(session) for session in segment_sessions]),
                }
            )
        fold += 1
        start += config.step_sessions
    result = pd.DataFrame(rows)
    if result["fold"].nunique() < config.min_folds:
        raise ValueError(f"Expected at least {config.min_folds} Phase 8J folds, generated {result['fold'].nunique()}")
    return result


def run_phase8j_walk_forward(filtered_trades: pd.DataFrame, spec: StrategySpec, config: Phase8JConfig = Phase8JConfig()) -> pd.DataFrame:
    if filtered_trades.empty:
        raise ValueError("Phase 8J requires non-empty filtered trades")
    sessions = sorted(filtered_trades["trading_session"].dropna().unique().tolist())
    folds = generate_phase8j_folds(sessions, config)
    rows: list[dict[str, Any]] = []
    for _, fold_row in folds.iterrows():
        segment_sessions = json.loads(str(fold_row["sessions_json"]))
        segment_trades = filtered_trades[filtered_trades["trading_session"].astype(str).isin(segment_sessions)].copy()
        rows.append(
            {
                "candidate_id": spec.canonical_id(),
                "instrument": spec.instrument,
                "family": spec.family,
                "timeframe": int(spec.timeframe),
                "fold": int(fold_row["fold"]),
                "segment": str(fold_row["segment"]),
                "segment_start": str(fold_row["segment_start"]),
                "segment_end": str(fold_row["segment_end"]),
                "segment_session_count": int(fold_row["segment_session_count"]),
                **_score_segment(segment_trades, segment_sessions),
            }
        )
    return pd.DataFrame(rows)[_fold_result_columns()]


def summarize_phase8j_walk_forward(fold_results: pd.DataFrame, spec: StrategySpec, config: Phase8JConfig = Phase8JConfig()) -> pd.DataFrame:
    if fold_results.empty:
        return pd.DataFrame(columns=_summary_columns())
    test = fold_results[fold_results["segment"].eq("test")]
    validation = fold_results[fold_results["segment"].eq("validation")]
    train = fold_results[fold_results["segment"].eq("train")]
    folds = int(test["fold"].nunique())
    test_positive = int((test["net_pnl"] > 0).sum())
    row: dict[str, Any] = {
        "candidate_id": spec.canonical_id(),
        "spec_json": spec.to_json(),
        "instrument": spec.instrument,
        "family": spec.family,
        "timeframe": int(spec.timeframe),
        "folds": folds,
        "train_net_pnl": round(float(train["net_pnl"].sum()), 2),
        "validation_net_pnl": round(float(validation["net_pnl"].sum()), 2),
        "test_net_pnl": round(float(test["net_pnl"].sum()), 2),
        "test_stress_net_pnl": round(float(test["stress_net_pnl"].sum()), 2),
        "test_trades": int(test["trades"].sum()),
        "test_active_sessions": int(test["active_sessions"].sum()),
        "test_active_session_pct": round(_safe_div(float(test["active_sessions"].sum()), float(test["segment_session_count"].sum())), 6),
        "test_positive_folds": test_positive,
        "test_positive_fold_pct": round(_safe_div(test_positive, folds), 6),
        "worst_test_fold_pnl": round(float(test["net_pnl"].min()), 2),
        "max_test_drawdown": round(float(test["max_drawdown"].min()), 2),
        "test_best_day_concentration": round(float(test["best_day_concentration"].max()), 6),
        "test_best_trade_concentration": round(float(test["best_trade_concentration"].max()), 6),
    }
    row["phase8j_score"] = round(_phase8j_score(row), 4)
    row["phase8j_label"] = _phase8j_label(row, config)
    row["phase8j_notes"] = _phase8j_notes(row, config)
    return pd.DataFrame([row])[_summary_columns()]


def render_phase8j_report(
    summary: pd.DataFrame,
    fold_results: pd.DataFrame,
    spec: StrategySpec,
    config: Phase8JConfig,
    *,
    spec_path: Path,
    filtered_trade_log_path: Path,
    fold_results_path: Path,
    summary_path: Path,
    report_path: Path,
    run_artifact_dir: Path | None = None,
) -> str:
    label_counts = summary["phase8j_label"].value_counts().to_dict() if not summary.empty and "phase8j_label" in summary.columns else {}
    lines = [
        "# Phase 8J Walk-Forward Strategy Mapping",
        "",
        "Generated by: `./.venv/Scripts/python.exe scripts/run_phase8j_walk_forward_strategy_mapping.py`",
        "",
        "## Scope And Guardrails",
        "",
        "- Research/simulation only. No live trading, broker adapters, order routing, API-key storage, webhooks, or automated execution were added.",
        "- Phase 8J maps the de-duplicated Phase 8I MNQ VWAP path to a deterministic StrategySpec-style artifact and evaluates rolling folds.",
        "- No paper-trading promotion: even a `phase8j_strategy_mapping_candidate` is only a research milestone pending independent validation.",
        "",
        "## StrategySpec Mapping",
        "",
        f"- Candidate ID: `{spec.canonical_id()}`",
        f"- Instrument/family/timeframe: `{spec.instrument}` / `{spec.family}` / `{spec.timeframe}`",
        f"- Entry: `{spec.entry.name}` `{json.dumps(spec.entry.params, sort_keys=True)}`",
        f"- Exit: `{spec.exit.name}` `{json.dumps(spec.exit.params, sort_keys=True)}`",
        f"- Risk/filter: `{json.dumps(spec.risk.params, sort_keys=True)}`",
        "",
        "## Summary",
        "",
        f"- Label counts: `{label_counts}`",
        f"- Fold rows: `{len(fold_results)}`",
        f"- Minimum test trades: `{config.min_test_trades}`",
        "",
        "| Candidate | Label | Score | Folds | Test PnL | Test Stress | Test Trades | Positive Folds | Worst Test Fold | Max Test DD | Day Conc. | Notes |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for _, row in summary.iterrows():
        lines.append(
            f"| `{row['candidate_id']}` | {row['phase8j_label']} | {float(row['phase8j_score']):.2f} | {int(row['folds'])} | "
            f"${float(row['test_net_pnl']):.2f} | ${float(row['test_stress_net_pnl']):.2f} | {int(row['test_trades'])} | "
            f"{float(row['test_positive_fold_pct']) * 100:.1f}% | ${float(row['worst_test_fold_pnl']):.2f} | ${float(row['max_test_drawdown']):.2f} | "
            f"{float(row['test_best_day_concentration']) * 100:.1f}% | {row['phase8j_notes']} |"
        )
    lines.extend(
        [
            "",
            "## Decision Rule",
            "",
            "- `phase8j_strategy_mapping_candidate` means the mapping survived this bounded fold diagnostic; it is not paper/live approval.",
            "- `phase8j_watchlist_needs_more_history` means aggregate behavior is positive but at least one fold, concentration, or drawdown gate is weak.",
            "- `rejected` means aggregate test PnL/stress or activity failed.",
            "",
            "## Outputs",
            "",
            f"- Strategy spec JSON: `{spec_path.as_posix()}`",
            f"- Filtered trade log CSV: `{filtered_trade_log_path.as_posix()}`",
            f"- Fold results CSV: `{fold_results_path.as_posix()}`",
            f"- Summary CSV: `{summary_path.as_posix()}`",
            f"- Report: `{report_path.as_posix()}`",
        ]
    )
    if run_artifact_dir is not None:
        lines.append(f"- Run-scoped artifacts: `{run_artifact_dir.as_posix()}`")
    lines.extend(["", "## Repro Command", "", "```bash", "./.venv/Scripts/python.exe scripts/run_phase8j_walk_forward_strategy_mapping.py", "```", ""])
    return "\n".join(lines)


def _entry_rule_for_family(family: str, first: pd.Series, filter_row: pd.Series, start: str, end: str, side_filter: str) -> EntryRule:
    common = {
        "source_hypothesis_id": str(first["hypothesis_id"]),
        "entry_delay": str(first.get("entry_delay", "next_5m_close")),
        "phase8i_filter_id": str(filter_row["filter_id"]),
        "entry_filter_start": start,
        "entry_filter_end": end,
        "side_filter": side_filter,
    }
    if family == "vwap_reclaim_rejection":
        return EntryRule("vwap_cross", {**common, "mode": "reclaim" if side_filter == "long" else "rejection"})
    return EntryRule("vwap_pullback", {**common, "pullback_ref": "vwap", "min_slope_ticks": 0})


def _select_filter_row(phase8i_results: pd.DataFrame, config: Phase8JConfig) -> pd.Series:
    target = phase8i_results[phase8i_results["filter_id"].astype(str).eq(config.target_filter_id)]
    if not target.empty:
        return target.iloc[0]
    ranked = phase8i_results.copy()
    ranked["_label_priority"] = ranked["phase8i_label"].map({"phase8i_filter_candidate": 2, "phase8i_watchlist_needs_validation": 1}).fillna(0)
    ranked = ranked.sort_values(["_label_priority", "phase8i_score"], ascending=[False, False])
    return ranked.iloc[0]


def _filter_params(filter_row: pd.Series) -> dict[str, Any]:
    raw = filter_row.get("filter_params_json", "{}")
    if pd.isna(raw):
        return {}
    return dict(json.loads(str(raw)))


def _score_segment(trades: pd.DataFrame, segment_sessions: list[Any]) -> dict[str, Any]:
    if trades.empty:
        return {
            "trades": 0,
            "active_sessions": 0,
            "active_session_pct": 0.0,
            "net_pnl": 0.0,
            "stress_net_pnl": 0.0,
            "avg_trade": 0.0,
            "win_rate": 0.0,
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
        "trades": int(len(ordered)),
        "active_sessions": int(ordered["trading_session"].nunique()),
        "active_session_pct": round(_safe_div(float(ordered["trading_session"].nunique()), float(len(segment_sessions))), 6),
        "net_pnl": round(net, 2),
        "stress_net_pnl": round(stress, 2),
        "avg_trade": round(float(ordered["net_pnl"].mean()), 6),
        "win_rate": round(float((ordered["net_pnl"] > 0).mean()), 6),
        "max_drawdown": round(float(drawdown.min()), 2),
        "best_day_concentration": round(_concentration(float(day_pnl.max()) if not day_pnl.empty else 0.0, net), 6),
        "best_trade_concentration": round(_concentration(float(ordered["net_pnl"].max()), net), 6),
    }


def _phase8j_score(row: dict[str, Any]) -> float:
    score = 0.0
    score += max(min(float(row["test_stress_net_pnl"]) / 4_000.0, 2.0), -2.0) * 24.0
    score += float(row["test_positive_fold_pct"]) * 24.0
    score += min(float(row["test_active_session_pct"]), 1.0) * 10.0
    score += min(float(row["test_trades"]) / 450.0, 1.0) * 8.0
    score -= min(abs(float(row["max_test_drawdown"])) / 6_000.0, 2.0) * 14.0
    score -= max(float(row["test_best_day_concentration"]) - 0.35, 0.0) * 120.0
    score -= max(float(row["test_best_trade_concentration"]) - 0.20, 0.0) * 100.0
    score -= abs(min(float(row["worst_test_fold_pnl"]), 0.0)) / 250.0
    return float(score)


def _phase8j_label(row: dict[str, Any], config: Phase8JConfig) -> str:
    if int(row["test_trades"]) < config.min_test_trades:
        return "rejected"
    if float(row["test_net_pnl"]) <= 0 or float(row["test_stress_net_pnl"]) <= 0:
        return "rejected"
    hard_fail = (
        float(row["validation_net_pnl"]) <= 0
        or float(row["test_positive_fold_pct"]) < config.min_test_positive_fold_pct
        or float(row["max_test_drawdown"]) < config.drawdown_limit
        or float(row["test_best_day_concentration"]) > config.concentration_limit
        or float(row["test_best_trade_concentration"]) > config.trade_concentration_limit
    )
    if hard_fail:
        return "phase8j_watchlist_needs_more_history"
    return "phase8j_strategy_mapping_candidate"


def _phase8j_notes(row: dict[str, Any], config: Phase8JConfig) -> str:
    notes: list[str] = []
    if int(row["test_trades"]) < config.min_test_trades:
        notes.append(f"only {int(row['test_trades'])} test trades; minimum is {config.min_test_trades}")
    if float(row["test_net_pnl"]) <= 0:
        notes.append("negative aggregate test PnL")
    if float(row["test_stress_net_pnl"]) <= 0:
        notes.append("fails aggregate test stress")
    if float(row["validation_net_pnl"]) <= 0:
        notes.append("negative aggregate validation PnL")
    if float(row["test_positive_fold_pct"]) < config.min_test_positive_fold_pct:
        notes.append("not every test fold is positive")
    if float(row["max_test_drawdown"]) < config.drawdown_limit:
        notes.append("test drawdown beyond limit")
    if float(row["test_best_day_concentration"]) > config.concentration_limit:
        notes.append("test one-day concentration risk")
    if float(row["test_best_trade_concentration"]) > config.trade_concentration_limit:
        notes.append("test one-trade concentration risk")
    return "; ".join(notes) if notes else "survives bounded walk-forward mapping diagnostic"


def _time_stop_minutes(exit_shape: str) -> int:
    if exit_shape.startswith("horizon_close_") and exit_shape.endswith("m"):
        return int(exit_shape.removeprefix("horizon_close_").removesuffix("m"))
    return 15


def _side_filter(trades: pd.DataFrame) -> str:
    sides = set(trades.get("side", pd.Series(dtype=object)).dropna().astype(str).unique())
    if sides == {"long"}:
        return "long"
    if sides == {"short"}:
        return "short"
    return "both"


def _parse_entry_time(values: pd.Series) -> pd.Series:
    return pd.to_datetime(values, utc=True).dt.tz_convert("America/New_York")


def _hhmm_to_minutes(value: str) -> int:
    hour, minute = value.split(":")
    return int(hour) * 60 + int(minute)


def _concentration(value: float, net_pnl: float) -> float:
    if net_pnl <= 0:
        return 1.0
    return float(max(value, 0.0) / net_pnl)


def _safe_div(numerator: float, denominator: float) -> float:
    return float(numerator / denominator) if denominator else 0.0


def _fold_result_columns() -> list[str]:
    return [
        "candidate_id",
        "instrument",
        "family",
        "timeframe",
        "fold",
        "segment",
        "segment_start",
        "segment_end",
        "segment_session_count",
        "trades",
        "active_sessions",
        "active_session_pct",
        "net_pnl",
        "stress_net_pnl",
        "avg_trade",
        "win_rate",
        "max_drawdown",
        "best_day_concentration",
        "best_trade_concentration",
    ]


def _summary_columns() -> list[str]:
    return [
        "candidate_id",
        "spec_json",
        "instrument",
        "family",
        "timeframe",
        "folds",
        "train_net_pnl",
        "validation_net_pnl",
        "test_net_pnl",
        "test_stress_net_pnl",
        "test_trades",
        "test_active_sessions",
        "test_active_session_pct",
        "test_positive_folds",
        "test_positive_fold_pct",
        "worst_test_fold_pnl",
        "max_test_drawdown",
        "test_best_day_concentration",
        "test_best_trade_concentration",
        "phase8j_score",
        "phase8j_label",
        "phase8j_notes",
    ]
