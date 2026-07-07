from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from .data_loader import discover_data_files, load_ohlcv_csv
from .phase4a import resample_signal_bars
from .phase5n import Phase5NResult, _finite_float, score_prefilter_specs
from .strategy_spec import EntryRule, ExitRule, RiskRule, StrategySpec
from .walk_forward import shared_complete_sessions


@dataclass(frozen=True)
class Phase7AConfig:
    symbol: str = "MGC"
    max_specs: int = 18
    min_specs: int = 12
    batch_size: int = 1
    max_new_specs_per_run: int | None = None
    timeframes: tuple[int, ...] = (1, 3, 5)

    def validate(self) -> "Phase7AConfig":
        if self.symbol != "MGC":
            raise ValueError("Phase 7A is intentionally MGC-only")
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
        return self


def select_mgc_reproduction_specs(config: Phase7AConfig = Phase7AConfig()) -> list[StrategySpec]:
    """Port the older project's MGC VWAP-pullback and opening-drive ideas as deterministic specs."""
    config.validate()
    specs: list[StrategySpec] = []
    symbol = config.symbol
    for timeframe in config.timeframes:
        for pullback_ticks in (2, 3):
            for stop_ticks, target_ticks in ((6, 6), (8, 8)):
                for cooldown in (3, 5):
                    specs.append(
                        StrategySpec(
                            instrument=symbol,
                            family="vwap_pullback_continuation",
                            timeframe=int(timeframe),
                            entry=EntryRule(
                                "vwap_pullback",
                                {
                                    "pullback_ref": "vwap",
                                    "pullback_ticks": pullback_ticks,
                                    "start_minute": 0,
                                    "min_slope_ticks": 0,
                                },
                            ),
                            exit=ExitRule("fixed_ticks", {"stop_ticks": stop_ticks, "target_ticks": target_ticks}),
                            risk=RiskRule("one_open_position", {"max_trades_per_day": 3, "side_filter": "short", "cooldown_minutes": cooldown}),
                            notes="Phase 7A port of older MGC VWAP pullback short-only reproduction candidate.",
                        ).validate()
                    )
    for timeframe in config.timeframes:
        for drive_minutes in (5, 10):
            for minimum_drive_ticks in (4, 8):
                specs.append(
                    StrategySpec(
                        instrument=symbol,
                        family="opening_drive_continuation",
                        timeframe=int(timeframe),
                        entry=EntryRule(
                            "opening_drive_breakout",
                            {
                                "drive_minutes": drive_minutes,
                                "minimum_drive_ticks": minimum_drive_ticks,
                                "breakout_offset_ticks": 1,
                            },
                        ),
                        exit=ExitRule("r_multiple", {"stop_buffer_ticks": 1, "target": "2R"}),
                        risk=RiskRule("one_open_position", {"max_trades_per_day": 1}),
                        notes="Phase 7A port of older MGC opening-drive continuation reproduction candidate.",
                    ).validate()
                )
    ordered = sorted(
        {spec.canonical_id(): spec for spec in specs}.values(),
        key=lambda spec: (
            0 if spec.family == "vwap_pullback_continuation" else 1,
            int(spec.timeframe),
            json.dumps(spec.entry.params, sort_keys=True),
            json.dumps(spec.exit.params, sort_keys=True),
            json.dumps(spec.risk.params, sort_keys=True),
            spec.canonical_id(),
        ),
    )
    selected = _round_robin_by_family(ordered, config.max_specs)
    if len(selected) < config.min_specs:
        raise ValueError(f"Phase 7A expected at least {config.min_specs} specs, selected {len(selected)}")
    return selected


def run_phase7a_reproduction(project_root: Path, config: Phase7AConfig = Phase7AConfig(), checkpoint_path: Path | None = None) -> Phase5NResult:
    config.validate()
    specs = select_mgc_reproduction_specs(config)
    if config.max_new_specs_per_run == 0:
        if checkpoint_path is None or not checkpoint_path.exists():
            return Phase5NResult(search_results=rank_phase7a_results(pd.DataFrame()), specs=specs, complete_sessions=[])
        return Phase5NResult(search_results=rank_phase7a_results(pd.read_csv(checkpoint_path)), specs=specs, complete_sessions=[])
    specs_for_run = _limit_specs_for_run(specs, checkpoint_path, config.max_new_specs_per_run)
    prepared, complete_sessions = _prepare_phase7a_data(project_root, config)
    scored = score_prefilter_specs(
        specs_for_run,
        prepared,
        complete_sessions,
        checkpoint_path=checkpoint_path,
        batch_size=config.batch_size,
    )
    return Phase5NResult(search_results=rank_phase7a_results(scored), specs=specs, complete_sessions=complete_sessions)


def rank_phase7a_results(candidate_summary: pd.DataFrame) -> pd.DataFrame:
    if candidate_summary.empty:
        return candidate_summary.copy()
    reusable = candidate_summary.drop(
        columns=[
            column
            for column in ("phase5n_rank", "phase5n_score", "phase5n_label", "phase5n_notes", "phase7a_rank", "phase7a_score", "phase7a_label", "phase7a_notes")
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
        score += min(max(net / 2_500.0, -2.0), 2.0) * 8.0
        score += min(max(slippage / 2_500.0, -2.0), 2.0) * 34.0
        score += min(max(validation / 1_000.0, -2.0), 2.0) * 10.0
        score += min(max(holdout / 1_000.0, -2.0), 2.0) * 14.0
        score += min(active, 0.40) * 12.0
        score += min(trades / 90.0, 1.0) * 8.0
        score -= min(abs(drawdown) / 1_500.0, 2.5) * 18.0
        score -= max(day - 0.25, 0.0) * 220.0
        score -= max(trade - 0.16, 0.0) * 220.0
        score -= min(ambiguity, 10) * 3.0
        if slippage <= 0:
            score -= 55.0
        if active < 0.10:
            score -= 20.0
        if trades < 30:
            score -= 22.0
        if validation < 0 or holdout < 0:
            score -= 14.0
        out["phase7a_score"] = round(float(score), 4)
        out["phase7a_label"] = _phase7a_label(out)
        out["phase7a_notes"] = _phase7a_notes(out)
        rows.append(out)
    ranked = pd.DataFrame(rows).sort_values(["phase7a_score", "slippage_4_ticks_net_pnl", "net_pnl"], ascending=[False, False, False]).reset_index(drop=True)
    ranked.insert(0, "phase7a_rank", range(1, len(ranked) + 1))
    return ranked


def write_phase7a_specs(specs: list[StrategySpec], path: Path) -> None:
    path.write_text(json.dumps([json.loads(spec.to_json()) for spec in specs], indent=2, sort_keys=True), encoding="utf-8")


def _prepare_phase7a_data(project_root: Path, config: Phase7AConfig) -> tuple[dict[str, dict[str, Any]], list[Any]]:
    raw_dir = project_root / "data" / "raw"
    files = discover_data_files(raw_dir)
    if not files:
        raise FileNotFoundError(f"No local raw CSV files found under {raw_dir}")
    source_files = [path for path in files if config.symbol.lower() in path.name.lower()]
    if not source_files:
        raise FileNotFoundError(f"No {config.symbol} raw CSV files found under {raw_dir}")
    full_data = pd.concat([load_ohlcv_csv(path) for path in source_files], ignore_index=True)
    full_data = full_data[full_data["symbol"].eq(config.symbol)].sort_values(["symbol", "timestamp"])
    sessions = shared_complete_sessions(full_data, symbols=(config.symbol,))
    scoped = full_data[(full_data["symbol"] == config.symbol) & (full_data["trading_session"].isin(sessions))].copy()
    full_symbol = scoped[scoped["trading_session"].isin(sessions)].copy()
    one_minute = full_symbol[full_symbol["session_segment"] == "RTH"].sort_values("timestamp").copy()
    return {
        config.symbol: {
            "full": full_symbol,
            "one_minute": one_minute,
            "timeframes": {tf: resample_signal_bars(one_minute, tf) for tf in sorted(set(config.timeframes))},
        }
    }, sessions


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


def _round_robin_by_family(specs: list[StrategySpec], max_specs: int) -> list[StrategySpec]:
    by_family = {
        "vwap_pullback_continuation": [spec for spec in specs if spec.family == "vwap_pullback_continuation"],
        "opening_drive_continuation": [spec for spec in specs if spec.family == "opening_drive_continuation"],
    }
    selected: list[StrategySpec] = []
    while len(selected) < max_specs and any(by_family.values()):
        for family in ("vwap_pullback_continuation", "opening_drive_continuation"):
            if by_family[family] and len(selected) < max_specs:
                selected.append(by_family[family].pop(0))
    return selected


def _phase7a_label(row: dict[str, Any]) -> str:
    if _finite_float(row.get("slippage_4_ticks_net_pnl", 0.0), 0.0) <= 0:
        return "rejected"
    if int(_finite_float(row.get("trades", 0), 0.0)) < 30:
        return "rejected"
    if _finite_float(row.get("active_session_pct", 0.0), 0.0) < 0.10:
        return "rejected"
    if _finite_float(row.get("best_day_concentration", 1.0), 1.0) > 0.25:
        return "rejected"
    if _finite_float(row.get("best_trade_concentration", 1.0), 1.0) > 0.16:
        return "rejected"
    if _finite_float(row.get("max_drawdown", 0.0), 0.0) < -1_500.0:
        return "rejected"
    if int(_finite_float(row.get("same_bar_stop_target_ambiguity_count", 0), 0.0)) > 0:
        return "rejected"
    if _finite_float(row.get("validation_pnl", 0.0), 0.0) < 0 or _finite_float(row.get("holdout_pnl", 0.0), 0.0) < 0:
        return "mgc_reproduction_watchlist"
    return "mgc_reproduction_prefilter_survivor"


def _phase7a_notes(row: dict[str, Any]) -> str:
    notes: list[str] = []
    if _finite_float(row.get("slippage_4_ticks_net_pnl", 0.0), 0.0) <= 0:
        notes.append("fails aggregate 4-tick slippage stress")
    if int(_finite_float(row.get("trades", 0), 0.0)) < 30:
        notes.append("too few full-history trades")
    if _finite_float(row.get("active_session_pct", 0.0), 0.0) < 0.10:
        notes.append("insufficient active-day coverage")
    if _finite_float(row.get("best_day_concentration", 1.0), 1.0) > 0.25:
        notes.append("one-day concentration risk")
    if _finite_float(row.get("best_trade_concentration", 1.0), 1.0) > 0.16:
        notes.append("one-trade concentration risk")
    if _finite_float(row.get("max_drawdown", 0.0), 0.0) < -1_500.0:
        notes.append("drawdown exceeds Phase 7A cap")
    if int(_finite_float(row.get("same_bar_stop_target_ambiguity_count", 0), 0.0)) > 0:
        notes.append("same-bar stop/target ambiguity remains")
    if _finite_float(row.get("validation_pnl", 0.0), 0.0) < 0:
        notes.append("negative validation split")
    if _finite_float(row.get("holdout_pnl", 0.0), 0.0) < 0:
        notes.append("negative holdout split")
    return "; ".join(notes) if notes else "Survives Phase 7A MGC reproduction prefilter gates; requires walk-forward validation."
