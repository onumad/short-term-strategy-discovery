from __future__ import annotations

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from .instruments import INSTRUMENTS


def write_phase2_report(result: dict, project_root: Path) -> None:
    ranked: pd.DataFrame = result["ranked"]
    top: pd.DataFrame = result["top"]
    sessions = result["complete_sessions"]
    paths = result["paths"]
    report_path = paths["report"]
    variants = len(ranked)
    traded = int((ranked["trades"] > 0).sum())
    paper = int((ranked["label"] == "paper_trade_candidate").sum())

    best_offensive = _best(ranked, "net_pnl")
    highest_frequency = _best(ranked, "trades_per_session")
    risk_adjusted = ranked[ranked["trades"] > 0].assign(
        risk_adjusted=ranked["net_pnl"] / ranked["max_drawdown"].abs().replace(0, pd.NA)
    ).sort_values(["risk_adjusted", "net_pnl"], ascending=False)
    best_risk = risk_adjusted.iloc[0] if not risk_adjusted.empty else None
    best_phase3 = _best(ranked, "ranking_score")

    lines = [
        "# Phase 2 Discovery Report",
        "",
        f"Date generated: {datetime.now(ZoneInfo('America/New_York')).date()}",
        "",
        "## Summary",
        "",
        f"- Strategy variants tested: `{variants}`.",
        f"- Variants with at least one trade: `{traded}`.",
        f"- Research window: `{sessions[0]}` through `{sessions[-1]}` ({len(sessions)} complete shared sessions).",
        "- Partial `2026-07-03` session excluded.",
        "- Highest possible label remains `paper_trade_candidate`; no live-trading approval is implied.",
        f"- Candidates labeled `paper_trade_candidate`: `{paper}`.",
        "",
        "## Cost And Execution Assumptions",
        "",
        "- Entry timing: signal is evaluated after a 1-minute bar closes; entry is next bar open.",
        "- Exit timing: target/stop/time flatten is evaluated after entry using 1-minute OHLC.",
        "- Conservative intrabar rule: if stop and target are both touched in the same bar, stop is assumed first.",
        "- Flatten time: `15:55 ET`.",
        "- Base slippage: 1 tick per side plus round-turn fees.",
        "- Stress slippage: 2 ticks per side plus the same round-turn fees.",
        "",
        "| Instrument | Tick Size | Tick Value | Point Value | Round-Turn Fees | Base Cost | Stress Cost |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for spec in INSTRUMENTS.values():
        lines.append(
            f"| {spec.symbol} | {spec.tick_size:g} | ${spec.tick_value:.2f} | "
            f"${spec.point_value:.2f} | ${spec.round_turn_fees:.2f} | "
            f"${spec.base_cost:.2f} | ${spec.stress_cost:.2f} |"
        )
    lines.extend(
        [
            "",
            "MNQ uses CME's Micro E-mini Nasdaq-100 contract sizing assumption of `$2 x index` and `0.25` index-point ticks. MGC uses CME's Micro Gold `10 troy ounces` contract sizing assumption; the audit assumes `0.10` price ticks worth `$1.00` per contract. Fee values are research assumptions and should be replaced with broker-specific all-in costs before paper-trading evaluation.",
            "",
            "Contract reference links: [CME MNQ contract specs](https://www.cmegroup.com/markets/equities/nasdaq/micro-e-mini-nasdaq-100.contractSpecs.html), [CME MGC contract specs](https://www.cmegroup.com/markets/metals/precious/e-micro-gold.contractSpecs.html).",
            "",
            "## Best Candidates",
            "",
            _candidate_line("Best offensive candidate", best_offensive),
            _candidate_line("Highest-frequency candidate", highest_frequency),
            _candidate_line("Best risk-adjusted candidate", best_risk),
            _candidate_line("Best Phase 3 validation candidate", best_phase3),
            "",
            "## Top Edge Table",
            "",
            "| Rank | Candidate | Label | Net PnL | Holdout PnL | Stress Net PnL | Trades | Trades/Session | Active % | Max DD | Score | Risk Notes |",
            "| ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
        ]
    )
    for idx, row in top.reset_index(drop=True).iterrows():
        lines.append(
            f"| {idx + 1} | `{row['candidate_id']}` | {row['label']} | "
            f"${row['net_pnl']:.2f} | ${row['holdout_pnl']:.2f} | ${row['stress_net_pnl']:.2f} | "
            f"{int(row['trades'])} | {row['trades_per_session']:.2f} | {row['active_session_pct']:.1%} | "
            f"${row['max_drawdown']:.2f} | {row['ranking_score']:.2f} | {row['risk_notes']} |"
        )

    family_summary = ranked.groupby("strategy_family").agg(
        variants=("candidate_id", "count"),
        traded=("trades", lambda s: int((s > 0).sum())),
        best_net=("net_pnl", "max"),
        best_score=("ranking_score", "max"),
        paper=("label", lambda s: int((s == "paper_trade_candidate").sum())),
    ).reset_index().sort_values("best_score", ascending=False)

    lines.extend(
        [
            "",
            "## Family Summary",
            "",
            "| Family | Variants | Traded | Best Net PnL | Best Score | Paper Candidates |",
            "| --- | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for _, row in family_summary.iterrows():
        lines.append(
            f"| {row['strategy_family']} | {int(row['variants'])} | {int(row['traded'])} | "
            f"${row['best_net']:.2f} | {row['best_score']:.2f} | {int(row['paper'])} |"
        )

    lines.extend(
        [
            "",
            "## Risks And Failure Modes",
            "",
            "- Phase 2 is a discovery sweep, not a full validation study.",
            "- The final holdout was scored after variant generation; it should not be used for further tuning.",
            "- One-minute OHLC data cannot prove intrabar order, so the simulator uses a conservative stop-first rule.",
            "- Results are sensitive to fee and slippage assumptions; stress results are included in the ranking table.",
            "- Continuous futures can include rollover effects; Phase 3 should inspect top candidates around roll periods.",
            "- MGC has more small non-1-minute gaps than MNQ in the Phase 1 audit; top MGC trade logs should be spot-checked.",
            "",
            "## Recommended Phase 3",
            "",
            "- Re-run the top candidates with parameter-neighbor sensitivity and stricter slippage.",
            "- Inspect each top trade log manually for obvious data-gap, time-of-day, or rollover artifacts.",
            "- Add MAE/MFE and a prop-firm style daily-loss rule model before any paper-trading plan.",
            "- Keep the same candidate labels and do not introduce live-trading approval language.",
            "",
            "## Reproducibility",
            "",
            "Command:",
            "",
            "```powershell",
            "python scripts/run_phase2_discovery.py",
            "```",
            "",
            "Outputs:",
            "",
            f"- Ranked candidates: `{paths['ranked']}`",
            f"- Top candidates: `{paths['top']}`",
            f"- Trade logs: `{paths['trade_logs']}`",
            f"- Charts: `{paths['charts']}`",
            "",
        ]
    )
    report_path.write_text("\n".join(lines), encoding="utf-8")


def _best(ranked: pd.DataFrame, column: str):
    usable = ranked[ranked["trades"] > 0].sort_values(column, ascending=False)
    if usable.empty:
        return None
    return usable.iloc[0]


def _candidate_line(label: str, row) -> str:
    if row is None:
        return f"- {label}: none."
    return (
        f"- {label}: `{row['candidate_id']}` "
        f"({row['label']}), net `${row['net_pnl']:.2f}`, "
        f"holdout `${row['holdout_pnl']:.2f}`, trades/session `{row['trades_per_session']:.2f}`, "
        f"score `{row['ranking_score']:.2f}`."
    )
