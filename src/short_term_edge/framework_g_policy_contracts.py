from __future__ import annotations

from typing import Any, Mapping


COUNTERFACTUAL_POLICY_VERSION = "counterfactual_model_overlay/v1"
LLM_TASK_REGISTRY_VERSION = "bounded_llm_task_registry/v1"
LLM_OUTPUT_ENVELOPE_VERSION = "bounded_llm_output_envelope/v1"


def counterfactual_policy_contract() -> dict[str, Any]:
    return {
        "schema_version": COUNTERFACTUAL_POLICY_VERSION,
        "authorization_stage": "research",
        "purpose": "offline deterministic measurement of model-score impact on an existing scheduler replay",
        "allowed_overlay_actions": [
            "no_model_baseline",
            "abstain_on_invalid_model_output",
            "veto_existing_candidate_at_fixed_threshold",
            "priority_tiebreak_among_existing_candidates",
        ],
        "prohibited_changes": [
            "generate_new_entry",
            "increase_position_size",
            "change_stop_or_target",
            "change_risk_limit",
            "override_risk_rejection",
            "change_official_gate",
            "route_order",
        ],
        "fixed_before_holdout": [
            "model_release_id",
            "calibration_version",
            "feature_contract_version",
            "overlay_action",
            "threshold",
            "scheduler_policy_version",
            "risk_policy_version",
            "cost_and_slippage_config",
        ],
        "required_baseline_and_overlay_metrics": [
            "net_pnl",
            "stress_pnl",
            "validation_pnl",
            "holdout_pnl",
            "walk_forward_stress_pnl",
            "max_drawdown",
            "best_day_concentration",
            "best_trade_concentration",
            "positive_wf_test_folds_pct",
            "worst_wf_test_fold",
            "active_days",
            "accepted_trades",
            "model_abstention_count",
            "risk_reject_count",
        ],
        "review_eligibility_rules": {
            "net_pnl_delta": "> 0",
            "stress_pnl_delta": ">= 0",
            "validation_pnl_delta": ">= 0",
            "holdout_pnl_delta": ">= 0",
            "walk_forward_stress_pnl_delta": ">= 0",
            "max_drawdown_must_not_worsen": True,
            "concentration_must_not_worsen": True,
            "positive_fold_fraction_must_not_worsen": True,
            "worst_fold_must_not_worsen": True,
            "minimum_active_day_retention": 0.80,
        },
        "automatic_scheduler_mutation": False,
        "automatic_signal_input_approval": False,
        "paper_trading_approved": False,
        "live_trading_approved": False,
    }


def evaluate_counterfactual_policy_impact(
    baseline: Mapping[str, Any], overlay: Mapping[str, Any], metadata: Mapping[str, Any]
) -> dict[str, Any]:
    contract = counterfactual_policy_contract()
    required_metrics = set(contract["required_baseline_and_overlay_metrics"])
    if missing := sorted(required_metrics - set(baseline)):
        raise ValueError(f"baseline policy metrics missing: {missing}")
    if missing := sorted(required_metrics - set(overlay)):
        raise ValueError(f"overlay policy metrics missing: {missing}")
    required_metadata = set(contract["fixed_before_holdout"])
    if missing := sorted(required_metadata - set(metadata)):
        raise ValueError(f"counterfactual metadata missing: {missing}")
    if metadata["overlay_action"] not in contract["allowed_overlay_actions"]:
        raise ValueError(f"counterfactual overlay action is not allowed: {metadata['overlay_action']}")
    if _as_bool(metadata.get("generates_new_entries", False)):
        raise ValueError("counterfactual overlay cannot generate new entries")
    if _as_bool(metadata.get("changes_size_or_risk", False)):
        raise ValueError("counterfactual overlay cannot change size or risk")

    failures: list[str] = []
    for field in ("stress_pnl", "validation_pnl", "holdout_pnl", "walk_forward_stress_pnl"):
        if float(overlay[field]) < float(baseline[field]):
            failures.append(f"{field}_worsened")
    if float(overlay["net_pnl"]) <= float(baseline["net_pnl"]):
        failures.append("net_pnl_not_improved")
    if float(overlay["max_drawdown"]) < float(baseline["max_drawdown"]):
        failures.append("max_drawdown_worsened")
    for field in ("best_day_concentration", "best_trade_concentration"):
        if float(overlay[field]) > float(baseline[field]):
            failures.append(f"{field}_worsened")
    if float(overlay["positive_wf_test_folds_pct"]) < float(baseline["positive_wf_test_folds_pct"]):
        failures.append("positive_wf_test_folds_pct_worsened")
    if float(overlay["worst_wf_test_fold"]) < float(baseline["worst_wf_test_fold"]):
        failures.append("worst_wf_test_fold_worsened")
    active_retention = _ratio(float(overlay["active_days"]), float(baseline["active_days"]))
    if active_retention < 0.80:
        failures.append("active_day_retention_below_80pct")
    return {
        "schema_version": "counterfactual_model_overlay_decision/v1",
        "authorization_stage": "research",
        "eligible_for_signal_input_review": not failures,
        "approved_as_signal_input": False,
        "scheduler_policy_mutated": False,
        "official_gates_changed": False,
        "paper_trading_approved": False,
        "live_trading_approved": False,
        "failed_checks": sorted(failures),
        "active_day_retention": round(active_retention, 6),
        "net_pnl_delta": round(float(overlay["net_pnl"]) - float(baseline["net_pnl"]), 2),
        "automatic_approval": False,
    }


def bounded_llm_task_registry() -> dict[str, Any]:
    common_prohibited = [
        "quantity",
        "position_size",
        "risk_limit",
        "risk_override",
        "broker_instruction",
        "order_payload",
        "credential",
    ]
    return {
        "schema_version": LLM_TASK_REGISTRY_VERSION,
        "authorization_stage": "research",
        "default_task_enabled": False,
        "free_form_text_is_commentary_only": True,
        "unknown_tasks_rejected": True,
        "invalid_outputs_discarded_not_coerced": True,
        "tasks": {
            "research_evidence_summary": {
                "enabled": True,
                "allowed_input_classes": ["versioned_research_reports", "versioned_metrics", "approved_taxonomy"],
                "required_output_fields": ["evidence_codes", "summary", "uncertainties"],
                "allowed_output_fields": ["evidence_codes", "summary", "uncertainties"],
                "prohibited_output_fields": common_prohibited,
                "may_affect_policy": False,
            },
            "incident_classification": {
                "enabled": True,
                "allowed_input_classes": ["redacted_incident_events", "approved_incident_taxonomy"],
                "required_output_fields": ["incident_class", "severity", "evidence_codes", "uncertainties"],
                "allowed_output_fields": ["incident_class", "severity", "evidence_codes", "uncertainties"],
                "prohibited_output_fields": common_prohibited,
                "may_affect_policy": False,
            },
            "operator_checklist": {
                "enabled": True,
                "allowed_input_classes": ["approved_runbook", "redacted_system_state"],
                "required_output_fields": ["checklist_items", "evidence_codes", "uncertainties"],
                "allowed_output_fields": ["checklist_items", "evidence_codes", "uncertainties"],
                "prohibited_output_fields": common_prohibited,
                "may_affect_policy": False,
            },
            "candidate_proposal": {
                "enabled": False,
                "enablement_requires_explicit_later_stage_policy": True,
                "allowed_input_classes": ["allowlisted_modules", "versioned_market_context", "approved_evidence_codes"],
                "required_output_fields": ["module_ids", "direction", "evidence_codes", "expires_at", "uncertainties"],
                "allowed_output_fields": ["module_ids", "direction", "evidence_codes", "expires_at", "uncertainties"],
                "prohibited_output_fields": common_prohibited,
                "may_affect_policy": False,
            },
        },
        "llm_may_authorize_orders": False,
        "llm_may_set_size_or_risk": False,
        "approved_as_signal_input_default": False,
        "paper_trading_approved": False,
        "live_trading_approved": False,
    }


def validate_llm_output_envelope(payload: Mapping[str, Any], registry: Mapping[str, Any] | None = None) -> dict[str, Any]:
    registry = registry or bounded_llm_task_registry()
    required_envelope = {
        "schema_version",
        "task_id",
        "model_identifier",
        "prompt_template_version",
        "tool_policy_version",
        "input_refs",
        "output",
        "validation_status",
        "authorization_stage",
        "approved_as_signal_input",
    }
    missing = sorted(required_envelope - set(payload))
    unknown = sorted(set(payload) - required_envelope)
    if missing:
        raise ValueError(f"LLM output envelope missing fields: {missing}")
    if unknown:
        raise ValueError(f"LLM output envelope has unknown fields: {unknown}")
    if payload["schema_version"] != LLM_OUTPUT_ENVELOPE_VERSION:
        raise ValueError("LLM output envelope schema mismatch")
    if payload["authorization_stage"] != "research" or _as_bool(payload["approved_as_signal_input"]):
        raise ValueError("LLM output envelope has invalid authorization")
    task_id = str(payload["task_id"])
    task = registry["tasks"].get(task_id)
    if task is None:
        raise ValueError(f"unknown LLM task: {task_id}")
    if not _as_bool(task["enabled"]):
        raise ValueError(f"LLM task is disabled: {task_id}")
    if payload["validation_status"] != "schema_valid":
        raise ValueError("LLM output must be schema valid")
    output = payload["output"]
    if not isinstance(output, Mapping):
        raise ValueError("LLM task output must be an object")
    required = set(task["required_output_fields"])
    allowed = set(task["allowed_output_fields"])
    if missing := sorted(required - set(output)):
        raise ValueError(f"LLM task output missing fields: {missing}")
    if unknown := sorted(set(output) - allowed):
        raise ValueError(f"LLM task output has unknown or prohibited fields: {unknown}")
    return dict(payload)


def _ratio(numerator: float, denominator: float) -> float:
    if denominator <= 0:
        return 0.0
    return numerator / denominator


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"true", "1", "yes"}
