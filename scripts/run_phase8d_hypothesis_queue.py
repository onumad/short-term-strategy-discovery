from __future__ import annotations

import os
import sys
from dataclasses import asdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from short_term_edge.experiments.artifacts import list_local_data_files, prepare_experiment_run, write_experiment_manifest  # noqa: E402
from short_term_edge.phase8d_hypothesis_queue import Phase8DConfig, build_phase8d_hypothesis_queue, render_phase8d_report  # noqa: E402

EXPERIMENT_NAME = "phase8d_hypothesis_queue"
GUARDRAILS = [
    "research/simulation only",
    "no live trading approval",
    "no broker adapters, order routing, API-key storage, webhooks, or automated execution",
    "hypothesis queue only; no backtest promotion",
]


def main() -> None:
    output_dir = PROJECT_ROOT / "outputs"
    report_dir = PROJECT_ROOT / "reports"
    output_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)

    run_paths = prepare_experiment_run(PROJECT_ROOT, EXPERIMENT_NAME, run_id=os.environ.get("EXPERIMENT_RUN_ID"))
    config = Phase8DConfig()
    queue = build_phase8d_hypothesis_queue(config)

    queue_path = output_dir / "phase8d_hypothesis_queue.csv"
    report_path = report_dir / "phase8d_hypothesis_queue_report.md"
    queue.to_csv(queue_path, index=False)
    queue.to_csv(run_paths.results_path, index=False)
    queue.to_json(run_paths.specs_path, orient="records", indent=2)

    report = render_phase8d_report(queue, config, queue_path=queue_path, report_path=report_path, run_artifact_dir=run_paths.run_dir)
    report_path.write_text(report, encoding="utf-8")
    run_paths.report_path.write_text(
        render_phase8d_report(queue, config, queue_path=run_paths.results_path, report_path=run_paths.report_path, run_artifact_dir=run_paths.run_dir),
        encoding="utf-8",
    )

    manifest = write_experiment_manifest(
        project_root=PROJECT_ROOT,
        paths=run_paths,
        experiment_name=EXPERIMENT_NAME,
        command="./.venv/Scripts/python.exe scripts/run_phase8d_hypothesis_queue.py",
        config=asdict(config),
        selected_specs_count=len(queue),
        results=queue,
        legacy_artifacts={"queue": queue_path, "report": report_path},
        guardrails=GUARDRAILS,
        data_files=list_local_data_files(PROJECT_ROOT),
    )

    print("Phase 8D broad hypothesis queue complete.")
    print(f"Hypotheses: {len(queue)}")
    print(f"Families: {queue['family'].nunique()}")
    print(f"Queue: {queue_path}")
    print(f"Report: {report_path}")
    print(f"Run artifacts: {run_paths.run_dir}")
    print(f"Manifest rows: {manifest['result_row_count']}")


if __name__ == "__main__":
    main()
