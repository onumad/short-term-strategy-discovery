from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from .ai_search import spec_to_phase4_candidate
from .data_loader import discover_data_files, load_ohlcv_csv
from .instruments import get_instrument
from .phase4a import _prepare_symbol_data, generate_phase4a_signals, simulate_phase4a_candidate
from .scoring import score_candidate_trades
from .strategy_spec import StrategySpec
from .walk_forward import WalkForwardConfig, generate_walk_forward_folds, shared_complete_sessions, summarize_walk_forward


@dataclass(frozen=True)
class Phase5HConfig:
    symbols: tuple[str, ...] = ("MNQ",)
    max_specs: int = 2
    walk_forward: WalkForwardConfig = WalkForwardConfig(train_sessions=120, validation_sessions=30, test_sessions=30, step_sessions=360, min_folds=2, max_candidates=1)

    def validate(self) -> "Phase5HConfig":
        if self.max_specs < 1:
            raise ValueError("max_specs must be positive")
        self.walk_forward.validate()
        return self


@dataclass(frozen=True)
class Phase5HResult:
    fold_results: pd.DataFrame
    search_results: pd.DataFrame
    specs: list[StrategySpec]
    filters: list[dict[str, str]]


def build_session_regimes(features: pd.DataFrame, *, symbol: str) -> pd.DataFrame:
    required = {"symbol", "trading_session", "prior_session_range", "gap_from_prior_close", "or_width_30m", "day_of_week"}
    missing = sorted(required.difference(features.columns))
    if missing:
        raise ValueError(f"missing required columns: {', '.join(missing)}")
    scoped = features[features["symbol"] == symbol].sort_values(["trading_session", "timestamp" if "timestamp" in features.columns else "trading_session"]).copy()
    sessions = scoped.groupby("trading_session", sort=True).first(numeric_only=False).reset_index()
    sessions["prior_range_bucket"] = _tertile_bucket(sessions["prior_session_range"])
    sessions["gap_abs_bucket"] = _tertile_bucket(sessions["gap_from_prior_close"].abs())
    sessions["or_width_bucket"] = _tertile_bucket(sessions["or_width_30m"])
    sessions["weekday_bucket"] = sessions["day_of_week"].map(lambda v: f"dow_{int(v)}" if pd.notna(v) else "unknown")
    return sessions[["trading_session", "prior_range_bucket", "gap_abs_bucket", "or_width_bucket", "weekday_bucket"]]


def filter_trades_by_regime(trades: pd.DataFrame, regimes: pd.DataFrame, criteria: dict[str, str]) -> pd.DataFrame:
    label = regime_filter_label(criteria)
    if trades.empty:
        out = trades.copy()
        out["regime_filter"] = label
        return out
    if not criteria:
        out = trades.copy()
        out["regime_filter"] = label
        return out
    merged = trades.merge(regimes, on="trading_session", how="left")
    mask = pd.Series(True, index=merged.index)
    for column, value in sorted(criteria.items()):
        if column not in merged.columns:
            raise ValueError(f"unknown regime filter column: {column}")
        mask &= merged[column].astype(str).eq(str(value))
    out = merged[mask].copy()
    out["regime_filter"] = label
    return out[trades.columns.tolist() + ["regime_filter"]]


def regime_filter_label(criteria: dict[str, str]) -> str:
    return "all" if not criteria else ";".join(f"{key}={criteria[key]}" for key in sorted(criteria))


def candidate_regime_filters() -> list[dict[str, str]]:
    return [
        {},
        {"prior_range_bucket": "mid"},
        {"prior_range_bucket": "high"},
        {"gap_abs_bucket": "low"},
        {"or_width_bucket": "mid"},
    ]


def rank_regime_filtered_results(candidate_summary: pd.DataFrame) -> pd.DataFrame:
    if candidate_summary.empty:
        return candidate_summary.copy()
    rows: list[dict[str, Any]] = []
    for _, row in candidate_summary.iterrows():
        out = row.to_dict()
        positive_fold_pct = float(out.get("test_positive_fold_pct", 0.0))
        slippage = float(out.get("test_slippage_4_ticks_net_pnl", 0.0))
        active = float(out.get("test_active_session_pct", 0.0))
        day_conc = float(out.get("test_best_day_concentration", 1.0))
        trade_conc = float(out.get("test_best_trade_concentration", 1.0))
        score = 0.0
        score += min(max(float(out.get("test_net_pnl", 0.0)) / 2_000.0, -2.0), 2.0) * 20.0
        score += min(max(slippage / 2_000.0, -2.0), 2.0) * 20.0
        score += positive_fold_pct * 30.0
        score += min(active, 0.75) * 10.0
        score -= max(day_conc - 0.35, 0.0) * 120.0
        score -= max(trade_conc - 0.20, 0.0) * 120.0
        out["phase5h_score"] = round(score, 4)
        out["phase5h_label"] = _phase5h_label(out)
        out["phase5h_notes"] = _phase5h_notes(out)
        rows.append(out)
    ranked = pd.DataFrame(rows).sort_values(["phase5h_score", "test_net_pnl"], ascending=[False, False]).reset_index(drop=True)
    ranked.insert(0, "phase5h_rank", range(1, len(ranked) + 1))
    return ranked


def run_phase5h_search(project_root: Path, config: Phase5HConfig = Phase5HConfig()) -> Phase5HResult:
    config.validate()
    specs = _load_phase5f_top_specs(project_root, config)[: config.max_specs]
    filters = candidate_regime_filters()
    raw_dir = project_root / "data" / "raw"
    files = discover_data_files(raw_dir)
    if not files:
        raise FileNotFoundError(f"No local raw CSV files found under {raw_dir}")
    full_data = pd.concat([load_ohlcv_csv(path) for path in files], ignore_index=True).sort_values(["symbol", "timestamp"])
    features = pd.read_parquet(project_root / "outputs" / "phase5b_features.parquet")
    sessions = shared_complete_sessions(full_data, symbols=config.symbols)
    folds = generate_walk_forward_folds(sessions, config.walk_forward)
    fold_frames: list[pd.DataFrame] = []
    summary_frames: list[pd.DataFrame] = []
    for spec in specs:
        regimes = build_session_regimes(features, symbol=spec.instrument)
        for fold_results in _evaluate_spec_filters(full_data, spec, folds, regimes, filters):
            label = str(fold_results["regime_filter"].iloc[0])
            summary = summarize_walk_forward(fold_results.drop(columns=["regime_filter"]))
            summary["regime_filter"] = label
            fold_frames.append(fold_results)
            summary_frames.append(summary)
    fold_results = pd.concat(fold_frames, ignore_index=True) if fold_frames else pd.DataFrame()
    candidate_summary = pd.concat(summary_frames, ignore_index=True) if summary_frames else pd.DataFrame()
    return Phase5HResult(fold_results=fold_results, search_results=rank_regime_filtered_results(candidate_summary), specs=specs, filters=filters)


def write_phase5h_specs(specs: list[StrategySpec], path: Path) -> None:
    path.write_text(json.dumps([json.loads(spec.to_json()) for spec in specs], indent=2, sort_keys=True), encoding="utf-8")


def _load_phase5f_top_specs(project_root: Path, config: Phase5HConfig) -> list[StrategySpec]:
    specs_by_id = {StrategySpec.from_dict(item).canonical_id(): StrategySpec.from_dict(item) for item in json.loads((project_root / "outputs" / "phase5f_candidate_specs.json").read_text(encoding="utf-8"))}
    ranked = pd.read_csv(project_root / "outputs" / "phase5f_walk_forward_search_results.csv")
    ranked = ranked[ranked["instrument"].isin(config.symbols)].sort_values("phase5f_rank")
    return [specs_by_id[candidate_id] for candidate_id in ranked["candidate_id"] if candidate_id in specs_by_id]


def _evaluate_spec_filters(full_data: pd.DataFrame, spec: StrategySpec, folds: list[Any], regimes: pd.DataFrame, filters: list[dict[str, str]]) -> list[pd.DataFrame]:
    rows_by_filter: dict[str, list[dict[str, Any]]] = {regime_filter_label(criteria): [] for criteria in filters}
    instrument = get_instrument(spec.instrument)
    candidate = spec_to_phase4_candidate(spec)
    for fold in folds:
        fold_sessions = list(fold.all_sessions)
        scoped = full_data[(full_data["symbol"] == spec.instrument) & (full_data["trading_session"].isin(fold_sessions))].copy()
        prepared = _prepare_symbol_data(scoped, fold_sessions)[spec.instrument]
        signals = generate_phase4a_signals(prepared["timeframes"][spec.timeframe], prepared["full"], candidate)
        trades = simulate_phase4a_candidate(prepared["one_minute"], signals, candidate, instrument, fold_sessions)
        for criteria in filters:
            label = regime_filter_label(criteria)
            filtered = filter_trades_by_regime(trades, regimes, criteria)
            for segment, segment_sessions in [("train", fold.train_sessions), ("validation", fold.validation_sessions), ("test", fold.test_sessions)]:
                segment_trades = filtered[filtered["trading_session"].isin(segment_sessions)].copy() if not filtered.empty else filtered
                row = {"fold": fold.fold, "segment": segment, "segment_start": segment_sessions[0], "segment_end": segment_sessions[-1], "regime_filter": label, **score_candidate_trades(spec, segment_trades, instrument, list(segment_sessions)).to_dict()}
                rows_by_filter[label].append(row)
    return [pd.DataFrame(rows) for rows in rows_by_filter.values()]


def _tertile_bucket(series: pd.Series) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce")
    ranked = values.rank(method="first", pct=True)
    return pd.cut(ranked, bins=[-0.01, 1 / 3, 2 / 3, 1.01], labels=["low", "mid", "high"]).astype("object").fillna("unknown")


def _phase5h_label(row: dict[str, Any]) -> str:
    if float(row.get("test_slippage_4_ticks_net_pnl", 0.0)) <= 0 or float(row.get("test_positive_fold_pct", 0.0)) < 0.67:
        return "rejected"
    if float(row.get("test_best_day_concentration", 1.0)) <= 0.35 and float(row.get("test_best_trade_concentration", 1.0)) <= 0.20:
        return "regime_filtered_candidate"
    return "watchlist_concentrated"


def _phase5h_notes(row: dict[str, Any]) -> str:
    notes: list[str] = []
    if float(row.get("test_positive_fold_pct", 0.0)) < 0.67:
        notes.append("weak positive-fold coverage")
    if float(row.get("test_slippage_4_ticks_net_pnl", 0.0)) <= 0:
        notes.append("fails aggregate 4-tick slippage stress")
    if float(row.get("test_best_day_concentration", 1.0)) > 0.35:
        notes.append("day concentration remains")
    if float(row.get("test_best_trade_concentration", 1.0)) > 0.20:
        notes.append("trade concentration remains")
    return "; ".join(notes) if notes else "Regime filter reduces concentration enough for further research."
