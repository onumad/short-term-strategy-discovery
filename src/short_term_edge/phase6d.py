from __future__ import annotations

import json
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import pandas as pd

from .phase5n import Phase5NResult, _finite_float, score_prefilter_specs
from .phase6a import _prepare_phase6a_data
from .phase6b import Phase6BConfig, select_ambiguity_reduction_specs
from .strategy_spec import RiskRule, StrategySpec


@dataclass(frozen=True)
class Phase6DConfig:
    symbol: str = "MNQ"
    max_specs: int = 24
    min_specs: int = 12
    batch_size: int = 1
    max_new_specs_per_run: int | None = None
    timeframes: tuple[int, ...] = (2, 3, 5)

    def validate(self) -> "Phase6DConfig":
        if self.symbol != "MNQ":
            raise ValueError("Phase 6D is intentionally MNQ-only")
        if self.min_specs < 1:
            raise ValueError("min_specs must be positive")
        if self.max_specs < self.min_specs:
            raise ValueError("max_specs must be greater than or equal to min_specs")
        if self.batch_size < 1:
            raise ValueError("batch_size must be positive")
        if self.max_new_specs_per_run is not None and self.max_new_specs_per_run < 0:
            raise ValueError("max_new_specs_per_run must be non-negative when provided")
        return self


def select_side_only_specs(project_root: Path, config: Phase6DConfig = Phase6DConfig()) -> list[StrategySpec]:
    """Build deterministic long-only and short-only variants from the strongest Phase 6B bases."""
    config.validate()
    base_specs = {spec.canonical_id(): spec for spec in select_ambiguity_reduction_specs(Phase6BConfig(symbol=config.symbol, max_specs=24, min_specs=16))}
    results_path = project_root / "outputs" / "phase6b_ambiguity_reduction_results.csv"
    if results_path.exists():
        ranked_ids = pd.read_csv(results_path).sort_values("phase6b_rank")["candidate_id"].astype(str).tolist()
    else:
        ranked_ids = list(base_specs)
    selected: list[StrategySpec] = []
    for candidate_id in ranked_ids:
        base = base_specs.get(candidate_id)
        if base is None:
            continue
        for side in ("long", "short"):
            params = dict(base.risk.params)
            params["side_filter"] = side
            notes = f"Phase 6D side-only search: {side}-only version of {base.canonical_id()}."
            selected.append(replace(base, risk=RiskRule(base.risk.name, params), notes=notes).validate())
        if len(selected) >= config.max_specs:
            break
    selected = selected[: config.max_specs]
    if len(selected) < config.min_specs:
        raise ValueError(f"Phase 6D expected at least {config.min_specs} specs, selected {len(selected)}")
    return selected


def run_phase6d_search(project_root: Path, config: Phase6DConfig = Phase6DConfig(), checkpoint_path: Path | None = None) -> Phase5NResult:
    config.validate()
    specs = select_side_only_specs(project_root, config)
    if config.max_new_specs_per_run == 0:
        if checkpoint_path is None or not checkpoint_path.exists():
            return Phase5NResult(search_results=rank_side_only_results(pd.DataFrame()), specs=specs, complete_sessions=[])
        return Phase5NResult(search_results=rank_side_only_results(pd.read_csv(checkpoint_path)), specs=specs, complete_sessions=[])
    specs_for_run = _limit_specs_for_run(specs, checkpoint_path, config.max_new_specs_per_run)
    prepared, complete_sessions = _prepare_phase6a_data(project_root, config)
    scored = score_prefilter_specs(
        specs_for_run,
        prepared,
        complete_sessions,
        checkpoint_path=checkpoint_path,
        batch_size=config.batch_size,
    )
    return Phase5NResult(search_results=rank_side_only_results(scored), specs=specs, complete_sessions=complete_sessions)


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


def rank_side_only_results(candidate_summary: pd.DataFrame) -> pd.DataFrame:
    if candidate_summary.empty:
        return candidate_summary.copy()
    reusable = candidate_summary.drop(
        columns=[
            column
            for column in ("phase5n_rank", "phase5n_score", "phase5n_label", "phase5n_notes", "phase6d_rank", "phase6d_score", "phase6d_label", "phase6d_notes")
            if column in candidate_summary.columns
        ]
    )
    rows: list[dict[str, Any]] = []
    for _, row in reusable.iterrows():
        out = row.to_dict()
        params = _parse_params(str(out.get("params", "")))
        raw_side = str(out.get("side_filter", ""))
        out["side_filter"] = raw_side if raw_side in {"long", "short"} else str(params.get("side_filter", _side_from_spec_json(out.get("spec_json"))))
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
        score += min(max(net / 3_000.0, -2.0), 2.0) * 8.0
        score += min(max(slippage / 3_000.0, -2.0), 2.0) * 34.0
        score += min(max(validation / 1_250.0, -2.0), 2.0) * 10.0
        score += min(max(holdout / 1_250.0, -2.0), 2.0) * 14.0
        score += min(active, 0.45) * 14.0
        score += min(trades / 80.0, 1.0) * 8.0
        score -= min(abs(drawdown) / 1_500.0, 2.5) * 18.0
        score -= max(day - 0.25, 0.0) * 240.0
        score -= max(trade - 0.16, 0.0) * 240.0
        score -= min(ambiguity, 10) * 3.0
        if out["side_filter"] not in {"long", "short"}:
            score -= 30.0
        if slippage <= 0:
            score -= 55.0
        if active < 0.10:
            score -= 20.0
        if trades < 30:
            score -= 22.0
        if validation < 0 or holdout < 0:
            score -= 14.0
        out["phase6d_score"] = round(float(score), 4)
        out["phase6d_label"] = _phase6d_label(out)
        out["phase6d_notes"] = _phase6d_notes(out)
        rows.append(out)
    ranked = pd.DataFrame(rows).sort_values(["phase6d_score", "slippage_4_ticks_net_pnl", "net_pnl"], ascending=[False, False, False]).reset_index(drop=True)
    ranked.insert(0, "phase6d_rank", range(1, len(ranked) + 1))
    return ranked


def write_phase6d_specs(specs: list[StrategySpec], path: Path) -> None:
    path.write_text(json.dumps([json.loads(spec.to_json()) for spec in specs], indent=2, sort_keys=True), encoding="utf-8")


def _parse_params(value: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for part in value.split(";"):
        if "=" in part:
            key, raw = part.split("=", 1)
            out[key.strip()] = raw.strip()
    return out


def _side_from_spec_json(value: Any) -> str:
    try:
        payload = json.loads(str(value))
    except (TypeError, ValueError, json.JSONDecodeError):
        return "both"
    return str(payload.get("risk", {}).get("params", {}).get("side_filter", "both"))


def _phase6d_label(row: dict[str, Any]) -> str:
    if str(row.get("side_filter", "both")) not in {"long", "short"}:
        return "rejected"
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
        return "side_only_watchlist"
    return "side_only_prefilter_survivor"


def _phase6d_notes(row: dict[str, Any]) -> str:
    notes: list[str] = []
    if str(row.get("side_filter", "both")) not in {"long", "short"}:
        notes.append("not a long-only or short-only candidate")
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
        notes.append("drawdown exceeds Phase 6D cap")
    if int(_finite_float(row.get("same_bar_stop_target_ambiguity_count", 0), 0.0)) > 0:
        notes.append("same-bar stop/target ambiguity remains")
    if _finite_float(row.get("validation_pnl", 0.0), 0.0) < 0:
        notes.append("negative validation split")
    if _finite_float(row.get("holdout_pnl", 0.0), 0.0) < 0:
        notes.append("negative holdout split")
    return "; ".join(notes) if notes else "Side-only candidate survives Phase 6D gates; requires deep validation."
