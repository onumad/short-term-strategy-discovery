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
from short_term_edge.phase14a_prior_level_reaction_scout import (  # noqa: E402
    PARTIAL_SESSIONS,
    Phase14AConfig,
    build_phase14a_specs,
    make_phase14a_recommendation,
    recommendation_to_json,
    render_phase14a_report,
    run_phase14a_scout,
    serialize_phase14a_specs,
)

EXPERIMENT_NAME = "phase14a_prior_level_reaction_scout"
RUN_COMMAND = "EXPERIMENT_RUN_ID=phase14a-r1-smoke ./.venv/Scripts/python.exe scripts/run_phase14a_prior_level_reaction_scout.py"
GUARDRAILS = [
    "research/simulation only",
    "no live trading approval",
    "no broker adapters, order routing, API-key storage, webhooks, credential storage, automated execution, or LLM-driven trade decisions",
    "MNQ-only 48-spec prior RTH close/midpoint reaction scout; excludes MGC, prior RTH high/low breakout, overnight, OR fade, OD pullback, VWAP, and volatility compression",
]


def main() -> None:
    output_dir = PROJECT_ROOT / "outputs"
    report_dir = PROJECT_ROOT / "reports"
    ensure_directory(output_dir)
    ensure_directory(report_dir)
    config = Phase14AConfig(max_specs=int(os.environ.get("PHASE14A_MAX_SPECS", "48")))
    specs = build_phase14a_specs(config)
    bars = _load_recent_mnq_bars(config.recent_sessions)
    registry_matrix = _load_registry_matrix(output_dir)
    playbook_daily = pd.read_csv(output_dir / "portfolio_audit_b_portfolio_daily_pnl.csv")
    gap_features = pd.read_csv(output_dir / "playbook_gap_audit_a_market_day_features.csv")
    result = run_phase14a_scout(bars, registry_matrix, playbook_daily, gap_features, config)
    recommendation = make_phase14a_recommendation(result)
    run_paths = prepare_experiment_run(PROJECT_ROOT, EXPERIMENT_NAME, run_id=os.environ.get("EXPERIMENT_RUN_ID"))
    paths = {
        "candidate_results": output_dir / "phase14a_candidate_results.csv",
        "trade_logs": output_dir / "phase14a_trade_logs.csv",
        "daily_pnl": output_dir / "phase14a_daily_pnl.csv",
        "walk_forward_folds": output_dir / "phase14a_walk_forward_folds.csv",
        "concentration_diagnostics": output_dir / "phase14a_concentration_diagnostics.csv",
        "level_summary": output_dir / "phase14a_level_summary.csv",
        "interaction_family_summary": output_dir / "phase14a_interaction_family_summary.csv",
        "side_summary": output_dir / "phase14a_side_summary.csv",
        "confirmation_summary": output_dir / "phase14a_confirmation_summary.csv",
        "exit_variant_summary": output_dir / "phase14a_exit_variant_summary.csv",
        "correlation_to_registry": output_dir / "phase14a_correlation_to_registry.csv",
        "correlation_to_playbook": output_dir / "phase14a_correlation_to_playbook.csv",
        "gap_coverage_summary": output_dir / "phase14a_gap_coverage_summary.csv",
        "strategy_specs": output_dir / "phase14a_strategy_specs.json",
        "recommendation": output_dir / "phase14a_next_action_recommendation.json",
    }
    report_path = report_dir / "phase14a_prior_level_reaction_scout_report.md"
    for key, path in paths.items():
        if key == "strategy_specs":
            write_json_artifact([spec.to_dict() for spec in specs], path)
        elif key == "recommendation":
            write_json_artifact(recommendation, path)
        else:
            write_csv_artifact(result[key], path)
    report_path.write_text(render_phase14a_report(result, recommendation, report_path), encoding="utf-8")
    for key, df in result.items():
        if isinstance(df, pd.DataFrame):
            write_csv_artifact(df, run_paths.run_dir / f"{key}.csv")
    write_csv_artifact(result["candidate_results"], run_paths.results_path)
    run_paths.specs_path.write_text(serialize_phase14a_specs(specs), encoding="utf-8")
    run_paths.report_path.write_text(render_phase14a_report(result, recommendation, run_paths.report_path), encoding="utf-8")
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
    print("Phase 14A prior-level reaction scout complete.")
    print(f"Specs evaluated: {len(result['candidate_results'])}")
    print(f"Trade rows: {len(result['trade_logs'])}")
    print(f"Next action: {recommendation.get('next_action')}")
    if top is not None:
        print(f"Top candidate: {top['candidate_id']} ({top['phase14a_label']})")
        print(f"Top net/stress/validation/holdout/avg_corr/gap: {top['net_pnl']} / {top['stress_pnl']} / {top['validation_pnl']} / {top['holdout_pnl']} / {top['average_correlation_to_registry']} / {top['gap_days_covered']}")
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


def _load_registry_matrix(output_dir: Path) -> pd.DataFrame:
    registry = pd.read_csv(output_dir / "playbook_module_registry.csv")
    pieces = []
    for phase in ("phase10b", "phase11a", "phase12a", "phase13a"):
        path = output_dir / f"{phase}_daily_pnl.csv"
        if not path.exists():
            continue
        daily = pd.read_csv(path)
        if "candidate_id" not in daily.columns:
            continue
        allowed = set(registry.loc[registry["phase"].astype(str).eq(phase), "candidate_id"].astype(str))
        for cid, seg in daily[daily["candidate_id"].astype(str).isin(allowed)].groupby("candidate_id"):
            col = f"{phase}::{cid}"
            pieces.append(seg.groupby("trading_session", as_index=False)["net_pnl"].sum().rename(columns={"net_pnl": col}))
    if not pieces:
        return pd.DataFrame(columns=["trading_session"])
    matrix = pieces[0]
    for piece in pieces[1:]:
        matrix = matrix.merge(piece, on="trading_session", how="outer")
    return matrix.fillna(0.0).sort_values("trading_session").reset_index(drop=True)


if __name__ == "__main__":
    main()
