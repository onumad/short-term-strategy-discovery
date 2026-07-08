from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from short_term_edge.experiments.artifacts import list_local_data_files, prepare_experiment_run, write_experiment_manifest  # noqa: E402
from short_term_edge.phase8b import Phase8BConfig, render_phase8b_report, synthesize_phase8b_failures  # noqa: E402

EXPERIMENT_NAME = "phase8b_failure_synthesis"
GUARDRAILS = [
    "research/simulation only",
    "no live trading approval",
    "no broker adapters, order routing, API-key storage, webhooks, or automated execution",
    "synthesis only; no strategy logic or promotion gates changed",
]


def main() -> None:
    output_dir = PROJECT_ROOT / "outputs"
    report_dir = PROJECT_ROOT / "reports"
    output_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)

    run_paths = prepare_experiment_run(PROJECT_ROOT, EXPERIMENT_NAME, run_id=os.environ.get("EXPERIMENT_RUN_ID"))
    config = Phase8BConfig()

    phase7c = pd.read_csv(PROJECT_ROOT / config.phase7c_path)
    phase7d = pd.read_csv(PROJECT_ROOT / config.phase7d_path)
    phase8a = pd.read_csv(PROJECT_ROOT / config.phase8a_path)
    phase8a_manifest = _load_json(PROJECT_ROOT / config.phase8a_manifest_path)

    result = synthesize_phase8b_failures(phase7c, phase7d, phase8a, phase8a_manifest=phase8a_manifest, config=config)

    summary_path = output_dir / "phase8b_failure_summary.csv"
    report_path = report_dir / "phase8b_failure_synthesis_report.md"
    run_summary_path = run_paths.run_dir / "failure_summary.csv"
    run_inputs_path = run_paths.run_dir / "inputs.json"

    result.failure_summary.to_csv(summary_path, index=False)
    result.failure_summary.to_csv(run_paths.results_path, index=False)
    result.failure_summary.to_csv(run_summary_path, index=False)
    run_inputs_path.write_text(
        json.dumps(
            {
                "inputs": {
                    "phase7c": config.phase7c_path.as_posix(),
                    "phase7d": config.phase7d_path.as_posix(),
                    "phase8a": config.phase8a_path.as_posix(),
                    "phase8a_manifest": config.phase8a_manifest_path.as_posix(),
                },
                "result": result.to_manifest_payload(),
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    run_paths.specs_path.write_text(run_inputs_path.read_text(encoding="utf-8"), encoding="utf-8")

    legacy_report = render_phase8b_report(
        result,
        config,
        summary_path=summary_path,
        report_path=report_path,
        run_artifact_dir=run_paths.run_dir,
    )
    report_path.write_text(legacy_report, encoding="utf-8")
    run_paths.report_path.write_text(
        render_phase8b_report(
            result,
            config,
            summary_path=run_summary_path,
            report_path=run_paths.report_path,
            run_artifact_dir=run_paths.run_dir,
        ),
        encoding="utf-8",
    )

    manifest = write_experiment_manifest(
        project_root=PROJECT_ROOT,
        paths=run_paths,
        experiment_name=EXPERIMENT_NAME,
        command="./.venv/Scripts/python.exe scripts/run_phase8b_failure_synthesis.py",
        config={**asdict(config), "phase8b_result": result.to_manifest_payload()},
        selected_specs_count=result.phase8a_selected_specs_count,
        results=result.failure_summary,
        legacy_artifacts={"failure_summary": summary_path, "report": report_path},
        guardrails=GUARDRAILS,
        data_files=list_local_data_files(PROJECT_ROOT, symbol=config.symbol),
    )

    print("Phase 8B MGC failure synthesis complete.")
    print(f"Failure summary: {summary_path}")
    print(f"Report: {report_path}")
    print(f"Run artifacts: {run_paths.run_dir}")
    print(f"Manifest: {run_paths.manifest_path}")
    print(f"Top failure category: {_top_category(result.failure_summary)}")
    print(f"Recommended next step: {result.recommended_next_step}")
    print(f"Manifest result rows: {manifest['result_row_count']}")


def _load_json(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _top_category(summary: pd.DataFrame) -> str:
    if summary.empty:
        return "none"
    row = summary.iloc[0]
    return f"{row['failure_category']} ({int(row['total_count'])})"


if __name__ == "__main__":
    main()
