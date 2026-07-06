from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from .data_loader import discover_data_files, load_ohlcv_csv
from .phase5h import _evaluate_spec_filters, build_session_regimes, filter_trades_by_regime, regime_filter_label
from .strategy_spec import StrategySpec
from .walk_forward import WalkForwardConfig, generate_walk_forward_folds, shared_complete_sessions, summarize_walk_forward


@dataclass(frozen=True)
class Phase5LConfig:
    symbol: str = "MNQ"
    max_specs: int = 1
    walk_forward: WalkForwardConfig = WalkForwardConfig(train_sessions=60, validation_sessions=20, test_sessions=20, step_sessions=10_000, min_folds=1, max_candidates=1)

    def validate(self) -> "Phase5LConfig":
        if self.symbol != "MNQ":
            raise ValueError("Phase 5L is intentionally MNQ-only")
        if self.max_specs < 1:
            raise ValueError("max_specs must be positive")
        self.walk_forward.validate()
        return self


@dataclass(frozen=True)
class Phase5LResult:
    fold_results: pd.DataFrame
    search_results: pd.DataFrame
    specs: list[StrategySpec]
    filters: list[dict[str, str]]


def vwap_regime_filters() -> list[dict[str, str]]:
    return [
        {},
        {"prior_range_bucket": "high"},
        {"prior_range_bucket": "mid"},
        {"gap_abs_bucket": "low"},
        {"or_width_bucket": "mid"},
        {"gap_abs_bucket": "low", "or_width_bucket": "mid"},
    ]


def rank_vwap_regime_results(candidate_summary: pd.DataFrame) -> pd.DataFrame:
    if candidate_summary.empty:
        return candidate_summary.copy()
    rows: list[dict[str, Any]] = []
    for _, row in candidate_summary.iterrows():
        out = row.to_dict()
        positive = _finite_float(out.get("test_positive_fold_pct", 0.0), 0.0)
        slippage = _finite_float(out.get("test_slippage_4_ticks_net_pnl", 0.0), 0.0)
        active = _finite_float(out.get("test_active_session_pct", 0.0), 0.0)
        day = _finite_float(out.get("test_best_day_concentration", 1.0), 1.0)
        trade = _finite_float(out.get("test_best_trade_concentration", 1.0), 1.0)
        out["test_active_session_pct"] = active
        out["test_best_day_concentration"] = day
        out["test_best_trade_concentration"] = trade
        score = 0.0
        score += min(max(float(out.get("test_net_pnl", 0.0)) / 500.0, -2.0), 2.0) * 8.0
        score += min(max(slippage / 500.0, -2.0), 2.0) * 12.0
        score += positive * 35.0
        score += min(active, 0.70) * 8.0
        score += 8.0 if 0.30 <= active <= 0.70 else 0.0
        score -= max(day - 0.35, 0.0) * 190.0
        score -= max(trade - 0.22, 0.0) * 170.0
        out["phase5l_score"] = round(score, 4)
        out["phase5l_label"] = _phase5l_label(out)
        out["phase5l_notes"] = _phase5l_notes(out)
        rows.append(out)
    ranked = pd.DataFrame(rows).sort_values(["phase5l_score", "test_slippage_4_ticks_net_pnl"], ascending=[False, False]).reset_index(drop=True)
    ranked.insert(0, "phase5l_rank", range(1, len(ranked) + 1))
    return ranked


def run_phase5l_search(project_root: Path, config: Phase5LConfig = Phase5LConfig()) -> Phase5LResult:
    config.validate()
    specs = _load_top_phase5k_specs(project_root, config)
    filters = vwap_regime_filters()
    raw_dir = project_root / "data" / "raw"
    files = discover_data_files(raw_dir)
    if not files:
        raise FileNotFoundError(f"No local raw CSV files found under {raw_dir}")
    full_data = pd.concat([load_ohlcv_csv(path) for path in files], ignore_index=True).sort_values(["symbol", "timestamp"])
    features = pd.read_parquet(project_root / "outputs" / "phase5b_features.parquet")
    sessions = shared_complete_sessions(full_data, symbols=(config.symbol,))
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
    return Phase5LResult(fold_results=fold_results, search_results=rank_vwap_regime_results(candidate_summary), specs=specs, filters=filters)


def write_phase5l_specs(specs: list[StrategySpec], path: Path) -> None:
    path.write_text(json.dumps([json.loads(spec.to_json()) for spec in specs], indent=2, sort_keys=True), encoding="utf-8")


def _load_top_phase5k_specs(project_root: Path, config: Phase5LConfig) -> list[StrategySpec]:
    specs_by_id = {StrategySpec.from_dict(item).canonical_id(): StrategySpec.from_dict(item) for item in json.loads((project_root / "outputs" / "phase5k_candidate_specs.json").read_text(encoding="utf-8"))}
    ranked = pd.read_csv(project_root / "outputs" / "phase5k_vwap_focus_results.csv")
    ranked = ranked[ranked["instrument"].eq(config.symbol)].sort_values("phase5k_rank")
    return [specs_by_id[candidate_id] for candidate_id in ranked["candidate_id"] if candidate_id in specs_by_id][: config.max_specs]


def _phase5l_label(row: dict[str, Any]) -> str:
    if _finite_float(row.get("test_slippage_4_ticks_net_pnl", 0.0), 0.0) <= 0 or _finite_float(row.get("test_positive_fold_pct", 0.0), 0.0) < 0.67:
        return "rejected"
    if _finite_float(row.get("test_best_day_concentration", 1.0), 1.0) <= 0.35 and _finite_float(row.get("test_best_trade_concentration", 1.0), 1.0) <= 0.22:
        return "vwap_regime_candidate"
    return "watchlist_concentrated"


def _phase5l_notes(row: dict[str, Any]) -> str:
    notes: list[str] = []
    if _finite_float(row.get("test_positive_fold_pct", 0.0), 0.0) < 0.67:
        notes.append("weak positive-fold coverage")
    if _finite_float(row.get("test_slippage_4_ticks_net_pnl", 0.0), 0.0) <= 0:
        notes.append("fails aggregate 4-tick slippage stress")
    if _finite_float(row.get("test_best_day_concentration", 1.0), 1.0) > 0.35:
        notes.append("day concentration remains")
    if _finite_float(row.get("test_best_trade_concentration", 1.0), 1.0) > 0.22:
        notes.append("trade concentration remains")
    return "; ".join(notes) if notes else "VWAP regime filter passed current concentration thresholds."


def _finite_float(value: Any, default: float) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return default
    return out if math.isfinite(out) else default
