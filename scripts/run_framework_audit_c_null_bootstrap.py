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
from short_term_edge.framework_audit_c_null_bootstrap import (  # noqa: E402
    FrameworkAuditCConfig,
    PHASES,
    RESEARCH_ONLY_GUARDRAIL,
    create_research_signal_registry,
    recommendation_to_json,
    render_framework_audit_c_report,
    run_framework_audit_c,
    write_framework_audit_c_outputs,
)
from short_term_edge.phase_common import write_csv_artifact  # noqa: E402

EXPERIMENT_NAME = "framework_audit_c_null_bootstrap"
RUN_COMMAND = "EXPERIMENT_RUN_ID=framework-audit-c-r1 ./.venv/Scripts/python.exe scripts/run_framework_audit_c_null_bootstrap.py"
GUARDRAILS = [
    "research/simulation only",
    "no live trading approval",
    "no broker adapters, order routing, API-key storage, webhooks, credential storage, automated execution, or LLM-driven trade decisions",
    "diagnostic bootstrap/null audit only; no new strategy signals, no gate changes, no candidate promotion",
]


def main() -> None:
    output_dir = PROJECT_ROOT / "outputs"
    report_dir = PROJECT_ROOT / "reports"
    report_path = report_dir / "framework_audit_c_null_bootstrap_report.md"
    iterations = int(os.environ.get("FRAMEWORK_AUDIT_C_ITERATIONS", "10000"))
    top3_iterations = int(os.environ.get("FRAMEWORK_AUDIT_C_TOP3_ITERATIONS", "50000"))
    use_top3 = os.environ.get("FRAMEWORK_AUDIT_C_USE_TOP3", "1") != "0"
    config = FrameworkAuditCConfig(iterations=iterations, top3_iterations=top3_iterations, use_top3_iterations=use_top3)
    result = run_framework_audit_c(output_dir, config)
    paths = write_framework_audit_c_outputs(result, output_dir, report_path)
    registry_paths = create_research_signal_registry(output_dir, report_dir)
    paths.update({f"registry_{key}": value for key, value in registry_paths.items()})
    run_paths = prepare_experiment_run(PROJECT_ROOT, EXPERIMENT_NAME, run_id=os.environ.get("EXPERIMENT_RUN_ID"))
    for key, value in result.items():
        if isinstance(value, pd.DataFrame):
            write_csv_artifact(value, run_paths.run_dir / f"{key}.csv")
    write_csv_artifact(result["candidate_selection"], run_paths.results_path)  # type: ignore[arg-type]
    run_paths.specs_path.write_text(recommendation_to_json({"audited_phases": PHASES, "iterations": iterations, "top3_iterations": top3_iterations, "official_gates_unchanged": True}), encoding="utf-8")
    run_paths.report_path.write_text(render_framework_audit_c_report(result, run_paths.report_path), encoding="utf-8")
    (run_paths.run_dir / "next_action_recommendation.json").write_text(recommendation_to_json(result["next_action_recommendation"]), encoding="utf-8")  # type: ignore[arg-type]
    manifest = write_experiment_manifest(
        project_root=PROJECT_ROOT,
        paths=run_paths,
        experiment_name=EXPERIMENT_NAME,
        command=RUN_COMMAND,
        config={
            "audited_phases": list(PHASES),
            "iterations": iterations,
            "top3_iterations": top3_iterations if use_top3 else iterations,
            "official_gates_unchanged": True,
            "input_source": "existing outputs only",
            "matched_random_entry_backtester": "skipped",
            "next_action": result["next_action_recommendation"].get("next_action"),  # type: ignore[union-attr]
        },
        selected_specs_count=len(result["candidate_selection"]),  # type: ignore[arg-type]
        results=result["candidate_selection"],  # type: ignore[arg-type]
        legacy_artifacts=paths,
        guardrails=GUARDRAILS,
        data_files=[],
    )
    selected = result["candidate_selection"]
    rec = result["next_action_recommendation"]
    trade_boot = result["trade_bootstrap_summary"]
    print("Framework Audit C null/bootstrap audit complete.")
    print(f"Inputs loaded: {', '.join(PHASES)} plus Framework Audit B summary when available")
    print(f"Audit candidates: {len(selected)}")
    print(f"Iterations base/top3: {iterations} / {top3_iterations if use_top3 else iterations}")
    print(f"Bootstrap rows: {len(trade_boot)}")
    print(f"Next action: {rec.get('next_action')}")
    print(f"Report: {report_path}")
    print(f"Run artifacts: {run_paths.run_dir}")
    print(f"Manifest rows: {manifest['result_row_count']}")
    print(RESEARCH_ONLY_GUARDRAIL)


if __name__ == "__main__":
    main()
