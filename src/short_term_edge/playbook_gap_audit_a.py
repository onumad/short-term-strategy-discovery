from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from .data_loader import discover_data_files, load_ohlcv_csv
from .phase_common import ensure_directory, write_csv_artifact, write_json_artifact

RESEARCH_ONLY_GUARDRAIL = "Research/simulation only. No live trading, broker adapters, order routing, webhooks, credential storage, automated execution, or LLM-driven trade decisions."
REALISTIC_MODES = ("one_trade_at_a_time_chronological", "max_one_trade_per_session")
BEST_SET = "audit_a_best_plus_phase13a"
PHASE_GROUPS = {
    "phase10b": "overnight_prior_level_module_coverage",
    "phase11a": "opening_range_fade_coverage",
    "phase12a": "opening_drive_pullback_coverage",
    "phase13a": "prior_rth_breakout_coverage",
}


@dataclass(frozen=True)
class PlaybookGapAuditAConfig:
    weak_fold_threshold: float = 0.0
    worst_days_limit: int = 20


def load_playbook_gap_audit_inputs(project_root: Path) -> dict[str, Any]:
    output_dir = project_root / "outputs"
    required = {
        "module_registry": output_dir / "playbook_module_registry.csv",
        "research_registry": output_dir / "research_signal_registry.csv",
        "portfolio_results": output_dir / "portfolio_audit_b_portfolio_results.csv",
        "portfolio_daily": output_dir / "portfolio_audit_b_portfolio_daily_pnl.csv",
        "portfolio_folds": output_dir / "portfolio_audit_b_portfolio_walk_forward_folds.csv",
        "incremental_contribution": output_dir / "portfolio_audit_b_incremental_contribution.csv",
        "phase13a_impact": output_dir / "portfolio_audit_b_phase13a_diversifier_impact.csv",
        "portfolio_b_recommendation": output_dir / "portfolio_audit_b_next_action_recommendation.json",
    }
    for phase in ("phase10b", "phase11a", "phase12a", "phase13a"):
        required[f"{phase}_daily"] = output_dir / f"{phase}_daily_pnl.csv"
        required[f"{phase}_trades"] = output_dir / f"{phase}_trade_logs.csv"
    missing = [str(path) for path in required.values() if not path.exists()]
    if missing:
        raise FileNotFoundError(f"Missing Playbook Gap Audit A input(s): {missing}")
    data = {key: _read_json(path) if path.suffix == ".json" else pd.read_csv(path) for key, path in required.items()}
    data["market_features"] = build_market_day_features(project_root / "data" / "raw")
    return data


def run_playbook_gap_audit_a(project_root: Path, config: PlaybookGapAuditAConfig = PlaybookGapAuditAConfig()) -> dict[str, pd.DataFrame | dict[str, Any] | list[dict[str, Any]]]:
    data = load_playbook_gap_audit_inputs(project_root)
    selected = selected_module_keys(data)
    module_daily = build_selected_module_daily_matrix(data, selected)
    coverage = build_module_coverage(data, selected, data["market_features"])
    weak_folds = weak_fold_analysis(data["portfolio_daily"], data["portfolio_folds"], data["portfolio_results"], module_daily, config)
    negative_days = negative_day_analysis(data["portfolio_daily"], data, config)
    no_trade_days = no_trade_day_analysis(data["portfolio_daily"], coverage, data["market_features"])
    gap_summary = summarize_gaps(coverage, negative_days, no_trade_days, weak_folds)
    briefs = build_candidate_module_briefs(gap_summary)
    recommendation = make_recommendation(gap_summary, briefs)
    return {
        "weak_folds": weak_folds,
        "negative_days": negative_days,
        "no_trade_days": no_trade_days,
        "market_day_features": data["market_features"],
        "module_coverage": coverage,
        "gap_summary": gap_summary,
        "candidate_module_briefs": briefs,
        "next_action_recommendation": recommendation,
    }


def selected_module_keys(data: dict[str, Any]) -> pd.DataFrame:
    registry = data["module_registry"].copy()
    keys = set()
    results = data["portfolio_results"]
    for _, row in results.iterrows():
        for key in str(row.get("signal_keys", "")).split(";"):
            if key:
                keys.add(key)
    registry["signal_key"] = registry.apply(lambda r: f"{r['phase']}::{r['candidate_id']}", axis=1)
    return registry[registry["signal_key"].isin(keys)].copy()


def build_selected_module_daily_matrix(data: dict[str, Any], selected: pd.DataFrame) -> pd.DataFrame:
    parts = []
    for _, row in selected.iterrows():
        phase, cid, key = str(row["phase"]), str(row["candidate_id"]), str(row["signal_key"])
        daily = data[f"{phase}_daily"]
        seg = daily[daily["candidate_id"].astype(str).eq(cid)][["trading_session", "net_pnl"]].copy()
        if seg.empty:
            continue
        parts.append(seg.groupby("trading_session", as_index=False)["net_pnl"].sum().rename(columns={"net_pnl": key}))
    if not parts:
        return pd.DataFrame(columns=["trading_session"])
    matrix = parts[0]
    for part in parts[1:]:
        matrix = matrix.merge(part, on="trading_session", how="outer")
    return matrix.fillna(0.0).sort_values("trading_session").reset_index(drop=True)


def weak_fold_analysis(portfolio_daily: pd.DataFrame, portfolio_folds: pd.DataFrame, portfolio_results: pd.DataFrame, module_daily: pd.DataFrame, config: PlaybookGapAuditAConfig) -> pd.DataFrame:
    rows = []
    for _, fold in portfolio_folds.iterrows():
        pdaily = portfolio_daily[(portfolio_daily["portfolio_set"].eq(fold["portfolio_set"])) & (portfolio_daily["portfolio_mode"].eq(fold["portfolio_mode"]))].sort_values("trading_session")
        result_row = portfolio_results[(portfolio_results["portfolio_set"].eq(fold["portfolio_set"])) & (portfolio_results["portfolio_mode"].eq(fold["portfolio_mode"]))]
        portfolio_keys = set()
        if not result_row.empty:
            portfolio_keys = {key for key in str(result_row.iloc[0].get("signal_keys", "")).split(";") if key}
        fold_sessions = fold_sessions_for(pdaily, int(fold["fold"]))
        module_seg = module_daily[module_daily["trading_session"].isin(fold_sessions)] if not module_daily.empty else pd.DataFrame()
        contributors = []
        if not module_seg.empty:
            eligible_cols = [c for c in module_seg.columns if c != "trading_session" and (not portfolio_keys or c in portfolio_keys)]
            for col in eligible_cols:
                if float(module_seg[col].abs().sum()) > 0:
                    contributors.append(col)
        rows.append({
            "portfolio_set": fold["portfolio_set"],
            "portfolio_mode": fold["portfolio_mode"],
            "fold": int(fold["fold"]),
            "fold_pnl": float(fold["net_pnl"]),
            "fold_stress_pnl": float(fold["stress_pnl"]),
            "fold_active_days": int(fold["active_days"]),
            "is_weak_fold": bool(float(fold["stress_pnl"]) <= config.weak_fold_threshold),
            "module_contributors": ";".join(sorted(contributors)),
            "phase13a_contributed": any(c.startswith("phase13a::") for c in contributors),
        })
    return pd.DataFrame(rows).sort_values(["is_weak_fold", "fold_stress_pnl"], ascending=[False, True]).reset_index(drop=True)


def fold_sessions_for(pdaily: pd.DataFrame, fold: int, folds: int = 6) -> list[str]:
    ordered = pdaily.sort_values("trading_session").reset_index(drop=True)
    if ordered.empty:
        return []
    size = max(1, len(ordered) // folds)
    start = (fold - 1) * size
    end = len(ordered) if fold == folds else min(len(ordered), fold * size)
    return ordered.iloc[start:end]["trading_session"].astype(str).tolist()


def negative_day_analysis(portfolio_daily: pd.DataFrame, data: dict[str, Any], config: PlaybookGapAuditAConfig) -> pd.DataFrame:
    rows = []
    phase13_days = phase_daily_sum(data, "phase13a")
    non13_days = sum_phase_daily(data, ["phase10b", "phase11a", "phase12a"])
    for mode in REALISTIC_MODES:
        seg = portfolio_daily[(portfolio_daily["portfolio_set"].eq(BEST_SET)) & (portfolio_daily["portfolio_mode"].eq(mode))].copy()
        seg = seg[seg["net_pnl"] < 0].sort_values("net_pnl").reset_index(drop=True)
        for _, row in seg.iterrows():
            session = str(row["trading_session"])
            p13 = float(phase13_days.get(session, 0.0))
            other = float(non13_days.get(session, 0.0))
            rows.append({
                "portfolio_set": BEST_SET,
                "portfolio_mode": mode,
                "trading_session": session,
                "net_pnl": float(row["net_pnl"]),
                "negative_day_rank": int(_ + 1),
                "is_worst_20_day": bool(int(_ + 1) <= config.worst_days_limit),
                "phase13a_pnl": p13,
                "non_phase13a_pnl": other,
                "phase13a_helped": bool(p13 > 0 and float(row["net_pnl"]) > other),
                "phase13a_hurt": bool(p13 < 0),
                "no_module_helped": bool(p13 <= 0 and other <= 0),
            })
    return pd.DataFrame(rows)


def no_trade_day_analysis(portfolio_daily: pd.DataFrame, coverage: pd.DataFrame, market_features: pd.DataFrame) -> pd.DataFrame:
    rows = []
    feature_sessions = set(market_features["trading_session"].astype(str)) if not market_features.empty else set(coverage["trading_session"].astype(str))
    for mode in REALISTIC_MODES:
        seg = portfolio_daily[(portfolio_daily["portfolio_set"].eq(BEST_SET)) & (portfolio_daily["portfolio_mode"].eq(mode))]
        traded = set(seg[seg["net_pnl"].ne(0.0)]["trading_session"].astype(str))
        all_sessions = sorted(feature_sessions | set(seg["trading_session"].astype(str)))
        for session in all_sessions:
            if session in traded:
                continue
            cov = coverage[coverage["trading_session"].astype(str).eq(session)]
            feat = market_features[market_features["trading_session"].astype(str).eq(session)] if not market_features.empty else pd.DataFrame()
            any_module = bool(cov.iloc[0]["any_module_coverage"]) if not cov.empty else False
            phase13 = bool(cov.iloc[0]["prior_rth_breakout_coverage"]) if not cov.empty else False
            large = bool(feat.iloc[0].get("large_intraday_movement", False)) if not feat.empty else False
            rows.append({
                "portfolio_set": BEST_SET,
                "portfolio_mode": mode,
                "trading_session": session,
                "current_playbook_no_accepted_trade": True,
                "phase13a_added_trade": phase13,
                "no_module_fired_at_all": not any_module,
                "large_intraday_movement": large,
                "rth_range": None if feat.empty else float(feat.iloc[0].get("rth_range", 0.0)),
            })
    return pd.DataFrame(rows)


def build_market_day_features(raw_dir: Path) -> pd.DataFrame:
    files = [p for p in discover_data_files(raw_dir) if "mnq" in p.name.lower()]
    if not files:
        return pd.DataFrame(columns=["trading_session"])
    df = pd.concat([load_ohlcv_csv(path) for path in files], ignore_index=True)
    df = df[df["symbol"].astype(str).str.upper().str.contains("MNQ")]
    rth = df[df["session_segment"].eq("RTH")].sort_values(["trading_session", "timestamp"]).copy()
    if rth.empty:
        return pd.DataFrame(columns=["trading_session"])
    rows = []
    daily = rth.groupby("trading_session", sort=True).agg(rth_open=("open", "first"), rth_close=("close", "last"), rth_high=("high", "max"), rth_low=("low", "min"))
    daily["prior_rth_close"] = daily["rth_close"].shift(1)
    range_median = float((daily["rth_high"] - daily["rth_low"]).median())
    for session, day in rth.groupby("trading_session", sort=True):
        d = daily.loc[session]
        rth_range = float(d["rth_high"] - d["rth_low"])
        first30 = day.head(30)
        first60 = day.head(60)
        lunch = day[(day["timestamp"].dt.strftime("%H:%M") >= "11:30") & (day["timestamp"].dt.strftime("%H:%M") < "13:00")]
        power = day[(day["timestamp"].dt.strftime("%H:%M") >= "14:30") & (day["timestamp"].dt.strftime("%H:%M") <= "15:45")]
        close_pos = float((d["rth_close"] - d["rth_low"]) / rth_range) if rth_range > 0 else 0.5
        prior_high = daily["rth_high"].shift(1).get(session)
        prior_low = daily["rth_low"].shift(1).get(session)
        rows.append({
            "trading_session": str(session),
            "rth_open": float(d["rth_open"]),
            "rth_close": float(d["rth_close"]),
            "rth_high": float(d["rth_high"]),
            "rth_low": float(d["rth_low"]),
            "rth_range": rth_range,
            "first_30m_direction": direction(first30),
            "first_60m_direction": direction(first60),
            "day_close_position_in_rth_range": round(close_pos, 6),
            "rth_trend_day_proxy": bool(close_pos >= 0.8 or close_pos <= 0.2),
            "rth_range_day_proxy": bool(0.35 <= close_pos <= 0.65 and rth_range <= range_median),
            "volatility_bucket": "high" if rth_range >= range_median * 1.25 else "low" if rth_range <= range_median * 0.75 else "normal",
            "gap_from_prior_rth_close": None if pd.isna(d["prior_rth_close"]) else round(float(d["rth_open"] - d["prior_rth_close"]), 2),
            "lunch_range_expansion": bool(not lunch.empty and (float(lunch["high"].max() - lunch["low"].min()) >= rth_range * 0.35)),
            "power_hour_expansion": bool(not power.empty and (float(power["high"].max() - power["low"].min()) >= rth_range * 0.35)),
            "prior_rth_high_low_interaction": bool((not pd.isna(prior_high) and d["rth_high"] >= prior_high) or (not pd.isna(prior_low) and d["rth_low"] <= prior_low)),
            "large_intraday_movement": bool(rth_range >= range_median * 1.25),
        })
    return pd.DataFrame(rows)


def direction(seg: pd.DataFrame) -> str:
    if seg.empty:
        return "unknown"
    diff = float(seg.iloc[-1]["close"] - seg.iloc[0]["open"])
    if diff > 0:
        return "up"
    if diff < 0:
        return "down"
    return "flat"


def build_module_coverage(data: dict[str, Any], selected: pd.DataFrame, market_features: pd.DataFrame) -> pd.DataFrame:
    sessions = set(market_features["trading_session"].astype(str)) if not market_features.empty else set()
    coverage_by_group: dict[str, set[str]] = {v: set() for v in PHASE_GROUPS.values()}
    for _, row in selected.iterrows():
        phase, cid = str(row["phase"]), str(row["candidate_id"])
        trades = data[f"{phase}_trades"]
        seg = trades[trades["candidate_id"].astype(str).eq(cid)]
        days = set(seg["trading_session"].astype(str))
        sessions |= days
        coverage_by_group[PHASE_GROUPS[phase]] |= days
    rows = []
    for session in sorted(sessions):
        row = {"trading_session": session}
        for group, days in coverage_by_group.items():
            row[group] = session in days
        row["any_module_coverage"] = any(row[group] for group in coverage_by_group)
        row["no_coverage"] = not row["any_module_coverage"]
        rows.append(row)
    coverage = pd.DataFrame(rows)
    if not market_features.empty:
        coverage = coverage.merge(market_features, on="trading_session", how="left")
    return coverage


def summarize_gaps(coverage: pd.DataFrame, negative_days: pd.DataFrame, no_trade_days: pd.DataFrame, weak_folds: pd.DataFrame) -> pd.DataFrame:
    rows = []
    def count(mask: pd.Series) -> int:
        return int(mask.fillna(False).sum())
    if coverage.empty:
        return pd.DataFrame(columns=["gap_type", "day_count", "evidence"])
    rows.append({"gap_type": "trend_days_with_no_module", "day_count": count(coverage["rth_trend_day_proxy"] & coverage["no_coverage"]), "evidence": "trend proxy and no selected module coverage"})
    rows.append({"gap_type": "range_days_with_no_module", "day_count": count(coverage["rth_range_day_proxy"] & coverage["no_coverage"]), "evidence": "range proxy and no selected module coverage"})
    rows.append({"gap_type": "high_volatility_reversal_days_with_no_module", "day_count": count(coverage["volatility_bucket"].eq("high") & coverage["rth_range_day_proxy"] & coverage["no_coverage"]), "evidence": "high range, range close, no coverage"})
    rows.append({"gap_type": "low_volatility_expansion_days_with_no_module", "day_count": count(coverage["volatility_bucket"].eq("low") & (coverage["lunch_range_expansion"] | coverage["power_hour_expansion"]) & coverage["no_coverage"]), "evidence": "low daily range with intraday expansion and no coverage"})
    rows.append({"gap_type": "power_hour_expansion_days_with_no_module", "day_count": count(coverage["power_hour_expansion"] & coverage["no_coverage"]), "evidence": "power-hour expansion and no coverage"})
    rows.append({"gap_type": "prior_level_interaction_not_covered_by_phase13a", "day_count": count(coverage["prior_rth_high_low_interaction"] & ~coverage["prior_rth_breakout_coverage"]), "evidence": "prior RTH level touched but Phase 13A did not cover"})
    rows.append({"gap_type": "overlap_heavy_days", "day_count": int((negative_days["phase13a_hurt"].fillna(False)).sum()) if not negative_days.empty else 0, "evidence": "negative days where diversifier hurt/overlapped"})
    rows.append({"gap_type": "weak_folds_after_phase13a", "day_count": int(weak_folds[weak_folds["phase13a_contributed"]]["is_weak_fold"].sum()) if not weak_folds.empty else 0, "evidence": "weak folds where Phase 13A contributed"})
    return pd.DataFrame(rows).sort_values("day_count", ascending=False).reset_index(drop=True)


def build_candidate_module_briefs(gap_summary: pd.DataFrame) -> list[dict[str, Any]]:
    specs = {
        "low_volatility_lunch_expansion": ("low_volatility_day", "range_expansion", "low_volatility_expansion_days_with_no_module", "lunch range, RTH range percentile", "13:00-15:00", "Targets lunch expansion after quiet context, unlike 10B/11A/12A/13A level-specific entries."),
        "power_hour_continuation": ("power_hour_expansion", "trend_continuation", "power_hour_expansion_days_with_no_module", "power-hour range and intraday trend proxy", "14:30-15:45", "Targets late continuation rather than overnight/opening/prior-RTH triggers."),
        "previous_day_midpoint_reaction": ("prior_level_interaction", "prior_level_reaction", "prior_level_interaction_not_covered_by_phase13a", "prior RTH midpoint/high/low", "10:00-14:30", "Uses previous-day midpoint reaction instead of Phase 13A high breakout."),
        "high_volatility_failed_breakout_reversal": ("high_volatility_day", "sweep_reversal", "high_volatility_reversal_days_with_no_module", "day range bucket and failed intraday extreme", "10:30-15:30", "Targets failed breakout reversal rather than opening-range fade or prior-RTH breakout."),
        "trend_day_late_pullback_continuation": ("trend_day", "pullback_continuation", "trend_days_with_no_module", "trend-day proxy and late pullback level", "13:30-15:30", "Targets late trend pullbacks, not opening-drive first pullback."),
    }
    rows = []
    counts = dict(zip(gap_summary["gap_type"], gap_summary["day_count"])) if not gap_summary.empty else {}
    for name, (condition, family, gap, features, window, diff) in specs.items():
        if int(counts.get(gap, 0)) <= 0:
            continue
        rows.append({
            "proposed_module_name": name,
            "target_market_condition": condition,
            "module_family": family,
            "why_it_may_be_uncorrelated": "Targets sessions or intraday windows with weak/no current playbook coverage.",
            "which_gap_it_targets": gap,
            "required_levels_features": features,
            "suggested_trade_window": window,
            "why_it_is_different_from_10B_11A_12A_13A": diff,
            "risk_of_overfit": "medium; future scout should use a small bounded matrix and unchanged chronological validation",
            "suggested_max_spec_budget_for_future_scout": 48,
            "diagnostic_only_no_signals_generated": True,
        })
    return rows


def make_recommendation(gap_summary: pd.DataFrame, briefs: list[dict[str, Any]]) -> dict[str, Any]:
    if gap_summary.empty:
        action = "improve_market_day_feature_audit"
        rationale = "Gap summary could not be computed from available features."
    else:
        top = gap_summary.iloc[0]
        if int(top["day_count"]) <= 0:
            action = "pause_strategy_search_and_review_manual_examples"
            rationale = "No useful uncovered market-condition gap was found."
        elif str(top["gap_type"]) == "overlap_heavy_days":
            action = "playbook_scheduler_a_overlap_priority_rules"
            rationale = "Playbook failures are dominated by overlap/priority diagnostics rather than a missing market regime."
        elif briefs and int(top["day_count"]) >= 10:
            action = "phase14a_targeted_gap_module_scout"
            rationale = f"Weak/no-trade days cluster around {top['gap_type']}."
        elif briefs:
            action = "phase14a_broad_uncorrelated_module_scout_small_matrix"
            rationale = "Gaps exist but are diverse; use a small broad uncorrelated scout."
        else:
            action = "pause_strategy_search_and_review_manual_examples"
            rationale = "No supported candidate module brief emerged from gap diagnostics."
    return {"next_action": action, "rationale": rationale, "official_gates_changed": False, "paper_trading_approved": False}


def render_gap_audit_report(result: dict[str, Any]) -> str:
    rec = result["next_action_recommendation"]
    weak = result["weak_folds"]
    gaps = result["gap_summary"]
    briefs = result["candidate_module_briefs"]
    lines = [
        "# Playbook Gap Audit A — Missing Days / Weak Fold Diagnostic",
        "",
        RESEARCH_ONLY_GUARDRAIL,
        "",
        "Diagnostic only. No signals generated, no strategy rules changed, no gate changes, no promotions, and no paper trading approval.",
        "",
        "## Summary",
        "",
        f"- Weak folds: `{int(weak['is_weak_fold'].sum()) if not weak.empty else 0}`",
        f"- Candidate module briefs: `{len(briefs)}`",
        f"- Next action: `{rec['next_action']}`",
        f"- Rationale: {rec['rationale']}",
        "- Paper trading approved: `false`",
        "",
        "## Top Gap Summary",
        "",
        "| Gap | Days | Evidence |",
        "| --- | ---: | --- |",
    ]
    for _, row in gaps.head(10).iterrows():
        lines.append(f"| {row['gap_type']} | {int(row['day_count'])} | {row['evidence']} |")
    lines += ["", "## Candidate Module Briefs", ""]
    for brief in briefs:
        lines.append(f"- `{brief['proposed_module_name']}` targets `{brief['which_gap_it_targets']}` via `{brief['module_family']}`; window `{brief['suggested_trade_window']}`.")
    return "\n".join(lines) + "\n"


def write_playbook_gap_audit_outputs(result: dict[str, Any], output_dir: Path, report_path: Path) -> dict[str, Path]:
    ensure_directory(output_dir)
    ensure_directory(report_path.parent)
    mapping = {
        "weak_folds": output_dir / "playbook_gap_audit_a_weak_folds.csv",
        "negative_days": output_dir / "playbook_gap_audit_a_negative_days.csv",
        "no_trade_days": output_dir / "playbook_gap_audit_a_no_trade_days.csv",
        "market_day_features": output_dir / "playbook_gap_audit_a_market_day_features.csv",
        "module_coverage": output_dir / "playbook_gap_audit_a_module_coverage.csv",
        "gap_summary": output_dir / "playbook_gap_audit_a_gap_summary.csv",
    }
    paths = {}
    for key, path in mapping.items():
        write_csv_artifact(result[key], path)  # type: ignore[arg-type]
        paths[key] = path
    briefs_path = output_dir / "playbook_gap_audit_a_candidate_module_briefs.json"
    write_json_artifact(result["candidate_module_briefs"], briefs_path)  # type: ignore[arg-type]
    rec_path = output_dir / "playbook_gap_audit_a_next_action_recommendation.json"
    write_json_artifact(result["next_action_recommendation"], rec_path)  # type: ignore[arg-type]
    report_path.write_text(render_gap_audit_report(result), encoding="utf-8")
    paths["candidate_module_briefs"] = briefs_path
    paths["recommendation"] = rec_path
    paths["report"] = report_path
    return paths


def phase_daily_sum(data: dict[str, Any], phase: str) -> dict[str, float]:
    daily = data[f"{phase}_daily"]
    return daily.groupby("trading_session")["net_pnl"].sum().to_dict()


def sum_phase_daily(data: dict[str, Any], phases: list[str]) -> dict[str, float]:
    total: dict[str, float] = {}
    for phase in phases:
        for session, value in phase_daily_sum(data, phase).items():
            total[str(session)] = total.get(str(session), 0.0) + float(value)
    return total


def _read_json(path: Path) -> dict[str, Any]:
    import json

    return json.loads(path.read_text(encoding="utf-8"))
