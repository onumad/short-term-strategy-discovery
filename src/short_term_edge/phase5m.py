from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from .data_loader import discover_data_files, load_ohlcv_csv
from .phase5f import _run_one_spec_walk_forward
from .strategy_spec import StrategySpec
from .walk_forward import WalkForwardConfig, generate_walk_forward_folds, shared_complete_sessions


@dataclass(frozen=True)
class Phase5MConfig:
    symbol: str = "MNQ"
    walk_forward: WalkForwardConfig = WalkForwardConfig(train_sessions=120, validation_sessions=30, test_sessions=30, step_sessions=360, min_folds=2, max_candidates=1)

    def validate(self) -> "Phase5MConfig":
        if self.symbol != "MNQ":
            raise ValueError("Phase 5M is intentionally MNQ-only")
        self.walk_forward.validate()
        return self


@dataclass(frozen=True)
class Phase5MResult:
    fold_results: pd.DataFrame
    search_results: pd.DataFrame
    spec: StrategySpec
    folds: list[Any]


def select_deep_vwap_spec(project_root: Path, config: Phase5MConfig = Phase5MConfig()) -> StrategySpec:
    config.validate()
    specs_by_id = {StrategySpec.from_dict(item).canonical_id(): StrategySpec.from_dict(item) for item in json.loads((project_root / "outputs" / "phase5k_candidate_specs.json").read_text(encoding="utf-8"))}
    ranked = pd.read_csv(project_root / "outputs" / "phase5k_vwap_focus_results.csv")
    ranked = ranked[ranked["instrument"].eq(config.symbol)].sort_values("phase5k_rank")
    for candidate_id in ranked["candidate_id"]:
        spec = specs_by_id.get(candidate_id)
        if spec is not None and spec.family == "vwap_reclaim_rejection":
            return spec
    raise ValueError("No Phase 5K VWAP candidate spec found")


def rank_deep_vwap_results(candidate_summary: pd.DataFrame) -> pd.DataFrame:
    if candidate_summary.empty:
        return candidate_summary.copy()
    rows: list[dict[str, Any]] = []
    for _, row in candidate_summary.iterrows():
        out = row.to_dict()
        folds = int(out.get("folds", 0))
        positive = float(out.get("test_positive_fold_pct", 0.0))
        slippage = float(out.get("test_slippage_4_ticks_net_pnl", 0.0))
        active = float(out.get("test_active_session_pct", 0.0))
        day = float(out.get("test_best_day_concentration", 1.0))
        trade = float(out.get("test_best_trade_concentration", 1.0))
        score = 0.0
        score += min(max(float(out.get("test_net_pnl", 0.0)) / 1_500.0, -2.0), 2.0) * 10.0
        score += min(max(slippage / 1_500.0, -2.0), 2.0) * 16.0
        score += positive * 35.0
        score += min(active, 0.70) * 8.0
        score += min(folds / 3.0, 1.0) * 12.0
        score -= max(day - 0.35, 0.0) * 170.0
        score -= max(trade - 0.22, 0.0) * 170.0
        if folds < 2:
            score -= 25.0
        out["phase5m_score"] = round(score, 4)
        out["phase5m_label"] = _phase5m_label(out)
        out["phase5m_notes"] = _phase5m_notes(out)
        rows.append(out)
    ranked = pd.DataFrame(rows).sort_values(["phase5m_score", "test_slippage_4_ticks_net_pnl"], ascending=[False, False]).reset_index(drop=True)
    ranked.insert(0, "phase5m_rank", range(1, len(ranked) + 1))
    return ranked


def run_phase5m_validation(project_root: Path, config: Phase5MConfig = Phase5MConfig()) -> Phase5MResult:
    config.validate()
    spec = select_deep_vwap_spec(project_root, config)
    raw_dir = project_root / "data" / "raw"
    files = discover_data_files(raw_dir)
    if not files:
        raise FileNotFoundError(f"No local raw CSV files found under {raw_dir}")
    full_data = pd.concat([load_ohlcv_csv(path) for path in files], ignore_index=True).sort_values(["symbol", "timestamp"])
    sessions = shared_complete_sessions(full_data, symbols=(config.symbol,))
    folds = generate_walk_forward_folds(sessions, config.walk_forward)
    result = _run_one_spec_walk_forward(project_root, full_data, spec, folds)
    return Phase5MResult(fold_results=result.fold_results, search_results=rank_deep_vwap_results(result.candidate_summary), spec=spec, folds=folds)


def write_phase5m_spec(spec: StrategySpec, path: Path) -> None:
    path.write_text(json.dumps(json.loads(spec.to_json()), indent=2, sort_keys=True), encoding="utf-8")


def _phase5m_label(row: dict[str, Any]) -> str:
    folds = int(row.get("folds", 0))
    if folds < 2:
        return "needs_deeper_validation"
    if float(row.get("test_slippage_4_ticks_net_pnl", 0.0)) <= 0 or float(row.get("test_positive_fold_pct", 0.0)) < 0.67:
        return "rejected"
    if float(row.get("test_best_day_concentration", 1.0)) <= 0.35 and float(row.get("test_best_trade_concentration", 1.0)) <= 0.22:
        return "deep_vwap_candidate"
    return "watchlist_concentrated"


def _phase5m_notes(row: dict[str, Any]) -> str:
    notes: list[str] = []
    if int(row.get("folds", 0)) < 2:
        notes.append("requires at least two folds for deep validation")
    if float(row.get("test_positive_fold_pct", 0.0)) < 0.67:
        notes.append("weak positive-fold coverage")
    if float(row.get("test_slippage_4_ticks_net_pnl", 0.0)) <= 0:
        notes.append("fails aggregate 4-tick slippage stress")
    if float(row.get("test_best_day_concentration", 1.0)) > 0.35:
        notes.append("day concentration remains")
    if float(row.get("test_best_trade_concentration", 1.0)) > 0.22:
        notes.append("trade concentration remains")
    return "; ".join(notes) if notes else "Deep VWAP validation passed current thresholds."
