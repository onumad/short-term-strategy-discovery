from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd


@dataclass(frozen=True)
class Phase8DConfig:
    max_hypotheses: int = 60
    instruments: tuple[str, ...] = ("MGC", "MNQ")
    timeframes: tuple[int, ...] = (1, 3, 5, 15)
    sides: tuple[str, ...] = ("long_only", "short_only", "both")


FAMILY_TEMPLATES: tuple[dict[str, str], ...] = (
    {
        "family": "opening_range_breakout",
        "setup_description": "Break away from the completed opening range after confirmation.",
        "decision_time_requirements": "opening range completed plus signal bar close",
        "kill_condition": "reject if cost stress or concentration dominates",
    },
    {
        "family": "opening_range_fade",
        "setup_description": "Fade failed opening-range extensions after price closes back inside the range.",
        "decision_time_requirements": "opening range completed plus failed-break close",
        "kill_condition": "reject if same-bar ambiguity or holdout weakness dominates",
    },
    {
        "family": "prior_high_low_breakout",
        "setup_description": "Trade continuation through prior-session high/low levels.",
        "decision_time_requirements": "prior session levels known before RTH open",
        "kill_condition": "reject if breakout events are too sparse or slippage-sensitive",
    },
    {
        "family": "prior_high_low_rejection",
        "setup_description": "Fade sweeps of prior-session high/low after rejection confirmation.",
        "decision_time_requirements": "prior levels known plus rejection close",
        "kill_condition": "reject if one-day concentration or ambiguity remains high",
    },
    {
        "family": "vwap_reclaim_rejection",
        "setup_description": "Trade reclaim/rejection around intraday VWAP after bar close confirmation.",
        "decision_time_requirements": "current-session VWAP and closed signal bar",
        "kill_condition": "reject if it fires in nearly every session without quality filters",
    },
    {
        "family": "vwap_pullback_continuation",
        "setup_description": "Trade with VWAP trend after a shallow pullback and continuation close.",
        "decision_time_requirements": "VWAP slope/pullback known at signal close",
        "kill_condition": "reject if old MGC failure modes repeat without filter improvement",
    },
    {
        "family": "opening_drive_continuation",
        "setup_description": "Follow strong opening drive continuation after a bounded drive window.",
        "decision_time_requirements": "drive window completed before signal",
        "kill_condition": "reject if drawdown path breaches before robust payout case",
    },
    {
        "family": "first_pullback_trend_continuation",
        "setup_description": "Trade first pullback after session trend is established.",
        "decision_time_requirements": "trend and pullback state from closed bars only",
        "kill_condition": "reject if event detection requires discretionary labeling",
    },
    {
        "family": "session_reversal_failed_breakout",
        "setup_description": "Trade reversal after a failed range or prior-level breakout.",
        "decision_time_requirements": "failed breakout and reversal confirmation close",
        "kill_condition": "reject if too many variants only repackage opening-range fade",
    },
    {
        "family": "volatility_compression_breakout",
        "setup_description": "Trade expansion after prior low-range/compression context.",
        "decision_time_requirements": "prior range bucket known before entry",
        "kill_condition": "reject if too sparse or only works in one market regime",
    },
    {
        "family": "overnight_range_breakout_fade",
        "setup_description": "Trade breakout or fade around overnight high/low/midpoint levels.",
        "decision_time_requirements": "overnight range finalized before RTH open",
        "kill_condition": "reject if overnight data quality or session handling is ambiguous",
    },
    {
        "family": "time_of_day_momentum_reversion",
        "setup_description": "Trade time-window-specific momentum or mean-reversion behavior.",
        "decision_time_requirements": "fixed clock window and closed bar only",
        "kill_condition": "reject if edge vanishes outside one narrow sample window",
    },
)


def build_phase8d_hypothesis_queue(config: Phase8DConfig = Phase8DConfig()) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for family_index, template in enumerate(FAMILY_TEMPLATES):
        for instrument in config.instruments:
            for side in config.sides:
                timeframe = _timeframe_for(template["family"], instrument, side, config.timeframes)
                row = {
                    "hypothesis_id": _hypothesis_id(instrument, timeframe, side, template["family"]),
                    "instrument": instrument,
                    "timeframe": int(timeframe),
                    "side": side,
                    "family": template["family"],
                    "setup_description": template["setup_description"],
                    "decision_time_requirements": template["decision_time_requirements"],
                    "expected_trade_frequency": _expected_trade_frequency(template["family"], timeframe, side),
                    "expected_cost_sensitivity": _cost_sensitivity(instrument, timeframe, template["family"]),
                    "lookahead_risk": _lookahead_risk(template["decision_time_requirements"]),
                    "ambiguity_risk": _ambiguity_risk(template["family"], timeframe),
                    "implementation_cost": _implementation_cost(template["family"]),
                    "scout_priority": 0.0,
                    "reason_to_try": _reason_to_try(instrument, side, timeframe, template["family"]),
                    "kill_condition": template["kill_condition"],
                    "family_order": family_index,
                }
                row["scout_priority"] = _priority(row)
                rows.append(row)
    ranked = pd.DataFrame(rows).sort_values(
        ["scout_priority", "family_order", "instrument", "side", "timeframe"], ascending=[False, True, True, True, True]
    )
    ranked = _diversify_top(ranked, top_n=10).head(config.max_hypotheses).reset_index(drop=True)
    ranked.insert(0, "phase8d_rank", range(1, len(ranked) + 1))
    return ranked.drop(columns=["family_order"])


def render_phase8d_report(
    queue: pd.DataFrame,
    config: Phase8DConfig,
    *,
    queue_path: Path,
    report_path: Path,
    run_artifact_dir: Path | None = None,
) -> str:
    lines = [
        "# Phase 8D Broad Hypothesis Queue",
        "",
        "Generated by: `./.venv/Scripts/python.exe scripts/run_phase8d_hypothesis_queue.py`",
        "",
        "## Scope And Guardrails",
        "",
        "- Research/simulation only. No live trading, broker adapters, order routing, API-key storage, webhooks, or automated execution were added.",
        "- Phase 8D is a prioritization queue, not a backtest or promotion decision.",
        "- Hypotheses must pass cheap event-study scouting before deeper strategy work.",
        "",
        "## Queue Shape",
        "",
        f"- Hypotheses: `{len(queue)}`",
        f"- Instruments: `{sorted(queue['instrument'].unique().tolist()) if not queue.empty else []}`",
        f"- Families: `{queue['family'].nunique() if not queue.empty else 0}`",
        f"- Timeframes: `{sorted(queue['timeframe'].unique().tolist()) if not queue.empty else []}`",
        f"- Sides: `{sorted(queue['side'].unique().tolist()) if not queue.empty else []}`",
        "",
        "## Top Queue Items",
        "",
        "| Rank | Hypothesis | Instrument | TF | Side | Family | Priority | Reason | Kill Condition |",
        "| ---: | --- | --- | ---: | --- | --- | ---: | --- | --- |",
    ]
    for _, row in queue.head(15).iterrows():
        lines.append(
            f"| {int(row['phase8d_rank'])} | `{row['hypothesis_id']}` | {row['instrument']} | {int(row['timeframe'])} | {row['side']} | "
            f"{row['family']} | {float(row['scout_priority']):.2f} | {row['reason_to_try']} | {row['kill_condition']} |"
        )
    lines.extend(
        [
            "",
            "## Kill Conditions",
            "",
            "- Reject quickly if event count is too sparse, gross forward behavior is negative, cost sensitivity dominates, same-bar ambiguity is high, or the idea is just another variant of an already-failed family.",
            "- Cap deep backtests to a few diverse survivors after event scouting.",
            "",
            "## Outputs",
            "",
            f"- Queue CSV: `{queue_path.as_posix()}`",
            f"- Report: `{report_path.as_posix()}`",
        ]
    )
    if run_artifact_dir is not None:
        lines.append(f"- Run-scoped artifacts: `{run_artifact_dir.as_posix()}`")
    lines.extend(["", "## Repro Command", "", "```bash", "./.venv/Scripts/python.exe scripts/run_phase8d_hypothesis_queue.py", "```", ""])
    return "\n".join(lines)


def _hypothesis_id(instrument: str, timeframe: int, side: str, family: str) -> str:
    payload = json.dumps({"instrument": instrument, "timeframe": int(timeframe), "side": side, "family": family}, sort_keys=True)
    return f"{instrument}_{family}_tf{int(timeframe)}_{side}_{hashlib.sha1(payload.encode('utf-8')).hexdigest()[:8]}"


def _timeframe_for(family: str, instrument: str, side: str, timeframes: tuple[int, ...]) -> int:
    base = {
        "opening_range_breakout": 1,
        "opening_range_fade": 3,
        "prior_high_low_breakout": 5,
        "prior_high_low_rejection": 3,
        "vwap_reclaim_rejection": 1,
        "vwap_pullback_continuation": 5,
        "opening_drive_continuation": 1,
        "first_pullback_trend_continuation": 5,
        "session_reversal_failed_breakout": 15,
        "volatility_compression_breakout": 15,
        "overnight_range_breakout_fade": 5,
        "time_of_day_momentum_reversion": 3,
    }[family]
    if instrument == "MNQ" and side == "short_only" and 15 in timeframes:
        return 15
    return base if base in timeframes else timeframes[0]


def _expected_trade_frequency(family: str, timeframe: int, side: str) -> str:
    if family in {"volatility_compression_breakout", "overnight_range_breakout_fade"}:
        return "low"
    if timeframe >= 15 or side != "both":
        return "medium"
    return "high"


def _cost_sensitivity(instrument: str, timeframe: int, family: str) -> str:
    if timeframe == 1 or family in {"vwap_reclaim_rejection", "opening_range_fade"}:
        return "high" if instrument == "MGC" else "medium"
    return "medium" if instrument == "MGC" else "low"


def _lookahead_risk(requirements: str) -> str:
    return "medium" if "completed" in requirements or "known" in requirements else "low"


def _ambiguity_risk(family: str, timeframe: int) -> str:
    if timeframe == 1 or "fade" in family or "rejection" in family:
        return "high"
    return "medium"


def _implementation_cost(family: str) -> str:
    if family in {"opening_range_breakout", "opening_range_fade", "vwap_reclaim_rejection", "prior_high_low_breakout", "prior_high_low_rejection"}:
        return "low"
    if family in {"volatility_compression_breakout", "time_of_day_momentum_reversion"}:
        return "medium"
    return "high"


def _priority(row: dict[str, Any]) -> float:
    score = 100.0
    score += {"low": 12.0, "medium": 6.0, "high": -10.0}[row["expected_cost_sensitivity"]]
    score += {"low": 6.0, "medium": 10.0, "high": -8.0}[row["expected_trade_frequency"]]
    score += {"low": 8.0, "medium": 3.0, "high": -12.0}[row["ambiguity_risk"]]
    score += {"low": 8.0, "medium": 0.0, "high": -8.0}[row["implementation_cost"]]
    if row["side"] != "both":
        score += 8.0
    if int(row["timeframe"]) != 1:
        score += 6.0
    if row["instrument"] == "MNQ":
        score += 3.0
    return round(score, 4)


def _reason_to_try(instrument: str, side: str, timeframe: int, family: str) -> str:
    return f"Diversifies away from the current MGC single-family grind via {instrument} {side} {timeframe}m {family}."


def _diversify_top(ranked: pd.DataFrame, top_n: int) -> pd.DataFrame:
    picked = []
    remaining = ranked.to_dict("records")
    family_counts: dict[str, int] = {}
    while remaining and len(picked) < top_n:
        choice_index = None
        for index, row in enumerate(remaining):
            if family_counts.get(row["family"], 0) >= 3:
                continue
            if len(picked) < 6:
                sides = {item["side"] for item in picked}
                instruments = {item["instrument"] for item in picked}
                if "long_only" not in sides and row["side"] != "long_only":
                    continue
                if len(picked) >= 1 and "short_only" not in sides and row["side"] != "short_only":
                    continue
                if len(picked) >= 2 and "MGC" not in instruments and row["instrument"] != "MGC":
                    continue
                if len(picked) >= 3 and "MNQ" not in instruments and row["instrument"] != "MNQ":
                    continue
            choice_index = index
            break
        if choice_index is None:
            choice_index = 0
        choice = remaining.pop(choice_index)
        picked.append(choice)
        family_counts[choice["family"]] = family_counts.get(choice["family"], 0) + 1
    picked_ids = {row["hypothesis_id"] for row in picked}
    tail = [row for row in remaining if row["hypothesis_id"] not in picked_ids]
    return pd.DataFrame(picked + tail)
