from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

from .ai_search import spec_to_phase4_candidate
from .data_loader import discover_data_files, load_ohlcv_csv
from .instruments import get_instrument
from .phase4a import _prepare_symbol_data
from .phase4a import generate_phase4a_signals, simulate_phase4a_candidate
from .scoring import score_candidate_trades
from .strategy_spec import StrategySpec


@dataclass(frozen=True)
class WalkForwardConfig:
    train_sessions: int = 360
    validation_sessions: int = 120
    test_sessions: int = 120
    step_sessions: int = 120
    min_folds: int = 1
    max_candidates: int = 6

    def validate(self) -> "WalkForwardConfig":
        for name, value in [
            ("train_sessions", self.train_sessions),
            ("validation_sessions", self.validation_sessions),
            ("test_sessions", self.test_sessions),
            ("step_sessions", self.step_sessions),
            ("min_folds", self.min_folds),
            ("max_candidates", self.max_candidates),
        ]:
            if int(value) < 1:
                raise ValueError(f"{name} must be positive")
        return self


@dataclass(frozen=True)
class WalkForwardFold:
    fold: int
    train_sessions: tuple[Any, ...]
    validation_sessions: tuple[Any, ...]
    test_sessions: tuple[Any, ...]

    @property
    def all_sessions(self) -> tuple[Any, ...]:
        return self.train_sessions + self.validation_sessions + self.test_sessions


@dataclass(frozen=True)
class WalkForwardResult:
    fold_results: pd.DataFrame
    candidate_summary: pd.DataFrame
    folds: list[WalkForwardFold]
    specs: list[StrategySpec]


def generate_walk_forward_folds(sessions: Iterable[Any], config: WalkForwardConfig = WalkForwardConfig()) -> list[WalkForwardFold]:
    config.validate()
    ordered = list(sessions)
    window = config.train_sessions + config.validation_sessions + config.test_sessions
    if len(ordered) < window:
        raise ValueError(f"Need at least {window} sessions for walk-forward validation, got {len(ordered)}")

    folds: list[WalkForwardFold] = []
    start = 0
    while start + window <= len(ordered):
        train_end = start + config.train_sessions
        validation_end = train_end + config.validation_sessions
        test_end = validation_end + config.test_sessions
        folds.append(
            WalkForwardFold(
                fold=len(folds) + 1,
                train_sessions=tuple(ordered[start:train_end]),
                validation_sessions=tuple(ordered[train_end:validation_end]),
                test_sessions=tuple(ordered[validation_end:test_end]),
            )
        )
        start += config.step_sessions

    if len(folds) < config.min_folds:
        raise ValueError(f"Expected at least {config.min_folds} folds, generated {len(folds)}")
    return folds


def load_phase5c_top_specs(project_root: Path, max_candidates: int = 6) -> list[StrategySpec]:
    results_path = project_root / "outputs" / "phase5c_search_results.csv"
    specs_path = project_root / "outputs" / "phase5c_candidate_specs.json"
    if results_path.exists():
        ranked = pd.read_csv(results_path)
        label_order = {
            "robust_research_candidate": 0,
            "watchlist": 1,
            "watchlist_needs_validation": 2,
            "rejected": 3,
        }
        ranked["_label_order"] = ranked["phase5c_label"].map(label_order).fillna(99)
        ranked = ranked.sort_values(["_label_order", "phase5c_score", "ranking_score"], ascending=[True, False, False])
        specs = [StrategySpec.from_json(str(payload)) for payload in ranked["spec_json"].head(max_candidates)]
        if specs:
            return specs
    if not specs_path.exists():
        raise FileNotFoundError(f"Missing Phase 5C specs at {specs_path}")
    payload = json.loads(specs_path.read_text(encoding="utf-8"))
    return [StrategySpec.from_dict(item) for item in payload[:max_candidates]]


def run_walk_forward_validation(project_root: Path, config: WalkForwardConfig = WalkForwardConfig()) -> WalkForwardResult:
    config.validate()
    raw_dir = project_root / "data" / "raw"
    files = discover_data_files(raw_dir)
    if not files:
        raise FileNotFoundError(f"No local raw CSV files found under {raw_dir}")
    full_data = pd.concat([load_ohlcv_csv(path) for path in files], ignore_index=True).sort_values(["symbol", "timestamp"])
    complete_sessions = shared_complete_sessions(full_data, symbols=tuple(spec.instrument for spec in load_phase5c_top_specs(project_root, config.max_candidates)))
    folds = generate_walk_forward_folds(complete_sessions, config)
    specs = load_phase5c_top_specs(project_root, config.max_candidates)

    rows: list[dict[str, Any]] = []
    for fold in folds:
        fold_sessions = list(fold.all_sessions)
        for symbol in dict.fromkeys(spec.instrument for spec in specs):
            symbol_specs = [spec for spec in specs if spec.instrument == symbol]
            scoped = full_data[(full_data["symbol"] == symbol) & (full_data["trading_session"].isin(fold_sessions))].copy()
            prepared = _prepare_symbol_data(scoped, fold_sessions)[symbol]
            for spec in symbol_specs:
                phase4_candidate = spec_to_phase4_candidate(spec)
                signal_bars = prepared["timeframes"][spec.timeframe]
                signals = generate_phase4a_signals(signal_bars, prepared["full"], phase4_candidate)
                trades = simulate_phase4a_candidate(prepared["one_minute"], signals, phase4_candidate, get_instrument(symbol), fold_sessions)
                for segment, segment_sessions in [
                    ("train", fold.train_sessions),
                    ("validation", fold.validation_sessions),
                    ("test", fold.test_sessions),
                ]:
                    segment_trades = trades[trades["trading_session"].isin(segment_sessions)].copy() if not trades.empty else trades
                    score = score_candidate_trades(spec, segment_trades, get_instrument(symbol), list(segment_sessions)).to_dict()
                    rows.append(
                        {
                            "fold": fold.fold,
                            "segment": segment,
                            "segment_start": segment_sessions[0],
                            "segment_end": segment_sessions[-1],
                            **score,
                        }
                    )
    fold_results = pd.DataFrame(rows)
    candidate_summary = summarize_walk_forward(fold_results)
    return WalkForwardResult(fold_results=fold_results, candidate_summary=candidate_summary, folds=folds, specs=specs)


def shared_complete_sessions(full_data: pd.DataFrame, symbols: tuple[str, ...], min_bars: int = 1_000) -> list[Any]:
    """Return full-history sessions complete for every requested symbol.

    The older discovery helper intentionally scopes to the original recent
    research window. Phase 5D needs the expanded 2023-2026 history, so it uses a
    local full-history complete-session intersection instead.
    """
    session_sets = []
    for symbol in dict.fromkeys(symbols):
        symbol_df = full_data[full_data["symbol"] == symbol]
        counts = symbol_df.groupby("trading_session").size()
        session_sets.append(set(counts[counts >= min_bars].index.tolist()))
    if not session_sets:
        return []
    return sorted(set.intersection(*session_sets))


def summarize_walk_forward(fold_results: pd.DataFrame) -> pd.DataFrame:
    if fold_results.empty:
        return pd.DataFrame()
    summaries: list[dict[str, Any]] = []
    for candidate_id, group in fold_results.groupby("candidate_id", sort=False):
        test = group[group["segment"] == "test"].copy()
        validation = group[group["segment"] == "validation"].copy()
        first = group.iloc[0]
        test_positive = int((test["net_pnl"] > 0).sum())
        folds = int(test["fold"].nunique())
        row = {
            "candidate_id": candidate_id,
            "instrument": first["instrument"],
            "family": first["family"],
            "timeframe": int(first["timeframe"]),
            "folds": folds,
            "validation_net_pnl": round(float(validation["net_pnl"].sum()), 4),
            "test_net_pnl": round(float(test["net_pnl"].sum()), 4),
            "test_slippage_4_ticks_net_pnl": round(float(test["slippage_4_ticks_net_pnl"].sum()), 4),
            "test_trades": int(test["trades"].sum()),
            "test_active_sessions": int(test["active_sessions"].sum()),
            "test_active_session_pct": round(float(test["active_sessions"].sum() / test_sessions_total(test)), 6),
            "test_win_rate": round(weighted_mean(test, "win_rate", "trades"), 6),
            "test_avg_trade": round(weighted_mean(test, "avg_trade", "trades"), 6),
            "worst_test_fold_pnl": round(float(test["net_pnl"].min()), 4),
            "max_test_drawdown": round(float(test["max_drawdown"].min()), 4),
            "test_best_day_concentration": round(float(test["best_day_concentration"].max()), 6),
            "test_best_trade_concentration": round(float(test["best_trade_concentration"].max()), 6),
            "test_positive_folds": test_positive,
            "test_positive_fold_pct": round(float(test_positive / folds), 6) if folds else 0.0,
        }
        summaries.append(apply_walk_forward_promotion(row))
    return pd.DataFrame(summaries).sort_values(["phase5d_score", "test_net_pnl"], ascending=[False, False]).reset_index(drop=True)


def test_sessions_total(test_rows: pd.DataFrame) -> int:
    if test_rows.empty:
        return 0
    return int(round((test_rows["active_sessions"] / test_rows["active_session_pct"].replace(0, pd.NA)).fillna(0).sum()))


def weighted_mean(rows: pd.DataFrame, value_col: str, weight_col: str) -> float:
    weights = rows[weight_col].astype(float)
    if rows.empty or float(weights.sum()) == 0.0:
        return 0.0
    return float((rows[value_col].astype(float) * weights).sum() / weights.sum())


def apply_walk_forward_promotion(row: dict[str, Any]) -> dict[str, Any]:
    out = dict(row)
    folds = max(int(out.get("folds", 0)), 1)
    positive_pct = float(out.get("test_positive_fold_pct", 0.0))
    test_net = float(out.get("test_net_pnl", 0.0))
    slippage_net = float(out.get("test_slippage_4_ticks_net_pnl", 0.0))
    active_pct = float(out.get("test_active_session_pct", 0.0))
    worst_fold = float(out.get("worst_test_fold_pnl", 0.0))
    drawdown = float(out.get("max_test_drawdown", 0.0))
    day_conc = float(out.get("test_best_day_concentration", 1.0))
    trade_conc = float(out.get("test_best_trade_concentration", 1.0))
    trades = int(out.get("test_trades", 0))

    score = 0.0
    score += min(max(test_net / 2_500.0, -2.0), 2.0) * 20.0
    score += min(max(slippage_net / 2_500.0, -2.0), 2.0) * 15.0
    score += positive_pct * 25.0
    score += min(active_pct, 1.0) * 15.0
    score += min(trades / max(folds * 40.0, 1.0), 1.0) * 10.0
    score -= min(abs(drawdown) / 2_500.0, 2.0) * 10.0
    score -= max(day_conc - 0.35, 0.0) * 25.0
    score -= max(trade_conc - 0.20, 0.0) * 25.0
    score -= abs(min(worst_fold, 0.0)) / 250.0
    out["phase5d_score"] = round(float(score), 4)

    notes: list[str] = []
    if positive_pct < 0.60:
        notes.append("insufficient positive test folds")
    if test_net <= 0:
        notes.append("negative aggregate test PnL")
    if slippage_net <= 0:
        notes.append("fails aggregate 4-tick slippage stress")
    if active_pct < 0.35:
        notes.append("low test active-session coverage")
    if day_conc > 0.35 or trade_conc > 0.20:
        notes.append("test concentration risk")
    if worst_fold < -1_000:
        notes.append("large negative test fold")
    if trades < folds * 10:
        notes.append("too few test trades")

    if test_net <= 0 or slippage_net <= 0 or positive_pct < 0.50 or trades < folds * 5:
        label = "rejected"
    elif positive_pct >= 0.60 and active_pct >= 0.35 and day_conc <= 0.35 and trade_conc <= 0.20 and out["phase5d_score"] >= 35:
        label = "paper_test_candidate"
    elif positive_pct >= 0.50 and slippage_net > 0:
        label = "robust_research_candidate"
    else:
        label = "watchlist"
    out["phase5d_label"] = label
    out["phase5d_notes"] = "; ".join(notes) if notes else "Passed Phase 5D promotion gates."
    return out
