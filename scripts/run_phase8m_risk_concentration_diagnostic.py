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
from short_term_edge.phase8m_risk_concentration_diagnostic import (  # noqa: E402
    Phase8MConfig,
    build_phase8m_candidate_specs,
    evaluate_phase8m_candidates,
    remap_phase8m_exits,
    render_phase8m_report,
)

EXPERIMENT_NAME = "phase8m_mnq_vwap_risk_exit_concentration"
GUARDRAILS = [
    "research/simulation only",
    "no live trading approval",
    "no broker adapters, order routing, API-key storage, webhooks, or automated execution",
    "bounded risk/exit/concentration diagnostic only; no paper-trading promotion",
]


def main() -> None:
    output_dir = PROJECT_ROOT / "outputs"
    report_dir = PROJECT_ROOT / "reports"
    output_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)

    source_trades_path = output_dir / "phase8j_filtered_trade_log.csv"
    if not source_trades_path.exists():
        raise FileNotFoundError(f"Phase 8M requires prior artifact: {source_trades_path}")
    raw_files = discover_data_files(PROJECT_ROOT / "data" / "raw")
    mnq_files = [path for path in raw_files if path.name.lower().startswith("mnq")]
    if not mnq_files:
        raise FileNotFoundError("Phase 8M requires an MNQ raw CSV under data/raw")
    raw_path = mnq_files[-1]

    source_trades = pd.read_csv(source_trades_path)
    mnq_bars = load_ohlcv_csv(raw_path)
    config = Phase8MConfig(max_specs=int(os.environ.get("PHASE8M_MAX_SPECS", "192")))
    specs = build_phase8m_candidate_specs(config)
    remapped_trades = remap_phase8m_exits(source_trades, mnq_bars, config)
    results, filtered_logs, folds, daily_pnl, concentration, outliers = evaluate_phase8m_candidates(remapped_trades, specs, config)

    run_paths = prepare_experiment_run(PROJECT_ROOT, EXPERIMENT_NAME, run_id=os.environ.get("EXPERIMENT_RUN_ID"))
    results_path = output_dir / "phase8m_candidate_results.csv"
    filtered_trade_logs_path = output_dir / "phase8m_filtered_trade_logs.csv"
    fold_results_path = output_dir / "phase8m_walk_forward_folds.csv"
    daily_pnl_path = output_dir / "phase8m_daily_pnl.csv"
    concentration_path = output_dir / "phase8m_concentration_diagnostics.csv"
    outlier_path = output_dir / "phase8m_outlier_session_diagnostics.csv"
    specs_path = output_dir / "phase8m_strategy_specs.json"
    remapped_trades_path = output_dir / "phase8m_exit_remapped_trades.csv"
    report_path = report_dir / "phase8m_risk_concentration_diagnostic_report.md"

    specs_payload = [spec.to_dict() for spec in specs]
    results.to_csv(results_path, index=False)
    filtered_logs.to_csv(filtered_trade_logs_path, index=False)
    folds.to_csv(fold_results_path, index=False)
    daily_pnl.to_csv(daily_pnl_path, index=False)
    concentration.to_csv(concentration_path, index=False)
    outliers.to_csv(outlier_path, index=False)
    remapped_trades.to_csv(remapped_trades_path, index=False)
    specs_path.write_text(json.dumps(specs_payload, indent=2, sort_keys=True), encoding="utf-8")

    results.to_csv(run_paths.results_path, index=False)
    filtered_logs.to_csv(run_paths.run_dir / "filtered_trade_logs.csv", index=False)
    folds.to_csv(run_paths.run_dir / "walk_forward_folds.csv", index=False)
    daily_pnl.to_csv(run_paths.run_dir / "daily_pnl.csv", index=False)
    concentration.to_csv(run_paths.run_dir / "concentration_diagnostics.csv", index=False)
    outliers.to_csv(run_paths.run_dir / "outlier_session_diagnostics.csv", index=False)
    remapped_trades.to_csv(run_paths.run_dir / "exit_remapped_trades.csv", index=False)
    run_paths.specs_path.write_text(json.dumps(specs_payload, indent=2, sort_keys=True), encoding="utf-8")

    report = render_phase8m_report(
        results,
        folds,
        concentration,
        outliers,
        config,
        results_path=results_path,
        filtered_trade_logs_path=filtered_trade_logs_path,
        fold_results_path=fold_results_path,
        daily_pnl_path=daily_pnl_path,
        concentration_path=concentration_path,
        outlier_path=outlier_path,
        specs_path=specs_path,
        report_path=report_path,
        run_artifact_dir=run_paths.run_dir,
    )
    report_path.write_text(report, encoding="utf-8")
    run_paths.report_path.write_text(
        render_phase8m_report(
            results,
            folds,
            concentration,
            outliers,
            config,
            results_path=run_paths.results_path,
            filtered_trade_logs_path=run_paths.run_dir / "filtered_trade_logs.csv",
            fold_results_path=run_paths.run_dir / "walk_forward_folds.csv",
            daily_pnl_path=run_paths.run_dir / "daily_pnl.csv",
            concentration_path=run_paths.run_dir / "concentration_diagnostics.csv",
            outlier_path=run_paths.run_dir / "outlier_session_diagnostics.csv",
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
        command="./.venv/Scripts/python.exe scripts/run_phase8m_risk_concentration_diagnostic.py",
        config={
            **asdict(config),
            "source_phase8j_filtered_trade_log": "outputs/phase8j_filtered_trade_log.csv",
            "source_trade_count": len(source_trades),
            "exit_remapped_trade_count": len(remapped_trades),
            "filtered_log_rows": len(filtered_logs),
            "fold_rows": len(folds),
            "daily_pnl_rows": len(daily_pnl),
            "concentration_rows": len(concentration),
            "outlier_rows": len(outliers),
            "raw_data_file": raw_path.relative_to(PROJECT_ROOT).as_posix(),
        },
        selected_specs_count=len(specs),
        results=results,
        legacy_artifacts={
            "results": results_path,
            "filtered_trade_logs": filtered_trade_logs_path,
            "fold_results": fold_results_path,
            "daily_pnl": daily_pnl_path,
            "concentration": concentration_path,
            "outliers": outlier_path,
            "specs": specs_path,
            "exit_remapped_trades": remapped_trades_path,
            "report": report_path,
        },
        guardrails=GUARDRAILS,
        data_files=list_local_data_files(PROJECT_ROOT, symbol="MNQ"),
    )

    top = results.iloc[0] if not results.empty else None
    print("Phase 8M MNQ VWAP risk/exit/concentration diagnostic complete.")
    print(f"Source Phase 8J trades: {len(source_trades)}")
    print(f"Exit-remapped trades: {len(remapped_trades)}")
    print(f"Specs evaluated: {len(specs)}")
    print(f"Results rows: {len(results)}")
    print(f"Filtered log rows: {len(filtered_logs)}")
    print(f"Fold rows: {len(folds)}")
    print(f"Report: {report_path}")
    print(f"Run artifacts: {run_paths.run_dir}")
    print(f"Manifest rows: {manifest['result_row_count']}")
    if top is not None:
        print(f"Top candidate: {top['candidate_id']} ({top['phase8m_label']})")
        print(f"Top net/stress/WF stress: {top['net_pnl']} / {top['stress_pnl']} / {top['walk_forward_stress_pnl']}")
        print(f"Top notes: {top['reject_reasons']}")


if __name__ == "__main__":
    main()
