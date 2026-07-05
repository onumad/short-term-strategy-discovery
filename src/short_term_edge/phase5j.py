from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from .ai_search import SearchConfig, propose_strategy_specs
from .data_loader import discover_data_files, load_ohlcv_csv
from .phase5f import _run_one_spec_walk_forward
from .strategy_spec import StrategySpec
from .walk_forward import WalkForwardConfig, generate_walk_forward_folds, shared_complete_sessions


@dataclass(frozen=True)
class Phase5JConfig:
    symbol: str = "MNQ"
    max_specs: int = 6
    timeframes: tuple[int, ...] = (1, 3)
    opening_range_minutes: tuple[int, ...] = (30,)
    walk_forward: WalkForwardConfig = WalkForwardConfig(train_sessions=120, validation_sessions=30, test_sessions=30, step_sessions=360, min_folds=2, max_candidates=1)

    def validate(self) -> "Phase5JConfig":
        if self.symbol != "MNQ":
            raise ValueError("Phase 5J is intentionally MNQ-only")
        if self.max_specs < 1:
            raise ValueError("max_specs must be positive")
        SearchConfig(symbols=(self.symbol,), max_candidates=1, recent_sessions=2, timeframes=self.timeframes, opening_range_minutes=self.opening_range_minutes).validate()
        self.walk_forward.validate()
        return self


@dataclass(frozen=True)
class Phase5JResult:
    fold_results: pd.DataFrame
    search_results: pd.DataFrame
    specs: list[StrategySpec]
    folds: list[Any]


def select_family_search_specs(config: Phase5JConfig = Phase5JConfig()) -> list[StrategySpec]:
    config.validate()
    search_config = SearchConfig(
        symbols=(config.symbol,),
        max_candidates=10_000,
        recent_sessions=2,
        timeframes=config.timeframes,
        opening_range_minutes=config.opening_range_minutes,
    )
    specs = propose_strategy_specs(search_config)
    families = ("opening_range_breakout", "vwap_reclaim_rejection", "prior_session_levels")
    by_family: dict[str, list[StrategySpec]] = {}
    for family in families:
        family_specs = sorted(
            [spec for spec in specs if spec.family == family],
            key=lambda spec: (int(spec.timeframe), json.dumps(spec.entry.params, sort_keys=True), json.dumps(spec.exit.params, sort_keys=True), spec.canonical_id()),
        )
        by_family[family] = family_specs[:2]
    selected: list[StrategySpec] = []
    for index in range(2):
        for family in families:
            if index < len(by_family[family]):
                selected.append(by_family[family][index])
    return selected[: config.max_specs]


def rank_family_search_results(candidate_summary: pd.DataFrame) -> pd.DataFrame:
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
        score += min(max(float(out.get("test_net_pnl", 0.0)) / 2_000.0, -2.0), 2.0) * 14.0
        score += min(max(slippage / 2_000.0, -2.0), 2.0) * 22.0
        score += positive * 35.0
        score += min(active, 0.70) * 10.0
        score -= max(day - 0.35, 0.0) * 150.0
        score -= max(trade - 0.22, 0.0) * 150.0
        if str(out.get("family")) != "opening_range_failure":
            score += 5.0
        out["phase5j_score"] = round(score, 4)
        out["phase5j_label"] = _phase5j_label(out)
        out["phase5j_notes"] = _phase5j_notes(out)
        rows.append(out)
    ranked = pd.DataFrame(rows).sort_values(["phase5j_score", "test_net_pnl"], ascending=[False, False]).reset_index(drop=True)
    ranked.insert(0, "phase5j_rank", range(1, len(ranked) + 1))
    return ranked


def run_phase5j_search(project_root: Path, config: Phase5JConfig = Phase5JConfig()) -> Phase5JResult:
    config.validate()
    specs = select_family_search_specs(config)
    raw_dir = project_root / "data" / "raw"
    files = discover_data_files(raw_dir)
    if not files:
        raise FileNotFoundError(f"No local raw CSV files found under {raw_dir}")
    full_data = pd.concat([load_ohlcv_csv(path) for path in files], ignore_index=True).sort_values(["symbol", "timestamp"])
    sessions = shared_complete_sessions(full_data, symbols=(config.symbol,))
    folds = generate_walk_forward_folds(sessions, config.walk_forward)
    fold_frames: list[pd.DataFrame] = []
    summary_frames: list[pd.DataFrame] = []
    for spec in specs:
        result = _run_one_spec_walk_forward(project_root, full_data, spec, folds)
        fold_frames.append(result.fold_results)
        summary_frames.append(result.candidate_summary)
    fold_results = pd.concat(fold_frames, ignore_index=True) if fold_frames else pd.DataFrame()
    candidate_summary = pd.concat(summary_frames, ignore_index=True) if summary_frames else pd.DataFrame()
    return Phase5JResult(fold_results=fold_results, search_results=rank_family_search_results(candidate_summary), specs=specs, folds=folds)


def write_phase5j_specs(specs: list[StrategySpec], path: Path) -> None:
    path.write_text(json.dumps([json.loads(spec.to_json()) for spec in specs], indent=2, sort_keys=True), encoding="utf-8")


def _phase5j_label(row: dict[str, Any]) -> str:
    if float(row.get("test_slippage_4_ticks_net_pnl", 0.0)) <= 0 or float(row.get("test_positive_fold_pct", 0.0)) < 0.67:
        return "rejected"
    if float(row.get("test_best_day_concentration", 1.0)) <= 0.35 and float(row.get("test_best_trade_concentration", 1.0)) <= 0.22:
        return "family_research_candidate"
    return "watchlist_concentrated"


def _phase5j_notes(row: dict[str, Any]) -> str:
    notes: list[str] = []
    if float(row.get("test_positive_fold_pct", 0.0)) < 0.67:
        notes.append("weak positive-fold coverage")
    if float(row.get("test_slippage_4_ticks_net_pnl", 0.0)) <= 0:
        notes.append("fails aggregate 4-tick slippage stress")
    if float(row.get("test_best_day_concentration", 1.0)) > 0.35:
        notes.append("day concentration remains")
    if float(row.get("test_best_trade_concentration", 1.0)) > 0.22:
        notes.append("trade concentration remains")
    return "; ".join(notes) if notes else "Family candidate passed current concentration thresholds."
