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
from short_term_edge.phase_common import ensure_directory, write_csv_artifact, write_json_artifact  # noqa: E402
from short_term_edge.phase10b_overnight_range_targeted_retest import (  # noqa: E402
    Phase10BConfig,
    build_phase10b_specs,
    make_phase10b_recommendation,
    recommendation_to_json,
    render_phase10b_report,
    run_phase10b_retest,
    serialize_phase10b_specs,
)

EXPERIMENT_NAME = "phase10b_overnight_range_targeted_retest"
GUARDRAILS = [
    "research/simulation only",
    "no live trading approval",
    "no broker adapters, order routing, API-key storage, webhooks, credential storage, automated execution, or LLM-driven trade decisions",
    "targeted 48-spec overnight-range diagnostic/retest only; no generalized optimizer",
]


def main() -> None:
    output_dir = PROJECT_ROOT / "outputs"
    report_dir = PROJECT_ROOT / "reports"
    ensure_directory(output_dir)
    ensure_directory(report_dir)
    config = Phase10BConfig(max_specs=int(os.environ.get("PHASE10B_MAX_SPECS", "48")))
    bars = _load_recent_mnq_bars(config.recent_sessions)
    result = run_phase10b_retest(bars, config)
    recommendation = make_phase10b_recommendation(result)
    run_paths = prepare_experiment_run(PROJECT_ROOT, EXPERIMENT_NAME, run_id=os.environ.get("EXPERIMENT_RUN_ID"))
    paths = {
        "candidate_results": output_dir / "phase10b_candidate_results.csv",
        "trade_logs": output_dir / "phase10b_trade_logs.csv",
        "walk_forward_folds": output_dir / "phase10b_walk_forward_folds.csv",
        "daily_pnl": output_dir / "phase10b_daily_pnl.csv",
        "concentration_diagnostics": output_dir / "phase10b_concentration_diagnostics.csv",
        "validation_failure_attribution": output_dir / "phase10b_validation_failure_attribution.csv",
        "range_regime_summary": output_dir / "phase10b_range_regime_summary.csv",
        "gap_regime_summary": output_dir / "phase10b_gap_regime_summary.csv",
        "touch_sequence_summary": output_dir / "phase10b_touch_sequence_summary.csv",
        "branch_summary": output_dir / "phase10b_branch_summary.csv",
        "exit_reason_summary": output_dir / "phase10b_exit_reason_summary.csv",
        "mfe_mae_summary": output_dir / "phase10b_mfe_mae_summary.csv",
        "strategy_specs": output_dir / "phase10b_strategy_specs.json",
        "recommendation": output_dir / "phase10b_next_action_recommendation.json",
    }
    report_path = report_dir / "phase10b_overnight_range_targeted_retest_report.md"
    for key, path in paths.items():
        if key == "strategy_specs":
            write_json_artifact([spec.to_dict() for spec in build_phase10b_specs(config)], path)
        elif key == "recommendation":
            write_json_artifact(recommendation, path)
        else:
            write_csv_artifact(result[key], path)
    report = render_phase10b_report(result, recommendation, report_path)
    report_path.write_text(report, encoding="utf-8")
    for key, df in result.items():
        if isinstance(df, pd.DataFrame):
            write_csv_artifact(df, run_paths.run_dir / f"{key}.csv")
    write_csv_artifact(result["candidate_results"], run_paths.results_path)
    run_paths.specs_path.write_text(serialize_phase10b_specs(build_phase10b_specs(config)), encoding="utf-8")
    run_paths.report_path.write_text(render_phase10b_report(result, recommendation, run_paths.report_path), encoding="utf-8")
    (run_paths.run_dir / "next_action_recommendation.json").write_text(recommendation_to_json(recommendation), encoding="utf-8")
    manifest = write_experiment_manifest(
        project_root=PROJECT_ROOT,
        paths=run_paths,
        experiment_name=EXPERIMENT_NAME,
        command="./.venv/Scripts/python.exe scripts/run_phase10b_overnight_range_targeted_retest.py",
        config={**asdict(config), "source_symbol": "MNQ", "source_rows": len(bars), "spec_count": len(build_phase10b_specs(config)), "trade_rows": len(result["trade_logs"]), "next_action": recommendation.get("next_action")},
        selected_specs_count=len(build_phase10b_specs(config)),
        results=result["candidate_results"],
        legacy_artifacts={**paths, "report": report_path},
        guardrails=GUARDRAILS,
        data_files=list_local_data_files(PROJECT_ROOT, symbol="MNQ"),
    )
    top = result["candidate_results"].iloc[0] if not result["candidate_results"].empty else None
    print("Phase 10B overnight range targeted retest complete.")
    print(f"Specs evaluated: {len(result['candidate_results'])}")
    print(f"Trade rows: {len(result['trade_logs'])}")
    print(f"Next action: {recommendation.get('next_action')}")
    if top is not None:
        print(f"Top candidate: {top['candidate_id']} ({top['phase10b_label']} / {top['research_axis_status']})")
        print(f"Top gross/net/stress/validation/holdout: {top['gross_pnl']} / {top['net_pnl']} / {top['stress_pnl']} / {top['validation_pnl']} / {top['holdout_pnl']}")
    print(f"Report: {report_path}")
    print(f"Run artifacts: {run_paths.run_dir}")
    print(f"Manifest rows: {manifest['result_row_count']}")


def _load_recent_mnq_bars(recent_sessions: int) -> pd.DataFrame:
    raw_dir = PROJECT_ROOT / "data" / "raw"
    files = [path for path in discover_data_files(raw_dir) if path.name.lower().startswith("mnq")]
    if not files:
        raise FileNotFoundError(f"No MNQ CSV files found under {raw_dir}")
    bars = pd.concat([load_ohlcv_csv(path) for path in files], ignore_index=True).sort_values(["symbol", "timestamp"])
    sessions = [s for s in sorted(bars["trading_session"].dropna().astype(str).unique().tolist()) if s != "2026-07-03"][-recent_sessions:]
    return bars[bars["trading_session"].astype(str).isin(sessions)].copy()


if __name__ == "__main__":
    main()
