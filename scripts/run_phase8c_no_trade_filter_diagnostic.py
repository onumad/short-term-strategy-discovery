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

from short_term_edge.ai_search import spec_to_phase4_candidate  # noqa: E402
from short_term_edge.experiments.artifacts import list_local_data_files, prepare_experiment_run, write_experiment_manifest  # noqa: E402
from short_term_edge.instruments import get_instrument  # noqa: E402
from short_term_edge.phase4a import generate_phase4a_signals, simulate_phase4a_candidate  # noqa: E402
from short_term_edge.phase5n import filter_signals_by_side  # noqa: E402
from short_term_edge.phase7a import Phase7AConfig, _prepare_phase7a_data  # noqa: E402
from short_term_edge.phase8c import Phase8CConfig, build_phase8c_filter_specs, evaluate_phase8c_filters, render_phase8c_report  # noqa: E402
from short_term_edge.strategy_spec import StrategySpec  # noqa: E402

EXPERIMENT_NAME = "phase8c_no_trade_filter"
GUARDRAILS = [
    "research/simulation only",
    "no live trading approval",
    "no broker adapters, order routing, API-key storage, webhooks, or automated execution",
    "pre-entry no-trade filters only; no entry/exit/sizing logic changed",
]


def main() -> None:
    output_dir = PROJECT_ROOT / "outputs"
    report_dir = PROJECT_ROOT / "reports"
    output_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)

    run_paths = prepare_experiment_run(PROJECT_ROOT, EXPERIMENT_NAME, run_id=os.environ.get("EXPERIMENT_RUN_ID"))
    config = Phase8CConfig()
    phase8a_results_path = output_dir / "phase8a_mgc_clean_family_results.csv"
    if not phase8a_results_path.exists():
        raise FileNotFoundError(f"Phase 8C requires existing Phase 8A results: {phase8a_results_path}")

    phase8a_results = pd.read_csv(phase8a_results_path)
    specs = _load_scored_specs(phase8a_results)
    trades, complete_sessions = _replay_phase8a_trades(specs)
    filter_specs = build_phase8c_filter_specs()
    results = evaluate_phase8c_filters(trades, filter_specs, complete_sessions=complete_sessions, config=config)

    results_path = output_dir / "phase8c_no_trade_filter_results.csv"
    report_path = report_dir / "phase8c_no_trade_filter_report.md"
    source_trades_path = run_paths.run_dir / "source_trades.csv"
    filter_specs_path = run_paths.run_dir / "filter_specs.json"

    results.to_csv(results_path, index=False)
    results.to_csv(run_paths.results_path, index=False)
    results.to_csv(run_paths.run_dir / "filter_results.csv", index=False)
    trades.to_csv(source_trades_path, index=False)
    filter_specs_payload = [spec.to_dict() for spec in filter_specs]
    filter_specs_path.write_text(json.dumps(filter_specs_payload, indent=2, sort_keys=True), encoding="utf-8")
    run_paths.specs_path.write_text(filter_specs_path.read_text(encoding="utf-8"), encoding="utf-8")

    report = render_phase8c_report(
        results,
        config,
        source_trade_count=len(trades),
        source_candidate_count=len(specs),
        results_path=results_path,
        report_path=report_path,
        run_artifact_dir=run_paths.run_dir,
    )
    report_path.write_text(report, encoding="utf-8")
    run_paths.report_path.write_text(
        render_phase8c_report(
            results,
            config,
            source_trade_count=len(trades),
            source_candidate_count=len(specs),
            results_path=run_paths.results_path,
            report_path=run_paths.report_path,
            run_artifact_dir=run_paths.run_dir,
        ),
        encoding="utf-8",
    )

    manifest = write_experiment_manifest(
        project_root=PROJECT_ROOT,
        paths=run_paths,
        experiment_name=EXPERIMENT_NAME,
        command="./.venv/Scripts/python.exe scripts/run_phase8c_no_trade_filter_diagnostic.py",
        config={
            **asdict(config),
            "source_phase8a_results": "outputs/phase8a_mgc_clean_family_results.csv",
            "source_trade_count": int(len(trades)),
            "filter_count": int(len(filter_specs)),
        },
        selected_specs_count=len(filter_specs),
        results=results,
        legacy_artifacts={"results": results_path, "report": report_path},
        guardrails=GUARDRAILS,
        data_files=list_local_data_files(PROJECT_ROOT, symbol=config.symbol),
    )

    print("Phase 8C no-trade/session-selection diagnostic complete.")
    print(f"Source trades: {len(trades)} from {len(specs)} Phase 8A specs")
    print(f"Results: {results_path}")
    print(f"Report: {report_path}")
    print(f"Run artifacts: {run_paths.run_dir}")
    print(f"Manifest: {run_paths.manifest_path}")
    print(f"Top filter: {_top_filter(results)}")
    print(f"Manifest result rows: {manifest['result_row_count']}")


def _load_scored_specs(phase8a_results: pd.DataFrame) -> list[StrategySpec]:
    if phase8a_results.empty:
        raise ValueError("Phase 8C requires at least one scored Phase 8A row")
    specs = []
    for _, row in phase8a_results.iterrows():
        specs.append(StrategySpec.from_json(str(row["spec_json"])))
    return specs


def _replay_phase8a_trades(specs: list[StrategySpec]) -> tuple[pd.DataFrame, list[object]]:
    timeframes = tuple(sorted({int(spec.timeframe) for spec in specs}))
    prepared, complete_sessions = _prepare_phase7a_data(PROJECT_ROOT, Phase7AConfig(symbol="MGC", max_specs=max(len(specs), 1), min_specs=1, timeframes=timeframes))
    symbol_data = prepared["MGC"]
    instrument = get_instrument("MGC")
    trade_frames: list[pd.DataFrame] = []
    for spec in specs:
        candidate = spec_to_phase4_candidate(spec)
        signals = generate_phase4a_signals(symbol_data["timeframes"][int(spec.timeframe)], symbol_data["full"], candidate)
        signals = filter_signals_by_side(signals, str(candidate.params.get("side_filter", "both")))
        trades = simulate_phase4a_candidate(symbol_data["one_minute"], signals, candidate, instrument, complete_sessions)
        if trades.empty:
            continue
        out = trades.copy()
        out.insert(0, "source_candidate_id", spec.canonical_id())
        out.insert(1, "source_family", spec.family)
        out.insert(2, "source_timeframe", int(spec.timeframe))
        trade_frames.append(out)
    if not trade_frames:
        return pd.DataFrame(), complete_sessions
    return pd.concat(trade_frames, ignore_index=True).sort_values(["entry_time", "exit_time"]).reset_index(drop=True), complete_sessions


def _top_filter(results: pd.DataFrame) -> str:
    if results.empty:
        return "none"
    row = results.iloc[0]
    return f"{row['filter_id']} ({row['phase8c_label']}, score {float(row['phase8c_score']):.2f})"


if __name__ == "__main__":
    main()
