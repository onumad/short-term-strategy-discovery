from __future__ import annotations

import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from .ai_search import SearchConfig, _score_spec, propose_strategy_specs
from .data_loader import discover_data_files, load_ohlcv_csv
from .discovery import _shared_complete_sessions
from .phase4a import _prepare_symbol_data
from .strategy_spec import StrategySpec


@dataclass(frozen=True)
class Phase5CConfig:
    symbols: tuple[str, ...] = ("MNQ", "MGC")
    candidates_per_symbol: int = 32
    recent_sessions: int = 120
    seed: int = 505
    timeframes: tuple[int, ...] = (1, 3, 5)
    opening_range_minutes: tuple[int, ...] = (15, 30, 60)

    def validate(self) -> "Phase5CConfig":
        if self.candidates_per_symbol < 1:
            raise ValueError("candidates_per_symbol must be positive")
        if self.recent_sessions < 2:
            raise ValueError("recent_sessions must include at least two sessions")
        SearchConfig(symbols=self.symbols, max_candidates=1, recent_sessions=self.recent_sessions, timeframes=self.timeframes, opening_range_minutes=self.opening_range_minutes).validate()
        return self


@dataclass(frozen=True)
class Phase5CResult:
    results: pd.DataFrame
    selected_specs: list[StrategySpec]
    complete_sessions: list[Any]


def select_seeded_strategy_specs(config: Phase5CConfig) -> list[StrategySpec]:
    """Select deterministic serializable specs with MNQ first, then MGC.

    This is a bounded seeded randomized search over explicit strategy templates, not
    an opaque model and not a live-signal generator.
    """
    config.validate()
    selected: list[StrategySpec] = []
    for symbol_index, symbol in enumerate(config.symbols):
        symbol_config = SearchConfig(
            symbols=(symbol,),
            max_candidates=10_000,
            recent_sessions=config.recent_sessions,
            timeframes=config.timeframes,
            opening_range_minutes=config.opening_range_minutes,
        )
        specs = propose_strategy_specs(symbol_config)
        rng = random.Random(config.seed + symbol_index * 10_000)
        priority = {"opening_range_failure": 0, "opening_range_breakout": 1, "vwap_reclaim_rejection": 2, "prior_session_levels": 3}
        specs = sorted(specs, key=lambda s: (priority.get(s.family, 99), s.timeframe, s.canonical_id()))
        head = specs[: max(4, config.candidates_per_symbol // 2)]
        tail = specs[max(4, config.candidates_per_symbol // 2) :]
        rng.shuffle(tail)
        selected.extend((head + tail)[: config.candidates_per_symbol])
    return selected


def run_phase5c_search(project_root: Path, config: Phase5CConfig = Phase5CConfig()) -> Phase5CResult:
    config.validate()
    raw_dir = project_root / "data" / "raw"
    files = discover_data_files(raw_dir)
    if not files:
        raise FileNotFoundError(f"No local raw CSV files found under {raw_dir}")
    full_data = pd.concat([load_ohlcv_csv(path) for path in files], ignore_index=True).sort_values(["symbol", "timestamp"])
    complete_sessions = _shared_complete_sessions(full_data)
    if config.recent_sessions:
        complete_sessions = complete_sessions[-config.recent_sessions :]
    scoped = full_data[(full_data["symbol"].isin(config.symbols)) & (full_data["trading_session"].isin(complete_sessions))].copy()
    prepared = _prepare_symbol_data(scoped, complete_sessions)
    specs = select_seeded_strategy_specs(config)
    rows: list[dict[str, Any]] = []
    for spec in specs:
        base = _score_spec(spec, prepared, complete_sessions).to_dict()
        rows.append(apply_phase5c_robust_scoring(base, spec))
    results = pd.DataFrame(rows).sort_values(["phase5c_score", "ranking_score", "net_pnl"], ascending=[False, False, False]).reset_index(drop=True)
    results.insert(0, "phase5c_rank", range(1, len(results) + 1))
    return Phase5CResult(results=results, selected_specs=specs, complete_sessions=complete_sessions)


def apply_phase5c_robust_scoring(row: dict[str, Any], spec: StrategySpec | None = None) -> dict[str, Any]:
    """Add conservative Phase 5C penalties and labels to one scored candidate row."""
    out = dict(row)
    complexity = _complexity_score(out, spec)
    drawdown_penalty = min(abs(float(out.get("max_drawdown", 0.0))) / 2_000.0, 3.0) * 8.0
    low_activity_penalty = max(0.0, 0.35 - float(out.get("active_session_pct", 0.0))) * 50.0 + max(0, 20 - int(out.get("trades", 0))) * 0.5
    concentration_penalty = max(0.0, float(out.get("best_day_concentration", 1.0)) - 0.35) * 35.0 + max(0.0, float(out.get("best_trade_concentration", 1.0)) - 0.20) * 35.0
    complexity_penalty = complexity * 1.5
    validation_pnl = float(out.get("validation_pnl", 0.0))
    holdout_pnl = float(out.get("holdout_pnl", 0.0))
    holdout_penalty = (abs(min(0.0, holdout_pnl)) / 150.0) + (8.0 if validation_pnl > 0 and holdout_pnl < validation_pnl * 0.25 else 0.0)
    slippage_pnl = float(out.get("slippage_4_ticks_net_pnl", 0.0))
    slippage_penalty = (abs(min(0.0, slippage_pnl)) / 150.0) + (10.0 if slippage_pnl <= 0 else 0.0)
    total_penalty = drawdown_penalty + low_activity_penalty + concentration_penalty + complexity_penalty + holdout_penalty + slippage_penalty
    phase5c_score = round(float(out.get("ranking_score", 0.0)) - total_penalty, 4)
    out.update(
        {
            "phase5c_score": phase5c_score,
            "complexity_score": round(float(complexity), 4),
            "drawdown_penalty": round(float(drawdown_penalty), 4),
            "low_activity_penalty": round(float(low_activity_penalty), 4),
            "concentration_penalty": round(float(concentration_penalty), 4),
            "complexity_penalty": round(float(complexity_penalty), 4),
            "holdout_penalty": round(float(holdout_penalty), 4),
            "slippage_stress_penalty": round(float(slippage_penalty), 4),
            "phase5c_total_penalty": round(float(total_penalty), 4),
        }
    )
    out["phase5c_label"] = _phase5c_label(out)
    out["phase5c_notes"] = _phase5c_notes(out)
    return out


def _phase5c_label(row: dict[str, Any]) -> str:
    if int(row.get("trades", 0)) < 20 or float(row.get("net_pnl", 0.0)) <= 0 or float(row.get("slippage_4_ticks_net_pnl", 0.0)) <= 0:
        return "rejected"
    if float(row.get("holdout_pnl", 0.0)) < 0 or float(row.get("phase5c_score", 0.0)) < 25:
        return "watchlist_needs_validation"
    if float(row.get("phase5c_score", 0.0)) >= 45 and float(row.get("active_session_pct", 0.0)) >= 0.45 and float(row.get("best_day_concentration", 1.0)) <= 0.35 and float(row.get("best_trade_concentration", 1.0)) <= 0.20:
        return "robust_research_candidate"
    return "watchlist"


def _phase5c_notes(row: dict[str, Any]) -> str:
    notes = []
    for column, label in [
        ("drawdown_penalty", "drawdown"),
        ("low_activity_penalty", "low activity"),
        ("concentration_penalty", "concentration"),
        ("complexity_penalty", "complexity"),
        ("holdout_penalty", "poor holdout"),
        ("slippage_stress_penalty", "slippage stress"),
    ]:
        if float(row.get(column, 0.0)) > 0:
            notes.append(label)
    return "; ".join(notes) if notes else "No major Phase 5C robustness penalties."


def _complexity_score(row: dict[str, Any], spec: StrategySpec | None) -> float:
    family_weight = {
        "opening_range_failure": 1.0,
        "opening_range_breakout": 1.0,
        "vwap_reclaim_rejection": 1.5,
        "prior_session_levels": 2.0,
    }.get(str(row.get("family", "")), 2.5)
    param_count = 0
    if spec is not None:
        param_count = len(spec.entry.params) + len(spec.exit.params) + len(spec.risk.params)
    timeframe_penalty = 0.5 if int(row.get("timeframe", 1)) > 1 else 0.0
    return family_weight + param_count * 0.25 + timeframe_penalty
