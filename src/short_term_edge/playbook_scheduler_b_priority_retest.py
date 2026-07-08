from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from .phase_common import ensure_directory, safe_divide, write_csv_artifact, write_json_artifact
from .portfolio_audit_b import RESEARCH_ONLY_GUARDRAIL, concentration, max_drawdown, signal_key, split_signal_key
from .portfolio_audit_c import portfolio_folds
from .portfolio_audit_d import PHASES, PHASE_PRIORITY as PORTFOLIO_D_PRIORITY

MODES = ("one_trade_at_a_time_chronological", "max_one_trade_per_session")
PRIORITY_POLICIES = (
    "existing_priority_baseline",
    "lowest_correlation_first",
    "highest_recent_validation_first",
    "hybrid_validation_then_correlation",
    "diversifier_first",
    "core_then_diversifier",
    "rare_setup_first",
    "concentration_adjusted_priority",
)
DIAGNOSTIC_FILTERS = ("no_filter_baseline", "exclude_overlap_heavy_days")
MAX_SELECTED_MODULES = 28
OFFICIAL_GATES_UNCHANGED = True
PAPER_TRADING_APPROVED = False
DIAGNOSTIC_ONLY_NO_SIGNALS_GENERATED = True
LIVE_TRADING_APPROVED = False
CANDIDATE_FOLD_GATE = 0.90
CANDIDATE_DAY_CONC_GATE = 0.15
CANDIDATE_TRADE_CONC_GATE = 0.08


def load_playbook_scheduler_b_inputs(output_dir: Path) -> dict[str, Any]:
    required: dict[str, Path] = {
        "playbook_module_registry": output_dir / "playbook_module_registry.csv",
        "research_signal_registry": output_dir / "research_signal_registry.csv",
        "scheduler_a_priority_results": output_dir / "playbook_scheduler_audit_a_priority_results.csv",
        "scheduler_a_regime_filter_results": output_dir / "playbook_scheduler_audit_a_regime_filter_results.csv",
        "scheduler_a_overlap_diagnostics": output_dir / "playbook_scheduler_audit_a_overlap_diagnostics.csv",
        "scheduler_a_daily_pnl": output_dir / "playbook_scheduler_audit_a_daily_pnl.csv",
        "scheduler_a_walk_forward_folds": output_dir / "playbook_scheduler_audit_a_walk_forward_folds.csv",
        "scheduler_a_concentration": output_dir / "playbook_scheduler_audit_a_concentration.csv",
        "scheduler_a_recommendation": output_dir / "playbook_scheduler_audit_a_next_action_recommendation.json",
        "portfolio_d_signal_selection": output_dir / "portfolio_audit_d_signal_selection.csv",
        "portfolio_d_signal_correlation": output_dir / "portfolio_audit_d_signal_correlation.csv",
        "portfolio_d_daily_matrix": output_dir / "portfolio_audit_d_daily_pnl_matrix.csv",
        "portfolio_d_results": output_dir / "portfolio_audit_d_portfolio_results.csv",
        "portfolio_d_daily": output_dir / "portfolio_audit_d_portfolio_daily_pnl.csv",
        "portfolio_d_folds": output_dir / "portfolio_audit_d_portfolio_walk_forward_folds.csv",
        "portfolio_d_overlap": output_dir / "portfolio_audit_d_trade_overlap_summary.csv",
        "portfolio_d_recommendation": output_dir / "portfolio_audit_d_next_action_recommendation.json",
    }
    for phase in PHASES:
        required[f"{phase}_trades"] = output_dir / f"{phase}_trade_logs.csv"
    missing = [str(path) for path in required.values() if not path.exists()]
    if missing:
        raise FileNotFoundError(f"Missing Playbook Scheduler B input(s): {missing}")
    return {key: _read_json(path) if path.suffix == ".json" else pd.read_csv(path) for key, path in required.items()}


def run_playbook_scheduler_b_priority_retest(output_dir: Path) -> dict[str, Any]:
    data = load_playbook_scheduler_b_inputs(output_dir)
    selected = select_scheduler_b_modules(data)
    selected_keys = selected["signal_key"].astype(str).tolist()
    trades = selected_trade_logs(data, selected_keys)
    daily_matrix = module_daily_matrix_from_trades(trades, selected_keys)
    avg_corr = average_abs_correlation(selected_keys, data["portfolio_d_signal_correlation"], daily_matrix)
    priority_orders = build_priority_policy_orders(selected, selected_keys, avg_corr)
    overlap_sessions = overlap_heavy_sessions(trades)
    baseline_by_mode = baseline_by_mode_from_portfolio_d(data["portfolio_d_results"])
    scheduler_a_baseline_by_mode = baseline_by_mode_from_scheduler_a(data["scheduler_a_priority_results"])

    policy_rows: list[dict[str, Any]] = []
    daily_rows: list[pd.DataFrame] = []
    fold_rows: list[pd.DataFrame] = []
    concentration_rows: list[dict[str, Any]] = []
    overlap_rows: list[dict[str, Any]] = []
    acceptance_rows: list[dict[str, Any]] = []

    for policy in PRIORITY_POLICIES:
        order_map = priority_orders[policy]
        for mode in MODES:
            for filter_name in DIAGNOSTIC_FILTERS:
                excluded_sessions = overlap_sessions if filter_name == "exclude_overlap_heavy_days" else set()
                accepted, skipped_overlap, skipped_session, rejected, excluded_count = construct_scheduled_trades(
                    trades, selected_keys, order_map, mode, excluded_sessions
                )
                daily = scheduled_daily_pnl(accepted, policy, mode, filter_name)
                folds = scheduler_folds(policy, mode, filter_name, daily)
                metrics = scheduler_policy_metrics(
                    policy=policy,
                    mode=mode,
                    filter_name=filter_name,
                    selected_keys=selected_keys,
                    accepted=accepted,
                    rejected=rejected,
                    daily=daily,
                    folds=folds,
                    skipped_overlap=skipped_overlap,
                    skipped_session=skipped_session,
                    excluded_count=excluded_count,
                    portfolio_d_baseline=baseline_by_mode.get(mode, {}),
                    scheduler_a_baseline=scheduler_a_baseline_by_mode.get(mode, {}),
                )
                policy_rows.append(metrics)
                daily_rows.append(daily)
                fold_rows.append(folds)
                concentration_rows.append({k: metrics[k] for k in ("priority_policy", "portfolio_mode", "diagnostic_filter", "best_day_concentration", "best_trade_concentration", "top_3_day_concentration", "top_5_trade_concentration")})
                overlap_rows.append(overlap_summary_row(policy, mode, filter_name, accepted, rejected, skipped_overlap, skipped_session, excluded_count))
                acceptance_rows.extend(module_acceptance_rows(policy, mode, filter_name, selected, accepted, rejected))

    policy_results = pd.DataFrame(policy_rows).sort_values(["priority_policy", "portfolio_mode", "diagnostic_filter"]).reset_index(drop=True)
    daily_pnl = _concat(daily_rows)
    folds = _concat(fold_rows)
    concentration_df = pd.DataFrame(concentration_rows).sort_values(["priority_policy", "portfolio_mode", "diagnostic_filter"]).reset_index(drop=True)
    overlap_df = pd.DataFrame(overlap_rows).sort_values(["priority_policy", "portfolio_mode", "diagnostic_filter"]).reset_index(drop=True)
    acceptance_df = pd.DataFrame(acceptance_rows).sort_values(["priority_policy", "portfolio_mode", "diagnostic_filter", "priority_rank", "signal_key"]).reset_index(drop=True)
    comparison = build_policy_comparison(policy_results)
    recommendation = make_next_action_recommendation(policy_results, acceptance_df)
    return {
        "module_selection": selected,
        "priority_policy_results": policy_results,
        "daily_pnl": daily_pnl,
        "walk_forward_folds": folds,
        "concentration": concentration_df,
        "overlap_summary": overlap_df,
        "policy_comparison": comparison,
        "module_acceptance_summary": acceptance_df,
        "next_action_recommendation": recommendation,
        "priority_policy_orders": priority_orders,
        "selected_signal_keys": selected_keys,
        "inputs_loaded": loaded_input_names(),
    }


def select_scheduler_b_modules(data: dict[str, Any], cap: int = MAX_SELECTED_MODULES) -> pd.DataFrame:
    modules = data["playbook_module_registry"].copy()
    dsel = data["portfolio_d_signal_selection"].copy()
    for df in (modules, dsel):
        if not df.empty:
            df["phase"] = df["phase"].astype(str)
            df["candidate_id"] = df["candidate_id"].astype(str)
            if "signal_key" not in df:
                df["signal_key"] = df.apply(lambda r: signal_key(r["phase"], r["candidate_id"]), axis=1)
            for col in ("net_pnl", "stress_pnl", "validation_pnl", "holdout_pnl", "walk_forward_stress_pnl", "best_day_concentration", "best_trade_concentration"):
                df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0) if col in df else 0.0
            df["prior_score"] = pd.to_numeric(df.get("prior_score", df[[c for c in ("net_pnl", "stress_pnl", "validation_pnl", "holdout_pnl", "walk_forward_stress_pnl") if c in df]].sum(axis=1)), errors="coerce").fillna(0.0)
    rows: list[pd.Series] = []
    seen: set[str] = set()

    def append_from(frame: pd.DataFrame, reason: str) -> None:
        if frame.empty or len(rows) >= cap:
            return
        row = frame.iloc[0].copy()
        key = str(row["signal_key"])
        if key in seen:
            return
        row["selection_reason_b"] = reason
        rows.append(row)
        seen.add(key)

    for phase in ("phase10b", "phase11a"):
        seg = modules[(modules["phase"].eq(phase)) & (modules["research_track"].astype(str).eq("parked_research_signal"))].sort_values(["prior_score", "net_pnl", "candidate_id"], ascending=[False, False, True])
        append_from(seg, f"required_top_{phase}_parked_module")
    phase12_d = dsel[dsel["phase"].eq("phase12a")].sort_values(["selection_rank", "prior_score", "candidate_id"], ascending=[True, False, True]) if "selection_rank" in dsel else dsel[dsel["phase"].eq("phase12a")].sort_values(["prior_score", "candidate_id"], ascending=[False, True])
    append_from(phase12_d if not phase12_d.empty else modules[modules["phase"].eq("phase12a")].sort_values(["prior_score", "candidate_id"], ascending=[False, True]), "required_phase12a_portfolio_d_fallback")
    for phase in ("phase13a", "phase14a", "phase15a"):
        seg = modules[(modules["phase"].eq(phase)) & (modules["portfolio_role"].astype(str).eq("diversifier_module"))].sort_values(["prior_score", "net_pnl", "candidate_id"], ascending=[False, False, True])
        for _, r in seg.iterrows():
            append_from(pd.DataFrame([r]), f"required_{phase}_diversifier_module")
    d_order = dsel.sort_values(["selection_rank", "prior_score", "candidate_id"], ascending=[True, False, True]) if "selection_rank" in dsel else dsel.sort_values(["prior_score", "candidate_id"], ascending=[False, True])
    for _, row in d_order.iterrows():
        append_from(pd.DataFrame([row]), "portfolio_audit_d_selected_module")
    fill = modules[modules["research_track"].astype(str).isin(["parked_research_signal", "rare_setup_research_signal"])].sort_values(["prior_score", "net_pnl", "candidate_id"], ascending=[False, False, True])
    for _, row in fill.iterrows():
        append_from(pd.DataFrame([row]), "cap_fill_existing_registry_module")
    selected = pd.DataFrame([r.to_dict() for r in rows[:cap]])
    if selected.empty:
        return selected
    selected.insert(0, "selection_rank_b", range(1, len(selected) + 1))
    return selected.reset_index(drop=True)


def selected_trade_logs(data: dict[str, Any], selected_keys: list[str]) -> pd.DataFrame:
    selected = set(selected_keys)
    rows = []
    for phase in PHASES:
        trades = data.get(f"{phase}_trades", pd.DataFrame()).copy()
        if trades.empty or "candidate_id" not in trades:
            continue
        trades["phase"] = phase
        trades["candidate_id"] = trades["candidate_id"].astype(str)
        trades["signal_key"] = trades["candidate_id"].map(lambda cid: signal_key(phase, cid))
        trades = trades[trades["signal_key"].isin(selected)].copy()
        if trades.empty:
            continue
        for col in ("entry_time", "exit_time"):
            trades[col] = pd.to_datetime(trades[col], errors="coerce", utc=True)
        for col in ("net_pnl", "stress_pnl", "gross_pnl"):
            trades[col] = pd.to_numeric(trades[col], errors="coerce").fillna(0.0) if col in trades else 0.0
        if "split" not in trades:
            trades["split"] = "not_available"
        rows.append(trades)
    out = _concat(rows)
    if out.empty:
        return pd.DataFrame(columns=["phase", "candidate_id", "signal_key", "entry_time", "exit_time", "trading_session", "net_pnl", "stress_pnl", "split"])
    return out.sort_values(["entry_time", "phase", "candidate_id", "exit_time"]).reset_index(drop=True)


def module_daily_matrix_from_trades(trades: pd.DataFrame, selected_keys: list[str]) -> pd.DataFrame:
    if trades.empty:
        return pd.DataFrame(columns=["trading_session", *selected_keys])
    daily = trades.groupby(["trading_session", "signal_key"], as_index=False)["net_pnl"].sum()
    matrix = daily.pivot(index="trading_session", columns="signal_key", values="net_pnl").fillna(0.0).reset_index()
    for key in selected_keys:
        if key not in matrix:
            matrix[key] = 0.0
    return matrix[["trading_session", *selected_keys]].sort_values("trading_session").reset_index(drop=True)


def average_abs_correlation(selected_keys: list[str], corr: pd.DataFrame, daily_matrix: pd.DataFrame) -> dict[str, float]:
    out = {key: 0.0 for key in selected_keys}
    if not corr.empty and {"signal_a", "signal_b", "daily_pnl_correlation"}.issubset(corr.columns):
        for key in selected_keys:
            seg = corr[((corr["signal_a"].astype(str).eq(key)) & (corr["signal_b"].astype(str).isin(selected_keys)) & (~corr["signal_b"].astype(str).eq(key))) | ((corr["signal_b"].astype(str).eq(key)) & (corr["signal_a"].astype(str).isin(selected_keys)) & (~corr["signal_a"].astype(str).eq(key)))]
            if not seg.empty:
                out[key] = round(float(pd.to_numeric(seg["daily_pnl_correlation"], errors="coerce").abs().mean()), 6)
        return out
    cols = [k for k in selected_keys if k in daily_matrix]
    if len(cols) > 1:
        c = daily_matrix[cols].corr().fillna(0.0).abs()
        out = {key: round(float(c.loc[key, [v for v in cols if v != key]].mean()), 6) for key in cols}
    return out


def build_priority_policy_orders(selected: pd.DataFrame, selected_keys: list[str], avg_corr: dict[str, float]) -> dict[str, dict[str, int]]:
    base = {key: i for i, key in enumerate(selected_keys)}
    meta = selected.set_index("signal_key") if not selected.empty else pd.DataFrame()
    def val(key: str, col: str, default: float = 0.0) -> float:
        try:
            return float(meta.loc[key].get(col, default)) if key in meta.index else default
        except Exception:
            return default
    def txt(key: str, col: str) -> str:
        try:
            return str(meta.loc[key].get(col, "")) if key in meta.index else ""
        except Exception:
            return ""
    phase_order_div = {"phase15a": 0, "phase14a": 1, "phase13a": 2, "phase10b": 3, "phase11a": 4, "phase12a": 5}
    phase_order_core = {"phase10b": 0, "phase11a": 1, "phase12a": 2, "phase13a": 3, "phase14a": 4, "phase15a": 5}
    orders = {
        "existing_priority_baseline": sorted(selected_keys, key=lambda k: (PORTFOLIO_D_PRIORITY.get(split_signal_key(k)[0], 99), base[k], k)),
        "lowest_correlation_first": sorted(selected_keys, key=lambda k: (avg_corr.get(k, 0.0), split_signal_key(k)[0], k)),
        "highest_recent_validation_first": sorted(selected_keys, key=lambda k: (-val(k, "validation_pnl"), avg_corr.get(k, 0.0), k)),
        "hybrid_validation_then_correlation": sorted(selected_keys, key=lambda k: (0 if val(k, "validation_pnl") > 0 and val(k, "holdout_pnl") > 0 else 1, avg_corr.get(k, 0.0), val(k, "best_day_concentration", 1.0), k)),
        "diversifier_first": sorted(selected_keys, key=lambda k: (phase_order_div.get(split_signal_key(k)[0], 99), k)),
        "core_then_diversifier": sorted(selected_keys, key=lambda k: (phase_order_core.get(split_signal_key(k)[0], 99), k)),
        "rare_setup_first": sorted(selected_keys, key=lambda k: (0 if txt(k, "research_track") == "rare_setup_research_signal" else 1, avg_corr.get(k, 0.0), k)),
        "concentration_adjusted_priority": sorted(selected_keys, key=lambda k: (val(k, "best_day_concentration", 1.0), val(k, "best_trade_concentration", 1.0), -val(k, "validation_pnl"), k)),
    }
    return {name: {key: i for i, key in enumerate(keys)} for name, keys in orders.items()}


def construct_scheduled_trades(trades: pd.DataFrame, signal_keys: list[str], order_map: dict[str, int], mode: str, excluded_sessions: set[str] | None = None) -> tuple[pd.DataFrame, int, int, pd.DataFrame, int]:
    excluded_sessions = excluded_sessions or set()
    seg = trades[trades["signal_key"].isin(signal_keys)].copy()
    excluded_count = int(seg[seg["trading_session"].astype(str).isin(excluded_sessions)].shape[0]) if excluded_sessions else 0
    if excluded_sessions:
        seg = seg[~seg["trading_session"].astype(str).isin(excluded_sessions)].copy()
    if seg.empty:
        return seg, 0, 0, pd.DataFrame(columns=list(trades.columns) + ["skip_reason"]), excluded_count
    seg["scheduler_priority"] = seg["signal_key"].map(order_map).fillna(9999).astype(int)
    seg = seg.sort_values(["entry_time", "scheduler_priority", "candidate_id", "exit_time"]).reset_index(drop=True)
    accepted = []
    rejected = []
    used_sessions: set[str] = set()
    last_exit = None
    skipped_overlap = 0
    skipped_session = 0
    for _, row in seg.iterrows():
        session = str(row["trading_session"])
        item = row.copy()
        if mode == "max_one_trade_per_session" and session in used_sessions:
            item["skip_reason"] = "session_already_used"
            rejected.append(item)
            skipped_session += 1
            continue
        if mode == "one_trade_at_a_time_chronological" and last_exit is not None and row["entry_time"] < last_exit:
            item["skip_reason"] = "overlapping_holding_period"
            rejected.append(item)
            skipped_overlap += 1
            continue
        accepted.append(row)
        used_sessions.add(session)
        if mode == "one_trade_at_a_time_chronological":
            last_exit = row["exit_time"] if last_exit is None else max(last_exit, row["exit_time"])
    return pd.DataFrame(accepted), skipped_overlap, skipped_session, pd.DataFrame(rejected), excluded_count


def scheduled_daily_pnl(accepted: pd.DataFrame, policy: str, mode: str, filter_name: str) -> pd.DataFrame:
    daily = accepted.groupby("trading_session", as_index=False)["net_pnl"].sum().sort_values("trading_session") if not accepted.empty else pd.DataFrame(columns=["trading_session", "net_pnl"])
    daily.insert(0, "diagnostic_filter", filter_name)
    daily.insert(0, "portfolio_mode", mode)
    daily.insert(0, "priority_policy", policy)
    return daily[["priority_policy", "portfolio_mode", "diagnostic_filter", "trading_session", "net_pnl"]]


def scheduler_folds(policy: str, mode: str, filter_name: str, daily: pd.DataFrame) -> pd.DataFrame:
    base = daily.rename(columns={"priority_policy": "portfolio_set"}).copy()
    base["portfolio_set"] = policy
    folds = portfolio_folds(policy, mode, base[["portfolio_set", "portfolio_mode", "trading_session", "net_pnl"]])
    if folds.empty:
        return pd.DataFrame(columns=["priority_policy", "portfolio_mode", "diagnostic_filter", "fold", "net_pnl", "stress_pnl", "active_days"])
    folds = folds.rename(columns={"portfolio_set": "priority_policy"})
    folds.insert(2, "diagnostic_filter", filter_name)
    return folds[["priority_policy", "portfolio_mode", "diagnostic_filter", "fold", "net_pnl", "stress_pnl", "active_days"]]


def scheduler_policy_metrics(policy: str, mode: str, filter_name: str, selected_keys: list[str], accepted: pd.DataFrame, rejected: pd.DataFrame, daily: pd.DataFrame, folds: pd.DataFrame, skipped_overlap: int, skipped_session: int, excluded_count: int, portfolio_d_baseline: dict[str, Any], scheduler_a_baseline: dict[str, Any]) -> dict[str, Any]:
    net = round(float(daily["net_pnl"].sum()), 2) if not daily.empty else 0.0
    split = accepted.groupby("split")["net_pnl"].sum().to_dict() if not accepted.empty and "split" in accepted else {}
    validation = round(float(split.get("validation", 0.0)), 2) if split else None
    holdout = round(float(split.get("holdout", 0.0)), 2) if split else None
    wf_test = round(float(folds["net_pnl"].sum()), 2) if not folds.empty else None
    wf_stress = round(float(folds["stress_pnl"].sum()), 2) if not folds.empty else None
    pos_folds = round(safe_divide(int((folds["stress_pnl"] > 0).sum()), len(folds)), 6) if not folds.empty else None
    worst_fold = round(float(folds["stress_pnl"].min()), 2) if not folds.empty else None
    weak_fold_count = int((folds["stress_pnl"] <= 0).sum()) if not folds.empty else 0
    weak_fold_pnl = round(float(folds.loc[folds["stress_pnl"] <= 0, "stress_pnl"].sum()), 2) if not folds.empty else 0.0
    day_conc = concentration(daily["net_pnl"] if not daily.empty else pd.Series(dtype=float))
    trade_conc = concentration(accepted["net_pnl"] if not accepted.empty else pd.Series(dtype=float))
    active_days = int(daily["trading_session"].nunique()) if not daily.empty else 0
    label, status = scheduler_label_status(net, validation, holdout, wf_stress, pos_folds, day_conc["best"], trade_conc["best"], portfolio_d_baseline, active_days)
    phase_counts = accepted.groupby("phase").size().sort_index().to_dict() if not accepted.empty else {}
    module_counts = accepted.groupby("signal_key").size().sort_index().to_dict() if not accepted.empty else {}
    return {
        "priority_policy": policy,
        "portfolio_mode": mode,
        "diagnostic_filter": filter_name,
        "diagnostic_filter_only": bool(filter_name != "no_filter_baseline"),
        "signals": len(selected_keys),
        "signal_keys": ";".join(selected_keys),
        "net_pnl": net,
        "validation_pnl": validation,
        "holdout_pnl": holdout,
        "walk_forward_test_pnl": wf_test,
        "walk_forward_stress_pnl": wf_stress,
        "positive_wf_test_folds_pct": pos_folds,
        "worst_wf_test_fold": worst_fold,
        "trades": int(len(accepted)),
        "active_days": active_days,
        "trades_per_active_day": round(safe_divide(len(accepted), active_days), 6),
        "max_drawdown": max_drawdown(daily["net_pnl"] if not daily.empty else pd.Series(dtype=float)),
        "best_day_concentration": day_conc["best"],
        "best_trade_concentration": trade_conc["best"],
        "top_3_day_concentration": day_conc["top3"],
        "top_5_trade_concentration": trade_conc["top5"],
        "skipped_overlap_count": int(skipped_overlap),
        "skipped_session_count": int(skipped_session),
        "excluded_overlap_heavy_trade_count": int(excluded_count),
        "accepted_trade_count_by_phase": json.dumps({str(k): int(v) for k, v in phase_counts.items()}, sort_keys=True),
        "accepted_trade_count_by_module": json.dumps({str(k): int(v) for k, v in module_counts.items()}, sort_keys=True),
        "weak_fold_count": weak_fold_count,
        "weak_fold_pnl": weak_fold_pnl,
        "improvement_vs_portfolio_audit_d_best": _delta(net, portfolio_d_baseline.get("net_pnl")),
        "improvement_vs_scheduler_a_baseline": _delta(net, scheduler_a_baseline.get("net_pnl")),
        "scheduler_b_label": label,
        "scheduler_b_status": status,
        "official_gates_changed": False,
        "paper_trading_approved": False,
        "diagnostic_only_no_signals_generated": True,
        "live_trading_approved": False,
    }


def scheduler_label_status(net: float, validation: float | None, holdout: float | None, wf_stress: float | None, pos_folds: float | None, best_day: float, best_trade: float, baseline: dict[str, Any], active_days: int) -> tuple[str, str]:
    candidate = net > 0 and (validation is None or validation > 0) and (holdout is None or holdout > 0) and (wf_stress is None or wf_stress > 0) and (pos_folds is None or pos_folds >= CANDIDATE_FOLD_GATE) and best_day <= CANDIDATE_DAY_CONC_GATE and best_trade <= CANDIDATE_TRADE_CONC_GATE
    if candidate:
        return "scheduler_b_candidate_for_review_packet_only", "scheduler_candidate_for_future_review_packet"
    if net <= 0:
        return "scheduler_b_failed_negative", "no_scheduler_benefit"
    base_fold = _float_or_none(baseline.get("positive_wf_test_folds_pct"))
    base_day = _float_or_none(baseline.get("best_day_concentration"))
    base_dd = _float_or_none(baseline.get("max_drawdown"))
    if best_day > CANDIDATE_DAY_CONC_GATE or best_trade > CANDIDATE_TRADE_CONC_GATE:
        if base_day is not None and best_day < base_day:
            return "scheduler_b_positive_but_concentrated", "priority_reduces_concentration"
        return "scheduler_b_positive_but_concentrated", "scheduler_still_nontradable"
    if pos_folds is not None and pos_folds < CANDIDATE_FOLD_GATE:
        if base_fold is not None and pos_folds > base_fold:
            return "scheduler_b_positive_but_fold_unstable", "priority_improves_folds"
        return "scheduler_b_positive_but_fold_unstable", "scheduler_still_nontradable"
    dd = _float_or_none(baseline.get("max_drawdown"))
    if base_dd is not None and dd is not None and dd > base_dd:
        return "scheduler_b_improves_priority_needs_review", "priority_improves_drawdown"
    if active_days > int(float(baseline.get("active_days", 0) or 0)):
        return "scheduler_b_improves_priority_needs_review", "priority_improves_activity"
    return "scheduler_b_no_improvement", "no_scheduler_benefit"


def overlap_heavy_sessions(trades: pd.DataFrame) -> set[str]:
    if trades.empty:
        return set()
    counts = trades.groupby("trading_session")["signal_key"].nunique()
    return set(counts[counts > 1].index.astype(str))


def overlap_summary_row(policy: str, mode: str, filter_name: str, accepted: pd.DataFrame, rejected: pd.DataFrame, skipped_overlap: int, skipped_session: int, excluded_count: int) -> dict[str, Any]:
    rejected_positive = int((rejected["net_pnl"] > 0).sum()) if not rejected.empty and "net_pnl" in rejected else 0
    rejected_negative = int((rejected["net_pnl"] < 0).sum()) if not rejected.empty and "net_pnl" in rejected else 0
    return {
        "priority_policy": policy,
        "portfolio_mode": mode,
        "diagnostic_filter": filter_name,
        "diagnostic_filter_only": bool(filter_name != "no_filter_baseline"),
        "accepted_trades": int(len(accepted)),
        "skipped_overlap_count": int(skipped_overlap),
        "skipped_session_count": int(skipped_session),
        "excluded_overlap_heavy_trade_count": int(excluded_count),
        "rejected_positive_trade_count": rejected_positive,
        "rejected_positive_pnl": round(float(rejected.loc[rejected["net_pnl"] > 0, "net_pnl"].sum()), 2) if not rejected.empty and "net_pnl" in rejected else 0.0,
        "rejected_negative_trade_count": rejected_negative,
        "rejected_negative_pnl": round(float(rejected.loc[rejected["net_pnl"] < 0, "net_pnl"].sum()), 2) if not rejected.empty and "net_pnl" in rejected else 0.0,
    }


def module_acceptance_rows(policy: str, mode: str, filter_name: str, selected: pd.DataFrame, accepted: pd.DataFrame, rejected: pd.DataFrame) -> list[dict[str, Any]]:
    rows = []
    acc_counts = accepted.groupby("signal_key").size().to_dict() if not accepted.empty else {}
    acc_pnl = accepted.groupby("signal_key")["net_pnl"].sum().to_dict() if not accepted.empty else {}
    rej_counts = rejected.groupby("signal_key").size().to_dict() if not rejected.empty and "signal_key" in rejected else {}
    rej_pnl = rejected.groupby("signal_key")["net_pnl"].sum().to_dict() if not rejected.empty and "signal_key" in rejected else {}
    for _, row in selected.iterrows():
        key = str(row["signal_key"])
        rows.append({
            "priority_policy": policy,
            "portfolio_mode": mode,
            "diagnostic_filter": filter_name,
            "diagnostic_filter_only": bool(filter_name != "no_filter_baseline"),
            "priority_rank": int(row.get("selection_rank_b", 0)),
            "phase": str(row.get("phase", "")),
            "candidate_id": str(row.get("candidate_id", "")),
            "signal_key": key,
            "selection_reason_b": str(row.get("selection_reason_b", "")),
            "accepted_trade_count": int(acc_counts.get(key, 0)),
            "accepted_net_pnl": round(float(acc_pnl.get(key, 0.0)), 2),
            "skipped_trade_count": int(rej_counts.get(key, 0)),
            "skipped_net_pnl": round(float(rej_pnl.get(key, 0.0)), 2),
            "acceptance_status": "accepted_some" if int(acc_counts.get(key, 0)) > 0 else "skipped_all_or_no_trades",
        })
    return rows


def build_policy_comparison(results: pd.DataFrame) -> pd.DataFrame:
    rows = []
    no_filter = results[results["diagnostic_filter"].eq("no_filter_baseline")]
    for mode in MODES:
        base = no_filter[(no_filter["portfolio_mode"].eq(mode)) & (no_filter["priority_policy"].eq("existing_priority_baseline"))]
        if base.empty:
            continue
        b = base.iloc[0]
        for _, r in no_filter[no_filter["portfolio_mode"].eq(mode)].iterrows():
            rows.append({
                "priority_policy": r["priority_policy"],
                "portfolio_mode": mode,
                "comparison_scope": "priority_only_no_filter",
                "net_pnl_delta_vs_existing_priority": _delta(r["net_pnl"], b["net_pnl"]),
                "fold_delta_vs_existing_priority": _delta(r["positive_wf_test_folds_pct"], b["positive_wf_test_folds_pct"]),
                "best_day_concentration_delta_vs_existing_priority": _delta(r["best_day_concentration"], b["best_day_concentration"]),
                "best_trade_concentration_delta_vs_existing_priority": _delta(r["best_trade_concentration"], b["best_trade_concentration"]),
                "active_days_delta_vs_existing_priority": int(r["active_days"] - b["active_days"]),
                "trades_delta_vs_existing_priority": int(r["trades"] - b["trades"]),
                "diagnostic_filter_only": False,
            })
        filt = results[(results["portfolio_mode"].eq(mode)) & (results["diagnostic_filter"].eq("exclude_overlap_heavy_days"))]
        for _, r in filt.iterrows():
            rows.append({
                "priority_policy": r["priority_policy"],
                "portfolio_mode": mode,
                "comparison_scope": "diagnostic_exclude_overlap_heavy_days",
                "net_pnl_delta_vs_existing_priority": _delta(r["net_pnl"], b["net_pnl"]),
                "fold_delta_vs_existing_priority": _delta(r["positive_wf_test_folds_pct"], b["positive_wf_test_folds_pct"]),
                "best_day_concentration_delta_vs_existing_priority": _delta(r["best_day_concentration"], b["best_day_concentration"]),
                "best_trade_concentration_delta_vs_existing_priority": _delta(r["best_trade_concentration"], b["best_trade_concentration"]),
                "active_days_delta_vs_existing_priority": int(r["active_days"] - b["active_days"]),
                "trades_delta_vs_existing_priority": int(r["trades"] - b["trades"]),
                "diagnostic_filter_only": True,
            })
    return pd.DataFrame(rows)


def make_next_action_recommendation(results: pd.DataFrame, acceptance: pd.DataFrame) -> dict[str, Any]:
    no_filter = results[results["diagnostic_filter"].eq("no_filter_baseline")]
    filters = results[results["diagnostic_filter"].eq("exclude_overlap_heavy_days")]
    baseline = no_filter[no_filter["priority_policy"].eq("existing_priority_baseline")]
    base_by_mode = {str(r["portfolio_mode"]): r for _, r in baseline.iterrows()}
    priority_improves_83 = False
    priority_helps_still_fails = False
    broad_instability = True
    for _, r in no_filter[~no_filter["priority_policy"].eq("existing_priority_baseline")].iterrows():
        b = base_by_mode.get(str(r["portfolio_mode"]))
        if b is None:
            continue
        fold_improved = (_delta(r["positive_wf_test_folds_pct"], b["positive_wf_test_folds_pct"]) or 0.0) > 0
        conc_improved = ((_delta(r["best_day_concentration"], b["best_day_concentration"]) or 0.0) < 0) or ((_delta(r["best_trade_concentration"], b["best_trade_concentration"]) or 0.0) < 0)
        activity_ratio = safe_divide(float(r["active_days"]), float(b["active_days"])) if float(b["active_days"] or 0) else 0.0
        if fold_improved or conc_improved:
            priority_helps_still_fails = True
        if float(r["positive_wf_test_folds_pct"] or 0) >= 0.833 and conc_improved and activity_ratio >= 0.80:
            priority_improves_83 = True
        if float(r["positive_wf_test_folds_pct"] or 0) >= 0.833:
            broad_instability = False
    filter_only_helps = False
    if not filters.empty:
        for _, r in filters.iterrows():
            b = base_by_mode.get(str(r["portfolio_mode"]))
            if b is not None and (_delta(r["positive_wf_test_folds_pct"], b["positive_wf_test_folds_pct"]) or 0.0) > 0:
                filter_only_helps = True
    consistently_harmful = consistently_harmful_module(acceptance, no_filter)
    if priority_improves_83:
        action = "playbook_scheduler_c_targeted_priority_review"
        rationale = "At least one priority-only policy improved folds to the 83.3% review threshold and improved concentration without major activity loss."
    elif consistently_harmful:
        action = "module_pruning_audit_a"
        rationale = f"Module {consistently_harmful} was consistently skipped or harmful across stronger priority-only rows."
    elif filter_only_helps and not priority_helps_still_fails:
        action = "regime_filter_b_diagnostic_review"
        rationale = "Only the diagnostic overlap-heavy-day exclusion improved folds; it remains diagnostic-only and is not a live/paper rule."
    elif priority_helps_still_fails:
        action = "keep_priority_policy_as_research_scheduler_and_run_weak_fold_module_scout"
        rationale = "Priority changes help folds or concentration, but Scheduler B rows still fail official review-style constraints."
    elif broad_instability:
        action = "validation_framework_audit_c_fold_design"
        rationale = "Fold instability remains broad despite priority retests."
    else:
        action = "phase16a_targeted_regime_module_scout"
        rationale = "No priority-only policy materially improves scheduler diagnostics."
    return {
        "next_action": action,
        "rationale": rationale,
        "official_gates_changed": False,
        "paper_trading_approved": False,
        "diagnostic_only_no_signals_generated": True,
        "live_trading_approved": False,
        "diagnostic_filters_are_not_live_or_paper_rules": True,
        "raw_sum_diagnostic_used_as_candidate": False,
    }


def consistently_harmful_module(acceptance: pd.DataFrame, no_filter_results: pd.DataFrame) -> str | None:
    if acceptance.empty or no_filter_results.empty:
        return None
    top = no_filter_results.sort_values(["positive_wf_test_folds_pct", "net_pnl"], ascending=[False, False]).head(4)
    keys = set(zip(top["priority_policy"], top["portfolio_mode"]))
    seg = acceptance[acceptance.apply(lambda r: (r["priority_policy"], r["portfolio_mode"]) in keys and r["diagnostic_filter"] == "no_filter_baseline", axis=1)]
    if seg.empty:
        return None
    grouped = seg.groupby("signal_key").agg(accepted=("accepted_trade_count", "sum"), skipped=("skipped_trade_count", "sum"), accepted_pnl=("accepted_net_pnl", "sum"))
    bad = grouped[(grouped["accepted"] == 0) | ((grouped["accepted_pnl"] < 0) & (grouped["skipped"] > grouped["accepted"]))]
    return None if bad.empty else str(bad.sort_values(["accepted_pnl", "skipped"]).index[0])


def baseline_by_mode_from_portfolio_d(results: pd.DataFrame) -> dict[str, dict[str, Any]]:
    out = {}
    for mode in MODES:
        seg = results[results["portfolio_mode"].astype(str).eq(mode)].copy()
        if not seg.empty:
            out[mode] = seg.sort_values(["net_pnl", "active_days", "portfolio_set"], ascending=[False, False, True]).iloc[0].to_dict()
    return out


def baseline_by_mode_from_scheduler_a(results: pd.DataFrame) -> dict[str, dict[str, Any]]:
    out = {}
    seg = results[(results["scheduler_variant"].astype(str).eq("existing_priority_baseline")) & (results["regime_filter"].astype(str).eq("no_filter_baseline"))].copy()
    for mode in MODES:
        m = seg[seg["portfolio_mode"].astype(str).eq(mode)]
        if not m.empty:
            out[mode] = m.iloc[0].to_dict()
    return out


def render_playbook_scheduler_b_report(result: dict[str, Any]) -> str:
    policy = result["priority_policy_results"]
    comparison = result["policy_comparison"]
    overlap = result["overlap_summary"]
    acceptance = result["module_acceptance_summary"]
    rec = result["next_action_recommendation"]
    best_priority = best_priority_only_result(policy)
    best_filter = best_diagnostic_filter_result(policy)
    lines = [
        "# Playbook Scheduler B — Priority Retest",
        "",
        RESEARCH_ONLY_GUARDRAIL,
        "",
        "Research-only scheduler retest using existing module trades only. No new signals, searches, candidate-result changes, official gate changes, promotions, paper-trading approval, or live-trading functionality were added.",
        "",
        "## Summary",
        "",
        f"- Selected modules: `{len(result['module_selection'])}` (hard cap `{MAX_SELECTED_MODULES}`)",
        f"- Priority policies tested: `{', '.join(PRIORITY_POLICIES)}`",
        f"- Modes tested: `{', '.join(MODES)}`",
        "- Diagnostic filters reported separately: `no_filter_baseline`, `exclude_overlap_heavy_days` (diagnostic-only; not a live/paper rule)",
        f"- Best priority-only result: `{best_priority.get('priority_policy')}` / `{best_priority.get('portfolio_mode')}` net `{float(best_priority.get('net_pnl', 0.0)):.2f}` positive folds `{float(best_priority.get('positive_wf_test_folds_pct') or 0.0):.3f}` concentration `{float(best_priority.get('best_day_concentration') or 0.0):.3f}`",
        f"- Best diagnostic-filter result: `{best_filter.get('priority_policy')}` / `{best_filter.get('portfolio_mode')}` net `{float(best_filter.get('net_pnl', 0.0)):.2f}` positive folds `{float(best_filter.get('positive_wf_test_folds_pct') or 0.0):.3f}` concentration `{float(best_filter.get('best_day_concentration') or 0.0):.3f}`",
        f"- Next action: `{rec['next_action']}`",
        f"- Rationale: {rec['rationale']}",
        "- Paper trading approved: `false`",
        "",
        "## Priority-only comparison (no filters)",
        "",
        markdown_table(comparison[comparison["comparison_scope"].eq("priority_only_no_filter")].head(40)),
        "",
        "## Diagnostic exclude-overlap-heavy comparison",
        "",
        "Diagnostic overlap filtering is shown for comparison only and is not recommended as a live/paper rule.",
        "",
        markdown_table(comparison[comparison["comparison_scope"].eq("diagnostic_exclude_overlap_heavy_days")].head(40)),
        "",
        "## Top scheduler rows",
        "",
        "| Policy | Mode | Filter | Net | Validation | Holdout | WF stress | Pos folds | Worst fold | Trades | Active days | Trades/day | Max DD | Best-day conc | Best-trade conc | Weak folds | Label | Status |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |",
    ]
    for _, r in policy.sort_values(["diagnostic_filter_only", "positive_wf_test_folds_pct", "net_pnl", "best_day_concentration"], ascending=[True, False, False, True]).head(30).iterrows():
        lines.append(f"| {r['priority_policy']} | {r['portfolio_mode']} | {r['diagnostic_filter']} | {float(r['net_pnl']):.2f} | {_fmt(r['validation_pnl'])} | {_fmt(r['holdout_pnl'])} | {_fmt(r['walk_forward_stress_pnl'])} | {float(r['positive_wf_test_folds_pct'] or 0):.3f} | {_fmt(r['worst_wf_test_fold'])} | {int(r['trades'])} | {int(r['active_days'])} | {float(r['trades_per_active_day']):.3f} | {float(r['max_drawdown']):.2f} | {float(r['best_day_concentration']):.3f} | {float(r['best_trade_concentration']):.3f} | {int(r['weak_fold_count'])} | {r['scheduler_b_label']} | {r['scheduler_b_status']} |")
    lines += [
        "",
        "## Module acceptance / suppression diagnostics",
        "",
        "Accepted/skipped module counts by policy are in `outputs/playbook_scheduler_b_module_acceptance_summary.csv`. Positive skipped PnL indicates priority rules may suppress helpful modules; negative skipped PnL indicates avoided harmful early modules.",
        "",
        markdown_table(acceptance.head(40)),
        "",
        "## Overlap diagnostics",
        "",
        markdown_table(overlap.head(40)),
        "",
        "## Guardrails",
        "",
        "Official gates changed: `false`.",
        "Paper trading approved: `false`.",
        "New strategy signals generated: `false`.",
        "Live trading approved: `false`.",
        "Raw-sum diagnostic used as scheduler candidate: `false`.",
        "",
    ]
    return "\n".join(lines)


def write_playbook_scheduler_b_outputs(result: dict[str, Any], output_dir: Path, report_path: Path) -> dict[str, Path]:
    ensure_directory(output_dir)
    ensure_directory(report_path.parent)
    mapping = {
        "priority_policy_results": output_dir / "playbook_scheduler_b_priority_policy_results.csv",
        "daily_pnl": output_dir / "playbook_scheduler_b_daily_pnl.csv",
        "walk_forward_folds": output_dir / "playbook_scheduler_b_walk_forward_folds.csv",
        "concentration": output_dir / "playbook_scheduler_b_concentration.csv",
        "overlap_summary": output_dir / "playbook_scheduler_b_overlap_summary.csv",
        "policy_comparison": output_dir / "playbook_scheduler_b_policy_comparison.csv",
        "module_acceptance_summary": output_dir / "playbook_scheduler_b_module_acceptance_summary.csv",
    }
    paths: dict[str, Path] = {}
    for key, path in mapping.items():
        write_csv_artifact(result[key], path)
        paths[key] = path
    rec_path = output_dir / "playbook_scheduler_b_next_action_recommendation.json"
    write_json_artifact(result["next_action_recommendation"], rec_path)
    report_path.write_text(render_playbook_scheduler_b_report(result), encoding="utf-8")
    paths["recommendation"] = rec_path
    paths["report"] = report_path
    return paths


def best_priority_only_result(results: pd.DataFrame) -> dict[str, Any]:
    seg = results[results["diagnostic_filter"].eq("no_filter_baseline")]
    if seg.empty:
        return {}
    return seg.sort_values(["positive_wf_test_folds_pct", "net_pnl", "best_day_concentration", "priority_policy"], ascending=[False, False, True, True]).iloc[0].to_dict()


def best_diagnostic_filter_result(results: pd.DataFrame) -> dict[str, Any]:
    seg = results[results["diagnostic_filter"].eq("exclude_overlap_heavy_days")]
    if seg.empty:
        return {}
    return seg.sort_values(["positive_wf_test_folds_pct", "net_pnl", "best_day_concentration", "priority_policy"], ascending=[False, False, True, True]).iloc[0].to_dict()


def loaded_input_names() -> list[str]:
    return [
        "outputs/playbook_module_registry.csv",
        "outputs/research_signal_registry.csv",
        "outputs/playbook_scheduler_audit_a_priority_results.csv",
        "outputs/playbook_scheduler_audit_a_regime_filter_results.csv",
        "outputs/playbook_scheduler_audit_a_overlap_diagnostics.csv",
        "outputs/playbook_scheduler_audit_a_daily_pnl.csv",
        "outputs/playbook_scheduler_audit_a_walk_forward_folds.csv",
        "outputs/playbook_scheduler_audit_a_concentration.csv",
        "outputs/playbook_scheduler_audit_a_next_action_recommendation.json",
        "outputs/portfolio_audit_d_signal_selection.csv",
        "outputs/portfolio_audit_d_signal_correlation.csv",
        "outputs/portfolio_audit_d_daily_pnl_matrix.csv",
        "outputs/portfolio_audit_d_portfolio_results.csv",
        "outputs/portfolio_audit_d_portfolio_daily_pnl.csv",
        "outputs/portfolio_audit_d_portfolio_walk_forward_folds.csv",
        "outputs/portfolio_audit_d_trade_overlap_summary.csv",
        "outputs/portfolio_audit_d_next_action_recommendation.json",
        *[f"outputs/{phase}_trade_logs.csv" for phase in PHASES],
    ]


def markdown_table(df: pd.DataFrame) -> str:
    if df.empty:
        return "No rows."
    cols = list(df.columns)
    lines = ["| " + " | ".join(cols) + " |", "| " + " | ".join("---" for _ in cols) + " |"]
    for _, row in df.iterrows():
        lines.append("| " + " | ".join(str(row[c]) for c in cols) + " |")
    return "\n".join(lines)


def _concat(frames: list[pd.DataFrame]) -> pd.DataFrame:
    frames = [f for f in frames if isinstance(f, pd.DataFrame) and not f.empty]
    return pd.concat(frames, ignore_index=True, sort=False) if frames else pd.DataFrame()


def _delta(value: Any, base: Any) -> float | None:
    v = _float_or_none(value)
    b = _float_or_none(base)
    return None if v is None or b is None else round(v - b, 6)


def _float_or_none(value: Any) -> float | None:
    try:
        if pd.isna(value):
            return None
        return float(value)
    except Exception:
        return None


def _fmt(value: Any) -> str:
    v = _float_or_none(value)
    return "" if v is None else f"{v:.2f}"


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))
