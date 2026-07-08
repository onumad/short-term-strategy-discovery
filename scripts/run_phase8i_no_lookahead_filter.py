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
from short_term_edge.phase8i_no_lookahead_filter import (  # noqa: E402
    Phase8IConfig,
    build_phase8i_filter_specs,
    evaluate_phase8i_filters,
    render_phase8i_report,
    select_phase8i_source_trades,
)

EXPERIMENT_NAME = "phase8i_no_lookahead_filter"
GUARDRAILS = [
    "research/simulation only",
    "no live trading approval",
    "no broker adapters, order routing, API-key storage, webhooks, or automated execution",
    "pre-entry time/session filters only; no paper-trading promotion",
]


def main() -> None:
    output_dir = PROJECT_ROOT / "outputs"
    report_dir = PROJECT_ROOT / "reports"
    output_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)

    phase8h_trade_path = output_dir / "phase8h_mnq_vwap_trade_log.csv"
    phase8h_overlap_path = output_dir / "phase8h_mnq_vwap_overlap_summary.csv"
    if not phase8h_trade_path.exists():
        raise FileNotFoundError(f"Phase 8I requires Phase 8H trade log: {phase8h_trade_path}")
    if not phase8h_overlap_path.exists():
        raise FileNotFoundError(f"Phase 8I requires Phase 8H overlap summary: {phase8h_overlap_path}")

    source_trades = pd.read_csv(phase8h_trade_path)
    overlap_summary = pd.read_csv(phase8h_overlap_path)
    config = Phase8IConfig()
    filter_specs = build_phase8i_filter_specs()
    deduped_trades = select_phase8i_source_trades(source_trades, overlap_summary, config)
    results = evaluate_phase8i_filters(deduped_trades, filter_specs, config)

    run_paths = prepare_experiment_run(PROJECT_ROOT, EXPERIMENT_NAME, run_id=os.environ.get("EXPERIMENT_RUN_ID"))
    deduped_path = output_dir / "phase8i_deduped_mnq_vwap_trade_log.csv"
    results_path = output_dir / "phase8i_no_lookahead_filter_results.csv"
    specs_path = output_dir / "phase8i_no_lookahead_filter_specs.json"
    report_path = report_dir / "phase8i_no_lookahead_filter_report.md"

    deduped_trades.to_csv(deduped_path, index=False)
    results.to_csv(results_path, index=False)
    specs_payload = [spec.to_dict() for spec in filter_specs]
    specs_path.write_text(json.dumps(specs_payload, indent=2, sort_keys=True), encoding="utf-8")
    results.to_csv(run_paths.results_path, index=False)
    run_paths.specs_path.write_text(json.dumps(specs_payload, indent=2, sort_keys=True), encoding="utf-8")
    deduped_trades.to_csv(run_paths.run_dir / "deduped_trade_log.csv", index=False)

    report = render_phase8i_report(
        results,
        config,
        source_trade_count=len(source_trades),
        deduped_trade_count=len(deduped_trades),
        results_path=results_path,
        report_path=report_path,
        run_artifact_dir=run_paths.run_dir,
    )
    report_path.write_text(report, encoding="utf-8")
    run_paths.report_path.write_text(
        render_phase8i_report(
            results,
            config,
            source_trade_count=len(source_trades),
            deduped_trade_count=len(deduped_trades),
            results_path=run_paths.results_path,
            report_path=run_paths.report_path,
            run_artifact_dir=run_paths.run_dir,
        ),
        encoding="utf-8",
    )

    manifest = write_experiment_manifest(
        project_root=PROJECT_ROOT,
        paths=run_paths,
        experiment_name=EXPERIMENT_NAME,
        command="./.venv/Scripts/python.exe scripts/run_phase8i_no_lookahead_filter.py",
        config={
            **asdict(config),
            "source_trade_log": "outputs/phase8h_mnq_vwap_trade_log.csv",
            "source_overlap_summary": "outputs/phase8h_mnq_vwap_overlap_summary.csv",
            "source_trade_count": len(source_trades),
            "deduped_trade_count": len(deduped_trades),
            "filter_count": len(filter_specs),
        },
        selected_specs_count=len(filter_specs),
        results=results,
        legacy_artifacts={
            "deduped_trade_log": deduped_path,
            "results": results_path,
            "specs": specs_path,
            "report": report_path,
        },
        guardrails=GUARDRAILS,
        data_files=list_local_data_files(PROJECT_ROOT, symbol="MNQ"),
    )

    print("Phase 8I no-lookahead filter diagnostic complete.")
    print(f"Source trade rows: {len(source_trades)}")
    print(f"De-duplicated trade rows: {len(deduped_trades)}")
    print(f"Filters evaluated: {len(results)}")
    print(f"Results: {results_path}")
    print(f"Report: {report_path}")
    print(f"Run artifacts: {run_paths.run_dir}")
    print(f"Manifest rows: {manifest['result_row_count']}")
    print(f"Top filter: {_top_filter(results)}")


def _top_filter(results: pd.DataFrame) -> str:
    if results.empty:
        return "none"
    row = results.iloc[0]
    return f"{row['filter_id']} ({row['phase8i_label']}, score {float(row['phase8i_score']):.2f})"


if __name__ == "__main__":
    main()
