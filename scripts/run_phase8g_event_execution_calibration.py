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
from short_term_edge.phase8g_event_execution_calibration import Phase8GConfig, render_phase8g_report, run_phase8g_calibration, select_phase8g_candidates  # noqa: E402

EXPERIMENT_NAME = "phase8g_event_execution_calibration"
GUARDRAILS = [
    "research/simulation only",
    "no live trading approval",
    "no broker adapters, order routing, API-key storage, webhooks, or automated execution",
    "calibration diagnostics only; no paper-trading promotion",
]
RECENT_SESSIONS = 180


def main() -> None:
    output_dir = PROJECT_ROOT / "outputs"
    report_dir = PROJECT_ROOT / "reports"
    output_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)

    event_path = output_dir / "phase8e_event_scout_results.csv"
    if not event_path.exists():
        raise FileNotFoundError(f"Phase 8G requires Phase 8E results: {event_path}")
    event_results = pd.read_csv(event_path)
    config = Phase8GConfig()
    selected = select_phase8g_candidates(event_results, config)
    if selected.empty:
        raise ValueError("Phase 8G found no Phase 8E backtest candidates to calibrate")

    run_paths = prepare_experiment_run(PROJECT_ROOT, EXPERIMENT_NAME, run_id=os.environ.get("EXPERIMENT_RUN_ID"))
    data_by_symbol = _load_recent_symbol_data(selected["instrument"].dropna().astype(str).unique().tolist())
    results = run_phase8g_calibration(event_results, data_by_symbol, config)

    results_path = output_dir / "phase8g_event_execution_calibration.csv"
    report_path = report_dir / "phase8g_event_execution_calibration_report.md"
    results.to_csv(results_path, index=False)
    results.to_csv(run_paths.results_path, index=False)
    selected.to_json(run_paths.specs_path, orient="records", indent=2)

    report = render_phase8g_report(results, config, results_path=results_path, report_path=report_path, run_artifact_dir=run_paths.run_dir)
    report_path.write_text(report, encoding="utf-8")
    run_paths.report_path.write_text(
        render_phase8g_report(results, config, results_path=run_paths.results_path, report_path=run_paths.report_path, run_artifact_dir=run_paths.run_dir),
        encoding="utf-8",
    )

    manifest = write_experiment_manifest(
        project_root=PROJECT_ROOT,
        paths=run_paths,
        experiment_name=EXPERIMENT_NAME,
        command="./.venv/Scripts/python.exe scripts/run_phase8g_event_execution_calibration.py",
        config={
            **asdict(config),
            "recent_sessions": RECENT_SESSIONS,
            "source_event_results": "outputs/phase8e_event_scout_results.csv",
        },
        selected_specs_count=len(selected),
        results=results,
        legacy_artifacts={"results": results_path, "report": report_path},
        guardrails=GUARDRAILS,
        data_files=list_local_data_files(PROJECT_ROOT),
    )

    print("Phase 8G event-to-execution calibration complete.")
    print(f"Event candidates calibrated: {len(selected)}")
    print(f"Calibration rows: {len(results)}")
    print(f"Results: {results_path}")
    print(f"Report: {report_path}")
    print(f"Run artifacts: {run_paths.run_dir}")
    print(f"Manifest rows: {manifest['result_row_count']}")
    print(f"Top calibration: {_top_calibration(results)}")


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


def _top_calibration(results: pd.DataFrame) -> str:
    if results.empty:
        return "none"
    row = results.iloc[0]
    return f"{row['calibration_id']} ({row['calibration_label']}, score {float(row['calibration_score']):.2f})"


if __name__ == "__main__":
    main()
