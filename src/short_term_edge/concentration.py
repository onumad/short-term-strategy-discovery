from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from .ai_search import spec_to_phase4_candidate
from .data_loader import discover_data_files, load_ohlcv_csv
from .instruments import get_instrument
from .phase4a import _prepare_symbol_data, generate_phase4a_signals, simulate_phase4a_candidate
from .strategy_spec import StrategySpec
from .walk_forward import WalkForwardConfig, generate_walk_forward_folds, shared_complete_sessions


def build_period_pnl(trades: pd.DataFrame, freq: str) -> pd.DataFrame:
    if trades.empty:
        return pd.DataFrame(columns=["candidate_id", "period", "net_pnl", "trades", "active_sessions", "avg_trade"])
    out = trades.copy()
    sessions = pd.to_datetime(out["trading_session"])
    if freq == "D":
        out["period"] = sessions.dt.strftime("%Y-%m-%d")
    elif freq == "W":
        iso = sessions.dt.isocalendar()
        out["period"] = iso["year"].astype(str) + "-W" + iso["week"].astype(str).str.zfill(2)
    elif freq == "M":
        out["period"] = sessions.dt.strftime("%Y-%m")
    else:
        raise ValueError("freq must be D, W, or M")
    return (
        out.groupby(["candidate_id", "period"], sort=True)
        .agg(net_pnl=("net_pnl", "sum"), trades=("net_pnl", "size"), active_sessions=("trading_session", "nunique"), avg_trade=("net_pnl", "mean"))
        .reset_index()
    )


def summarize_concentration(day_pnl: pd.DataFrame, week_pnl: pd.DataFrame, month_pnl: pd.DataFrame) -> pd.DataFrame:
    candidates = sorted(set(day_pnl.get("candidate_id", pd.Series(dtype=str))).union(week_pnl.get("candidate_id", pd.Series(dtype=str))).union(month_pnl.get("candidate_id", pd.Series(dtype=str))))
    rows: list[dict[str, Any]] = []
    for candidate_id in candidates:
        d = day_pnl[day_pnl["candidate_id"] == candidate_id]
        w = week_pnl[week_pnl["candidate_id"] == candidate_id]
        m = month_pnl[month_pnl["candidate_id"] == candidate_id]
        total = float(d["net_pnl"].sum()) if not d.empty else 0.0
        best_day = _best_period(d)
        best_week = _best_period(w)
        best_month = _best_period(m)
        worst_day = _worst_period(d)
        worst_week = _worst_period(w)
        worst_month = _worst_period(m)
        row = {
            "candidate_id": candidate_id,
            "total_net_pnl": round(total, 4),
            "days": int(len(d)),
            "weeks": int(len(w)),
            "months": int(len(m)),
            "trades": int(d["trades"].sum()) if not d.empty else 0,
            "best_day": best_day["period"],
            "best_day_pnl": round(best_day["net_pnl"], 4),
            "best_day_concentration": round(_concentration(best_day["net_pnl"], total), 6),
            "worst_day": worst_day["period"],
            "worst_day_pnl": round(worst_day["net_pnl"], 4),
            "best_week": best_week["period"],
            "best_week_pnl": round(best_week["net_pnl"], 4),
            "best_week_concentration": round(_concentration(best_week["net_pnl"], total), 6),
            "worst_week": worst_week["period"],
            "worst_week_pnl": round(worst_week["net_pnl"], 4),
            "best_month": best_month["period"],
            "best_month_pnl": round(best_month["net_pnl"], 4),
            "best_month_concentration": round(_concentration(best_month["net_pnl"], total), 6),
            "worst_month": worst_month["period"],
            "worst_month_pnl": round(worst_month["net_pnl"], 4),
        }
        row["concentration_label"] = _label(row)
        row["concentration_notes"] = _notes(row)
        rows.append(row)
    return pd.DataFrame(rows).sort_values(["concentration_label", "total_net_pnl"], ascending=[True, False]).reset_index(drop=True)


def build_phase5f_fold_pnl(project_root: Path) -> pd.DataFrame:
    folds = pd.read_csv(project_root / "outputs" / "phase5f_walk_forward_fold_results.csv")
    test = folds[folds["segment"] == "test"].copy()
    columns = [
        "candidate_id",
        "fold",
        "segment_start",
        "segment_end",
        "net_pnl",
        "slippage_4_ticks_net_pnl",
        "trades",
        "active_sessions",
        "best_day_concentration",
        "best_trade_concentration",
    ]
    return test[columns].reset_index(drop=True)


def summarize_phase5f_fold_concentration(project_root: Path) -> pd.DataFrame:
    test = build_phase5f_fold_pnl(project_root)
    rows: list[dict[str, Any]] = []
    for candidate_id, group in test.groupby("candidate_id", sort=False):
        total = float(group["net_pnl"].sum())
        best_fold = group.sort_values(["net_pnl", "fold"], ascending=[False, True]).iloc[0]
        worst_fold = group.sort_values(["net_pnl", "fold"], ascending=[True, True]).iloc[0]
        row = {
            "candidate_id": candidate_id,
            "folds": int(group["fold"].nunique()),
            "total_net_pnl": round(total, 4),
            "total_slippage_4_ticks_net_pnl": round(float(group["slippage_4_ticks_net_pnl"].sum()), 4),
            "trades": int(group["trades"].sum()),
            "positive_folds": int((group["net_pnl"] > 0).sum()),
            "best_fold": int(best_fold["fold"]),
            "best_fold_pnl": round(float(best_fold["net_pnl"]), 4),
            "best_fold_concentration": round(_concentration(float(best_fold["net_pnl"]), total), 6),
            "worst_fold": int(worst_fold["fold"]),
            "worst_fold_pnl": round(float(worst_fold["net_pnl"]), 4),
            "max_test_best_day_concentration": round(float(group["best_day_concentration"].max()), 6),
            "max_test_best_trade_concentration": round(float(group["best_trade_concentration"].max()), 6),
        }
        row["concentration_label"] = _fold_label(row)
        row["concentration_notes"] = _fold_notes(row)
        rows.append(row)
    return pd.DataFrame(rows).sort_values(["concentration_label", "total_net_pnl"], ascending=[True, False]).reset_index(drop=True)


def load_phase5f_specs(project_root: Path) -> list[StrategySpec]:
    path = project_root / "outputs" / "phase5f_candidate_specs.json"
    return [StrategySpec.from_dict(item) for item in json.loads(path.read_text(encoding="utf-8"))]


def generate_phase5f_test_trades(project_root: Path, config: WalkForwardConfig | None = None) -> pd.DataFrame:
    config = config or WalkForwardConfig(train_sessions=120, validation_sessions=30, test_sessions=30, step_sessions=360, min_folds=2, max_candidates=1)
    specs = load_phase5f_specs(project_root)
    raw_dir = project_root / "data" / "raw"
    files = discover_data_files(raw_dir)
    if not files:
        raise FileNotFoundError(f"No local raw CSV files found under {raw_dir}")
    full_data = pd.concat([load_ohlcv_csv(path) for path in files], ignore_index=True).sort_values(["symbol", "timestamp"])
    sessions = shared_complete_sessions(full_data, symbols=tuple(dict.fromkeys(spec.instrument for spec in specs)))
    folds = generate_walk_forward_folds(sessions, config)
    rows: list[pd.DataFrame] = []
    for spec in specs:
        for fold in folds:
            fold_sessions = list(fold.all_sessions)
            scoped = full_data[(full_data["symbol"] == spec.instrument) & (full_data["trading_session"].isin(fold_sessions))].copy()
            prepared = _prepare_symbol_data(scoped, fold_sessions)[spec.instrument]
            candidate = spec_to_phase4_candidate(spec)
            signals = generate_phase4a_signals(prepared["timeframes"][spec.timeframe], prepared["full"], candidate)
            trades = simulate_phase4a_candidate(prepared["one_minute"], signals, candidate, get_instrument(spec.instrument), fold_sessions)
            if trades.empty:
                continue
            test_trades = trades[trades["trading_session"].isin(fold.test_sessions)].copy()
            if test_trades.empty:
                continue
            test_trades["fold"] = fold.fold
            test_trades["segment"] = "test"
            rows.append(test_trades)
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


def _best_period(frame: pd.DataFrame) -> dict[str, Any]:
    if frame.empty:
        return {"period": "", "net_pnl": 0.0}
    row = frame.sort_values(["net_pnl", "period"], ascending=[False, True]).iloc[0]
    return {"period": str(row["period"]), "net_pnl": float(row["net_pnl"])}


def _worst_period(frame: pd.DataFrame) -> dict[str, Any]:
    if frame.empty:
        return {"period": "", "net_pnl": 0.0}
    row = frame.sort_values(["net_pnl", "period"], ascending=[True, True]).iloc[0]
    return {"period": str(row["period"]), "net_pnl": float(row["net_pnl"])}


def _concentration(value: float, total: float) -> float:
    return float(value / total) if total > 0 else 1.0


def _label(row: dict[str, Any]) -> str:
    if float(row["total_net_pnl"]) <= 0:
        return "rejected"
    if float(row["best_day_concentration"]) > 0.35 or float(row["best_week_concentration"]) > 0.55 or float(row["best_month_concentration"]) > 0.70:
        return "concentrated"
    return "distributed"


def _notes(row: dict[str, Any]) -> str:
    notes = []
    if float(row["best_day_concentration"]) > 0.35:
        notes.append("day concentration")
    if float(row["best_week_concentration"]) > 0.55:
        notes.append("week concentration")
    if float(row["best_month_concentration"]) > 0.70:
        notes.append("month concentration")
    if float(row["total_net_pnl"]) <= 0:
        notes.append("negative total test PnL")
    return "; ".join(notes) if notes else "PnL is reasonably distributed across tested periods."


def _fold_label(row: dict[str, Any]) -> str:
    if float(row["total_net_pnl"]) <= 0 or float(row["total_slippage_4_ticks_net_pnl"]) <= 0:
        return "rejected"
    if float(row["best_fold_concentration"]) > 0.70 or float(row["max_test_best_day_concentration"]) > 0.35 or float(row["max_test_best_trade_concentration"]) > 0.25:
        return "concentrated"
    return "distributed"


def _fold_notes(row: dict[str, Any]) -> str:
    notes = []
    if float(row["best_fold_concentration"]) > 0.70:
        notes.append("fold concentration")
    if float(row["max_test_best_day_concentration"]) > 0.35:
        notes.append("day concentration inside test fold")
    if float(row["max_test_best_trade_concentration"]) > 0.25:
        notes.append("trade concentration inside test fold")
    if float(row["total_slippage_4_ticks_net_pnl"]) <= 0:
        notes.append("fails aggregate 4-tick slippage stress")
    return "; ".join(notes) if notes else "Fold-level PnL is reasonably distributed."
