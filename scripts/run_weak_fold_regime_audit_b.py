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
from short_term_edge.weak_fold_regime_audit_b import (  # noqa: E402
    RESEARCH_ONLY_GUARDRAIL,
    render_weak_fold_regime_audit_b_report,
    run_weak_fold_regime_audit_b,
    write_weak_fold_regime_audit_b_outputs,
)

EXPERIMENT_NAME = "weak_fold_regime_audit_b"
RUN_COMMAND = "EXPERIMENT_RUN_ID=weak-fold-regime-audit-b-r1 ./.venv/Scripts/python.exe scripts/run_weak_fold_regime_audit_b.py"
GUARDRAILS = [
    "research/simulation only",
    "diagnostic weak-fold regime audit only",
    "no new signals, no strategy searches, no candidate-result changes, no official gate changes, no promotion",
    "no live trading approval; no broker adapters, order routing, webhooks, credentials, automated execution, or LLM-driven trade decisions",
    "paper_trading_approved remains false",
]


def main() -> None:
    output_dir = PROJECT_ROOT / "outputs"
    report_path = PROJECT_ROOT / "reports" / "weak_fold_regime_audit_b_report.md"
    result = run_weak_fold_regime_audit_b(PROJECT_ROOT)
    paths = write_weak_fold_regime_audit_b_outputs(result, output_dir, report_path)
    run_paths = prepare_experiment_run(PROJECT_ROOT, EXPERIMENT_NAME, os.environ.get("EXPERIMENT_RUN_ID", "weak-fold-regime-audit-b-r1"))
    for key, value in result.items():
        if isinstance(value, pd.DataFrame):
            write_csv_artifact(value, run_paths.run_dir / f"{key}.csv")
    write_json_artifact(result["candidate_remedies"], run_paths.run_dir / "candidate_remedies.json")
    write_json_artifact(result["next_action_recommendation"], run_paths.run_dir / "next_action_recommendation.json")
    write_csv_artifact(result["fold_summary"], run_paths.results_path)
    run_paths.specs_path.write_text(
        '{\n  "diagnostic_only": true,\n  "new_signals_generated": false,\n  "official_gates_unchanged": true,\n  "paper_trading_approved": false\n}\n',
        encoding="utf-8",
    )
    run_paths.report_path.write_text(render_weak_fold_regime_audit_b_report(result), encoding="utf-8")
    manifest = write_experiment_manifest(
        project_root=PROJECT_ROOT,
        paths=run_paths,
        experiment_name=EXPERIMENT_NAME,
        command=RUN_COMMAND,
        config={
            "official_gates_unchanged": True,
            "paper_trading_approved": False,
            "input_source": "Portfolio Audit B/C/D outputs, playbook/research registries, phase daily/trade logs, and local MNQ raw data for diagnostics only",
            "next_action": result["next_action_recommendation"].get("next_action"),
        },
        selected_specs_count=0,
        results=result["fold_summary"],
        legacy_artifacts=paths,
        guardrails=GUARDRAILS,
        data_files=[],
    )
    print("Weak Fold Regime Audit B complete.")
    print(f"Weak folds: {int(result['fold_summary']['is_weak_fold'].sum()) if not result['fold_summary'].empty else 0}")
    print(f"Weak-fold day rows: {len(result['weak_fold_days'])}")
    print(f"Candidate remedy briefs: {len(result['candidate_remedies'])}")
    print(f"Next action: {result['next_action_recommendation'].get('next_action')}")
    print(f"Report: {report_path}")
    print(f"Run artifacts: {run_paths.run_dir}")
    print(f"Manifest rows: {manifest['result_row_count']}")
    print(RESEARCH_ONLY_GUARDRAIL)


if __name__ == "__main__":
    main()
