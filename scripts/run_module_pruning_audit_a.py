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
from short_term_edge.module_pruning_audit_a import (  # noqa: E402
    MODES,
    PRIORITY_POLICIES,
    PRUNING_VARIANTS,
    RESEARCH_ONLY_GUARDRAIL,
    SEED_SUSPECT_MODULE,
    best_pruning_result,
    loaded_input_names,
    render_module_pruning_audit_a_report,
    run_module_pruning_audit_a,
    write_module_pruning_audit_a_outputs,
)
from short_term_edge.phase_common import write_csv_artifact, write_json_artifact  # noqa: E402

EXPERIMENT_NAME = "module_pruning_audit_a"
RUN_COMMAND = "EXPERIMENT_RUN_ID=module-pruning-a-r1 ./.venv/Scripts/python.exe scripts/run_module_pruning_audit_a.py"
GUARDRAILS = [
    "research/simulation only",
    "harmful/redundant module diagnostic only",
    "existing Scheduler B, Portfolio Audit D, Weak Fold Audit B, registries, and trade logs only",
    "no new signals, no strategy searches, no candidate-result changes, no registry removals, no official gate changes, no promotions, no paper trading approval",
    "no broker adapters, order routing, webhooks, credential storage, automated execution, or LLM-driven trade decisions",
]


def main() -> None:
    output_dir = PROJECT_ROOT / "outputs"
    report_path = PROJECT_ROOT / "reports" / "module_pruning_audit_a_report.md"
    result = run_module_pruning_audit_a(output_dir)
    paths = write_module_pruning_audit_a_outputs(result, output_dir, report_path)

    run_paths = prepare_experiment_run(PROJECT_ROOT, EXPERIMENT_NAME, os.environ.get("EXPERIMENT_RUN_ID", "module-pruning-a-r1"))
    for key in ("module_diagnostics", "pruning_variants", "portfolio_results", "daily_pnl", "walk_forward_folds", "concentration", "overlap_summary", "redundancy_pairs"):
        value = result[key]
        if isinstance(value, pd.DataFrame):
            write_csv_artifact(value, run_paths.run_dir / f"{key}.csv")
    write_csv_artifact(result["portfolio_results"], run_paths.results_path)
    specs = {
        "diagnostic_only": True,
        "official_gates_unchanged": True,
        "paper_trading_approved": False,
        "new_signals_generated": False,
        "registry_modules_removed": False,
        "raw_sum_diagnostic_used_as_candidate": False,
        "seed_suspect_module": SEED_SUSPECT_MODULE,
        "seed_sibling_modules": result["seed_sibling_modules"],
        "pruning_variants": list(PRUNING_VARIANTS),
        "priority_policies": list(PRIORITY_POLICIES),
        "modes": list(MODES),
        "selected_signal_keys": result["selected_signal_keys"],
        "inputs_loaded": loaded_input_names(),
    }
    write_json_artifact(specs, run_paths.specs_path)
    run_paths.report_path.write_text(render_module_pruning_audit_a_report(result), encoding="utf-8")
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
            "registry_modules_removed": False,
            "next_action": result["next_action_recommendation"].get("next_action"),
            "inputs_loaded": loaded_input_names(),
        },
        selected_specs_count=len(PRUNING_VARIANTS) * len(PRIORITY_POLICIES) * len(MODES),
        results=result["portfolio_results"],
        legacy_artifacts={**paths, "artifact_recommendation": rec_path},
        guardrails=GUARDRAILS,
        data_files=[],
    )
    best = best_pruning_result(result["portfolio_results"])
    print("Module Pruning Audit A complete.")
    print(f"Seed suspect: {SEED_SUSPECT_MODULE}")
    print(f"Seed siblings: {';'.join(result['seed_sibling_modules'])}")
    print(f"Pruning variants: {', '.join(PRUNING_VARIANTS)}")
    print(f"Rows: {len(result['portfolio_results'])}")
    print(f"Best pruning result: {best.get('pruning_variant')} / {best.get('priority_policy')} / {best.get('portfolio_mode')} net={best.get('net_pnl')} pos_folds={best.get('positive_wf_test_folds_pct')} label={best.get('pruning_a_label')}")
    print(f"Next action: {result['next_action_recommendation'].get('next_action')}")
    print(f"Report: {report_path}")
    print(f"Run artifacts: {run_paths.run_dir}")
    print(f"Manifest rows: {manifest['result_row_count']}")
    print(RESEARCH_ONLY_GUARDRAIL)


if __name__ == "__main__":
    main()
