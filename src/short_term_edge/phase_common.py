from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

from .instruments import get_instrument


def ensure_directory(path: Path) -> Path:
    """Create an artifact directory and return it."""
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_csv_artifact(frame: pd.DataFrame, path: Path) -> Path:
    """Write a DataFrame artifact with the project's standard CSV options."""
    ensure_directory(path.parent)
    frame.to_csv(path, index=False)
    return path


def deterministic_json(payload: Any) -> str:
    """Serialize phase payloads deterministically for stable artifacts."""
    return json.dumps(payload, indent=2, sort_keys=True, default=str)


def write_json_artifact(payload: Any, path: Path) -> Path:
    """Write deterministic JSON to an artifact path."""
    ensure_directory(path.parent)
    path.write_text(deterministic_json(payload), encoding="utf-8")
    return path


def serialize_specs(specs: Iterable[Any]) -> str:
    """Serialize strategy specs whose objects expose to_dict()."""
    return deterministic_json([spec.to_dict() for spec in specs])


def safe_divide(numerator: float, denominator: float) -> float:
    return round(float(numerator / denominator), 6) if denominator else 0.0


def positive_concentration(best_value: float, total_value: float) -> float:
    """Concentration share using only positive best values; returns 1.0 when total is non-positive."""
    return safe_divide(max(float(best_value), 0.0), float(total_value)) if total_value > 0 else 1.0


def add_cost_waterfall(
    trades: pd.DataFrame,
    *,
    instrument_symbol: str,
    gross_column: str = "gross_pnl",
    net_column: str = "net_pnl",
    inplace: bool = False,
) -> pd.DataFrame:
    """Add fees-only and normal-slippage PnL columns without changing trade logic."""
    out = trades if inplace else trades.copy()
    inst = get_instrument(instrument_symbol)
    out["fees_only_pnl"] = out[gross_column] - inst.base_cost
    out["normal_slippage_pnl"] = out[net_column]
    return out


def fold_summary(folds: pd.DataFrame) -> dict[str, Any]:
    if folds.empty:
        return {
            "walk_forward_test_pnl": 0.0,
            "walk_forward_stress_pnl": 0.0,
            "positive_wf_test_folds_pct": 0.0,
            "worst_wf_test_fold": 0.0,
        }
    return {
        "walk_forward_test_pnl": round(float(folds["net_pnl"].sum()), 2),
        "walk_forward_stress_pnl": round(float(folds["stress_pnl"].sum()), 2),
        "positive_wf_test_folds_pct": safe_divide(int((folds["stress_pnl"] > 0).sum()), len(folds)),
        "worst_wf_test_fold": round(float(folds["stress_pnl"].min()), 2),
    }


def standard_zero_metrics(*, include_gross_waterfall: bool = False) -> dict[str, Any]:
    metrics: dict[str, Any] = {
        "trades": 0,
        "active_days": 0,
        "trades_per_active_day": 0.0,
        "net_pnl": 0.0,
        "stress_pnl": 0.0,
        "validation_pnl": 0.0,
        "holdout_pnl": 0.0,
        "max_drawdown": 0.0,
        "best_day_concentration": 1.0,
        "best_trade_concentration": 1.0,
        "avg_mfe": 0.0,
        "avg_mae": 0.0,
        **fold_summary(pd.DataFrame()),
    }
    if include_gross_waterfall:
        metrics = {"gross_pnl": 0.0, "fees_only_pnl": 0.0, "normal_slippage_pnl": 0.0, **metrics}
    return metrics


def daily_pnl_summary(trades: pd.DataFrame) -> pd.DataFrame:
    if trades.empty:
        return pd.DataFrame()
    return (
        trades.groupby(["candidate_id", "trading_session"])
        .agg(trades=("net_pnl", "size"), net_pnl=("net_pnl", "sum"), stress_pnl=("stress_pnl", "sum"))
        .reset_index()
    )


def concentration_diagnostics(trades: pd.DataFrame) -> pd.DataFrame:
    if trades.empty:
        return pd.DataFrame()
    return (
        trades.groupby(["candidate_id", "trading_session"])
        .agg(pnl=("net_pnl", "sum"), trades=("net_pnl", "size"))
        .reset_index()
        .sort_values("pnl", ascending=False)
    )


def grouped_trade_summary(
    trades: pd.DataFrame,
    column: str,
    *,
    include_gross: bool = False,
) -> pd.DataFrame:
    if trades.empty or column not in trades:
        return pd.DataFrame()
    aggregations: dict[str, tuple[str, str]] = {"trades": ("net_pnl", "size")}
    if include_gross:
        aggregations["gross_pnl"] = ("gross_pnl", "sum")
    aggregations.update(
        {
            "net_pnl": ("net_pnl", "sum"),
            "stress_pnl": ("stress_pnl", "sum"),
            "avg_mfe": ("mfe", "mean"),
            "avg_mae": ("mae", "mean"),
        }
    )
    return (
        trades.groupby(column)
        .agg(**dict(aggregations))
        .reset_index()
        .rename(columns={column: "group"})
        .sort_values("stress_pnl", ascending=False)
    )
