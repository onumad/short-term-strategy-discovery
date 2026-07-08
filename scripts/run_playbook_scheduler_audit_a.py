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
from short_term_edge.playbook_scheduler_audit_a import (  # noqa: E402
    MODES,
    REGIME_FILTERS,
    RESEARCH_ONLY_GUARDRAIL,
    SCHEDULER_VARIANTS,
    best_result,
    loaded_input_names,
    render_playbook_scheduler_audit_a_report,
    run_playbook_scheduler_audit_a,
    write_playbook_scheduler_audit_a_outputs,
)

EXPERIMENT_NAME = "playbook_scheduler_audit_a"
RUN_COMMAND = "EXPERIMENT_RUN_ID=playbook-scheduler-audit-a-r1 ./.venv/Scripts/python.exe scripts/run_playbook_scheduler_audit_a.py"
GUARDRAILS = [
    "research/simulation only",
    "diagnostic scheduler audit only",
    "existing module trade logs and Portfolio Audit D / Weak Fold Regime Audit B outputs only",
    "no new signals, no strategy searches, no candidate-result changes, no official gate changes, no promotions, no paper trading approval",
    "no broker adapters, order routing, webhooks, credential storage, automated execution, or LLM-driven trade decisions",
]


def main() -> None:
    output_dir = PROJECT_ROOT / "outputs"
    report_path = PROJECT_ROOT / "reports" / "playbook_scheduler_audit_a_report.md"
    result = run_playbook_scheduler_audit_a(output_dir)
    paths = write_playbook_scheduler_audit_a_outputs(result, output_dir, report_path)

    run_paths = prepare_experiment_run(PROJECT_ROOT, EXPERIMENT_NAME, os.environ.get("EXPERIMENT_RUN_ID", "playbook-scheduler-audit-a-r1"))
    for key in ("priority_results", "regime_filter_results", "overlap_diagnostics", "daily_pnl", "walk_forward_folds", "concentration"):
        value = result[key]
        if isinstance(value, pd.DataFrame):
            write_csv_artifact(value, run_paths.run_dir / f"{key}.csv")
    write_csv_artifact(result["priority_results"], run_paths.results_path)
    specs = {
        "diagnostic_only": True,
        "official_gates_unchanged": True,
        "paper_trading_approved": False,
        "new_signals_generated": False,
        "scheduler_variants": list(SCHEDULER_VARIANTS),
        "modes": list(MODES),
        "diagnostic_regime_filters": list(REGIME_FILTERS),
        "selected_signal_keys": result["selected_signal_keys"],
        "input_source": "existing module trade logs plus Portfolio Audit D and Weak Fold Regime Audit B outputs only",
    }
    write_json_artifact(specs, run_paths.specs_path)
    run_paths.report_path.write_text(render_playbook_scheduler_audit_a_report(result), encoding="utf-8")
    rec_path = run_paths.run_dir / "next_action_recommendation.json"
    write_json_artifact(result["next_action_recommendation"], rec_path)
    manifest = write_experiment_manifest(
        project_root=PROJECT_ROOT,
        paths=run_paths,
        experiment_name=EXPERIMENT_NAME,
        command=RUN_COMMAND,
        config={
            "scheduler_variants": list(SCHEDULER_VARIANTS),
            "modes": list(MODES),
            "diagnostic_regime_filters": list(REGIME_FILTERS),
            "official_gates_unchanged": True,
            "paper_trading_approved": False,
            "new_signals_generated": False,
            "next_action": result["next_action_recommendation"].get("next_action"),
            "inputs_loaded": loaded_input_names(),
        },
        selected_specs_count=len(SCHEDULER_VARIANTS) * len(MODES) * len(REGIME_FILTERS),
        results=result["priority_results"],
        legacy_artifacts={**paths, "artifact_recommendation": rec_path},
        guardrails=GUARDRAILS,
        data_files=[],
    )
    best = best_result(result["priority_results"])
    print("Playbook Scheduler Audit A complete.")
    print(f"Scheduler variants: {', '.join(SCHEDULER_VARIANTS)}")
    print(f"Regime filters: {', '.join(REGIME_FILTERS)}")
    print(f"Rows: {len(result['priority_results'])}")
    print(f"Best: {best.get('scheduler_variant')} / {best.get('portfolio_mode')} / {best.get('regime_filter')} net={best.get('net_pnl')} pos_folds={best.get('positive_wf_test_folds_pct')}")
    print(f"Next action: {result['next_action_recommendation'].get('next_action')}")
    print(f"Report: {report_path}")
    print(f"Run artifacts: {run_paths.run_dir}")
    print(f"Manifest rows: {manifest['result_row_count']}")
    print(RESEARCH_ONLY_GUARDRAIL)


if __name__ == "__main__":
    main()
