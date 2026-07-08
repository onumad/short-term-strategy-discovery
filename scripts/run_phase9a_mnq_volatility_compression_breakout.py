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

from short_term_edge.data_loader import discover_data_files, load_ohlcv_csv  # noqa: E402
from short_term_edge.experiments.artifacts import list_local_data_files, prepare_experiment_run, write_experiment_manifest  # noqa: E402
from short_term_edge.phase9a_volatility_compression_breakout import (  # noqa: E402
    Phase9AConfig,
    build_phase9a_specs,
    evaluate_phase9a_candidates,
    render_phase9a_report,
    specs_to_json,
)

EXPERIMENT_NAME = "phase9a_mnq_volatility_compression_breakout"
GUARDRAILS = [
    "research/simulation only",
    "no live trading approval",
    "no broker adapters, order routing, API-key storage, webhooks, or automated execution",
    "bounded MNQ volatility-compression breakout probe only; no paper-trading promotion",
]


def main() -> None:
    output_dir = PROJECT_ROOT / "outputs"
    report_dir = PROJECT_ROOT / "reports"
    output_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)

    config = Phase9AConfig(max_specs=int(os.environ.get("PHASE9A_MAX_SPECS", "24")))
    specs = build_phase9a_specs(config)
    bars = _load_mnq_bars()
    results, trade_logs, folds, daily_pnl, concentration = evaluate_phase9a_candidates(bars, specs, config)

    run_paths = prepare_experiment_run(PROJECT_ROOT, EXPERIMENT_NAME, run_id=os.environ.get("EXPERIMENT_RUN_ID"))
    results_path = output_dir / "phase9a_candidate_results.csv"
    trade_logs_path = output_dir / "phase9a_trade_logs.csv"
    folds_path = output_dir / "phase9a_walk_forward_folds.csv"
    daily_path = output_dir / "phase9a_daily_pnl.csv"
    concentration_path = output_dir / "phase9a_concentration_diagnostics.csv"
    specs_path = output_dir / "phase9a_strategy_specs.json"
    report_path = report_dir / "phase9a_mnq_volatility_compression_breakout_report.md"

    results.to_csv(results_path, index=False)
    trade_logs.to_csv(trade_logs_path, index=False)
    folds.to_csv(folds_path, index=False)
    daily_pnl.to_csv(daily_path, index=False)
    concentration.to_csv(concentration_path, index=False)
    specs_path.write_text(specs_to_json(specs), encoding="utf-8")

    results.to_csv(run_paths.results_path, index=False)
    trade_logs.to_csv(run_paths.run_dir / "trade_logs.csv", index=False)
    folds.to_csv(run_paths.run_dir / "walk_forward_folds.csv", index=False)
    daily_pnl.to_csv(run_paths.run_dir / "daily_pnl.csv", index=False)
    concentration.to_csv(run_paths.run_dir / "concentration_diagnostics.csv", index=False)
    run_paths.specs_path.write_text(specs_to_json(specs), encoding="utf-8")

    report = render_phase9a_report(
        results,
        config,
        results_path=results_path,
        trade_logs_path=trade_logs_path,
        folds_path=folds_path,
        daily_path=daily_path,
        concentration_path=concentration_path,
        specs_path=specs_path,
        report_path=report_path,
        run_artifact_dir=run_paths.run_dir,
    )
    report_path.write_text(report, encoding="utf-8")
    run_paths.report_path.write_text(
        render_phase9a_report(
            results,
            config,
            results_path=run_paths.results_path,
            trade_logs_path=run_paths.run_dir / "trade_logs.csv",
            folds_path=run_paths.run_dir / "walk_forward_folds.csv",
            daily_path=run_paths.run_dir / "daily_pnl.csv",
            concentration_path=run_paths.run_dir / "concentration_diagnostics.csv",
            specs_path=run_paths.specs_path,
            report_path=run_paths.report_path,
            run_artifact_dir=run_paths.run_dir,
        ),
        encoding="utf-8",
    )

    manifest = write_experiment_manifest(
        project_root=PROJECT_ROOT,
        paths=run_paths,
        experiment_name=EXPERIMENT_NAME,
        command="./.venv/Scripts/python.exe scripts/run_phase9a_mnq_volatility_compression_breakout.py",
        config={**asdict(config), "source_symbol": "MNQ", "source_rows": len(bars), "spec_count": len(specs), "trade_log_rows": len(trade_logs), "fold_rows": len(folds)},
        selected_specs_count=len(specs),
        results=results,
        legacy_artifacts={"results": results_path, "trade_logs": trade_logs_path, "folds": folds_path, "daily_pnl": daily_path, "concentration": concentration_path, "specs": specs_path, "report": report_path},
        guardrails=GUARDRAILS,
        data_files=list_local_data_files(PROJECT_ROOT, symbol="MNQ"),
    )

    top = results.iloc[0] if not results.empty else None
    print("Phase 9A MNQ volatility compression breakout complete.")
    print(f"Specs evaluated: {len(specs)}")
    print(f"Rows: {len(results)}")
    print(f"Trade log rows: {len(trade_logs)}")
    print(f"Report: {report_path}")
    print(f"Run artifacts: {run_paths.run_dir}")
    print(f"Manifest rows: {manifest['result_row_count']}")
    if top is not None:
        print(f"Top candidate: {top['candidate_id']} ({top['phase9a_label']})")
        print(f"Top net/stress/WF stress: {top['net_pnl']} / {top['stress_pnl']} / {top['walk_forward_stress_pnl']}")
        print(f"Top notes: {top['reject_reasons']}")


def _load_mnq_bars() -> pd.DataFrame:
    raw_dir = PROJECT_ROOT / "data" / "raw"
    files = [path for path in discover_data_files(raw_dir) if path.name.lower().startswith("mnq")]
    if not files:
        raise FileNotFoundError(f"No MNQ CSV files found under {raw_dir}")
    bars = pd.concat([load_ohlcv_csv(path) for path in files], ignore_index=True).sort_values(["symbol", "timestamp"])
    sessions = sorted(bars["trading_session"].dropna().astype(str).unique().tolist())[-252:]
    return bars[bars["trading_session"].astype(str).isin(sessions)].copy()


if __name__ == "__main__":
    main()
