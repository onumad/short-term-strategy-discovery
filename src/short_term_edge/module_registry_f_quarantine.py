from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from .phase_common import deterministic_json, ensure_directory, write_csv_artifact, write_json_artifact
from .playbook_scheduler_policy import build_playbook_scheduler_policy, load_playbook_scheduler_policy_inputs


QUARANTINE_STATUS = "quarantined_noncausal_definition"
NOT_FLAGGED_STATUS = "not_flagged_by_phase10b_causality_audit"
QUARANTINE_REASON = (
    "Historical Phase 10B range filter used a full-sample percentile, allowing future sessions to change "
    "historical eligibility."
)
REGISTRY_FIELDS = (
    "causality_review_status",
    "scheduler_eligible",
    "ml_backfill_eligible",
    "quarantine_reason",
    "replacement_module_id",
)


@dataclass(frozen=True)
class ModuleRegistryFConfig:
    project_root: Path
    output_dir: Path
    report_dir: Path
    artifact_dir: Path
    run_id: str = "module-registry-f-r1"


def build_module_registry_f_quarantine(project_root: Path, run_id: str = "module-registry-f-r1") -> dict[str, Any]:
    return run_module_registry_f_quarantine(
        ModuleRegistryFConfig(
            project_root=project_root,
            output_dir=project_root / "outputs",
            report_dir=project_root / "reports",
            artifact_dir=project_root / "artifacts" / "module_registry_f_quarantine" / run_id,
            run_id=run_id,
        )
    )


def run_module_registry_f_quarantine(config: ModuleRegistryFConfig) -> dict[str, Any]:
    for directory in (config.output_dir, config.report_dir, config.artifact_dir):
        ensure_directory(directory)
    registry_path = config.output_dir / "playbook_module_registry.csv"
    audit_path = config.output_dir / "ml_backfill_e_phase10b_module_audit.csv"
    schema_path = config.output_dir / "playbook_module_registry_schema.json"
    registry = pd.read_csv(registry_path)
    audit = pd.read_csv(audit_path)
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    updated_registry, quarantine = apply_quarantine(registry, audit)
    updated_schema = update_registry_schema(schema)

    scheduler_inputs = load_playbook_scheduler_policy_inputs(config.project_root)
    scheduler_inputs["playbook_module_registry"] = updated_registry
    scheduler_policy = build_playbook_scheduler_policy(scheduler_inputs)
    validate_quarantine(updated_registry, scheduler_policy, quarantine)
    recommendation = build_recommendation(quarantine, scheduler_policy)
    paths = write_outputs(config, updated_registry, updated_schema, scheduler_policy, quarantine, recommendation)
    return {
        "registry": updated_registry,
        "schema": updated_schema,
        "scheduler_policy": scheduler_policy,
        "quarantine": quarantine,
        "next_action_recommendation": recommendation,
        "paths": paths,
    }


def apply_quarantine(registry: pd.DataFrame, audit: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    required_registry = {"module_id", "phase", "candidate_id"}
    required_audit = {"signal_key", "candidate_id", "noncausal_definition_detected", "audit_reason"}
    if missing := sorted(required_registry - set(registry.columns)):
        raise ValueError(f"Module registry missing columns: {missing}")
    if missing := sorted(required_audit - set(audit.columns)):
        raise ValueError(f"Causality audit missing columns: {missing}")
    unsafe = audit[audit["noncausal_definition_detected"].map(_as_bool)].copy()
    unsafe_keys = set(unsafe["signal_key"].astype(str))
    registry_keys = registry["phase"].astype(str) + "::" + registry["candidate_id"].astype(str)
    missing_keys = sorted(unsafe_keys - set(registry_keys))
    if missing_keys:
        raise ValueError(f"Audited modules missing from registry: {missing_keys}")
    if len(unsafe_keys) != len(unsafe):
        raise ValueError("Causality audit contains duplicate unsafe signal keys")

    updated = registry.copy()
    flagged = registry_keys.isin(unsafe_keys)
    updated["causality_review_status"] = NOT_FLAGGED_STATUS
    updated["scheduler_eligible"] = True
    updated["ml_backfill_eligible"] = True
    updated["quarantine_reason"] = ""
    updated["replacement_module_id"] = ""
    updated.loc[flagged, "causality_review_status"] = QUARANTINE_STATUS
    updated.loc[flagged, "scheduler_eligible"] = False
    updated.loc[flagged, "ml_backfill_eligible"] = False
    updated.loc[flagged, "quarantine_reason"] = QUARANTINE_REASON
    updated = updated.sort_values(["phase", "candidate_id"]).reset_index(drop=True)
    quarantine = updated[updated["causality_review_status"].eq(QUARANTINE_STATUS)].copy()
    return updated, quarantine


def update_registry_schema(schema: dict[str, Any]) -> dict[str, Any]:
    updated = json.loads(json.dumps(schema))
    columns = list(updated.get("columns", []))
    required = list(updated.get("required_columns", []))
    for field in REGISTRY_FIELDS:
        if field not in columns:
            columns.append(field)
        if field not in required:
            required.append(field)
    updated["columns"] = columns
    updated["required_columns"] = required
    updated["causality_quarantine"] = {
        "quarantine_status": QUARANTINE_STATUS,
        "historical_ids_preserved": True,
        "scheduler_eligible_default_for_quarantine": False,
        "ml_backfill_eligible_default_for_quarantine": False,
        "silent_definition_replacement_allowed": False,
    }
    return updated


def validate_quarantine(registry: pd.DataFrame, policy: dict[str, Any], quarantine: pd.DataFrame) -> None:
    if quarantine.empty:
        raise ValueError("No modules were quarantined")
    if not (~quarantine["scheduler_eligible"].map(_as_bool)).all():
        raise ValueError("A quarantined module remains scheduler eligible")
    if not (~quarantine["ml_backfill_eligible"].map(_as_bool)).all():
        raise ValueError("A quarantined module remains ML-backfill eligible")
    default_ids = set(policy["recommended_default_scheduler_universe"]["module_ids"])
    overlap = sorted(default_ids.intersection(quarantine["module_id"].astype(str)))
    if overlap:
        raise ValueError(f"Quarantined modules remain in default scheduler: {overlap}")
    if registry["module_id"].duplicated().any():
        raise ValueError("Registry module IDs are no longer unique")


def build_recommendation(quarantine: pd.DataFrame, policy: dict[str, Any]) -> dict[str, Any]:
    return {
        "next_action": "phase10b_causal_v2_replay_and_validation",
        "rationale": "The six historical noncausal modules are preserved but excluded from scheduler and ML backfill; any replacement must use a new versioned causal definition.",
        "quarantined_module_count": int(len(quarantine)),
        "default_scheduler_module_count": int(policy["recommended_default_scheduler_universe"]["module_count"]),
        "historical_module_ids_preserved": True,
        "registry_mutated": True,
        "scheduler_policy_mutated": True,
        "strategy_replayed": False,
        "model_trained": False,
        "official_gates_changed": False,
        "paper_trading_approved": False,
        "live_trading_approved": False,
    }


def write_outputs(
    config: ModuleRegistryFConfig,
    registry: pd.DataFrame,
    schema: dict[str, Any],
    scheduler_policy: dict[str, Any],
    quarantine: pd.DataFrame,
    recommendation: dict[str, Any],
) -> dict[str, Path]:
    paths = {
        "registry_csv": config.output_dir / "playbook_module_registry.csv",
        "registry_json": config.output_dir / "playbook_module_registry.json",
        "registry_schema": config.output_dir / "playbook_module_registry_schema.json",
        "scheduler_policy": config.output_dir / "playbook_scheduler_policy.json",
        "quarantine": config.output_dir / "module_registry_f_quarantined_modules.csv",
        "recommendation": config.output_dir / "module_registry_f_next_action_recommendation.json",
        "report": config.report_dir / "module_registry_f_quarantine_report.md",
    }
    write_csv_artifact(registry, paths["registry_csv"])
    paths["registry_json"].write_text(deterministic_json(registry.to_dict(orient="records")), encoding="utf-8")
    write_json_artifact(schema, paths["registry_schema"])
    write_json_artifact(scheduler_policy, paths["scheduler_policy"])
    write_csv_artifact(quarantine, paths["quarantine"])
    write_json_artifact(recommendation, paths["recommendation"])
    paths["report"].write_text(render_report(recommendation), encoding="utf-8")
    for path in paths.values():
        shutil.copy2(path, config.artifact_dir / path.name)
    manifest = {"run_id": config.run_id, "files": sorted(path.name for path in paths.values()), **recommendation}
    paths["manifest"] = write_json_artifact(manifest, config.artifact_dir / "manifest.json")
    return paths


def render_report(recommendation: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# Module Registry F — Phase 10B Causality Quarantine",
            "",
            "Research/simulation only. No paper or live trading is approved.",
            "",
            "## Result",
            f"- Historical modules quarantined: `{recommendation['quarantined_module_count']}`",
            f"- Default scheduler modules after quarantine: `{recommendation['default_scheduler_module_count']}`",
            "- Historical module identifiers were preserved; no definition was silently rewritten.",
            "- Quarantined rows are ineligible for default scheduling and ML label backfill.",
            "",
            "## Next action",
            f"- `{recommendation['next_action']}`",
            f"- {recommendation['rationale']}",
            "",
            "## Guardrails",
            "- `official_gates_changed: false`",
            "- `paper_trading_approved: false`",
            "- `live_trading_approved: false`",
            "- `model_trained: false`",
        ]
    ) + "\n"


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"true", "1", "yes"}
