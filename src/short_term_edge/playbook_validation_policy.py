"""Standardized playbook fold-validation policy.

Validation Framework D is additive policy/reporting support only. It uses existing
Validation Framework Audit C and playbook framework artifacts; it does not generate
signals, run searches, change candidate results, loosen official gates, promote
candidates, or approve paper/live trading.
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

AUDIT_C_INPUT_FILES = {
    "fold_boundary_summary": "validation_framework_audit_c_fold_boundary_summary.csv",
    "alternative_fold_results": "validation_framework_audit_c_alternative_fold_results.csv",
    "fold_sensitivity_summary": "validation_framework_audit_c_fold_sensitivity_summary.csv",
    "module_activity_by_fold": "validation_framework_audit_c_module_activity_by_fold.csv",
    "playbook_activity_by_fold": "validation_framework_audit_c_playbook_activity_by_fold.csv",
    "fold_regime_composition": "validation_framework_audit_c_fold_regime_composition.csv",
    "gate_sensitivity_by_fold_design": "validation_framework_audit_c_gate_sensitivity_by_fold_design.csv",
    "recommended_validation_policy": "validation_framework_audit_c_recommended_validation_policy.json",
    "next_action_recommendation": "validation_framework_audit_c_next_action_recommendation.json",
}

PLAYBOOK_INPUT_FILES = {
    "playbook_evaluation_config": "playbook_evaluation_config.json",
    "playbook_labeling_rules": "playbook_labeling_rules.json",
    "playbook_module_taxonomy": "playbook_module_taxonomy.json",
    "playbook_module_registry": "playbook_module_registry.csv",
    "research_signal_registry": "research_signal_registry.csv",
}

STANDARD_FOLD_VIEWS = {
    "existing_project_folds": {
        "role": "continuity_primary_reported_view",
        "required_in_future_reports": True,
        "diagnostic_companion_only": False,
        "official_promotion_gate": False,
        "description": "Retained for continuity with prior research and still reported.",
        "adequacy_warning_required": False,
    },
    "half_year_folds": {
        "role": "diagnostic_companion_less_coarse_view",
        "required_in_future_reports": True,
        "diagnostic_companion_only": True,
        "official_promotion_gate": False,
        "description": "Diagnostic companion fold view; Audit C showed it may be less coarse than existing folds.",
        "adequacy_warning_required": False,
    },
    "rolling_6_month_test_folds": {
        "role": "diagnostic_regime_sensitivity_view",
        "required_in_future_reports": True,
        "diagnostic_companion_only": True,
        "official_promotion_gate": False,
        "description": "Diagnostic regime-sensitivity view; not an official promotion gate.",
        "adequacy_warning_required": False,
    },
    "quarterly_folds": {
        "role": "diagnostic_stress_view",
        "required_in_future_reports": True,
        "diagnostic_companion_only": True,
        "official_promotion_gate": False,
        "description": "Diagnostic stress view. It may be too sparse for rare modules, so adequacy warnings are required.",
        "adequacy_warning_required": True,
    },
}

FOLD_ADEQUACY_DEFAULTS = {
    "thresholds_are_configurable_defaults": True,
    "module_fold_min_active_days": 10,
    "module_fold_min_trades": 10,
    "playbook_fold_min_active_days": 30,
    "playbook_fold_min_trades": 30,
    "low_activity_implies_no_signal": False,
    "low_activity_can_block_tradability": True,
}

FUTURE_VALIDATION_FIELDS = [
    "validation_level",
    "primary_fold_view",
    "companion_fold_views",
    "fold_adequacy_status",
    "folds_below_min_activity",
    "module_level_positive_fold_pct",
    "playbook_level_positive_fold_pct",
    "fold_design_sensitivity_flag",
    "official_gates_passed",
    "paper_trading_approved",
]

REPORTING_LANGUAGE = [
    "fold result is low-activity / not fully interpretable",
    "positive research signal but not tradable",
    "playbook-level fold stability failed",
    "alternative fold views are diagnostic only",
    "official gates unchanged",
]

NEXT_ACTION_RECOMMENDATION = {
    "next_action": "phase16a_targeted_regime_module_scout",
    "rationale": "Playbook fold policy is standardized diagnostically; next module search should target unresolved weak regimes while reporting existing, half-year, and rolling 6-month fold views.",
    "official_gates_changed": False,
    "paper_trading_approved": False,
    "live_trading_approved": False,
}


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=False), encoding="utf-8")


def load_validation_framework_d_inputs(project_root: Path) -> dict[str, Any]:
    """Load all required existing artifacts fail-closed."""
    outputs = project_root / "outputs"
    reports = project_root / "reports"
    required_paths: dict[str, Path] = {}
    required_paths.update({name: outputs / filename for name, filename in AUDIT_C_INPUT_FILES.items()})
    required_paths.update({name: outputs / filename for name, filename in PLAYBOOK_INPUT_FILES.items()})
    required_paths["playbook_research_objective"] = project_root / "playbook_research_objective.md"
    required_paths["audit_c_report"] = reports / "validation_framework_audit_c_fold_design_report.md"

    missing = [str(path) for path in required_paths.values() if not path.exists()]
    if missing:
        raise FileNotFoundError(f"Missing Validation Framework D input(s): {missing}")

    loaded: dict[str, Any] = {}
    for name, path in required_paths.items():
        if path.suffix == ".csv":
            loaded[name] = pd.read_csv(path)
        elif path.suffix == ".json":
            loaded[name] = _read_json(path)
        else:
            loaded[name] = path.read_text(encoding="utf-8")
    loaded["input_paths"] = {name: str(path) for name, path in required_paths.items()}
    return loaded


def build_validation_levels() -> dict[str, Any]:
    return {
        "module_level_validation": {
            "used_for": "individual specialized modules",
            "may_be_sparse": True,
            "requires_fold_adequacy_before_interpreting_pass_fail": True,
            "low_activity_alone_means_no_signal": False,
            "low_activity_can_block_tradability": True,
            "required_diagnostics": [
                "active_days_per_fold",
                "trades_per_fold",
                "folds_below_min_activity",
                "fold_result_interpretable",
                "module_level_positive_fold_pct",
            ],
        },
        "playbook_level_validation": {
            "used_for": "combined module portfolios and schedulers",
            "responsible_for_regular_opportunity": True,
            "required_diagnostics": [
                "fold_stability",
                "concentration",
                "drawdown",
                "active_days",
                "module_contribution",
                "playbook_level_positive_fold_pct",
            ],
        },
        "paper_review_validation": {
            "strictest_level": True,
            "official_gates_changed": False,
            "paper_trading_approved_by_this_policy": False,
            "no_official_paper_review_threshold_loosened": True,
            "alternative_folds_diagnostic_unless_later_human_promoted": True,
        },
    }


def build_playbook_validation_policy(data: Mapping[str, Any]) -> dict[str, Any]:
    """Build deterministic standardized fold policy without changing gates."""
    sensitivity = data["fold_sensitivity_summary"]
    gate = data["gate_sensitivity_by_fold_design"]
    observed_fold_views = sorted(str(v) for v in sensitivity.get("fold_design", pd.Series(dtype=object)).dropna().unique())
    material_change_count = int(sensitivity.get("conclusion_materially_changes", pd.Series(dtype=bool)).fillna(False).astype(bool).sum()) if not sensitivity.empty else 0
    official_gate_changes_seen = bool(gate.get("official_gates_changed", pd.Series(dtype=bool)).fillna(False).astype(bool).any()) if not gate.empty else False

    policy = {
        "policy_name": "validation_framework_d_standardize_playbook_folds",
        "diagnostic_only": True,
        "research_only_guardrail": RESEARCH_ONLY_GUARDRAIL,
        "official_gates_changed": False,
        "paper_trading_approved": False,
        "live_trading_approved": False,
        "new_strategy_signals_generated": False,
        "strategy_searches_run": False,
        "candidate_results_changed": False,
        "candidates_promoted": False,
        "official_gate_policy": {
            "no_official_paper_review_threshold_is_loosened": True,
            "official_promotion_gates_remain_unchanged": True,
            "alternative_folds_are_diagnostic_companions_unless_explicitly_promoted_later_by_human_review": True,
            "quarterly_folds_are_official_promotion_gates": False,
            "rolling_3_month_folds_are_official_promotion_gates": False,
            "audit_c_gate_sensitivity_official_gate_changes_seen": official_gate_changes_seen,
        },
        "validation_levels": build_validation_levels(),
        "standard_fold_views": deepcopy(STANDARD_FOLD_VIEWS),
        "fold_adequacy_defaults": deepcopy(FOLD_ADEQUACY_DEFAULTS),
        "rare_module_fold_adequacy_rules": {
            "report_active_days_per_fold": True,
            "report_trades_per_fold": True,
            "report_folds_below_min_activity": True,
            "report_whether_fold_result_is_interpretable": True,
            "do_not_mark_no_signal_solely_because_rare_module_folds_are_sparse": True,
            "tradability_may_still_be_blocked_by_low_activity": True,
        },
        "future_candidate_output_fields": list(FUTURE_VALIDATION_FIELDS),
        "reporting_language": list(REPORTING_LANGUAGE),
        "audit_c_evidence_summary": {
            "observed_fold_views": observed_fold_views,
            "fold_designs_with_material_sensitivity_rows": material_change_count,
            "audit_c_policy_fold_conclusions_change_by_design": bool(data["recommended_validation_policy"].get("fold_conclusions_change_by_design", False)),
            "audit_c_policy_alternative_folds_diagnostic_only": bool(data["recommended_validation_policy"].get("alternative_fold_designs_are_diagnostic_companion_only", False)),
        },
    }
    return policy


def build_policy_schema(policy: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "Playbook validation fold policy schema",
        "type": "object",
        "required": [
            "policy_name",
            "official_gates_changed",
            "paper_trading_approved",
            "live_trading_approved",
            "validation_levels",
            "standard_fold_views",
            "fold_adequacy_defaults",
            "future_candidate_output_fields",
        ],
        "properties": {
            "policy_name": {"type": "string"},
            "official_gates_changed": {"const": False},
            "paper_trading_approved": {"const": False},
            "live_trading_approved": {"const": False},
            "validation_levels": {"type": "object", "required": list(policy["validation_levels"].keys())},
            "standard_fold_views": {"type": "object", "required": list(STANDARD_FOLD_VIEWS.keys())},
            "fold_adequacy_defaults": {
                "type": "object",
                "required": [
                    "module_fold_min_active_days",
                    "module_fold_min_trades",
                    "playbook_fold_min_active_days",
                    "playbook_fold_min_trades",
                    "low_activity_implies_no_signal",
                ],
            },
            "future_candidate_output_fields": {"type": "array", "contains": {"const": "validation_level"}},
        },
    }


def classify_fold_adequacy(*, validation_level: str, active_days: int, trades: int, policy: Mapping[str, Any]) -> dict[str, Any]:
    defaults = policy["fold_adequacy_defaults"]
    if validation_level == "module_level_validation":
        min_active = int(defaults["module_fold_min_active_days"])
        min_trades = int(defaults["module_fold_min_trades"])
    elif validation_level == "playbook_level_validation":
        min_active = int(defaults["playbook_fold_min_active_days"])
        min_trades = int(defaults["playbook_fold_min_trades"])
    else:
        raise ValueError(f"unknown validation_level: {validation_level}")
    below = int(active_days) < min_active or int(trades) < min_trades
    return {
        "validation_level": validation_level,
        "active_days": int(active_days),
        "trades": int(trades),
        "min_active_days": min_active,
        "min_trades": min_trades,
        "fold_adequacy_status": "low_activity_not_fully_interpretable" if below else "interpretable",
        "fold_result_interpretable": not below,
        "fold_below_min_activity": below,
        "signal_evidence_status_forced_to_no_signal": False,
        "tradability_blocked_by_low_activity": bool(below),
    }


def build_fold_design_decision_table(policy: Mapping[str, Any]) -> pd.DataFrame:
    rows = []
    for fold_view, spec in policy["standard_fold_views"].items():
        rows.append(
            {
                "fold_view": fold_view,
                "role": spec["role"],
                "required_in_future_reports": bool(spec["required_in_future_reports"]),
                "diagnostic_companion_only": bool(spec["diagnostic_companion_only"]),
                "official_promotion_gate": bool(spec["official_promotion_gate"]),
                "adequacy_warning_required": bool(spec["adequacy_warning_required"]),
                "reporting_rule": spec["description"],
            }
        )
    rows.append(
        {
            "fold_view": "rolling_3_month_test_folds",
            "role": "excluded_from_standard_required_views",
            "required_in_future_reports": False,
            "diagnostic_companion_only": True,
            "official_promotion_gate": False,
            "adequacy_warning_required": True,
            "reporting_rule": "Do not make rolling 3-month folds official promotion gates; use only if explicitly requested as extra diagnostics.",
        }
    )
    return pd.DataFrame(rows).sort_values("fold_view").reset_index(drop=True)


def build_module_fold_adequacy_rules(policy: Mapping[str, Any]) -> pd.DataFrame:
    defaults = policy["fold_adequacy_defaults"]
    rows = [
        {
            "validation_level": "module_level_validation",
            "rule": "minimum_active_days_per_fold",
            "configurable_default": defaults["module_fold_min_active_days"],
            "diagnostic_only": True,
            "effect": "fold result is low-activity / not fully interpretable below this value",
            "converts_to_no_signal": False,
            "can_block_tradability": True,
        },
        {
            "validation_level": "module_level_validation",
            "rule": "minimum_trades_per_fold",
            "configurable_default": defaults["module_fold_min_trades"],
            "diagnostic_only": True,
            "effect": "fold result is low-activity / not fully interpretable below this value",
            "converts_to_no_signal": False,
            "can_block_tradability": True,
        },
        {
            "validation_level": "module_level_validation",
            "rule": "report_folds_below_min_activity",
            "configurable_default": True,
            "diagnostic_only": True,
            "effect": "report active days, trades, adequacy status, and count of sparse folds before interpreting pass/fail",
            "converts_to_no_signal": False,
            "can_block_tradability": True,
        },
    ]
    return pd.DataFrame(rows)


def build_playbook_fold_reporting_rules(policy: Mapping[str, Any]) -> pd.DataFrame:
    defaults = policy["fold_adequacy_defaults"]
    rows = [
        {
            "validation_level": "playbook_level_validation",
            "reporting_rule": "minimum_active_days_per_fold",
            "configurable_default": defaults["playbook_fold_min_active_days"],
            "required_metric": "active_days_per_fold",
        },
        {
            "validation_level": "playbook_level_validation",
            "reporting_rule": "minimum_trades_per_fold",
            "configurable_default": defaults["playbook_fold_min_trades"],
            "required_metric": "trades_per_fold",
        },
        {
            "validation_level": "playbook_level_validation",
            "reporting_rule": "fold_stability_and_concentration",
            "configurable_default": "required",
            "required_metric": "fold stability, concentration, drawdown, active days, module contribution",
        },
        {
            "validation_level": "paper_review_validation",
            "reporting_rule": "official_gates_unchanged",
            "configurable_default": False,
            "required_metric": "official_gates_changed=false and paper_trading_approved=false",
        },
    ]
    return pd.DataFrame(rows)


def render_standardized_fold_policy_report(
    *,
    policy: Mapping[str, Any],
    decision_table: pd.DataFrame,
    module_rules: pd.DataFrame,
    playbook_rules: pd.DataFrame,
    recommendation: Mapping[str, Any],
) -> str:
    lines = [
        "# Validation Framework D — Standardize Playbook Folds",
        "",
        RESEARCH_ONLY_GUARDRAIL,
        "",
        "This is an additive validation-policy artifact only. It generated no new signals, ran no strategy searches, changed no candidate results, loosened no official gates, promoted no candidates, and approved no paper or live trading.",
        "",
        "## Official gates and approvals",
        "",
        "- official_gates_changed: `false`",
        "- paper_trading_approved: `false`",
        "- live_trading_approved: `false`",
        "- No official paper-review threshold is loosened.",
        "- Alternative fold views are diagnostic only unless explicitly promoted later by human review.",
        "",
        "## Validation levels",
        "",
    ]
    for level, spec in policy["validation_levels"].items():
        lines.extend([f"### {level}", ""])
        for key, value in spec.items():
            lines.append(f"- {key}: `{value}`")
        lines.append("")
    lines.extend([
        "## Standard fold views",
        "",
        markdown_table(decision_table),
        "",
        "Quarterly folds and rolling 3-month folds are not official promotion gates.",
        "",
        "## Rare-module fold adequacy rules",
        "",
        markdown_table(module_rules),
        "",
        "Low activity alone does not mean no signal. Low activity can still block tradability. Future reports should state when a fold result is low-activity / not fully interpretable.",
        "",
        "## Playbook fold reporting rules",
        "",
        markdown_table(playbook_rules),
        "",
        "## Future candidate output fields",
        "",
        ", ".join(policy["future_candidate_output_fields"]),
        "",
        "## Required reporting language",
        "",
    ])
    lines.extend(f"- {phrase}" for phrase in policy["reporting_language"])
    lines.extend([
        "",
        "## Audit C evidence used",
        "",
    ])
    for key, value in policy["audit_c_evidence_summary"].items():
        lines.append(f"- {key}: `{value}`")
    lines.extend([
        "",
        "## Recommended next action",
        "",
        f"- next_action: `{recommendation['next_action']}`",
        f"- rationale: {recommendation['rationale']}",
        f"- official_gates_changed: `{str(recommendation['official_gates_changed']).lower()}`",
        f"- paper_trading_approved: `{str(recommendation['paper_trading_approved']).lower()}`",
        f"- live_trading_approved: `{str(recommendation['live_trading_approved']).lower()}`",
        "",
    ])
    return "\n".join(lines)


def markdown_table(df: pd.DataFrame) -> str:
    if df.empty:
        return "_No rows._"
    rows = df.copy()
    rows = rows.fillna("")
    columns = [str(c) for c in rows.columns]
    out = ["| " + " | ".join(columns) + " |", "| " + " | ".join(["---"] * len(columns)) + " |"]
    for _, row in rows.iterrows():
        out.append("| " + " | ".join(str(row[c]).replace("\n", " ") for c in rows.columns) + " |")
    return "\n".join(out)


def build_validation_framework_d_artifacts(project_root: Path) -> dict[str, Any]:
    data = load_validation_framework_d_inputs(project_root)
    policy = build_playbook_validation_policy(data)
    schema = build_policy_schema(policy)
    decision_table = build_fold_design_decision_table(policy)
    module_rules = build_module_fold_adequacy_rules(policy)
    playbook_rules = build_playbook_fold_reporting_rules(policy)
    recommendation = deepcopy(NEXT_ACTION_RECOMMENDATION)
    report = render_standardized_fold_policy_report(
        policy=policy,
        decision_table=decision_table,
        module_rules=module_rules,
        playbook_rules=playbook_rules,
        recommendation=recommendation,
    )
    return {
        "inputs_loaded": sorted(k for k in data.keys() if k != "input_paths"),
        "policy": policy,
        "schema": schema,
        "decision_table": decision_table,
        "module_rules": module_rules,
        "playbook_rules": playbook_rules,
        "recommendation": recommendation,
        "report": report,
    }
