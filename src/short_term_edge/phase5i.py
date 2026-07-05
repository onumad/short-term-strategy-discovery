from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from .data_loader import discover_data_files, load_ohlcv_csv
from .phase5h import _evaluate_spec_filters, _load_phase5f_top_specs, build_session_regimes, regime_filter_label
from .strategy_spec import StrategySpec
from .walk_forward import WalkForwardConfig, generate_walk_forward_folds, shared_complete_sessions, summarize_walk_forward


@dataclass(frozen=True)
class Phase5IConfig:
    symbols: tuple[str, ...] = ("MNQ",)
    max_specs: int = 3
    walk_forward: WalkForwardConfig = WalkForwardConfig(train_sessions=120, validation_sessions=30, test_sessions=30, step_sessions=360, min_folds=2, max_candidates=1)

    def validate(self) -> "Phase5IConfig":
        if self.max_specs < 1:
            raise ValueError("max_specs must be positive")
        self.walk_forward.validate()
        return self


@dataclass(frozen=True)
class Phase5IResult:
    fold_results: pd.DataFrame
    search_results: pd.DataFrame
    specs: list[StrategySpec]
    filters: list[dict[str, str]]


def expanded_regime_filters() -> list[dict[str, str]]:
    filters: list[dict[str, str]] = [{}]
    for column in ("prior_range_bucket", "gap_abs_bucket", "or_width_bucket"):
        for bucket in ("low", "mid", "high"):
            filters.append({column: bucket})
    filters.extend(
        [
            {"prior_range_bucket": "high", "gap_abs_bucket": "low"},
            {"prior_range_bucket": "high", "gap_abs_bucket": "mid"},
            {"prior_range_bucket": "high", "or_width_bucket": "mid"},
            {"prior_range_bucket": "mid", "or_width_bucket": "mid"},
            {"gap_abs_bucket": "low", "or_width_bucket": "mid"},
        ]
    )
    seen: set[tuple[tuple[str, str], ...]] = set()
    unique: list[dict[str, str]] = []
    for item in filters:
        key = tuple(sorted(item.items()))
        if key not in seen:
            seen.add(key)
            unique.append(item)
    return unique


def rank_expanded_regime_results(candidate_summary: pd.DataFrame) -> pd.DataFrame:
    if candidate_summary.empty:
        return candidate_summary.copy()
    rows: list[dict[str, Any]] = []
    for _, row in candidate_summary.iterrows():
        out = row.to_dict()
        positive = float(out.get("test_positive_fold_pct", 0.0))
        slippage = float(out.get("test_slippage_4_ticks_net_pnl", 0.0))
        active = float(out.get("test_active_session_pct", 0.0))
        day = float(out.get("test_best_day_concentration", 1.0))
        trade = float(out.get("test_best_trade_concentration", 1.0))
        score = 0.0
        score += min(max(float(out.get("test_net_pnl", 0.0)) / 2_000.0, -2.0), 2.0) * 15.0
        score += min(max(slippage / 2_000.0, -2.0), 2.0) * 20.0
        score += positive * 35.0
        score += min(active, 0.70) * 12.0
        score -= max(day - 0.35, 0.0) * 140.0
        score -= max(trade - 0.22, 0.0) * 140.0
        if regime_filter_label({}) != str(out.get("regime_filter", "")):
            score += 3.0
        out["phase5i_score"] = round(score, 4)
        out["phase5i_label"] = _phase5i_label(out)
        out["phase5i_notes"] = _phase5i_notes(out)
        rows.append(out)
    ranked = pd.DataFrame(rows).sort_values(["phase5i_score", "test_net_pnl"], ascending=[False, False]).reset_index(drop=True)
    ranked.insert(0, "phase5i_rank", range(1, len(ranked) + 1))
    return ranked


def run_phase5i_search(project_root: Path, config: Phase5IConfig = Phase5IConfig()) -> Phase5IResult:
    config.validate()
    specs = _load_phase5f_top_specs(project_root, config)[: config.max_specs]
    filters = expanded_regime_filters()
    raw_dir = project_root / "data" / "raw"
    files = discover_data_files(raw_dir)
    if not files:
        raise FileNotFoundError(f"No local raw CSV files found under {raw_dir}")
    full_data = pd.concat([load_ohlcv_csv(path) for path in files], ignore_index=True).sort_values(["symbol", "timestamp"])
    features = pd.read_parquet(project_root / "outputs" / "phase5b_features.parquet")
    sessions = shared_complete_sessions(full_data, symbols=config.symbols)
    folds = generate_walk_forward_folds(sessions, config.walk_forward)
    fold_frames: list[pd.DataFrame] = []
    summary_frames: list[pd.DataFrame] = []
    for spec in specs:
        regimes = build_session_regimes(features, symbol=spec.instrument)
        for fold_results in _evaluate_spec_filters(full_data, spec, folds, regimes, filters):
            label = str(fold_results["regime_filter"].iloc[0])
            summary = summarize_walk_forward(fold_results.drop(columns=["regime_filter"]))
            summary["regime_filter"] = label
            fold_frames.append(fold_results)
            summary_frames.append(summary)
    fold_results = pd.concat(fold_frames, ignore_index=True) if fold_frames else pd.DataFrame()
    candidate_summary = pd.concat(summary_frames, ignore_index=True) if summary_frames else pd.DataFrame()
    return Phase5IResult(fold_results=fold_results, search_results=rank_expanded_regime_results(candidate_summary), specs=specs, filters=filters)


def write_phase5i_specs(specs: list[StrategySpec], path: Path) -> None:
    path.write_text(json.dumps([json.loads(spec.to_json()) for spec in specs], indent=2, sort_keys=True), encoding="utf-8")


def _phase5i_label(row: dict[str, Any]) -> str:
    if float(row.get("test_slippage_4_ticks_net_pnl", 0.0)) <= 0 or float(row.get("test_positive_fold_pct", 0.0)) < 0.67:
        return "rejected"
    if float(row.get("test_best_day_concentration", 1.0)) <= 0.35 and float(row.get("test_best_trade_concentration", 1.0)) <= 0.22:
        return "regime_filtered_candidate"
    return "watchlist_concentrated"


def _phase5i_notes(row: dict[str, Any]) -> str:
    notes: list[str] = []
    if float(row.get("test_positive_fold_pct", 0.0)) < 0.67:
        notes.append("weak positive-fold coverage")
    if float(row.get("test_slippage_4_ticks_net_pnl", 0.0)) <= 0:
        notes.append("fails aggregate 4-tick slippage stress")
    if float(row.get("test_best_day_concentration", 1.0)) > 0.35:
        notes.append("day concentration remains")
    if float(row.get("test_best_trade_concentration", 1.0)) > 0.22:
        notes.append("trade concentration remains")
    return "; ".join(notes) if notes else "Expanded regime filter passed current concentration thresholds."
