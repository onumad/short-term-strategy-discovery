"""Rare-module validation track review for Phase 16A.

This module builds policy/review artifacts from existing Phase 16A and
Validation Framework D outputs only. It does not generate strategy signals, run
searches, mutate candidate results or registries, change official gates, promote
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

REVIEW_LABELS = (
    "phase16a_positive_uncorrelated_research_signal",
    "phase16a_watchlist_needs_more_history",
)

STANDARD_FOLD_VIEWS = (
    "existing_project_folds",
    "half_year_folds",
    "rolling_6_month_test_folds",
    "quarterly_folds",
)

REQUIRED_OUTPUT_FILES = {
    "playbook_validation_policy": "playbook_validation_policy.json",
    "playbook_fold_policy_schema": "playbook_fold_policy_schema.json",
    "validation_framework_d_module_fold_adequacy_rules": "validation_framework_d_module_fold_adequacy_rules.csv",
    "validation_framework_d_playbook_fold_reporting_rules": "validation_framework_d_playbook_fold_reporting_rules.csv",
    "validation_framework_d_next_action_recommendation": "validation_framework_d_next_action_recommendation.json",
    "phase16a_candidate_results": "phase16a_candidate_results.csv",
    "phase16a_trade_logs": "phase16a_trade_logs.csv",
    "phase16a_daily_pnl": "phase16a_daily_pnl.csv",
    "phase16a_walk_forward_folds": "phase16a_walk_forward_folds.csv",
    "phase16a_concentration_diagnostics": "phase16a_concentration_diagnostics.csv",
    "phase16a_fold_view_summary": "phase16a_fold_view_summary.csv",
    "phase16a_module_fold_adequacy": "phase16a_module_fold_adequacy.csv",
    "phase16a_correlation_to_registry": "phase16a_correlation_to_registry.csv",
    "phase16a_correlation_to_playbook": "phase16a_correlation_to_playbook.csv",
    "phase16a_gap_coverage_summary": "phase16a_gap_coverage_summary.csv",
    "phase16a_next_action_recommendation": "phase16a_next_action_recommendation.json",
    "research_signal_registry_csv": "research_signal_registry.csv",
    "research_signal_registry_json": "research_signal_registry.json",
    "playbook_module_registry_csv": "playbook_module_registry.csv",
    "playbook_module_registry_json": "playbook_module_registry.json",
}

PHASE16A_REPORT_FILE = "phase16a_high_vol_mixed_regime_scout_report.md"

RARE_MODULE_CLASSES = {
    "rare_signal_insufficient_evidence": "Sparse module with insufficient positive validation/stress/holdout evidence for rare-track registration.",
    "rare_positive_research_signal": "Sparse module with positive stress, validation, holdout, and walk-forward stress evidence.",
    "rare_uncorrelated_diversifier_candidate": "Rare positive research signal with low average correlation to the existing registry.",
    "rare_priority_for_more_data": "Rare positive or borderline signal that should be prioritized for more history before any tradability review.",
    "rare_rejected_negative_or_unstable": "Rare or watchlist-labeled module blocked by negative/non-positive validation, holdout, stress, high correlation, or unstable fold evidence.",
}

RARE_MODULE_MINIMUM_REQUIREMENTS = {
    "stress_pnl_gt_0": True,
    "validation_pnl_gt_0": True,
    "holdout_pnl_gt_0": True,
    "walk_forward_stress_pnl_gt_0": True,
    "average_correlation_to_registry_lte": 0.35,
    "paper_trading_approved": False,
}

POLICY = {
    "policy_name": "rare_module_validation_track_phase16a_case_study",
    "research_only_guardrail": RESEARCH_ONLY_GUARDRAIL,
    "official_gates_changed": False,
    "paper_trading_approved": False,
    "live_trading_approved": False,
    "new_strategy_signals_generated": False,
    "strategy_searches_run": False,
    "candidate_results_changed": False,
    "candidates_promoted": False,
    "rare_module_track_enabled": True,
    "rare_module_classes": deepcopy(RARE_MODULE_CLASSES),
    "rare_module_minimum_requirements": deepcopy(RARE_MODULE_MINIMUM_REQUIREMENTS),
    "rare_module_registry_allowed_statuses": [
        "rare_setup_research_signal",
        "rare_setup_diversifier",
        "priority_for_more_data",
    ],
    "rare_module_blocked_statuses": [
        "watchlist_or_paper_review_from_rare_positive_evidence_only",
        "paper_trading_approved",
        "official_gate_promotion",
        "live_trading_approved",
        "broker_or_order_routing_enabled",
    ],
    "fold_adequacy_interpretation": {
        "low_activity_status": "low_activity_not_fully_interpretable",
        "low_activity_alone_means_no_signal": False,
        "low_activity_blocks_tradability": True,
        "alternative_fold_views_are_diagnostic_only": True,
        "required_fold_views": list(STANDARD_FOLD_VIEWS),
    },
    "watchlist_label_hygiene_rules": {
        "do_not_allow_registry_watchlist_if_zero_or_near_zero_trades": True,
        "near_zero_trades_threshold_lte": 5,
        "do_not_allow_registry_watchlist_if_validation_pnl_lte_0": True,
        "do_not_allow_registry_watchlist_if_holdout_pnl_lte_0": True,
        "do_not_allow_registry_watchlist_if_walk_forward_stress_pnl_lte_0": True,
        "do_not_allow_registry_watchlist_if_max_correlation_to_registry_gt": 0.35,
        "do_not_allow_registry_watchlist_if_fold_adequacy_low_activity": True,
        "allowed_outcomes": [
            "not_registered",
            "registered_only_as_rare_setup_research_signal_if_rare_rules_pass",
            "parked_as_weak_or_no_signal",
        ],
    },
    "future_phase_reporting_requirements": [
        "report rare_module_class separately from phase label",
        "report fold_adequacy_status and per-fold activity before interpreting fold pass/fail",
        "report signal_evidence_status separately from tradability_status",
        "report average and max correlation to registry and playbook",
        "report gap_days_covered and incremental_gap_days_covered",
        "state that rare positive evidence alone cannot create watchlist, paper-review, or paper-trading approval",
        "keep official_gates_changed=false and paper_trading_approved=false unless explicit later human review changes scope",
    ],
}

CANDIDATE_REVIEW_COLUMNS = [
    "candidate_id",
    "label",
    "net_pnl",
    "stress_pnl",
    "validation_pnl",
    "holdout_pnl",
    "walk_forward_stress_pnl",
    "trades",
    "active_days",
    "existing_project_folds_adequacy",
    "half_year_folds_adequacy",
    "rolling_6_month_test_folds_adequacy",
    "quarterly_folds_adequacy",
    "average_correlation_to_registry",
    "max_correlation_to_registry",
    "average_correlation_to_playbook",
    "max_correlation_to_playbook",
    "gap_days_covered",
    "incremental_gap_days_covered",
    "fold_adequacy_status",
    "signal_evidence_status",
    "tradability_status",
    "recommended_research_track",
    "recommended_portfolio_role",
    "rare_module_class",
    "watchlist_hygiene_status",
    "registration_decision",
]


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_jsonable(payload), indent=2, sort_keys=False), encoding="utf-8")


def load_rare_module_validation_inputs(project_root: Path) -> dict[str, Any]:
    outputs = project_root / "outputs"
    reports = project_root / "reports"
    required_paths = {name: outputs / filename for name, filename in REQUIRED_OUTPUT_FILES.items()}
    required_paths["phase16a_report"] = reports / PHASE16A_REPORT_FILE
    missing = [str(path) for path in required_paths.values() if not path.exists()]
    if missing:
        raise FileNotFoundError(f"Missing rare-module validation input(s): {missing}")

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


def reviewed_phase16a_candidates(candidate_results: pd.DataFrame) -> pd.DataFrame:
    reviewed = candidate_results[candidate_results["phase16a_label"].isin(REVIEW_LABELS)].copy()
    return reviewed.sort_values(["phase16a_rank", "candidate_id"]).reset_index(drop=True)


def phase16a_watchlist_rows(candidate_results: pd.DataFrame) -> pd.DataFrame:
    return candidate_results[candidate_results["phase16a_label"].eq("phase16a_watchlist_needs_more_history")].copy()


def identify_phase16a_positive_uncorrelated_candidates(candidate_results: pd.DataFrame) -> pd.DataFrame:
    return candidate_results[candidate_results["phase16a_label"].eq("phase16a_positive_uncorrelated_research_signal")].copy()


def passes_rare_module_registration_rules(row: Mapping[str, Any]) -> bool:
    return (
        float(row.get("stress_pnl", 0.0)) > 0.0
        and float(row.get("validation_pnl", 0.0)) > 0.0
        and float(row.get("holdout_pnl", 0.0)) > 0.0
        and float(row.get("walk_forward_stress_pnl", 0.0)) > 0.0
        and float(row.get("average_correlation_to_registry", 1.0)) <= float(RARE_MODULE_MINIMUM_REQUIREMENTS["average_correlation_to_registry_lte"])
        and not bool(row.get("paper_trading_approved", False))
    )


def classify_rare_module(row: Mapping[str, Any]) -> str:
    if passes_rare_module_registration_rules(row):
        return "rare_uncorrelated_diversifier_candidate"
    if (
        float(row.get("stress_pnl", 0.0)) > 0.0
        and float(row.get("validation_pnl", 0.0)) > 0.0
        and float(row.get("holdout_pnl", 0.0)) > 0.0
    ):
        return "rare_positive_research_signal"
    if (
        float(row.get("stress_pnl", 0.0)) <= 0.0
        or float(row.get("validation_pnl", 0.0)) <= 0.0
        or float(row.get("holdout_pnl", 0.0)) <= 0.0
        or float(row.get("walk_forward_stress_pnl", 0.0)) <= 0.0
        or float(row.get("max_correlation_to_registry", 0.0)) > 0.35
    ):
        return "rare_rejected_negative_or_unstable"
    return "rare_signal_insufficient_evidence"


def watchlist_hygiene_status(row: Mapping[str, Any]) -> str:
    if str(row.get("phase16a_label", "")) != "phase16a_watchlist_needs_more_history":
        return "not_watchlist_label"
    blockers = []
    if int(row.get("trades", 0)) <= int(POLICY["watchlist_label_hygiene_rules"]["near_zero_trades_threshold_lte"]):
        blockers.append("zero_or_near_zero_trades")
    if float(row.get("validation_pnl", 0.0)) <= 0.0:
        blockers.append("nonpositive_validation")
    if float(row.get("holdout_pnl", 0.0)) <= 0.0:
        blockers.append("nonpositive_holdout")
    if float(row.get("walk_forward_stress_pnl", 0.0)) <= 0.0:
        blockers.append("nonpositive_walk_forward_stress")
    if float(row.get("max_correlation_to_registry", 0.0)) > float(POLICY["watchlist_label_hygiene_rules"]["do_not_allow_registry_watchlist_if_max_correlation_to_registry_gt"]):
        blockers.append("high_max_registry_correlation")
    if str(row.get("fold_adequacy_status", "")) == "low_activity_not_fully_interpretable":
        blockers.append("insufficient_fold_adequacy")
    if blockers:
        return "blocked_from_registry_watchlist: " + "; ".join(blockers)
    return "watchlist_label_hygiene_ok_but_not_paper_review"


def registration_decision(row: Mapping[str, Any]) -> str:
    if passes_rare_module_registration_rules(row):
        if str(row.get("phase16a_label", "")) == "phase16a_positive_uncorrelated_research_signal":
            return "add_to_registry_as_rare_setup_diversifier"
        return "add_to_registry_as_priority_for_more_data"
    if watchlist_hygiene_status(row).startswith("blocked_from_registry_watchlist"):
        return "reject_from_registry"
    klass = classify_rare_module(row)
    if klass == "rare_rejected_negative_or_unstable":
        return "reject_from_registry"
    return "not_registered_yet_due_to_sparse_evidence"


def recommended_research_track(row: Mapping[str, Any]) -> str:
    if passes_rare_module_registration_rules(row):
        return "rare_setup_research_signal"
    if classify_rare_module(row) == "rare_rejected_negative_or_unstable":
        return "parked_weak_or_no_signal"
    return "more_history_needed_before_registration"


def recommended_portfolio_role(row: Mapping[str, Any]) -> str:
    if passes_rare_module_registration_rules(row):
        return "diversifier_module"
    if classify_rare_module(row) == "rare_positive_research_signal":
        return "rare_setup_module"
    return "none"


def fold_adequacy_by_candidate(module_fold_adequacy: pd.DataFrame) -> pd.DataFrame:
    grouped = (
        module_fold_adequacy.groupby(["candidate_id", "fold_view"], dropna=False)
        .agg(
            folds=("fold", "count"),
            total_active_days=("active_days", "sum"),
            total_trades=("trades", "sum"),
            folds_below_min_activity=("below_min_activity", "sum"),
            interpretable_folds=("fold_result_interpretable", "sum"),
        )
        .reset_index()
    )
    grouped["adequacy_status"] = grouped.apply(_format_fold_adequacy, axis=1)
    return grouped


def build_adequacy_summary(reviewed: pd.DataFrame, module_fold_adequacy: pd.DataFrame) -> pd.DataFrame:
    candidate_ids = set(reviewed["candidate_id"].astype(str))
    summary = fold_adequacy_by_candidate(module_fold_adequacy)
    summary = summary[summary["candidate_id"].astype(str).isin(candidate_ids)].copy()
    return summary.sort_values(["candidate_id", "fold_view"]).reset_index(drop=True)


def build_candidate_review(data: Mapping[str, Any]) -> pd.DataFrame:
    reviewed = reviewed_phase16a_candidates(data["phase16a_candidate_results"])
    adequacy = fold_adequacy_by_candidate(data["phase16a_module_fold_adequacy"])
    adequacy_lookup = {
        (str(row.candidate_id), str(row.fold_view)): str(row.adequacy_status)
        for row in adequacy.itertuples(index=False)
    }
    rows = []
    for _, row in reviewed.iterrows():
        item = row.to_dict()
        out = {
            "candidate_id": item["candidate_id"],
            "label": item["phase16a_label"],
            "net_pnl": _round_float(item.get("net_pnl")),
            "stress_pnl": _round_float(item.get("stress_pnl")),
            "validation_pnl": _round_float(item.get("validation_pnl")),
            "holdout_pnl": _round_float(item.get("holdout_pnl")),
            "walk_forward_stress_pnl": _round_float(item.get("walk_forward_stress_pnl")),
            "trades": int(item.get("trades", 0)),
            "active_days": int(item.get("active_days", 0)),
            "average_correlation_to_registry": _round_float(item.get("average_correlation_to_registry"), 6),
            "max_correlation_to_registry": _round_float(item.get("max_correlation_to_registry"), 6),
            "average_correlation_to_playbook": _round_float(item.get("average_correlation_to_playbook"), 6),
            "max_correlation_to_playbook": _round_float(item.get("max_correlation_to_playbook"), 6),
            "gap_days_covered": int(item.get("gap_days_covered", 0)),
            "incremental_gap_days_covered": int(item.get("incremental_gap_days_covered", 0)),
            "fold_adequacy_status": item.get("fold_adequacy_status", ""),
            "signal_evidence_status": item.get("signal_evidence_status", ""),
            "tradability_status": "not_tradable_low_activity" if passes_rare_module_registration_rules(item) else item.get("tradability_status", ""),
            "recommended_research_track": recommended_research_track(item),
            "recommended_portfolio_role": recommended_portfolio_role(item),
            "rare_module_class": classify_rare_module(item),
            "watchlist_hygiene_status": watchlist_hygiene_status(item),
            "registration_decision": registration_decision(item),
        }
        for view in STANDARD_FOLD_VIEWS:
            out[f"{view}_adequacy"] = adequacy_lookup.get((str(item["candidate_id"]), view), "missing")
        rows.append(out)
    return pd.DataFrame(rows, columns=CANDIDATE_REVIEW_COLUMNS)


def build_registration_decisions(candidate_review: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "candidate_id",
        "label",
        "rare_module_class",
        "fold_adequacy_status",
        "signal_evidence_status",
        "tradability_status",
        "recommended_research_track",
        "recommended_portfolio_role",
        "watchlist_hygiene_status",
        "registration_decision",
    ]
    return candidate_review[columns].copy()


def build_policy() -> dict[str, Any]:
    return deepcopy(POLICY)


def build_next_action_recommendation(candidate_review: pd.DataFrame, policy: Mapping[str, Any]) -> dict[str, Any]:
    positive = candidate_review[candidate_review["label"].eq("phase16a_positive_uncorrelated_research_signal")]
    positive_rare_passes = positive[positive["registration_decision"].isin(["add_to_registry_as_rare_setup_diversifier", "add_to_registry_as_priority_for_more_data"])]
    watchlist = candidate_review[candidate_review["label"].eq("phase16a_watchlist_needs_more_history")]
    misleading_watchlist = watchlist[watchlist["watchlist_hygiene_status"].str.startswith("blocked_from_registry_watchlist", na=False)]

    if len(positive_rare_passes) > 0:
        primary = "research_signal_registry_e_add_phase16a_rare_modules"
        rationale = "Phase 16A top positive uncorrelated candidates pass rare-module registration rules, but remain research-only and not tradable due to low activity."
    else:
        primary = "collect_more_data_for_phase16a_or_skip_registry"
        rationale = "Phase 16A top candidates are too sparse or unstable even for rare-module registration."

    recommended_actions = [primary]
    if len(misleading_watchlist) > 0:
        recommended_actions.append("phase16a_label_hygiene_patch")
    recommended_actions.append("playbook_framework_e_rare_module_policy_integration")

    return {
        "next_action": primary,
        "recommended_actions": recommended_actions,
        "rationale": rationale,
        "phase16a_positive_uncorrelated_candidates_reviewed": int(len(positive)),
        "phase16a_positive_uncorrelated_candidates_passing_rare_rules": int(len(positive_rare_passes)),
        "phase16a_watchlist_rows_reviewed": int(len(watchlist)),
        "phase16a_watchlist_rows_blocked_by_hygiene": int(len(misleading_watchlist)),
        "official_gates_changed": False,
        "paper_trading_approved": False,
        "live_trading_approved": False,
        "new_strategy_signals_generated": False,
        "strategy_searches_run": False,
        "candidate_results_changed": False,
        "registries_mutated": False,
        "rare_module_track_enabled": bool(policy["rare_module_track_enabled"]),
    }


def render_report(
    *,
    candidate_review: pd.DataFrame,
    adequacy_summary: pd.DataFrame,
    registration_decisions: pd.DataFrame,
    policy: Mapping[str, Any],
    recommendation: Mapping[str, Any],
) -> str:
    label_counts = candidate_review["label"].value_counts().sort_index().to_dict()
    decision_counts = registration_decisions["registration_decision"].value_counts().sort_index().to_dict()
    watchlist_findings = candidate_review[candidate_review["label"].eq("phase16a_watchlist_needs_more_history")][
        ["candidate_id", "watchlist_hygiene_status", "registration_decision"]
    ]
    lines = [
        "# Rare Module Validation Track Review — Phase 16A Case Study",
        "",
        RESEARCH_ONLY_GUARDRAIL,
        "",
        "This is a validation/registration policy review only. It generated no new signals, ran no strategy searches, changed no existing candidate results, mutated no registries, changed no official promotion gates, promoted no candidates, and approved no paper or live trading.",
        "",
        "## Guardrails",
        "",
        "- official_gates_changed: `false`",
        "- paper_trading_approved: `false`",
        "- live_trading_approved: `false`",
        "- new_strategy_signals_generated: `false`",
        "- strategy_searches_run: `false`",
        "- candidate_results_changed: `false`",
        "- registries_mutated: `false`",
        "",
        "## Phase 16A candidates reviewed",
        "",
        f"- label_counts: `{label_counts}`",
        "",
        markdown_table(candidate_review),
        "",
        "## Fold adequacy summary",
        "",
        markdown_table(adequacy_summary),
        "",
        "## Rare-module validation classes",
        "",
    ]
    for name, description in policy["rare_module_classes"].items():
        lines.append(f"- {name}: {description}")
    lines.extend([
        "",
        "## Policy decisions",
        "",
        "- Rare modules may enter registry only as research-track rare setup/diversifier records when stress, validation, holdout, walk-forward stress, average-correlation, and no-paper requirements pass.",
        "- Rare positive evidence alone cannot create watchlist, paper-review, paper-trading approval, or official gate promotion.",
        "- Registered rare modules must use research_track=`rare_setup_research_signal`, tradability_status=`not_tradable_low_activity`, fold_adequacy_status=`low_activity_not_fully_interpretable`, and portfolio_role=`diversifier_module` or `rare_setup_module`.",
        "",
        "## Watchlist label hygiene findings",
        "",
        markdown_table(watchlist_findings),
        "",
        "## Registration decisions",
        "",
        f"- decision_counts: `{decision_counts}`",
        "",
        markdown_table(registration_decisions),
        "",
        "## Recommended next action",
        "",
        f"- next_action: `{recommendation['next_action']}`",
        f"- recommended_actions: `{recommendation['recommended_actions']}`",
        f"- rationale: {recommendation['rationale']}",
        f"- official_gates_changed: `{str(recommendation['official_gates_changed']).lower()}`",
        f"- paper_trading_approved: `{str(recommendation['paper_trading_approved']).lower()}`",
        f"- live_trading_approved: `{str(recommendation['live_trading_approved']).lower()}`",
        "",
    ])
    return "\n".join(lines)


def build_rare_module_validation_track_artifacts(project_root: Path) -> dict[str, Any]:
    data = load_rare_module_validation_inputs(project_root)
    policy = build_policy()
    candidate_review = build_candidate_review(data)
    adequacy_summary = build_adequacy_summary(reviewed_phase16a_candidates(data["phase16a_candidate_results"]), data["phase16a_module_fold_adequacy"])
    registration_decisions = build_registration_decisions(candidate_review)
    recommendation = build_next_action_recommendation(candidate_review, policy)
    report = render_report(
        candidate_review=candidate_review,
        adequacy_summary=adequacy_summary,
        registration_decisions=registration_decisions,
        policy=policy,
        recommendation=recommendation,
    )
    return {
        "inputs_loaded": sorted(k for k in data.keys() if k != "input_paths"),
        "policy": policy,
        "candidate_review": candidate_review,
        "adequacy_summary": adequacy_summary,
        "registration_decisions": registration_decisions,
        "recommendation": recommendation,
        "report": report,
    }


def markdown_table(df: pd.DataFrame) -> str:
    if df.empty:
        return "_No rows._"
    rows = df.copy().fillna("")
    columns = [str(c) for c in rows.columns]
    out = ["| " + " | ".join(columns) + " |", "| " + " | ".join(["---"] * len(columns)) + " |"]
    for _, row in rows.iterrows():
        out.append("| " + " | ".join(str(row[c]).replace("\n", " ") for c in rows.columns) + " |")
    return "\n".join(out)


def _format_fold_adequacy(row: pd.Series) -> str:
    folds = int(row["folds"])
    below = int(row["folds_below_min_activity"])
    interpretable = int(row["interpretable_folds"])
    if below == 0:
        return f"interpretable ({interpretable}/{folds} folds interpretable)"
    return f"low_activity_not_fully_interpretable ({below}/{folds} folds below min activity; {interpretable}/{folds} interpretable)"


def _round_float(value: Any, digits: int = 2) -> float:
    if pd.isna(value):
        return 0.0
    return round(float(value), digits)


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
