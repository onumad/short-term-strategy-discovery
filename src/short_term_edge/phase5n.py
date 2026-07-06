from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import pandas as pd

from .ai_search import SearchConfig, _score_spec, propose_strategy_specs
from .data_loader import discover_data_files, load_ohlcv_csv
from .phase4a import resample_signal_bars
from .strategy_spec import StrategySpec
from .walk_forward import shared_complete_sessions


@dataclass(frozen=True)
class Phase5NConfig:
    symbol: str = "MNQ"
    max_specs: int = 60
    min_specs: int = 40
    batch_size: int = 5
    timeframes: tuple[int, ...] = (1, 3, 5)
    opening_range_minutes: tuple[int, ...] = (10, 15, 20, 30, 45, 60)

    def validate(self) -> "Phase5NConfig":
        if self.symbol != "MNQ":
            raise ValueError("Phase 5N is intentionally MNQ-only")
        if self.min_specs < 1:
            raise ValueError("min_specs must be positive")
        if self.max_specs < self.min_specs:
            raise ValueError("max_specs must be greater than or equal to min_specs")
        if self.batch_size < 1:
            raise ValueError("batch_size must be positive")
        SearchConfig(
            symbols=(self.symbol,),
            max_candidates=1,
            recent_sessions=2,
            timeframes=self.timeframes,
            opening_range_minutes=self.opening_range_minutes,
        ).validate()
        return self


@dataclass(frozen=True)
class Phase5NResult:
    search_results: pd.DataFrame
    specs: list[StrategySpec]
    complete_sessions: list[Any]


def select_prefilter_specs(config: Phase5NConfig = Phase5NConfig()) -> list[StrategySpec]:
    """Select a bounded, deterministic MNQ family sweep for cheap full-history prefiltering."""
    config.validate()
    search_config = SearchConfig(
        symbols=(config.symbol,),
        max_candidates=10_000,
        recent_sessions=2,
        timeframes=config.timeframes,
        opening_range_minutes=config.opening_range_minutes,
    )
    proposed = propose_strategy_specs(search_config)
    base_cap = max(1, config.max_specs // 4)
    remainder = max(0, config.max_specs - base_cap * 4)
    family_caps = {
        "opening_range_failure": base_cap,
        "opening_range_breakout": base_cap,
        "vwap_reclaim_rejection": base_cap,
        "prior_session_levels": base_cap + remainder,
    }
    selected: list[StrategySpec] = []
    for family in ("opening_range_failure", "opening_range_breakout", "vwap_reclaim_rejection", "prior_session_levels"):
        family_specs = sorted(
            [spec for spec in proposed if spec.family == family],
            key=lambda spec: (
                int(spec.timeframe),
                int(spec.entry.params.get("or_minutes", 0)),
                str(spec.entry.params.get("target", spec.entry.params.get("mode", ""))),
                int(spec.exit.params.get("stop_ticks", 0)),
                int(spec.exit.params.get("target_ticks", 0)),
                int(spec.risk.params.get("max_trades_per_day", 1)),
                spec.canonical_id(),
            ),
        )
        selected.extend(family_specs[: family_caps[family]])
    if len(selected) < config.max_specs:
        selected_ids = {spec.canonical_id() for spec in selected}
        remaining = sorted(
            [spec for spec in proposed if spec.canonical_id() not in selected_ids],
            key=lambda spec: (
                int(spec.timeframe),
                spec.family,
                json.dumps(spec.entry.params, sort_keys=True),
                json.dumps(spec.exit.params, sort_keys=True),
                spec.canonical_id(),
            ),
        )
        selected.extend(remaining[: config.max_specs - len(selected)])
    selected = selected[: config.max_specs]
    if len(selected) < config.min_specs:
        raise ValueError(f"Phase 5N expected at least {config.min_specs} specs, selected {len(selected)}")
    return selected


def run_phase5n_prefilter(project_root: Path, config: Phase5NConfig = Phase5NConfig(), checkpoint_path: Path | None = None) -> Phase5NResult:
    config.validate()
    specs = select_prefilter_specs(config)
    raw_dir = project_root / "data" / "raw"
    files = discover_data_files(raw_dir)
    if not files:
        raise FileNotFoundError(f"No local raw CSV files found under {raw_dir}")
    symbol_files = [path for path in files if config.symbol.lower() in path.name.lower()]
    source_files = symbol_files if symbol_files else files
    full_data = pd.concat([load_ohlcv_csv(path) for path in source_files], ignore_index=True)
    full_data = full_data[full_data["symbol"].eq(config.symbol)].sort_values(["symbol", "timestamp"])
    sessions = shared_complete_sessions(full_data, symbols=(config.symbol,))
    scoped = full_data[(full_data["symbol"] == config.symbol) & (full_data["trading_session"].isin(sessions))].copy()
    prepared = _prepare_phase5n_symbol_data(scoped, sessions, config.timeframes)
    results = score_prefilter_specs(specs, prepared, sessions, checkpoint_path=checkpoint_path, batch_size=config.batch_size)
    return Phase5NResult(search_results=results, specs=specs, complete_sessions=sessions)


def score_prefilter_specs(
    specs: list[StrategySpec],
    prepared: dict[str, dict[str, Any]],
    complete_sessions: list[Any],
    checkpoint_path: Path | None = None,
    batch_size: int = 5,
    score_func: Callable[[StrategySpec, dict[str, dict[str, Any]], list[Any]], Any] = _score_spec,
) -> pd.DataFrame:
    """Score specs with optional resumable checkpoint writes after each bounded batch."""
    if batch_size < 1:
        raise ValueError("batch_size must be positive")
    rows: list[dict[str, Any]] = []
    completed_ids: set[str] = set()
    if checkpoint_path is not None and checkpoint_path.exists():
        existing = pd.read_csv(checkpoint_path)
        if not existing.empty and "candidate_id" in existing.columns:
            existing = existing.drop_duplicates("candidate_id", keep="first")
            rows.extend(existing.to_dict("records"))
            completed_ids = {str(candidate_id) for candidate_id in existing["candidate_id"]}

    pending = [spec for spec in specs if spec.canonical_id() not in completed_ids]
    for start in range(0, len(pending), batch_size):
        batch = pending[start : start + batch_size]
        for spec in batch:
            rows.append(score_func(spec, prepared, complete_sessions).to_dict())
        if checkpoint_path is not None:
            checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
            pd.DataFrame(rows).drop_duplicates("candidate_id", keep="first").to_csv(checkpoint_path, index=False)
            print(f"Phase 5N checkpoint: {len(rows)}/{len(specs)} specs scored -> {checkpoint_path}", flush=True)
    return rank_prefilter_results(pd.DataFrame(rows))


def _prepare_phase5n_symbol_data(full_data: pd.DataFrame, complete_sessions: list[Any], timeframes: tuple[int, ...]) -> dict[str, dict[str, Any]]:
    full_symbol = full_data[full_data["trading_session"].isin(complete_sessions)].copy()
    one_minute = full_symbol[full_symbol["session_segment"] == "RTH"].sort_values("timestamp").copy()
    return {
        "MNQ": {
            "full": full_symbol,
            "one_minute": one_minute,
            "timeframes": {tf: resample_signal_bars(one_minute, tf) for tf in sorted(set(timeframes))},
        }
    }


def rank_prefilter_results(candidate_summary: pd.DataFrame) -> pd.DataFrame:
    if candidate_summary.empty:
        return candidate_summary.copy()
    rows: list[dict[str, Any]] = []
    for _, row in candidate_summary.iterrows():
        out = row.to_dict()
        net = _finite_float(out.get("net_pnl", 0.0), 0.0)
        slippage = _finite_float(out.get("slippage_4_ticks_net_pnl", 0.0), 0.0)
        active = _finite_float(out.get("active_session_pct", 0.0), 0.0)
        trades = int(_finite_float(out.get("trades", 0), 0.0))
        drawdown = _finite_float(out.get("max_drawdown", 0.0), 0.0)
        day = _finite_float(out.get("best_day_concentration", 1.0), 1.0)
        trade = _finite_float(out.get("best_trade_concentration", 1.0), 1.0)
        validation = _finite_float(out.get("validation_pnl", 0.0), 0.0)
        holdout = _finite_float(out.get("holdout_pnl", 0.0), 0.0)

        score = 0.0
        score += min(max(net / 4_000.0, -2.0), 2.0) * 12.0
        score += min(max(slippage / 4_000.0, -2.0), 2.0) * 28.0
        score += min(max(validation / 1_500.0, -2.0), 2.0) * 8.0
        score += min(max(holdout / 1_500.0, -2.0), 2.0) * 12.0
        score += min(active, 0.70) * 16.0
        score += min(trades / 180.0, 1.0) * 10.0
        score -= min(abs(drawdown) / 2_500.0, 2.0) * 12.0
        score -= max(day - 0.30, 0.0) * 170.0
        score -= max(trade - 0.20, 0.0) * 170.0
        if slippage <= 0:
            score -= 45.0
        if active < 0.20:
            score -= 25.0
        if trades < 60:
            score -= 18.0
        if validation < 0 or holdout < 0:
            score -= 12.0

        out["phase5n_score"] = round(score, 4)
        out["phase5n_label"] = _phase5n_label(out)
        out["phase5n_notes"] = _phase5n_notes(out)
        rows.append(out)
    ranked = pd.DataFrame(rows).sort_values(["phase5n_score", "slippage_4_ticks_net_pnl", "net_pnl"], ascending=[False, False, False]).reset_index(drop=True)
    ranked.insert(0, "phase5n_rank", range(1, len(ranked) + 1))
    return ranked


def write_phase5n_specs(specs: list[StrategySpec], path: Path) -> None:
    path.write_text(json.dumps([json.loads(spec.to_json()) for spec in specs], indent=2, sort_keys=True), encoding="utf-8")


def _phase5n_label(row: dict[str, Any]) -> str:
    if _finite_float(row.get("slippage_4_ticks_net_pnl", 0.0), 0.0) <= 0:
        return "rejected"
    if int(_finite_float(row.get("trades", 0), 0.0)) < 60:
        return "rejected"
    if _finite_float(row.get("active_session_pct", 0.0), 0.0) < 0.20:
        return "rejected"
    if _finite_float(row.get("best_day_concentration", 1.0), 1.0) > 0.30:
        return "rejected"
    if _finite_float(row.get("best_trade_concentration", 1.0), 1.0) > 0.20:
        return "rejected"
    if _finite_float(row.get("max_drawdown", 0.0), 0.0) < -2_500.0:
        return "rejected"
    if _finite_float(row.get("validation_pnl", 0.0), 0.0) < 0 or _finite_float(row.get("holdout_pnl", 0.0), 0.0) < 0:
        return "watchlist_needs_walk_forward"
    return "prefilter_survivor"


def _phase5n_notes(row: dict[str, Any]) -> str:
    notes: list[str] = []
    if _finite_float(row.get("slippage_4_ticks_net_pnl", 0.0), 0.0) <= 0:
        notes.append("fails aggregate 4-tick slippage stress")
    if int(_finite_float(row.get("trades", 0), 0.0)) < 60:
        notes.append("too few full-history trades")
    if _finite_float(row.get("active_session_pct", 0.0), 0.0) < 0.20:
        notes.append("insufficient active-day coverage")
    if _finite_float(row.get("best_day_concentration", 1.0), 1.0) > 0.30:
        notes.append("one-day concentration risk")
    if _finite_float(row.get("best_trade_concentration", 1.0), 1.0) > 0.20:
        notes.append("one-trade concentration risk")
    if _finite_float(row.get("max_drawdown", 0.0), 0.0) < -2_500.0:
        notes.append("drawdown exceeds prefilter cap")
    if _finite_float(row.get("validation_pnl", 0.0), 0.0) < 0:
        notes.append("negative validation split")
    if _finite_float(row.get("holdout_pnl", 0.0), 0.0) < 0:
        notes.append("negative holdout split")
    return "; ".join(notes) if notes else "Survives Phase 5N full-history prefilter gates; requires Phase 5O walk-forward validation."


def _finite_float(value: Any, default: float) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return default
    return out if math.isfinite(out) else default
