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
from short_term_edge.phase_common import write_csv_artifact  # noqa: E402
from short_term_edge.portfolio_audit_b import (  # noqa: E402
    PHASES,
    RESEARCH_ONLY_GUARDRAIL,
    render_portfolio_audit_b_report,
    run_portfolio_audit_b,
    write_portfolio_audit_b_outputs,
)

EXPERIMENT_NAME = "portfolio_audit_b"
RUN_COMMAND = "EXPERIMENT_RUN_ID=portfolio-audit-b-r1 ./.venv/Scripts/python.exe scripts/run_portfolio_audit_b.py"
GUARDRAILS = [
    "research/simulation only",
    "no live trading approval",
    "no broker adapters, order routing, webhooks, credential storage, automated execution, or LLM-driven trade decisions",
    "diagnostic portfolio audit only; no new entry rules, no raw-bar signal generation, no gate changes, no promotion",
]


def main() -> None:
    output_dir = PROJECT_ROOT / "outputs"
    report_path = PROJECT_ROOT / "reports" / "portfolio_audit_b_report.md"
    result = run_portfolio_audit_b(output_dir)
    paths = write_portfolio_audit_b_outputs(result, output_dir, report_path)
    run_paths = prepare_experiment_run(PROJECT_ROOT, EXPERIMENT_NAME, os.environ.get("EXPERIMENT_RUN_ID", "portfolio-audit-b-r1"))
    for key, value in result.items():
        if isinstance(value, pd.DataFrame):
            write_csv_artifact(value, run_paths.run_dir / f"{key}.csv")
    write_csv_artifact(result["portfolio_results"], run_paths.results_path)  # type: ignore[arg-type]
    run_paths.specs_path.write_text('{\n  "diagnostic_only": true,\n  "official_gates_unchanged": true,\n  "paper_trading_approved": false\n}\n', encoding="utf-8")
    run_paths.report_path.write_text(render_portfolio_audit_b_report(result, run_paths.report_path), encoding="utf-8")
    manifest = write_experiment_manifest(
        project_root=PROJECT_ROOT,
        paths=run_paths,
        experiment_name=EXPERIMENT_NAME,
        command=RUN_COMMAND,
        config={
            "audited_phases": list(PHASES),
            "official_gates_unchanged": True,
            "paper_trading_approved": False,
            "input_source": "playbook module registry and existing phase/Portfolio Audit A outputs only",
            "next_action": result["next_action_recommendation"].get("next_action"),  # type: ignore[union-attr]
        },
        selected_specs_count=len(result["signal_selection"]),  # type: ignore[arg-type]
        results=result["portfolio_results"],  # type: ignore[arg-type]
        legacy_artifacts=paths,
        guardrails=GUARDRAILS,
        data_files=[],
    )
    print("Portfolio Audit B complete.")
    print(f"Selected modules: {len(result['signal_selection'])}")
    print(f"Portfolio rows: {len(result['portfolio_results'])}")
    print(f"Next action: {result['next_action_recommendation'].get('next_action')}")
    print(f"Report: {report_path}")
    print(f"Run artifacts: {run_paths.run_dir}")
    print(f"Manifest rows: {manifest['result_row_count']}")
    print(RESEARCH_ONLY_GUARDRAIL)


if __name__ == "__main__":
    main()
