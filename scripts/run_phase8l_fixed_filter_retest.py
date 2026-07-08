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
from short_term_edge.phase8l_fixed_filter_retest import (  # noqa: E402
    Phase8LConfig,
    build_phase8l_filter_specs,
    evaluate_phase8l_filters,
    render_phase8l_report,
)

EXPERIMENT_NAME = "phase8l_fixed_filter_retest"
GUARDRAILS = [
    "research/simulation only",
    "no live trading approval",
    "no broker adapters, order routing, API-key storage, webhooks, or automated execution",
    "fixed no-lookahead filter retest only; no paper-trading promotion",
]


def main() -> None:
    output_dir = PROJECT_ROOT / "outputs"
    report_dir = PROJECT_ROOT / "reports"
    output_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)

    phase8j_trades_path = output_dir / "phase8j_filtered_trade_log.csv"
    phase8k_actions_path = output_dir / "phase8k_candidate_actions.csv"
    for path in [phase8j_trades_path, phase8k_actions_path]:
        if not path.exists():
            raise FileNotFoundError(f"Phase 8L requires prior artifact: {path}")

    trades = pd.read_csv(phase8j_trades_path)
    actions = pd.read_csv(phase8k_actions_path)
    config = Phase8LConfig()
    specs = build_phase8l_filter_specs(actions, config)
    results, filtered_logs = evaluate_phase8l_filters(trades, specs, config)

    run_paths = prepare_experiment_run(PROJECT_ROOT, EXPERIMENT_NAME, run_id=os.environ.get("EXPERIMENT_RUN_ID"))
    results_path = output_dir / "phase8l_filter_retest_results.csv"
    specs_path = output_dir / "phase8l_filter_retest_specs.json"
    filtered_trade_logs_path = output_dir / "phase8l_filtered_trade_logs.csv"
    report_path = report_dir / "phase8l_fixed_filter_retest_report.md"

    specs_payload = [spec.to_dict() for spec in specs]
    results.to_csv(results_path, index=False)
    filtered_logs.to_csv(filtered_trade_logs_path, index=False)
    specs_path.write_text(json.dumps(specs_payload, indent=2, sort_keys=True), encoding="utf-8")
    results.to_csv(run_paths.results_path, index=False)
    filtered_logs.to_csv(run_paths.run_dir / "filtered_trade_logs.csv", index=False)
    run_paths.specs_path.write_text(json.dumps(specs_payload, indent=2, sort_keys=True), encoding="utf-8")

    report = render_phase8l_report(
        results,
        config,
        results_path=results_path,
        specs_path=specs_path,
        filtered_trade_logs_path=filtered_trade_logs_path,
        report_path=report_path,
        run_artifact_dir=run_paths.run_dir,
    )
    report_path.write_text(report, encoding="utf-8")
    run_paths.report_path.write_text(
        render_phase8l_report(
            results,
            config,
            results_path=run_paths.results_path,
            specs_path=run_paths.specs_path,
            filtered_trade_logs_path=run_paths.run_dir / "filtered_trade_logs.csv",
            report_path=run_paths.report_path,
            run_artifact_dir=run_paths.run_dir,
        ),
        encoding="utf-8",
    )

    symbol = str(trades["instrument"].dropna().iloc[0]) if "instrument" in trades.columns and not trades.empty else None
    manifest = write_experiment_manifest(
        project_root=PROJECT_ROOT,
        paths=run_paths,
        experiment_name=EXPERIMENT_NAME,
        command="./.venv/Scripts/python.exe scripts/run_phase8l_fixed_filter_retest.py",
        config={
            **asdict(config),
            "source_phase8j_filtered_trade_log": "outputs/phase8j_filtered_trade_log.csv",
            "source_phase8k_candidate_actions": "outputs/phase8k_candidate_actions.csv",
            "source_trade_count": len(trades),
            "source_action_count": len(actions),
            "spec_count": len(specs),
            "filtered_log_rows": len(filtered_logs),
        },
        selected_specs_count=len(specs),
        results=results,
        legacy_artifacts={
            "results": results_path,
            "specs": specs_path,
            "filtered_trade_logs": filtered_trade_logs_path,
            "report": report_path,
        },
        guardrails=GUARDRAILS,
        data_files=list_local_data_files(PROJECT_ROOT, symbol=symbol),
    )

    top = results.iloc[0] if not results.empty else None
    print("Phase 8L fixed no-lookahead filter retest complete.")
    print(f"Source Phase 8J trades: {len(trades)}")
    print(f"Source Phase 8K actions: {len(actions)}")
    print(f"Specs evaluated: {len(specs)}")
    print(f"Results rows: {len(results)}")
    print(f"Filtered log rows: {len(filtered_logs)}")
    print(f"Report: {report_path}")
    print(f"Run artifacts: {run_paths.run_dir}")
    print(f"Manifest rows: {manifest['result_row_count']}")
    if top is not None:
        print(f"Top filter: {top['filter_id']} ({top['phase8l_label']})")
        print(f"Top notes: {top['phase8l_notes']}")


if __name__ == "__main__":
    main()
