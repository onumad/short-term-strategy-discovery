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
from short_term_edge.phase9c_vcb_targeted_retest import (  # noqa: E402
    Phase9CConfig,
    build_phase9c_specs,
    make_phase9c_recommendation,
    recommendation_to_json,
    render_phase9c_report,
    run_phase9c_retest,
    serialize_phase9c_specs,
)

EXPERIMENT_NAME = "phase9c_vcb_targeted_retest"
GUARDRAILS = [
    "research/simulation only",
    "no live trading approval",
    "no broker adapters, order routing, API-key storage, webhooks, or automated execution",
    "targeted short-only retest only; no generalized optimizer",
]


def main() -> None:
    output_dir = PROJECT_ROOT / "outputs"
    report_dir = PROJECT_ROOT / "reports"
    output_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)
    config = Phase9CConfig(max_specs=int(os.environ.get("PHASE9C_MAX_SPECS", "48")))
    bars = _load_recent_mnq_bars(config.recent_sessions)
    result = run_phase9c_retest(bars, config)
    recommendation = make_phase9c_recommendation(result)
    run_paths = prepare_experiment_run(PROJECT_ROOT, EXPERIMENT_NAME, run_id=os.environ.get("EXPERIMENT_RUN_ID"))

    paths = {
        "candidate_results": output_dir / "phase9c_candidate_results.csv",
        "trade_logs": output_dir / "phase9c_trade_logs.csv",
        "walk_forward_folds": output_dir / "phase9c_walk_forward_folds.csv",
        "daily_pnl": output_dir / "phase9c_daily_pnl.csv",
        "concentration_diagnostics": output_dir / "phase9c_concentration_diagnostics.csv",
        "exit_reason_summary": output_dir / "phase9c_exit_reason_summary.csv",
        "stop_failure_summary": output_dir / "phase9c_stop_failure_summary.csv",
        "time_window_summary": output_dir / "phase9c_time_window_summary.csv",
        "strategy_specs": output_dir / "phase9c_strategy_specs.json",
        "recommendation": output_dir / "phase9c_next_action_recommendation.json",
    }
    report_path = report_dir / "phase9c_vcb_targeted_retest_report.md"

    result["candidate_results"].to_csv(paths["candidate_results"], index=False)
    result["trade_logs"].to_csv(paths["trade_logs"], index=False)
    result["walk_forward_folds"].to_csv(paths["walk_forward_folds"], index=False)
    result["daily_pnl"].to_csv(paths["daily_pnl"], index=False)
    result["concentration_diagnostics"].to_csv(paths["concentration_diagnostics"], index=False)
    result["exit_reason_summary"].to_csv(paths["exit_reason_summary"], index=False)
    result["stop_failure_summary"].to_csv(paths["stop_failure_summary"], index=False)
    result["time_window_summary"].to_csv(paths["time_window_summary"], index=False)
    paths["strategy_specs"].write_text(serialize_phase9c_specs(build_phase9c_specs(config)), encoding="utf-8")
    paths["recommendation"].write_text(recommendation_to_json(recommendation), encoding="utf-8")

    for key, df in result.items():
        if isinstance(df, pd.DataFrame):
            df.to_csv(run_paths.run_dir / f"{key}.csv", index=False)
    result["candidate_results"].to_csv(run_paths.results_path, index=False)
    run_paths.specs_path.write_text(serialize_phase9c_specs(build_phase9c_specs(config)), encoding="utf-8")
    (run_paths.run_dir / "next_action_recommendation.json").write_text(recommendation_to_json(recommendation), encoding="utf-8")

    report = render_phase9c_report(result, recommendation, report_path)
    report_path.write_text(report, encoding="utf-8")
    run_paths.report_path.write_text(render_phase9c_report(result, recommendation, run_paths.report_path), encoding="utf-8")

    manifest = write_experiment_manifest(
        project_root=PROJECT_ROOT,
        paths=run_paths,
        experiment_name=EXPERIMENT_NAME,
        command="./.venv/Scripts/python.exe scripts/run_phase9c_vcb_targeted_retest.py",
        config={**asdict(config), "source_symbol": "MNQ", "source_rows": len(bars), "spec_count": len(build_phase9c_specs(config)), "trade_rows": len(result["trade_logs"]), "next_action": recommendation.get("next_action")},
        selected_specs_count=len(build_phase9c_specs(config)),
        results=result["candidate_results"],
        legacy_artifacts={**paths, "report": report_path},
        guardrails=GUARDRAILS,
        data_files=list_local_data_files(PROJECT_ROOT, symbol="MNQ"),
    )
    top = result["candidate_results"].iloc[0] if not result["candidate_results"].empty else None
    print("Phase 9C VCB targeted retest complete.")
    print(f"Specs evaluated: {len(result['candidate_results'])}")
    print(f"Trade rows: {len(result['trade_logs'])}")
    print(f"Next action: {recommendation.get('next_action')}")
    if top is not None:
        print(f"Top candidate: {top['candidate_id']} ({top['phase9c_label']})")
        print(f"Top net/stress/validation/holdout: {top['net_pnl']} / {top['stress_pnl']} / {top['validation_pnl']} / {top['holdout_pnl']}")
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
