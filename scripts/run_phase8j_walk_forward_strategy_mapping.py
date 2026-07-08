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
from short_term_edge.phase8j_walk_forward_strategy_mapping import (  # noqa: E402
    Phase8JConfig,
    apply_phase8j_strategy_spec,
    build_phase8j_strategy_spec,
    render_phase8j_report,
    run_phase8j_walk_forward,
    summarize_phase8j_walk_forward,
)

EXPERIMENT_NAME = "phase8j_walk_forward_strategy_mapping"
GUARDRAILS = [
    "research/simulation only",
    "no live trading approval",
    "no broker adapters, order routing, API-key storage, webhooks, or automated execution",
    "StrategySpec mapping and walk-forward diagnostic only; no paper-trading promotion",
]


def main() -> None:
    output_dir = PROJECT_ROOT / "outputs"
    report_dir = PROJECT_ROOT / "reports"
    output_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)

    phase8i_trades_path = output_dir / "phase8i_deduped_mnq_vwap_trade_log.csv"
    phase8i_results_path = output_dir / "phase8i_no_lookahead_filter_results.csv"
    if not phase8i_trades_path.exists():
        raise FileNotFoundError(f"Phase 8J requires Phase 8I de-duplicated trade log: {phase8i_trades_path}")
    if not phase8i_results_path.exists():
        raise FileNotFoundError(f"Phase 8J requires Phase 8I filter results: {phase8i_results_path}")

    source_trades = pd.read_csv(phase8i_trades_path)
    phase8i_results = pd.read_csv(phase8i_results_path)
    config = Phase8JConfig()
    spec = build_phase8j_strategy_spec(source_trades, phase8i_results, config)
    filtered_trades = apply_phase8j_strategy_spec(source_trades, spec)
    fold_results = run_phase8j_walk_forward(filtered_trades, spec, config)
    summary = summarize_phase8j_walk_forward(fold_results, spec, config)

    run_paths = prepare_experiment_run(PROJECT_ROOT, EXPERIMENT_NAME, run_id=os.environ.get("EXPERIMENT_RUN_ID"))
    spec_path = output_dir / "phase8j_strategy_spec.json"
    filtered_trade_log_path = output_dir / "phase8j_filtered_trade_log.csv"
    fold_results_path = output_dir / "phase8j_walk_forward_folds.csv"
    summary_path = output_dir / "phase8j_walk_forward_summary.csv"
    report_path = report_dir / "phase8j_walk_forward_strategy_mapping_report.md"

    spec_payload = {**spec.to_dict(), "canonical_id": spec.canonical_id()}
    spec_path.write_text(json.dumps(spec_payload, indent=2, sort_keys=True), encoding="utf-8")
    run_paths.specs_path.write_text(json.dumps(spec_payload, indent=2, sort_keys=True), encoding="utf-8")
    filtered_trades.to_csv(filtered_trade_log_path, index=False)
    fold_results.to_csv(fold_results_path, index=False)
    summary.to_csv(summary_path, index=False)
    summary.to_csv(run_paths.results_path, index=False)
    filtered_trades.to_csv(run_paths.run_dir / "filtered_trade_log.csv", index=False)
    fold_results.to_csv(run_paths.run_dir / "folds.csv", index=False)

    report = render_phase8j_report(
        summary,
        fold_results,
        spec,
        config,
        spec_path=spec_path,
        filtered_trade_log_path=filtered_trade_log_path,
        fold_results_path=fold_results_path,
        summary_path=summary_path,
        report_path=report_path,
        run_artifact_dir=run_paths.run_dir,
    )
    report_path.write_text(report, encoding="utf-8")
    run_paths.report_path.write_text(
        render_phase8j_report(
            summary,
            fold_results,
            spec,
            config,
            spec_path=run_paths.specs_path,
            filtered_trade_log_path=run_paths.run_dir / "filtered_trade_log.csv",
            fold_results_path=run_paths.run_dir / "folds.csv",
            summary_path=run_paths.results_path,
            report_path=run_paths.report_path,
            run_artifact_dir=run_paths.run_dir,
        ),
        encoding="utf-8",
    )

    manifest = write_experiment_manifest(
        project_root=PROJECT_ROOT,
        paths=run_paths,
        experiment_name=EXPERIMENT_NAME,
        command="./.venv/Scripts/python.exe scripts/run_phase8j_walk_forward_strategy_mapping.py",
        config={
            **asdict(config),
            "source_phase8i_trade_log": "outputs/phase8i_deduped_mnq_vwap_trade_log.csv",
            "source_phase8i_results": "outputs/phase8i_no_lookahead_filter_results.csv",
            "source_trade_count": len(source_trades),
            "filtered_trade_count": len(filtered_trades),
            "strategy_candidate_id": spec.canonical_id(),
            "fold_result_rows": len(fold_results),
        },
        selected_specs_count=1,
        results=summary,
        legacy_artifacts={
            "spec": spec_path,
            "filtered_trade_log": filtered_trade_log_path,
            "fold_results": fold_results_path,
            "summary": summary_path,
            "report": report_path,
        },
        guardrails=GUARDRAILS,
        data_files=list_local_data_files(PROJECT_ROOT, symbol=spec.instrument),
    )

    top = summary.iloc[0] if not summary.empty else None
    print("Phase 8J walk-forward StrategySpec mapping complete.")
    print(f"Strategy candidate: {spec.canonical_id()}")
    print(f"Source trade rows: {len(source_trades)}")
    print(f"Filtered trade rows: {len(filtered_trades)}")
    print(f"Fold rows: {len(fold_results)}")
    print(f"Summary rows: {len(summary)}")
    print(f"Results: {summary_path}")
    print(f"Report: {report_path}")
    print(f"Run artifacts: {run_paths.run_dir}")
    print(f"Manifest rows: {manifest['result_row_count']}")
    if top is not None:
        print(f"Decision: {top['phase8j_label']} ({top['phase8j_notes']})")


if __name__ == "__main__":
    main()
