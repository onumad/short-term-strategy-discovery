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
from short_term_edge.phase8d_hypothesis_queue import Phase8DConfig, build_phase8d_hypothesis_queue  # noqa: E402
from short_term_edge.phase8e_event_scout import Phase8EConfig, render_phase8e_report, run_phase8e_event_scout  # noqa: E402

EXPERIMENT_NAME = "phase8e_event_scout"
GUARDRAILS = [
    "research/simulation only",
    "no live trading approval",
    "no broker adapters, order routing, API-key storage, webhooks, or automated execution",
    "event-study labels only; no strategy execution or promotion",
]
RECENT_SESSIONS = 180


def main() -> None:
    output_dir = PROJECT_ROOT / "outputs"
    report_dir = PROJECT_ROOT / "reports"
    output_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)

    run_paths = prepare_experiment_run(PROJECT_ROOT, EXPERIMENT_NAME, run_id=os.environ.get("EXPERIMENT_RUN_ID"))
    config = Phase8EConfig()
    queue_path = output_dir / "phase8d_hypothesis_queue.csv"
    if queue_path.exists():
        queue = pd.read_csv(queue_path)
    else:
        queue = build_phase8d_hypothesis_queue(Phase8DConfig())
    data_by_symbol = _load_recent_symbol_data(queue["instrument"].dropna().astype(str).unique().tolist())
    results = run_phase8e_event_scout(queue, data_by_symbol, config)

    results_path = output_dir / "phase8e_event_scout_results.csv"
    report_path = report_dir / "phase8e_event_scout_report.md"
    results.to_csv(results_path, index=False)
    results.to_csv(run_paths.results_path, index=False)
    queue.head(config.max_hypotheses).to_json(run_paths.specs_path, orient="records", indent=2)

    report = render_phase8e_report(results, config, results_path=results_path, report_path=report_path, run_artifact_dir=run_paths.run_dir)
    report_path.write_text(report, encoding="utf-8")
    run_paths.report_path.write_text(
        render_phase8e_report(results, config, results_path=run_paths.results_path, report_path=run_paths.report_path, run_artifact_dir=run_paths.run_dir),
        encoding="utf-8",
    )

    manifest = write_experiment_manifest(
        project_root=PROJECT_ROOT,
        paths=run_paths,
        experiment_name=EXPERIMENT_NAME,
        command="./.venv/Scripts/python.exe scripts/run_phase8e_event_scout.py",
        config={**asdict(config), "recent_sessions": RECENT_SESSIONS, "source_queue": "outputs/phase8d_hypothesis_queue.csv"},
        selected_specs_count=min(len(queue), config.max_hypotheses),
        results=results,
        legacy_artifacts={"results": results_path, "report": report_path},
        guardrails=GUARDRAILS,
        data_files=list_local_data_files(PROJECT_ROOT),
    )

    print("Phase 8E cheap event-study scout complete.")
    print(f"Hypotheses scouted: {len(results)}")
    print(f"Backtest candidates: {int((results['phase8e_label'] == 'backtest_candidate').sum()) if not results.empty else 0}")
    print(f"Results: {results_path}")
    print(f"Report: {report_path}")
    print(f"Run artifacts: {run_paths.run_dir}")
    print(f"Manifest rows: {manifest['result_row_count']}")


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


if __name__ == "__main__":
    main()
