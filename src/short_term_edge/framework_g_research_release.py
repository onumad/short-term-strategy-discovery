from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

from .phase_common import ensure_directory, write_json_artifact


AUTHORIZATION_STAGE = "research"
PREDICTION_SCHEMA_VERSION = "ml_prediction_envelope/v1"
MODEL_RELEASE_SCHEMA_VERSION = "ml_model_release/v1"
EVALUATION_POLICY_VERSION = "ml_evaluation_policy/v1"
CALIBRATION_FIT_POLICY_VERSION = "ml_calibration_fit_policy/v1"

PREDICTION_FIELDS = (
    "schema_version",
    "event_id",
    "correlation_id",
    "created_at",
    "effective_at",
    "expires_at",
    "environment",
    "release_id",
    "source_versions",
    "authorization_stage",
    "model_version",
    "calibration_version",
    "feature_contract_version",
    "label_contract_version",
    "feature_available_at",
    "score",
    "uncertainty",
    "prediction_status",
    "abstention_reason",
    "approved_as_signal_input",
)

PROHIBITED_PREDICTION_FIELDS = {
    "side",
    "quantity",
    "size",
    "order_type",
    "broker_instruction",
    "risk_limit",
    "risk_override",
    "paper_trading_approved",
    "live_trading_approved",
}


def authorization_policy() -> dict[str, Any]:
    return {
        "schema_version": "research_authorization_policy/v1",
        "authorization_stage": AUTHORIZATION_STAGE,
        "allowed_stages": ["research", "paper", "shadow", "controlled_live"],
        "stage_change_requires_explicit_project_policy_change": True,
        "approved_as_signal_input_default": False,
        "paper_trading_approved": False,
        "shadow_execution_approved": False,
        "live_trading_approved": False,
        "model_may_authorize_orders": False,
        "llm_may_authorize_orders": False,
        "independent_risk_required_for_any_later_stage_action": True,
    }


def prediction_schema() -> dict[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": PREDICTION_SCHEMA_VERSION,
        "type": "object",
        "additionalProperties": False,
        "required": list(PREDICTION_FIELDS),
        "properties": {
            "schema_version": {"const": PREDICTION_SCHEMA_VERSION},
            "event_id": {"type": "string", "minLength": 1},
            "correlation_id": {"type": "string", "minLength": 1},
            "created_at": {"type": "string", "format": "date-time"},
            "effective_at": {"type": "string", "format": "date-time"},
            "expires_at": {"type": "string", "format": "date-time"},
            "environment": {"const": "research"},
            "release_id": {"type": "string", "minLength": 1},
            "source_versions": {"type": "object"},
            "authorization_stage": {"const": AUTHORIZATION_STAGE},
            "model_version": {"type": "string", "minLength": 1},
            "calibration_version": {"type": ["string", "null"]},
            "feature_contract_version": {"type": "string", "minLength": 1},
            "label_contract_version": {"type": "string", "minLength": 1},
            "feature_available_at": {"type": "string", "format": "date-time"},
            "score": {"type": ["number", "null"], "minimum": 0.0, "maximum": 1.0},
            "uncertainty": {"type": ["number", "null"], "minimum": 0.0, "maximum": 1.0},
            "prediction_status": {"enum": ["predicted", "abstained"]},
            "abstention_reason": {"type": ["string", "null"]},
            "approved_as_signal_input": {"const": False},
        },
    }


def model_release_schema() -> dict[str, Any]:
    return {
        "schema_version": MODEL_RELEASE_SCHEMA_VERSION,
        "authorization_stage": AUTHORIZATION_STAGE,
        "required_fields": [
            "release_id",
            "model_version",
            "artifact_sha256",
            "source_revision",
            "dependency_versions",
            "training_data_hashes",
            "feature_contract_version",
            "label_contract_version",
            "calibration_version",
            "training_config",
            "evaluation_report",
            "approval_state",
        ],
        "approval_state_defaults": {
            "eligible_for_signal_input_review": False,
            "approved_as_signal_input": False,
            "paper_trading_approved": False,
            "live_trading_approved": False,
        },
        "immutable_after_publication": True,
        "silent_replacement_allowed": False,
    }


def ml_evaluation_policy() -> dict[str, Any]:
    return {
        "schema_version": EVALUATION_POLICY_VERSION,
        "authorization_stage": AUTHORIZATION_STAGE,
        "thresholds_are_framework_defaults_not_official_trading_gates": True,
        "required_prerequisites": {
            "causal_features": True,
            "coverage_aligned_targets": True,
            "chronological_splits": True,
            "leakage_checks_pass": True,
            "training_only_preprocessing": True,
        },
        "discrimination": {
            "must_beat_declared_baseline_on_primary_holdout": True,
            "minimum_rolling_holdouts_beating_baseline": 2,
            "rolling_holdout_count": 3,
        },
        "calibration": {
            "brier_score_must_beat_prevalence_baseline": True,
            "maximum_expected_calibration_error": 0.10,
            "maximum_worst_fold_expected_calibration_error": 0.15,
            "calibration_slope_range": [0.75, 1.25],
            "maximum_absolute_calibration_intercept": 0.10,
            "calibration_mapping_fit_on_training_or_validation_only": True,
        },
        "drift_and_coverage": {
            "maximum_feature_or_score_psi": 0.20,
            "minimum_prediction_coverage": 0.95,
            "invalid_or_stale_input_abstention_rate": 1.0,
            "ood_evaluation_required": True,
            "missing_feature_behavior": "abstain",
        },
        "counterfactual_policy_impact": {
            "required_before_signal_input_review": True,
            "costs_and_slippage_required": True,
            "must_not_worsen_drawdown": True,
            "must_not_worsen_concentration": True,
            "must_not_worsen_weak_fold_behavior": True,
            "deterministic_risk_constraints_required": True,
        },
        "approval_behavior": {
            "passing_metrics_only_sets_eligible_for_signal_input_review": True,
            "automatic_signal_input_approval": False,
            "approved_as_signal_input_default": False,
            "paper_trading_approved": False,
            "live_trading_approved": False,
        },
    }


def calibration_fit_policy() -> dict[str, Any]:
    return {
        "schema_version": CALIBRATION_FIT_POLICY_VERSION,
        "authorization_stage": AUTHORIZATION_STAGE,
        "allowed_fit_partitions": ["train", "validation", "cross_fitted_oof"],
        "prohibited_fit_partitions": ["holdout", "future_unseen_confirmation"],
        "allowed_threshold_selection_partitions": ["validation", "cross_fitted_oof"],
        "prohibited_threshold_selection_partitions": ["holdout", "future_unseen_confirmation"],
        "baseline_b_existing_holdouts_status": "consumed_exploratory_selection_evidence",
        "baseline_b_existing_holdouts_confirmatory": False,
        "future_unseen_confirmation_required": True,
        "calibration_may_set_signal_input_approval": False,
        "approved_as_signal_input_default": False,
        "paper_trading_approved": False,
        "live_trading_approved": False,
    }


def validate_calibration_plan(plan: Mapping[str, Any]) -> dict[str, Any]:
    required = {
        "model_release_id",
        "calibration_method",
        "fit_partitions",
        "threshold_selection_partitions",
        "existing_holdout_status",
        "future_confirmation_status",
    }
    if missing := sorted(required - set(plan)):
        raise ValueError(f"calibration plan missing fields: {missing}")
    policy = calibration_fit_policy()
    fit = {str(value) for value in plan["fit_partitions"]}
    threshold = {str(value) for value in plan["threshold_selection_partitions"]}
    if invalid := sorted(fit - set(policy["allowed_fit_partitions"])):
        raise ValueError(f"calibration plan uses prohibited fit partitions: {invalid}")
    if invalid := sorted(threshold - set(policy["allowed_threshold_selection_partitions"])):
        raise ValueError(f"calibration plan uses prohibited threshold partitions: {invalid}")
    if plan["existing_holdout_status"] != "consumed_exploratory_selection_evidence":
        raise ValueError("calibration plan must mark existing holdouts as consumed")
    if plan["future_confirmation_status"] not in {"not_available", "reserved_unseen"}:
        raise ValueError("calibration plan has invalid future confirmation status")
    return {
        **dict(plan),
        "schema_version": "validated_ml_calibration_plan/v1",
        "authorization_stage": AUTHORIZATION_STAGE,
        "exploratory_calibration_authorized": True,
        "confirmatory_evidence": False,
        "approved_as_signal_input": False,
        "paper_trading_approved": False,
        "live_trading_approved": False,
    }


def validate_prediction_envelope(payload: Mapping[str, Any]) -> dict[str, Any]:
    keys = set(payload)
    missing = sorted(set(PREDICTION_FIELDS) - keys)
    unknown = sorted(keys - set(PREDICTION_FIELDS))
    prohibited = sorted(keys & PROHIBITED_PREDICTION_FIELDS)
    if missing:
        raise ValueError(f"prediction envelope missing fields: {missing}")
    if unknown:
        raise ValueError(f"prediction envelope has unknown fields: {unknown}")
    if prohibited:
        raise ValueError(f"prediction envelope has prohibited authority fields: {prohibited}")
    if payload["schema_version"] != PREDICTION_SCHEMA_VERSION:
        raise ValueError("prediction schema version mismatch")
    if payload["authorization_stage"] != AUTHORIZATION_STAGE or payload["environment"] != "research":
        raise ValueError("prediction envelope is not research-authorized")
    if _as_bool(payload["approved_as_signal_input"]):
        raise ValueError("prediction cannot self-approve as a signal input")
    for field in ("event_id", "correlation_id", "release_id", "model_version", "feature_contract_version", "label_contract_version"):
        if not str(payload[field]).strip():
            raise ValueError(f"prediction field is blank: {field}")
    created = _parse_time(payload["created_at"])
    effective = _parse_time(payload["effective_at"])
    expires = _parse_time(payload["expires_at"])
    available = _parse_time(payload["feature_available_at"])
    if available > effective:
        raise ValueError("feature availability is after prediction effective time")
    if created > effective or effective >= expires:
        raise ValueError("prediction timestamps are out of order")
    status = str(payload["prediction_status"])
    score = payload["score"]
    uncertainty = payload["uncertainty"]
    reason = payload["abstention_reason"]
    if status == "predicted":
        if score is None or uncertainty is None or reason not in (None, ""):
            raise ValueError("predicted envelope requires score/uncertainty and no abstention reason")
        if not 0.0 <= float(score) <= 1.0 or not 0.0 <= float(uncertainty) <= 1.0:
            raise ValueError("prediction score or uncertainty is out of range")
    elif status == "abstained":
        if score is not None or uncertainty is not None or not str(reason or "").strip():
            raise ValueError("abstained envelope requires null score/uncertainty and a reason")
    else:
        raise ValueError(f"unknown prediction status: {status}")
    return dict(payload)


def evaluate_model_review_eligibility(metrics: Mapping[str, Any]) -> dict[str, Any]:
    required_flags = (
        "causal_features",
        "coverage_aligned_targets",
        "chronological_splits",
        "leakage_checks_pass",
        "training_only_preprocessing",
        "primary_holdout_beats_baseline",
        "brier_beats_prevalence_baseline",
        "calibration_mapping_fit_without_holdout",
        "ood_evaluation_completed",
        "counterfactual_policy_impact_passed",
    )
    missing = sorted(set(required_flags) - set(metrics))
    if missing:
        raise ValueError(f"model evaluation metrics missing fields: {missing}")
    policy = ml_evaluation_policy()
    failures: list[str] = []
    failures.extend(name for name in required_flags if not _as_bool(metrics[name]))
    if int(metrics.get("rolling_holdouts_beating_baseline", 0)) < 2:
        failures.append("rolling_holdouts_beating_baseline")
    if float(metrics.get("expected_calibration_error", 1.0)) > 0.10:
        failures.append("expected_calibration_error")
    if float(metrics.get("worst_fold_expected_calibration_error", 1.0)) > 0.15:
        failures.append("worst_fold_expected_calibration_error")
    slope = float(metrics.get("calibration_slope", 0.0))
    if not 0.75 <= slope <= 1.25:
        failures.append("calibration_slope")
    if abs(float(metrics.get("calibration_intercept", 1.0))) > 0.10:
        failures.append("calibration_intercept")
    if float(metrics.get("maximum_feature_or_score_psi", 1.0)) > 0.20:
        failures.append("maximum_feature_or_score_psi")
    if float(metrics.get("prediction_coverage", 0.0)) < 0.95:
        failures.append("prediction_coverage")
    if float(metrics.get("invalid_input_abstention_rate", 0.0)) < 1.0:
        failures.append("invalid_input_abstention_rate")
    return {
        "schema_version": "ml_signal_input_review/v1",
        "authorization_stage": AUTHORIZATION_STAGE,
        "eligible_for_signal_input_review": not failures,
        "approved_as_signal_input": False,
        "failed_checks": sorted(set(failures)),
        "automatic_approval": False,
        "paper_trading_approved": False,
        "live_trading_approved": False,
        "policy_version": policy["schema_version"],
    }


@dataclass(frozen=True)
class FrameworkGPaths:
    output_dir: Path
    report_dir: Path
    artifact_dir: Path


def write_ml_contract_artifacts(paths: FrameworkGPaths) -> dict[str, Path]:
    for directory in (paths.output_dir, paths.report_dir, paths.artifact_dir):
        ensure_directory(directory)
    payloads = {
        "authorization_policy": authorization_policy(),
        "prediction_schema": prediction_schema(),
        "model_release_schema": model_release_schema(),
        "ml_evaluation_policy": ml_evaluation_policy(),
        "calibration_fit_policy": calibration_fit_policy(),
    }
    written: dict[str, Path] = {}
    for name, payload in payloads.items():
        path = paths.output_dir / f"framework_g_{name}.json"
        write_json_artifact(payload, path)
        shutil.copy2(path, paths.artifact_dir / path.name)
        written[name] = path
    return written


def _parse_time(value: Any) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"invalid ISO timestamp: {value}") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"timestamp must include timezone: {value}")
    return parsed


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"true", "1", "yes"}
