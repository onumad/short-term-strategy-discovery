from __future__ import annotations

import os
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from short_term_edge.experiments.artifacts import prepare_experiment_run, write_experiment_manifest  # noqa: E402
from short_term_edge.phase_common import write_csv_artifact, write_json_artifact  # noqa: E402
from short_term_edge.validation_framework_audit_c_fold_design import (  # noqa: E402
    RESEARCH_ONLY_GUARDRAIL,
    render_validation_framework_audit_c_report,
    run_validation_framework_audit_c_fold_design,
    write_validation_framework_audit_c_outputs,
)

EXPERIMENT_NAME = "validation_framework_audit_c"
RUN_COMMAND = "EXPERIMENT_RUN_ID=validation-framework-audit-c-r1 ./.venv/Scripts/python.exe scripts/run_validation_framework_audit_c_fold_design.py"
GUARDRAILS = [
    "research/simulation only",
    "diagnostic fold-design audit only",
    "no new signals, no strategy searches, no candidate-result changes, no official gate changes, no promotion",
    "no live trading approval; no broker adapters, order routing, webhooks, credentials, automated execution, or LLM-driven trade decisions",
    "paper_trading_approved remains false",
]


def main() -> None:
    output_dir = PROJECT_ROOT / "outputs"
    report_path = PROJECT_ROOT / "reports" / "validation_framework_audit_c_fold_design_report.md"
    result = run_validation_framework_audit_c_fold_design(PROJECT_ROOT)
    paths = write_validation_framework_audit_c_outputs(result, output_dir, report_path)

    run_paths = prepare_experiment_run(
        PROJECT_ROOT,
        EXPERIMENT_NAME,
        os.environ.get("EXPERIMENT_RUN_ID", "validation-framework-audit-c-r1"),
    )
    for key, value in result.items():
        if isinstance(value, pd.DataFrame):
            write_csv_artifact(value, run_paths.run_dir / f"{key}.csv")
    write_json_artifact(result["recommended_validation_policy"], run_paths.run_dir / "recommended_validation_policy.json")
    write_json_artifact(result["next_action_recommendation"], run_paths.run_dir / "next_action_recommendation.json")
    write_csv_artifact(result["fold_sensitivity_summary"], run_paths.results_path)
    run_paths.specs_path.write_text(
        '{\n  "diagnostic_only": true,\n  "new_signals_generated": false,\n  "official_gates_unchanged": true,\n  "paper_trading_approved": false\n}\n',
        encoding="utf-8",
    )
    run_paths.report_path.write_text(render_validation_framework_audit_c_report(result), encoding="utf-8")
    manifest = write_experiment_manifest(
        project_root=PROJECT_ROOT,
        paths=run_paths,
        experiment_name=EXPERIMENT_NAME,
        command=RUN_COMMAND,
        config={
            "official_gates_unchanged": True,
            "paper_trading_approved": False,
            "input_source": "Existing scheduler/portfolio fold outputs, module daily PnL, registries, and Weak Fold Regime Audit B day features only",
            "next_action": result["next_action_recommendation"].get("next_action"),
        },
        selected_specs_count=0,
        results=result["fold_sensitivity_summary"],
        legacy_artifacts=paths,
        guardrails=GUARDRAILS,
        data_files=[],
    )
    print("Validation Framework Audit C — Fold Design complete.")
    print(f"Inputs loaded: {len(result['inputs_loaded'])}")
    print(f"Current fold rows: {len(result['fold_boundary_summary'])}")
    print(f"Alternative fold rows: {len(result['alternative_fold_results'])}")
    print(f"Module activity rows: {len(result['module_activity_by_fold'])}")
    print(f"Next action: {result['next_action_recommendation'].get('next_action')}")
    print(f"Report: {report_path}")
    print(f"Run artifacts: {run_paths.run_dir}")
    print(f"Manifest rows: {manifest['result_row_count']}")
    print(RESEARCH_ONLY_GUARDRAIL)


if __name__ == "__main__":
    main()
