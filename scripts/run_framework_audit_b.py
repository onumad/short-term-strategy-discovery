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
from short_term_edge.framework_audit_b import (  # noqa: E402
    FrameworkAuditBConfig,
    PHASES,
    RESEARCH_ONLY_GUARDRAIL,
    recommendation_to_json,
    render_framework_audit_b_report,
    run_framework_audit_b,
    write_framework_audit_b_outputs,
)
from short_term_edge.phase_common import write_csv_artifact  # noqa: E402

EXPERIMENT_NAME = "framework_audit_b"
RUN_COMMAND = "EXPERIMENT_RUN_ID=framework-audit-b-r1 ./.venv/Scripts/python.exe scripts/run_framework_audit_b.py"
GUARDRAILS = [
    "research/simulation only",
    "no live trading approval",
    "no broker adapters, order routing, API-key storage, webhooks, credential storage, automated execution, or LLM-driven trade decisions",
    "diagnostic audit only; no new strategy signals, no gate changes, no candidate promotion",
]


def main() -> None:
    output_dir = PROJECT_ROOT / "outputs"
    report_path = PROJECT_ROOT / "reports" / "framework_audit_b_report.md"
    config = FrameworkAuditBConfig()
    result = run_framework_audit_b(output_dir, config)
    paths = write_framework_audit_b_outputs(result, output_dir, report_path)
    run_paths = prepare_experiment_run(PROJECT_ROOT, EXPERIMENT_NAME, run_id=os.environ.get("EXPERIMENT_RUN_ID"))
    for key, value in result.items():
        if isinstance(value, pd.DataFrame):
            write_csv_artifact(value, run_paths.run_dir / f"{key}.csv")
    write_csv_artifact(result["research_signal_summary"], run_paths.results_path)  # type: ignore[arg-type]
    run_paths.specs_path.write_text(recommendation_to_json({"audited_phases": PHASES, "official_gates_unchanged": True}), encoding="utf-8")
    run_paths.report_path.write_text(render_framework_audit_b_report(result, run_paths.report_path), encoding="utf-8")
    (run_paths.run_dir / "next_action_recommendation.json").write_text(recommendation_to_json(result["next_action_recommendation"]), encoding="utf-8")  # type: ignore[arg-type]
    manifest = write_experiment_manifest(
        project_root=PROJECT_ROOT,
        paths=run_paths,
        experiment_name=EXPERIMENT_NAME,
        command=RUN_COMMAND,
        config={
            "audited_phases": list(PHASES),
            "official_gates_unchanged": True,
            "input_source": "existing outputs only",
            "next_action": result["next_action_recommendation"].get("next_action"),  # type: ignore[union-attr]
        },
        selected_specs_count=len(result["research_signal_summary"]),  # type: ignore[arg-type]
        results=result["research_signal_summary"],  # type: ignore[arg-type]
        legacy_artifacts=paths,
        guardrails=GUARDRAILS,
        data_files=[],
    )
    summary = result["research_signal_summary"]
    rec = result["next_action_recommendation"]
    print("Framework Audit B complete.")
    print(f"Inputs loaded: {', '.join(PHASES)}")
    print(f"Audit candidates: {len(summary)}")
    print(f"Next action: {rec.get('next_action')}")
    print(f"Report: {report_path}")
    print(f"Run artifacts: {run_paths.run_dir}")
    print(f"Manifest rows: {manifest['result_row_count']}")
    print(RESEARCH_ONLY_GUARDRAIL)


if __name__ == "__main__":
    main()
