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
from short_term_edge.phase13a_uncorrelated_family_scout import (  # noqa: E402
    PARTIAL_SESSIONS,
    Phase13AConfig,
    build_phase13a_specs,
    make_phase13a_recommendation,
    recommendation_to_json,
    render_phase13a_report,
    run_phase13a_scout,
    serialize_phase13a_specs,
)

EXPERIMENT_NAME = "phase13a_uncorrelated_family_scout"
RUN_COMMAND = "EXPERIMENT_RUN_ID=phase13a-r1-smoke ./.venv/Scripts/python.exe scripts/run_phase13a_uncorrelated_family_scout.py"
GUARDRAILS = [
    "research/simulation only",
    "no live trading approval",
    "no broker adapters, order routing, API-key storage, webhooks, credential storage, automated execution, or LLM-driven trade decisions",
    "MNQ-only 48-spec uncorrelated family scout; excludes overnight-range, OR fade, OD pullback, VWAP, VCB, and MGC",
]


def main() -> None:
    output_dir = PROJECT_ROOT / "outputs"
    report_dir = PROJECT_ROOT / "reports"
    ensure_directory(output_dir)
    ensure_directory(report_dir)
    config = Phase13AConfig(max_specs=int(os.environ.get("PHASE13A_MAX_SPECS", "48")))
    specs = build_phase13a_specs(config)
    bars = _load_recent_mnq_bars(config.recent_sessions)
    registry_matrix = pd.read_csv(output_dir / "portfolio_audit_a_daily_pnl_matrix.csv")
    portfolio_daily = pd.read_csv(output_dir / "portfolio_audit_a_portfolio_daily_pnl.csv")
    result = run_phase13a_scout(bars, registry_matrix, portfolio_daily, config)
    recommendation = make_phase13a_recommendation(result)
    run_paths = prepare_experiment_run(PROJECT_ROOT, EXPERIMENT_NAME, run_id=os.environ.get("EXPERIMENT_RUN_ID"))
    paths = {
        "candidate_results": output_dir / "phase13a_candidate_results.csv",
        "trade_logs": output_dir / "phase13a_trade_logs.csv",
        "daily_pnl": output_dir / "phase13a_daily_pnl.csv",
        "walk_forward_folds": output_dir / "phase13a_walk_forward_folds.csv",
        "concentration_diagnostics": output_dir / "phase13a_concentration_diagnostics.csv",
        "family_summary": output_dir / "phase13a_family_summary.csv",
        "side_summary": output_dir / "phase13a_side_summary.csv",
        "entry_model_summary": output_dir / "phase13a_entry_model_summary.csv",
        "exit_variant_summary": output_dir / "phase13a_exit_variant_summary.csv",
        "correlation_to_registry": output_dir / "phase13a_correlation_to_registry.csv",
        "correlation_to_portfolios": output_dir / "phase13a_correlation_to_portfolios.csv",
        "strategy_specs": output_dir / "phase13a_strategy_specs.json",
        "recommendation": output_dir / "phase13a_next_action_recommendation.json",
    }
    report_path = report_dir / "phase13a_uncorrelated_family_scout_report.md"
    for key, path in paths.items():
        if key == "strategy_specs":
            write_json_artifact([spec.to_dict() for spec in specs], path)
        elif key == "recommendation":
            write_json_artifact(recommendation, path)
        else:
            write_csv_artifact(result[key], path)
    report_path.write_text(render_phase13a_report(result, recommendation, report_path), encoding="utf-8")
    for key, df in result.items():
        if isinstance(df, pd.DataFrame):
            write_csv_artifact(df, run_paths.run_dir / f"{key}.csv")
    write_csv_artifact(result["candidate_results"], run_paths.results_path)
    run_paths.specs_path.write_text(serialize_phase13a_specs(specs), encoding="utf-8")
    run_paths.report_path.write_text(render_phase13a_report(result, recommendation, run_paths.report_path), encoding="utf-8")
    (run_paths.run_dir / "next_action_recommendation.json").write_text(recommendation_to_json(recommendation), encoding="utf-8")
    manifest = write_experiment_manifest(
        project_root=PROJECT_ROOT,
        paths=run_paths,
        experiment_name=EXPERIMENT_NAME,
        command=RUN_COMMAND,
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
    print("Phase 13A uncorrelated family scout complete.")
    print(f"Specs evaluated: {len(result['candidate_results'])}")
    print(f"Trade rows: {len(result['trade_logs'])}")
    print(f"Next action: {recommendation.get('next_action')}")
    if top is not None:
        print(f"Top candidate: {top['candidate_id']} ({top['phase13a_label']})")
        print(f"Top net/stress/validation/holdout/corr: {top['net_pnl']} / {top['stress_pnl']} / {top['validation_pnl']} / {top['holdout_pnl']} / {top['average_correlation_to_registry']}")
    print(f"Report: {report_path}")
    print(f"Run artifacts: {run_paths.run_dir}")
    print(f"Manifest rows: {manifest['result_row_count']}")
    print("Research/simulation only. No live trading, broker adapters, order routing, webhooks, credential storage, automated execution, or LLM-driven trade decisions.")


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
