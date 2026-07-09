from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from .backtest import split_sessions
from .ml_backfill_e_phase10b_causality_audit import build_session_percentile_comparison
from .phase10a_overnight_range_breakout_fade import compute_overnight_levels
from .phase10b_overnight_range_targeted_retest import (
    Phase10BConfig,
    Phase10BSpec,
    _add_cost_waterfall,
    _as_10a_spec,
    _build_base_trade_pool,
    _candidate_row,
    _concentration,
    _daily_pnl,
    _fold_rows,
    _mfe_mae_summary,
    _summary,
    _validation_attribution,
    apply_phase10b_pre_entry_filters,
    build_phase10b_specs,
)
from .phase_common import deterministic_json, ensure_directory, write_csv_artifact, write_json_artifact


DEFINITION_VERSION = "phase10b_causal_v2_prior_session_expanding_percentile"


@dataclass(frozen=True)
class Phase10BCausalV2Spec:
    historical_spec: Phase10BSpec
    minimum_prior_sessions: int = 20

    def __getattr__(self, name: str) -> Any:
        return getattr(self.historical_spec, name)

    @property
    def historical_candidate_id(self) -> str:
        return self.historical_spec.candidate_id

    @property
    def candidate_id(self) -> str:
        return f"{self.historical_candidate_id}_causalv2_prior{self.minimum_prior_sessions}"

    def to_dict(self) -> dict[str, Any]:
        return {
            **self.historical_spec.to_dict(),
            "candidate_id": self.candidate_id,
            "historical_candidate_id": self.historical_candidate_id,
            "definition_version": DEFINITION_VERSION,
            "percentile_history_rule": "prior_completed_sessions_only",
            "minimum_prior_sessions": self.minimum_prior_sessions,
            "warmup_behavior": "unknown_and_ineligible_for_replay",
        }


def build_causal_v2_specs(historical_candidate_ids: list[str], minimum_prior_sessions: int = 20) -> list[Phase10BCausalV2Spec]:
    if minimum_prior_sessions < 1:
        raise ValueError("minimum_prior_sessions must be positive")
    by_id = {spec.candidate_id: spec for spec in build_phase10b_specs()}
    missing = sorted(set(historical_candidate_ids) - set(by_id))
    if missing:
        raise ValueError(f"Historical Phase 10B specs not found: {missing}")
    specs = [Phase10BCausalV2Spec(by_id[candidate], minimum_prior_sessions) for candidate in historical_candidate_ids]
    if any(spec.range_filter == "all_ranges" for spec in specs):
        raise ValueError("Causal v2 migration is only for quarantined percentile-filter modules")
    return specs


def causal_percentile_levels(bars: pd.DataFrame, minimum_prior_sessions: int = 20) -> pd.DataFrame:
    levels = compute_overnight_levels(bars)
    comparison = build_session_percentile_comparison(
        levels[["trading_session", "overnight_range_points"]], minimum_prior_sessions
    )
    keep = comparison[
        [
            "trading_session",
            "overnight_range_points",
            "causal_expanding_percentile",
            "prior_session_count",
            "causal_percentile_available",
        ]
    ].copy()
    keep["definition_version"] = DEFINITION_VERSION
    return keep


def attach_causal_percentiles(trades: pd.DataFrame, levels: pd.DataFrame) -> pd.DataFrame:
    if trades.empty:
        return trades.copy()
    required = {"trading_session", "causal_expanding_percentile", "causal_percentile_available"}
    if missing := sorted(required - set(levels.columns)):
        raise ValueError(f"Causal levels missing columns: {missing}")
    out = trades.copy()
    out["trading_session"] = out["trading_session"].astype(str)
    mapping = levels.copy()
    mapping["trading_session"] = mapping["trading_session"].astype(str)
    mapping = mapping.drop_duplicates("trading_session")
    out = out.merge(
        mapping[["trading_session", "causal_expanding_percentile", "prior_session_count", "causal_percentile_available"]],
        on="trading_session",
        how="left",
        validate="many_to_one",
    )
    out["historical_full_sample_percentile_not_used"] = out.get("overnight_range_percentile")
    out["overnight_range_percentile"] = out["causal_expanding_percentile"]
    return out


def run_phase10b_causal_v2_validation(
    bars: pd.DataFrame,
    historical_candidate_ids: list[str],
    config: Phase10BConfig = Phase10BConfig(max_specs=6),
    minimum_prior_sessions: int = 20,
) -> dict[str, Any]:
    specs = build_causal_v2_specs(historical_candidate_ids, minimum_prior_sessions)
    historical_specs = [spec.historical_spec for spec in specs]
    base_trades = _build_base_trade_pool(bars, historical_specs)
    levels = causal_percentile_levels(bars, minimum_prior_sessions)
    base_trades = attach_causal_percentiles(base_trades, levels)
    sessions = sorted(bars["trading_session"].dropna().astype(str).unique().tolist())
    split_map = split_sessions(sessions)
    rows: list[dict[str, Any]] = []
    trade_frames: list[pd.DataFrame] = []
    fold_frames: list[pd.DataFrame] = []
    for spec in specs:
        base_id = _as_10a_spec(spec.historical_spec).candidate_id
        trades = apply_phase10b_pre_entry_filters(
            base_trades[base_trades["base_candidate_id"].eq(base_id)], spec.historical_spec
        )
        if not trades.empty:
            trades = trades.copy()
            for field, value in spec.to_dict().items():
                trades[field] = value
            trades["split"] = trades["trading_session"].astype(str).map(split_map)
            _add_cost_waterfall(trades)
            trade_frames.append(trades)
            fold_frames.append(_fold_rows(trades, spec, sessions, config))
        row = _candidate_row(spec, trades, sessions, split_map, config)
        row["phase10b_causal_v2_label"] = str(row.pop("phase10b_label")).replace("phase10b_", "phase10b_causal_v2_")
        row["phase10b_causal_v2_score"] = row.pop("phase10b_score")
        rows.append(row)
    trade_logs = pd.concat(trade_frames, ignore_index=True) if trade_frames else pd.DataFrame()
    folds = pd.concat(fold_frames, ignore_index=True) if fold_frames else pd.DataFrame()
    candidates = pd.DataFrame(rows).sort_values(
        ["phase10b_causal_v2_score", "stress_pnl"], ascending=[False, False]
    ).reset_index(drop=True)
    candidates.insert(0, "phase10b_causal_v2_rank", range(1, len(candidates) + 1))
    result: dict[str, Any] = {
        "candidate_results": candidates,
        "trade_logs": trade_logs,
        "walk_forward_folds": folds,
        "daily_pnl": _daily_pnl(trade_logs),
        "concentration_diagnostics": _concentration(trade_logs),
        "validation_failure_attribution": _validation_attribution(trade_logs),
        "range_regime_summary": _summary(trade_logs, "range_filter"),
        "exit_reason_summary": _summary(trade_logs, "exit_reason"),
        "mfe_mae_summary": _mfe_mae_summary(trade_logs),
        "causal_level_diagnostics": levels,
        "specs": pd.DataFrame([spec.to_dict() for spec in specs]),
    }
    result["next_action_recommendation"] = make_recommendation(result)
    return result


def make_recommendation(result: dict[str, Any]) -> dict[str, Any]:
    candidates = result["candidate_results"]
    passed = candidates[candidates["phase10b_causal_v2_label"].eq("phase10b_causal_v2_candidate_for_paper_review")]
    positive = candidates[
        (candidates["stress_pnl"] > 0)
        & (candidates["validation_pnl"] > 0)
        & (candidates["holdout_pnl"] > 0)
        & (candidates["walk_forward_stress_pnl"] > 0)
    ]
    base = {
        "definition_version": DEFINITION_VERSION,
        "candidate_count": int(len(candidates)),
        "full_gate_pass_count": int(len(passed)),
        "positive_oos_axis_count": int(len(positive)),
        "registry_mutated": False,
        "scheduler_policy_mutated": False,
        "model_trained": False,
        "official_gates_changed": False,
        "paper_trading_approved": False,
        "live_trading_approved": False,
    }
    if not passed.empty:
        return {
            **base,
            "next_action": "independent_portfolio_review_before_causal_v2_registry_inclusion",
            "rationale": "At least one causal replacement cleared module gates, but registry and scheduler inclusion still require independent portfolio review.",
            "top_candidate": passed.iloc[0].to_dict(),
        }
    if not positive.empty:
        return {
            **base,
            "next_action": "park_causal_v2_as_nontradable_research_signal",
            "rationale": "Causal replacements retained some out-of-sample signal evidence but did not clear unchanged module gates; do not add them to the default scheduler or ML backfill.",
            "top_candidate": positive.iloc[0].to_dict(),
        }
    return {
        **base,
        "next_action": "reject_causal_v2_replacement_and_keep_historical_modules_quarantined",
        "rationale": "The causal replacements did not retain sufficient out-of-sample evidence; keep historical modules quarantined and do not resume their ML backfill.",
    }


def write_phase10b_causal_v2_outputs(
    result: dict[str, Any], project_root: Path, run_id: str = "phase10b-causal-v2-r1"
) -> dict[str, Path]:
    output_dir = project_root / "outputs"
    report_dir = project_root / "reports"
    artifact_dir = project_root / "artifacts" / "phase10b_causal_v2_validation" / run_id
    for directory in (output_dir, report_dir, artifact_dir):
        ensure_directory(directory)
    paths: dict[str, Path] = {}
    for key, value in result.items():
        if isinstance(value, pd.DataFrame):
            path = output_dir / f"phase10b_causal_v2_{key}.csv"
            write_csv_artifact(value, path)
            paths[key] = path
    paths["recommendation"] = write_json_artifact(
        result["next_action_recommendation"], output_dir / "phase10b_causal_v2_next_action_recommendation.json"
    )
    paths["report"] = report_dir / "phase10b_causal_v2_validation_report.md"
    paths["report"].write_text(render_report(result), encoding="utf-8")
    for path in paths.values():
        shutil.copy2(path, artifact_dir / path.name)
    manifest = {
        "run_id": run_id,
        "definition_version": DEFINITION_VERSION,
        "files": sorted(path.name for path in paths.values()),
        **{k: result["next_action_recommendation"][k] for k in (
            "next_action", "registry_mutated", "scheduler_policy_mutated", "model_trained",
            "official_gates_changed", "paper_trading_approved", "live_trading_approved",
        )},
    }
    paths["manifest"] = write_json_artifact(manifest, artifact_dir / "manifest.json")
    return paths


def render_report(result: dict[str, Any]) -> str:
    recommendation = result["next_action_recommendation"]
    candidates = result["candidate_results"]
    lines = [
        "# Phase 10B Causal V2 Replay and Validation",
        "",
        "Research/simulation only. No paper or live trading is approved.",
        "",
        "## Definition",
        "- New candidate identifiers; quarantined historical modules were not modified.",
        "- Overnight-range percentiles use prior completed sessions only.",
        "- The first 20 sessions are unknown and excluded from percentile-filter eligibility.",
        "- Entries and fills preserve the historical next-bar execution assumptions and cost waterfall.",
        "",
        "## Result",
        f"- Candidates: `{len(candidates)}`",
        f"- Full gate passes: `{recommendation['full_gate_pass_count']}`",
        f"- Positive validation/holdout/walk-forward axes: `{recommendation['positive_oos_axis_count']}`",
        f"- Next action: `{recommendation['next_action']}`",
        f"- Rationale: {recommendation['rationale']}",
        "",
        "| Candidate | Label | Net | Stress | Validation | Holdout | WF stress | Concentration |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for _, row in candidates.iterrows():
        lines.append(
            f"| `{row['candidate_id']}` | {row['phase10b_causal_v2_label']} | ${row['net_pnl']:.2f} | "
            f"${row['stress_pnl']:.2f} | ${row['validation_pnl']:.2f} | ${row['holdout_pnl']:.2f} | "
            f"${row['walk_forward_stress_pnl']:.2f} | {row['best_day_concentration']:.3f} |"
        )
    return "\n".join(lines) + "\n"


def recommendation_to_json(recommendation: dict[str, Any]) -> str:
    return deterministic_json(recommendation)
