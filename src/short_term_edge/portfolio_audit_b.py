from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from pathlib import Path
from typing import Any

import pandas as pd

from .phase_common import ensure_directory, safe_divide, write_csv_artifact, write_json_artifact

PHASES = ("phase10b", "phase11a", "phase12a", "phase13a")
PHASE_PRIORITY = {"phase13a": 0, "phase10b": 1, "phase11a": 2, "phase12a": 3}
RESEARCH_ONLY_GUARDRAIL = "Research/simulation only. No live trading, broker adapters, order routing, webhooks, credential storage, automated execution, or LLM-driven trade decisions."
OFFICIAL_GATES = {
    "best_day_concentration": 0.15,
    "best_trade_concentration": 0.08,
    "positive_wf_test_folds_pct": 0.90,
    "min_active_days": 60,
}
MODES = ("raw_sum_diagnostic", "one_trade_at_a_time_chronological", "max_one_trade_per_session")


@dataclass(frozen=True)
class PortfolioAuditBConfig:
    max_selected_modules: int = 20
    greedy_limit: int = 6


def load_portfolio_audit_b_inputs(output_dir: Path) -> dict[str, Any]:
    required = {
        "registry_csv": output_dir / "research_signal_registry.csv",
        "registry_json": output_dir / "research_signal_registry.json",
        "module_registry_csv": output_dir / "playbook_module_registry.csv",
        "module_registry_json": output_dir / "playbook_module_registry.json",
        "registry_b_recommendation": output_dir / "research_signal_registry_b_next_action_recommendation.json",
        "audit_a_selection": output_dir / "portfolio_audit_a_signal_selection.csv",
        "audit_a_correlation": output_dir / "portfolio_audit_a_signal_correlation.csv",
        "audit_a_daily_matrix": output_dir / "portfolio_audit_a_daily_pnl_matrix.csv",
        "audit_a_results": output_dir / "portfolio_audit_a_portfolio_results.csv",
        "audit_a_daily": output_dir / "portfolio_audit_a_portfolio_daily_pnl.csv",
        "audit_a_recommendation": output_dir / "portfolio_audit_a_next_action_recommendation.json",
    }
    for phase in PHASES:
        required[f"{phase}_candidates"] = output_dir / f"{phase}_candidate_results.csv"
        required[f"{phase}_trades"] = output_dir / f"{phase}_trade_logs.csv"
        required[f"{phase}_daily"] = output_dir / f"{phase}_daily_pnl.csv"
        required[f"{phase}_folds"] = output_dir / f"{phase}_walk_forward_folds.csv"
    required["phase13a_corr_registry"] = output_dir / "phase13a_correlation_to_registry.csv"
    required["phase13a_corr_portfolios"] = output_dir / "phase13a_correlation_to_portfolios.csv"
    missing = [str(path) for path in required.values() if not path.exists()]
    if missing:
        raise FileNotFoundError(f"Missing Portfolio Audit B input(s): {missing}")
    return {key: _read_json(path) if path.suffix == ".json" else pd.read_csv(path) for key, path in required.items()}


def run_portfolio_audit_b(output_dir: Path, config: PortfolioAuditBConfig = PortfolioAuditBConfig()) -> dict[str, pd.DataFrame | dict[str, Any]]:
    data = load_portfolio_audit_b_inputs(output_dir)
    selected = select_portfolio_b_modules(data, config)
    trades = selected_trade_logs(data, selected)
    daily_matrix = build_daily_pnl_matrix(data, selected)
    correlation = signal_correlation(daily_matrix)
    overlap = trade_overlap_summary(trades)
    results, daily, folds, concentration_rows, drawdown_rows, incremental, impact = build_portfolios_b(selected, trades, daily_matrix, correlation, data, config)
    recommendation = make_portfolio_b_recommendation(results, impact)
    return {
        "signal_selection": selected,
        "signal_correlation": correlation,
        "daily_pnl_matrix": daily_matrix,
        "trade_overlap_summary": overlap,
        "portfolio_results": results,
        "portfolio_daily_pnl": daily,
        "portfolio_walk_forward_folds": folds,
        "portfolio_concentration": concentration_rows,
        "portfolio_drawdown_summary": drawdown_rows,
        "incremental_contribution": incremental,
        "phase13a_diversifier_impact": impact,
        "next_action_recommendation": recommendation,
    }


def select_portfolio_b_modules(data: dict[str, Any], config: PortfolioAuditBConfig = PortfolioAuditBConfig()) -> pd.DataFrame:
    modules = data["module_registry_csv"].copy()
    modules["phase"] = modules["phase"].astype(str)
    modules["candidate_id"] = modules["candidate_id"].astype(str)
    modules["module_id"] = modules.get("module_id", modules["candidate_id"]).astype(str)
    score_cols = ["net_pnl", "stress_pnl", "validation_pnl", "holdout_pnl", "walk_forward_stress_pnl"]
    for col in score_cols:
        if col in modules:
            modules[col] = pd.to_numeric(modules[col], errors="coerce").fillna(0.0)
    modules["prior_score"] = modules[score_cols].sum(axis=1)
    rows: list[pd.Series] = []
    seen: set[tuple[str, str]] = set()

    audit_a_keys = audit_a_best_signal_keys(data)
    for key in audit_a_keys:
        phase, cid = split_signal_key(key)
        matches = modules[modules["phase"].eq(phase) & modules["candidate_id"].eq(cid)]
        if not matches.empty:
            append_module(rows, seen, matches.iloc[0], "audit_a_best_reconstructed")

    for phase in ("phase10b", "phase11a", "phase12a"):
        phase_rows = modules[modules["phase"].eq(phase) & modules["research_track"].eq("parked_research_signal")]
        if phase_rows.empty:
            phase_rows = modules[modules["phase"].eq(phase)]
        if not phase_rows.empty:
            top = phase_rows.sort_values(["prior_score", "net_pnl", "candidate_id"], ascending=[False, False, True]).iloc[0]
            append_module(rows, seen, top, f"top_{phase}_parked_signal")

    phase13 = modules[modules["phase"].eq("phase13a") & modules["portfolio_role"].eq("diversifier_module")].sort_values(["prior_score", "candidate_id"], ascending=[False, True])
    for _, row in phase13.iterrows():
        append_module(rows, seen, row, "phase13a_diversifier_module")

    parked = modules[modules["research_track"].eq("parked_research_signal")].sort_values(["prior_score", "candidate_id"], ascending=[False, True])
    for _, row in parked.iterrows():
        append_module(rows, seen, row, "selected_parked_research_signal")
        if len(rows) >= config.max_selected_modules:
            break

    rare = modules[modules["research_track"].eq("rare_setup_research_signal")].sort_values(["prior_score", "candidate_id"], ascending=[False, True])
    for _, row in rare.iterrows():
        append_module(rows, seen, row, "selected_rare_setup_research_signal")
        if len(rows) >= config.max_selected_modules:
            break

    selected = pd.DataFrame([r.to_dict() for r in rows[: config.max_selected_modules]])
    if selected.empty:
        return selected
    selected.insert(0, "selection_rank", range(1, len(selected) + 1))
    selected["signal_key"] = selected.apply(lambda r: signal_key(r["phase"], r["candidate_id"]), axis=1)
    return selected


def audit_a_best_signal_keys(data: dict[str, Any]) -> list[str]:
    results = data["audit_a_results"].copy()
    seg = results[results["portfolio_set"].astype(str).eq("diversified_low_correlation_top5")]
    if seg.empty:
        return []
    preferred = seg[seg["portfolio_mode"].astype(str).eq("raw_sum_diagnostic")]
    row = (preferred if not preferred.empty else seg.sort_values("net_pnl", ascending=False)).iloc[0]
    return [v for v in str(row.get("signal_keys", "")).split(";") if v]


def build_daily_pnl_matrix(data: dict[str, Any], selected: pd.DataFrame) -> pd.DataFrame:
    parts = []
    for _, row in selected.iterrows():
        phase = str(row["phase"])
        cid = str(row["candidate_id"])
        daily = data[f"{phase}_daily"]
        seg = daily[daily["candidate_id"].astype(str).eq(cid)][["trading_session", "net_pnl"]].copy()
        if seg.empty:
            continue
        key = signal_key(phase, cid)
        seg = seg.groupby("trading_session", as_index=False)["net_pnl"].sum().rename(columns={"net_pnl": key})
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
    return pd.DataFrame(
        {"signal_a": a, "signal_b": b, "daily_pnl_correlation": round(float(corr.loc[a, b]), 6)}
        for a in cols
        for b in cols
    )


def selected_trade_logs(data: dict[str, Any], selected: pd.DataFrame) -> pd.DataFrame:
    parts = []
    for _, row in selected.iterrows():
        phase, cid = str(row["phase"]), str(row["candidate_id"])
        trades = data[f"{phase}_trades"]
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
        overlap = 0
        for _, trade in seg.iterrows():
            overlap += int(((other["entry_time"] < trade["exit_time"]) & (other["exit_time"] > trade["entry_time"])).sum())
        rows.append({"signal_key": key, "same_timestamp_overlap": same_ts, "overlapping_holding_periods": overlap, "same_session_overlap": same_session})
    return pd.DataFrame(rows).sort_values("signal_key").reset_index(drop=True)


def portfolio_sets_b(selected: pd.DataFrame, correlation: pd.DataFrame, config: PortfolioAuditBConfig = PortfolioAuditBConfig()) -> dict[str, list[str]]:
    phase13 = selected[selected["phase"].eq("phase13a")]["signal_key"].astype(str).tolist()
    audit_a = selected[selected["selection_reason"].astype(str).str.contains("audit_a_best_reconstructed")]["signal_key"].astype(str).tolist()
    sets: dict[str, list[str]] = {
        "audit_a_best_reconstructed": audit_a,
        "audit_a_best_plus_phase13a": unique(audit_a + phase13),
        "top_cross_family_plus_phase13a": unique([top_key_for_phase(selected, p) for p in ("phase10b", "phase11a", "phase12a") if top_key_for_phase(selected, p)] + phase13),
        "diversifier_only_phase13a": phase13,
        "all_parked_modules_with_phase13a": selected[selected["research_track"].eq("parked_research_signal")]["signal_key"].astype(str).tolist(),
        "rare_plus_diversifier_modules": unique(selected[selected["research_track"].eq("rare_setup_research_signal")]["signal_key"].astype(str).tolist() + phase13),
    }
    sets["greedy_low_correlation_with_phase13a"] = greedy_low_correlation_with_phase13a(selected, correlation, config.greedy_limit)
    return sets


def top_key_for_phase(selected: pd.DataFrame, phase: str) -> str | None:
    seg = selected[selected["phase"].eq(phase)].sort_values(["prior_score", "selection_rank", "candidate_id"], ascending=[False, True, True])
    return None if seg.empty else str(seg.iloc[0]["signal_key"])


def greedy_low_correlation_with_phase13a(selected: pd.DataFrame, correlation: pd.DataFrame, limit: int) -> list[str]:
    eligible = selected.sort_values(["prior_score", "selection_rank", "candidate_id"], ascending=[False, True, True]).copy()
    if eligible.empty:
        return []
    chosen = [str(eligible.iloc[0]["signal_key"])]
    phase13 = eligible[eligible["phase"].eq("phase13a")]
    if not phase13.empty and not any(k.startswith("phase13a::") for k in chosen):
        chosen.append(str(phase13.iloc[0]["signal_key"]))
    remaining = [str(v) for v in eligible["signal_key"].tolist() if str(v) not in chosen]
    while remaining and len(chosen) < limit:
        remaining.sort(key=lambda key: (avg_abs_corr(key, chosen, correlation), key))
        chosen.append(remaining.pop(0))
    return chosen[:limit]


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


def build_portfolios_b(selected: pd.DataFrame, trades: pd.DataFrame, daily_matrix: pd.DataFrame, correlation: pd.DataFrame, data: dict[str, Any], config: PortfolioAuditBConfig) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    sets = portfolio_sets_b(selected, correlation, config)
    result_rows: list[dict[str, Any]] = []
    daily_rows: list[pd.DataFrame] = []
    fold_rows: list[pd.DataFrame] = []
    conc_rows: list[dict[str, Any]] = []
    dd_rows: list[dict[str, Any]] = []
    inc_rows: list[dict[str, Any]] = []
    baseline_metrics: dict[str, dict[str, Any]] = {}

    for set_name, keys in sets.items():
        for mode in MODES:
            accepted, skipped_overlap, skipped_session = construct_portfolio_trades(trades, keys, mode)
            daily = portfolio_daily_from_mode(daily_matrix, accepted, keys, set_name, mode)
            if set_name == "audit_a_best_reconstructed":
                baseline_metrics[mode] = simple_metrics(accepted, daily, keys, skipped_overlap, skipped_session, correlation)

    for set_name, keys in sets.items():
        for mode in MODES:
            accepted, skipped_overlap, skipped_session = construct_portfolio_trades(trades, keys, mode)
            daily = portfolio_daily_from_mode(daily_matrix, accepted, keys, set_name, mode)
            baseline = baseline_metrics.get(mode, {})
            metrics = portfolio_metrics_b(set_name, mode, keys, accepted, daily, skipped_overlap, skipped_session, correlation, baseline)
            result_rows.append(metrics)
            daily_rows.append(daily)
            folds = portfolio_folds(set_name, mode, daily)
            fold_rows.append(folds)
            conc_rows.append({k: metrics[k] for k in ("portfolio_set", "portfolio_mode", "best_day_concentration", "best_trade_concentration", "top_3_day_concentration", "top_5_trade_concentration")})
            dd_rows.append({"portfolio_set": set_name, "portfolio_mode": mode, "max_drawdown": metrics["max_drawdown"]})
            inc_rows.append(incremental_contribution_row(set_name, mode, keys, accepted, daily, daily_matrix, baseline, skipped_overlap, skipped_session))
    results = pd.DataFrame(result_rows)
    incremental = pd.DataFrame(inc_rows)
    impact = phase13a_impact(results, incremental)
    return results, concat(daily_rows), concat(fold_rows), pd.DataFrame(conc_rows), pd.DataFrame(dd_rows), incremental, impact


def portfolio_daily_from_mode(daily_matrix: pd.DataFrame, accepted: pd.DataFrame, signal_keys: list[str], set_name: str, mode: str) -> pd.DataFrame:
    if mode == "raw_sum_diagnostic":
        cols = [c for c in signal_keys if c in daily_matrix.columns]
        daily = daily_matrix[["trading_session", *cols]].copy() if cols else pd.DataFrame(columns=["trading_session"])
        daily["net_pnl"] = daily[cols].sum(axis=1) if cols else 0.0
    else:
        daily = accepted.groupby("trading_session", as_index=False)["net_pnl"].sum() if not accepted.empty else pd.DataFrame(columns=["trading_session", "net_pnl"])
    daily["portfolio_set"] = set_name
    daily["portfolio_mode"] = mode
    return daily[["portfolio_set", "portfolio_mode", "trading_session", "net_pnl"]].sort_values("trading_session").reset_index(drop=True)


def simple_metrics(trades: pd.DataFrame, daily: pd.DataFrame, keys: list[str], skipped_overlap: int, skipped_session: int, correlation: pd.DataFrame) -> dict[str, Any]:
    return portfolio_metrics_b("baseline", "baseline", keys, trades, daily, skipped_overlap, skipped_session, correlation, {})


def portfolio_metrics_b(set_name: str, mode: str, signal_keys: list[str], trades: pd.DataFrame, daily: pd.DataFrame, skipped_overlap: int, skipped_session: int, correlation: pd.DataFrame, baseline: dict[str, Any]) -> dict[str, Any]:
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
    phase13 = trades[trades["phase"].eq("phase13a")] if not trades.empty and "phase" in trades else pd.DataFrame()
    inc_days = incremental_active_days(trades[~trades["phase"].eq("phase13a")] if not trades.empty and "phase" in trades else pd.DataFrame(), phase13)
    conc_delta = delta(day_conc["best"], baseline.get("best_day_concentration"))
    fold_delta = delta(pos_folds, baseline.get("positive_wf_test_folds_pct"))
    drawdown = max_drawdown(daily["net_pnl"] if not daily.empty else pd.Series(dtype=float))
    dd_delta = delta(drawdown, baseline.get("max_drawdown"))
    passes = official_gates_pass(net, validation, holdout, wf_stress, pos_folds, day_conc["best"], trade_conc["best"], active_days, baseline)
    label, status = portfolio_label_status(net, validation, holdout, wf_stress, pos_folds, day_conc["best"], trade_conc["best"], active_days, baseline, passes, conc_delta, fold_delta)
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
        "phase13a_net_contribution": round(float(phase13["net_pnl"].sum()), 2) if not phase13.empty else 0.0,
        "phase13a_trade_count": int(len(phase13)),
        "phase13a_active_days": int(phase13["trading_session"].nunique()) if not phase13.empty else 0,
        "incremental_active_days_from_phase13a": int(inc_days),
        "concentration_delta_vs_audit_a_best": conc_delta,
        "fold_delta_vs_audit_a_best": fold_delta,
        "drawdown_delta_vs_audit_a_best": dd_delta,
        "official_gates_passed": bool(passes),
        "portfolio_label": label,
        "research_status": status,
        "paper_trading_approved": False,
    }


def incremental_contribution_row(set_name: str, mode: str, signal_keys: list[str], accepted: pd.DataFrame, daily: pd.DataFrame, daily_matrix: pd.DataFrame, baseline: dict[str, Any], skipped_overlap: int, skipped_session: int) -> dict[str, Any]:
    phase13 = accepted[accepted["phase"].eq("phase13a")] if not accepted.empty and "phase" in accepted else pd.DataFrame()
    non13 = accepted[~accepted["phase"].eq("phase13a")] if not accepted.empty and "phase" in accepted else pd.DataFrame()
    base_cols = [k for k in signal_keys if not k.startswith("phase13a::") and k in daily_matrix.columns]
    base_daily = daily_matrix[["trading_session", *base_cols]].copy() if base_cols else pd.DataFrame(columns=["trading_session"])
    base_daily["existing_net_pnl"] = base_daily[base_cols].sum(axis=1) if base_cols else 0.0
    p13_daily = phase13.groupby("trading_session", as_index=False)["net_pnl"].sum() if not phase13.empty else pd.DataFrame(columns=["trading_session", "net_pnl"])
    joined = p13_daily.merge(base_daily[["trading_session", "existing_net_pnl"]], on="trading_session", how="left").fillna({"existing_net_pnl": 0.0})
    return {
        "portfolio_set": set_name,
        "portfolio_mode": mode,
        "phase13a_net_contribution": round(float(phase13["net_pnl"].sum()), 2) if not phase13.empty else 0.0,
        "phase13a_trade_count": int(len(phase13)),
        "phase13a_active_days": int(phase13["trading_session"].nunique()) if not phase13.empty else 0,
        "incremental_active_days_from_phase13a": incremental_active_days(non13, phase13),
        "phase13a_days_existing_no_trade": int((joined["existing_net_pnl"] == 0).sum()) if not joined.empty else 0,
        "phase13a_days_existing_negative_pnl": int((joined["existing_net_pnl"] < 0).sum()) if not joined.empty else 0,
        "phase13a_overlap_skipped": int(skipped_overlap if mode == "one_trade_at_a_time_chronological" else 0),
        "phase13a_session_skipped": int(skipped_session if mode == "max_one_trade_per_session" else 0),
    }


def phase13a_impact(results: pd.DataFrame, incremental: pd.DataFrame) -> pd.DataFrame:
    rows = []
    base = results[results["portfolio_set"].eq("audit_a_best_reconstructed")].set_index("portfolio_mode")
    plus = results[results["portfolio_set"].eq("audit_a_best_plus_phase13a")].set_index("portfolio_mode")
    for mode in MODES:
        if mode not in base.index or mode not in plus.index:
            continue
        b = base.loc[mode]
        p = plus.loc[mode]
        rows.append({
            "portfolio_mode": mode,
            "active_days_delta": int(p["active_days"] - b["active_days"]),
            "fold_delta": delta(p["positive_wf_test_folds_pct"], b["positive_wf_test_folds_pct"]),
            "best_day_concentration_delta": delta(p["best_day_concentration"], b["best_day_concentration"]),
            "best_trade_concentration_delta": delta(p["best_trade_concentration"], b["best_trade_concentration"]),
            "drawdown_delta": delta(p["max_drawdown"], b["max_drawdown"]),
            "correlation_delta": delta(p["average_pairwise_daily_correlation"], b["average_pairwise_daily_correlation"]),
            "phase13a_net_contribution": p["phase13a_net_contribution"],
            "phase13a_trade_count": p["phase13a_trade_count"],
            "phase13a_active_days": p["phase13a_active_days"],
            "keep_role_assessment": role_assessment(p),
        })
    return pd.DataFrame(rows)


def role_assessment(row: pd.Series) -> str:
    if row.get("phase13a_trade_count", 0) <= 0:
        return "parked_module"
    if row.get("active_days", 0) < OFFICIAL_GATES["min_active_days"]:
        return "rare_setup_module"
    if row.get("best_day_concentration", 1.0) <= 0.30 or row.get("average_pairwise_daily_correlation", 1.0) <= 0.25:
        return "diversifier_module"
    return "candidate_for_more_data"


def make_portfolio_b_recommendation(results: pd.DataFrame, impact: pd.DataFrame) -> dict[str, Any]:
    if results.empty:
        return {"next_action": "improve_standard_trade_log_schema_before_more_portfolio_work", "rationale": "Portfolio Audit B metrics were not computable from existing outputs.", "official_gates_changed": False, "paper_trading_approved": False}
    if bool(results["official_gates_passed"].astype(bool).any()):
        return {"next_action": "portfolio_review_packet_only", "rationale": "At least one diagnostic portfolio passed existing gates; paper trading remains unapproved.", "official_gates_changed": False, "paper_trading_approved": False}
    if not impact.empty:
        active = bool((impact["active_days_delta"] > 0).any())
        corr = bool((impact["correlation_delta"] < 0).any())
        conc = bool((impact["best_day_concentration_delta"] < 0).any() and (impact["best_trade_concentration_delta"] < 0).any())
        folds = bool((impact["fold_delta"] > 0).any())
        if conc and folds:
            return {"next_action": "portfolio_audit_c_review_packet_only", "rationale": "Phase 13A materially improved concentration and fold stability but the portfolio still misses at least one gate.", "official_gates_changed": False, "paper_trading_approved": False}
        if active or corr:
            return {"next_action": "keep_phase13a_as_diversifier_and_search_more_uncorrelated_modules", "rationale": "Phase 13A improves activity or correlation, but fold/concentration gates remain insufficient.", "official_gates_changed": False, "paper_trading_approved": False}
    return {"next_action": "park_phase13a_prior_rth_breakout_no_retest", "rationale": "Phase 13A did not improve playbook activity, correlation, fold stability, or concentration enough to justify active diversifier status.", "official_gates_changed": False, "paper_trading_approved": False}


def render_portfolio_audit_b_report(result: dict[str, pd.DataFrame | dict[str, Any]], report_path: Path) -> str:
    results = result["portfolio_results"]
    impact = result["phase13a_diversifier_impact"]
    rec = result["next_action_recommendation"]
    lines = [
        "# Portfolio Audit B — Playbook With Phase 13A Diversifier Modules",
        "",
        RESEARCH_ONLY_GUARDRAIL,
        "",
        "## Scope",
        "",
        "Diagnostic portfolio audit only. It uses existing registry and phase outputs, does not generate signals, does not change official gates, does not promote candidates, and does not approve paper trading.",
        "",
        "## Summary",
        "",
        f"- Selected modules: `{len(result['signal_selection'])}`",
        f"- Portfolio rows: `{len(results)}`",
        f"- Next action: `{rec.get('next_action')}`",
        f"- Rationale: {rec.get('rationale')}",
        "- Paper trading approved: `false`",
        "",
        "## Phase 13A Impact Versus Audit A Best",
        "",
        "| Mode | Active days Δ | Fold Δ | Best-day conc Δ | Best-trade conc Δ | Drawdown Δ | Correlation Δ | Role assessment |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    if isinstance(impact, pd.DataFrame) and not impact.empty:
        for _, r in impact.iterrows():
            lines.append(f"| {r['portfolio_mode']} | {int(r['active_days_delta'])} | {float(r['fold_delta']):.3f} | {float(r['best_day_concentration_delta']):.3f} | {float(r['best_trade_concentration_delta']):.3f} | {float(r['drawdown_delta']):.2f} | {float(r['correlation_delta']):.3f} | {r['keep_role_assessment']} |")
    lines += ["", "## Portfolio Results", "", "| Set | Mode | Net | Active days | Best-day conc | Best-trade conc | Positive folds | Label | Status |", "| --- | --- | ---: | ---: | ---: | ---: | ---: | --- | --- |"]
    if isinstance(results, pd.DataFrame) and not results.empty:
        for _, r in results.sort_values(["portfolio_label", "net_pnl"], ascending=[True, False]).iterrows():
            lines.append(f"| {r['portfolio_set']} | {r['portfolio_mode']} | {float(r['net_pnl']):.2f} | {int(r['active_days'])} | {float(r['best_day_concentration']):.3f} | {float(r['best_trade_concentration']):.3f} | {float(r['positive_wf_test_folds_pct'] or 0):.3f} | {r['portfolio_label']} | {r['research_status']} |")
    lines += ["", "## Interpretation", "", "Phase 13A remains research-only. Portfolio Audit B reports diagnostic gate status only; no portfolio is paper-trading approved.", ""]
    return "\n".join(lines)


def write_portfolio_audit_b_outputs(result: dict[str, pd.DataFrame | dict[str, Any]], output_dir: Path, report_path: Path) -> dict[str, Path]:
    ensure_directory(output_dir)
    ensure_directory(report_path.parent)
    mapping = {
        "signal_selection": output_dir / "portfolio_audit_b_signal_selection.csv",
        "signal_correlation": output_dir / "portfolio_audit_b_signal_correlation.csv",
        "daily_pnl_matrix": output_dir / "portfolio_audit_b_daily_pnl_matrix.csv",
        "trade_overlap_summary": output_dir / "portfolio_audit_b_trade_overlap_summary.csv",
        "portfolio_results": output_dir / "portfolio_audit_b_portfolio_results.csv",
        "portfolio_daily_pnl": output_dir / "portfolio_audit_b_portfolio_daily_pnl.csv",
        "portfolio_walk_forward_folds": output_dir / "portfolio_audit_b_portfolio_walk_forward_folds.csv",
        "portfolio_concentration": output_dir / "portfolio_audit_b_portfolio_concentration.csv",
        "portfolio_drawdown_summary": output_dir / "portfolio_audit_b_portfolio_drawdown_summary.csv",
        "incremental_contribution": output_dir / "portfolio_audit_b_incremental_contribution.csv",
        "phase13a_diversifier_impact": output_dir / "portfolio_audit_b_phase13a_diversifier_impact.csv",
    }
    paths: dict[str, Path] = {}
    for key, path in mapping.items():
        write_csv_artifact(result[key], path)  # type: ignore[arg-type]
        paths[key] = path
    rec = output_dir / "portfolio_audit_b_next_action_recommendation.json"
    write_json_artifact(result["next_action_recommendation"], rec)  # type: ignore[arg-type]
    report_path.write_text(render_portfolio_audit_b_report(result, report_path), encoding="utf-8")
    paths["recommendation"] = rec
    paths["report"] = report_path
    return paths


def portfolio_folds(set_name: str, mode: str, daily: pd.DataFrame, folds: int = 6) -> pd.DataFrame:
    if daily.empty:
        return pd.DataFrame(columns=["portfolio_set", "portfolio_mode", "fold", "net_pnl", "stress_pnl", "active_days"])
    ordered = daily.sort_values("trading_session").reset_index(drop=True)
    rows = []
    size = max(1, len(ordered) // folds)
    for idx in range(folds):
        start = idx * size
        end = len(ordered) if idx == folds - 1 else min(len(ordered), (idx + 1) * size)
        seg = ordered.iloc[start:end]
        if seg.empty:
            continue
        net = round(float(seg["net_pnl"].sum()), 2)
        rows.append({"portfolio_set": set_name, "portfolio_mode": mode, "fold": idx + 1, "net_pnl": net, "stress_pnl": round(net - len(seg), 2), "active_days": int(seg["trading_session"].nunique())})
    return pd.DataFrame(rows)


def concentration(values: pd.Series) -> dict[str, float]:
    vals = pd.Series(values, dtype=float).sort_values(ascending=False)
    total = float(vals.sum())
    if total <= 0 or vals.empty:
        return {"best": 1.0, "top3": 1.0, "top5": 1.0}
    pos = vals.clip(lower=0)
    return {"best": round(safe_divide(float(pos.head(1).sum()), total), 6), "top3": round(safe_divide(float(pos.head(3).sum()), total), 6), "top5": round(safe_divide(float(pos.head(5).sum()), total), 6)}


def max_drawdown(values: pd.Series) -> float:
    equity = pd.Series(values, dtype=float).cumsum()
    if equity.empty:
        return 0.0
    return round(float((equity - equity.cummax()).min()), 2)


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


def portfolio_label_status(net: float, validation: float | None, holdout: float | None, wf_stress: float | None, pos_folds: float | None, best_day: float, best_trade: float, active_days: int, baseline: dict[str, Any], passes: bool, conc_delta: float | None, fold_delta: float | None) -> tuple[str, str]:
    if net <= 0:
        return "portfolio_b_failed_negative", "no_portfolio_benefit"
    if passes:
        return "portfolio_b_candidate_for_review_packet_only", "portfolio_candidate_for_future_review_packet"
    if best_day > OFFICIAL_GATES["best_day_concentration"] or best_trade > OFFICIAL_GATES["best_trade_concentration"]:
        status = "phase13a_reduces_concentration" if conc_delta is not None and conc_delta < 0 else "portfolio_still_nontradable"
        return "portfolio_b_positive_but_concentrated", status
    if pos_folds is not None and pos_folds < OFFICIAL_GATES["positive_wf_test_folds_pct"]:
        status = "phase13a_improves_folds" if fold_delta is not None and fold_delta > 0 else "portfolio_still_nontradable"
        return "portfolio_b_positive_but_fold_unstable", status
    if active_days < OFFICIAL_GATES["min_active_days"]:
        return "portfolio_b_positive_but_low_activity", "phase13a_improves_activity"
    return "portfolio_b_no_incremental_improvement", "portfolio_still_nontradable"


def incremental_active_days(existing: pd.DataFrame, phase13: pd.DataFrame) -> int:
    if phase13.empty:
        return 0
    existing_days = set(existing["trading_session"].astype(str)) if not existing.empty and "trading_session" in existing else set()
    phase13_days = set(phase13["trading_session"].astype(str))
    return len(phase13_days - existing_days)


def pairwise_corr_for(signal_keys: list[str], correlation: pd.DataFrame) -> pd.Series:
    vals = []
    for a, b in combinations(signal_keys, 2):
        row = correlation[correlation["signal_a"].eq(a) & correlation["signal_b"].eq(b)]
        if not row.empty:
            vals.append(float(row.iloc[0]["daily_pnl_correlation"]))
    return pd.Series(vals, dtype=float)


def avg_abs_corr(sig: str, chosen: list[str], correlation: pd.DataFrame) -> float:
    vals = []
    for other in chosen:
        row = correlation[correlation["signal_a"].eq(sig) & correlation["signal_b"].eq(other)]
        vals.append(abs(float(row.iloc[0]["daily_pnl_correlation"]))) if not row.empty else vals.append(1.0)
    return sum(vals) / len(vals) if vals else 0.0


def overlap_count(trades: pd.DataFrame) -> int:
    count = 0
    rows = list(trades.itertuples())
    for i, a in enumerate(rows):
        for b in rows[i + 1 :]:
            if a.entry_time < b.exit_time and b.entry_time < a.exit_time:
                count += 1
    return count


def delta(value: Any, baseline: Any) -> float | None:
    if baseline is None or value is None or pd.isna(baseline) or pd.isna(value):
        return None
    return round(float(value) - float(baseline), 6)


def append_module(rows: list[pd.Series], seen: set[tuple[str, str]], row: pd.Series, reason: str) -> None:
    key = (str(row["phase"]), str(row["candidate_id"]))
    if key in seen:
        return
    item = row.copy()
    item["selection_reason"] = reason
    rows.append(item)
    seen.add(key)


def signal_key(phase: str, candidate_id: str) -> str:
    return f"{phase}::{candidate_id}"


def split_signal_key(key: str) -> tuple[str, str]:
    phase, cid = key.split("::", 1)
    return phase, cid


def unique(values: list[str | None]) -> list[str]:
    out = []
    seen = set()
    for value in values:
        if value and value not in seen:
            out.append(value)
            seen.add(value)
    return out


def concat(parts: list[pd.DataFrame]) -> pd.DataFrame:
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()


def _read_json(path: Path) -> dict[str, Any]:
    import json

    return json.loads(path.read_text(encoding="utf-8"))
