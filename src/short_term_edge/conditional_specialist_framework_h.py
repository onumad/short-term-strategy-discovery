"""Conditional Specialist Framework H contracts and diagnostics.

This module adds metadata and research-policy contracts. It does not execute
strategies, generate signals, mutate historical registry labels, or authorize
paper/live trading.
"""

from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import pandas as pd

from .experiments.artifacts import ExperimentRunPaths, write_experiment_manifest
from .phase_common import ensure_directory, write_csv_artifact, write_json_artifact


ACTIVATION_CONTRACT_VERSION = "specialist_activation_contract/v1"
SPECIALIST_POLICY_VERSION = "conditional_specialist_playbook_policy/v1"
COVERAGE_SCHEMA_VERSION = "specialist_condition_coverage_matrix/v1"
HYPOTHESIS_LEDGER_VERSION = "strategy_hypothesis_ledger/v1"

SESSION_WINDOWS = (
    "pre_rth",
    "opening_0930_1030",
    "morning_1030_1130",
    "midday_1130_1330",
    "afternoon_1330_1500",
    "power_hour_1500_1600",
)

ACTIVATION_COLUMNS = [
    "module_id",
    "phase",
    "candidate_id",
    "activation_condition_id",
    "activation_contract_version",
    "market_condition",
    "module_family",
    "session_window",
    "decision_time_et",
    "entry_window_et",
    "required_point_in_time_features",
    "eligible_when",
    "ineligible_when",
    "maximum_setups_per_session",
    "warmup_behavior",
    "no_trade_is_valid",
    "runtime_binding_status",
    "contract_source",
    "signal_evidence_status",
    "tradability_status",
    "research_track",
    "condition_eligibility_status",
    "research_eligible",
    "default_scheduler_admitted",
    "default_admission_failures",
    "paper_trading_approved",
    "live_trading_approved",
]


@dataclass(frozen=True)
class ConditionalSpecialistFrameworkHConfig:
    project_root: Path
    registry_path: Path
    registry_schema_path: Path
    scheduler_policy_path: Path
    taxonomy_path: Path
    output_dir: Path
    report_dir: Path
    artifact_dir: Path
    run_id: str = "conditional-specialist-framework-h-r1"


def activation_contract_schema() -> dict[str, Any]:
    return {
        "schema_version": ACTIVATION_CONTRACT_VERSION,
        "description": "Point-in-time metadata contract describing when a deterministic specialist may evaluate a setup.",
        "required_fields": list(ACTIVATION_COLUMNS),
        "condition_eligibility_states": ["runtime_state_required", "condition_active", "condition_inactive", "invalid_or_stale_inputs"],
        "eligibility_layers": {
            "condition_eligible": "The current point-in-time market state satisfies the specialist activation contract.",
            "research_eligible": "The registered module may participate in an explicit research audit.",
            "default_scheduler_admitted": "The module passed standalone tradability and incremental playbook contribution requirements.",
        },
        "no_trade_is_valid": True,
        "unknown_or_stale_inputs": "condition_ineligible_fail_closed",
        "runtime_binding_required_before_active_use": True,
        "paper_trading_approved": False,
        "live_trading_approved": False,
    }


def conditional_specialist_policy() -> dict[str, Any]:
    return {
        "schema_version": SPECIALIST_POLICY_VERSION,
        "authorization_stage": "research",
        "objective": "portfolio of complementary deterministic specialists that wait for their own point-in-time market conditions",
        "no_trade_is_valid": True,
        "minimum_trades_per_day": None,
        "forced_daily_activity": False,
        "activity_evaluation_horizon": "rolling_playbook_windows_not_individual_days",
        "scheduler_sequence": [
            "validate_point_in_time_inputs",
            "evaluate_specialist_activation_conditions",
            "filter_to_research_or_default_admission_context",
            "resolve_overlap_and_priority_among_existing_candidates",
            "accept_one_valid_candidate_or_no_trade",
        ],
        "default_admission_requirements": [
            "runtime_activation_contract_bound_and_tested",
            "research_track_regular_practice_candidate",
            "tradability_status_review_packet_candidate",
            "official_module_gates_passed",
            "positive_incremental_playbook_contribution",
            "not_quarantined",
        ],
        "rare_module_behavior": "registry_only_unless_explicit_rare_or_diversifier_audit",
        "parked_module_behavior": "historical_replay_or_explicit_diagnostic_only",
        "historical_replay_is_not_default_admission": True,
        "paper_trading_approved": False,
        "shadow_execution_approved": False,
        "live_trading_approved": False,
        "official_gates_changed": False,
    }


def build_activation_contracts(registry: pd.DataFrame) -> pd.DataFrame:
    required = {
        "module_id",
        "phase",
        "candidate_id",
        "market_condition",
        "module_family",
        "signal_evidence_status",
        "tradability_status",
        "research_track",
    }
    if missing := sorted(required - set(registry.columns)):
        raise ValueError(f"module registry missing Framework H fields: {missing}")
    rows = []
    for item in registry.to_dict(orient="records"):
        template = _activation_template(item)
        failures = default_admission_failures(item, template)
        evidence = str(item.get("signal_evidence_status", ""))
        quarantine = str(item.get("causality_review_status", "")) == "quarantined_noncausal_definition"
        research_eligible = evidence not in {"", "no_signal"} and not quarantine
        rows.append(
            {
                "module_id": str(item["module_id"]),
                "phase": str(item["phase"]),
                "candidate_id": str(item["candidate_id"]),
                "activation_condition_id": _activation_condition_id(item, template),
                "activation_contract_version": ACTIVATION_CONTRACT_VERSION,
                "market_condition": str(item["market_condition"]),
                "module_family": str(item["module_family"]),
                **template,
                "no_trade_is_valid": True,
                "runtime_binding_status": "metadata_only_not_runtime_enforced",
                "contract_source": "normalized_from_registered_phase_candidate_and_existing_strategy_semantics",
                "signal_evidence_status": evidence,
                "tradability_status": str(item["tradability_status"]),
                "research_track": str(item["research_track"]),
                "condition_eligibility_status": "runtime_state_required",
                "research_eligible": research_eligible,
                "default_scheduler_admitted": not failures,
                "default_admission_failures": ";".join(failures),
                "paper_trading_approved": False,
                "live_trading_approved": False,
            }
        )
    contracts = pd.DataFrame(rows, columns=ACTIVATION_COLUMNS).sort_values(["phase", "candidate_id"]).reset_index(drop=True)
    validate_activation_contracts(contracts)
    return contracts


def default_admission_failures(item: Mapping[str, Any], template: Mapping[str, Any]) -> list[str]:
    failures = []
    if template.get("runtime_binding_status", "metadata_only_not_runtime_enforced") != "runtime_bound_and_tested":
        failures.append("runtime_activation_contract_not_bound")
    if str(item.get("research_track")) != "regular_practice_candidate":
        failures.append("not_regular_practice_candidate")
    if str(item.get("tradability_status")) != "review_packet_candidate":
        failures.append("standalone_tradability_not_passed")
    if not _as_bool(item.get("official_gates_passed", False)):
        failures.append("official_module_gates_not_passed")
    contribution = str(item.get("portfolio_contribution_status", ""))
    if contribution not in {"positive_incremental_contribution", "accepted_diversifier", "improves_playbook"}:
        failures.append("positive_incremental_contribution_not_established")
    if str(item.get("causality_review_status", "")) == "quarantined_noncausal_definition":
        failures.append("quarantined_noncausal_definition")
    return failures


def validate_activation_contracts(contracts: pd.DataFrame) -> None:
    if list(contracts.columns) != ACTIVATION_COLUMNS:
        raise ValueError("activation contract columns do not match the versioned schema")
    if contracts["module_id"].duplicated().any():
        raise ValueError("activation contracts contain duplicate module ids")
    if not contracts["activation_contract_version"].eq(ACTIVATION_CONTRACT_VERSION).all():
        raise ValueError("activation contract version mismatch")
    if not contracts["no_trade_is_valid"].eq(True).all():
        raise ValueError("every specialist contract must allow no trade")
    if contracts["decision_time_et"].astype(str).str.fullmatch(r"\d{2}:\d{2}").ne(True).any():
        raise ValueError("activation contracts contain invalid decision times")
    if contracts[["eligible_when", "ineligible_when", "required_point_in_time_features"]].astype(str).apply(lambda col: col.str.strip().eq("")).any(axis=None):
        raise ValueError("activation contracts contain blank causal rules")
    if contracts["paper_trading_approved"].astype(bool).any() or contracts["live_trading_approved"].astype(bool).any():
        raise ValueError("activation contracts cannot approve paper or live trading")


def build_condition_coverage_matrix(contracts: pd.DataFrame, taxonomy: Mapping[str, Any]) -> pd.DataFrame:
    rows = []
    for condition in taxonomy["market_condition"]:
        for window in SESSION_WINDOWS:
            segment = contracts[contracts["market_condition"].eq(condition) & contracts["session_window"].eq(window)]
            positive = segment["signal_evidence_status"].isin(
                ["positive_research_signal", "real_but_nontradable_signal", "priority_research_signal_for_more_data"]
            )
            admitted = segment["default_scheduler_admitted"].eq(True)
            if segment.empty:
                status = "uncovered"
            elif admitted.any():
                status = "default_admitted_coverage"
            elif positive.any():
                status = "research_signal_nontradable_coverage"
            else:
                status = "weak_or_parked_coverage"
            rows.append(
                {
                    "schema_version": COVERAGE_SCHEMA_VERSION,
                    "market_condition": condition,
                    "session_window": window,
                    "registered_modules": len(segment),
                    "research_eligible_modules": int(segment["research_eligible"].sum()) if not segment.empty else 0,
                    "positive_signal_modules": int(positive.sum()),
                    "default_admitted_modules": int(admitted.sum()),
                    "coverage_status": status,
                    "module_ids": ";".join(segment["module_id"].astype(str)),
                    "no_trade_is_valid": True,
                }
            )
    return pd.DataFrame(rows)


def build_redundancy_audit(contracts: pd.DataFrame) -> pd.DataFrame:
    grouped = contracts.groupby(["activation_condition_id", "session_window", "module_family"], dropna=False)
    rows = []
    for key, segment in grouped:
        if len(segment) < 2:
            continue
        rows.append(
            {
                "activation_condition_id": key[0],
                "session_window": key[1],
                "module_family": key[2],
                "module_count": len(segment),
                "module_ids": ";".join(segment["module_id"].astype(str)),
                "redundancy_status": "shared_activation_contract_requires_variant_deduplication",
                "default_admitted_count": int(segment["default_scheduler_admitted"].sum()),
            }
        )
    return pd.DataFrame(rows, columns=[
        "activation_condition_id",
        "session_window",
        "module_family",
        "module_count",
        "module_ids",
        "redundancy_status",
        "default_admitted_count",
    ]).sort_values(["module_count", "activation_condition_id"], ascending=[False, True]).reset_index(drop=True)


def build_hypothesis_ledger(registry: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (phase, family, condition), segment in registry.groupby(["phase", "module_family", "market_condition"], dropna=False):
        evidence = sorted(set(segment["signal_evidence_status"].astype(str)))
        tracks = sorted(set(segment["research_track"].astype(str)))
        rows.append(
            {
                "schema_version": HYPOTHESIS_LEDGER_VERSION,
                "hypothesis_id": f"{phase}::{_slug(family)}::{_slug(condition)}",
                "phase": phase,
                "module_family": family,
                "market_condition": condition,
                "configurations_consumed": len(segment),
                "module_ids": ";".join(segment["module_id"].astype(str)),
                "signal_evidence_statuses": ";".join(evidence),
                "research_tracks": ";".join(tracks),
                "best_stress_pnl": _numeric_max(segment, "stress_pnl"),
                "best_holdout_pnl": _numeric_max(segment, "holdout_pnl"),
                "revisit_rule": "new_data_or_structurally_distinct_mechanism_required",
                "parameter_variation_alone_may_reopen": False,
                "paper_trading_approved": False,
            }
        )
    return pd.DataFrame(rows).sort_values(["phase", "module_family", "market_condition"]).reset_index(drop=True)


def build_framework_recommendation(
    contracts: pd.DataFrame,
    coverage: pd.DataFrame,
    redundancy: pd.DataFrame,
    historical_replay_count: int = 0,
) -> dict[str, Any]:
    admitted = int(contracts["default_scheduler_admitted"].sum())
    uncovered = coverage[coverage["coverage_status"].eq("uncovered")]
    return {
        "schema_version": "conditional_specialist_framework_h_recommendation/v1",
        "next_action": "obtain_preregistered_structural_specialist_brief_then_run_one_bounded_scout",
        "rationale": "No current module satisfies default-admission requirements. Preserve historical replay, rank gaps from explicit evidence rather than matrix order, and research one preregistered complementary specialist at a time.",
        "registered_module_count": len(contracts),
        "default_admitted_module_count": admitted,
        "nonadmitted_registered_module_count": len(contracts) - admitted,
        "historical_replay_module_count": int(historical_replay_count),
        "uncovered_condition_window_cells": len(uncovered),
        "redundancy_cluster_count": len(redundancy),
        "priority_gap": None,
        "priority_gap_selection_status": "requires_evidence_backed_ranking_not_first_uncovered_matrix_cell",
        "no_trade_is_valid": True,
        "forced_daily_activity": False,
        "official_gates_changed": False,
        "paper_trading_approved": False,
        "live_trading_approved": False,
    }


def build_registry_schema_additions(existing_schema: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "playbook_module_registry_specialist_additions/v1",
        "base_schema_name": existing_schema.get("schema_name"),
        "base_schema_version": existing_schema.get("version"),
        "activation_contract_stored_separately": True,
        "activation_contract_join_key": "module_id",
        "new_fields": {
            column: {"required": True, "source": ACTIVATION_CONTRACT_VERSION}
            for column in ACTIVATION_COLUMNS
            if column not in {"module_id", "phase", "candidate_id", "market_condition", "module_family", "signal_evidence_status", "tradability_status", "research_track", "paper_trading_approved", "live_trading_approved"}
        },
        "historical_registry_rows_mutated": False,
        "official_gates_changed": False,
        "paper_trading_approved_default": False,
    }


def build_historical_replay_universe(scheduler_policy: Mapping[str, Any]) -> pd.DataFrame:
    universe = scheduler_policy.get("recommended_default_scheduler_universe", {})
    module_ids = list(universe.get("module_ids", []))
    signal_keys = list(universe.get("signal_keys", []))
    if len(module_ids) != len(signal_keys):
        raise ValueError("historical scheduler replay universe ids and signal keys are misaligned")
    return pd.DataFrame(
        {
            "module_id": module_ids,
            "signal_key": signal_keys,
            "universe_role": "historical_research_replay",
            "default_scheduler_admitted": False,
            "compatibility_identifier_preserved": True,
            "paper_trading_approved": False,
            "live_trading_approved": False,
        }
    )


def build_conditional_specialist_framework_h(
    project_root: Path, run_id: str = "conditional-specialist-framework-h-r1"
) -> dict[str, Any]:
    outputs = project_root / "outputs"
    return run_conditional_specialist_framework_h(
        ConditionalSpecialistFrameworkHConfig(
            project_root=project_root,
            registry_path=outputs / "playbook_module_registry.csv",
            registry_schema_path=outputs / "playbook_module_registry_schema.json",
            scheduler_policy_path=outputs / "playbook_scheduler_policy.json",
            taxonomy_path=outputs / "playbook_module_taxonomy.json",
            output_dir=outputs,
            report_dir=project_root / "reports",
            artifact_dir=project_root / "artifacts" / "conditional_specialist_framework_h" / run_id,
            run_id=run_id,
        )
    )


def run_conditional_specialist_framework_h(config: ConditionalSpecialistFrameworkHConfig) -> dict[str, Any]:
    for directory in (config.output_dir, config.report_dir, config.artifact_dir):
        ensure_directory(directory)
    registry = pd.read_csv(config.registry_path)
    registry_schema = json.loads(config.registry_schema_path.read_text(encoding="utf-8"))
    scheduler_policy = json.loads(config.scheduler_policy_path.read_text(encoding="utf-8"))
    taxonomy = json.loads(config.taxonomy_path.read_text(encoding="utf-8"))
    contracts = build_activation_contracts(registry)
    coverage = build_condition_coverage_matrix(contracts, taxonomy)
    redundancy = build_redundancy_audit(contracts)
    hypotheses = build_hypothesis_ledger(registry)
    historical_replay = build_historical_replay_universe(scheduler_policy)
    default_admission = contracts[contracts["default_scheduler_admitted"].eq(True)].copy()
    policy = conditional_specialist_policy()
    policy.update(
        {
            "registered_module_count": len(contracts),
            "historical_replay_module_count": len(historical_replay),
            "default_admitted_module_count": len(default_admission),
            "historical_replay_policy_name": scheduler_policy.get("policy_name"),
            "historical_replay_universe_compatibility_preserved": True,
        }
    )
    schema_additions = build_registry_schema_additions(registry_schema)
    recommendation = build_framework_recommendation(contracts, coverage, redundancy, len(historical_replay))
    result_row = pd.DataFrame(
        [
            {
                "framework_version": SPECIALIST_POLICY_VERSION,
                "registered_modules": len(contracts),
                "research_eligible_modules": int(contracts["research_eligible"].sum()),
                "historical_replay_modules": len(historical_replay),
                "default_admitted_modules": len(default_admission),
                "uncovered_condition_window_cells": int(coverage["coverage_status"].eq("uncovered").sum()),
                "redundancy_clusters": len(redundancy),
                "hypothesis_families_recorded": len(hypotheses),
                "no_trade_is_valid": True,
                "official_gates_changed": False,
                "paper_trading_approved": False,
                "live_trading_approved": False,
                "next_action": recommendation["next_action"],
            }
        ]
    )
    paths = write_framework_h_outputs(
        config,
        contracts=contracts,
        coverage=coverage,
        redundancy=redundancy,
        hypotheses=hypotheses,
        historical_replay=historical_replay,
        default_admission=default_admission,
        policy=policy,
        activation_schema=activation_contract_schema(),
        registry_schema_additions=schema_additions,
        recommendation=recommendation,
        result_row=result_row,
    )
    return {
        "activation_contracts": contracts,
        "coverage_matrix": coverage,
        "redundancy_audit": redundancy,
        "hypothesis_ledger": hypotheses,
        "historical_replay_universe": historical_replay,
        "default_admission_universe": default_admission,
        "policy": policy,
        "activation_schema": activation_contract_schema(),
        "registry_schema_additions": schema_additions,
        "recommendation": recommendation,
        "result_row": result_row,
        "paths": paths,
    }


def write_framework_h_outputs(config: ConditionalSpecialistFrameworkHConfig, **items: Any) -> dict[str, Path]:
    paths = {
        "activation_contracts": config.output_dir / "playbook_specialist_activation_contracts.csv",
        "coverage_matrix": config.output_dir / "playbook_specialist_condition_coverage_matrix.csv",
        "redundancy_audit": config.output_dir / "playbook_specialist_redundancy_audit.csv",
        "hypothesis_ledger": config.output_dir / "strategy_hypothesis_ledger.csv",
        "historical_replay_universe": config.output_dir / "playbook_historical_replay_universe.csv",
        "default_admission_universe": config.output_dir / "playbook_default_admission_universe.csv",
        "policy": config.output_dir / "playbook_conditional_specialist_policy.json",
        "activation_schema": config.output_dir / "playbook_specialist_activation_contract_schema.json",
        "registry_schema_additions": config.output_dir / "playbook_specialist_registry_schema_additions.json",
        "recommendation": config.output_dir / "conditional_specialist_framework_h_next_action_recommendation.json",
        "report": config.report_dir / "conditional_specialist_framework_h_report.md",
    }
    frame_keys = {
        "activation_contracts": "contracts",
        "coverage_matrix": "coverage",
        "redundancy_audit": "redundancy",
        "hypothesis_ledger": "hypotheses",
        "historical_replay_universe": "historical_replay",
        "default_admission_universe": "default_admission",
    }
    for path_key, item_key in frame_keys.items():
        write_csv_artifact(items[item_key], paths[path_key])
    for key in ("policy", "activation_schema", "registry_schema_additions", "recommendation"):
        write_json_artifact(items[key], paths[key])
    report = render_framework_h_report(items)
    paths["report"].write_text(report, encoding="utf-8")

    run_paths = ExperimentRunPaths(
        experiment_name="conditional_specialist_framework_h",
        run_id=config.run_id,
        run_dir=config.artifact_dir,
        results_path=config.artifact_dir / "results.csv",
        specs_path=config.artifact_dir / "specs.json",
        report_path=config.artifact_dir / "report.md",
        manifest_path=config.artifact_dir / "manifest.json",
    )
    write_csv_artifact(items["result_row"], run_paths.results_path)
    run_paths.specs_path.write_text(json.dumps(items["policy"], indent=2, sort_keys=True), encoding="utf-8")
    shutil.copy2(paths["report"], run_paths.report_path)
    write_experiment_manifest(
        project_root=config.project_root,
        paths=run_paths,
        experiment_name=run_paths.experiment_name,
        command="./.venv/Scripts/python.exe scripts/build_conditional_specialist_framework_h.py",
        config={"framework_version": SPECIALIST_POLICY_VERSION, "strategy_replay": False, "strategy_search": False},
        selected_specs_count=0,
        results=items["result_row"],
        legacy_artifacts=paths,
        guardrails=[
            "research/simulation only",
            "no strategy signals generated",
            "historical replay identifiers preserved",
            "historical replay is not default admission",
            "no trade is a valid daily outcome",
            "official gates unchanged",
            "paper shadow and live trading not approved",
        ],
        data_files=[config.registry_path, config.registry_schema_path, config.scheduler_policy_path, config.taxonomy_path],
        release_id=f"conditional-specialist-framework-h:{config.run_id}",
        schema_versions={
            "activation_contract": ACTIVATION_CONTRACT_VERSION,
            "specialist_policy": SPECIALIST_POLICY_VERSION,
            "coverage_matrix": COVERAGE_SCHEMA_VERSION,
            "hypothesis_ledger": HYPOTHESIS_LEDGER_VERSION,
        },
        source_versions={"scheduler_policy": str(items["policy"].get("historical_replay_policy_name"))},
    )
    paths["manifest"] = run_paths.manifest_path
    return paths


def render_framework_h_report(items: Mapping[str, Any]) -> str:
    contracts = items["contracts"]
    coverage = items["coverage"]
    redundancy = items["redundancy"]
    hypotheses = items["hypotheses"]
    historical = items["historical_replay"]
    admitted = items["default_admission"]
    recommendation = items["recommendation"]
    coverage_counts = coverage["coverage_status"].value_counts().sort_index().to_dict()
    lines = [
        "# Conditional Specialist Framework H",
        "",
        "Research/simulation only. No strategy signals were generated and no paper, shadow, or live trading is approved.",
        "",
        "## Operational objective",
        "",
        "Each deterministic specialist waits for its own causal activation condition. The playbook may combine complementary opportunities over time, but no module or day is forced to trade.",
        "",
        "## Eligibility layers",
        "",
        "1. Condition eligibility requires the current point-in-time market state.",
        "2. Research eligibility permits only explicit offline audits.",
        "3. Default admission requires runtime-bound activation, regular-practice status, standalone tradability, official gates, and positive incremental contribution.",
        "",
        "## Current classification",
        "",
        f"- Registered modules: `{len(contracts)}`",
        f"- Research-eligible modules: `{int(contracts['research_eligible'].sum())}`",
        f"- Historical replay modules: `{len(historical)}`",
        f"- Default-admitted modules: `{len(admitted)}`",
        f"- Activation contracts runtime-bound: `{int(contracts['runtime_binding_status'].eq('runtime_bound_and_tested').sum())}`",
        f"- Coverage cell statuses: `{json.dumps(coverage_counts, sort_keys=True)}`",
        f"- Redundancy clusters: `{len(redundancy)}`",
        f"- Recorded hypothesis families: `{len(hypotheses)}`",
        "",
        "The prior 16-module scheduler universe is preserved as a historical research replay identifier. It is not evidence of current default admission.",
        "",
        "## No-trade behavior",
        "",
        "- `no_trade_is_valid: true`",
        "- `minimum_trades_per_day: null`",
        "- Opportunity coverage is evaluated over rolling playbook windows, not by forcing daily activity.",
        "- Missing, stale, incomplete, or inactive conditions fail closed to no trade.",
        "",
        "## Research control",
        "",
        "The hypothesis ledger records consumed families and forbids reopening them through parameter variation alone. New data or a structurally distinct mechanism is required.",
        "",
        "## Recommendation",
        "",
        f"- Next action: `{recommendation['next_action']}`",
        f"- Rationale: {recommendation['rationale']}",
        "",
        "## Guardrails",
        "",
        "- `official_gates_changed: false`",
        "- `paper_trading_approved: false`",
        "- `live_trading_approved: false`",
        "",
    ]
    return "\n".join(lines)


def _activation_template(item: Mapping[str, Any]) -> dict[str, Any]:
    phase = str(item.get("phase", ""))
    candidate = str(item.get("candidate_id", "")).lower()
    if phase == "phase10b":
        opening = "opening_response" in candidate
        return _template(
            "opening_0930_1030" if opening else "midday_1130_1330",
            "09:45" if opening else "11:30",
            "09:45-11:30" if opening else "11:30-14:30",
            "prior_rth_levels;overnight_range;gap_context;completed_response_bar",
            "price interacts with the frozen overnight-range level and the registered opening/midday response confirmation completes",
            "overnight level unavailable, response confirmation incomplete, entry window closed, or configured touch rule not satisfied",
        )
    if phase == "phase11a":
        midday = "midday_response" in candidate
        or_minutes = 30 if "or30" in candidate else 5
        return _template(
            "midday_1130_1330" if midday else "opening_0930_1030",
            "11:30" if midday else ("10:00" if or_minutes == 30 else "09:35"),
            "11:30-14:30" if midday else "09:35-11:30",
            f"completed_opening_range_{or_minutes}m;current_close;confirmation_state",
            "price breaches a completed opening-range boundary and the registered close-back-inside confirmation completes",
            "opening range incomplete, confirmation absent, entry window closed, or opening-range boundary unavailable",
        )
    if phase == "phase12a":
        return _template(
            "opening_0930_1030",
            "09:45",
            "09:45-11:30",
            "completed_opening_drive;drive_boundary_or_ema20;pullback_confirmation",
            "a completed directional opening drive makes its first registered pullback and resume confirmation",
            "opening drive incomplete, prior pullback already consumed, resume confirmation absent, or entry window closed",
        )
    if phase == "phase13a":
        return _template(
            "morning_1030_1130",
            "09:30",
            "09:30-15:30",
            "prior_rth_high;prior_rth_low;current_close;breakout_confirmation",
            "price breaks the registered prior-RTH boundary and the causal close confirmation completes",
            "prior-RTH levels unavailable, breakout confirmation absent, or entry window closed",
        )
    if phase == "phase14a":
        return _template(
            "morning_1030_1130",
            "10:00",
            "10:00-14:30",
            "prior_rth_level;current_bars;rejection_confirmation",
            "price interacts with the registered prior-session level and the rejection confirmation completes",
            "prior-session level unavailable, rejection confirmation absent, or entry window closed",
        )
    if phase == "phase15a":
        power = "power_hour" in candidate
        return _template(
            "power_hour_1500_1600" if power else "afternoon_1330_1500",
            "15:00" if power else "13:30",
            "15:00-15:45" if power else "13:30-15:30",
            "completed_intraday_trend_context;pullback_or_power_range;resume_confirmation",
            "the registered late-session continuation context and causal resume confirmation are both present",
            "trend context absent, confirmation incomplete, or flatten window too near",
        )
    if phase == "phase16a":
        return _template(
            "afternoon_1330_1500",
            "13:30",
            "13:30-15:30",
            "completed_morning_range;high_volatility_context;mixed_direction_state;resolution_confirmation",
            "a broad high-volatility mixed session resolves through the registered causal confirmation",
            "high-volatility mixed context absent, resolution incomplete, or entry window closed",
        )
    return _template(
        "midday_1130_1330",
        "11:30",
        "11:30-15:00",
        "registered_point_in_time_inputs",
        "the registered deterministic module condition is satisfied using completed observations",
        "required input missing or stale, registered condition absent, or entry window closed",
    )


def _template(window: str, decision: str, entry: str, features: str, eligible: str, ineligible: str) -> dict[str, Any]:
    return {
        "session_window": window,
        "decision_time_et": decision,
        "entry_window_et": entry,
        "required_point_in_time_features": features,
        "eligible_when": eligible,
        "ineligible_when": ineligible,
        "maximum_setups_per_session": 1,
        "warmup_behavior": "ineligible_until_all_required_inputs_are_complete",
        "runtime_binding_status": "metadata_only_not_runtime_enforced",
    }


def _activation_condition_id(item: Mapping[str, Any], template: Mapping[str, Any]) -> str:
    return "::".join(
        [
            _slug(item.get("market_condition", "unknown")),
            _slug(item.get("module_family", "unknown")),
            _slug(template["session_window"]),
            _slug(template["eligible_when"]),
        ]
    )


def _slug(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value).lower()).strip("_")[:120]


def _numeric_max(frame: pd.DataFrame, column: str) -> float | None:
    if column not in frame:
        return None
    values = pd.to_numeric(frame[column], errors="coerce").dropna()
    return round(float(values.max()), 2) if not values.empty else None


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"true", "1", "yes"}
