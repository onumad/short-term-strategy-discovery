from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from pathlib import Path
from typing import Any

import pandas as pd

from .phase_common import ensure_directory, safe_divide, write_csv_artifact, write_json_artifact
from .portfolio_audit_b import (
    OFFICIAL_GATES,
    RESEARCH_ONLY_GUARDRAIL,
    avg_abs_corr,
    concentration,
    concat,
    delta,
    max_drawdown,
    overlap_count,
    signal_key,
    split_signal_key,
    unique,
)
from .portfolio_audit_c import phase_days_existing_condition, portfolio_folds

PHASES = ("phase10b", "phase11a", "phase12a", "phase13a", "phase14a", "phase15a", "phase16a")
PHASE_PRIORITY = {"phase16a": 0, "phase15a": 1, "phase14a": 2, "phase13a": 3, "phase10b": 4, "phase11a": 5, "phase12a": 6}
MODES = ("raw_sum_diagnostic", "one_trade_at_a_time_chronological", "max_one_trade_per_session")
PORTFOLIO_SETS = (
    "scheduler_d_best_reconstructed",
    "scheduler_d_best_plus_phase16a",
    "portfolio_d_best_plus_phase16a",
    "top_cross_family_plus_13a_14a_15a_16a",
    "rare_modules_only",
    "phase16a_only",
    "diversifier_modules_all",
    "greedy_low_correlation_with_phase16a",
    "weak_regime_focused_mix",
)


@dataclass(frozen=True)
class PortfolioAuditEConfig:
    max_selected_modules: int = 32
    greedy_limit: int = 10


def _read_json(path: Path) -> dict[str, Any]:
    import json

    return json.loads(path.read_text(encoding="utf-8"))


def load_portfolio_audit_e_inputs(output_dir: Path) -> dict[str, Any]:
    required = {
        "registry_csv": output_dir / "research_signal_registry.csv",
        "registry_json": output_dir / "research_signal_registry.json",
        "module_registry_csv": output_dir / "playbook_module_registry.csv",
        "module_registry_json": output_dir / "playbook_module_registry.json",
        "rare_policy": output_dir / "playbook_rare_module_policy.json",
        "rare_audit_rules": output_dir / "playbook_rare_module_portfolio_audit_rules.json",
        "framework_e_recommendation": output_dir / "playbook_framework_e_next_action_recommendation.json",
        "portfolio_d_selection": output_dir / "portfolio_audit_d_signal_selection.csv",
        "portfolio_d_results": output_dir / "portfolio_audit_d_portfolio_results.csv",
        "portfolio_d_daily": output_dir / "portfolio_audit_d_portfolio_daily_pnl.csv",
        "portfolio_d_folds": output_dir / "portfolio_audit_d_portfolio_walk_forward_folds.csv",
        "portfolio_d_recommendation": output_dir / "portfolio_audit_d_next_action_recommendation.json",
        "scheduler_d_results": output_dir / "playbook_scheduler_d_overlay_policy_results.csv",
        "scheduler_d_daily": output_dir / "playbook_scheduler_d_daily_pnl.csv",
        "scheduler_d_folds": output_dir / "playbook_scheduler_d_walk_forward_folds.csv",
        "scheduler_d_concentration": output_dir / "playbook_scheduler_d_concentration.csv",
        "scheduler_d_recommendation": output_dir / "playbook_scheduler_d_next_action_recommendation.json",
        "scheduler_c_results": output_dir / "playbook_scheduler_c_pruning_policy_results.csv",
        "scheduler_c_daily": output_dir / "playbook_scheduler_c_daily_pnl.csv",
        "scheduler_c_folds": output_dir / "playbook_scheduler_c_walk_forward_folds.csv",
        "scheduler_c_concentration": output_dir / "playbook_scheduler_c_concentration.csv",
        "scheduler_c_recommendation": output_dir / "playbook_scheduler_c_next_action_recommendation.json",
        "weak_regime_features": output_dir / "weak_fold_regime_audit_b_market_regime_features.csv",
        "weak_fold_days": output_dir / "weak_fold_regime_audit_b_weak_fold_days.csv",
        "bad_day_clusters": output_dir / "weak_fold_regime_audit_b_bad_day_clusters.csv",
        "regime_comparison": output_dir / "weak_fold_regime_audit_b_regime_comparison.csv",
        "phase16a_gap_coverage": output_dir / "phase16a_gap_coverage_summary.csv",
    }
    for phase in PHASES:
        required[f"{phase}_trades"] = output_dir / f"{phase}_trade_logs.csv"
        required[f"{phase}_daily"] = output_dir / f"{phase}_daily_pnl.csv"
        if (output_dir / f"{phase}_candidate_results.csv").exists():
            required[f"{phase}_candidates"] = output_dir / f"{phase}_candidate_results.csv"
        if (output_dir / f"{phase}_walk_forward_folds.csv").exists():
            required[f"{phase}_folds"] = output_dir / f"{phase}_walk_forward_folds.csv"
    missing = [str(path) for path in required.values() if not path.exists()]
    if missing:
        raise FileNotFoundError(f"Missing Portfolio Audit E input(s): {missing}")
    return {key: _read_json(path) if path.suffix == ".json" else pd.read_csv(path) for key, path in required.items()}


def run_portfolio_audit_e(output_dir: Path, config: PortfolioAuditEConfig = PortfolioAuditEConfig()) -> dict[str, pd.DataFrame | dict[str, Any]]:
    data = load_portfolio_audit_e_inputs(output_dir)
    selected = select_portfolio_e_modules(data, config)
    trades = selected_trade_logs(data, selected)
    daily_matrix = build_daily_pnl_matrix(data, selected)
    correlation = signal_correlation(daily_matrix)
    overlap = trade_overlap_summary(trades)
    results, daily, folds, conc, dd, inc, impact16, rare_summary, weak_summary = build_portfolios_e(selected, trades, daily_matrix, correlation, data, config)
    recommendation = make_portfolio_e_recommendation(results, impact16, rare_summary, weak_summary)
    return {
        "signal_selection": selected,
        "signal_correlation": correlation,
        "daily_pnl_matrix": daily_matrix,
        "trade_overlap_summary": overlap,
        "portfolio_results": results,
        "portfolio_daily_pnl": daily,
        "portfolio_walk_forward_folds": folds,
        "portfolio_concentration": conc,
        "portfolio_drawdown_summary": dd,
        "incremental_contribution": inc,
        "phase16a_rare_module_impact": impact16,
        "rare_module_contribution_summary": rare_summary,
        "weak_regime_coverage_summary": weak_summary,
        "next_action_recommendation": recommendation,
    }


def _score_columns(modules: pd.DataFrame) -> list[str]:
    cols = ["net_pnl", "stress_pnl", "validation_pnl", "holdout_pnl", "walk_forward_stress_pnl"]
    for col in cols:
        modules[col] = pd.to_numeric(modules[col], errors="coerce").fillna(0.0) if col in modules else 0.0
    return cols


def select_portfolio_e_modules(data: dict[str, Any], config: PortfolioAuditEConfig = PortfolioAuditEConfig()) -> pd.DataFrame:
    modules = data["module_registry_csv"].copy()
    modules["phase"] = modules["phase"].astype(str)
    modules["candidate_id"] = modules["candidate_id"].astype(str)
    modules["module_id"] = modules.get("module_id", modules["candidate_id"]).astype(str)
    modules["research_track"] = modules.get("research_track", "").astype(str)
    modules["portfolio_role"] = modules.get("portfolio_role", "").astype(str)
    modules["prior_score"] = modules[_score_columns(modules)].sum(axis=1)
    rows: list[pd.Series] = []
    seen: set[tuple[str, str]] = set()

    # Required inclusions first, so the 32-module cap cannot crowd them out.
    for phase in ("phase16a", "phase13a", "phase14a", "phase15a"):
        seg = modules[modules["phase"].eq(phase) & modules["portfolio_role"].eq("diversifier_module")]
        if phase == "phase16a":
            seg = seg[seg["research_track"].eq("rare_setup_research_signal")]
        for _, row in seg.sort_values(["prior_score", "candidate_id"], ascending=[False, True]).iterrows():
            append_module(rows, seen, row, f"required_{phase}_diversifier_module")

    for phase in ("phase10b", "phase11a", "phase12a"):
        phase_rows = modules[modules["phase"].eq(phase) & modules["research_track"].eq("parked_research_signal")]
        reason = f"top_{phase}_parked_signal"
        if phase_rows.empty:
            phase_rows = modules[modules["phase"].eq(phase)]
            reason = f"top_{phase}_fallback_no_parked_signal_in_module_registry"
        if not phase_rows.empty:
            top = phase_rows.sort_values(["prior_score", "net_pnl", "candidate_id"], ascending=[False, False, True]).iloc[0]
            append_module(rows, seen, top, reason)

    for reason, keys in (
        ("scheduler_d_best_reconstructed", scheduler_d_best_signal_keys(data)),
        ("portfolio_d_best_reconstructed", portfolio_d_best_signal_keys(data)),
        ("scheduler_c_best_reconstructed", scheduler_c_best_signal_keys(data)),
    ):
        for key in keys:
            phase, cid = split_signal_key(key)
            matches = modules[modules["phase"].eq(phase) & modules["candidate_id"].eq(cid)]
            if not matches.empty:
                append_module(rows, seen, matches.iloc[0], reason)
            if len(rows) >= config.max_selected_modules:
                break
        if len(rows) >= config.max_selected_modules:
            break

    if len(rows) < config.max_selected_modules:
        fill = modules[modules["research_track"].isin(["parked_research_signal", "rare_setup_research_signal"])].sort_values(["prior_score", "candidate_id"], ascending=[False, True])
        for _, row in fill.iterrows():
            append_module(rows, seen, row, "selected_registry_fill")
            if len(rows) >= config.max_selected_modules:
                break

    selected = pd.DataFrame([r.to_dict() for r in rows[: config.max_selected_modules]])
    if selected.empty:
        return selected
    selected.insert(0, "selection_rank", range(1, len(selected) + 1))
    selected["signal_key"] = selected.apply(lambda r: signal_key(r["phase"], r["candidate_id"]), axis=1)
    selected["outside_module_registry_for_baseline"] = False
    selected["rare_module_validation_class"] = selected.apply(rare_validation_class, axis=1)
    selected["fold_adequacy_status"] = selected.get("fold_adequacy_status", "not_available")
    selected["fold_interpretability"] = selected["fold_adequacy_status"].map(lambda v: "low_activity_not_fully_interpretable" if str(v) == "low_activity_not_fully_interpretable" else "standard_or_not_available")
    selected["module_level_fold_warning"] = selected["fold_adequacy_status"].map(lambda v: "low_activity_fold_warning" if str(v) == "low_activity_not_fully_interpretable" else "not_available")
    selected["playbook_level_contribution_status"] = "pending_portfolio_audit_e"
    return selected


def _best_keys_from_results(results: pd.DataFrame, prefer_non_raw: bool = True) -> list[str]:
    if results.empty or "signal_keys" not in results:
        return []
    seg = results.copy()
    if prefer_non_raw and "portfolio_mode" in seg:
        non_raw = seg[~seg["portfolio_mode"].astype(str).eq("raw_sum_diagnostic")].copy()
        if not non_raw.empty:
            seg = non_raw
    sort_cols = [c for c in ["official_gates_passed", "net_pnl", "active_days", "portfolio_set", "portfolio_mode"] if c in seg]
    ascending = [False, False, False, True, True][: len(sort_cols)]
    row = seg.sort_values(sort_cols, ascending=ascending).iloc[0]
    return [v for v in str(row.get("signal_keys", "")).split(";") if v]


def scheduler_d_best_signal_keys(data: dict[str, Any]) -> list[str]:
    return _best_keys_from_results(data.get("scheduler_d_results", pd.DataFrame()))


def scheduler_c_best_signal_keys(data: dict[str, Any]) -> list[str]:
    return _best_keys_from_results(data.get("scheduler_c_results", pd.DataFrame()))


def portfolio_d_best_signal_keys(data: dict[str, Any]) -> list[str]:
    return _best_keys_from_results(data.get("portfolio_d_results", pd.DataFrame()))


def build_daily_pnl_matrix(data: dict[str, Any], selected: pd.DataFrame) -> pd.DataFrame:
    parts = []
    for _, row in selected.iterrows():
        phase, cid = str(row["phase"]), str(row["candidate_id"])
        daily = data.get(f"{phase}_daily", pd.DataFrame())
        if not {"candidate_id", "trading_session", "net_pnl"}.issubset(daily.columns):
            continue
        seg = daily[daily["candidate_id"].astype(str).eq(cid)][["trading_session", "net_pnl"]].copy()
        if seg.empty:
            continue
        seg = seg.groupby("trading_session", as_index=False)["net_pnl"].sum().rename(columns={"net_pnl": signal_key(phase, cid)})
        parts.append(seg)
    if not parts:
        return pd.DataFrame(columns=["trading_session"])
    matrix = parts[0]
    for part in parts[1:]:
        matrix = matrix.merge(part, on="trading_session", how="outer")
    return matrix.fillna(0.0).sort_values("trading_session").reset_index(drop=True)


def signal_correlation(daily_matrix: pd.DataFrame) -> pd.DataFrame:
    cols = [c for c in daily_matrix.columns if c != "trading_session"]
    if not cols:
        return pd.DataFrame(columns=["signal_a", "signal_b", "daily_pnl_correlation"])
    corr = daily_matrix[cols].corr().fillna(0.0)
    return pd.DataFrame({"signal_a": a, "signal_b": b, "daily_pnl_correlation": round(float(corr.loc[a, b]), 6)} for a in cols for b in cols)


def selected_trade_logs(data: dict[str, Any], selected: pd.DataFrame) -> pd.DataFrame:
    parts = []
    for _, row in selected.iterrows():
        phase, cid = str(row["phase"]), str(row["candidate_id"])
        trades = data.get(f"{phase}_trades", pd.DataFrame())
        if "candidate_id" not in trades:
            continue
        seg = trades[trades["candidate_id"].astype(str).eq(cid)].copy()
        if seg.empty:
            continue
        seg["phase"] = phase
        seg["signal_key"] = signal_key(phase, cid)
        seg["phase_priority"] = PHASE_PRIORITY[phase]
        for col in ("entry_time", "exit_time"):
            seg[col] = pd.to_datetime(seg[col], errors="coerce", utc=True)
        parts.append(seg)
    return concat(parts)


def trade_overlap_summary(trades: pd.DataFrame) -> pd.DataFrame:
    if trades.empty:
        return pd.DataFrame(columns=["signal_key", "same_timestamp_overlap", "overlapping_holding_periods", "same_session_overlap"])
    rows = []
    for key, seg in trades.groupby("signal_key"):
        other = trades[~trades["signal_key"].eq(key)]
        same_ts = int(seg["entry_time"].isin(other["entry_time"]).sum())
        same_session = int(seg["trading_session"].isin(other["trading_session"]).sum())
        overlaps = 0
        for _, trade in seg.iterrows():
            overlaps += int(((other["entry_time"] < trade["exit_time"]) & (other["exit_time"] > trade["entry_time"])).sum())
        rows.append({"signal_key": key, "same_timestamp_overlap": same_ts, "overlapping_holding_periods": overlaps, "same_session_overlap": same_session})
    return pd.DataFrame(rows).sort_values("signal_key").reset_index(drop=True)


def portfolio_sets_e(selected: pd.DataFrame, correlation: pd.DataFrame, data: dict[str, Any], config: PortfolioAuditEConfig = PortfolioAuditEConfig()) -> dict[str, list[str]]:
    all_keys = set(selected["signal_key"].astype(str))
    phase16 = selected[selected["phase"].eq("phase16a")]["signal_key"].astype(str).tolist()
    diversifiers = selected[selected["portfolio_role"].eq("diversifier_module")]["signal_key"].astype(str).tolist()
    rare = selected[selected["research_track"].eq("rare_setup_research_signal")]["signal_key"].astype(str).tolist()
    scheduler_d = [k for k in scheduler_d_best_signal_keys(data) if k in all_keys]
    portfolio_d = [k for k in portfolio_d_best_signal_keys(data) if k in all_keys]
    cross = unique([top_key_for_phase(selected, p) for p in ("phase10b", "phase11a", "phase12a") if top_key_for_phase(selected, p)] + [k for p in ("phase13a", "phase14a", "phase15a", "phase16a") for k in selected[selected["phase"].eq(p) & selected["portfolio_role"].eq("diversifier_module")]["signal_key"].astype(str).tolist()])
    sets = {
        "scheduler_d_best_reconstructed": scheduler_d,
        "scheduler_d_best_plus_phase16a": unique(scheduler_d + phase16),
        "portfolio_d_best_plus_phase16a": unique(portfolio_d + phase16),
        "top_cross_family_plus_13a_14a_15a_16a": cross,
        "rare_modules_only": rare,
        "phase16a_only": phase16,
        "diversifier_modules_all": diversifiers,
        "greedy_low_correlation_with_phase16a": greedy_low_correlation_with_phase16a(selected, correlation, config.greedy_limit),
        "weak_regime_focused_mix": weak_regime_focused_mix(selected, data, phase16, config.greedy_limit),
    }
    return sets


def top_key_for_phase(selected: pd.DataFrame, phase: str) -> str | None:
    seg = selected[selected["phase"].eq(phase)].sort_values(["prior_score", "selection_rank", "candidate_id"], ascending=[False, True, True])
    return None if seg.empty else str(seg.iloc[0]["signal_key"])


def greedy_low_correlation_with_phase16a(selected: pd.DataFrame, correlation: pd.DataFrame, limit: int) -> list[str]:
    eligible = selected.sort_values(["prior_score", "selection_rank", "candidate_id"], ascending=[False, True, True]).copy()
    if eligible.empty:
        return []
    chosen: list[str] = []
    phase16 = eligible[eligible["phase"].eq("phase16a")]
    if not phase16.empty:
        chosen.append(str(phase16.iloc[0]["signal_key"]))
    remaining = [str(v) for v in eligible["signal_key"].tolist() if str(v) not in chosen]
    while remaining and len(chosen) < limit:
        remaining.sort(key=lambda key: (avg_abs_corr(key, chosen, correlation), -score_for_key(key, selected), key))
        chosen.append(remaining.pop(0))
    return chosen[:limit]


def weak_regime_focused_mix(selected: pd.DataFrame, data: dict[str, Any], phase16: list[str], limit: int) -> list[str]:
    weak_days = set(data.get("weak_fold_days", pd.DataFrame()).get("trading_session", pd.Series(dtype=str)).astype(str))
    matrix = build_daily_pnl_matrix(data, selected)
    scores: list[tuple[float, str]] = []
    for key in [c for c in matrix.columns if c != "trading_session"]:
        seg = matrix[matrix["trading_session"].astype(str).isin(weak_days)]
        scores.append((float(seg[key].sum()) if not seg.empty and key in seg else 0.0, key))
    chosen = unique(phase16[:1])
    for _, key in sorted(scores, key=lambda x: (-x[0], x[1])):
        if key not in chosen:
            chosen.append(key)
        if len(chosen) >= limit:
            break
    return chosen


def score_for_key(key: str, selected: pd.DataFrame) -> float:
    row = selected[selected["signal_key"].astype(str).eq(key)]
    return 0.0 if row.empty else float(row.iloc[0].get("prior_score", 0.0))


def construct_portfolio_trades(trades: pd.DataFrame, signal_keys: list[str], mode: str) -> tuple[pd.DataFrame, int, int]:
    seg = trades[trades["signal_key"].isin(signal_keys)].copy()
    if seg.empty:
        return seg, 0, 0
    seg = seg.sort_values(["entry_time", "phase_priority", "candidate_id", "exit_time"]).reset_index(drop=True)
    if mode == "raw_sum_diagnostic":
        return seg, 0, 0
    accepted = []
    skipped_overlap = 0
    skipped_session = 0
    used_sessions: set[str] = set()
    last_exit = None
    for _, row in seg.iterrows():
        session = str(row["trading_session"])
        if mode == "max_one_trade_per_session" and session in used_sessions:
            skipped_session += 1
            continue
        if mode == "one_trade_at_a_time_chronological" and last_exit is not None and row["entry_time"] < last_exit:
            skipped_overlap += 1
            continue
        accepted.append(row)
        used_sessions.add(session)
        if mode == "one_trade_at_a_time_chronological":
            last_exit = row["exit_time"] if last_exit is None else max(last_exit, row["exit_time"])
    return pd.DataFrame(accepted), skipped_overlap, skipped_session


def build_portfolios_e(selected: pd.DataFrame, trades: pd.DataFrame, daily_matrix: pd.DataFrame, correlation: pd.DataFrame, data: dict[str, Any], config: PortfolioAuditEConfig) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    sets = portfolio_sets_e(selected, correlation, data, config)
    result_rows: list[dict[str, Any]] = []
    daily_rows: list[pd.DataFrame] = []
    fold_rows: list[pd.DataFrame] = []
    conc_rows: list[dict[str, Any]] = []
    dd_rows: list[dict[str, Any]] = []
    inc_rows: list[dict[str, Any]] = []
    baseline_metrics: dict[str, dict[str, Any]] = {}
    for mode in MODES:
        accepted, skipped_overlap, skipped_session = construct_portfolio_trades(trades, sets.get("scheduler_d_best_reconstructed", []), mode)
        daily = portfolio_daily_from_mode(daily_matrix, accepted, sets.get("scheduler_d_best_reconstructed", []), "scheduler_d_best_reconstructed", mode)
        baseline_metrics[mode] = portfolio_metrics_e("baseline", "baseline", sets.get("scheduler_d_best_reconstructed", []), accepted, daily, skipped_overlap, skipped_session, correlation, {}, daily_matrix, data)
    for set_name, keys in sets.items():
        for mode in MODES:
            accepted, skipped_overlap, skipped_session = construct_portfolio_trades(trades, keys, mode)
            daily = portfolio_daily_from_mode(daily_matrix, accepted, keys, set_name, mode)
            baseline = baseline_metrics.get(mode, {})
            metrics = portfolio_metrics_e(set_name, mode, keys, accepted, daily, skipped_overlap, skipped_session, correlation, baseline, daily_matrix, data)
            result_rows.append(metrics)
            daily_rows.append(daily)
            fold_rows.append(portfolio_folds(set_name, mode, daily))
            conc_rows.append({k: metrics[k] for k in ("portfolio_set", "portfolio_mode", "best_day_concentration", "best_trade_concentration", "top_3_day_concentration", "top_5_trade_concentration")})
            dd_rows.append({"portfolio_set": set_name, "portfolio_mode": mode, "max_drawdown": metrics["max_drawdown"]})
            inc_rows.append(incremental_contribution_row(set_name, mode, keys, accepted, daily_matrix, baseline, skipped_overlap, skipped_session, data))
    results = pd.DataFrame(result_rows)
    incremental = pd.DataFrame(inc_rows)
    impact16 = phase16a_impact(results, incremental)
    rare_summary = rare_module_contribution_summary(selected, results, trades)
    weak_summary = weak_regime_coverage_summary(results, daily_matrix, data)
    return results, concat(daily_rows), concat(fold_rows), pd.DataFrame(conc_rows), pd.DataFrame(dd_rows), incremental, impact16, rare_summary, weak_summary


def portfolio_daily_from_mode(daily_matrix: pd.DataFrame, accepted: pd.DataFrame, signal_keys: list[str], set_name: str, mode: str) -> pd.DataFrame:
    if mode == "raw_sum_diagnostic":
        cols = [c for c in signal_keys if c in daily_matrix.columns]
        daily = daily_matrix[["trading_session", *cols]].copy() if cols else pd.DataFrame(columns=["trading_session"])
        daily["net_pnl"] = daily[cols].sum(axis=1) if cols else 0.0
        if cols:
            daily = daily[daily[cols].ne(0.0).any(axis=1)].copy()
    else:
        daily = accepted.groupby("trading_session", as_index=False)["net_pnl"].sum() if not accepted.empty else pd.DataFrame(columns=["trading_session", "net_pnl"])
    daily["portfolio_set"] = set_name
    daily["portfolio_mode"] = mode
    return daily[["portfolio_set", "portfolio_mode", "trading_session", "net_pnl"]].sort_values("trading_session").reset_index(drop=True)


def portfolio_metrics_e(set_name: str, mode: str, signal_keys: list[str], trades: pd.DataFrame, daily: pd.DataFrame, skipped_overlap: int, skipped_session: int, correlation: pd.DataFrame, baseline: dict[str, Any], daily_matrix: pd.DataFrame, data: dict[str, Any]) -> dict[str, Any]:
    net = round(float(daily["net_pnl"].sum()), 2) if not daily.empty else 0.0
    stress = round(float(trades["stress_pnl"].sum()), 2) if "stress_pnl" in trades else None
    split = trades.groupby("split")["net_pnl"].sum().to_dict() if "split" in trades else {}
    validation = round(float(split.get("validation", 0.0)), 2) if split else None
    holdout = round(float(split.get("holdout", 0.0)), 2) if split else None
    folds = portfolio_folds(set_name, mode, daily)
    wf_test = round(float(folds["net_pnl"].sum()), 2) if not folds.empty else None
    wf_stress = round(float(folds["stress_pnl"].sum()), 2) if not folds.empty else None
    pos_folds = round(safe_divide(int((folds["stress_pnl"] > 0).sum()), len(folds)), 6) if not folds.empty else None
    worst_fold = round(float(folds["stress_pnl"].min()), 2) if not folds.empty else None
    trade_conc = concentration(trades["net_pnl"] if not trades.empty else pd.Series(dtype=float))
    day_conc = concentration(daily["net_pnl"] if not daily.empty else pd.Series(dtype=float))
    corr_vals = pairwise_corr_for(signal_keys, correlation)
    active_days = int(daily["trading_session"].nunique()) if not daily.empty else 0
    phase16 = phase_slice(trades, "phase16a")
    rare = trades[trades["signal_key"].isin([k for k in signal_keys if "phase16a::" in k or rare_key(k, data)])] if not trades.empty else pd.DataFrame()
    weak_help_hurt = phase_weak_help_hurt(phase16, data)
    highvol_help_hurt = phase_high_vol_help_hurt(phase16, data)
    conc_delta = delta(day_conc["best"], baseline.get("best_day_concentration"))
    fold_delta = delta(pos_folds, baseline.get("positive_wf_test_folds_pct"))
    drawdown = max_drawdown(daily["net_pnl"] if not daily.empty else pd.Series(dtype=float))
    dd_delta = delta(drawdown, baseline.get("max_drawdown"))
    activity_delta = delta(active_days, baseline.get("active_days"))
    passes = official_gates_pass(net, validation, holdout, wf_stress, pos_folds, day_conc["best"], trade_conc["best"], active_days, baseline)
    label, status = portfolio_label_status(net, validation, holdout, wf_stress, pos_folds, day_conc["best"], trade_conc["best"], active_days, baseline, passes, conc_delta, fold_delta, activity_delta, delta(corr_vals.abs().mean() if len(corr_vals) else 0.0, baseline.get("average_pairwise_daily_correlation")), weak_help_hurt)
    return {
        "portfolio_set": set_name,
        "portfolio_mode": mode,
        "signals": len(signal_keys),
        "signal_keys": ";".join(signal_keys),
        "net_pnl": net,
        "stress_pnl": stress,
        "validation_pnl": validation,
        "holdout_pnl": holdout,
        "walk_forward_test_pnl": wf_test,
        "walk_forward_stress_pnl": wf_stress,
        "positive_wf_test_folds_pct": pos_folds,
        "worst_wf_test_fold": worst_fold,
        "trades": int(len(trades)),
        "active_days": active_days,
        "trades_per_active_day": round(safe_divide(len(trades), active_days), 6),
        "max_drawdown": drawdown,
        "best_day_concentration": day_conc["best"],
        "best_trade_concentration": trade_conc["best"],
        "top_3_day_concentration": day_conc["top3"],
        "top_5_trade_concentration": trade_conc["top5"],
        "average_pairwise_daily_correlation": round(float(corr_vals.abs().mean()), 6) if len(corr_vals) else 0.0,
        "max_pairwise_daily_correlation": round(float(corr_vals.abs().max()), 6) if len(corr_vals) else 0.0,
        "trade_overlap_count": int(overlap_count(trades)),
        "skipped_overlap_count": int(skipped_overlap),
        "skipped_session_count": int(skipped_session),
        "phase16a_net_contribution": phase_net(phase16),
        "phase16a_trade_count": int(len(phase16)),
        "phase16a_active_days": phase_active_days(phase16),
        "phase16a_days_existing_no_trade": phase_days_existing_condition(phase16, signal_keys, daily_matrix, "phase16a::", "no_trade"),
        "phase16a_days_existing_negative_pnl": phase_days_existing_condition(phase16, signal_keys, daily_matrix, "phase16a::", "negative"),
        "incremental_active_days_from_phase16a": incremental_active_days(trades[~trades.get("phase", pd.Series(dtype=str)).eq("phase16a")] if not trades.empty and "phase" in trades else pd.DataFrame(), phase16),
        "phase16a_weak_fold_days_helped": weak_help_hurt["helped"],
        "phase16a_weak_fold_days_hurt": weak_help_hurt["hurt"],
        "phase16a_high_vol_mixed_days_helped": highvol_help_hurt["helped"],
        "phase16a_high_vol_mixed_days_hurt": highvol_help_hurt["hurt"],
        "rare_module_net_contribution": phase_net(rare),
        "rare_module_active_days": phase_active_days(rare),
        "rare_module_overlap_count": int(overlap_count(rare)),
        "fold_delta_vs_scheduler_d_best": fold_delta,
        "concentration_delta_vs_scheduler_d_best": conc_delta,
        "activity_delta_vs_scheduler_d_best": activity_delta,
        "drawdown_delta_vs_scheduler_d_best": dd_delta,
        "official_gates_passed": bool(passes),
        "portfolio_label": label,
        "research_status": status,
        "paper_trading_approved": False,
    }


def rare_key(key: str, data: dict[str, Any]) -> bool:
    modules = data.get("module_registry_csv", pd.DataFrame())
    if modules.empty:
        return False
    phase, cid = split_signal_key(key)
    row = modules[modules["phase"].astype(str).eq(phase) & modules["candidate_id"].astype(str).eq(cid)]
    return False if row.empty else str(row.iloc[0].get("research_track", "")) == "rare_setup_research_signal"


def phase_slice(trades: pd.DataFrame, phase: str) -> pd.DataFrame:
    return trades[trades["phase"].eq(phase)] if not trades.empty and "phase" in trades else pd.DataFrame()


def phase_net(phase_trades: pd.DataFrame) -> float:
    return round(float(phase_trades["net_pnl"].sum()), 2) if not phase_trades.empty else 0.0


def phase_active_days(phase_trades: pd.DataFrame) -> int:
    return int(phase_trades["trading_session"].nunique()) if not phase_trades.empty and "trading_session" in phase_trades else 0


def incremental_active_days(existing: pd.DataFrame, phase_trades: pd.DataFrame) -> int:
    if phase_trades.empty:
        return 0
    existing_days = set(existing["trading_session"].astype(str)) if not existing.empty and "trading_session" in existing else set()
    return len(set(phase_trades["trading_session"].astype(str)) - existing_days)


def incremental_contribution_row(set_name: str, mode: str, signal_keys: list[str], accepted: pd.DataFrame, daily_matrix: pd.DataFrame, baseline: dict[str, Any], skipped_overlap: int, skipped_session: int, data: dict[str, Any]) -> dict[str, Any]:
    phase16 = phase_slice(accepted, "phase16a")
    rare = accepted[accepted["signal_key"].isin([k for k in signal_keys if rare_key(k, data)])] if not accepted.empty else pd.DataFrame()
    return {
        "portfolio_set": set_name,
        "portfolio_mode": mode,
        "phase16a_net_contribution": phase_net(phase16),
        "phase16a_trade_count": int(len(phase16)),
        "phase16a_active_days": phase_active_days(phase16),
        "incremental_active_days_from_phase16a": incremental_active_days(accepted[~accepted["phase"].eq("phase16a")] if not accepted.empty and "phase" in accepted else pd.DataFrame(), phase16),
        "phase16a_days_existing_no_trade": phase_days_existing_condition(phase16, signal_keys, daily_matrix, "phase16a::", "no_trade"),
        "phase16a_days_existing_negative_pnl": phase_days_existing_condition(phase16, signal_keys, daily_matrix, "phase16a::", "negative"),
        "phase16a_overlap_skipped": int(skipped_overlap if mode == "one_trade_at_a_time_chronological" else 0),
        "phase16a_session_skipped": int(skipped_session if mode == "max_one_trade_per_session" else 0),
        "rare_module_net_contribution": phase_net(rare),
        "rare_module_trade_count": int(len(rare)),
        "rare_module_active_days": phase_active_days(rare),
    }


def phase16a_impact(results: pd.DataFrame, incremental: pd.DataFrame) -> pd.DataFrame:
    rows = []
    base = results[results["portfolio_set"].eq("scheduler_d_best_reconstructed")].set_index("portfolio_mode")
    plus = results[results["portfolio_set"].eq("scheduler_d_best_plus_phase16a")].set_index("portfolio_mode")
    for mode in MODES:
        if mode not in base.index or mode not in plus.index:
            continue
        b, p = base.loc[mode], plus.loc[mode]
        inc = incremental[(incremental["portfolio_set"].eq("scheduler_d_best_plus_phase16a")) & (incremental["portfolio_mode"].eq(mode))]
        inc_row = inc.iloc[0].to_dict() if not inc.empty else {}
        rows.append({
            "portfolio_mode": mode,
            "active_days_delta": int(p["active_days"] - b["active_days"]),
            "fold_delta": delta(p["positive_wf_test_folds_pct"], b["positive_wf_test_folds_pct"]),
            "best_day_concentration_delta": delta(p["best_day_concentration"], b["best_day_concentration"]),
            "best_trade_concentration_delta": delta(p["best_trade_concentration"], b["best_trade_concentration"]),
            "drawdown_delta": delta(p["max_drawdown"], b["max_drawdown"]),
            "correlation_delta": delta(p["average_pairwise_daily_correlation"], b["average_pairwise_daily_correlation"]),
            "phase16a_net_contribution": p["phase16a_net_contribution"],
            "phase16a_trade_count": p["phase16a_trade_count"],
            "phase16a_active_days": p["phase16a_active_days"],
            "phase16a_overlap_skipped": int(inc_row.get("phase16a_overlap_skipped", 0)),
            "phase16a_session_skipped": int(inc_row.get("phase16a_session_skipped", 0)),
            "phase16a_days_existing_no_trade": int(inc_row.get("phase16a_days_existing_no_trade", 0)),
            "phase16a_days_existing_negative_pnl": int(inc_row.get("phase16a_days_existing_negative_pnl", 0)),
            "playbook_level_contribution_status": contribution_status(p, b),
        })
    return pd.DataFrame(rows)


def rare_module_contribution_summary(selected: pd.DataFrame, results: pd.DataFrame, trades: pd.DataFrame) -> pd.DataFrame:
    rare_selected = selected[selected["research_track"].eq("rare_setup_research_signal")].copy()
    rows = []
    for _, row in rare_selected.sort_values(["phase", "candidate_id"]).iterrows():
        key = row["signal_key"]
        seg = trades[trades["signal_key"].eq(key)] if not trades.empty else pd.DataFrame()
        rows.append({
            "signal_key": key,
            "phase": row["phase"],
            "candidate_id": row["candidate_id"],
            "rare_module_validation_class": row.get("rare_module_validation_class", rare_validation_class(row)),
            "fold_adequacy_status": row.get("fold_adequacy_status", "not_available"),
            "fold_interpretability": row.get("fold_interpretability", "not_available"),
            "research_track": row.get("research_track", "not_available"),
            "tradability_status": row.get("tradability_status", "not_available"),
            "portfolio_role": row.get("portfolio_role", "not_available"),
            "module_level_fold_warning": row.get("module_level_fold_warning", "not_available"),
            "playbook_level_contribution_status": "positive_contribution" if phase_net(seg) > 0 else "no_positive_contribution",
            "net_contribution": phase_net(seg),
            "trade_count": int(len(seg)),
            "active_days": phase_active_days(seg),
            "overlap_count": int(overlap_count(seg)) if not seg.empty else 0,
        })
    return pd.DataFrame(rows)


def high_vol_mixed_days_from_features(features: pd.DataFrame) -> set[str]:
    if not isinstance(features, pd.DataFrame) or "trading_session" not in features:
        return set()
    high_vol_mask = pd.Series(False, index=features.index)
    mixed_mask = pd.Series(False, index=features.index)
    if "high_volatility_bucket" in features:
        high_vol_mask = features["high_volatility_bucket"].astype(bool)
    elif "volatility_bucket" in features:
        high_vol_mask = features["volatility_bucket"].astype(str).str.lower().eq("high")
    if "intraday_reversal_proxy" in features:
        mixed_mask = mixed_mask | features["intraday_reversal_proxy"].astype(bool)
    if {"first_30m_direction", "first_60m_direction"}.issubset(features.columns):
        mixed_mask = mixed_mask | features["first_30m_direction"].astype(str).ne(features["first_60m_direction"].astype(str))
    if {"morning_trend_proxy", "afternoon_trend_proxy"}.issubset(features.columns):
        mixed_mask = mixed_mask | features["morning_trend_proxy"].astype(bool).ne(features["afternoon_trend_proxy"].astype(bool))
    text = features.apply(lambda row: " ".join(map(str, row.tolist())), axis=1).str.lower()
    return set(features.loc[(high_vol_mask & mixed_mask) | (text.str.contains("high") & text.str.contains("mixed")), "trading_session"].astype(str))


def weak_regime_coverage_summary(results: pd.DataFrame, daily_matrix: pd.DataFrame, data: dict[str, Any]) -> pd.DataFrame:
    weak = set(data.get("weak_fold_days", pd.DataFrame()).get("trading_session", pd.Series(dtype=str)).astype(str))
    high_vol = high_vol_mixed_days_from_features(data.get("weak_regime_features", pd.DataFrame()))
    phase16_cols = [c for c in daily_matrix.columns if c.startswith("phase16a::")]
    rows = []
    for portfolio_set in PORTFOLIO_SETS:
        for day_set_name, days in ("weak_fold", weak), ("high_vol_mixed", high_vol):
            seg = daily_matrix[daily_matrix["trading_session"].astype(str).isin(days)] if days else pd.DataFrame()
            pnl = seg[phase16_cols].sum(axis=1) if not seg.empty and phase16_cols else pd.Series(dtype=float)
            rows.append({
                "portfolio_set": portfolio_set,
                "regime_day_set": day_set_name,
                "regime_days": len(days),
                "phase16a_days_with_contribution": int((pnl != 0).sum()) if len(pnl) else 0,
                "phase16a_helped_days": int((pnl > 0).sum()) if len(pnl) else 0,
                "phase16a_hurt_days": int((pnl < 0).sum()) if len(pnl) else 0,
                "phase16a_net_pnl_on_regime_days": round(float(pnl.sum()), 2) if len(pnl) else 0.0,
            })
    return pd.DataFrame(rows)


def phase_weak_help_hurt(phase_trades: pd.DataFrame, data: dict[str, Any]) -> dict[str, int]:
    days = set(data.get("weak_fold_days", pd.DataFrame()).get("trading_session", pd.Series(dtype=str)).astype(str))
    return _help_hurt(phase_trades, days)


def phase_high_vol_help_hurt(phase_trades: pd.DataFrame, data: dict[str, Any]) -> dict[str, int]:
    days = high_vol_mixed_days_from_features(data.get("weak_regime_features", pd.DataFrame()))
    return _help_hurt(phase_trades, days)


def _help_hurt(trades: pd.DataFrame, days: set[str]) -> dict[str, int]:
    if trades.empty or not days:
        return {"helped": 0, "hurt": 0}
    daily = trades[trades["trading_session"].astype(str).isin(days)].groupby("trading_session")["net_pnl"].sum()
    return {"helped": int((daily > 0).sum()), "hurt": int((daily < 0).sum())}


def contribution_status(row: pd.Series, baseline: pd.Series) -> str:
    if row.get("phase16a_net_contribution", 0) <= 0:
        return "no_incremental_improvement"
    if row.get("active_days", 0) > baseline.get("active_days", 0):
        return "improves_activity"
    if row.get("average_pairwise_daily_correlation", 1) < baseline.get("average_pairwise_daily_correlation", 1):
        return "reduces_correlation"
    return "positive_isolated_research_signal"


def rare_validation_class(row: pd.Series) -> str:
    if str(row.get("research_track", "")) != "rare_setup_research_signal":
        return "not_rare_module"
    if float(row.get("net_pnl", 0) or 0) <= 0:
        return "rare_rejected_negative_or_unstable"
    if str(row.get("portfolio_role", "")) == "diversifier_module":
        return "rare_uncorrelated_diversifier_candidate"
    return "rare_positive_research_signal"


def pairwise_corr_for(signal_keys: list[str], correlation: pd.DataFrame) -> pd.Series:
    vals = []
    for a, b in combinations(signal_keys, 2):
        row = correlation[correlation["signal_a"].eq(a) & correlation["signal_b"].eq(b)]
        if not row.empty:
            vals.append(float(row.iloc[0]["daily_pnl_correlation"]))
    return pd.Series(vals, dtype=float)


def official_gates_pass(net: float, validation: float | None, holdout: float | None, wf_stress: float | None, pos_folds: float | None, best_day: float, best_trade: float, active_days: int, baseline: dict[str, Any]) -> bool:
    return (
        net > 0
        and (validation is None or validation > 0)
        and (holdout is None or holdout > 0)
        and (wf_stress is None or wf_stress > 0)
        and (pos_folds is None or pos_folds >= OFFICIAL_GATES["positive_wf_test_folds_pct"])
        and best_day <= OFFICIAL_GATES["best_day_concentration"]
        and best_trade <= OFFICIAL_GATES["best_trade_concentration"]
        and active_days > int(baseline.get("active_days", -1))
    )


def portfolio_label_status(net: float, validation: float | None, holdout: float | None, wf_stress: float | None, pos_folds: float | None, best_day: float, best_trade: float, active_days: int, baseline: dict[str, Any], passes: bool, conc_delta: float | None, fold_delta: float | None, activity_delta: float | None, corr_delta: float | None, weak_help_hurt: dict[str, int]) -> tuple[str, str]:
    if net <= 0:
        return "portfolio_e_failed_negative", "no_portfolio_benefit"
    if passes:
        return "portfolio_e_candidate_for_review_packet_only", "portfolio_candidate_for_future_review_packet"
    if weak_help_hurt.get("helped", 0) > weak_help_hurt.get("hurt", 0) and fold_delta is not None and fold_delta > 0:
        return "portfolio_e_improves_rare_module_contribution_needs_review", "phase16a_improves_weak_regime_coverage"
    if best_day > OFFICIAL_GATES["best_day_concentration"] or best_trade > OFFICIAL_GATES["best_trade_concentration"]:
        if conc_delta is not None and conc_delta < 0:
            return "portfolio_e_positive_but_concentrated", "phase16a_reduces_concentration"
        if corr_delta is not None and corr_delta < 0:
            return "portfolio_e_positive_but_concentrated", "phase16a_reduces_correlation"
        return "portfolio_e_positive_but_concentrated", "portfolio_still_nontradable"
    if pos_folds is not None and pos_folds < OFFICIAL_GATES["positive_wf_test_folds_pct"]:
        if fold_delta is not None and fold_delta > 0:
            return "portfolio_e_positive_but_fold_unstable", "phase16a_improves_folds"
        return "portfolio_e_positive_but_fold_unstable", "portfolio_still_nontradable"
    if active_days < OFFICIAL_GATES["min_active_days"]:
        return "portfolio_e_positive_but_low_activity", "phase16a_improves_activity"
    if activity_delta is not None and activity_delta > 0:
        return "portfolio_e_improves_rare_module_contribution_needs_review", "phase16a_improves_activity"
    return "portfolio_e_no_incremental_improvement", "portfolio_still_nontradable"


def make_portfolio_e_recommendation(results: pd.DataFrame, impact: pd.DataFrame, rare_summary: pd.DataFrame, weak_summary: pd.DataFrame) -> dict[str, Any]:
    base = {"official_gates_changed": False, "paper_trading_approved": False, "rare_module_track_enabled": True}
    if results.empty:
        return {**base, "next_action": "improve_standard_trade_log_schema_before_more_portfolio_work", "rationale": "Portfolio Audit E metrics were not computable from existing output schemas."}
    active = bool((impact.get("active_days_delta", pd.Series(dtype=float)) > 0).any()) if not impact.empty else False
    corr = bool((impact.get("correlation_delta", pd.Series(dtype=float)) < 0).any()) if not impact.empty else False
    folds = bool((impact.get("fold_delta", pd.Series(dtype=float)) > 0).any()) if not impact.empty else False
    weak = bool((weak_summary.get("phase16a_helped_days", pd.Series(dtype=float)) > weak_summary.get("phase16a_hurt_days", pd.Series(dtype=float))).any()) if not weak_summary.empty else False
    rare_positive = bool((rare_summary.get("net_contribution", pd.Series(dtype=float)) > 0).any()) if not rare_summary.empty else False
    overlap_drawdown = bool((results.get("rare_module_overlap_count", pd.Series(dtype=float)) > 0).any() and (results.get("drawdown_delta_vs_scheduler_d_best", pd.Series(dtype=float)) < 0).any())
    if active and corr and not folds:
        return {**base, "next_action": "keep_phase16a_as_rare_diversifier_and_continue_regime_scouting", "rationale": "Phase 16A improved activity or correlation diagnostics, but fold stability did not materially improve."}
    if weak and folds:
        return {**base, "next_action": "portfolio_audit_f_review_packet_only", "rationale": "Phase 16A improved weak-regime coverage and fold diagnostics but at least one unchanged gate remains missed."}
    if overlap_drawdown:
        return {**base, "next_action": "playbook_scheduler_e_rare_module_priority_audit", "rationale": "Rare modules improved activity as a group but increased overlap or drawdown diagnostics."}
    if not active and not corr and not rare_positive:
        return {**base, "next_action": "park_phase16a_rare_modules_no_retest", "rationale": "Phase 16A rare modules did not improve playbook-level activity, correlation, folds, concentration, drawdown, or weak-regime coverage."}
    if not folds:
        return {**base, "next_action": "phase17a_next_weak_regime_module_scout", "rationale": "Fold instability remains unchanged after adding rare modules."}
    return {**base, "next_action": "keep_phase16a_as_rare_diversifier_and_continue_regime_scouting", "rationale": "Rare modules show diagnostic playbook contribution, but paper trading remains unapproved."}


def append_module(rows: list[pd.Series], seen: set[tuple[str, str]], row: pd.Series, reason: str) -> None:
    key = (str(row["phase"]), str(row["candidate_id"]))
    if key in seen:
        return
    item = row.copy()
    item["selection_reason"] = reason
    rows.append(item)
    seen.add(key)


def render_portfolio_audit_e_report(result: dict[str, pd.DataFrame | dict[str, Any]], report_path: Path) -> str:
    results = result["portfolio_results"]
    impact = result["phase16a_rare_module_impact"]
    rare = result["rare_module_contribution_summary"]
    weak = result["weak_regime_coverage_summary"]
    rec = result["next_action_recommendation"]
    lines = [
        "# Portfolio Audit E — Playbook With Phase 16A Rare High-Vol Modules",
        "",
        RESEARCH_ONLY_GUARDRAIL,
        "",
        "## Scope",
        "",
        "Diagnostic portfolio audit only. It uses existing registries, scheduler/portfolio baselines, weak-regime context, and completed phase outputs; it does not generate signals, run searches, change official gates, promote candidates, approve paper trading, or add live-trading functionality.",
        "",
        "## Summary",
        "",
        f"- Selected modules: `{len(result['signal_selection'])}`",
        f"- Portfolio rows: `{len(results)}`",
        f"- Next action: `{rec.get('next_action')}`",
        f"- Rationale: {rec.get('rationale')}",
        "- Paper trading approved: `false`",
        "",
        "## Phase 16A Impact Versus Scheduler D Best",
        "",
        "| Mode | Active days Δ | Fold Δ | Best-day conc Δ | Best-trade conc Δ | Drawdown Δ | Correlation Δ | PnL | Trades | Active days | Overlap skipped | Session skipped | No-trade days | Negative-PnL days | Contribution status |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    if isinstance(impact, pd.DataFrame) and not impact.empty:
        for _, r in impact.iterrows():
            lines.append(f"| {r['portfolio_mode']} | {int(r['active_days_delta'])} | {float(r['fold_delta'] or 0):.3f} | {float(r['best_day_concentration_delta'] or 0):.3f} | {float(r['best_trade_concentration_delta'] or 0):.3f} | {float(r['drawdown_delta'] or 0):.2f} | {float(r['correlation_delta'] or 0):.3f} | {float(r['phase16a_net_contribution']):.2f} | {int(r['phase16a_trade_count'])} | {int(r['phase16a_active_days'])} | {int(r['phase16a_overlap_skipped'])} | {int(r['phase16a_session_skipped'])} | {int(r['phase16a_days_existing_no_trade'])} | {int(r['phase16a_days_existing_negative_pnl'])} | {r['playbook_level_contribution_status']} |")
    lines += ["", "## Rare Module Contribution", "", "| Signal | Phase | Validation class | Fold adequacy | Research track | Tradability | Role | Playbook contribution | Net | Trades | Days |", "| --- | --- | --- | --- | --- | --- | --- | --- | ---: | ---: | ---: |"]
    if isinstance(rare, pd.DataFrame) and not rare.empty:
        for _, r in rare.iterrows():
            lines.append(f"| {r['signal_key']} | {r['phase']} | {r['rare_module_validation_class']} | {r['fold_adequacy_status']} | {r['research_track']} | {r['tradability_status']} | {r['portfolio_role']} | {r['playbook_level_contribution_status']} | {float(r['net_contribution']):.2f} | {int(r['trade_count'])} | {int(r['active_days'])} |")
    lines += ["", "## Weak-Regime Coverage", "", "| Set | Regime days | Phase16A days | Helped | Hurt | Net |", "| --- | ---: | ---: | ---: | ---: | ---: |"]
    if isinstance(weak, pd.DataFrame) and not weak.empty:
        for _, r in weak[weak["regime_day_set"].eq("weak_fold")].iterrows():
            lines.append(f"| {r['portfolio_set']} | {int(r['regime_days'])} | {int(r['phase16a_days_with_contribution'])} | {int(r['phase16a_helped_days'])} | {int(r['phase16a_hurt_days'])} | {float(r['phase16a_net_pnl_on_regime_days']):.2f} |")
    lines += ["", "## Portfolio Results", "", "| Set | Mode | Net | Active days | Max DD | Avg corr | Best-day conc | Best-trade conc | Positive folds | Label | Status |", "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |"]
    if isinstance(results, pd.DataFrame) and not results.empty:
        for _, r in results.sort_values(["portfolio_mode", "net_pnl"], ascending=[True, False]).iterrows():
            lines.append(f"| {r['portfolio_set']} | {r['portfolio_mode']} | {float(r['net_pnl']):.2f} | {int(r['active_days'])} | {float(r['max_drawdown']):.2f} | {float(r['average_pairwise_daily_correlation']):.3f} | {float(r['best_day_concentration']):.3f} | {float(r['best_trade_concentration']):.3f} | {float(r['positive_wf_test_folds_pct'] or 0):.3f} | {r['portfolio_label']} | {r['research_status']} |")
    lines += ["", "## Interpretation", "", "Phase 16A and rare modules remain research-only. Portfolio Audit E reports diagnostic playbook contribution only; no portfolio is paper-trading approved and no live-trading functionality is added.", ""]
    return "\n".join(lines)


def write_portfolio_audit_e_outputs(result: dict[str, pd.DataFrame | dict[str, Any]], output_dir: Path, report_path: Path) -> dict[str, Path]:
    ensure_directory(output_dir)
    ensure_directory(report_path.parent)
    mapping = {
        "signal_selection": output_dir / "portfolio_audit_e_signal_selection.csv",
        "signal_correlation": output_dir / "portfolio_audit_e_signal_correlation.csv",
        "daily_pnl_matrix": output_dir / "portfolio_audit_e_daily_pnl_matrix.csv",
        "trade_overlap_summary": output_dir / "portfolio_audit_e_trade_overlap_summary.csv",
        "portfolio_results": output_dir / "portfolio_audit_e_portfolio_results.csv",
        "portfolio_daily_pnl": output_dir / "portfolio_audit_e_portfolio_daily_pnl.csv",
        "portfolio_walk_forward_folds": output_dir / "portfolio_audit_e_portfolio_walk_forward_folds.csv",
        "portfolio_concentration": output_dir / "portfolio_audit_e_portfolio_concentration.csv",
        "portfolio_drawdown_summary": output_dir / "portfolio_audit_e_portfolio_drawdown_summary.csv",
        "incremental_contribution": output_dir / "portfolio_audit_e_incremental_contribution.csv",
        "phase16a_rare_module_impact": output_dir / "portfolio_audit_e_phase16a_rare_module_impact.csv",
        "rare_module_contribution_summary": output_dir / "portfolio_audit_e_rare_module_contribution_summary.csv",
        "weak_regime_coverage_summary": output_dir / "portfolio_audit_e_weak_regime_coverage_summary.csv",
    }
    paths: dict[str, Path] = {}
    for key, path in mapping.items():
        write_csv_artifact(result[key], path)  # type: ignore[arg-type]
        paths[key] = path
    rec = output_dir / "portfolio_audit_e_next_action_recommendation.json"
    write_json_artifact(result["next_action_recommendation"], rec)  # type: ignore[arg-type]
    report_path.write_text(render_portfolio_audit_e_report(result, report_path), encoding="utf-8")
    paths["recommendation"] = rec
    paths["report"] = report_path
    return paths
