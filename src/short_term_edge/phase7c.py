from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from .phase7a import Phase7AConfig, _prepare_phase7a_data


@dataclass(frozen=True)
class AssumptionComparison:
    axis: str
    legacy_assumption: str
    current_assumption: str
    drift: str
    severity: str
    recommended_action: str

    def to_dict(self) -> dict[str, str]:
        return {
            "axis": self.axis,
            "legacy_assumption": self.legacy_assumption,
            "current_assumption": self.current_assumption,
            "drift": self.drift,
            "severity": self.severity,
            "recommended_action": self.recommended_action,
        }


@dataclass(frozen=True)
class Phase7CResult:
    comparisons: pd.DataFrame
    legacy_summary: dict[str, Any]
    current_summary: dict[str, Any]


LEGACY_README_DEFAULT = Path("C:/Users/ulzii/Documents/New project/README.md")


def collect_legacy_mgc_combo_summary(legacy_readme: Path = LEGACY_README_DEFAULT) -> dict[str, Any]:
    """Read-only mining of old-project MGC combo assumptions from the legacy README."""
    text = legacy_readme.read_text(encoding="utf-8") if legacy_readme.exists() else ""
    return {
        "source": str(legacy_readme),
        "has_readme": bool(text),
        "instrument": "MGC" if "MGC" in text else "unknown",
        "data_period": _first_match(text, r"mgc_6mo_(\d{4}-\d{2}-\d{2})_to_(\d{4}-\d{2}-\d{2})\.csv", default="unknown"),
        "best_combo": _first_match(text, r"Current best displayed combo.*?`([^`]+)`", default="unknown", flags=re.DOTALL),
        "objective": "payout-first funded-policy objective with restarts" if "payout-first" in text else "net PnL tournament",
        "walk_forward": "30 train days x 20 test days" if "30x20" in text or "--train-days 30 --test-days 20" in text else "not found",
        "quantity": "q2 for aggressive payout-first; q1 for conservative displayed combo" if "--quantity 2" in text else "q1/default",
        "max_trades_per_day": "4/5/20 variants" if "--max-trades-per-day 4" in text and "--max-trades-per-day 20" in text else "not found",
        "risk_policy": "phase-aware funded quantity plus daily profit/loss policy grid" if "--phase-daily-profit-targets" in text else "basic daily risk gates",
        "cost_slippage": "stress scenarios up to 3 commission + 1 tick or 3 ticks slippage" if "stress-slippage-ticks-per-side" in text else "baseline costs only",
        "reported_result": _first_match(
            text,
            r"The current `max4 30x20` path passes evaluation.*?stitched max-loss breach on \d{4}-\d{2}-\d{2}\.",
            default="not found",
            flags=re.DOTALL,
        ),
    }


def collect_current_phase7b_summary(project_root: Path) -> dict[str, Any]:
    results_path = project_root / "outputs" / "phase7b_mgc_combo_results.csv"
    report_path = project_root / "reports" / "phase7b_mgc_combo_report.md"
    summary: dict[str, Any] = {
        "source": str(results_path),
        "instrument": "MGC",
        "objective": "strict net-PnL research gates with 4-tick slippage, concentration, drawdown, validation, and holdout checks",
        "quantity": "q1/current instrument contract math",
        "max_trades_per_day": "3/4 combo variants",
        "risk_policy": "fixed daily loss lockout 250 and daily profit lockout 500 during combo simulation",
        "cost_slippage": "4 ticks per side aggregate stress for promotion gates",
        "same_bar_policy": "stop-first conservative intrabar handling; ambiguity count is a rejection flag",
    }
    if results_path.exists():
        data = pd.read_csv(results_path)
        summary["rows"] = int(len(data))
        summary["labels"] = data["phase7b_label"].value_counts().to_dict() if "phase7b_label" in data.columns else {}
        if not data.empty:
            top = data.iloc[0]
            summary["top_combo"] = str(top.get("combo_id", "unknown"))
            summary["top_label"] = str(top.get("phase7b_label", "unknown"))
            summary["top_net_pnl"] = float(top.get("net_pnl", 0.0))
            summary["top_slippage_4_ticks_net_pnl"] = float(top.get("slippage_4_ticks_net_pnl", 0.0))
            summary["top_notes"] = str(top.get("phase7b_notes", ""))
    if report_path.exists():
        summary["report"] = str(report_path)
    try:
        prepared, sessions = _prepare_phase7a_data(project_root, Phase7AConfig(symbol="MGC", max_specs=6, min_specs=6, timeframes=(1,)))
        one_minute = prepared["MGC"]["one_minute"]
        summary["complete_sessions"] = int(len(sessions))
        summary["data_period"] = f"{min(sessions)} to {max(sessions)}" if sessions else "unknown"
        summary["one_minute_rows"] = int(len(one_minute))
    except Exception as exc:  # pragma: no cover - defensive for missing local data
        summary["data_period"] = f"unavailable: {exc}"
    return summary


def build_assumption_drift_comparisons(legacy: dict[str, Any], current: dict[str, Any]) -> list[AssumptionComparison]:
    return [
        AssumptionComparison(
            axis="optimization objective",
            legacy_assumption=str(legacy.get("objective", "unknown")),
            current_assumption=str(current.get("objective", "unknown")),
            drift="Legacy winners were selected for funded-payout path survival, while Phase 7B rejects on stricter research robustness gates.",
            severity="high",
            recommended_action="Do not broaden the same combo blindly; first reproduce a payout-path diagnostic under current data so the objective difference is isolated.",
        ),
        AssumptionComparison(
            axis="data window",
            legacy_assumption=str(legacy.get("data_period", "unknown")),
            current_assumption=str(current.get("data_period", "unknown")),
            drift="Legacy documentation references a six-month MGC window; current Phase 7B uses the current repo's full local complete-session MGC history.",
            severity="high",
            recommended_action="Add a bounded date-window mode for the legacy six-month period, then compare full-history vs matched-window results before adding new families.",
        ),
        AssumptionComparison(
            axis="position sizing",
            legacy_assumption=str(legacy.get("quantity", "unknown")),
            current_assumption=str(current.get("quantity", "unknown")),
            drift="Legacy payout leaders used q2 in aggressive modes; current reproduction scores single-contract style results.",
            severity="medium",
            recommended_action="Keep q1 for robustness scoring, but report a separate q2 payout-path sensitivity without changing promotion gates.",
        ),
        AssumptionComparison(
            axis="daily trade cap",
            legacy_assumption=str(legacy.get("max_trades_per_day", "unknown")),
            current_assumption=str(current.get("max_trades_per_day", "unknown")),
            drift="Legacy experiments included 4, 5, and 20 completed-trade caps; Phase 7B only tested 3 and 4.",
            severity="medium",
            recommended_action="If the matched-window audit is not catastrophic, add max-5 as an explicit drift test, not as a promoted production setting.",
        ),
        AssumptionComparison(
            axis="phase and lockout policy",
            legacy_assumption=str(legacy.get("risk_policy", "unknown")),
            current_assumption=str(current.get("risk_policy", "unknown")),
            drift="Legacy phase-aware policies changed funded quantity and daily caps; Phase 7B applies one fixed daily loss/profit policy to all periods.",
            severity="high",
            recommended_action="Implement a research-only phase-policy replay from Phase 7B trade logs before changing entries or exits.",
        ),
        AssumptionComparison(
            axis="cost and slippage stress",
            legacy_assumption=str(legacy.get("cost_slippage", "unknown")),
            current_assumption=str(current.get("cost_slippage", "unknown")),
            drift="Current 4-tick stress is intentionally harsher than several legacy stress leaders and explains much of the negative-transfer result.",
            severity="medium",
            recommended_action="Report a small stress grid side-by-side, while keeping 4-tick stress as the promotion gate.",
        ),
        AssumptionComparison(
            axis="same-bar ambiguity",
            legacy_assumption="not emphasized in legacy README",
            current_assumption=str(current.get("same_bar_policy", "unknown")),
            drift="Current repo rejects candidates with unresolved same-bar stop/target ambiguity; legacy notes focus on payout path and rule breaches instead.",
            severity="high",
            recommended_action="Quantify same-bar ambiguous trades by component and session; do not promote any candidate until ambiguity is removed or bounded conservatively.",
        ),
    ]


def run_phase7c_assumption_drift_audit(project_root: Path, legacy_readme: Path = LEGACY_README_DEFAULT) -> Phase7CResult:
    legacy = collect_legacy_mgc_combo_summary(legacy_readme)
    current = collect_current_phase7b_summary(project_root)
    comparisons = pd.DataFrame([comparison.to_dict() for comparison in build_assumption_drift_comparisons(legacy, current)])
    severity_order = {"high": 0, "medium": 1, "low": 2}
    comparisons = comparisons.sort_values(["severity", "axis"], key=lambda col: col.map(severity_order).fillna(99) if col.name == "severity" else col).reset_index(drop=True)
    return Phase7CResult(comparisons=comparisons, legacy_summary=legacy, current_summary=current)


def render_phase7c_report(result: Phase7CResult, comparisons_path: Path, report_path: Path) -> str:
    label_counts = result.current_summary.get("labels", {})
    lines = [
        "# Phase 7C MGC Legacy Assumption Drift Audit",
        "",
        "Generated by: `./.venv/Scripts/python.exe scripts/run_phase7c_assumption_drift_audit.py`",
        "",
        "## Scope And Guardrails",
        "",
        "- Research/simulation only. No live trading, broker adapters, API-key storage, webhooks, order routing, or automated execution were added.",
        "- Phase 7C audits why the old MGC combo did not transfer cleanly before broadening strategy search.",
        "- This is a diagnostic/reporting phase; it does not loosen Phase 7B promotion gates.",
        "",
        "## Evidence Sources",
        "",
        f"- Legacy source: `{result.legacy_summary.get('source')}`",
        f"- Current Phase 7B results: `{result.current_summary.get('source')}`",
        f"- Comparisons CSV: `{comparisons_path}`",
        f"- Report: `{report_path}`",
        "",
        "## Current Phase 7B Snapshot",
        "",
        f"- Data period: `{result.current_summary.get('data_period', 'unknown')}`",
        f"- Complete sessions: `{result.current_summary.get('complete_sessions', 'unknown')}`",
        f"- Rows scored: `{result.current_summary.get('rows', 'unknown')}`",
        f"- Label counts: `{label_counts}`",
        f"- Top combo: `{result.current_summary.get('top_combo', 'unknown')}` / `{result.current_summary.get('top_label', 'unknown')}`",
        f"- Top net / 4-tick stress: `${result.current_summary.get('top_net_pnl', 0.0):.2f}` / `${result.current_summary.get('top_slippage_4_ticks_net_pnl', 0.0):.2f}`",
        "",
        "## Drift Table",
        "",
        "| Severity | Axis | Legacy Assumption | Current Assumption | Drift | Recommended Action |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for _, row in result.comparisons.iterrows():
        lines.append(
            f"| {row['severity']} | {row['axis']} | {row['legacy_assumption']} | {row['current_assumption']} | {row['drift']} | {row['recommended_action']} |"
        )
    lines.extend(
        [
            "",
            "## Recommendation",
            "",
            "Next implementation should be a bounded Phase 7D payout-path / matched-window diagnostic using existing deterministic Phase 7B trade logs. Do not add new live-trading integrations or broaden entry families until objective, date-window, phase-policy, and same-bar drift are isolated.",
            "",
            "## Repro Command",
            "",
            "```bash",
            "./.venv/Scripts/python.exe scripts/run_phase7c_assumption_drift_audit.py",
            "```",
            "",
        ]
    )
    return "\n".join(lines)


def _first_match(text: str, pattern: str, *, default: str, flags: int = 0) -> str:
    match = re.search(pattern, text, flags)
    if not match:
        return default
    if len(match.groups()) == 2:
        return f"{match.group(1)} to {match.group(2)}"
    if len(match.groups()) == 1:
        return " ".join(match.group(1).split())
    return " ".join(match.group(0).split())
