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
from short_term_edge.playbook_scheduler_c_pruning_retest import (  # noqa: E402
    MAX_SELECTED_MODULES,
    MODES,
    PRIORITY_POLICIES,
    PRUNING_VARIANTS,
    RESEARCH_ONLY_GUARDRAIL,
    best_scheduler_c_result,
    loaded_input_names,
    render_playbook_scheduler_c_report,
    run_playbook_scheduler_c_pruning_retest,
    write_playbook_scheduler_c_outputs,
)

EXPERIMENT_NAME = "playbook_scheduler_c"
RUN_COMMAND = "EXPERIMENT_RUN_ID=playbook-scheduler-c-r1 ./.venv/Scripts/python.exe scripts/run_playbook_scheduler_c_pruning_retest.py"
GUARDRAILS = [
    "research/simulation only",
    "pruning/priority retest only",
    "existing Module Pruning Audit A, Scheduler B, registries, and phase trade logs only",
    "no new signals, no strategy searches, no candidate-result changes, no registry mutation, no official gate changes, no promotions, no paper trading approval",
    "no weak-fold-derived regime filters",
    "no broker adapters, order routing, webhooks, credential storage, automated execution, or LLM-driven trade decisions",
]


def main() -> None:
    output_dir = PROJECT_ROOT / "outputs"
    report_path = PROJECT_ROOT / "reports" / "playbook_scheduler_c_pruning_retest_report.md"
    result = run_playbook_scheduler_c_pruning_retest(output_dir)
    paths = write_playbook_scheduler_c_outputs(result, output_dir, report_path)

    run_paths = prepare_experiment_run(PROJECT_ROOT, EXPERIMENT_NAME, os.environ.get("EXPERIMENT_RUN_ID", "playbook-scheduler-c-r1"))
    for key in ("policy_results", "daily_pnl", "walk_forward_folds", "concentration", "overlap_summary", "module_acceptance_summary", "pruned_module_summary"):
        value = result[key]
        if isinstance(value, pd.DataFrame):
            write_csv_artifact(value, run_paths.run_dir / f"{key}.csv")
    write_csv_artifact(result["policy_results"], run_paths.results_path)
    specs = {
        "diagnostic_only": True,
        "official_gates_unchanged": True,
        "paper_trading_approved": False,
        "new_signals_generated": False,
        "registry_files_mutated": False,
        "raw_sum_diagnostic_used_as_candidate": False,
        "weak_fold_regime_filters_used": False,
        "max_selected_modules": MAX_SELECTED_MODULES,
        "pruning_variants": list(PRUNING_VARIANTS),
        "priority_policies": list(PRIORITY_POLICIES),
        "modes": list(MODES),
        "selected_signal_keys": result["selected_signal_keys"],
        "seed_cluster_modules": result["seed_cluster_modules"],
        "inputs_loaded": loaded_input_names(),
    }
    write_json_artifact(specs, run_paths.specs_path)
    run_paths.report_path.write_text(render_playbook_scheduler_c_report(result), encoding="utf-8")
    rec_path = run_paths.run_dir / "next_action_recommendation.json"
    write_json_artifact(result["next_action_recommendation"], rec_path)
    manifest = write_experiment_manifest(
        project_root=PROJECT_ROOT,
        paths=run_paths,
        experiment_name=EXPERIMENT_NAME,
        command=RUN_COMMAND,
        config={
            "pruning_variants": list(PRUNING_VARIANTS),
            "priority_policies": list(PRIORITY_POLICIES),
            "modes": list(MODES),
            "official_gates_unchanged": True,
            "paper_trading_approved": False,
            "new_signals_generated": False,
            "registry_files_mutated": False,
            "weak_fold_regime_filters_used": False,
            "next_action": result["next_action_recommendation"].get("next_action"),
            "inputs_loaded": loaded_input_names(),
        },
        selected_specs_count=len(PRUNING_VARIANTS) * len(PRIORITY_POLICIES) * len(MODES),
        results=result["policy_results"],
        legacy_artifacts={**paths, "artifact_recommendation": rec_path},
        guardrails=GUARDRAILS,
        data_files=[],
    )
    best = best_scheduler_c_result(result["policy_results"])
    print("Playbook Scheduler C pruning retest complete.")
    print(f"Selected modules: {len(result['selected_signal_keys'])}")
    print(f"Seed cluster: {';'.join(result['seed_cluster_modules'])}")
    print(f"Pruning variants: {', '.join(PRUNING_VARIANTS)}")
    print(f"Rows: {len(result['policy_results'])}")
    print(f"Best Scheduler C result: {best.get('pruning_variant')} / {best.get('priority_policy')} / {best.get('portfolio_mode')} net={best.get('net_pnl')} pos_folds={best.get('positive_wf_test_folds_pct')} label={best.get('scheduler_c_label')}")
    print(f"Next action: {result['next_action_recommendation'].get('next_action')}")
    print(f"Report: {report_path}")
    print(f"Run artifacts: {run_paths.run_dir}")
    print(f"Manifest rows: {manifest['result_row_count']}")
    print(RESEARCH_ONLY_GUARDRAIL)


if __name__ == "__main__":
    main()
