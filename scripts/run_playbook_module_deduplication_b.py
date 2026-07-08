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
from short_term_edge.playbook_module_deduplication_b import (  # noqa: E402
    OVERLAY_VERSION,
    RESEARCH_ONLY_GUARDRAIL,
    loaded_input_names,
    render_playbook_module_deduplication_b_report,
    run_playbook_module_deduplication_b,
    write_playbook_module_deduplication_b_outputs,
)

EXPERIMENT_NAME = "playbook_module_deduplication_b"
RUN_COMMAND = "EXPERIMENT_RUN_ID=playbook-module-deduplication-b-r1 ./.venv/Scripts/python.exe scripts/run_playbook_module_deduplication_b.py"
GUARDRAILS = [
    "research/simulation only",
    "deduplication/deprioritization review only",
    "existing registries, Module Pruning Audit A, Scheduler B/C outputs, and phase trade logs only",
    "no new signals, no strategy searches, no registry mutation, no official gate changes, no promotions, no paper trading approval",
    "scheduler overlay is proposed only and not written into live scheduler logic",
    "no broker adapters, order routing, webhooks, credential storage, automated execution, or LLM-driven trade decisions",
]


def main() -> None:
    output_dir = PROJECT_ROOT / "outputs"
    report_path = PROJECT_ROOT / "reports" / "playbook_module_deduplication_b_report.md"
    result = run_playbook_module_deduplication_b(output_dir)
    paths = write_playbook_module_deduplication_b_outputs(result, output_dir, report_path)

    run_paths = prepare_experiment_run(PROJECT_ROOT, EXPERIMENT_NAME, os.environ.get("EXPERIMENT_RUN_ID", "playbook-module-deduplication-b-r1"))
    for key in ("redundancy_clusters", "module_review", "representative_modules", "deprioritization_candidates"):
        value = result[key]
        if isinstance(value, pd.DataFrame):
            write_csv_artifact(value, run_paths.run_dir / f"{key}.csv")
    write_csv_artifact(result["module_review"], run_paths.results_path)
    specs = {
        "overlay_version": OVERLAY_VERSION,
        "diagnostic_only": True,
        "registry_mutation": False,
        "official_gates_changed": False,
        "paper_trading_approved": False,
        "new_signals_generated": False,
        "live_trading_approved": False,
        "seed_suspect_module": result["seed_suspect_module"],
        "seed_cluster_modules": result["seed_cluster_modules"],
        "inputs_loaded": loaded_input_names(),
    }
    write_json_artifact(specs, run_paths.specs_path)
    run_paths.report_path.write_text(render_playbook_module_deduplication_b_report(result), encoding="utf-8")
    overlay_path = run_paths.run_dir / "scheduler_overlay.json"
    rec_path = run_paths.run_dir / "next_action_recommendation.json"
    write_json_artifact(result["scheduler_overlay"], overlay_path)
    write_json_artifact(result["next_action_recommendation"], rec_path)
    manifest = write_experiment_manifest(
        project_root=PROJECT_ROOT,
        paths=run_paths,
        experiment_name=EXPERIMENT_NAME,
        command=RUN_COMMAND,
        config={
            "overlay_version": OVERLAY_VERSION,
            "registry_mutation": False,
            "official_gates_changed": False,
            "paper_trading_approved": False,
            "new_signals_generated": False,
            "next_action": result["next_action_recommendation"].get("next_action"),
            "inputs_loaded": loaded_input_names(),
        },
        selected_specs_count=len(result["module_review"]),
        results=result["module_review"],
        legacy_artifacts={**paths, "artifact_overlay": overlay_path, "artifact_recommendation": rec_path},
        guardrails=GUARDRAILS,
        data_files=[],
    )
    print("Playbook Module Deduplication B review complete.")
    print(f"Inputs loaded: {len(loaded_input_names())}")
    print(f"Redundancy clusters found: {len(result['redundancy_clusters'])}")
    print(f"Seed cluster: {';'.join(result['seed_cluster_modules'])}")
    print(f"Modules to keep: {len(result['scheduler_overlay']['modules_to_keep'])}")
    print(f"Modules to deprioritize: {len(result['scheduler_overlay']['modules_to_deprioritize'])}")
    print(f"Modules to park: {len(result['scheduler_overlay']['modules_to_park'])}")
    print(f"Next action: {result['next_action_recommendation'].get('next_action')}")
    print(f"Report: {report_path}")
    print(f"Run artifacts: {run_paths.run_dir}")
    print(f"Manifest rows: {manifest['result_row_count']}")
    print(RESEARCH_ONLY_GUARDRAIL)


if __name__ == "__main__":
    main()
