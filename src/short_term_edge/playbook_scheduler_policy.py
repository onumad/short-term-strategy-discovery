"""Playbook Scheduler F rare-module scheduler exclusion policy.

This module integrates the Scheduler E finding into additive scheduler policy
artifacts only. It uses existing Scheduler E, registry, and rare-module policy
outputs; it does not generate signals, run strategy searches, alter historical
candidate results, change official gates, promote candidates, or approve paper
or live trading.
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

SCHEDULER_F_RECOMMENDATION = {
    "next_action": "phase17a_next_gap_module_scout_without_rare_scheduler_inclusion",
    "rationale": "Rare modules remain tracked as research signals but should be excluded from default scheduler construction until more evidence is available.",
    "official_gates_changed": False,
    "paper_trading_approved": False,
    "default_include_rare_modules_in_scheduler": False,
}

REQUIRED_INPUT_FILES = {
    "scheduler_e_recommendation": "playbook_scheduler_e_next_action_recommendation.json",
    "scheduler_e_policy_results": "playbook_scheduler_e_policy_results.csv",
    "scheduler_e_rare_module_impact": "playbook_scheduler_e_rare_module_impact.csv",
    "scheduler_e_rare_module_acceptance_summary": "playbook_scheduler_e_rare_module_acceptance_summary.csv",
    "research_signal_registry": "research_signal_registry.csv",
    "playbook_module_registry": "playbook_module_registry.csv",
    "rare_module_policy": "playbook_rare_module_policy.json",
    "rare_module_portfolio_audit_rules": "playbook_rare_module_portfolio_audit_rules.json",
}


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_jsonable(payload), indent=2, sort_keys=False), encoding="utf-8")


def load_playbook_scheduler_policy_inputs(project_root: Path) -> dict[str, Any]:
    outputs = project_root / "outputs"
    required_paths = {name: outputs / filename for name, filename in REQUIRED_INPUT_FILES.items()}
    required_paths["playbook_research_objective"] = project_root / "playbook_research_objective.md"

    missing = [str(path) for path in required_paths.values() if not path.exists()]
    if missing:
        raise FileNotFoundError(f"Missing Playbook Scheduler F input(s): {missing}")

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


def rare_module_mask(registry: pd.DataFrame) -> pd.Series:
    research_track = registry.get("research_track", pd.Series(index=registry.index, dtype=object)).astype(str)
    portfolio_role = registry.get("portfolio_role", pd.Series(index=registry.index, dtype=object)).astype(str)
    contribution_status = registry.get("portfolio_contribution_status", pd.Series(index=registry.index, dtype=object)).astype(str)
    return (
        research_track.eq("rare_setup_research_signal")
        | portfolio_role.eq("rare_setup_module")
        | contribution_status.str.contains("rare", case=False, na=False)
    )


def quarantine_mask(registry: pd.DataFrame) -> pd.Series:
    status = registry.get("causality_review_status", pd.Series(index=registry.index, dtype=object)).astype(str)
    scheduler_eligible = registry.get("scheduler_eligible", pd.Series(True, index=registry.index, dtype=bool))
    scheduler_eligible = scheduler_eligible.astype(str).str.strip().str.lower().isin({"true", "1", "yes"})
    return status.eq("quarantined_noncausal_definition") | ~scheduler_eligible


def rare_modules_from_registry(registry: pd.DataFrame) -> pd.DataFrame:
    return registry[rare_module_mask(registry)].copy().sort_values(["phase", "candidate_id"]).reset_index(drop=True)


def default_scheduler_universe(registry: pd.DataFrame) -> pd.DataFrame:
    """Return the historical replay universe retained for label reproducibility."""
    universe = registry[~rare_module_mask(registry) & ~quarantine_mask(registry)].copy()
    return universe.sort_values(["phase", "candidate_id"]).reset_index(drop=True)


def default_admission_universe(registry: pd.DataFrame) -> pd.DataFrame:
    """Fail-closed current admission under Conditional Specialist Framework H."""
    rows = registry.copy()
    required_columns = {
        "research_track",
        "tradability_status",
        "official_gates_passed",
        "portfolio_contribution_status",
        "activation_runtime_binding_status",
    }
    if not required_columns <= set(rows.columns):
        return rows.iloc[0:0].copy()
    regular = rows["research_track"].astype(str).eq("regular_practice_candidate")
    tradable = rows["tradability_status"].astype(str).eq("review_packet_candidate")
    gates = rows["official_gates_passed"].map(_as_bool)
    contribution = rows["portfolio_contribution_status"].astype(str).isin(
        {"positive_incremental_contribution", "accepted_diversifier", "improves_playbook"}
    )
    runtime_bound = rows["activation_runtime_binding_status"].astype(str).eq("runtime_bound_and_tested")
    admitted = rows[regular & tradable & gates & contribution & runtime_bound & ~rare_module_mask(rows) & ~quarantine_mask(rows)].copy()
    return admitted.sort_values(["phase", "candidate_id"]).reset_index(drop=True)


def rare_low_activity_scheduler_mapping(signal_evidence_status: str = "positive_research_signal") -> dict[str, Any]:
    return {
        "signal_evidence_status": signal_evidence_status,
        "signal_evidence_status_forced_to_no_signal": False,
        "rare_module_default_scheduler_status": "registry_only_excluded_from_default_scheduler",
        "tradability_status": "not_tradable_low_activity",
        "low_activity_blocks_tradability": True,
        "low_activity_erases_signal_evidence": False,
        "paper_trading_approved": False,
        "official_gates_changed": False,
    }


def validate_guardrail_inputs(data: Mapping[str, Any]) -> None:
    for name in ["scheduler_e_recommendation", "rare_module_policy", "rare_module_portfolio_audit_rules"]:
        payload = data[name]
        if _as_bool(payload.get("official_gates_changed", False)):
            raise ValueError(f"{name} changed official gates")
        if _as_bool(payload.get("paper_trading_approved", False)):
            raise ValueError(f"{name} approved paper trading")
        if _as_bool(payload.get("live_trading_approved", False)):
            raise ValueError(f"{name} approved live trading")


def build_playbook_scheduler_policy(data: Mapping[str, Any]) -> dict[str, Any]:
    validate_guardrail_inputs(data)
    registry = data["playbook_module_registry"]
    rare = rare_modules_from_registry(registry)
    quarantined = registry[quarantine_mask(registry)].copy().sort_values(["phase", "candidate_id"])
    default_universe = default_scheduler_universe(registry)
    admitted_universe = default_admission_universe(registry)
    scheduler_e = data["scheduler_e_recommendation"]

    return {
        "policy_name": "playbook_scheduler_f_rare_module_exclusion_policy",
        "source_scheduler_e_next_action": scheduler_e.get("next_action"),
        "source_scheduler_e_rationale": scheduler_e.get("rationale"),
        "research_only_guardrail": RESEARCH_ONLY_GUARDRAIL,
        "default_include_rare_modules_in_scheduler": False,
        "rare_modules_allowed_in_explicit_audits": True,
        "rare_module_default_scheduler_status": "registry_only_excluded_from_default_scheduler",
        "official_gates_changed": False,
        "paper_trading_approved": False,
        "live_trading_approved": False,
        "new_strategy_signals_generated": False,
        "strategy_searches_run": False,
        "candidate_results_changed": False,
        "candidates_promoted": False,
        "registry_mutation": False,
        "causality_quarantine_enforced": True,
        "phase16a_rare_modules_not_deleted": True,
        "phase16a_rare_modules_not_rejected_as_no_signal": True,
        "low_activity_does_not_erase_signal_evidence": True,
        "low_activity_blocks_tradability": True,
        "scheduler_semantics_version": "conditional_specialist_scheduler/v1",
        "no_trade_is_valid": True,
        "minimum_trades_per_day": None,
        "forced_daily_activity": False,
        "eligibility_layers": ["condition_eligible", "research_eligible", "default_scheduler_admitted"],
        "recommended_default_scheduler_universe": {
            "description": "Compatibility identifier for the historical research replay universe; not current default admission under Framework H.",
            "semantic_status": "historical_research_replay_universe_not_current_default_admission",
            "module_count": int(len(default_universe)),
            "module_ids": default_universe.get("module_id", pd.Series(dtype=object)).astype(str).tolist(),
            "signal_keys": [f"{row.phase}::{row.candidate_id}" for row in default_universe.itertuples(index=False)],
            "excluded_rare_module_count": int(len(rare)),
            "excluded_rare_module_ids": rare.get("module_id", pd.Series(dtype=object)).astype(str).tolist(),
            "excluded_quarantined_module_count": int(len(quarantined)),
            "excluded_quarantined_module_ids": quarantined.get("module_id", pd.Series(dtype=object)).astype(str).tolist(),
        },
        "current_default_admission_universe": {
            "description": "Modules satisfying runtime activation, regular-practice, standalone tradability, official gate, and incremental-contribution requirements.",
            "module_count": int(len(admitted_universe)),
            "module_ids": admitted_universe.get("module_id", pd.Series(dtype=object)).astype(str).tolist(),
            "signal_keys": [f"{row.phase}::{row.candidate_id}" for row in admitted_universe.itertuples(index=False)],
            "fail_closed_when_activation_binding_missing": True,
        },
        "historical_replay_semantics": {
            "historical_module_ids_preserved": True,
            "used_for_reproducible_target_d_and_baseline_b_replay": True,
            "implies_current_default_admission": False,
            "implies_tradability": False,
            "implies_paper_trading_approval": False,
        },
        "causality_quarantine_summary": {
            "quarantined_module_count": int(len(quarantined)),
            "all_quarantined_excluded_from_default_scheduler": not bool(
                set(quarantined.get("module_id", pd.Series(dtype=object)).astype(str)).intersection(
                    default_universe.get("module_id", pd.Series(dtype=object)).astype(str)
                )
            ),
            "historical_module_ids_preserved": True,
            "silent_definition_replacement": False,
        },
        "rare_module_exception_rules": {
            "allowed_contexts": [
                "explicit_rare_module_audit",
                "explicit_diversifier_audit",
                "rare_module_more_data_review",
            ],
            "required_explicit_flag": "include_rare_modules_in_scheduler=true",
            "default_without_explicit_flag": "exclude_rare_modules_from_active_scheduler_candidates",
            "must_report_rare_module_contribution_separately": True,
            "must_preserve_registry_only_status": True,
            "must_keep_paper_trading_approved_false": True,
            "must_keep_official_gates_changed_false": True,
        },
        "future_audit_requirements": {
            "more_evidence_required_before_default_scheduler_inclusion": True,
            "do_not_map_low_activity_to_no_signal": True,
            "separate_signal_evidence_from_tradability": True,
            "report_active_days_trades_pnl_overlap_drawdown_and_fold_effects": True,
            "verify_phase16a_rare_modules_remain_registered": True,
            "verify_no_live_trading_or_paper_approval": True,
        },
        "rare_module_registry_summary": {
            "rare_module_count": int(len(rare)),
            "phase16a_rare_module_count": int((rare.get("phase", pd.Series(dtype=object)).astype(str) == "phase16a").sum()),
            "all_rare_modules_registry_only_by_default": True,
            "all_rare_modules_not_tradable_low_activity_or_nontradable": _all_rare_nontradable(rare),
            "all_rare_modules_paper_trading_false": _all_false(rare, "paper_trading_approved"),
            "all_rare_modules_official_gates_false": _all_false(rare, "official_gates_passed"),
        },
        "input_guardrail_summary": {
            "scheduler_e_recommended_parking_rare_modules": scheduler_e.get("next_action") == "park_rare_modules_in_registry_but_exclude_from_scheduler",
            "scheduler_e_paper_trading_approved": bool(scheduler_e.get("paper_trading_approved", False)),
            "scheduler_e_official_gates_changed": bool(scheduler_e.get("official_gates_changed", False)),
            "rare_policy_loaded": bool(data["rare_module_policy"].get("rare_module_track_enabled", False)),
            "portfolio_audit_rules_allow_rare_diversifier_candidates": bool(data["rare_module_portfolio_audit_rules"].get("include_rare_modules_as_diversifier_candidates", False)),
        },
    }


def build_playbook_scheduler_f_artifacts(project_root: Path) -> dict[str, Any]:
    data = load_playbook_scheduler_policy_inputs(project_root)
    policy = build_playbook_scheduler_policy(data)
    rare_modules = rare_modules_from_registry(data["playbook_module_registry"])
    default_universe = default_scheduler_universe(data["playbook_module_registry"])
    admitted_universe = default_admission_universe(data["playbook_module_registry"])
    recommendation = deepcopy(SCHEDULER_F_RECOMMENDATION)
    report = render_scheduler_policy_report(policy=policy, recommendation=recommendation)
    result_row = pd.DataFrame([
        {
            "policy_name": policy["policy_name"],
            "default_include_rare_modules_in_scheduler": False,
            "rare_modules_allowed_in_explicit_audits": True,
            "default_scheduler_module_count": policy["recommended_default_scheduler_universe"]["module_count"],
            "current_default_admitted_module_count": int(len(admitted_universe)),
            "excluded_rare_module_count": policy["recommended_default_scheduler_universe"]["excluded_rare_module_count"],
            "phase16a_rare_module_count": policy["rare_module_registry_summary"]["phase16a_rare_module_count"],
            "official_gates_changed": False,
            "paper_trading_approved": False,
            "live_trading_approved": False,
            "scheduler_f_label": "rare_modules_registry_only_excluded_from_default_scheduler",
            "next_action": recommendation["next_action"],
        }
    ])
    return {
        "inputs_loaded": sorted(k for k in data if k != "input_paths"),
        "policy": policy,
        "recommendation": recommendation,
        "report": report,
        "result_row": result_row,
        "rare_modules": rare_modules,
        "default_scheduler_universe": default_universe,
        "default_admission_universe": admitted_universe,
    }


def render_scheduler_policy_report(*, policy: Mapping[str, Any], recommendation: Mapping[str, Any]) -> str:
    summary = policy["rare_module_registry_summary"]
    universe = policy["recommended_default_scheduler_universe"]
    lines = [
        "# Playbook Scheduler F — Rare Module Scheduler Exclusion Policy",
        "",
        RESEARCH_ONLY_GUARDRAIL,
        "",
        "This is a policy/configuration artifact only. It generated no new signals, ran no strategy searches, changed no historical candidate results, changed no official promotion gates, promoted no candidates, and approved no paper or live trading.",
        "",
        "## Policy summary",
        "",
        "- Rare modules remain in the research and playbook registries.",
        "- Rare modules are registry-only and excluded from default active scheduler candidate sets.",
        "- Rare modules may be included only in explicit rare-module or diversifier audits.",
        "- Phase 16A rare modules are not deleted and are not rejected as no_signal.",
        "- Low activity does not erase signal evidence, but low activity still blocks tradability.",
        "",
        "## Default scheduler policy",
        "",
        "- default_include_rare_modules_in_scheduler: `false`",
        "- rare_modules_allowed_in_explicit_audits: `true`",
        "- rare_module_default_scheduler_status: `registry_only_excluded_from_default_scheduler`",
        f"- default_scheduler_module_count: `{universe['module_count']}`",
        f"- current_default_admitted_module_count: `{policy['current_default_admission_universe']['module_count']}`",
        f"- excluded_rare_module_count: `{universe['excluded_rare_module_count']}`",
        "- The compatibility universe is historical research replay only; it does not imply current admission or tradability.",
        "- no_trade_is_valid: `true`",
        "- minimum_trades_per_day: `null`",
        "",
        "## Rare module registry summary",
        "",
        f"- rare_module_count: `{summary['rare_module_count']}`",
        f"- phase16a_rare_module_count: `{summary['phase16a_rare_module_count']}`",
        f"- all_rare_modules_registry_only_by_default: `{str(summary['all_rare_modules_registry_only_by_default']).lower()}`",
        f"- all_rare_modules_paper_trading_false: `{str(summary['all_rare_modules_paper_trading_false']).lower()}`",
        f"- all_rare_modules_official_gates_false: `{str(summary['all_rare_modules_official_gates_false']).lower()}`",
        "",
        "## Exception rules",
        "",
    ]
    for context in policy["rare_module_exception_rules"]["allowed_contexts"]:
        lines.append(f"- Allowed only with explicit context: `{context}`")
    lines.extend([
        "- Explicit flag required: `include_rare_modules_in_scheduler=true`",
        "- Without that flag, rare modules remain excluded from active scheduler candidates.",
        "- Any explicit rare/diversifier audit must keep paper_trading_approved=false and official_gates_changed=false.",
        "",
        "## Future audit requirements",
        "",
        "- Require more evidence before any default scheduler inclusion is reconsidered.",
        "- Keep signal evidence separate from tradability/practice readiness.",
        "- Report rare-module active days, trades, PnL, overlap, drawdown, and fold effects separately.",
        "- Verify Phase 16A rare modules remain registered, not deleted, and not mapped to no_signal solely because of low activity.",
        "",
        "## Official gates and approvals",
        "",
        "- official_gates_changed: `false`",
        "- paper_trading_approved: `false`",
        "- live_trading_approved: `false`",
        "",
        "## Recommended next action",
        "",
        f"- next_action: `{recommendation['next_action']}`",
        f"- rationale: {recommendation['rationale']}",
        f"- official_gates_changed: `{str(recommendation['official_gates_changed']).lower()}`",
        f"- paper_trading_approved: `{str(recommendation['paper_trading_approved']).lower()}`",
        f"- default_include_rare_modules_in_scheduler: `{str(recommendation['default_include_rare_modules_in_scheduler']).lower()}`",
        "",
    ])
    return "\n".join(lines)


def append_scheduler_f_objective_note(existing: str) -> str:
    heading = "## Scheduler F rare-module scheduler policy note"
    note = (
        f"\n\n{heading}\n\n"
        "Scheduler E found that rare modules should remain tracked as research/playbook registry signals but should be excluded from default active scheduler candidate sets until more evidence/data is available. "
        "Rare modules may be included only in explicit rare-module or diversifier audits. Low activity does not erase signal evidence and Phase 16A rare modules are not deleted or rejected as no_signal, but low activity still blocks tradability. "
        "Official gates remain unchanged and paper trading remains not approved.\n"
    )
    if heading in existing:
        return existing
    return existing.rstrip() + note


def _all_false(df: pd.DataFrame, column: str) -> bool:
    if df.empty or column not in df.columns:
        return False
    return bool((df[column].astype(str).str.lower() == "false").all())


def _all_rare_nontradable(df: pd.DataFrame) -> bool:
    if df.empty or "tradability_status" not in df.columns:
        return False
    values = df["tradability_status"].astype(str)
    return bool(values.str.startswith("not_tradable").all())


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
