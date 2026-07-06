from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from .phase5n import Phase5NResult, _finite_float, score_prefilter_specs
from .phase6a import _prepare_phase6a_data
from .strategy_spec import EntryRule, ExitRule, RiskRule, StrategySpec


@dataclass(frozen=True)
class Phase6BConfig:
    symbol: str = "MNQ"
    max_specs: int = 24
    min_specs: int = 16
    batch_size: int = 1
    max_new_specs_per_run: int | None = None
    timeframes: tuple[int, ...] = (2, 3, 5)
    opening_range_minutes: tuple[int, ...] = (15, 30, 60, 90)

    def validate(self) -> "Phase6BConfig":
        if self.symbol != "MNQ":
            raise ValueError("Phase 6B is intentionally MNQ-only")
        if self.min_specs < 1:
            raise ValueError("min_specs must be positive")
        if self.max_specs < self.min_specs:
            raise ValueError("max_specs must be greater than or equal to min_specs")
        if self.batch_size < 1:
            raise ValueError("batch_size must be positive")
        if self.max_new_specs_per_run is not None and self.max_new_specs_per_run < 0:
            raise ValueError("max_new_specs_per_run must be non-negative when provided")
        if any(int(tf) <= 0 for tf in self.timeframes):
            raise ValueError("timeframes must be positive")
        if any(int(minutes) <= 0 for minutes in self.opening_range_minutes):
            raise ValueError("opening_range_minutes must be positive")
        return self


def select_ambiguity_reduction_specs(config: Phase6BConfig = Phase6BConfig()) -> list[StrategySpec]:
    """Select bounded MNQ specs that trade less frequently and avoid Phase 6A ambiguity failure modes."""
    config.validate()
    symbol = config.symbol
    specs: list[StrategySpec] = []

    for timeframe in config.timeframes:
        for minutes in config.opening_range_minutes:
            for min_range in (20.0, 30.0):
                for target, stop_mode in (("1R", "full_range"), ("2R", "half_range")):
                    specs.append(
                        StrategySpec(
                            instrument=symbol,
                            family="opening_range_breakout",
                            timeframe=int(timeframe),
                            entry=EntryRule("close_outside_range", {"or_minutes": int(minutes), "min_range": min_range}),
                            exit=ExitRule("r_multiple", {"target": target, "stop_mode": stop_mode}),
                            risk=RiskRule("one_open_position", {"max_trades_per_day": 1, "stop_after_first_loser": True}),
                            notes="Phase 6B ambiguity reduction: one trade per day, wider opening-range filter, and loser stop rule.",
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
                            risk=RiskRule("one_open_position", {"max_trades_per_day": 1, "stop_after_first_loser": True}),
                            notes="Phase 6B ambiguity reduction: one trade per day, wider opening-range filter, and loser stop rule.",
                        ).validate()
                    )

    for timeframe in config.timeframes:
        for mode in ("reclaim", "rejection"):
            for stop_ticks, target_ticks in ((40, 80), (60, 120)):
                specs.append(
                    StrategySpec(
                        instrument=symbol,
                        family="vwap_reclaim_rejection",
                        timeframe=int(timeframe),
                        entry=EntryRule("vwap_cross", {"mode": mode}),
                        exit=ExitRule("fixed_ticks", {"stop_ticks": stop_ticks, "target_ticks": target_ticks}),
                        risk=RiskRule("one_open_position", {"max_trades_per_day": 1, "stop_after_first_loser": True}),
                        notes="Phase 6B ambiguity reduction: one trade per day, wider stop/target, and loser stop rule.",
                    ).validate()
                )

    for timeframe in config.timeframes:
        for mode in ("break_hold", "prior_close_reclaim"):
            for stop_ticks, target_ticks in ((40, 80), (60, 120)):
                specs.append(
                    StrategySpec(
                        instrument=symbol,
                        family="prior_session_levels",
                        timeframe=int(timeframe),
                        entry=EntryRule("prior_level_reaction", {"mode": mode}),
                        exit=ExitRule("fixed_ticks", {"stop_ticks": stop_ticks, "target_ticks": target_ticks}),
                        risk=RiskRule("one_open_position", {"max_trades_per_day": 1, "stop_after_first_loser": True}),
                        notes="Phase 6B ambiguity reduction: one trade per day, wider stop/target, and loser stop rule.",
                    ).validate()
                )

    unique = {spec.canonical_id(): spec for spec in specs}
    ordered = sorted(
        unique.values(),
        key=lambda spec: (
            _family_order(spec.family),
            int(spec.timeframe),
            int(spec.entry.params.get("or_minutes", 0)),
            float(spec.entry.params.get("min_range", 0.0)),
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
        raise ValueError(f"Phase 6B expected at least {config.min_specs} specs, selected {len(selected)}")
    return selected


def run_phase6b_search(project_root: Path, config: Phase6BConfig = Phase6BConfig(), checkpoint_path: Path | None = None) -> Phase5NResult:
    config.validate()
    specs = select_ambiguity_reduction_specs(config)
    if config.max_new_specs_per_run == 0:
        if checkpoint_path is None or not checkpoint_path.exists():
            return Phase5NResult(search_results=rank_phase6b_results(pd.DataFrame()), specs=specs, complete_sessions=[])
        return Phase5NResult(search_results=rank_phase6b_results(pd.read_csv(checkpoint_path)), specs=specs, complete_sessions=[])
    specs_for_run = _limit_specs_for_run(specs, checkpoint_path, config.max_new_specs_per_run)
    prepared, complete_sessions = _prepare_phase6a_data(project_root, config)
    scored = score_prefilter_specs(
        specs_for_run,
        prepared,
        complete_sessions,
        checkpoint_path=checkpoint_path,
        batch_size=config.batch_size,
    )
    return Phase5NResult(search_results=rank_phase6b_results(scored), specs=specs, complete_sessions=complete_sessions)


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


def rank_phase6b_results(candidate_summary: pd.DataFrame) -> pd.DataFrame:
    if candidate_summary.empty:
        return candidate_summary.copy()
    reusable = candidate_summary.drop(
        columns=[
            column
            for column in ("phase5n_rank", "phase5n_score", "phase5n_label", "phase5n_notes", "phase6b_rank", "phase6b_score", "phase6b_label", "phase6b_notes")
            if column in candidate_summary.columns
        ]
    )
    rows: list[dict[str, Any]] = []
    for _, row in reusable.iterrows():
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
        ambiguity = int(_finite_float(out.get("same_bar_stop_target_ambiguity_count", 0), 0.0))

        score = 0.0
        score += min(max(net / 4_000.0, -2.0), 2.0) * 8.0
        score += min(max(slippage / 4_000.0, -2.0), 2.0) * 34.0
        score += min(max(validation / 1_500.0, -2.0), 2.0) * 10.0
        score += min(max(holdout / 1_500.0, -2.0), 2.0) * 14.0
        score += min(active, 0.55) * 12.0
        score += min(trades / 120.0, 1.0) * 8.0
        score -= min(abs(drawdown) / 1_800.0, 2.5) * 18.0
        score -= max(day - 0.25, 0.0) * 230.0
        score -= max(trade - 0.16, 0.0) * 230.0
        score -= min(ambiguity, 10) * 3.0
        if slippage <= 0:
            score -= 55.0
        if active < 0.15:
            score -= 20.0
        if trades < 40:
            score -= 22.0
        if validation < 0 or holdout < 0:
            score -= 14.0

        out["phase6b_score"] = round(score, 4)
        out["phase6b_label"] = _phase6b_label(out)
        out["phase6b_notes"] = _phase6b_notes(out)
        rows.append(out)
    ranked = pd.DataFrame(rows).sort_values(["phase6b_score", "slippage_4_ticks_net_pnl", "net_pnl"], ascending=[False, False, False]).reset_index(drop=True)
    ranked.insert(0, "phase6b_rank", range(1, len(ranked) + 1))
    return ranked


def write_phase6b_specs(specs: list[StrategySpec], path: Path) -> None:
    path.write_text(json.dumps([json.loads(spec.to_json()) for spec in specs], indent=2, sort_keys=True), encoding="utf-8")


def _phase6b_label(row: dict[str, Any]) -> str:
    if _finite_float(row.get("slippage_4_ticks_net_pnl", 0.0), 0.0) <= 0:
        return "rejected"
    if int(_finite_float(row.get("trades", 0), 0.0)) < 40:
        return "rejected"
    if _finite_float(row.get("active_session_pct", 0.0), 0.0) < 0.15:
        return "rejected"
    if _finite_float(row.get("best_day_concentration", 1.0), 1.0) > 0.25:
        return "rejected"
    if _finite_float(row.get("best_trade_concentration", 1.0), 1.0) > 0.16:
        return "rejected"
    if _finite_float(row.get("max_drawdown", 0.0), 0.0) < -1_800.0:
        return "rejected"
    if int(_finite_float(row.get("same_bar_stop_target_ambiguity_count", 0), 0.0)) > 0:
        return "rejected"
    if _finite_float(row.get("validation_pnl", 0.0), 0.0) < 0 or _finite_float(row.get("holdout_pnl", 0.0), 0.0) < 0:
        return "watchlist_needs_walk_forward"
    return "prefilter_survivor"


def _phase6b_notes(row: dict[str, Any]) -> str:
    notes: list[str] = []
    if _finite_float(row.get("slippage_4_ticks_net_pnl", 0.0), 0.0) <= 0:
        notes.append("fails aggregate 4-tick slippage stress")
    if int(_finite_float(row.get("trades", 0), 0.0)) < 40:
        notes.append("too few full-history trades")
    if _finite_float(row.get("active_session_pct", 0.0), 0.0) < 0.15:
        notes.append("insufficient active-day coverage")
    if _finite_float(row.get("best_day_concentration", 1.0), 1.0) > 0.25:
        notes.append("one-day concentration risk")
    if _finite_float(row.get("best_trade_concentration", 1.0), 1.0) > 0.16:
        notes.append("one-trade concentration risk")
    if _finite_float(row.get("max_drawdown", 0.0), 0.0) < -1_800.0:
        notes.append("drawdown exceeds Phase 6B cap")
    if int(_finite_float(row.get("same_bar_stop_target_ambiguity_count", 0), 0.0)) > 0:
        notes.append("same-bar stop/target ambiguity remains")
    if _finite_float(row.get("validation_pnl", 0.0), 0.0) < 0:
        notes.append("negative validation split")
    if _finite_float(row.get("holdout_pnl", 0.0), 0.0) < 0:
        notes.append("negative holdout split")
    return "; ".join(notes) if notes else "Survives Phase 6B ambiguity/concentration reduction gates; requires Phase 6C deep validation."


def _round_robin_by_family(specs: list[StrategySpec], max_specs: int) -> list[StrategySpec]:
    families = ("opening_range_breakout", "opening_range_failure", "vwap_reclaim_rejection", "prior_session_levels")
    by_family = {family: _interleave_by_timeframe([spec for spec in specs if spec.family == family]) for family in families}
    selected: list[StrategySpec] = []
    while len(selected) < max_specs and any(by_family.values()):
        for family in families:
            if by_family[family] and len(selected) < max_specs:
                selected.append(by_family[family].pop(0))
    return selected


def _interleave_by_timeframe(specs: list[StrategySpec]) -> list[StrategySpec]:
    timeframes = sorted({int(spec.timeframe) for spec in specs})
    buckets = {timeframe: [spec for spec in specs if int(spec.timeframe) == timeframe] for timeframe in timeframes}
    out: list[StrategySpec] = []
    while any(buckets.values()):
        for timeframe in timeframes:
            if buckets[timeframe]:
                out.append(buckets[timeframe].pop(0))
    return out


def _family_order(family: str) -> int:
    order = {
        "opening_range_breakout": 0,
        "opening_range_failure": 1,
        "vwap_reclaim_rejection": 2,
        "prior_session_levels": 3,
    }
    return order.get(family, 99)
