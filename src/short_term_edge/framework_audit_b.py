from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from .phase_common import deterministic_json, ensure_directory, safe_divide, write_csv_artifact, write_json_artifact

PHASES = ("phase10b", "phase11a", "phase12a")
RESEARCH_ONLY_GUARDRAIL = "Research/simulation only. No live trading, broker adapters, order routing, webhooks, credential storage, automated execution, or LLM-driven trade decisions."
OFFICIAL_GATES = {
    "best_day_concentration": 0.15,
    "best_trade_concentration": 0.08,
    "positive_wf_test_folds_pct": 0.90,
    "min_active_days": 35,
    "min_trades": 60,
    "trades_per_active_day_min": 1.0,
    "trades_per_active_day_max": 3.0,
}


@dataclass(frozen=True)
class FrameworkAuditBConfig:
    phases: tuple[str, ...] = PHASES
    best_day_thresholds: tuple[float, ...] = (0.15, 0.20, 0.25, 0.30)
    best_trade_thresholds: tuple[float, ...] = (0.08, 0.12, 0.15, 0.20, 0.30)
    positive_fold_thresholds: tuple[float, ...] = (0.90, 0.833, 0.75, 0.667, 0.50)
    active_day_thresholds: tuple[int, ...] = (50, 75, 100)


def load_phase_outputs(output_dir: Path, phases: tuple[str, ...] = PHASES) -> dict[str, dict[str, Any]]:
    loaded: dict[str, dict[str, Any]] = {}
    for phase in phases:
        files = {
            "candidate_results": output_dir / f"{phase}_candidate_results.csv",
            "trade_logs": output_dir / f"{phase}_trade_logs.csv",
            "walk_forward_folds": output_dir / f"{phase}_walk_forward_folds.csv",
            "daily_pnl": output_dir / f"{phase}_daily_pnl.csv",
            "concentration_diagnostics": output_dir / f"{phase}_concentration_diagnostics.csv",
            "recommendation": output_dir / f"{phase}_next_action_recommendation.json",
        }
        missing = [str(path) for path in files.values() if not path.exists()]
        if missing:
            raise FileNotFoundError(f"Missing Framework Audit B input(s) for {phase}: {missing}")
        loaded[phase] = {
            "candidate_results": pd.read_csv(files["candidate_results"]),
            "trade_logs": pd.read_csv(files["trade_logs"]),
            "walk_forward_folds": pd.read_csv(files["walk_forward_folds"]),
            "daily_pnl": pd.read_csv(files["daily_pnl"]),
            "concentration_diagnostics": pd.read_csv(files["concentration_diagnostics"]),
            "recommendation": _read_json(files["recommendation"]),
        }
    return loaded


def run_framework_audit_b(output_dir: Path, config: FrameworkAuditBConfig = FrameworkAuditBConfig()) -> dict[str, pd.DataFrame | dict[str, Any]]:
    data = load_phase_outputs(output_dir, config.phases)
    candidates = _select_audit_candidates(data)
    summary = _research_signal_summary(candidates)
    cost = _cost_waterfall_summary(candidates)
    folds = _fold_stability_summary(candidates, data)
    concentration = _concentration_summary(candidates, data)
    activity = _activity_summary(candidates)
    dependency = _top_trade_day_dependency(candidates, data)
    gate = _gate_sensitivity(data, config)
    recommendation = make_framework_audit_b_recommendation(summary, cost, gate, concentration, activity, dependency)
    return {
        "research_signal_summary": summary,
        "gate_sensitivity": gate,
        "cost_waterfall_summary": cost,
        "fold_stability_summary": folds,
        "concentration_summary": concentration,
        "activity_summary": activity,
        "top_trade_day_dependency": dependency,
        "next_action_recommendation": recommendation,
    }


def _select_audit_candidates(data: dict[str, dict[str, Any]]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for phase, payload in data.items():
        c = payload["candidate_results"].copy()
        if c.empty:
            continue
        c["phase"] = phase
        label_col = _label_col(c, phase)
        rec_id = payload["recommendation"].get("top_candidate", {}).get("candidate_id")
        selected = []
        if rec_id and rec_id in set(c["candidate_id"].astype(str)):
            selected.append(c[c["candidate_id"].astype(str).eq(str(rec_id))].iloc[0])
        else:
            selected.append(c.iloc[0])
        positive = c[(c.get("stress_pnl", 0) > 0) & (c.get("validation_pnl", 0) > 0) & (c.get("holdout_pnl", 0) > 0) & (c.get("walk_forward_stress_pnl", 0) > 0)]
        selected.extend(row for _, row in positive.iterrows())
        for row in selected:
            key = (phase, str(row["candidate_id"]))
            if key in seen:
                continue
            seen.add(key)
            item = row.to_dict()
            item["phase"] = phase
            item["phase_label"] = item.get(label_col, "")
            item["selected_reason"] = "recommendation_top_candidate" if str(item["candidate_id"]) == str(rec_id) else "positive_stress_validation_holdout_wf"
            rows.append(item)
    return pd.DataFrame(rows)


def _research_signal_summary(candidates: pd.DataFrame) -> pd.DataFrame:
    if candidates.empty:
        return pd.DataFrame()
    rows = []
    for _, r in candidates.iterrows():
        rows.append(
            {
                "phase": r["phase"],
                "candidate_id": r["candidate_id"],
                "selected_reason": r.get("selected_reason", ""),
                "label": r.get("phase_label", ""),
                "research_axis_status": r.get("research_axis_status", ""),
                "net_pnl": _f(r.get("net_pnl")),
                "stress_pnl": _f(r.get("stress_pnl")),
                "validation_pnl": _f(r.get("validation_pnl")),
                "holdout_pnl": _f(r.get("holdout_pnl")),
                "walk_forward_stress_pnl": _f(r.get("walk_forward_stress_pnl")),
                "best_day_concentration": _f(r.get("best_day_concentration")),
                "best_trade_concentration": _f(r.get("best_trade_concentration")),
                "trades": int(_f(r.get("trades"))),
                "active_days": int(_f(r.get("active_days"))),
                "interpretation": _interpret_signal(r),
                "reject_reasons": r.get("reject_reasons", ""),
            }
        )
    return pd.DataFrame(rows)


def _cost_waterfall_summary(candidates: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, r in candidates.iterrows():
        gross = _f(r.get("gross_pnl"))
        fees = _f(r.get("fees_only_pnl"))
        net = _f(r.get("net_pnl"))
        stress = _f(r.get("stress_pnl"))
        gross_to_net = round(gross - net, 2)
        net_to_stress = round(net - stress, 2)
        primary = bool(gross > 0 and stress <= 0) or (stress <= 0 and gross_to_net + net_to_stress >= abs(stress))
        rows.append({"phase": r["phase"], "candidate_id": r["candidate_id"], "gross_pnl": gross, "fees_only_pnl": fees, "normal_slippage_pnl": net, "net_pnl": net, "stress_pnl": stress, "gross_to_net_drag": gross_to_net, "net_to_stress_drag": net_to_stress, "costs_primary_failure_reason": primary})
    return pd.DataFrame(rows)


def _gate_sensitivity(data: dict[str, dict[str, Any]], config: FrameworkAuditBConfig) -> pd.DataFrame:
    all_candidates = []
    for phase, payload in data.items():
        c = payload["candidate_results"].copy()
        c["phase"] = phase
        all_candidates.append(c)
    candidates = pd.concat(all_candidates, ignore_index=True) if all_candidates else pd.DataFrame()
    rows = []
    if candidates.empty:
        return pd.DataFrame()
    for threshold in config.best_day_thresholds:
        mask = _base_gate_mask(candidates) & (candidates["best_day_concentration"] <= threshold) & (candidates["best_trade_concentration"] <= OFFICIAL_GATES["best_trade_concentration"]) & _official_fold_mask(candidates) & _activity_mask(candidates, OFFICIAL_GATES["min_active_days"])
        rows.append(_gate_row("best_day_concentration", threshold, mask, candidates))
    for threshold in config.best_trade_thresholds:
        mask = _base_gate_mask(candidates) & (candidates["best_day_concentration"] <= OFFICIAL_GATES["best_day_concentration"]) & (candidates["best_trade_concentration"] <= threshold) & _official_fold_mask(candidates) & _activity_mask(candidates, OFFICIAL_GATES["min_active_days"])
        rows.append(_gate_row("best_trade_concentration", threshold, mask, candidates))
    for threshold in config.positive_fold_thresholds:
        mask = _base_gate_mask(candidates) & _official_concentration_mask(candidates) & (candidates["positive_wf_test_folds_pct"] >= threshold) & (candidates["walk_forward_stress_pnl"] > 0) & _activity_mask(candidates, OFFICIAL_GATES["min_active_days"])
        rows.append(_gate_row("positive_wf_test_folds_pct", threshold, mask, candidates))
    for threshold in config.active_day_thresholds:
        mask = _base_gate_mask(candidates) & _official_concentration_mask(candidates) & _official_fold_mask(candidates) & _activity_mask(candidates, threshold)
        rows.append(_gate_row("active_days", threshold, mask, candidates))
    return pd.DataFrame(rows)


def _fold_stability_summary(candidates: pd.DataFrame, data: dict[str, dict[str, Any]]) -> pd.DataFrame:
    rows = []
    for _, r in candidates.iterrows():
        folds = data[str(r["phase"])]["walk_forward_folds"]
        seg = folds[folds["candidate_id"].astype(str).eq(str(r["candidate_id"]))]
        dist = [round(float(v), 2) for v in seg.get("stress_pnl", pd.Series(dtype=float)).tolist()]
        worst = min(dist) if dist else _f(r.get("worst_wf_test_fold"))
        total = sum(dist) if dist else _f(r.get("walk_forward_stress_pnl"))
        rows.append({"phase": r["phase"], "candidate_id": r["candidate_id"], "positive_wf_test_folds_pct": _f(r.get("positive_wf_test_folds_pct")), "worst_wf_test_fold": _f(r.get("worst_wf_test_fold")), "fold_stress_pnl_distribution": ";".join(str(v) for v in dist), "one_bad_fold_explains_rejection": bool(worst < 0 and total - worst > 0)})
    return pd.DataFrame(rows)


def _concentration_summary(candidates: pd.DataFrame, data: dict[str, dict[str, Any]]) -> pd.DataFrame:
    rows = []
    for _, r in candidates.iterrows():
        trades = data[str(r["phase"])]["trade_logs"]
        seg = trades[trades["candidate_id"].astype(str).eq(str(r["candidate_id"]))].copy()
        net = _f(r.get("net_pnl"))
        if seg.empty:
            rows.append(_empty_concentration_row(r, net))
            continue
        daily = seg.groupby("trading_session")["net_pnl"].sum().sort_values(ascending=False)
        trade_pnl = seg["net_pnl"].sort_values(ascending=False)
        best_day = float(daily.iloc[0]) if len(daily) else 0.0
        best_trade = float(trade_pnl.iloc[0]) if len(trade_pnl) else 0.0
        top3_trades = float(trade_pnl.head(3).sum()) if len(trade_pnl) else 0.0
        rows.append(
            {
                "phase": r["phase"],
                "candidate_id": r["candidate_id"],
                "best_day_concentration": _f(r.get("best_day_concentration")),
                "best_trade_concentration": _f(r.get("best_trade_concentration")),
                "top3_day_concentration": safe_divide(float(daily.head(3).clip(lower=0).sum()), net) if net > 0 else 1.0,
                "top5_trade_concentration": safe_divide(float(trade_pnl.head(5).clip(lower=0).sum()), net) if net > 0 else 1.0,
                "pnl_without_best_day": round(net - best_day, 2),
                "pnl_without_best_trade": round(net - best_trade, 2),
                "pnl_without_top3_trades": round(net - top3_trades, 2),
                "positive_without_best_day": net - best_day > 0,
                "positive_without_best_trade": net - best_trade > 0,
                "positive_without_top3_trades": net - top3_trades > 0,
            }
        )
    return pd.DataFrame(rows)


def _activity_summary(candidates: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, r in candidates.iterrows():
        active = int(_f(r.get("active_days")))
        trades = int(_f(r.get("trades")))
        tpd = _f(r.get("trades_per_active_day"))
        structural = "structural_or_filter_limited" if active < 75 or trades < 75 else "adequate_sample"
        rows.append({"phase": r["phase"], "candidate_id": r["candidate_id"], "trades": trades, "active_days": active, "trades_per_active_day": tpd, "activity_limitation": structural, "regular_practice_plausible": bool(active >= 75 and 1 <= tpd <= 3)})
    return pd.DataFrame(rows)


def _top_trade_day_dependency(candidates: pd.DataFrame, data: dict[str, dict[str, Any]]) -> pd.DataFrame:
    conc = _concentration_summary(candidates, data)
    if conc.empty:
        return conc
    return conc[["phase", "candidate_id", "pnl_without_best_day", "pnl_without_best_trade", "pnl_without_top3_trades", "positive_without_best_day", "positive_without_best_trade", "positive_without_top3_trades"]].copy()


def make_framework_audit_b_recommendation(summary: pd.DataFrame, cost: pd.DataFrame, gate: pd.DataFrame, concentration: pd.DataFrame, activity: pd.DataFrame, dependency: pd.DataFrame) -> dict[str, Any]:
    if not dependency.empty and not bool((dependency["positive_without_best_day"] & dependency["positive_without_best_trade"]).any()):
        return {"next_action": "pause_strategy_search_and_review_framework", "rationale": "Audited parked signals did not remain positive after removing top day/trade dependency."}
    if not cost.empty and safe_divide(int(cost["costs_primary_failure_reason"].sum()), len(cost)) >= 0.5:
        return {"next_action": "revisit_cost_slippage_assumptions", "rationale": "Cost drag was the primary failure mode for most audited candidates."}
    relaxed = int(gate["pass_count"].max()) if not gate.empty else 0
    official_like = int(gate[(gate["gate_type"].eq("best_day_concentration") & gate["threshold"].eq(0.15))]["pass_count"].max()) if not gate.empty and not gate[(gate["gate_type"].eq("best_day_concentration") & gate["threshold"].eq(0.15))].empty else 0
    if relaxed >= 3 and official_like == 0:
        return {"next_action": "create_two_tier_labeling_system", "rationale": "Several candidates pass relaxed diagnostic gates while failing official gates."}
    if not activity.empty and safe_divide(int((activity["activity_limitation"] == "structural_or_filter_limited").sum()), len(activity)) >= 0.5:
        return {"next_action": "separate_rare_setup_research_track", "rationale": "Activity constraints are a dominant rejection mode among audited signals."}
    if not dependency.empty and bool((dependency["positive_without_best_day"] & dependency["positive_without_best_trade"]).any()):
        return {"next_action": "preserve_as_priority_research_signal_for_more_data", "rationale": "At least one signal remains positive after removing top day and trade but still misses robustness gates."}
    return {"next_action": "pause_strategy_search_and_review_framework", "rationale": "No audited signal produced sufficient robust evidence under official diagnostic criteria."}


def render_framework_audit_b_report(result: dict[str, pd.DataFrame | dict[str, Any]], report_path: Path) -> str:
    summary = result["research_signal_summary"]
    recommendation = result["next_action_recommendation"]
    lines = [
        "# Framework Audit B — Research Signal / Gate / Backtester Sanity Audit",
        "",
        RESEARCH_ONLY_GUARDRAIL,
        "",
        "## Summary",
        "",
        f"- Audit candidates: `{len(summary) if isinstance(summary, pd.DataFrame) else 0}`",
        f"- Next action: `{recommendation.get('next_action')}`",
        f"- Rationale: {recommendation.get('rationale')}",
        "",
        "## Audited Signals",
        "",
        "| Phase | Candidate | Interpretation | Net | Stress | Val | Holdout | Reject reasons |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: | --- |",
    ]
    if isinstance(summary, pd.DataFrame) and not summary.empty:
        for _, r in summary.iterrows():
            lines.append(f"| {r['phase']} | `{r['candidate_id']}` | {r['interpretation']} | {float(r['net_pnl']):.2f} | {float(r['stress_pnl']):.2f} | {float(r['validation_pnl']):.2f} | {float(r['holdout_pnl']):.2f} | {r['reject_reasons']} |")
    lines += [
        "",
        "## Outputs",
        "",
        "- `outputs/framework_audit_b_research_signal_summary.csv`",
        "- `outputs/framework_audit_b_gate_sensitivity.csv`",
        "- `outputs/framework_audit_b_cost_waterfall_summary.csv`",
        "- `outputs/framework_audit_b_fold_stability_summary.csv`",
        "- `outputs/framework_audit_b_concentration_summary.csv`",
        "- `outputs/framework_audit_b_activity_summary.csv`",
        "- `outputs/framework_audit_b_top_trade_day_dependency.csv`",
        "- `outputs/framework_audit_b_next_action_recommendation.json`",
        f"- `{report_path.as_posix()}`",
    ]
    return "\n".join(lines) + "\n"


def write_framework_audit_b_outputs(result: dict[str, pd.DataFrame | dict[str, Any]], output_dir: Path, report_path: Path) -> dict[str, Path]:
    ensure_directory(output_dir)
    ensure_directory(report_path.parent)
    mapping = {
        "research_signal_summary": output_dir / "framework_audit_b_research_signal_summary.csv",
        "gate_sensitivity": output_dir / "framework_audit_b_gate_sensitivity.csv",
        "cost_waterfall_summary": output_dir / "framework_audit_b_cost_waterfall_summary.csv",
        "fold_stability_summary": output_dir / "framework_audit_b_fold_stability_summary.csv",
        "concentration_summary": output_dir / "framework_audit_b_concentration_summary.csv",
        "activity_summary": output_dir / "framework_audit_b_activity_summary.csv",
        "top_trade_day_dependency": output_dir / "framework_audit_b_top_trade_day_dependency.csv",
    }
    paths: dict[str, Path] = {}
    for key, path in mapping.items():
        write_csv_artifact(result[key], path)  # type: ignore[arg-type]
        paths[key] = path
    rec_path = output_dir / "framework_audit_b_next_action_recommendation.json"
    write_json_artifact(result["next_action_recommendation"], rec_path)
    report_path.write_text(render_framework_audit_b_report(result, report_path), encoding="utf-8")
    paths["recommendation"] = rec_path
    paths["report"] = report_path
    return paths


def recommendation_to_json(recommendation: dict[str, Any]) -> str:
    return deterministic_json(recommendation)


def _base_gate_mask(c: pd.DataFrame) -> pd.Series:
    return (c["net_pnl"] > 0) & (c["stress_pnl"] > 0) & (c["validation_pnl"] > 0) & (c["holdout_pnl"] > 0) & (c["walk_forward_stress_pnl"] > 0) & (c["max_drawdown"] >= -6000)


def _official_concentration_mask(c: pd.DataFrame) -> pd.Series:
    return (c["best_day_concentration"] <= OFFICIAL_GATES["best_day_concentration"]) & (c["best_trade_concentration"] <= OFFICIAL_GATES["best_trade_concentration"])


def _official_fold_mask(c: pd.DataFrame) -> pd.Series:
    return (c["positive_wf_test_folds_pct"] >= OFFICIAL_GATES["positive_wf_test_folds_pct"]) & (c["worst_wf_test_fold"] >= -1500) & (c["walk_forward_stress_pnl"] > 0)


def _activity_mask(c: pd.DataFrame, active_day_threshold: float) -> pd.Series:
    return (c["trades"] >= OFFICIAL_GATES["min_trades"]) & (c["active_days"] >= active_day_threshold) & (c["trades_per_active_day"] >= OFFICIAL_GATES["trades_per_active_day_min"]) & (c["trades_per_active_day"] <= OFFICIAL_GATES["trades_per_active_day_max"])


def _gate_row(gate_type: str, threshold: float, mask: pd.Series, candidates: pd.DataFrame) -> dict[str, Any]:
    return {"gate_type": gate_type, "threshold": threshold, "pass_count": int(mask.sum()), "total_candidates": int(len(candidates)), "diagnostic_only": True}


def _interpret_signal(r: pd.Series) -> str:
    net = _f(r.get("net_pnl"))
    stress = _f(r.get("stress_pnl"))
    val = _f(r.get("validation_pnl"))
    hold = _f(r.get("holdout_pnl"))
    folds = _f(r.get("positive_wf_test_folds_pct"))
    day = _f(r.get("best_day_concentration"))
    trade = _f(r.get("best_trade_concentration"))
    active = _f(r.get("active_days"))
    if min(net, stress, val, hold) <= 0:
        return "likely_noise" if stress <= 0 else "weak_research_signal"
    if active < 60:
        return "candidate_needs_more_history"
    if folds < 0.75 or day > 0.30 or trade > 0.30:
        return "real_but_nontradable_signal"
    if day <= 0.20 or trade <= 0.12 or folds >= 0.75:
        return "framework_gate_too_strict_possible"
    return "weak_research_signal"


def _empty_concentration_row(r: pd.Series, net: float) -> dict[str, Any]:
    return {"phase": r["phase"], "candidate_id": r["candidate_id"], "best_day_concentration": _f(r.get("best_day_concentration")), "best_trade_concentration": _f(r.get("best_trade_concentration")), "top3_day_concentration": 1.0, "top5_trade_concentration": 1.0, "pnl_without_best_day": net, "pnl_without_best_trade": net, "pnl_without_top3_trades": net, "positive_without_best_day": net > 0, "positive_without_best_trade": net > 0, "positive_without_top3_trades": net > 0}


def _label_col(candidates: pd.DataFrame, phase: str) -> str:
    preferred = f"{phase}_label"
    if preferred in candidates.columns:
        return preferred
    labels = [col for col in candidates.columns if col.endswith("_label")]
    return labels[0] if labels else "label"


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
