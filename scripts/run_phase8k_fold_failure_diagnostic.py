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
from short_term_edge.phase8k_fold_failure_diagnostic import (  # noqa: E402
    Phase8KConfig,
    build_phase8k_candidate_actions,
    build_phase8k_next_step_queue,
    render_phase8k_report,
    summarize_phase8k_buckets,
    summarize_phase8k_sessions,
    tag_phase8k_trades_with_folds,
)

EXPERIMENT_NAME = "phase8k_fold_failure_diagnostic"
GUARDRAILS = [
    "research/simulation only",
    "no live trading approval",
    "no broker adapters, order routing, API-key storage, webhooks, or automated execution",
    "diagnostic-only follow-up queue; no paper-trading promotion",
]


def main() -> None:
    output_dir = PROJECT_ROOT / "outputs"
    report_dir = PROJECT_ROOT / "reports"
    output_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)

    filtered_trade_log_path = output_dir / "phase8j_filtered_trade_log.csv"
    fold_results_path = output_dir / "phase8j_walk_forward_folds.csv"
    summary_path = output_dir / "phase8j_walk_forward_summary.csv"
    for path in [filtered_trade_log_path, fold_results_path, summary_path]:
        if not path.exists():
            raise FileNotFoundError(f"Phase 8K requires Phase 8J artifact: {path}")

    filtered_trades = pd.read_csv(filtered_trade_log_path)
    fold_results = pd.read_csv(fold_results_path)
    phase8j_summary = pd.read_csv(summary_path)
    config = Phase8KConfig()

    tagged_trades = tag_phase8k_trades_with_folds(filtered_trades, fold_results, config)
    session_diagnostics = summarize_phase8k_sessions(tagged_trades, fold_results, config)
    bucket_diagnostics = summarize_phase8k_buckets(tagged_trades, config)
    candidate_actions = build_phase8k_candidate_actions(session_diagnostics, bucket_diagnostics, config)
    next_step_queue = build_phase8k_next_step_queue(candidate_actions, session_diagnostics, bucket_diagnostics, config)

    run_paths = prepare_experiment_run(PROJECT_ROOT, EXPERIMENT_NAME, run_id=os.environ.get("EXPERIMENT_RUN_ID"))
    tagged_trades_path = output_dir / "phase8k_tagged_trades.csv"
    session_diagnostics_path = output_dir / "phase8k_session_diagnostics.csv"
    bucket_diagnostics_path = output_dir / "phase8k_bucket_diagnostics.csv"
    candidate_actions_path = output_dir / "phase8k_candidate_actions.csv"
    next_step_queue_path = output_dir / "phase8k_next_step_queue.csv"
    report_path = report_dir / "phase8k_fold_failure_diagnostic_report.md"

    tagged_trades.to_csv(tagged_trades_path, index=False)
    session_diagnostics.to_csv(session_diagnostics_path, index=False)
    bucket_diagnostics.to_csv(bucket_diagnostics_path, index=False)
    candidate_actions.to_csv(candidate_actions_path, index=False)
    next_step_queue.to_csv(next_step_queue_path, index=False)
    next_step_queue.to_csv(run_paths.results_path, index=False)
    (run_paths.run_dir / "tagged_trades.csv").write_text(tagged_trades.to_csv(index=False), encoding="utf-8")
    (run_paths.run_dir / "session_diagnostics.csv").write_text(session_diagnostics.to_csv(index=False), encoding="utf-8")
    (run_paths.run_dir / "bucket_diagnostics.csv").write_text(bucket_diagnostics.to_csv(index=False), encoding="utf-8")
    (run_paths.run_dir / "candidate_actions.csv").write_text(candidate_actions.to_csv(index=False), encoding="utf-8")
    run_paths.specs_path.write_text(json.dumps(candidate_actions.to_dict(orient="records"), indent=2, sort_keys=True), encoding="utf-8")

    report = render_phase8k_report(
        session_diagnostics,
        bucket_diagnostics,
        candidate_actions,
        next_step_queue,
        config,
        tagged_trades_path=tagged_trades_path,
        session_diagnostics_path=session_diagnostics_path,
        bucket_diagnostics_path=bucket_diagnostics_path,
        candidate_actions_path=candidate_actions_path,
        next_step_queue_path=next_step_queue_path,
        report_path=report_path,
        run_artifact_dir=run_paths.run_dir,
    )
    report_path.write_text(report, encoding="utf-8")
    run_paths.report_path.write_text(
        render_phase8k_report(
            session_diagnostics,
            bucket_diagnostics,
            candidate_actions,
            next_step_queue,
            config,
            tagged_trades_path=run_paths.run_dir / "tagged_trades.csv",
            session_diagnostics_path=run_paths.run_dir / "session_diagnostics.csv",
            bucket_diagnostics_path=run_paths.run_dir / "bucket_diagnostics.csv",
            candidate_actions_path=run_paths.run_dir / "candidate_actions.csv",
            next_step_queue_path=run_paths.results_path,
            report_path=run_paths.report_path,
            run_artifact_dir=run_paths.run_dir,
        ),
        encoding="utf-8",
    )

    symbol = str(filtered_trades["instrument"].dropna().iloc[0]) if "instrument" in filtered_trades.columns and not filtered_trades.empty else None
    manifest = write_experiment_manifest(
        project_root=PROJECT_ROOT,
        paths=run_paths,
        experiment_name=EXPERIMENT_NAME,
        command="./.venv/Scripts/python.exe scripts/run_phase8k_fold_failure_diagnostic.py",
        config={
            **asdict(config),
            "source_phase8j_filtered_trade_log": "outputs/phase8j_filtered_trade_log.csv",
            "source_phase8j_fold_results": "outputs/phase8j_walk_forward_folds.csv",
            "source_phase8j_summary": "outputs/phase8j_walk_forward_summary.csv",
            "phase8j_label": str(phase8j_summary.iloc[0].get("phase8j_label", "unknown")) if not phase8j_summary.empty else "unknown",
            "source_trade_count": len(filtered_trades),
            "tagged_trade_count": len(tagged_trades),
            "session_diagnostic_rows": len(session_diagnostics),
            "bucket_diagnostic_rows": len(bucket_diagnostics),
            "candidate_action_rows": len(candidate_actions),
        },
        selected_specs_count=len(candidate_actions),
        results=next_step_queue,
        legacy_artifacts={
            "tagged_trades": tagged_trades_path,
            "session_diagnostics": session_diagnostics_path,
            "bucket_diagnostics": bucket_diagnostics_path,
            "candidate_actions": candidate_actions_path,
            "next_step_queue": next_step_queue_path,
            "report": report_path,
        },
        guardrails=GUARDRAILS,
        data_files=list_local_data_files(PROJECT_ROOT, symbol=symbol),
    )

    top_action = candidate_actions.iloc[0] if not candidate_actions.empty else None
    print("Phase 8K fold failure diagnostic complete.")
    print(f"Source Phase 8J trades: {len(filtered_trades)}")
    print(f"Tagged fold-trade rows: {len(tagged_trades)}")
    print(f"Session diagnostics: {len(session_diagnostics)}")
    print(f"Bucket diagnostics: {len(bucket_diagnostics)}")
    print(f"Candidate actions: {len(candidate_actions)}")
    print(f"Next steps: {len(next_step_queue)}")
    print(f"Report: {report_path}")
    print(f"Run artifacts: {run_paths.run_dir}")
    print(f"Manifest rows: {manifest['result_row_count']}")
    if top_action is not None:
        print(f"Top action: {top_action['action_rule']} ({top_action['phase8k_action_label']})")


if __name__ == "__main__":
    main()
