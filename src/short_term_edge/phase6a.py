from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from .phase5n import Phase5NResult, rank_prefilter_results, score_prefilter_specs
from .strategy_spec import EntryRule, ExitRule, RiskRule, StrategySpec


@dataclass(frozen=True)
class Phase6AConfig:
    symbol: str = "MNQ"
    max_specs: int = 48
    min_specs: int = 40
    batch_size: int = 1
    max_new_specs_per_run: int | None = None
    timeframes: tuple[int, ...] = (1, 2, 3, 5)
    opening_range_minutes: tuple[int, ...] = (5, 10, 15, 20, 30, 45, 60, 90)

    def validate(self) -> "Phase6AConfig":
        if self.symbol != "MNQ":
            raise ValueError("Phase 6A is intentionally MNQ-only")
        if self.min_specs < 1:
            raise ValueError("min_specs must be positive")
        if self.max_specs < self.min_specs:
            raise ValueError("max_specs must be greater than or equal to min_specs")
        if self.batch_size < 1:
            raise ValueError("batch_size must be positive")
        if self.max_new_specs_per_run is not None and self.max_new_specs_per_run < 1:
            raise ValueError("max_new_specs_per_run must be positive when provided")
        if any(int(tf) <= 0 for tf in self.timeframes):
            raise ValueError("timeframes must be positive")
        if any(int(minutes) <= 0 for minutes in self.opening_range_minutes):
            raise ValueError("opening_range_minutes must be positive")
        return self


def select_phase6a_specs(config: Phase6AConfig = Phase6AConfig()) -> list[StrategySpec]:
    """Select a deterministic MNQ-first dimension expansion after Phase 5N found no survivors."""
    config.validate()
    symbol = config.symbol
    min_range = 10.0
    specs: list[StrategySpec] = []

    for timeframe in config.timeframes:
        for minutes in config.opening_range_minutes:
            for stop_mode, target in (("half_range", "1R"), ("half_range", "2R"), ("full_range", "1R")):
                specs.append(
                    StrategySpec(
                        instrument=symbol,
                        family="opening_range_breakout",
                        timeframe=int(timeframe),
                        entry=EntryRule("close_outside_range", {"or_minutes": int(minutes), "min_range": min_range}),
                        exit=ExitRule("r_multiple", {"target": target, "stop_mode": stop_mode}),
                        risk=RiskRule("one_open_position", {"max_trades_per_day": 1}),
                        notes="Expanded deterministic Phase 6A search: opening-range breakout dimension expansion.",
                    ).validate()
                )
            for target in ("mid", "opposite"):
                specs.append(
                    StrategySpec(
                        instrument=symbol,
                        family="opening_range_failure",
                        timeframe=int(timeframe),
                        entry=EntryRule("close_back_inside", {"or_minutes": int(minutes), "target": target, "min_range": min_range}),
                        exit=ExitRule("range_target", {"target": target}),
                        risk=RiskRule("one_open_position", {"max_trades_per_day": 1}),
                        notes="Expanded deterministic Phase 6A search: opening-range failure dimension expansion.",
                    ).validate()
                )

    for timeframe in config.timeframes:
        for mode in ("reclaim", "rejection", "both"):
            for stop_ticks, target_ticks in ((20, 30), (30, 45), (40, 80), (60, 120)):
                specs.append(
                    StrategySpec(
                        instrument=symbol,
                        family="vwap_reclaim_rejection",
                        timeframe=int(timeframe),
                        entry=EntryRule("vwap_cross", {"mode": mode}),
                        exit=ExitRule("fixed_ticks", {"stop_ticks": stop_ticks, "target_ticks": target_ticks}),
                        risk=RiskRule("one_open_position", {"max_trades_per_day": 2}),
                        notes="Expanded deterministic Phase 6A search: VWAP stop/target dimension expansion.",
                    ).validate()
                )

    for timeframe in config.timeframes:
        for mode in ("break_hold", "sweep_reverse", "prior_close_reclaim"):
            for stop_ticks, target_ticks in ((20, 30), (30, 45), (40, 80), (60, 120)):
                specs.append(
                    StrategySpec(
                        instrument=symbol,
                        family="prior_session_levels",
                        timeframe=int(timeframe),
                        entry=EntryRule("prior_level_reaction", {"mode": mode}),
                        exit=ExitRule("fixed_ticks", {"stop_ticks": stop_ticks, "target_ticks": target_ticks}),
                        risk=RiskRule("one_open_position", {"max_trades_per_day": 2}),
                        notes="Expanded deterministic Phase 6A search: prior-session stop/target dimension expansion.",
                    ).validate()
                )

    unique: dict[str, StrategySpec] = {spec.canonical_id(): spec for spec in specs}
    ordered = sorted(
        unique.values(),
        key=lambda spec: (
            _family_order(spec.family),
            int(spec.timeframe),
            int(spec.entry.params.get("or_minutes", 0)),
            str(spec.entry.params.get("mode", spec.entry.params.get("target", ""))),
            int(spec.exit.params.get("stop_ticks", 0)),
            int(spec.exit.params.get("target_ticks", 0)),
            str(spec.exit.params.get("stop_mode", "")),
            str(spec.exit.params.get("target", "")),
            spec.canonical_id(),
        ),
    )
    selected = _round_robin_by_family(ordered, config.max_specs)
    if len(selected) < config.min_specs:
        raise ValueError(f"Phase 6A expected at least {config.min_specs} specs, selected {len(selected)}")
    return selected


def run_phase6a_expansion(project_root: Path, config: Phase6AConfig = Phase6AConfig(), checkpoint_path: Path | None = None) -> Phase5NResult:
    config.validate()
    specs = select_phase6a_specs(config)
    specs_for_run = _limit_specs_for_run(specs, checkpoint_path, config.max_new_specs_per_run)
    prepared, complete_sessions = _prepare_phase6a_data(project_root, config)
    prepared_result = score_prefilter_specs(
        specs_for_run,
        prepared,
        complete_sessions,
        checkpoint_path=checkpoint_path,
        batch_size=config.batch_size,
    )
    return Phase5NResult(search_results=rank_phase6a_results(prepared_result), specs=specs, complete_sessions=complete_sessions)


def _limit_specs_for_run(specs: list[StrategySpec], checkpoint_path: Path | None, max_new_specs: int | None) -> list[StrategySpec]:
    if max_new_specs is None:
        return specs
    completed_ids: set[str] = set()
    if checkpoint_path is not None and checkpoint_path.exists():
        existing = pd.read_csv(checkpoint_path)
        if not existing.empty and "candidate_id" in existing.columns:
            completed_ids = {str(candidate_id) for candidate_id in existing["candidate_id"]}
    completed = [spec for spec in specs if spec.canonical_id() in completed_ids]
    pending = [spec for spec in specs if spec.canonical_id() not in completed_ids]
    return completed + pending[:max_new_specs]


def rank_phase6a_results(candidate_summary: pd.DataFrame) -> pd.DataFrame:
    reusable = candidate_summary.drop(
        columns=[
            column
            for column in ("phase5n_rank", "phase5n_score", "phase5n_label", "phase5n_notes", "phase6a_rank", "phase6a_score", "phase6a_label", "phase6a_notes")
            if column in candidate_summary.columns
        ]
    )
    ranked = rank_prefilter_results(reusable)
    if ranked.empty:
        return ranked.copy()
    ranked = ranked.rename(
        columns={
            "phase5n_rank": "phase6a_rank",
            "phase5n_score": "phase6a_score",
            "phase5n_label": "phase6a_label",
            "phase5n_notes": "phase6a_notes",
        }
    )
    return ranked


def write_phase6a_specs(specs: list[StrategySpec], path: Path) -> None:
    path.write_text(json.dumps([json.loads(spec.to_json()) for spec in specs], indent=2, sort_keys=True), encoding="utf-8")


def _round_robin_by_family(specs: list[StrategySpec], max_specs: int) -> list[StrategySpec]:
    families = ("opening_range_failure", "opening_range_breakout", "vwap_reclaim_rejection", "prior_session_levels")
    by_family = {family: _interleave_by_timeframe([spec for spec in specs if spec.family == family]) for family in families}
    selected: list[StrategySpec] = []
    while len(selected) < max_specs and any(by_family.values()):
        for family in families:
            if by_family[family] and len(selected) < max_specs:
                selected.append(by_family[family].pop(0))
    return selected


def _interleave_by_timeframe(specs: list[StrategySpec]) -> list[StrategySpec]:
    timeframes = sorted({int(spec.timeframe) for spec in specs})
    buckets = {
        timeframe: sorted(
            [spec for spec in specs if int(spec.timeframe) == timeframe],
            key=lambda spec: (
                _variant_order(spec),
                _opening_range_order(int(spec.entry.params.get("or_minutes", 0))),
                int(spec.exit.params.get("stop_ticks", 0)),
                int(spec.exit.params.get("target_ticks", 0)),
                spec.canonical_id(),
            ),
        )
        for timeframe in timeframes
    }
    out: list[StrategySpec] = []
    while any(buckets.values()):
        for timeframe in timeframes:
            if buckets[timeframe]:
                out.append(buckets[timeframe].pop(0))
    return out


def _opening_range_order(minutes: int) -> int:
    order = {5: 0, 90: 1, 10: 2, 60: 3, 15: 4, 45: 5, 20: 6, 30: 7}
    return order.get(minutes, 99)


def _variant_order(spec: StrategySpec) -> int:
    if spec.family == "opening_range_breakout":
        target = str(spec.exit.params.get("target", ""))
        stop_mode = str(spec.exit.params.get("stop_mode", ""))
        return {("1R", "half_range"): 0, ("2R", "half_range"): 1, ("1R", "full_range"): 2}.get((target, stop_mode), 9)
    if spec.family == "opening_range_failure":
        return {"mid": 0, "opposite": 1}.get(str(spec.entry.params.get("target", "")), 9)
    return 0


def _family_order(family: str) -> int:
    order = {
        "opening_range_failure": 0,
        "opening_range_breakout": 1,
        "vwap_reclaim_rejection": 2,
        "prior_session_levels": 3,
    }
    return order.get(family, 99)


def _prepare_phase6a_data(project_root: Path, config: Phase6AConfig) -> tuple[dict[str, dict[str, Any]], list[Any]]:
    from .data_loader import discover_data_files, load_ohlcv_csv
    from .phase5n import _prepare_phase5n_symbol_data
    from .walk_forward import shared_complete_sessions

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
    return _prepare_phase5n_symbol_data(scoped, sessions, config.timeframes), sessions
