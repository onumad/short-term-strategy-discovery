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
from short_term_edge.phase11a_opening_range_fade_confirmation import (  # noqa: E402
    PARTIAL_SESSIONS,
    Phase11AConfig,
    build_phase11a_specs,
    make_phase11a_recommendation,
    recommendation_to_json,
    render_phase11a_report,
    run_phase11a_retest,
    serialize_phase11a_specs,
)

EXPERIMENT_NAME = "phase11a_opening_range_fade_confirmation"
GUARDRAILS = [
    "research/simulation only",
    "no live trading approval",
    "no broker adapters, order routing, API-key storage, webhooks, credential storage, automated execution, or LLM-driven trade decisions",
    "MNQ-only 48-spec RTH opening-range fade confirmation test; no overnight-derived filters",
]


def main() -> None:
    output_dir = PROJECT_ROOT / "outputs"
    report_dir = PROJECT_ROOT / "reports"
    ensure_directory(output_dir)
    ensure_directory(report_dir)
    config = Phase11AConfig(max_specs=int(os.environ.get("PHASE11A_MAX_SPECS", "48")))
    specs = build_phase11a_specs(config)
    bars = _load_recent_mnq_bars(config.recent_sessions)
    result = run_phase11a_retest(bars, config)
    recommendation = make_phase11a_recommendation(result)
    run_paths = prepare_experiment_run(PROJECT_ROOT, EXPERIMENT_NAME, run_id=os.environ.get("EXPERIMENT_RUN_ID"))
    paths = {
        "candidate_results": output_dir / "phase11a_candidate_results.csv",
        "trade_logs": output_dir / "phase11a_trade_logs.csv",
        "walk_forward_folds": output_dir / "phase11a_walk_forward_folds.csv",
        "daily_pnl": output_dir / "phase11a_daily_pnl.csv",
        "concentration_diagnostics": output_dir / "phase11a_concentration_diagnostics.csv",
        "or_window_summary": output_dir / "phase11a_or_window_summary.csv",
        "side_summary": output_dir / "phase11a_side_summary.csv",
        "entry_window_summary": output_dir / "phase11a_entry_window_summary.csv",
        "confirmation_summary": output_dir / "phase11a_confirmation_summary.csv",
        "exit_variant_summary": output_dir / "phase11a_exit_variant_summary.csv",
        "exit_reason_summary": output_dir / "phase11a_exit_reason_summary.csv",
        "touch_sequence_summary": output_dir / "phase11a_touch_sequence_summary.csv",
        "opening_range_width_summary": output_dir / "phase11a_opening_range_width_summary.csv",
        "sweep_distance_summary": output_dir / "phase11a_sweep_distance_summary.csv",
        "mfe_mae_summary": output_dir / "phase11a_mfe_mae_summary.csv",
        "invalid_risk_summary": output_dir / "phase11a_invalid_risk_summary.csv",
        "strategy_specs": output_dir / "phase11a_strategy_specs.json",
        "recommendation": output_dir / "phase11a_next_action_recommendation.json",
    }
    report_path = report_dir / "phase11a_opening_range_fade_confirmation_report.md"
    for key, path in paths.items():
        if key == "strategy_specs":
            write_json_artifact([spec.to_dict() for spec in specs], path)
        elif key == "recommendation":
            write_json_artifact(recommendation, path)
        else:
            write_csv_artifact(result[key], path)
    report = render_phase11a_report(result, recommendation, report_path)
    report_path.write_text(report, encoding="utf-8")
    for key, df in result.items():
        if isinstance(df, pd.DataFrame):
            write_csv_artifact(df, run_paths.run_dir / f"{key}.csv")
    write_csv_artifact(result["candidate_results"], run_paths.results_path)
    run_paths.specs_path.write_text(serialize_phase11a_specs(specs), encoding="utf-8")
    run_paths.report_path.write_text(render_phase11a_report(result, recommendation, run_paths.report_path), encoding="utf-8")
    (run_paths.run_dir / "next_action_recommendation.json").write_text(recommendation_to_json(recommendation), encoding="utf-8")
    manifest = write_experiment_manifest(
        project_root=PROJECT_ROOT,
        paths=run_paths,
        experiment_name=EXPERIMENT_NAME,
        command="EXPERIMENT_RUN_ID=phase11a-r1-smoke ./.venv/Scripts/python.exe scripts/run_phase11a_opening_range_fade_confirmation.py",
        config={
            **asdict(config),
            "source_symbol": "MNQ",
            "source_rows": len(bars),
            "spec_count": len(specs),
            "trade_rows": len(result["trade_logs"]),
            "excluded_partial_sessions": sorted(PARTIAL_SESSIONS),
            "next_action": recommendation.get("next_action"),
        },
        selected_specs_count=len(specs),
        results=result["candidate_results"],
        legacy_artifacts={**paths, "report": report_path},
        guardrails=GUARDRAILS,
        data_files=list_local_data_files(PROJECT_ROOT, symbol="MNQ"),
    )
    top = result["candidate_results"].iloc[0] if not result["candidate_results"].empty else None
    print("Phase 11A opening range fade confirmation complete.")
    print(f"Specs evaluated: {len(result['candidate_results'])}")
    print(f"Trade rows: {len(result['trade_logs'])}")
    print(f"Next action: {recommendation.get('next_action')}")
    if top is not None:
        print(f"Top candidate: {top['candidate_id']} ({top['phase11a_label']} / {top['research_axis_status']})")
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
    sessions = [s for s in sorted(bars["trading_session"].dropna().astype(str).unique().tolist()) if s not in PARTIAL_SESSIONS][-recent_sessions:]
    return bars[bars["trading_session"].astype(str).isin(sessions)].copy()


if __name__ == "__main__":
    main()
