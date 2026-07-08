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
from short_term_edge.phase8h_mnq_vwap_concentration_exit_diagnostic import (  # noqa: E402
    Phase8HConfig,
    render_phase8h_report,
    replay_phase8h_trades,
    run_phase8h_exit_shape_grid,
    select_phase8h_inputs,
    summarize_phase8h_concentration,
    summarize_phase8h_overlap,
)

EXPERIMENT_NAME = "phase8h_mnq_vwap_concentration_exit_diagnostic"
GUARDRAILS = [
    "research/simulation only",
    "no live trading approval",
    "no broker adapters, order routing, API-key storage, webhooks, or automated execution",
    "concentration and exit diagnostics only; no paper-trading promotion",
]
RECENT_SESSIONS = 180


def main() -> None:
    output_dir = PROJECT_ROOT / "outputs"
    report_dir = PROJECT_ROOT / "reports"
    output_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)

    event_path = output_dir / "phase8e_event_scout_results.csv"
    phase8g_path = output_dir / "phase8g_event_execution_calibration.csv"
    if not event_path.exists():
        raise FileNotFoundError(f"Phase 8H requires Phase 8E results: {event_path}")
    if not phase8g_path.exists():
        raise FileNotFoundError(f"Phase 8H requires Phase 8G results: {phase8g_path}")

    event_results = pd.read_csv(event_path)
    phase8g_results = pd.read_csv(phase8g_path)
    config = Phase8HConfig()
    selected = select_phase8h_inputs(event_results, phase8g_results, config)
    if selected.empty:
        raise ValueError("Phase 8H found no positive/stress-positive MNQ VWAP Phase 8G horizon-close rows")

    run_paths = prepare_experiment_run(PROJECT_ROOT, EXPERIMENT_NAME, run_id=os.environ.get("EXPERIMENT_RUN_ID"))
    data_by_symbol = _load_recent_symbol_data(selected["instrument"].dropna().astype(str).unique().tolist())

    trade_log = replay_phase8h_trades(selected, data_by_symbol, config)
    concentration_summary = summarize_phase8h_concentration(trade_log, config)
    exit_shape_results = run_phase8h_exit_shape_grid(selected, data_by_symbol, config)
    overlap_summary = summarize_phase8h_overlap(trade_log)

    trade_log_path = output_dir / "phase8h_mnq_vwap_trade_log.csv"
    summary_path = output_dir / "phase8h_mnq_vwap_concentration_summary.csv"
    exit_shape_path = output_dir / "phase8h_mnq_vwap_exit_shape_results.csv"
    overlap_path = output_dir / "phase8h_mnq_vwap_overlap_summary.csv"
    report_path = report_dir / "phase8h_mnq_vwap_concentration_exit_diagnostic_report.md"

    trade_log.to_csv(trade_log_path, index=False)
    concentration_summary.to_csv(summary_path, index=False)
    exit_shape_results.to_csv(exit_shape_path, index=False)
    overlap_summary.to_csv(overlap_path, index=False)
    exit_shape_results.to_csv(run_paths.results_path, index=False)
    selected.to_json(run_paths.specs_path, orient="records", indent=2)
    trade_log.to_csv(run_paths.run_dir / "trade_log.csv", index=False)
    concentration_summary.to_csv(run_paths.run_dir / "concentration_summary.csv", index=False)
    overlap_summary.to_csv(run_paths.run_dir / "overlap_summary.csv", index=False)

    report = render_phase8h_report(
        selected,
        concentration_summary,
        exit_shape_results,
        overlap_summary,
        config,
        trade_log_path=trade_log_path,
        summary_path=summary_path,
        exit_shape_path=exit_shape_path,
        report_path=report_path,
        run_artifact_dir=run_paths.run_dir,
    )
    report_path.write_text(report, encoding="utf-8")
    run_paths.report_path.write_text(
        render_phase8h_report(
            selected,
            concentration_summary,
            exit_shape_results,
            overlap_summary,
            config,
            trade_log_path=run_paths.run_dir / "trade_log.csv",
            summary_path=run_paths.run_dir / "concentration_summary.csv",
            exit_shape_path=run_paths.results_path,
            report_path=run_paths.report_path,
            run_artifact_dir=run_paths.run_dir,
        ),
        encoding="utf-8",
    )

    manifest = write_experiment_manifest(
        project_root=PROJECT_ROOT,
        paths=run_paths,
        experiment_name=EXPERIMENT_NAME,
        command="./.venv/Scripts/python.exe scripts/run_phase8h_mnq_vwap_concentration_exit_diagnostic.py",
        config={
            **asdict(config),
            "recent_sessions": RECENT_SESSIONS,
            "source_event_results": "outputs/phase8e_event_scout_results.csv",
            "source_phase8g_results": "outputs/phase8g_event_execution_calibration.csv",
            "selected_hypothesis_ids": selected["hypothesis_id"].astype(str).tolist(),
        },
        selected_specs_count=len(selected),
        results=exit_shape_results,
        legacy_artifacts={
            "trade_log": trade_log_path,
            "concentration_summary": summary_path,
            "exit_shape_results": exit_shape_path,
            "overlap_summary": overlap_path,
            "report": report_path,
        },
        guardrails=GUARDRAILS,
        data_files=list_local_data_files(PROJECT_ROOT, symbol=config.target_instrument),
    )

    print("Phase 8H MNQ VWAP concentration/exit diagnostic complete.")
    print(f"Selected hypotheses: {len(selected)}")
    print(f"Trade rows: {len(trade_log)}")
    print(f"Concentration rows: {len(concentration_summary)}")
    print(f"Exit-shape rows: {len(exit_shape_results)}")
    print(f"Results: {exit_shape_path}")
    print(f"Trade log: {trade_log_path}")
    print(f"Report: {report_path}")
    print(f"Run artifacts: {run_paths.run_dir}")
    print(f"Manifest rows: {manifest['result_row_count']}")
    print(f"Decision: {_top_decision(concentration_summary, overlap_summary)}")


def _load_recent_symbol_data(symbols: list[str]) -> dict[str, pd.DataFrame]:
    raw_dir = PROJECT_ROOT / "data" / "raw"
    files = discover_data_files(raw_dir)
    data: dict[str, pd.DataFrame] = {}
    for symbol in sorted(set(symbols)):
        symbol_files = [path for path in files if symbol.lower() in path.name.lower()]
        if not symbol_files:
            continue
        frame = pd.concat([load_ohlcv_csv(path) for path in symbol_files], ignore_index=True)
        frame = frame[frame["symbol"].eq(symbol)].sort_values(["trading_session", "timestamp"])
        sessions = sorted(frame["trading_session"].dropna().unique().tolist())[-RECENT_SESSIONS:]
        data[symbol] = frame[frame["trading_session"].isin(sessions)].copy()
    return data


def _top_decision(concentration_summary: pd.DataFrame, overlap_summary: pd.DataFrame) -> str:
    if not overlap_summary.empty and overlap_summary["phase8h_overlap_label"].eq("phase8h_duplicate_signal").any():
        return "phase8h_duplicate_signal (de-duplicate overlapping MNQ VWAP hypotheses before future work)"
    if concentration_summary.empty:
        return "none"
    overall = concentration_summary[concentration_summary["summary_scope"].eq("overall")]
    if overall.empty:
        return "none"
    row = overall.iloc[0]
    return f"{row['phase8h_label']} ({row['phase8h_notes']})"


if __name__ == "__main__":
    main()
