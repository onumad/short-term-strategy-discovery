from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from short_term_edge.ai_search import SearchConfig, run_bounded_search


def main() -> None:
    output_dir = PROJECT_ROOT / "outputs"
    report_dir = PROJECT_ROOT / "reports"
    output_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)

    config = SearchConfig(
        symbols=("MNQ", "MGC"),
        max_candidates=32,
        recent_sessions=120,
        timeframes=(1, 3, 5),
        opening_range_minutes=(15, 30, 60),
    )
    result = run_bounded_search(PROJECT_ROOT, config)

    candidates_path = output_dir / "phase5_ai_candidates.csv"
    feature_path = output_dir / "phase5_feature_summary.csv"
    report_path = report_dir / "phase5_ai_search_report.md"
    result.candidates.to_csv(candidates_path, index=False)
    result.feature_summary.to_csv(feature_path, index=False)
    report_path.write_text(_report(result, config, candidates_path, feature_path), encoding="utf-8")

    print(f"Phase 5A AI search complete.")
    print(f"Candidates: {candidates_path}")
    print(f"Feature summary: {feature_path}")
    print(f"Report: {report_path}")
    print(f"Rows scored: {len(result.candidates)}")
    if not result.candidates.empty:
        top = result.candidates.iloc[0]
        print(f"Top candidate: {top['candidate_id']} score={top['ranking_score']} label={top['label']} net_pnl={top['net_pnl']:.2f}")


def _report(result, config: SearchConfig, candidates_path: Path, feature_path: Path) -> str:
    sessions = result.complete_sessions
    ranked = result.candidates
    now = datetime.now(ZoneInfo("America/New_York"))
    lines = [
        "# Phase 5A AI Strategy Finder Foundation Report",
        "",
        f"Date generated: {now.date()} {now.strftime('%H:%M:%S %Z')}",
        "",
        "## Scope And Guardrails",
        "",
        "- This is a deterministic AI-assisted/search foundation, not an opaque neural-net trader.",
        "- The search proposes serializable rule specs from explicit bounded grids; validation scores them on historical data.",
        "- No live trading, broker adapters, API-key storage, webhooks, order routing, or automated execution were added.",
        "- Source data was local only under `data/raw`; the script does not download more data.",
        "- Strategy results remain research/simulation candidates only and require independent validation before any paper-trading process.",
        "",
        "## Bounded Run Configuration",
        "",
        f"- Symbols: `{', '.join(config.symbols)}`",
        f"- Max candidates: `{config.max_candidates}`",
        f"- Recent complete shared sessions: `{config.recent_sessions}`",
        f"- Actual session window: `{sessions[0] if sessions else 'none'}` through `{sessions[-1] if sessions else 'none'}` (`{len(sessions)}` sessions)",
        f"- Timeframes: `{', '.join(str(tf) + 'm' for tf in config.timeframes)}`",
        f"- Opening range windows: `{', '.join(str(m) + 'm' for m in config.opening_range_minutes)}`",
        "- Cost model: instrument `base_cost` and `stress_cost` are included in each score row; strict 4-tick slippage is also reported.",
        "",
        "## Outputs",
        "",
        f"- Candidate scores: `{candidates_path}`",
        f"- Feature summary: `{feature_path}`",
        f"- Report: `{PROJECT_ROOT / 'reports' / 'phase5_ai_search_report.md'}`",
        "",
        "## Feature Foundation",
        "",
        "The feature builder creates inspectable no-lookahead columns: session VWAP, EMA/SMA, realized range, shifted prior-session levels, opening-range levels only after the opening window is complete, and offline-only `label_*` forward returns.",
        "",
    ]
    if result.feature_summary.empty:
        lines.append("- No feature rows were generated.")
    else:
        lines.extend(["| Symbol | Rows | Sessions | First Timestamp | Last Timestamp |", "| --- | ---: | ---: | --- | --- |"])
        for _, row in result.feature_summary.iterrows():
            lines.append(f"| {row['symbol']} | {int(row['rows'])} | {int(row['sessions'])} | {row['first_timestamp']} | {row['last_timestamp']} |")

    lines.extend(["", "## Top Candidate Scores", ""])
    if ranked.empty:
        lines.append("- No candidates were scored.")
    else:
        lines.extend(["| Rank | Candidate | Family | TF | Label | Score | Net | Holdout | 4-Tick Slip | Trades | Active % | Risk Notes |", "| ---: | --- | --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |"])
        for idx, row in ranked.head(12).iterrows():
            lines.append(
                f"| {idx + 1} | `{row['candidate_id']}` | {row['family']} | {int(row['timeframe'])}m | {row['label']} | {row['ranking_score']:.2f} | ${row['net_pnl']:.2f} | ${row['holdout_pnl']:.2f} | ${row['slippage_4_ticks_net_pnl']:.2f} | {int(row['trades'])} | {row['active_session_pct']:.1%} | {row['risk_notes']} |"
            )

    label_counts = ranked["label"].value_counts().to_dict() if not ranked.empty else {}
    lines.extend(
        [
            "",
            "## Initial Readout",
            "",
            f"- Label counts: `{label_counts}`",
            "- Treat all positive results as candidates for further walk-forward / out-of-sample review, not deployable systems.",
            "- Concentration, low coverage, negative holdout, and strict-slippage failures are intentionally conservative risk flags.",
            "",
            "## How To Scale Later",
            "",
            "- Increase `max_candidates` gradually after reviewing generated specs and runtime.",
            "- Increase `recent_sessions` or remove the cap for a slower full-history validation.",
            "- Add new families only as deterministic, serializable rule templates with unit tests and no-lookahead checks.",
            "- Keep LLM/AI involvement limited to proposing or ranking auditable rule specs; validation must remain deterministic.",
            "",
            "## Repro Command",
            "",
            "```bash",
            "./.venv/Scripts/python.exe scripts/run_phase5_ai_search.py",
            "```",
            "",
        ]
    )
    return "\n".join(lines)


if __name__ == "__main__":
    main()
