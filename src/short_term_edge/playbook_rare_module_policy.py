"""Playbook Framework E rare-module policy integration.

This module builds additive future-evaluation, registry, reporting, and
portfolio-audit policy artifacts from existing rare-module validation and
registry outputs only. It does not generate signals, run searches, change
candidate results, loosen official gates, promote candidates, or approve
paper/live trading.
"""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any, Mapping

import pandas as pd

RESEARCH_ONLY_GUARDRAIL = (
    "Research/simulation only. No live trading, broker adapters, order routing, webhooks, "
    "credential storage, automated execution, or LLM-driven trade decisions."
)

RARE_MODULE_REQUIRED_FIELDS = [
    "rare_module_track_enabled",
    "rare_module_validation_class",
    "fold_adequacy_status",
    "fold_interpretability",
    "rare_module_registration_decision",
    "rare_module_revisit_condition",
    "rare_module_portfolio_role",
    "module_level_fold_warning",
    "playbook_level_contribution_status",
]

RARE_MODULE_VALIDATION_CLASSES = {
    "rare_signal_insufficient_evidence": "Rare/sparse module without enough positive stress, validation, holdout, and walk-forward stress evidence.",
    "rare_positive_research_signal": "Rare positive research signal with positive research evidence but not enough module-level activity for tradability.",
    "rare_uncorrelated_diversifier_candidate": "Rare positive research signal with low average correlation and possible playbook diversification value.",
    "rare_priority_for_more_data": "Rare setup that should be revisited after materially more history before tradability/review consideration.",
    "rare_rejected_negative_or_unstable": "Rare/watchlist-labeled row blocked by negative, unstable, high-correlation, or misleading evidence.",
}

RARE_MODULE_REGISTRY_RULES = {
    "minimum_research_evidence_rules": {
        "stress_pnl": "> 0",
        "validation_pnl": "> 0",
        "holdout_pnl": "> 0",
        "walk_forward_stress_pnl": "> 0",
        "average_correlation_to_registry": "<= 0.35",
        "paper_trading_approved": False,
    },
    "required_registry_values_when_added": {
        "research_track": "rare_setup_research_signal",
        "tradability_status": "not_tradable_low_activity",
        "paper_trading_approved": False,
        "official_gates_passed": False,
    },
}

PORTFOLIO_AUDIT_RULES = {
    "include_rare_modules_as_diversifier_candidates": True,
    "report_rare_module_contribution_separately": True,
    "avoid_treating_low_activity_as_no_signal": True,
    "block_paper_review_unless_official_gates_pass_at_playbook_or_review_level": True,
    "required_rare_module_contribution_fields": [
        "rare_module_id",
        "rare_module_validation_class",
        "rare_module_active_days_added",
        "rare_module_incremental_trades",
        "rare_module_incremental_pnl",
        "rare_module_weak_fold_improvement_status",
        "rare_module_average_correlation_delta",
        "rare_module_overlap_delta",
        "rare_module_drawdown_delta",
        "playbook_level_contribution_status",
    ],
    "required_questions": [
        "whether rare modules add active days",
        "whether rare modules improve weak folds",
        "whether rare modules reduce correlation",
        "whether rare modules increase overlap or drawdown",
    ],
}

WATCHLIST_HYGIENE_RULES = {
    "watchlist_needs_more_history_is_not_review_approval": True,
    "required_before_any_review_language": {
        "stress_pnl": "> 0",
        "validation_pnl": "> 0",
        "holdout_pnl": "> 0",
        "walk_forward_stress_pnl": "> 0",
        "fold_adequacy": "interpretable_or_explicitly_rare_track_compatible",
        "paper_trading_approved": False,
    },
    "invalid_watchlist_review_status": "blocked_from_review",
}

NEXT_ACTION_RECOMMENDATION = {
    "next_action": "portfolio_audit_e_with_phase16a_rare_modules",
    "rationale": "Rare-module policy is integrated; next audit should test whether Phase 16A rare high-vol mixed modules improve playbook-level activity, folds, concentration, and weak-regime coverage.",
    "official_gates_changed": False,
    "paper_trading_approved": False,
    "rare_module_track_enabled": True,
}

INPUT_FILES = {
    "rare_module_validation_track_policy": "rare_module_validation_track_policy.json",
    "rare_module_validation_track_registration_decisions": "rare_module_validation_track_registration_decisions.csv",
    "rare_module_validation_track_next_action_recommendation": "rare_module_validation_track_next_action_recommendation.json",
    "research_signal_registry_csv": "research_signal_registry.csv",
    "research_signal_registry_json": "research_signal_registry.json",
    "research_signal_registry_e_next_action_recommendation": "research_signal_registry_e_next_action_recommendation.json",
    "playbook_module_registry_csv": "playbook_module_registry.csv",
    "playbook_module_registry_json": "playbook_module_registry.json",
    "playbook_validation_policy": "playbook_validation_policy.json",
    "playbook_fold_policy_schema": "playbook_fold_policy_schema.json",
    "validation_framework_d_module_fold_adequacy_rules": "validation_framework_d_module_fold_adequacy_rules.csv",
    "validation_framework_d_playbook_fold_reporting_rules": "validation_framework_d_playbook_fold_reporting_rules.csv",
    "playbook_evaluation_config": "playbook_evaluation_config.json",
    "playbook_labeling_rules": "playbook_labeling_rules.json",
    "playbook_module_taxonomy": "playbook_module_taxonomy.json",
}

REPORT_FILES = {
    "rare_module_validation_track_review_report": "rare_module_validation_track_review_report.md",
    "research_signal_registry_e_phase16a_update_report": "research_signal_registry_e_phase16a_update_report.md",
}


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_jsonable(payload), indent=2, sort_keys=False), encoding="utf-8")


def load_playbook_rare_module_policy_inputs(project_root: Path) -> dict[str, Any]:
    outputs = project_root / "outputs"
    reports = project_root / "reports"
    required_paths = {name: outputs / filename for name, filename in INPUT_FILES.items()}
    required_paths.update({name: reports / filename for name, filename in REPORT_FILES.items()})
    required_paths["playbook_research_objective"] = project_root / "playbook_research_objective.md"
    schema_path = outputs / "playbook_module_registry_schema.json"
    if schema_path.exists():
        required_paths["playbook_module_registry_schema"] = schema_path

    missing = [str(path) for path in required_paths.values() if not path.exists()]
    if missing:
        raise FileNotFoundError(f"Missing Playbook Framework E input(s): {missing}")

    loaded: dict[str, Any] = {}
    for name, path in required_paths.items():
        if path.suffix == ".csv":
            loaded[name] = pd.read_csv(path)
        elif path.suffix == ".json":
            loaded[name] = json.loads(path.read_text(encoding="utf-8"))
        else:
            loaded[name] = path.read_text(encoding="utf-8")
    loaded["input_paths"] = {name: str(path) for name, path in required_paths.items()}
    return loaded


def phase16a_rare_modules_in_registry(playbook_registry: pd.DataFrame) -> pd.DataFrame:
    mask = (
        playbook_registry.get("phase", pd.Series(dtype=object)).astype(str).eq("phase16a")
        & playbook_registry.get("research_track", pd.Series(dtype=object)).astype(str).eq("rare_setup_research_signal")
    )
    return playbook_registry[mask].copy().sort_values("candidate_id").reset_index(drop=True)


def rare_low_activity_mapping(signal_evidence_status: str = "positive_research_signal") -> dict[str, Any]:
    return {
        "fold_adequacy_status": "low_activity_not_fully_interpretable",
        "signal_evidence_status": signal_evidence_status,
        "signal_evidence_status_forced_to_no_signal": False,
        "tradability_status": "not_tradable_low_activity",
        "paper_trading_approved": False,
        "official_gates_passed": False,
    }


def passes_rare_registry_rules(row: Mapping[str, Any]) -> bool:
    return (
        _as_float(row.get("stress_pnl")) > 0.0
        and _as_float(row.get("validation_pnl")) > 0.0
        and _as_float(row.get("holdout_pnl")) > 0.0
        and _as_float(row.get("walk_forward_stress_pnl")) > 0.0
        and _as_float(row.get("average_correlation_to_registry")) <= 0.35
        and not _as_bool(row.get("paper_trading_approved", False))
    )


def watchlist_hygiene_review_status(row: Mapping[str, Any]) -> str:
    label = str(row.get("label", row.get("phase16a_label", "")))
    tradability = str(row.get("tradability_status", ""))
    if "watchlist_needs_more_history" not in label and tradability != "watchlist_needs_more_history":
        return "not_watchlist_label"
    fold_status = str(row.get("fold_adequacy_status", ""))
    fold_compatible = fold_status in {"interpretable", "rare_track_compatible", "low_activity_not_fully_interpretable"}
    if (
        _as_float(row.get("stress_pnl")) > 0.0
        and _as_float(row.get("validation_pnl")) > 0.0
        and _as_float(row.get("holdout_pnl")) > 0.0
        and _as_float(row.get("walk_forward_stress_pnl")) > 0.0
        and fold_compatible
        and not _as_bool(row.get("paper_trading_approved", False))
    ):
        return "rare_track_compatible_but_not_review_approval"
    return "blocked_from_review"


def build_playbook_rare_module_policy(data: Mapping[str, Any]) -> dict[str, Any]:
    registry = data["playbook_module_registry_csv"]
    phase16a_rare = phase16a_rare_modules_in_registry(registry)
    validation_policy = data["rare_module_validation_track_policy"]
    return {
        "policy_name": "playbook_framework_e_rare_module_policy_integration",
        "research_only_guardrail": RESEARCH_ONLY_GUARDRAIL,
        "rare_module_definition": {
            "specialized_module": True,
            "has_positive_research_evidence": True,
            "may_be_low_activity": True,
            "may_have_low_activity_not_fully_interpretable_fold_adequacy": True,
            "not_tradable_by_itself": True,
            "may_contribute_as_playbook_diversifier": True,
        },
        "official_gates_changed": False,
        "paper_trading_approved": False,
        "live_trading_approved": False,
        "no_official_paper_review_threshold_is_loosened": True,
        "rare_module_track_enabled": True,
        "rare_module_track_scope": "research-only",
        "new_strategy_signals_generated": False,
        "strategy_searches_run": False,
        "candidate_results_changed": False,
        "candidates_promoted": False,
        "required_rare_module_fields": list(RARE_MODULE_REQUIRED_FIELDS),
        "rare_module_validation_classes": deepcopy(RARE_MODULE_VALIDATION_CLASSES),
        "registry_behavior": deepcopy(RARE_MODULE_REGISTRY_RULES),
        "portfolio_audit_behavior": deepcopy(PORTFOLIO_AUDIT_RULES),
        "fold_adequacy_behavior": {
            "module_level_sparse_folds_status": "low_activity_not_fully_interpretable",
            "low_fold_adequacy_erases_positive_signal_evidence": False,
            "low_fold_adequacy_blocks_tradability_or_review_unless_playbook_level_evidence_later_supports_it": True,
            "portfolio_level_fold_stability_required_for_playbook_review": True,
        },
        "watchlist_hygiene": deepcopy(WATCHLIST_HYGIENE_RULES),
        "future_reporting_language": {
            "preferred": [
                "rare positive research signal",
                "rare setup diversifier",
                "low activity / fold result not fully interpretable",
                "not tradable by itself",
                "portfolio contribution required before further review",
                "paper trading not approved",
            ],
            "avoid_without_qualification": [
                "watchlist",
                "approved",
                "tradable",
                "passed unless official gates passed",
            ],
        },
        "phase16a_registry_evidence_summary": {
            "phase16a_rare_modules_present_in_registry": int(len(phase16a_rare)),
            "module_ids": phase16a_rare.get("module_id", pd.Series(dtype=object)).astype(str).tolist(),
            "all_paper_trading_approved_false": bool((phase16a_rare["paper_trading_approved"].astype(str).str.lower() == "false").all()) if not phase16a_rare.empty else False,
            "all_official_gates_passed_false": bool((phase16a_rare["official_gates_passed"].astype(str).str.lower() == "false").all()) if not phase16a_rare.empty else False,
        },
        "source_policy": {
            "policy_name": validation_policy.get("policy_name"),
            "rare_module_track_enabled": validation_policy.get("rare_module_track_enabled"),
            "official_gates_changed": validation_policy.get("official_gates_changed"),
            "paper_trading_approved": validation_policy.get("paper_trading_approved"),
        },
    }


def build_reporting_guidelines(policy: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "guideline_name": "playbook_rare_module_reporting_guidelines",
        "official_gates_changed": False,
        "paper_trading_approved": False,
        "required_phrases": policy["future_reporting_language"]["preferred"],
        "avoid_phrases_without_qualification": policy["future_reporting_language"]["avoid_without_qualification"],
        "required_sections": [
            "rare-module contribution",
            "module-level fold warning",
            "playbook-level contribution status",
            "watchlist hygiene",
            "research-only guardrail",
        ],
    }


def build_portfolio_audit_rules(policy: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "rule_set_name": "playbook_rare_module_portfolio_audit_rules",
        "official_gates_changed": False,
        "paper_trading_approved": False,
        **deepcopy(policy["portfolio_audit_behavior"]),
    }


def build_registry_schema_additions(policy: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema_addition_name": "playbook_rare_module_registry_schema_additions",
        "official_gates_changed": False,
        "paper_trading_approved_default": False,
        "required_rare_module_fields": list(policy["required_rare_module_fields"]),
        "field_definitions": {
            "rare_module_track_enabled": "Boolean flag that marks rows governed by the rare setup research-only track.",
            "rare_module_validation_class": "One of the standardized rare-module validation classes.",
            "fold_adequacy_status": "Module-level fold adequacy; sparse rare modules use low_activity_not_fully_interpretable.",
            "fold_interpretability": "Whether module-level folds are interpretable, low-activity, or rare-track compatible.",
            "rare_module_registration_decision": "Research-only registration decision, never paper approval.",
            "rare_module_revisit_condition": "Condition for revisiting with more data or playbook-level evidence.",
            "rare_module_portfolio_role": "Rare setup diversifier / rare setup module / none.",
            "module_level_fold_warning": "Required warning when module-level folds are sparse.",
            "playbook_level_contribution_status": "Separately reported portfolio/playbook contribution result.",
        },
        "allowed_rare_module_validation_classes": list(RARE_MODULE_VALIDATION_CLASSES.keys()),
    }


def build_updated_playbook_evaluation_config(existing: Mapping[str, Any]) -> dict[str, Any]:
    config = deepcopy(existing)
    fields = list(config.get("future_candidate_output_fields", []))
    for field in RARE_MODULE_REQUIRED_FIELDS:
        if field not in fields:
            fields.append(field)
    config["future_candidate_output_fields"] = fields
    config["rare_module_policy_integration"] = {
        "rare_module_track_enabled": True,
        "low_activity_does_not_imply_no_signal": True,
        "tradability_status_when_low_activity": "not_tradable_low_activity",
        "portfolio_contribution_required_before_further_review": True,
        "official_gates_changed": False,
        "paper_trading_approved": False,
    }
    return config


def build_updated_playbook_labeling_rules(existing: Mapping[str, Any]) -> dict[str, Any]:
    rules = deepcopy(existing)
    classes = list(rules.get("rare_module_validation_class", []))
    for klass in RARE_MODULE_VALIDATION_CLASSES:
        if klass not in classes:
            classes.append(klass)
    rules["rare_module_validation_class"] = classes
    rules["rare_module_low_activity_rule"] = rare_low_activity_mapping()
    rules["watchlist_hygiene_rule"] = deepcopy(WATCHLIST_HYGIENE_RULES)
    rules["official_gates_changed"] = False
    return rules


def build_updated_playbook_module_taxonomy(existing: Mapping[str, Any]) -> dict[str, Any]:
    taxonomy = deepcopy(existing)
    roles = list(taxonomy.get("portfolio_role", []))
    for role in ["rare_setup_diversifier", "rare_setup_module"]:
        if role not in roles:
            roles.append(role)
    taxonomy["portfolio_role"] = roles
    taxonomy["rare_module_validation_class"] = list(RARE_MODULE_VALIDATION_CLASSES.keys())
    taxonomy["rare_module_required_fields"] = list(RARE_MODULE_REQUIRED_FIELDS)
    return taxonomy


def build_updated_registry_schema(existing: Mapping[str, Any] | None, additions: Mapping[str, Any]) -> dict[str, Any] | None:
    if existing is None:
        return None
    schema = deepcopy(existing)
    columns = list(schema.get("columns", []))
    for field in additions["required_rare_module_fields"]:
        if field not in columns:
            columns.append(field)
    schema["columns"] = columns
    schema["rare_module_schema_additions"] = deepcopy(additions)
    schema["official_gates_changed"] = False
    schema["paper_trading_approved_default"] = False
    return schema


def render_policy_integration_report(
    *,
    policy: Mapping[str, Any],
    reporting_guidelines: Mapping[str, Any],
    portfolio_rules: Mapping[str, Any],
    schema_additions: Mapping[str, Any],
    recommendation: Mapping[str, Any],
) -> str:
    summary = policy["phase16a_registry_evidence_summary"]
    lines = [
        "# Playbook Framework E — Rare Module Policy Integration",
        "",
        RESEARCH_ONLY_GUARDRAIL,
        "",
        "This is additive/config/reporting policy integration only. It generated no new signals, ran no strategy searches, changed no existing candidate results, changed no official promotion gates, promoted no candidates, and approved no paper or live trading.",
        "",
        "## Official gates and approvals",
        "",
        "- official_gates_changed: `false`",
        "- paper_trading_approved: `false`",
        "- live_trading_approved: `false`",
        "- No official paper-review threshold is loosened.",
        "- Rare module track is research-only.",
        "",
        "## Rare module definition",
        "",
        "A rare module is a specialized module with positive research evidence that may be low activity and may have low_activity_not_fully_interpretable fold adequacy. It is not tradable by itself, but may contribute as a rare setup diversifier inside the playbook after portfolio contribution is measured.",
        "",
        "## Required rare-module fields",
        "",
        ", ".join(policy["required_rare_module_fields"]),
        "",
        "## Rare-module validation classes",
        "",
    ]
    lines.extend(f"- {name}: {description}" for name, description in policy["rare_module_validation_classes"].items())
    lines.extend([
        "",
        "## Rare-module registry behavior",
        "",
        "Rare modules may be added only when stress_pnl, validation_pnl, holdout_pnl, and walk_forward_stress_pnl are all positive, average correlation to registry is <= 0.35, and paper_trading_approved is false.",
        "Registered rare modules must remain research_track=`rare_setup_research_signal`, tradability_status=`not_tradable_low_activity`, paper_trading_approved=`false`, and official_gates_passed=`false`.",
        "",
        "## Portfolio-audit rare-module behavior",
        "",
    ])
    for question in portfolio_rules["required_questions"]:
        lines.append(f"- Report {question}.")
    lines.extend([
        "- Include rare modules as diversifier candidates and report rare-module contribution separately.",
        "- Avoid treating low activity as no_signal.",
        "- Still block paper-review unless official gates pass at playbook/review level.",
        "",
        "## Fold adequacy behavior",
        "",
        "- Module-level folds with too few trades should be marked low_activity_not_fully_interpretable.",
        "- Low fold adequacy does not erase positive signal evidence.",
        "- Low fold adequacy blocks tradability/review unless later playbook-level evidence supports review.",
        "- Portfolio-level fold stability remains required for playbook review.",
        "",
        "## Watchlist hygiene",
        "",
        "Future reports must not treat watchlist_needs_more_history labels as review approval unless positive stress/validation/holdout/walk-forward stress evidence exists, fold adequacy is interpretable or explicitly rare-track compatible, and paper_trading_approved remains false.",
        "",
        "## Future reporting language",
        "",
    ])
    lines.extend(f"- Use: {phrase}" for phrase in reporting_guidelines["required_phrases"])
    lines.extend([
        "- Avoid unqualified: watchlist, approved, tradable, passed unless official gates passed.",
        "",
        "## Phase 16A rare modules in registry",
        "",
        f"- phase16a_rare_modules_present_in_registry: `{summary['phase16a_rare_modules_present_in_registry']}`",
        f"- all_paper_trading_approved_false: `{str(summary['all_paper_trading_approved_false']).lower()}`",
        f"- all_official_gates_passed_false: `{str(summary['all_official_gates_passed_false']).lower()}`",
        "",
        "## Registry schema additions",
        "",
        ", ".join(schema_additions["required_rare_module_fields"]),
        "",
        "## Recommended next action",
        "",
        f"- next_action: `{recommendation['next_action']}`",
        f"- rationale: {recommendation['rationale']}",
        f"- official_gates_changed: `{str(recommendation['official_gates_changed']).lower()}`",
        f"- paper_trading_approved: `{str(recommendation['paper_trading_approved']).lower()}`",
        f"- rare_module_track_enabled: `{str(recommendation['rare_module_track_enabled']).lower()}`",
        "",
    ])
    return "\n".join(lines)


def append_framework_e_report_note(existing: str) -> str:
    note = (
        "\n\n## Framework E rare-module policy note\n\n"
        "Future registry and portfolio-audit reports should treat Phase 16A-style rows as rare positive research signal / rare setup diversifier candidates only when rare-module evidence rules pass. "
        "Low activity / fold result not fully interpretable does not convert positive signal evidence to no_signal, but the module remains not tradable by itself and paper trading not approved. "
        "Portfolio contribution required before further review; official gates unchanged.\n"
    )
    if "## Framework E rare-module policy note" in existing:
        return existing
    return existing.rstrip() + note


def build_playbook_framework_e_artifacts(project_root: Path) -> dict[str, Any]:
    data = load_playbook_rare_module_policy_inputs(project_root)
    policy = build_playbook_rare_module_policy(data)
    reporting_guidelines = build_reporting_guidelines(policy)
    portfolio_rules = build_portfolio_audit_rules(policy)
    schema_additions = build_registry_schema_additions(policy)
    recommendation = deepcopy(NEXT_ACTION_RECOMMENDATION)
    updated_config = build_updated_playbook_evaluation_config(data["playbook_evaluation_config"])
    updated_labeling_rules = build_updated_playbook_labeling_rules(data["playbook_labeling_rules"])
    updated_taxonomy = build_updated_playbook_module_taxonomy(data["playbook_module_taxonomy"])
    updated_registry_schema = build_updated_registry_schema(data.get("playbook_module_registry_schema"), schema_additions)
    report = render_policy_integration_report(
        policy=policy,
        reporting_guidelines=reporting_guidelines,
        portfolio_rules=portfolio_rules,
        schema_additions=schema_additions,
        recommendation=recommendation,
    )
    return {
        "inputs_loaded": sorted(k for k in data.keys() if k != "input_paths"),
        "policy": policy,
        "reporting_guidelines": reporting_guidelines,
        "portfolio_audit_rules": portfolio_rules,
        "registry_schema_additions": schema_additions,
        "recommendation": recommendation,
        "updated_playbook_evaluation_config": updated_config,
        "updated_playbook_labeling_rules": updated_labeling_rules,
        "updated_playbook_module_taxonomy": updated_taxonomy,
        "updated_playbook_module_registry_schema": updated_registry_schema,
        "report": report,
        "phase16a_rare_modules": phase16a_rare_modules_in_registry(data["playbook_module_registry_csv"]),
        "research_signal_registry": data["research_signal_registry_csv"],
        "playbook_module_registry": data["playbook_module_registry_csv"],
    }


def _as_float(value: Any) -> float:
    if value is None or pd.isna(value):
        return 0.0
    return float(value)


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"true", "1", "yes"}


def _jsonable(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, Path):
        return value.as_posix()
    if hasattr(value, "item"):
        return value.item()
    return value
