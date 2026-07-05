from __future__ import annotations

import json
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from .ai_search import SearchConfig, propose_strategy_specs
from .data_loader import discover_data_files, load_ohlcv_csv
from .strategy_spec import StrategySpec
from .walk_forward import WalkForwardConfig, WalkForwardResult, generate_walk_forward_folds, shared_complete_sessions, summarize_walk_forward


@dataclass(frozen=True)
class Phase5FConfig:
    symbols: tuple[str, ...] = ("MNQ", "MGC")
    candidates_per_symbol: int = 12
    seed: int = 606
    timeframes: tuple[int, ...] = (1, 3, 5)
    opening_range_minutes: tuple[int, ...] = (10, 15, 20, 30, 45, 60)
    walk_forward: WalkForwardConfig = WalkForwardConfig(train_sessions=240, validation_sessions=60, test_sessions=60, step_sessions=240, min_folds=2, max_candidates=1)

    def validate(self) -> "Phase5FConfig":
        if self.candidates_per_symbol < 1:
            raise ValueError("candidates_per_symbol must be positive")
        SearchConfig(symbols=self.symbols, max_candidates=1, recent_sessions=2, timeframes=self.timeframes, opening_range_minutes=self.opening_range_minutes).validate()
        self.walk_forward.validate()
        return self


@dataclass(frozen=True)
class Phase5FResult:
    fold_results: pd.DataFrame
    search_results: pd.DataFrame
    specs: list[StrategySpec]
    folds: list[Any]


def select_walk_forward_search_specs(config: Phase5FConfig = Phase5FConfig()) -> list[StrategySpec]:
    """Select deterministic opening-range-failure specs for walk-forward-aware search.

    Timeframes are part of the explicit search space; defaults check 1m, 3m, and
    5m signal bars. MNQ is selected first, then MGC.
    """
    config.validate()
    selected: list[StrategySpec] = []
    for symbol_index, symbol in enumerate(config.symbols):
        search_config = SearchConfig(
            symbols=(symbol,),
            max_candidates=10_000,
            recent_sessions=2,
            timeframes=config.timeframes,
            opening_range_minutes=config.opening_range_minutes,
        )
        specs = [spec for spec in propose_strategy_specs(search_config) if spec.family == "opening_range_failure"]
        target_priority = {"opposite": 0, "mid": 1}
        specs = sorted(specs, key=lambda spec: (int(spec.entry.params.get("or_minutes", 0)), target_priority.get(str(spec.entry.params.get("target", "")), 99), spec.canonical_id()))
        head: list[StrategySpec] = []
        for timeframe in config.timeframes:
            match = next((spec for spec in specs if spec.timeframe == timeframe and spec not in head), None)
            if match is not None:
                head.append(match)
        for spec in specs:
            if len(head) >= max(len(config.timeframes), config.candidates_per_symbol // 2):
                break
            if spec not in head:
                head.append(spec)
        tail = [spec for spec in specs if spec not in head]
        random.Random(config.seed + symbol_index * 10_000).shuffle(tail)
        selected.extend((head + tail)[: config.candidates_per_symbol])
    return selected


def rank_walk_forward_search(candidate_summary: pd.DataFrame) -> pd.DataFrame:
    if candidate_summary.empty:
        return candidate_summary.copy()
    rows: list[dict[str, Any]] = []
    label_bonus = {"paper_test_candidate": 30.0, "robust_research_candidate": 12.0, "watchlist": 0.0, "rejected": -25.0}
    for _, row in candidate_summary.iterrows():
        out = row.to_dict()
        score = float(out.get("phase5d_score", 0.0))
        score += label_bonus.get(str(out.get("phase5d_label", "")), -10.0)
        score += float(out.get("test_positive_fold_pct", 0.0)) * 20.0
        score += min(max(float(out.get("test_slippage_4_ticks_net_pnl", 0.0)) / 2_500.0, -2.0), 2.0) * 10.0
        score -= max(float(out.get("test_best_day_concentration", 1.0)) - 0.35, 0.0) * 35.0
        score -= max(float(out.get("test_best_trade_concentration", 1.0)) - 0.20, 0.0) * 35.0
        out["phase5f_score"] = round(score, 4)
        out["phase5f_label"] = _phase5f_label(out)
        out["phase5f_notes"] = _phase5f_notes(out)
        rows.append(out)
    ranked = pd.DataFrame(rows).sort_values(["phase5f_score", "test_net_pnl"], ascending=[False, False]).reset_index(drop=True)
    ranked.insert(0, "phase5f_rank", range(1, len(ranked) + 1))
    return ranked


def run_phase5f_search(project_root: Path, config: Phase5FConfig = Phase5FConfig()) -> Phase5FResult:
    config.validate()
    specs = select_walk_forward_search_specs(config)
    raw_dir = project_root / "data" / "raw"
    files = discover_data_files(raw_dir)
    if not files:
        raise FileNotFoundError(f"No local raw CSV files found under {raw_dir}")
    full_data = pd.concat([load_ohlcv_csv(path) for path in files], ignore_index=True).sort_values(["symbol", "timestamp"])
    sessions = shared_complete_sessions(full_data, symbols=config.symbols)
    folds = generate_walk_forward_folds(sessions, config.walk_forward)
    fold_frames: list[pd.DataFrame] = []
    summary_frames: list[pd.DataFrame] = []
    for spec in specs:
        wf_config = WalkForwardConfig(
            train_sessions=config.walk_forward.train_sessions,
            validation_sessions=config.walk_forward.validation_sessions,
            test_sessions=config.walk_forward.test_sessions,
            step_sessions=config.walk_forward.step_sessions,
            min_folds=config.walk_forward.min_folds,
            max_candidates=1,
        )
        # Reuse the Phase 5D evaluator with an injected one-spec list by writing no
        # temporary files: evaluate one spec directly via the private helper shape.
        result = _run_one_spec_walk_forward(project_root, full_data, spec, folds)
        fold_frames.append(result.fold_results)
        summary_frames.append(result.candidate_summary)
    fold_results = pd.concat(fold_frames, ignore_index=True) if fold_frames else pd.DataFrame()
    candidate_summary = pd.concat(summary_frames, ignore_index=True) if summary_frames else pd.DataFrame()
    return Phase5FResult(fold_results=fold_results, search_results=rank_walk_forward_search(candidate_summary), specs=specs, folds=folds)


def _run_one_spec_walk_forward(project_root: Path, full_data: pd.DataFrame, spec: StrategySpec, folds: list[Any]) -> WalkForwardResult:
    from .ai_search import spec_to_phase4_candidate
    from .instruments import get_instrument
    from .phase4a import _prepare_symbol_data, generate_phase4a_signals, simulate_phase4a_candidate
    from .scoring import score_candidate_trades

    rows: list[dict[str, Any]] = []
    for fold in folds:
        fold_sessions = list(fold.all_sessions)
        scoped = full_data[(full_data["symbol"] == spec.instrument) & (full_data["trading_session"].isin(fold_sessions))].copy()
        prepared = _prepare_symbol_data(scoped, fold_sessions)[spec.instrument]
        candidate = spec_to_phase4_candidate(spec)
        signals = generate_phase4a_signals(prepared["timeframes"][spec.timeframe], prepared["full"], candidate)
        trades = simulate_phase4a_candidate(prepared["one_minute"], signals, candidate, get_instrument(spec.instrument), fold_sessions)
        for segment, segment_sessions in [("train", fold.train_sessions), ("validation", fold.validation_sessions), ("test", fold.test_sessions)]:
            segment_trades = trades[trades["trading_session"].isin(segment_sessions)].copy() if not trades.empty else trades
            rows.append({"fold": fold.fold, "segment": segment, "segment_start": segment_sessions[0], "segment_end": segment_sessions[-1], **score_candidate_trades(spec, segment_trades, get_instrument(spec.instrument), list(segment_sessions)).to_dict()})
    fold_results = pd.DataFrame(rows)
    return WalkForwardResult(fold_results=fold_results, candidate_summary=summarize_walk_forward(fold_results), folds=folds, specs=[spec])


def write_phase5f_specs(specs: list[StrategySpec], path: Path) -> None:
    path.write_text(json.dumps([json.loads(spec.to_json()) for spec in specs], indent=2, sort_keys=True), encoding="utf-8")


def _phase5f_label(row: dict[str, Any]) -> str:
    if str(row.get("phase5d_label")) == "paper_test_candidate" and float(row.get("phase5f_score", 0.0)) >= 55.0:
        return "paper_test_candidate"
    if str(row.get("phase5d_label")) in {"paper_test_candidate", "robust_research_candidate"} and float(row.get("phase5f_score", 0.0)) >= 35.0:
        return "robust_research_candidate"
    if float(row.get("test_slippage_4_ticks_net_pnl", 0.0)) > 0 and float(row.get("test_positive_fold_pct", 0.0)) >= 0.50:
        return "watchlist"
    return "rejected"


def _phase5f_notes(row: dict[str, Any]) -> str:
    notes: list[str] = []
    if float(row.get("test_positive_fold_pct", 0.0)) < 0.60:
        notes.append("weak positive-fold coverage")
    if float(row.get("test_slippage_4_ticks_net_pnl", 0.0)) <= 0:
        notes.append("fails aggregate 4-tick slippage stress")
    if float(row.get("test_best_day_concentration", 1.0)) > 0.35 or float(row.get("test_best_trade_concentration", 1.0)) > 0.20:
        notes.append("concentration risk")
    return "; ".join(notes) if notes else "Stable walk-forward search candidate."
