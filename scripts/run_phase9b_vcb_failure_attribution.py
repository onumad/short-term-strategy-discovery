from __future__ import annotations

import os
import sys
from dataclasses import asdict
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from short_term_edge.data_loader import discover_data_files, load_ohlcv_csv  # noqa: E402
from short_term_edge.experiments.artifacts import list_local_data_files, prepare_experiment_run, write_experiment_manifest  # noqa: E402
from short_term_edge.phase9b_vcb_failure_attribution import (  # noqa: E402
    Phase9BConfig,
    build_phase9b_specs,
    make_phase9b_recommendation,
    recommendation_to_json,
    render_phase9b_report,
    run_phase9b_diagnostic,
)

EXPERIMENT_NAME = "phase9b_vcb_failure_attribution"
GUARDRAILS = [
    "research/simulation only",
    "no live trading approval",
    "no broker adapters, order routing, API-key storage, webhooks, or automated execution",
    "diagnostic-only failure attribution; no candidate promotion and no generalized optimizer",
]


def main() -> None:
    output_dir = PROJECT_ROOT / "outputs"
    report_dir = PROJECT_ROOT / "reports"
    output_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)

    config = Phase9BConfig(max_specs=int(os.environ.get("PHASE9B_MAX_SPECS", "48")))
    bars = _load_recent_mnq_bars(config.recent_sessions)
    result = run_phase9b_diagnostic(bars, config)
    recommendation = make_phase9b_recommendation(result)
    run_paths = prepare_experiment_run(PROJECT_ROOT, EXPERIMENT_NAME, run_id=os.environ.get("EXPERIMENT_RUN_ID"))

    paths = {
        "trade_attribution": output_dir / "phase9b_trade_attribution.csv",
        "side_summary": output_dir / "phase9b_side_summary.csv",
        "time_bucket_summary": output_dir / "phase9b_time_bucket_summary.csv",
        "exit_reason_summary": output_dir / "phase9b_exit_reason_summary.csv",
        "session_loss_summary": output_dir / "phase9b_session_loss_summary.csv",
        "mfe_mae_summary": output_dir / "phase9b_mfe_mae_summary.csv",
        "entry_timing_diagnostic": output_dir / "phase9b_entry_timing_diagnostic.csv",
        "stop_target_diagnostic": output_dir / "phase9b_stop_target_diagnostic.csv",
        "candidate_results": output_dir / "phase9b_candidate_results.csv",
        "specs": output_dir / "phase9b_strategy_specs.csv",
        "recommendation": output_dir / "phase9b_next_action_recommendation.json",
    }
    report_path = report_dir / "phase9b_vcb_failure_attribution_report.md"

    result["trades"].to_csv(paths["trade_attribution"], index=False)
    result["side_summary"].to_csv(paths["side_summary"], index=False)
    result["time_bucket_summary"].to_csv(paths["time_bucket_summary"], index=False)
    result["exit_reason_summary"].to_csv(paths["exit_reason_summary"], index=False)
    result["session_loss_summary"].to_csv(paths["session_loss_summary"], index=False)
    result["mfe_mae_summary"].to_csv(paths["mfe_mae_summary"], index=False)
    result["entry_timing_diagnostic"].to_csv(paths["entry_timing_diagnostic"], index=False)
    result["stop_target_diagnostic"].to_csv(paths["stop_target_diagnostic"], index=False)
    result["candidate_results"].to_csv(paths["candidate_results"], index=False)
    result["specs"].to_csv(paths["specs"], index=False)
    paths["recommendation"].write_text(recommendation_to_json(recommendation), encoding="utf-8")

    for key, df in result.items():
        if isinstance(df, pd.DataFrame):
            df.to_csv(run_paths.run_dir / f"{key}.csv", index=False)
    (run_paths.run_dir / "next_action_recommendation.json").write_text(recommendation_to_json(recommendation), encoding="utf-8")

    report = render_phase9b_report(result, recommendation, report_path)
    report_path.write_text(report, encoding="utf-8")
    run_paths.report_path.write_text(render_phase9b_report(result, recommendation, run_paths.report_path), encoding="utf-8")
    result["candidate_results"].to_csv(run_paths.results_path, index=False)
    result["specs"].to_csv(run_paths.specs_path, index=False)

    manifest = write_experiment_manifest(
        project_root=PROJECT_ROOT,
        paths=run_paths,
        experiment_name=EXPERIMENT_NAME,
        command="./.venv/Scripts/python.exe scripts/run_phase9b_vcb_failure_attribution.py",
        config={**asdict(config), "source_symbol": "MNQ", "source_rows": len(bars), "spec_count": len(build_phase9b_specs(config)), "trade_rows": len(result["trades"]), "next_action": recommendation.get("next_action")},
        selected_specs_count=len(build_phase9b_specs(config)),
        results=result["candidate_results"],
        legacy_artifacts={**paths, "report": report_path},
        guardrails=GUARDRAILS,
        data_files=list_local_data_files(PROJECT_ROOT, symbol="MNQ"),
    )

    print("Phase 9B VCB failure attribution complete.")
    print(f"Specs evaluated: {len(result['candidate_results'])}")
    print(f"Trade attribution rows: {len(result['trades'])}")
    print(f"Next action: {recommendation.get('next_action')}")
    print(f"Report: {report_path}")
    print(f"Run artifacts: {run_paths.run_dir}")
    print(f"Manifest rows: {manifest['result_row_count']}")


def _load_recent_mnq_bars(recent_sessions: int) -> pd.DataFrame:
    raw_dir = PROJECT_ROOT / "data" / "raw"
    files = [path for path in discover_data_files(raw_dir) if path.name.lower().startswith("mnq")]
    if not files:
        raise FileNotFoundError(f"No MNQ CSV files found under {raw_dir}")
    bars = pd.concat([load_ohlcv_csv(path) for path in files], ignore_index=True).sort_values(["symbol", "timestamp"])
    sessions = sorted(bars["trading_session"].dropna().astype(str).unique().tolist())[-recent_sessions:]
    return bars[bars["trading_session"].astype(str).isin(sessions)].copy()


if __name__ == "__main__":
    main()
