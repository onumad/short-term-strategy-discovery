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
class Phase5KConfig:
    symbol: str = "MNQ"
    max_specs: int = 6
    timeframes: tuple[int, ...] = (1, 3, 5)
    walk_forward: WalkForwardConfig = WalkForwardConfig(train_sessions=60, validation_sessions=20, test_sessions=20, step_sessions=10_000, min_folds=1, max_candidates=1)

    def validate(self) -> "Phase5KConfig":
        if self.symbol != "MNQ":
            raise ValueError("Phase 5K is intentionally MNQ-only")
        if self.max_specs < 1:
            raise ValueError("max_specs must be positive")
        SearchConfig(symbols=(self.symbol,), max_candidates=1, recent_sessions=2, timeframes=self.timeframes, opening_range_minutes=(30,)).validate()
        self.walk_forward.validate()
        return self


@dataclass(frozen=True)
class Phase5KResult:
    fold_results: pd.DataFrame
    search_results: pd.DataFrame
    specs: list[StrategySpec]
    folds: list[Any]


def select_vwap_focus_specs(config: Phase5KConfig = Phase5KConfig()) -> list[StrategySpec]:
    config.validate()
    specs = propose_strategy_specs(
        SearchConfig(
            symbols=(config.symbol,),
            max_candidates=10_000,
            recent_sessions=2,
            timeframes=config.timeframes,
            opening_range_minutes=(30,),
        )
    )
    vwap = sorted(
        [spec for spec in specs if spec.family == "vwap_reclaim_rejection"],
        key=lambda spec: (
            int(spec.timeframe),
            str(spec.entry.params["mode"]),
            int(spec.exit.params["stop_ticks"]),
            int(spec.exit.params["target_ticks"]),
            spec.canonical_id(),
        ),
    )
    modes = ("reclaim", "rejection", "both")
    risk_pairs = sorted({(int(spec.exit.params["stop_ticks"]), int(spec.exit.params["target_ticks"])) for spec in vwap})
    selected: list[StrategySpec] = []
    for timeframe in config.timeframes:
        for stop_ticks, target_ticks in risk_pairs:
            for mode in modes:
                match = next(
                    (
                        spec
                        for spec in vwap
                        if spec.timeframe == timeframe
                        and spec.entry.params["mode"] == mode
                        and int(spec.exit.params["stop_ticks"]) == stop_ticks
                        and int(spec.exit.params["target_ticks"]) == target_ticks
                    ),
                    None,
                )
                if match is not None:
                    selected.append(match)
                if len(selected) >= config.max_specs:
                    return selected
    return selected[: config.max_specs]


def rank_vwap_focus_results(candidate_summary: pd.DataFrame) -> pd.DataFrame:
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
        score += min(max(float(out.get("test_net_pnl", 0.0)) / 1_000.0, -2.0), 2.0) * 8.0
        score += min(max(slippage / 1_000.0, -2.0), 2.0) * 14.0
        score += positive * 35.0
        score += min(active, 0.70) * 8.0
        score -= max(day - 0.35, 0.0) * 170.0
        score -= max(trade - 0.22, 0.0) * 170.0
        if 0.30 <= active <= 0.70:
            score += 6.0
        out["phase5k_score"] = round(score, 4)
        out["phase5k_label"] = _phase5k_label(out)
        out["phase5k_notes"] = _phase5k_notes(out)
        rows.append(out)
    ranked = pd.DataFrame(rows).sort_values(["phase5k_score", "test_slippage_4_ticks_net_pnl"], ascending=[False, False]).reset_index(drop=True)
    ranked.insert(0, "phase5k_rank", range(1, len(ranked) + 1))
    return ranked


def run_phase5k_search(project_root: Path, config: Phase5KConfig = Phase5KConfig()) -> Phase5KResult:
    config.validate()
    specs = select_vwap_focus_specs(config)
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
    return Phase5KResult(fold_results=fold_results, search_results=rank_vwap_focus_results(candidate_summary), specs=specs, folds=folds)


def write_phase5k_specs(specs: list[StrategySpec], path: Path) -> None:
    path.write_text(json.dumps([json.loads(spec.to_json()) for spec in specs], indent=2, sort_keys=True), encoding="utf-8")


def _phase5k_label(row: dict[str, Any]) -> str:
    if float(row.get("test_slippage_4_ticks_net_pnl", 0.0)) <= 0 or float(row.get("test_positive_fold_pct", 0.0)) < 0.67:
        return "rejected"
    if float(row.get("test_best_day_concentration", 1.0)) <= 0.35 and float(row.get("test_best_trade_concentration", 1.0)) <= 0.22:
        return "vwap_research_candidate"
    return "watchlist_concentrated"


def _phase5k_notes(row: dict[str, Any]) -> str:
    notes: list[str] = []
    if float(row.get("test_positive_fold_pct", 0.0)) < 0.67:
        notes.append("weak positive-fold coverage")
    if float(row.get("test_slippage_4_ticks_net_pnl", 0.0)) <= 0:
        notes.append("fails aggregate 4-tick slippage stress")
    if float(row.get("test_best_day_concentration", 1.0)) > 0.35:
        notes.append("day concentration remains")
    if float(row.get("test_best_trade_concentration", 1.0)) > 0.22:
        notes.append("trade concentration remains")
    return "; ".join(notes) if notes else "VWAP candidate passed current concentration thresholds."
