from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

from .data_loader import discover_data_files, load_ohlcv_csv
from .discovery import _shared_complete_sessions
from .features import build_feature_frame
from .instruments import get_instrument
from .phase3b import ExecutionMode
from .phase4a import Phase4ACandidate, _prepare_symbol_data, generate_phase4a_signals, simulate_phase4a_candidate
from .scoring import CandidateScore, score_candidate_trades
from .strategy_spec import EntryRule, ExitRule, RiskRule, SearchSpace, StrategySpec


@dataclass(frozen=True)
class SearchConfig:
    symbols: tuple[str, ...] = ("MNQ", "MGC")
    max_candidates: int = 32
    recent_sessions: int = 120
    timeframes: tuple[int, ...] = (1, 3, 5)
    opening_range_minutes: tuple[int, ...] = (15, 30, 60)

    def validate(self) -> "SearchConfig":
        if self.max_candidates < 1:
            raise ValueError("max_candidates must be positive")
        if self.recent_sessions < 2:
            raise ValueError("recent_sessions must include at least two sessions")
        SearchSpace(symbols=self.symbols, timeframes=self.timeframes, opening_range_minutes=self.opening_range_minutes).validate()
        return self


@dataclass(frozen=True)
class SearchResult:
    candidates: pd.DataFrame
    feature_summary: pd.DataFrame
    complete_sessions: list[Any]
    searched_specs: list[StrategySpec]


def propose_strategy_specs(config: SearchConfig) -> list[StrategySpec]:
    config.validate()
    specs: list[StrategySpec] = []
    for symbol in config.symbols:
        min_range = {"MNQ": 10.0, "MGC": 1.0}[symbol]
        tick = get_instrument(symbol).tick_size
        stop_target_pairs = {"MNQ": [(40, 60), (60, 90)], "MGC": [(12, 18), (18, 27)]}[symbol]
        for timeframe in config.timeframes:
            for minutes in config.opening_range_minutes:
                for target in ("mid", "opposite"):
                    for max_trades in (1, 2):
                        specs.append(
                            StrategySpec(
                                instrument=symbol,
                                family="opening_range_failure",
                                timeframe=timeframe,
                                entry=EntryRule("close_back_inside", {"or_minutes": minutes, "target": target, "min_range": min_range}),
                                exit=ExitRule("range_target", {"target": target}),
                                risk=RiskRule("one_open_position", {"max_trades_per_day": max_trades}),
                                notes="Deterministic AI-search proposal: fade failed opening-range break after bar closes back inside.",
                            ).validate()
                        )
                for rr in ("1R", "2R"):
                    specs.append(
                        StrategySpec(
                            instrument=symbol,
                            family="opening_range_breakout",
                            timeframe=timeframe,
                            entry=EntryRule("close_outside_range", {"or_minutes": minutes, "min_range": min_range}),
                            exit=ExitRule("r_multiple", {"target": rr, "stop_mode": "half_range"}),
                            risk=RiskRule("one_open_position", {"max_trades_per_day": 1}),
                            notes="Deterministic AI-search proposal: opening-range breakout with fixed R multiple.",
                        ).validate()
                    )
            for mode in ("reclaim", "rejection", "both"):
                for stop_ticks, target_ticks in stop_target_pairs:
                    specs.append(
                        StrategySpec(
                            instrument=symbol,
                            family="vwap_reclaim_rejection",
                            timeframe=timeframe,
                            entry=EntryRule("vwap_cross", {"mode": mode}),
                            exit=ExitRule("fixed_ticks", {"stop_ticks": stop_ticks, "target_ticks": target_ticks}),
                            risk=RiskRule("one_open_position", {"max_trades_per_day": 2}),
                            notes="Deterministic AI-search proposal: VWAP reclaim/rejection confirmation.",
                        ).validate()
                    )
            for mode in ("break_hold", "sweep_reverse", "prior_close_reclaim"):
                stop_ticks, target_ticks = stop_target_pairs[0]
                specs.append(
                    StrategySpec(
                        instrument=symbol,
                        family="prior_session_levels",
                        timeframe=timeframe,
                        entry=EntryRule("prior_level_reaction", {"mode": mode}),
                        exit=ExitRule("fixed_ticks", {"stop_ticks": stop_ticks, "target_ticks": target_ticks}),
                        risk=RiskRule("one_open_position", {"max_trades_per_day": 2}),
                        notes="Deterministic AI-search proposal: prior-session level reaction.",
                    ).validate()
                )
    return specs[: config.max_candidates]


def run_bounded_search(project_root: Path, config: SearchConfig = SearchConfig()) -> SearchResult:
    config.validate()
    raw_dir = project_root / "data" / "raw"
    files = discover_data_files(raw_dir)
    if not files:
        raise FileNotFoundError(f"No local raw CSV files found under {raw_dir}")
    frames = [load_ohlcv_csv(path) for path in files]
    full_data = pd.concat(frames, ignore_index=True).sort_values(["symbol", "timestamp"])
    complete_sessions = _shared_complete_sessions(full_data)
    if config.recent_sessions:
        complete_sessions = complete_sessions[-config.recent_sessions :]
    scoped = full_data[(full_data["symbol"].isin(config.symbols)) & (full_data["trading_session"].isin(complete_sessions))].copy()
    prepared = _prepare_symbol_data(scoped, complete_sessions)
    specs = propose_strategy_specs(config)
    rows: list[dict[str, Any]] = []
    for spec in specs:
        score = _score_spec(spec, prepared, complete_sessions)
        rows.append(score.to_dict())
    candidates = pd.DataFrame(rows).sort_values(["ranking_score", "net_pnl", "trades"], ascending=[False, False, False]).reset_index(drop=True)
    feature_summary = summarize_feature_inputs(scoped, config)
    return SearchResult(candidates=candidates, feature_summary=feature_summary, complete_sessions=complete_sessions, searched_specs=specs)


def summarize_feature_inputs(scoped_data: pd.DataFrame, config: SearchConfig) -> pd.DataFrame:
    rows = []
    for symbol, symbol_df in scoped_data.groupby("symbol", sort=True):
        rth = symbol_df[symbol_df["session_segment"] == "RTH"].copy()
        if rth.empty:
            continue
        features = build_feature_frame(rth, opening_range_minutes=min(config.opening_range_minutes), forward_minutes=5)
        rows.append(
            {
                "symbol": symbol,
                "rows": int(len(features)),
                "sessions": int(features["trading_session"].nunique()),
                "first_timestamp": str(features["timestamp"].min()),
                "last_timestamp": str(features["timestamp"].max()),
                "feature_columns": ",".join([c for c in features.columns if c not in rth.columns]),
            }
        )
    return pd.DataFrame(rows)


def _score_spec(spec: StrategySpec, prepared: dict[str, dict[str, Any]], complete_sessions: list[Any]) -> CandidateScore:
    symbol_data = prepared.get(spec.instrument)
    if symbol_data is None:
        raise ValueError(f"No prepared data for {spec.instrument}")
    phase4_candidate = spec_to_phase4_candidate(spec)
    signal_bars = symbol_data["timeframes"][spec.timeframe]
    signals = generate_phase4a_signals(signal_bars, symbol_data["full"], phase4_candidate)
    trades = simulate_phase4a_candidate(symbol_data["one_minute"], signals, phase4_candidate, get_instrument(spec.instrument), complete_sessions)
    return score_candidate_trades(spec, trades, get_instrument(spec.instrument), complete_sessions)


def spec_to_phase4_candidate(spec: StrategySpec) -> Phase4ACandidate:
    spec.validate()
    params = _phase4_params(spec)
    side_filter = str(spec.risk.params.get("side_filter", "both"))
    if side_filter not in {"both", "long", "short"}:
        raise ValueError("side_filter must be one of: both, long, short")
    if side_filter != "both":
        params["side_filter"] = side_filter
    max_trades = int(spec.risk.params.get("max_trades_per_day", 1))
    mode = ExecutionMode(
        "phase5_one_open_position" if max_trades == 1 else "phase5_max2_one_open_position",
        max_trades_per_day=max_trades,
        one_open_position=True,
        stop_after_first_loser=bool(spec.risk.params.get("stop_after_first_loser", False)),
    )
    return Phase4ACandidate(
        candidate_id=spec.canonical_id(),
        instrument=spec.instrument,
        family=spec.family,
        variant=spec.canonical_id().split(f"{spec.family}_", 1)[-1],
        signal_timeframe=int(spec.timeframe),
        execution_timeframe="1m",
        entry_rule=spec.entry.name,
        stop_rule=spec.exit.name,
        target_rule=str(spec.exit.params.get("target", spec.exit.params.get("target_ticks", spec.exit.params.get("rr", "configured")))),
        time_stop="15:55 ET",
        mode=mode,
        params=params,
        discovery_role="ai_search_foundation",
        manual_rule=False,
    )


def _phase4_params(spec: StrategySpec) -> dict[str, Any]:
    tick = get_instrument(spec.instrument).tick_size
    if spec.family == "opening_range_failure":
        return {
            "or_minutes": int(spec.entry.params["or_minutes"]),
            "target": str(spec.entry.params["target"]),
            "min_range": float(spec.entry.params["min_range"]),
        }
    if spec.family == "opening_range_breakout":
        return {
            "or_minutes": int(spec.entry.params["or_minutes"]),
            "stop_mode": str(spec.exit.params.get("stop_mode", "half_range")),
            "target": str(spec.exit.params["target"]),
            "min_range": float(spec.entry.params["min_range"]),
        }
    if spec.family == "opening_drive_continuation":
        return {
            "drive_minutes": int(spec.entry.params["drive_minutes"]),
            "minimum_drive_ticks": int(spec.entry.params["minimum_drive_ticks"]),
            "breakout_offset_ticks": int(spec.entry.params.get("breakout_offset_ticks", 1)),
            "stop_buffer_ticks": int(spec.exit.params.get("stop_buffer_ticks", 1)),
            "target": str(spec.exit.params["target"]),
            "tick_size": tick,
        }
    if spec.family == "vwap_pullback_continuation":
        return {
            "pullback_ref": str(spec.entry.params.get("pullback_ref", "vwap")),
            "pullback_ticks": int(spec.entry.params["pullback_ticks"]),
            "start_minute": int(spec.entry.params.get("start_minute", 0)),
            "min_slope_ticks": int(spec.entry.params.get("min_slope_ticks", 0)),
            "stop_ticks": int(spec.exit.params["stop_ticks"]),
            "target_ticks": int(spec.exit.params["target_ticks"]),
            "tick_size": tick,
        }
    if spec.family == "vwap_reclaim_rejection":
        return {
            "mode": str(spec.entry.params["mode"]),
            "stop_ticks": int(spec.exit.params["stop_ticks"]),
            "target_ticks": int(spec.exit.params["target_ticks"]),
            "tick_size": tick,
        }
    if spec.family == "prior_session_levels":
        return {
            "mode": str(spec.entry.params["mode"]),
            "stop_ticks": int(spec.exit.params["stop_ticks"]),
            "target_ticks": int(spec.exit.params["target_ticks"]),
            "tick_size": tick,
        }
    raise ValueError(f"Unsupported spec family for Phase 5A conversion: {spec.family}")
