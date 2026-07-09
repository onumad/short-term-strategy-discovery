from __future__ import annotations

import os
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from short_term_edge.experiments.artifacts import (  # noqa: E402
    prepare_experiment_run,
    write_experiment_manifest,
)
from short_term_edge.framework_g_policy_contracts import (  # noqa: E402
    COUNTERFACTUAL_POLICY_VERSION,
    LLM_TASK_REGISTRY_VERSION,
    bounded_llm_task_registry,
    counterfactual_policy_contract,
)
from short_term_edge.framework_g_research_release import (  # noqa: E402
    EVALUATION_POLICY_VERSION,
    MODEL_RELEASE_SCHEMA_VERSION,
    PREDICTION_SCHEMA_VERSION,
    FrameworkGPaths,
    write_ml_contract_artifacts,
)
from short_term_edge.phase_common import deterministic_json, ensure_directory, write_json_artifact  # noqa: E402


def main() -> None:
    run_id = os.environ.get("EXPERIMENT_RUN_ID", "framework-g-r1")
    output_dir = PROJECT_ROOT / "outputs"
    report_dir = PROJECT_ROOT / "reports"
    ensure_directory(output_dir)
    ensure_directory(report_dir)
    run_paths = prepare_experiment_run(PROJECT_ROOT, "framework_g_research_release", run_id)

    paths = write_ml_contract_artifacts(
        FrameworkGPaths(output_dir=output_dir, report_dir=report_dir, artifact_dir=run_paths.run_dir)
    )
    counterfactual_path = output_dir / "framework_g_counterfactual_policy_contract.json"
    llm_registry_path = output_dir / "framework_g_bounded_llm_task_registry.json"
    recommendation_path = output_dir / "framework_g_next_action_recommendation.json"
    report_path = report_dir / "framework_g_research_release_report.md"
    write_json_artifact(counterfactual_policy_contract(), counterfactual_path)
    write_json_artifact(bounded_llm_task_registry(), llm_registry_path)
    recommendation = {
        "next_action": "ml_baseline_b_calibration_drift_and_policy_impact_audit",
        "rationale": "Framework G now defines research-release provenance, strict non-authoritative prediction and LLM contracts, model-specific evaluation gates, and a deterministic counterfactual policy-impact boundary.",
        "authorization_stage": "research",
        "approved_as_signal_input": False,
        "paper_trading_approved": False,
        "shadow_execution_approved": False,
        "live_trading_approved": False,
        "official_gates_changed": False,
        "model_trained": False,
        "strategy_signals_generated": False,
        "scheduler_policy_mutated": False,
    }
    write_json_artifact(recommendation, recommendation_path)
    report = render_report(recommendation)
    report_path.write_text(report, encoding="utf-8")
    for path in (counterfactual_path, llm_registry_path, recommendation_path, report_path):
        (run_paths.run_dir / path.name).write_bytes(path.read_bytes())

    result = pd.DataFrame(
        [
            {
                "framework": "framework_g_research_release",
                "authorization_stage": "research",
                "manifest_schema_version": "research_run_manifest/v2",
                "prediction_schema_version": PREDICTION_SCHEMA_VERSION,
                "model_release_schema_version": MODEL_RELEASE_SCHEMA_VERSION,
                "evaluation_policy_version": EVALUATION_POLICY_VERSION,
                "counterfactual_policy_version": COUNTERFACTUAL_POLICY_VERSION,
                "llm_task_registry_version": LLM_TASK_REGISTRY_VERSION,
                "approved_as_signal_input": False,
                "paper_trading_approved": False,
                "live_trading_approved": False,
            }
        ]
    )
    result.to_csv(run_paths.results_path, index=False)
    specs = {
        "schema_versions": {
            "prediction": PREDICTION_SCHEMA_VERSION,
            "model_release": MODEL_RELEASE_SCHEMA_VERSION,
            "evaluation_policy": EVALUATION_POLICY_VERSION,
            "counterfactual_policy": COUNTERFACTUAL_POLICY_VERSION,
            "llm_task_registry": LLM_TASK_REGISTRY_VERSION,
        },
        "authorization_stage": "research",
        "approved_as_signal_input": False,
    }
    run_paths.specs_path.write_text(deterministic_json(specs), encoding="utf-8")
    run_paths.report_path.write_text(report, encoding="utf-8")
    legacy = {
        **paths,
        "counterfactual_policy": counterfactual_path,
        "llm_task_registry": llm_registry_path,
        "recommendation": recommendation_path,
        "report": report_path,
    }
    manifest = write_experiment_manifest(
        project_root=PROJECT_ROOT,
        paths=run_paths,
        experiment_name="framework_g_research_release",
        command="./.venv/Scripts/python.exe scripts/build_framework_g_research_release.py",
        config={"policy_only": True, "strategy_replay": False, "model_training": False},
        selected_specs_count=0,
        results=result,
        legacy_artifacts=legacy,
        guardrails=(
            "research/simulation only",
            "no model or LLM authority",
            "no strategy signals generated",
            "no scheduler or risk mutation",
            "paper and live trading not approved",
        ),
        release_id=f"framework-g:{run_id}",
        authorization_stage="research",
        schema_versions=specs["schema_versions"],
        source_versions={"baseline_b": "ml_baseline_b_coverage_classifier/v1"},
    )
    print("Framework G research release contracts complete.")
    print(f"Authorization stage: {manifest['authorization_stage']}")
    print(f"Manifest schema: {manifest['schema_version']}")
    print(f"Approved as signal input: {manifest['approval_state']['approved_as_signal_input']}")
    print(f"Next action: {recommendation['next_action']}")
    print(f"Report: {report_path}")
    print(f"Artifacts: {run_paths.run_dir}")


def render_report(recommendation: dict[str, object]) -> str:
    return "\n".join(
        [
            "# Framework G — Research Release and Model Contract",
            "",
            "Research/simulation only. No paper, shadow, or live trading is approved.",
            "",
            "## Delivered contracts",
            "- Research manifest v2 with SHA-256 lineage, source revision, runtime versions, and dirty-worktree provenance.",
            "- Research-only authorization policy with no automatic stage promotion.",
            "- Strict ML model-release and prediction envelopes with abstention and unknown-field rejection.",
            "- ML evaluation policy covering causality, readiness, calibration, drift, OOD, coverage, and policy impact.",
            "- Deterministic counterfactual overlay contract that cannot create entries, increase size, or change risk.",
            "- Bounded LLM task registry; candidate proposals are disabled and every task is non-authoritative.",
            "",
            "## Approval boundary",
            "Passing framework metrics may create eligibility for human signal-input review only. It never sets `approved_as_signal_input=true` and never changes scheduler, risk, paper, shadow, or live authorization.",
            "",
            "## Next action",
            f"- `{recommendation['next_action']}`",
            f"- {recommendation['rationale']}",
            "",
            "## Guardrails",
            "- `authorization_stage: research`",
            "- `approved_as_signal_input: false`",
            "- `paper_trading_approved: false`",
            "- `shadow_execution_approved: false`",
            "- `live_trading_approved: false`",
            "- `official_gates_changed: false`",
        ]
    ) + "\n"


if __name__ == "__main__":
    main()
