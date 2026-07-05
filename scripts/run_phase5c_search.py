from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from short_term_edge.phase5c import Phase5CConfig, run_phase5c_search  # noqa: E402


def main() -> None:
    output_dir = PROJECT_ROOT / "outputs"
    report_dir = PROJECT_ROOT / "reports"
    output_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)

    config = Phase5CConfig(symbols=("MNQ", "MGC"), candidates_per_symbol=32, recent_sessions=120, seed=505)
    result = run_phase5c_search(PROJECT_ROOT, config)

    results_path = output_dir / "phase5c_search_results.csv"
    specs_path = output_dir / "phase5c_candidate_specs.json"
    report_path = report_dir / "phase5c_search_report.md"
    result.results.to_csv(results_path, index=False)
    specs_path.write_text(json.dumps([json.loads(spec.to_json()) for spec in result.selected_specs], indent=2, sort_keys=True), encoding="utf-8")
    report_path.write_text(_report(result, config, results_path, specs_path), encoding="utf-8")

    print("Phase 5C robust deterministic search complete.")
    print(f"Search results: {results_path}")
    print(f"Candidate specs: {specs_path}")
    print(f"Report: {report_path}")
    print(f"Rows scored: {len(result.results)}")
    if not result.results.empty:
        top = result.results.iloc[0]
        print(f"Top candidate: {top['candidate_id']} phase5c_score={top['phase5c_score']} label={top['phase5c_label']} net_pnl={top['net_pnl']:.2f}")


def _report(result, config: Phase5CConfig, results_path: Path, specs_path: Path) -> str:
    now = datetime.now(ZoneInfo("America/New_York"))
    ranked = result.results
    sessions = result.complete_sessions
    lines = [
        "# Phase 5C Robust Deterministic Search Report",
        "",
        f"Date generated: {now.date()} {now.strftime('%H:%M:%S %Z')}",
        "",
        "## Scope And Guardrails",
        "",
        "- Research/simulation only. No live trading, broker adapters, API-key storage, webhooks, order routing, or automated execution were added.",
        "- The search emits serializable deterministic strategy specs only; it does not emit live signals.",
        "- Source data is local only under `data/raw`; no additional data was downloaded.",
        "- Optuna was intentionally not added: the bounded deterministic seeded search is sufficient for this milestone and avoids a new dependency.",
        "- Focus order is MNQ first, then MGC; candidate selection preserves that order before final score ranking.",
        "",
        "## Bounded Run Configuration",
        "",
        f"- Symbols: `{', '.join(config.symbols)}`",
        f"- Candidates per symbol: `{config.candidates_per_symbol}`",
        f"- Seed: `{config.seed}`",
        f"- Recent complete shared sessions: `{config.recent_sessions}`",
        f"- Actual session window: `{sessions[0] if sessions else 'none'}` through `{sessions[-1] if sessions else 'none'}` (`{len(sessions)}` sessions)",
        "- Robust score penalties: drawdown, low activity, concentration, complexity, weak holdout, and 4-tick slippage stress failure.",
        "",
        "## Outputs",
        "",
        f"- Search results: `{results_path}`",
        f"- Candidate specs: `{specs_path}`",
        f"- Report: `{PROJECT_ROOT / 'reports' / 'phase5c_search_report.md'}`",
        "",
        "## Top Robust Scores",
        "",
    ]
    if ranked.empty:
        lines.append("- No candidates were scored.")
    else:
        lines.extend(["| Rank | Candidate | Symbol | Family | TF | Label | Score | Net | Holdout | 4-Tick Slip | Trades | Penalty Notes |", "| ---: | --- | --- | --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | --- |"])
        for _, row in ranked.head(15).iterrows():
            lines.append(
                f"| {int(row['phase5c_rank'])} | `{row['candidate_id']}` | {row['instrument']} | {row['family']} | {int(row['timeframe'])}m | {row['phase5c_label']} | {row['phase5c_score']:.2f} | ${row['net_pnl']:.2f} | ${row['holdout_pnl']:.2f} | ${row['slippage_4_ticks_net_pnl']:.2f} | {int(row['trades'])} | {row['phase5c_notes']} |"
            )
        label_counts = ranked["phase5c_label"].value_counts().to_dict()
        by_symbol = ranked.groupby("instrument")["phase5c_label"].value_counts().to_dict()
        lines.extend(["", "## Readout", "", f"- Label counts: `{label_counts}`", f"- Label counts by symbol: `{by_symbol}`"])
    lines.extend(
        [
            "",
            "## Repro Command",
            "",
            "```bash",
            "./.venv/Scripts/python.exe scripts/run_phase5c_search.py",
            "```",
            "",
        ]
    )
    return "\n".join(lines)


if __name__ == "__main__":
    main()
