"""Playbook evaluation config, labels, and reporting alignment.

This module is additive framework support only. It does not generate signals,
modify historical labels, or change official promotion gates.
"""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any, Mapping

import pandas as pd

MODULE_ACTIVITY_GATE = {
    "regular_practice_module": {
        "description": "Module intended to contribute repeatable practice opportunities.",
        "minimum_active_days_guidance": 40,
        "low_activity_blocks_tradability": True,
        "low_activity_implies_no_signal": False,
    },
    "rare_setup_module": {
        "description": "Specialized module that may be infrequent but can still carry signal evidence.",
        "minimum_active_days_guidance": None,
        "low_activity_blocks_tradability": True,
        "low_activity_implies_no_signal": False,
    },
    "parked_module": {
        "description": "Module retained for research evidence or future data, not practice readiness.",
        "minimum_active_days_guidance": None,
        "low_activity_blocks_tradability": True,
        "low_activity_implies_no_signal": False,
    },
}

PLAYBOOK_ACTIVITY_GATE = {
    "target_total_active_days": 70,
    "target_total_opportunities_per_day": "regular combined opportunity; exact threshold is review-context dependent",
    "max_same_session_trades": "diagnostic cap defined per playbook audit",
    "max_module_overlap": "prefer lower overlap; measure before review packet",
}

RARE_SETUP_ACTIVITY_GATE = {
    "low_activity_does_not_imply_no_signal": True,
    "must_still_evaluate": [
        "stress_pnl",
        "validation_pnl",
        "holdout_pnl",
        "concentration",
        "fold_stability",
        "portfolio_contribution",
    ],
    "tradability_blocker_when_low_activity": "not_tradable_low_activity",
}

SIGNAL_SCORE_COMPONENTS = [
    "stress_pnl",
    "validation_pnl",
    "holdout_pnl",
    "walk_forward_stress_pnl",
    "mfe_mae_quality",
    "outlier_robustness",
    "plain_english_logic",
]

TRADABILITY_SCORE_COMPONENTS = [
    "active_days",
    "trades_per_active_day",
    "fold_stability",
    "concentration",
    "drawdown",
    "official_gate_passes",
]

PORTFOLIO_SCORE_COMPONENTS = [
    "incremental_active_days",
    "lower_correlation_to_existing_modules",
    "reduced_drawdown",
    "reduced_concentration",
    "improved_fold_stability",
    "reduced_overlap_with_existing_modules",
]

FUTURE_CANDIDATE_OUTPUT_FIELDS = [
    "module_id",
    "signal_evidence_status",
    "tradability_status",
    "research_track",
    "market_condition",
    "module_family",
    "portfolio_role",
    "plain_english_rule",
    "official_gates_passed",
    "paper_trading_approved",
    "portfolio_contribution_status",
]

REPORTING_GUIDELINES = {
    "preferred_language": [
        "positive research signal but not tradable",
        "rare setup research signal",
        "tradability failed due to low activity",
        "blocked by concentration/fold stability",
        "no paper trading approved",
    ],
    "discouraged_language": [
        "failed badly when signal evidence is positive",
        "no signal solely because activity is low",
        "paper-trading ready without official gate pass",
    ],
    "required_guardrail_sentence": "Research/simulation only. No live trading, broker adapters, order routing, webhooks, credential storage, automated execution, or LLM-driven trade decisions.",
}

OFFICIAL_PROMOTION_GATES_REFERENCE = {
    "changed_by_playbook_framework_c": False,
    "paper_trading_approved_default": False,
    "review_packet_only_when_passed": True,
    "gates": {
        "net_pnl": "> 0",
        "stress_pnl": "> 0",
        "validation_pnl": "> 0 when computable",
        "holdout_pnl": "> 0 when computable",
        "walk_forward_stress_pnl": "> 0 when computable",
        "positive_wf_test_folds_pct": ">= 0.90 when computable",
        "best_day_concentration": "<= 0.15",
        "best_trade_concentration": "<= 0.08",
        "activity": "adequate for review context; low activity remains a tradability blocker",
        "plain_english_rule": "required",
    },
}

NEXT_ACTION_RULES = [
    {
        "condition": "positive_but_rare",
        "next_action": "add_to_module_registry",
        "paper_trading_approved": False,
    },
    {
        "condition": "positive_and_uncorrelated",
        "next_action": "run_portfolio_audit",
        "paper_trading_approved": False,
    },
    {
        "condition": "positive_but_concentrated",
        "next_action": "park_or_seek_diversifier",
        "paper_trading_approved": False,
    },
    {
        "condition": "negative_or_no_signal",
        "next_action": "reject",
        "paper_trading_approved": False,
    },
    {
        "condition": "portfolio_improves_but_still_fails",
        "next_action": "search_new_uncorrelated_family",
        "paper_trading_approved": False,
    },
    {
        "condition": "official_gates_pass",
        "next_action": "review_packet_only",
        "paper_trading_approved": False,
    },
]

RECOMMENDATION = {
    "next_action": "phase13a_final_acceptance_then_module_registry_update",
    "rationale": "Playbook evaluation config now separates module signal evidence, tradability, and portfolio contribution while preserving official gates.",
    "official_gates_changed": False,
    "paper_trading_approved": False,
}


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_playbook_taxonomy(project_root: Path) -> dict[str, Any]:
    return load_json(project_root / "outputs" / "playbook_module_taxonomy.json")


def build_playbook_evaluation_config(taxonomy: Mapping[str, Any]) -> dict[str, Any]:
    """Build additive future-evaluation config without changing gates."""
    return {
        "objective": "diversified specialized deterministic MNQ intraday playbook",
        "module_activity_gate": deepcopy(MODULE_ACTIVITY_GATE),
        "playbook_activity_gate": deepcopy(PLAYBOOK_ACTIVITY_GATE),
        "rare_setup_activity_gate": deepcopy(RARE_SETUP_ACTIVITY_GATE),
        "signal_score_components": list(SIGNAL_SCORE_COMPONENTS),
        "tradability_score_components": list(TRADABILITY_SCORE_COMPONENTS),
        "portfolio_score_components": list(PORTFOLIO_SCORE_COMPONENTS),
        "future_candidate_output_fields": list(FUTURE_CANDIDATE_OUTPUT_FIELDS),
        "official_promotion_gates_reference": deepcopy(OFFICIAL_PROMOTION_GATES_REFERENCE),
        "taxonomy": deepcopy(dict(taxonomy)),
    }


def build_labeling_rules(taxonomy: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "signal_evidence_status": list(taxonomy["signal_evidence_status"]),
        "tradability_status": list(taxonomy["tradability_status"]),
        "research_track": list(taxonomy["research_track"]),
        "next_action_rules": deepcopy(NEXT_ACTION_RULES),
        "paper_trading_approved_default": False,
        "low_activity_rule": {
            "signal_evidence_status_forced_to_no_signal": False,
            "tradability_status_when_low_activity": "not_tradable_low_activity",
        },
        "official_gates_changed": False,
    }


def build_reporting_guidelines() -> dict[str, Any]:
    return deepcopy(REPORTING_GUIDELINES)


def default_future_candidate_record(module_id: str, **overrides: Any) -> dict[str, Any]:
    record = {field: None for field in FUTURE_CANDIDATE_OUTPUT_FIELDS}
    record.update(
        {
            "module_id": module_id,
            "official_gates_passed": False,
            "paper_trading_approved": False,
        }
    )
    record.update(overrides)
    if record.get("paper_trading_approved") is None:
        record["paper_trading_approved"] = False
    return record


def classify_module_activity(
    *,
    signal_evidence_status: str,
    active_days: int,
    module_activity_type: str,
) -> dict[str, str]:
    """Classify activity while keeping signal evidence separate from tradability."""
    if module_activity_type not in MODULE_ACTIVITY_GATE:
        raise ValueError(f"unknown module_activity_type: {module_activity_type}")
    evidence = signal_evidence_status
    tradability = "review_packet_candidate"
    research_track = "regular_practice_candidate"
    if module_activity_type == "rare_setup_module":
        research_track = "rare_setup_research_signal"
    elif module_activity_type == "parked_module":
        research_track = "parked_research_signal"
    minimum = MODULE_ACTIVITY_GATE[module_activity_type]["minimum_active_days_guidance"]
    if minimum is not None and active_days < int(minimum):
        tradability = "not_tradable_low_activity"
    if module_activity_type in {"rare_setup_module", "parked_module"} and active_days <= 0:
        tradability = "not_tradable_low_activity"
    return {
        "signal_evidence_status": evidence,
        "tradability_status": tradability,
        "research_track": research_track,
    }


def next_action_for_module(
    *,
    signal_evidence_status: str,
    research_track: str = "",
    average_correlation: float | None = None,
    tradability_status: str = "",
    portfolio_improves: bool = False,
    official_gates_passed: bool = False,
) -> str:
    if official_gates_passed:
        return "review_packet_only"
    if portfolio_improves:
        return "search_new_uncorrelated_family"
    if signal_evidence_status in {"no_signal", "weak_research_signal"}:
        return "reject"
    if tradability_status == "not_tradable_concentrated":
        return "park_or_seek_diversifier"
    if average_correlation is not None and abs(float(average_correlation)) <= 0.35:
        return "run_portfolio_audit"
    if research_track == "rare_setup_research_signal":
        return "add_to_module_registry"
    return "add_to_module_registry"


def classify_existing_registry_rows(registry: pd.DataFrame) -> pd.DataFrame:
    """Return a copy with future playbook defaults while preserving old labels."""
    rows = registry.copy(deep=True)
    rows["original_signal_evidence_status"] = rows.get("signal_evidence_status", pd.Series(dtype=object))
    rows["original_tradability_status"] = rows.get("tradability_status", pd.Series(dtype=object))
    rows["original_research_track"] = rows.get("research_track", pd.Series(dtype=object))
    rows["paper_trading_approved"] = False
    if "official_gates_passed" not in rows.columns:
        rows["official_gates_passed"] = False
    if "portfolio_contribution_status" not in rows.columns:
        rows["portfolio_contribution_status"] = "not_evaluated_in_framework_c"
    return rows


def render_alignment_report(*, registry_rows: int, config: Mapping[str, Any], recommendation: Mapping[str, Any]) -> str:
    return "\n".join(
        [
            "# Playbook Framework C — Evaluation Config, Labels, and Reporting Alignment",
            "",
            REPORTING_GUIDELINES["required_guardrail_sentence"],
            "",
            "## Purpose",
            "",
            "This additive framework aligns future phases with the diversified playbook direction. It does not generate new signals, alter historical candidate results, change official gates, promote candidates, or approve paper trading.",
            "",
            "## Config Sections Created",
            "",
            "- module_activity_gate",
            "- playbook_activity_gate",
            "- rare_setup_activity_gate",
            "- signal_score_components",
            "- tradability_score_components",
            "- portfolio_score_components",
            "- future_candidate_output_fields",
            "- official_promotion_gates_reference",
            "",
            "## Activity Gate Alignment",
            "",
            "Individual modules do not need to trade daily. Rare setup low activity does not force `signal_evidence_status` to `no_signal`; it can still force `tradability_status` to `not_tradable_low_activity`. The combined playbook remains responsible for regular opportunity.",
            "",
            "## Reporting Language",
            "",
            "Use `positive research signal but not tradable`, `rare setup research signal`, `tradability failed due to low activity`, `blocked by concentration/fold stability`, and `no paper trading approved` where appropriate.",
            "",
            "## Existing Registry Compatibility",
            "",
            f"Existing research signal registry rows classified without changing old labels: {registry_rows}.",
            "",
            "## Official Gates And Paper Trading",
            "",
            f"Official gates changed: `{str(recommendation['official_gates_changed']).lower()}`.",
            f"Paper trading approved: `{str(recommendation['paper_trading_approved']).lower()}`.",
            "",
            "## Next Recommendation",
            "",
            f"- Next action: `{recommendation['next_action']}`",
            f"- Rationale: {recommendation['rationale']}",
            "",
            "## Output Field Defaults",
            "",
            f"Future candidate output fields: {', '.join(config['future_candidate_output_fields'])}.",
            "`paper_trading_approved` defaults to `false`.",
            "",
        ]
    )


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=False), encoding="utf-8")
