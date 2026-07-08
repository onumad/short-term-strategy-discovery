from __future__ import annotations

import os
import shlex
import sys
from dataclasses import asdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from short_term_edge.phase8a import (  # noqa: E402
    Phase8AConfig,
    render_phase8a_report,
    run_phase8a_mgc_clean_family_search,
    write_phase8a_specs,
)
from short_term_edge.experiments.artifacts import (  # noqa: E402
    list_local_data_files,
    prepare_experiment_run,
    write_experiment_manifest,
)


EXPERIMENT_NAME = "phase8a_mgc_clean_family"
GUARDRAILS = (
    "research/simulation only",
    "no live trading approval",
    "no broker adapters, order routing, API-key storage, webhooks, or automated execution",
    "prefilter labels require walk-forward validation before paper-test consideration",
)


def main() -> None:
    output_dir = PROJECT_ROOT / "outputs"
    report_dir = PROJECT_ROOT / "reports"
    output_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)
    run_id = os.environ.get("EXPERIMENT_RUN_ID")
    run_paths = prepare_experiment_run(PROJECT_ROOT, EXPERIMENT_NAME, run_id=run_id)

    max_new = int(os.environ.get("PHASE8A_MAX_NEW_SPECS", "1"))
    repro_command = _phase8a_repro_command(max_new_specs=max_new, run_id=run_id)
    config = Phase8AConfig(symbol="MGC", max_specs=12, min_specs=6, max_new_specs_per_run=max_new, timeframes=(1, 3))
    results_path = output_dir / "phase8a_mgc_clean_family_results.csv"
    specs_path = output_dir / "phase8a_candidate_specs.json"
    report_path = report_dir / "phase8a_mgc_clean_family_report.md"

    result = run_phase8a_mgc_clean_family_search(PROJECT_ROOT, config, checkpoint_path=results_path)
    result.search_results.to_csv(results_path, index=False)
    result.search_results.to_csv(run_paths.results_path, index=False)
    write_phase8a_specs(result.specs, specs_path)
    write_phase8a_specs(result.specs, run_paths.specs_path)
    report_path.write_text(
        render_phase8a_report(
            config,
            result.search_results,
            selected_specs_count=len(result.specs),
            complete_sessions_count=len(result.complete_sessions),
            results_path=results_path,
            specs_path=specs_path,
            report_path=report_path,
            repro_command=repro_command,
        ),
        encoding="utf-8",
    )
    run_paths.report_path.write_text(
        render_phase8a_report(
            config,
            result.search_results,
            selected_specs_count=len(result.specs),
            complete_sessions_count=len(result.complete_sessions),
            results_path=run_paths.results_path,
            specs_path=run_paths.specs_path,
            report_path=run_paths.report_path,
            repro_command=repro_command,
        ),
        encoding="utf-8",
    )
    write_experiment_manifest(
        project_root=PROJECT_ROOT,
        paths=run_paths,
        experiment_name=EXPERIMENT_NAME,
        command=repro_command,
        config=asdict(config),
        selected_specs_count=len(result.specs),
        results=result.search_results,
        legacy_artifacts={"results": results_path, "specs": specs_path, "report": report_path},
        guardrails=GUARDRAILS,
        data_files=list_local_data_files(PROJECT_ROOT, symbol=config.symbol),
    )

    print("Phase 8A MGC clean-family prefilter search complete.")
    print(f"Search results: {results_path}")
    print(f"Candidate specs: {specs_path}")
    print(f"Report: {report_path}")
    print(f"Run artifacts: {run_paths.run_dir}")
    print(f"Manifest: {run_paths.manifest_path}")
    print(f"Rows scored: {len(result.search_results)} / {len(result.specs)} selected specs")
    if not result.search_results.empty:
        top = result.search_results.iloc[0]
        print(
            f"Top candidate: {top['candidate_id']} score={top['phase8a_score']} "
            f"label={top['phase8a_label']} net={top['net_pnl']:.2f} slip4={top['slippage_4_ticks_net_pnl']:.2f}"
        )


def _phase8a_repro_command(max_new_specs: int, run_id: str | None = None) -> str:
    assignments = []
    if run_id:
        assignments.append(f"EXPERIMENT_RUN_ID={shlex.quote(run_id)}")
    assignments.append(f"PHASE8A_MAX_NEW_SPECS={int(max_new_specs)}")
    assignments.append("./.venv/Scripts/python.exe scripts/run_phase8a_mgc_clean_family_search.py")
    return " ".join(assignments)


if __name__ == "__main__":
    main()
