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
from short_term_edge.research_signal_registry import (  # noqa: E402
    PHASES,
    RESEARCH_ONLY_GUARDRAIL,
    build_research_signal_registry,
    recommendation_to_json,
    render_registry_report,
    write_registry_outputs,
)

EXPERIMENT_NAME = "research_signal_registry"
RUN_COMMAND = "./.venv/Scripts/python.exe scripts/build_research_signal_registry.py"
GUARDRAILS = [
    "research/simulation only",
    "no live trading approval",
    "no broker adapters, order routing, webhooks, credential storage, automated execution, or LLM-driven trade decisions",
    "additive registry only; no old label changes, no gate changes, no candidate promotion",
]


def main() -> None:
    output_dir = PROJECT_ROOT / "outputs"
    report_dir = PROJECT_ROOT / "reports"
    result = build_research_signal_registry(output_dir)
    paths = write_registry_outputs(result, output_dir, report_dir)
    run_paths = prepare_experiment_run(PROJECT_ROOT, EXPERIMENT_NAME, run_id=os.environ.get("EXPERIMENT_RUN_ID", "research-signal-registry-a"))
    registry = result["registry"]
    recommendation = result["recommendation"]
    write_csv_artifact(registry, run_paths.results_path)  # type: ignore[arg-type]
    run_paths.specs_path.write_text(recommendation_to_json({"audited_phases": PHASES, "official_gates_unchanged": True, "old_labels_unchanged": True}), encoding="utf-8")
    run_paths.report_path.write_text(render_registry_report(registry, recommendation), encoding="utf-8")  # type: ignore[arg-type]
    (run_paths.run_dir / "research_signal_registry.json").write_text((output_dir / "research_signal_registry.json").read_text(encoding="utf-8"), encoding="utf-8")
    (run_paths.run_dir / "next_action_recommendation.json").write_text(recommendation_to_json(recommendation), encoding="utf-8")  # type: ignore[arg-type]
    manifest = write_experiment_manifest(
        project_root=PROJECT_ROOT,
        paths=run_paths,
        experiment_name=EXPERIMENT_NAME,
        command=RUN_COMMAND,
        config={
            "audited_phases": list(PHASES),
            "official_gates_unchanged": True,
            "old_phase_labels_unchanged": True,
            "paper_trading_approved": False,
            "input_source": "Framework Audit B/C and existing phase outputs only",
            "next_action": recommendation.get("next_action"),  # type: ignore[union-attr]
        },
        selected_specs_count=len(registry),  # type: ignore[arg-type]
        results=registry,  # type: ignore[arg-type]
        legacy_artifacts=paths,
        guardrails=GUARDRAILS,
        data_files=[],
    )
    print("Research Signal Registry A complete.")
    print(f"Registry rows: {len(registry)}")
    print(f"Next action: {recommendation.get('next_action')}")
    print(f"Report: {paths['report']}")
    print(f"Run artifacts: {run_paths.run_dir}")
    print(f"Manifest rows: {manifest['result_row_count']}")
    print(RESEARCH_ONLY_GUARDRAIL)


if __name__ == "__main__":
    main()
