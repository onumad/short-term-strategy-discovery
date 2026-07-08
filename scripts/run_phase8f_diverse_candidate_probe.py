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
from short_term_edge.phase4a import _prepare_symbol_data  # noqa: E402
from short_term_edge.phase5n import score_prefilter_specs  # noqa: E402
from short_term_edge.phase8f_diverse_candidate_probe import Phase8FConfig, rank_phase8f_results, render_phase8f_report, select_phase8f_specs, write_phase8f_specs  # noqa: E402
from short_term_edge.walk_forward import shared_complete_sessions  # noqa: E402

EXPERIMENT_NAME = "phase8f_diverse_candidate_probe"
GUARDRAILS = [
    "research/simulation only",
    "no live trading approval",
    "no broker adapters, order routing, API-key storage, webhooks, or automated execution",
    "bounded probe only; no parameter sweep or promotion",
]


def main() -> None:
    output_dir = PROJECT_ROOT / "outputs"
    report_dir = PROJECT_ROOT / "reports"
    output_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)

    run_paths = prepare_experiment_run(PROJECT_ROOT, EXPERIMENT_NAME, run_id=os.environ.get("EXPERIMENT_RUN_ID"))
    config = Phase8FConfig()
    event_path = output_dir / "phase8e_event_scout_results.csv"
    if not event_path.exists():
        raise FileNotFoundError(f"Phase 8F requires Phase 8E results: {event_path}")
    event_results = pd.read_csv(event_path)
    specs = select_phase8f_specs(event_results, config)
    if not specs:
        raise ValueError("Phase 8F found no supported Phase 8E backtest candidates")

    prepared, sessions = _prepare_phase8f_data(specs)
    raw_results = score_prefilter_specs(specs, prepared, sessions, checkpoint_path=None, batch_size=1)
    results = rank_phase8f_results(raw_results)

    results_path = output_dir / "phase8f_diverse_candidate_probe_results.csv"
    report_path = report_dir / "phase8f_diverse_candidate_probe_report.md"
    results.to_csv(results_path, index=False)
    results.to_csv(run_paths.results_path, index=False)
    write_phase8f_specs(specs, output_dir / "phase8f_diverse_candidate_specs.json")
    write_phase8f_specs(specs, run_paths.specs_path)

    report = render_phase8f_report(results, config, results_path=results_path, report_path=report_path, run_artifact_dir=run_paths.run_dir)
    report_path.write_text(report, encoding="utf-8")
    run_paths.report_path.write_text(
        render_phase8f_report(results, config, results_path=run_paths.results_path, report_path=run_paths.report_path, run_artifact_dir=run_paths.run_dir),
        encoding="utf-8",
    )

    manifest = write_experiment_manifest(
        project_root=PROJECT_ROOT,
        paths=run_paths,
        experiment_name=EXPERIMENT_NAME,
        command="./.venv/Scripts/python.exe scripts/run_phase8f_diverse_candidate_probe.py",
        config={**asdict(config), "source_event_results": "outputs/phase8e_event_scout_results.csv", "complete_sessions": len(sessions)},
        selected_specs_count=len(specs),
        results=results,
        legacy_artifacts={"results": results_path, "specs": output_dir / "phase8f_diverse_candidate_specs.json", "report": report_path},
        guardrails=GUARDRAILS,
        data_files=list_local_data_files(PROJECT_ROOT),
    )

    print("Phase 8F diverse candidate probe complete.")
    print(f"Specs scored: {len(specs)}")
    print(f"Rows: {len(results)}")
    print(f"Results: {results_path}")
    print(f"Report: {report_path}")
    print(f"Run artifacts: {run_paths.run_dir}")
    print(f"Top candidate: {_top_candidate(results)}")
    print(f"Manifest rows: {manifest['result_row_count']}")


def _prepare_phase8f_data(specs) -> tuple[dict[str, dict[str, object]], list[object]]:
    symbols = tuple(sorted({spec.instrument for spec in specs}))
    raw_dir = PROJECT_ROOT / "data" / "raw"
    files = discover_data_files(raw_dir)
    frames = []
    for symbol in symbols:
        symbol_files = [path for path in files if symbol.lower() in path.name.lower()]
        if not symbol_files:
            raise FileNotFoundError(f"No {symbol} raw CSV files found under {raw_dir}")
        frames.extend(load_ohlcv_csv(path) for path in symbol_files)
    full_data = pd.concat(frames, ignore_index=True).sort_values(["symbol", "timestamp"])
    sessions = shared_complete_sessions(full_data, symbols=symbols)
    scoped = full_data[(full_data["symbol"].isin(symbols)) & (full_data["trading_session"].isin(sessions))].copy()
    return _prepare_symbol_data(scoped, sessions), sessions


def _top_candidate(results: pd.DataFrame) -> str:
    if results.empty:
        return "none"
    row = results.iloc[0]
    return f"{row['candidate_id']} ({row['phase8f_label']}, score {float(row['phase8f_score']):.2f})"


if __name__ == "__main__":
    main()
