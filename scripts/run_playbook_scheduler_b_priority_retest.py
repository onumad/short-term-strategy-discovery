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
from short_term_edge.playbook_scheduler_b_priority_retest import (  # noqa: E402
    DIAGNOSTIC_FILTERS,
    MAX_SELECTED_MODULES,
    MODES,
    PRIORITY_POLICIES,
    RESEARCH_ONLY_GUARDRAIL,
    best_diagnostic_filter_result,
    best_priority_only_result,
    loaded_input_names,
    render_playbook_scheduler_b_report,
    run_playbook_scheduler_b_priority_retest,
    write_playbook_scheduler_b_outputs,
)

EXPERIMENT_NAME = "playbook_scheduler_b"
RUN_COMMAND = "EXPERIMENT_RUN_ID=playbook-scheduler-b-r1 ./.venv/Scripts/python.exe scripts/run_playbook_scheduler_b_priority_retest.py"
GUARDRAILS = [
    "research/simulation only",
    "priority scheduler retest only",
    "existing module trade logs plus Scheduler Audit A and Portfolio Audit D outputs only",
    "no new signals, no strategy searches, no candidate-result changes, no official gate changes, no promotions, no paper trading approval",
    "diagnostic overlap-heavy-day filter is not a live or paper rule",
    "no broker adapters, order routing, webhooks, credential storage, automated execution, or LLM-driven trade decisions",
]


def main() -> None:
    output_dir = PROJECT_ROOT / "outputs"
    report_path = PROJECT_ROOT / "reports" / "playbook_scheduler_b_priority_retest_report.md"
    result = run_playbook_scheduler_b_priority_retest(output_dir)
    paths = write_playbook_scheduler_b_outputs(result, output_dir, report_path)

    run_paths = prepare_experiment_run(PROJECT_ROOT, EXPERIMENT_NAME, os.environ.get("EXPERIMENT_RUN_ID", "playbook-scheduler-b-r1"))
    for key in ("priority_policy_results", "daily_pnl", "walk_forward_folds", "concentration", "overlap_summary", "policy_comparison", "module_acceptance_summary"):
        value = result[key]
        if isinstance(value, pd.DataFrame):
            write_csv_artifact(value, run_paths.run_dir / f"{key}.csv")
    write_csv_artifact(result["priority_policy_results"], run_paths.results_path)
    specs = {
        "diagnostic_only": True,
        "official_gates_unchanged": True,
        "paper_trading_approved": False,
        "new_signals_generated": False,
        "raw_sum_diagnostic_used_as_candidate": False,
        "max_selected_modules": MAX_SELECTED_MODULES,
        "selected_module_count": len(result["module_selection"]),
        "priority_policies": list(PRIORITY_POLICIES),
        "modes": list(MODES),
        "diagnostic_filters": list(DIAGNOSTIC_FILTERS),
        "selected_signal_keys": result["selected_signal_keys"],
        "input_source": "existing module trade logs plus Scheduler Audit A and Portfolio Audit D outputs only",
    }
    write_json_artifact(specs, run_paths.specs_path)
    run_paths.report_path.write_text(render_playbook_scheduler_b_report(result), encoding="utf-8")
    rec_path = run_paths.run_dir / "next_action_recommendation.json"
    write_json_artifact(result["next_action_recommendation"], rec_path)
    manifest = write_experiment_manifest(
        project_root=PROJECT_ROOT,
        paths=run_paths,
        experiment_name=EXPERIMENT_NAME,
        command=RUN_COMMAND,
        config={
            "priority_policies": list(PRIORITY_POLICIES),
            "modes": list(MODES),
            "diagnostic_filters": list(DIAGNOSTIC_FILTERS),
            "selected_module_count": len(result["module_selection"]),
            "official_gates_unchanged": True,
            "paper_trading_approved": False,
            "new_signals_generated": False,
            "next_action": result["next_action_recommendation"].get("next_action"),
            "inputs_loaded": loaded_input_names(),
        },
        selected_specs_count=len(PRIORITY_POLICIES) * len(MODES) * len(DIAGNOSTIC_FILTERS),
        results=result["priority_policy_results"],
        legacy_artifacts={**paths, "artifact_recommendation": rec_path},
        guardrails=GUARDRAILS,
        data_files=[],
    )
    best_priority = best_priority_only_result(result["priority_policy_results"])
    best_filter = best_diagnostic_filter_result(result["priority_policy_results"])
    print("Playbook Scheduler B priority retest complete.")
    print(f"Priority policies: {', '.join(PRIORITY_POLICIES)}")
    print(f"Diagnostic filters: {', '.join(DIAGNOSTIC_FILTERS)}")
    print(f"Selected modules: {len(result['module_selection'])}")
    print(f"Rows: {len(result['priority_policy_results'])}")
    print(f"Best priority-only: {best_priority.get('priority_policy')} / {best_priority.get('portfolio_mode')} net={best_priority.get('net_pnl')} pos_folds={best_priority.get('positive_wf_test_folds_pct')}")
    print(f"Best diagnostic-filter: {best_filter.get('priority_policy')} / {best_filter.get('portfolio_mode')} net={best_filter.get('net_pnl')} pos_folds={best_filter.get('positive_wf_test_folds_pct')}")
    print(f"Next action: {result['next_action_recommendation'].get('next_action')}")
    print(f"Report: {report_path}")
    print(f"Run artifacts: {run_paths.run_dir}")
    print(f"Manifest rows: {manifest['result_row_count']}")
    print(RESEARCH_ONLY_GUARDRAIL)


if __name__ == "__main__":
    main()
