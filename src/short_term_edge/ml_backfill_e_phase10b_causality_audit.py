from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .data_loader import load_ohlcv_csv
from .ml_dataset_a_day_regime import RESEARCH_ONLY_GUARDRAIL
from .phase10a_overnight_range_breakout_fade import compute_overnight_levels
from .phase10b_overnight_range_targeted_retest import Phase10BSpec, build_phase10b_specs
from .phase_common import ensure_directory, write_csv_artifact, write_json_artifact


NONCAUSAL_REASON = (
    "Registered Phase 10B range filter uses a full-sample percentile rank, so future sessions can change "
    "historical eligibility."
)


@dataclass(frozen=True)
class MlBackfillEConfig:
    project_root: Path
    scheduler_policy_path: Path
    module_registry_path: Path
    target_d_module_outcome_path: Path
    raw_data_path: Path
    output_dir: Path
    report_dir: Path
    artifact_dir: Path
    run_id: str = "ml-backfill-e-r1"
    minimum_prior_sessions: int = 20


def build_ml_backfill_e_phase10b_causality_audit(
    project_root: Path,
    run_id: str = "ml-backfill-e-r1",
    minimum_prior_sessions: int = 20,
) -> dict[str, Any]:
    outputs = project_root / "outputs"
    config = MlBackfillEConfig(
        project_root=project_root,
        scheduler_policy_path=outputs / "playbook_scheduler_policy.json",
        module_registry_path=outputs / "playbook_module_registry.csv",
        target_d_module_outcome_path=outputs / "ml_target_d_module_daily_outcome.csv",
        raw_data_path=project_root / "data" / "raw" / "mnq_1m_databento_20230101_20260703.csv",
        output_dir=outputs,
        report_dir=project_root / "reports",
        artifact_dir=project_root / "artifacts" / "ml_backfill_e_phase10b_causality_audit" / run_id,
        run_id=run_id,
        minimum_prior_sessions=minimum_prior_sessions,
    )
    return run_ml_backfill_e_phase10b_causality_audit(config)


def run_ml_backfill_e_phase10b_causality_audit(config: MlBackfillEConfig) -> dict[str, Any]:
    for directory in (config.output_dir, config.report_dir, config.artifact_dir):
        ensure_directory(directory)
    policy = json.loads(config.scheduler_policy_path.read_text(encoding="utf-8"))
    registry = pd.read_csv(config.module_registry_path)
    target_d = pd.read_csv(config.target_d_module_outcome_path)
    unsafe_specs = detect_unsafe_phase10b_specs(policy, registry, build_phase10b_specs())
    module_audit = build_module_audit(unsafe_specs, target_d)

    bars = load_ohlcv_csv(config.raw_data_path)
    levels = compute_overnight_levels(bars)[["trading_session", "overnight_range_points", "overnight_range_percentile"]]
    comparison = build_session_percentile_comparison(levels, config.minimum_prior_sessions)
    drift = build_eligibility_drift_summary(unsafe_specs, comparison)
    proposed_actions = build_proposed_actions(module_audit, drift)
    recommendation = build_recommendation(module_audit, drift)
    paths = write_outputs(config, module_audit, comparison, drift, proposed_actions, recommendation)
    return {
        "module_audit": module_audit,
        "session_percentile_comparison": comparison,
        "eligibility_drift_summary": drift,
        "proposed_actions": proposed_actions,
        "next_action_recommendation": recommendation,
        "paths": paths,
    }


def detect_unsafe_phase10b_specs(
    policy: dict[str, Any], registry: pd.DataFrame, specs: list[Phase10BSpec]
) -> list[Phase10BSpec]:
    configured = [str(v) for v in policy["recommended_default_scheduler_universe"]["signal_keys"]]
    registry_keys = set(registry["phase"].astype(str) + "::" + registry["candidate_id"].astype(str))
    missing = sorted(set(configured) - registry_keys)
    if missing:
        raise ValueError(f"Default scheduler modules missing from registry: {missing}")
    by_id = {spec.candidate_id: spec for spec in specs}
    phase10b_ids = [key.split("::", 1)[1] for key in configured if key.startswith("phase10b::")]
    unknown = sorted(set(phase10b_ids) - set(by_id))
    if unknown:
        raise ValueError(f"Default Phase 10B specs not found: {unknown}")
    return [by_id[candidate] for candidate in phase10b_ids if by_id[candidate].range_filter != "all_ranges"]


def build_module_audit(specs: list[Phase10BSpec], target_d: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    phase10b = target_d[target_d["phase"].astype(str).eq("phase10b")].copy()
    for spec in specs:
        source = phase10b[phase10b["candidate_id"].astype(str).eq(spec.candidate_id)]
        statuses = sorted(source["outcome_status"].dropna().astype(str).unique().tolist()) if not source.empty else []
        reliable = bool(source.get("reliable_outcome_coverage", pd.Series(dtype=bool)).fillna(False).astype(bool).any())
        missing_rows = int(source["outcome_status"].eq("missing_source_day").sum()) if not source.empty else 0
        rows.append(
            {
                "signal_key": f"phase10b::{spec.candidate_id}",
                "candidate_id": spec.candidate_id,
                "range_filter": spec.range_filter,
                "noncausal_definition_detected": True,
                "target_d_backfill_status": "unavailable_for_backfill" if not reliable else "unexpected_reliable_coverage",
                "target_d_outcome_statuses": ";".join(statuses),
                "target_d_missing_source_rows": missing_rows,
                "missing_coverage_treated_as_zero": False,
                "audit_reason": NONCAUSAL_REASON,
                "official_gates_changed": False,
                "paper_trading_approved": False,
            }
        )
    return pd.DataFrame(rows).sort_values("candidate_id").reset_index(drop=True)


def build_session_percentile_comparison(levels: pd.DataFrame, minimum_prior_sessions: int = 20) -> pd.DataFrame:
    if minimum_prior_sessions < 1:
        raise ValueError("minimum_prior_sessions must be positive")
    required = {"trading_session", "overnight_range_points"}
    missing = sorted(required - set(levels.columns))
    if missing:
        raise ValueError(f"Overnight levels missing columns: {missing}")
    out = levels[["trading_session", "overnight_range_points"]].copy()
    out["trading_session"] = out["trading_session"].astype(str)
    out["overnight_range_points"] = pd.to_numeric(out["overnight_range_points"], errors="raise")
    out = out.drop_duplicates("trading_session").sort_values("trading_session").reset_index(drop=True)
    out["full_sample_percentile"] = out["overnight_range_points"].rank(pct=True)
    causal: list[float] = []
    prior_counts: list[int] = []
    values = out["overnight_range_points"].to_numpy(dtype=float)
    for index, current in enumerate(values):
        prior = values[:index]
        prior_counts.append(len(prior))
        causal.append(float(np.mean(prior <= current)) if len(prior) >= minimum_prior_sessions else np.nan)
    out["causal_expanding_percentile"] = causal
    out["prior_session_count"] = prior_counts
    out["causal_percentile_available"] = out["causal_expanding_percentile"].notna()
    out["absolute_percentile_drift"] = (out["full_sample_percentile"] - out["causal_expanding_percentile"]).abs()
    out["minimum_prior_sessions"] = int(minimum_prior_sessions)
    return out


def eligibility_for_filter(percentile: pd.Series, range_filter: str) -> pd.Series:
    values = pd.to_numeric(percentile, errors="coerce")
    result = pd.Series(pd.NA, index=values.index, dtype="boolean")
    known = values.notna()
    if range_filter == "exclude_narrowest_20":
        result.loc[known] = values.loc[known] > 0.20
    elif range_filter == "exclude_widest_20":
        result.loc[known] = values.loc[known] < 0.80
    elif range_filter == "middle_60_only":
        result.loc[known] = (values.loc[known] > 0.20) & (values.loc[known] < 0.80)
    elif range_filter == "all_ranges":
        result.loc[known] = True
    else:
        raise ValueError(f"Unknown range filter: {range_filter}")
    return result


def build_eligibility_drift_summary(specs: list[Phase10BSpec], comparison: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    available = comparison["causal_percentile_available"].astype(bool)
    for spec in specs:
        full = eligibility_for_filter(comparison["full_sample_percentile"], spec.range_filter)
        causal = eligibility_for_filter(comparison["causal_expanding_percentile"], spec.range_filter)
        changed = available & full.ne(causal).fillna(False)
        comparable = int(available.sum())
        rows.append(
            {
                "signal_key": f"phase10b::{spec.candidate_id}",
                "candidate_id": spec.candidate_id,
                "range_filter": spec.range_filter,
                "total_sessions": len(comparison),
                "causal_comparable_sessions": comparable,
                "causal_unavailable_sessions": int((~available).sum()),
                "full_sample_eligible_sessions": int(full.fillna(False).sum()),
                "causal_eligible_sessions": int(causal.fillna(False).sum()),
                "eligibility_drift_sessions": int(changed.sum()),
                "eligibility_drift_rate": round(float(changed.sum() / comparable), 6) if comparable else np.nan,
                "noncausal_definition_detected": True,
                "missing_coverage_treated_as_zero": False,
            }
        )
    return pd.DataFrame(rows).sort_values("candidate_id").reset_index(drop=True)


def build_proposed_actions(module_audit: pd.DataFrame, drift: pd.DataFrame) -> pd.DataFrame:
    merged = module_audit.merge(
        drift[["signal_key", "eligibility_drift_sessions", "eligibility_drift_rate"]], on="signal_key", how="left"
    )
    merged["proposed_action"] = "quarantine_then_migrate_to_causal_expanding_percentile_definition"
    merged["registry_mutation_applied"] = False
    merged["strategy_replayed"] = False
    merged["model_trained"] = False
    return merged


def build_recommendation(module_audit: pd.DataFrame, drift: pd.DataFrame) -> dict[str, Any]:
    has_noncausal = bool(module_audit["noncausal_definition_detected"].any())
    drifted = int((drift["eligibility_drift_sessions"] > 0).sum())
    return {
        "next_action": "module_registry_f_quarantine_noncausal_phase10b_modules" if has_noncausal else "ml_target_d_backfill_resume",
        "rationale": (
            "Default Phase 10B range-filter modules use a noncausal full-sample percentile definition; quarantine "
            "them and review migration to a prior-session expanding percentile before label backfill."
            if has_noncausal
            else "No noncausal Phase 10B percentile definition was detected."
        ),
        "unsafe_module_count": int(len(module_audit)),
        "modules_with_observed_eligibility_drift": drifted,
        "registry_mutated": False,
        "scheduler_policy_mutated": False,
        "strategy_replayed": False,
        "model_trained": False,
        "research_only": True,
        "official_gates_changed": False,
        "paper_trading_approved": False,
        "live_trading_approved": False,
    }


def write_outputs(
    config: MlBackfillEConfig,
    module_audit: pd.DataFrame,
    comparison: pd.DataFrame,
    drift: pd.DataFrame,
    actions: pd.DataFrame,
    recommendation: dict[str, Any],
) -> dict[str, Path]:
    paths = {
        "module_audit": config.output_dir / "ml_backfill_e_phase10b_module_audit.csv",
        "session_comparison": config.output_dir / "ml_backfill_e_phase10b_session_percentile_comparison.csv",
        "drift_summary": config.output_dir / "ml_backfill_e_phase10b_eligibility_drift_summary.csv",
        "proposed_action": config.output_dir / "ml_backfill_e_phase10b_proposed_action.csv",
        "recommendation": config.output_dir / "ml_backfill_e_phase10b_next_action_recommendation.json",
        "report": config.report_dir / "ml_backfill_e_phase10b_causality_audit_report.md",
    }
    write_csv_artifact(module_audit, paths["module_audit"])
    write_csv_artifact(comparison, paths["session_comparison"])
    write_csv_artifact(drift, paths["drift_summary"])
    write_csv_artifact(actions, paths["proposed_action"])
    write_json_artifact(recommendation, paths["recommendation"])
    paths["report"].write_text(render_report(module_audit, comparison, drift, recommendation), encoding="utf-8")

    for path in paths.values():
        shutil.copy2(path, config.artifact_dir / path.name)
    manifest = {
        "run_id": config.run_id,
        "audit": "ML Backfill E — Phase 10B Percentile Causality Audit",
        "minimum_prior_sessions": config.minimum_prior_sessions,
        "files": sorted(path.name for path in paths.values()),
        **{key: recommendation[key] for key in (
            "registry_mutated", "scheduler_policy_mutated", "strategy_replayed", "model_trained",
            "official_gates_changed", "paper_trading_approved", "live_trading_approved",
        )},
    }
    paths["manifest"] = write_json_artifact(manifest, config.artifact_dir / "manifest.json")
    return paths


def render_report(
    module_audit: pd.DataFrame,
    comparison: pd.DataFrame,
    drift: pd.DataFrame,
    recommendation: dict[str, Any],
) -> str:
    comparable = int(comparison["causal_percentile_available"].sum())
    lines = [
        "# ML Backfill E — Phase 10B Percentile Causality Audit",
        "",
        RESEARCH_ONLY_GUARDRAIL,
        "No strategy replay, model training, registry mutation, scheduler-policy mutation, gate change, or paper/live trading approval occurred.",
        "",
        "## Summary",
        f"- Unsafe default Phase 10B modules: `{len(module_audit)}`",
        f"- Sessions with causal percentile available: `{comparable}`",
        f"- Modules with observed eligibility drift: `{int((drift['eligibility_drift_sessions'] > 0).sum())}`",
        f"- Next action: `{recommendation['next_action']}`",
        "",
        "## Finding",
        "The registered filters rank overnight range against the complete sample. That lets future sessions change a historical session's percentile and eligibility. The causal comparison ranks each session only against prior complete sessions; early sessions without enough history remain unknown, never zero or ineligible.",
        "",
        "## Proposed action",
        "Quarantine the six noncausal default modules from scheduler/backfill use, then review explicit migration to a versioned prior-session expanding-percentile definition. Do not silently rewrite the registered historical modules.",
        "",
        "## Guardrails",
        "- `official_gates_changed: false`",
        "- `paper_trading_approved: false`",
        "- `live_trading_approved: false`",
        "- Registry and scheduler policy were not mutated.",
    ]
    return "\n".join(lines) + "\n"
