from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from .phase_common import deterministic_json, ensure_directory, write_csv_artifact, write_json_artifact

PHASES = ("phase10b", "phase11a", "phase12a")
RESEARCH_ONLY_GUARDRAIL = "Research/simulation only. No live trading, broker adapters, order routing, webhooks, credential storage, automated execution, or LLM-driven trade decisions."
REGISTRY_COLUMNS = [
    "phase",
    "candidate_id",
    "family",
    "plain_english_rule",
    "net_pnl",
    "stress_pnl",
    "validation_pnl",
    "holdout_pnl",
    "walk_forward_stress_pnl",
    "positive_wf_test_folds_pct",
    "trades",
    "active_days",
    "best_day_concentration",
    "best_trade_concentration",
    "bootstrap_or_null_classification",
    "signal_evidence_status",
    "tradability_status",
    "research_track",
    "revisit_condition",
    "source_report",
]


def load_registry_inputs(output_dir: Path) -> dict[str, Any]:
    required = {
        "audit_b_summary": output_dir / "framework_audit_b_research_signal_summary.csv",
        "audit_b_recommendation": output_dir / "framework_audit_b_next_action_recommendation.json",
        "audit_c_selection": output_dir / "framework_audit_c_candidate_selection.csv",
        "audit_c_outlier": output_dir / "framework_audit_c_outlier_removal_summary.csv",
        "audit_c_gate_probability": output_dir / "framework_audit_c_gate_probability_summary.csv",
        "audit_c_null_baseline": output_dir / "framework_audit_c_null_baseline_summary.csv",
        "audit_c_family_comparison": output_dir / "framework_audit_c_family_comparison.csv",
        "audit_c_recommendation": output_dir / "framework_audit_c_next_action_recommendation.json",
    }
    for phase in PHASES:
        required[f"{phase}_candidates"] = output_dir / f"{phase}_candidate_results.csv"
    missing = [str(path) for path in required.values() if not path.exists()]
    if missing:
        raise FileNotFoundError(f"Missing Research Signal Registry input(s): {missing}")
    data: dict[str, Any] = {}
    for key, path in required.items():
        data[key] = _read_json(path) if path.suffix == ".json" else pd.read_csv(path)
    return data


def build_research_signal_registry(output_dir: Path) -> dict[str, pd.DataFrame | dict[str, Any]]:
    data = load_registry_inputs(output_dir)
    registry = _build_registry_frame(data)
    recommendation = make_registry_recommendation(registry, data["audit_c_recommendation"])
    return {"registry": registry, "recommendation": recommendation}


def _build_registry_frame(data: dict[str, Any]) -> pd.DataFrame:
    audit_c = data["audit_c_selection"].copy()
    audit_b = data["audit_b_summary"].copy()
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()

    for phase in PHASES:
        phase_rows = audit_c[audit_c["phase"].astype(str).eq(phase)].sort_values("audit_c_rank")
        rec_top = phase_rows[phase_rows["selected_reason"].astype(str).eq("recommendation_top_candidate")].head(1)
        if rec_top.empty and not phase_rows.empty:
            rec_top = phase_rows.head(1)
        for _, row in rec_top.iterrows():
            _append_registry_row(rows, seen, row)

    for _, row in audit_c.sort_values("audit_c_rank").iterrows():
        _append_registry_row(rows, seen, row)

    # Framework Audit B may include parked signals not selected by Audit C; keep registry additive.
    for _, row in audit_b.iterrows():
        normalized = row.to_dict()
        normalized["bootstrap_or_null_classification"] = normalized.get("interpretation", "weak_research_signal")
        normalized["audit_c_classification"] = normalized["bootstrap_or_null_classification"]
        _append_registry_row(rows, seen, pd.Series(normalized))

    registry = pd.DataFrame(rows, columns=REGISTRY_COLUMNS)
    return registry.sort_values(["phase", "research_track", "candidate_id"]).reset_index(drop=True)


def _append_registry_row(rows: list[dict[str, Any]], seen: set[tuple[str, str]], row: pd.Series) -> None:
    key = (str(row.get("phase")), str(row.get("candidate_id")))
    if key in seen:
        return
    seen.add(key)
    classification = str(row.get("audit_c_classification") or row.get("bootstrap_or_null_classification") or "weak_research_signal")
    item = {
        "phase": key[0],
        "candidate_id": key[1],
        "family": family_for_phase(key[0]),
        "plain_english_rule": plain_english_rule(key[0]),
        "net_pnl": _f(row.get("net_pnl")),
        "stress_pnl": _f(row.get("stress_pnl")),
        "validation_pnl": _f(row.get("validation_pnl")),
        "holdout_pnl": _f(row.get("holdout_pnl")),
        "walk_forward_stress_pnl": _f(row.get("walk_forward_stress_pnl")),
        "positive_wf_test_folds_pct": _f(row.get("positive_wf_test_folds_pct")),
        "trades": int(_f(row.get("trades"))),
        "active_days": int(_f(row.get("active_days"))),
        "best_day_concentration": _f(row.get("best_day_concentration")),
        "best_trade_concentration": _f(row.get("best_trade_concentration")),
        "bootstrap_or_null_classification": normalize_bootstrap_classification(classification),
        "source_report": source_report_for_phase(key[0]),
    }
    item["signal_evidence_status"] = signal_evidence_status(item)
    item["tradability_status"] = tradability_status(item)
    item["research_track"] = research_track(item)
    item["revisit_condition"] = revisit_condition(item)
    rows.append(item)


def normalize_bootstrap_classification(value: str) -> str:
    allowed = {
        "likely_noise",
        "weak_research_signal",
        "real_but_nontradable_signal",
        "priority_research_signal_for_more_data",
        "framework_gate_too_strict_possible",
        "candidate_needs_more_history",
    }
    return value if value in allowed else "weak_research_signal"


def signal_evidence_status(row: dict[str, Any]) -> str:
    classification = str(row.get("bootstrap_or_null_classification", ""))
    if _f(row.get("stress_pnl")) <= 0:
        return "no_signal"
    if classification == "priority_research_signal_for_more_data":
        return "priority_research_signal_for_more_data"
    if classification == "real_but_nontradable_signal":
        return "real_but_nontradable_signal"
    if min(_f(row.get("validation_pnl")), _f(row.get("holdout_pnl")), _f(row.get("walk_forward_stress_pnl"))) > 0:
        return "positive_research_signal"
    return "weak_research_signal"


def tradability_status(row: dict[str, Any]) -> str:
    if _f(row.get("stress_pnl")) <= 0 or _f(row.get("net_pnl")) <= 0:
        return "not_tradable_negative"
    if _f(row.get("active_days")) < 60 or _f(row.get("trades")) < 60:
        return "not_tradable_low_activity"
    if _f(row.get("best_day_concentration")) > 0.15 or _f(row.get("best_trade_concentration")) > 0.08:
        return "not_tradable_concentrated"
    if _f(row.get("positive_wf_test_folds_pct")) < 0.90:
        return "not_tradable_fold_unstable"
    if _official_gate_pass(row):
        return "review_packet_candidate"
    return "watchlist_needs_more_history"


def research_track(row: dict[str, Any]) -> str:
    if row.get("signal_evidence_status") == "priority_research_signal_for_more_data":
        return "priority_research_signal_for_more_data"
    if row.get("tradability_status") == "not_tradable_low_activity":
        return "rare_setup_research_signal"
    if row.get("signal_evidence_status") in {"positive_research_signal", "real_but_nontradable_signal"}:
        return "parked_research_signal"
    return "regular_practice_candidate"


def revisit_condition(row: dict[str, Any]) -> str:
    status = str(row.get("tradability_status"))
    if status == "not_tradable_negative":
        return "Do not revisit without new evidence that stress/validation/holdout behavior changed."
    if status == "not_tradable_low_activity":
        return "Revisit only after materially more sessions improve sample size without changing rules."
    if status == "not_tradable_concentrated":
        return "Revisit only if additional data reduces top-day/trade concentration under official gates."
    if status == "not_tradable_fold_unstable":
        return "Revisit only after unchanged rules show stronger fold stability."
    return "Revisit only through a review packet; this registry does not approve paper trading."


def make_registry_recommendation(registry: pd.DataFrame, audit_c_recommendation: dict[str, Any]) -> dict[str, Any]:
    counts = registry["research_track"].value_counts().sort_index().to_dict() if not registry.empty else {}
    priority_count = int(counts.get("priority_research_signal_for_more_data", 0))
    if priority_count:
        next_action = "preserve_priority_research_signals_for_more_data"
        rationale = "Registry contains priority research signals, but none are approved for paper trading."
    elif int(counts.get("parked_research_signal", 0)) or int(counts.get("rare_setup_research_signal", 0)):
        next_action = "maintain_two_tier_research_signal_registry"
        rationale = "Audit C supports separating signal evidence from tradability/practice readiness while preserving official gates."
    else:
        next_action = "pause_strategy_search_and_review_framework"
        rationale = "Registry contains no positive parked research evidence."
    return {
        "next_action": next_action,
        "rationale": rationale,
        "source_audit_c_next_action": audit_c_recommendation.get("next_action", ""),
        "paper_trading_approved": False,
        "official_gates_changed": False,
        "registry_counts": {str(k): int(v) for k, v in counts.items()},
    }


def write_registry_outputs(result: dict[str, pd.DataFrame | dict[str, Any]], output_dir: Path, report_dir: Path) -> dict[str, Path]:
    ensure_directory(output_dir)
    ensure_directory(report_dir)
    registry = result["registry"]
    recommendation = result["recommendation"]
    paths = {
        "registry_csv": output_dir / "research_signal_registry.csv",
        "registry_json": output_dir / "research_signal_registry.json",
        "recommendation": output_dir / "research_signal_registry_next_action_recommendation.json",
        "report": report_dir / "research_signal_registry_report.md",
    }
    write_csv_artifact(registry, paths["registry_csv"])  # type: ignore[arg-type]
    paths["registry_json"].write_text(deterministic_json(registry.to_dict(orient="records")), encoding="utf-8")  # type: ignore[union-attr]
    write_json_artifact(recommendation, paths["recommendation"])  # type: ignore[arg-type]
    paths["report"].write_text(render_registry_report(registry, recommendation), encoding="utf-8")  # type: ignore[union-attr,arg-type]
    return paths


def render_registry_report(registry: pd.DataFrame, recommendation: dict[str, Any]) -> str:
    lines = [
        "# Research Signal Registry A — Two-Tier Labeling System",
        "",
        RESEARCH_ONLY_GUARDRAIL,
        "",
        "## Why Two-Tier Labeling Was Added",
        "",
        "Framework Audit B/C found signals that can show positive bootstrap/outlier evidence while still failing tradability gates. The registry is additive and does not alter official phase labels or promotion gates.",
        "",
        "## Signal Evidence vs Tradability",
        "",
        "Signal evidence describes whether the historical rule appears better than noise. Tradability/practice readiness describes whether unchanged official gates allow review. A real-but-nontradable signal remains blocked from paper-review unless official gates pass.",
        "",
        "## Parked Families",
        "",
    ]
    parked = registry[registry["research_track"].isin(["parked_research_signal", "rare_setup_research_signal"])]
    families = sorted(set(parked["family"].astype(str))) if not parked.empty else []
    lines.append("- " + ", ".join(families) if families else "- none")
    priority = registry[registry["research_track"].eq("priority_research_signal_for_more_data")]
    lines += [
        "",
        "## Priority For More Data",
        "",
        "- none" if priority.empty else "- " + ", ".join(sorted(set(priority["family"].astype(str)))),
        "",
        "## Paper Trading Status",
        "",
        "No candidate is approved for paper trading. This registry only separates research evidence from tradability labels.",
        "",
        "## Recommendation",
        "",
        f"- Next action: `{recommendation.get('next_action')}`",
        f"- Rationale: {recommendation.get('rationale')}",
        "",
        "## Registry",
        "",
        "| Phase | Candidate | Evidence | Tradability | Track |",
        "| --- | --- | --- | --- | --- |",
    ]
    for _, r in registry.iterrows():
        lines.append(f"| {r['phase']} | `{r['candidate_id']}` | {r['signal_evidence_status']} | {r['tradability_status']} | {r['research_track']} |")
    return "\n".join(lines) + "\n"


def family_for_phase(phase: str) -> str:
    if phase == "phase10b":
        return "overnight_range_targeted_retest"
    if phase == "phase11a":
        return "opening_range_fade_confirmation"
    if phase == "phase12a":
        return "opening_drive_first_pullback"
    return "unknown"


def plain_english_rule(phase: str) -> str:
    if phase == "phase10b":
        return "MNQ overnight-range targeted retest signal using unchanged Phase 10B rules."
    if phase == "phase11a":
        return "MNQ opening-range fade after stricter confirmation using unchanged Phase 11A rules."
    if phase == "phase12a":
        return "MNQ opening-drive first-pullback continuation using unchanged Phase 12A rules."
    return "Unknown parked research signal."


def source_report_for_phase(phase: str) -> str:
    if phase == "phase10b":
        return "reports/phase10b_research_signal_packet.md"
    if phase == "phase11a":
        return "reports/phase11a_research_signal_packet.md"
    if phase == "phase12a":
        return "reports/phase12a_research_signal_packet.md"
    return "reports/research_signal_registry_report.md"


def recommendation_to_json(recommendation: dict[str, Any]) -> str:
    return deterministic_json(recommendation)


def _official_gate_pass(row: dict[str, Any]) -> bool:
    return (
        _f(row.get("net_pnl")) > 0
        and _f(row.get("stress_pnl")) > 0
        and _f(row.get("validation_pnl")) > 0
        and _f(row.get("holdout_pnl")) > 0
        and _f(row.get("walk_forward_stress_pnl")) > 0
        and _f(row.get("positive_wf_test_folds_pct")) >= 0.90
        and _f(row.get("best_day_concentration")) <= 0.15
        and _f(row.get("best_trade_concentration")) <= 0.08
        and _f(row.get("active_days")) >= 60
        and _f(row.get("trades")) >= 60
    )


def _read_json(path: Path) -> dict[str, Any]:
    import json

    return json.loads(path.read_text(encoding="utf-8"))


def _f(value: Any) -> float:
    try:
        if pd.isna(value):
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0
