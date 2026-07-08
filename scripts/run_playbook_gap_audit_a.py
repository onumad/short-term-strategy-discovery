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
from short_term_edge.playbook_gap_audit_a import (  # noqa: E402
    RESEARCH_ONLY_GUARDRAIL,
    render_gap_audit_report,
    run_playbook_gap_audit_a,
    write_playbook_gap_audit_outputs,
)

EXPERIMENT_NAME = "playbook_gap_audit_a"
RUN_COMMAND = "EXPERIMENT_RUN_ID=playbook-gap-audit-a-r1 ./.venv/Scripts/python.exe scripts/run_playbook_gap_audit_a.py"
GUARDRAILS = [
    "research/simulation only",
    "no live trading approval",
    "no broker adapters, order routing, webhooks, credential storage, automated execution, or LLM-driven trade decisions",
    "diagnostic gap audit only; no new signals, no strategy searches, no gate changes, no promotion",
]


def main() -> None:
    output_dir = PROJECT_ROOT / "outputs"
    report_path = PROJECT_ROOT / "reports" / "playbook_gap_audit_a_report.md"
    result = run_playbook_gap_audit_a(PROJECT_ROOT)
    paths = write_playbook_gap_audit_outputs(result, output_dir, report_path)
    run_paths = prepare_experiment_run(PROJECT_ROOT, EXPERIMENT_NAME, os.environ.get("EXPERIMENT_RUN_ID", "playbook-gap-audit-a-r1"))
    for key, value in result.items():
        if isinstance(value, pd.DataFrame):
            write_csv_artifact(value, run_paths.run_dir / f"{key}.csv")
    write_json_artifact(result["candidate_module_briefs"], run_paths.run_dir / "candidate_module_briefs.json")  # type: ignore[arg-type]
    write_json_artifact(result["next_action_recommendation"], run_paths.run_dir / "next_action_recommendation.json")  # type: ignore[arg-type]
    write_csv_artifact(result["gap_summary"], run_paths.results_path)  # type: ignore[arg-type]
    run_paths.specs_path.write_text('{\n  "diagnostic_only": true,\n  "official_gates_unchanged": true,\n  "paper_trading_approved": false\n}\n', encoding="utf-8")
    run_paths.report_path.write_text(render_gap_audit_report(result), encoding="utf-8")
    manifest = write_experiment_manifest(
        project_root=PROJECT_ROOT,
        paths=run_paths,
        experiment_name=EXPERIMENT_NAME,
        command=RUN_COMMAND,
        config={
            "official_gates_unchanged": True,
            "paper_trading_approved": False,
            "input_source": "Portfolio Audit B outputs, playbook registry, phase daily/trade logs, and local MNQ raw data for diagnostics only",
            "next_action": result["next_action_recommendation"].get("next_action"),  # type: ignore[union-attr]
        },
        selected_specs_count=len(result["candidate_module_briefs"]),  # type: ignore[arg-type]
        results=result["gap_summary"],  # type: ignore[arg-type]
        legacy_artifacts=paths,
        guardrails=GUARDRAILS,
        data_files=[],
    )
    print("Playbook Gap Audit A complete.")
    print(f"Weak folds: {int(result['weak_folds']['is_weak_fold'].sum())}")
    print(f"Candidate module briefs: {len(result['candidate_module_briefs'])}")
    print(f"Next action: {result['next_action_recommendation'].get('next_action')}")
    print(f"Report: {report_path}")
    print(f"Run artifacts: {run_paths.run_dir}")
    print(f"Manifest rows: {manifest['result_row_count']}")
    print(RESEARCH_ONLY_GUARDRAIL)


if __name__ == "__main__":
    main()
