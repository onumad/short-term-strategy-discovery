from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from .phase_common import ensure_directory, safe_divide, write_csv_artifact, write_json_artifact
from .portfolio_audit_b import RESEARCH_ONLY_GUARDRAIL, concentration, max_drawdown, signal_key, split_signal_key
from .portfolio_audit_c import portfolio_folds
from .portfolio_audit_d import PHASES, PHASE_PRIORITY as EXISTING_PHASE_PRIORITY

MODES = ("one_trade_at_a_time_chronological", "max_one_trade_per_session")
SCHEDULER_VARIANTS = (
    "existing_priority_baseline",
    "phase15a_first",
    "phase14a_first",
    "phase13a_first",
    "phase10b_first",
    "rare_setup_first",
    "lowest_correlation_first",
    "highest_recent_validation_first",
)
REGIME_FILTERS = (
    "exclude_high_vol_mixed_days",
    "exclude_high_vol_mixed_power_expand_days",
    "exclude_high_vol_mixed_no_power_expand_days",
    "exclude_overlap_heavy_days",
    "no_filter_baseline",
)
OFFICIAL_GATES_UNCHANGED = True
PAPER_TRADING_APPROVED = False
DIAGNOSTIC_ONLY_NO_SIGNALS_GENERATED = True


def load_playbook_scheduler_audit_a_inputs(output_dir: Path) -> dict[str, Any]:
    required: dict[str, Path] = {
        "playbook_module_registry": output_dir / "playbook_module_registry.csv",
        "research_signal_registry": output_dir / "research_signal_registry.csv",
        "portfolio_d_results": output_dir / "portfolio_audit_d_portfolio_results.csv",
        "portfolio_d_daily": output_dir / "portfolio_audit_d_portfolio_daily_pnl.csv",
        "portfolio_d_folds": output_dir / "portfolio_audit_d_portfolio_walk_forward_folds.csv",
        "portfolio_d_overlap": output_dir / "portfolio_audit_d_trade_overlap_summary.csv",
        "portfolio_d_recommendation": output_dir / "portfolio_audit_d_next_action_recommendation.json",
        "weak_fold_b_fold_summary": output_dir / "weak_fold_regime_audit_b_fold_summary.csv",
        "weak_fold_b_weak_days": output_dir / "weak_fold_regime_audit_b_weak_fold_days.csv",
        "weak_fold_b_market_features": output_dir / "weak_fold_regime_audit_b_market_regime_features.csv",
        "weak_fold_b_regime_comparison": output_dir / "weak_fold_regime_audit_b_regime_comparison.csv",
        "weak_fold_b_overlap_diag": output_dir / "weak_fold_regime_audit_b_overlap_and_scheduler_diagnostics.csv",
        "weak_fold_b_bad_day_clusters": output_dir / "weak_fold_regime_audit_b_bad_day_clusters.csv",
    }
    for phase in PHASES:
        required[f"{phase}_trades"] = output_dir / f"{phase}_trade_logs.csv"
    missing = [str(path) for path in required.values() if not path.exists()]
    if missing:
        raise FileNotFoundError(f"Missing Playbook Scheduler Audit A input(s): {missing}")
    data: dict[str, Any] = {}
    for key, path in required.items():
        data[key] = _read_json(path) if path.suffix == ".json" else pd.read_csv(path)
    return data


def run_playbook_scheduler_audit_a(output_dir: Path) -> dict[str, Any]:
    data = load_playbook_scheduler_audit_a_inputs(output_dir)
    selected_keys = selected_portfolio_d_signal_keys(data["portfolio_d_results"])
    module_meta = module_metadata(data, selected_keys)
    trades = selected_trade_logs(data, selected_keys)
    daily_matrix = module_daily_matrix_from_trades(trades)
    overlap_days = overlap_heavy_sessions(trades)
    priority_rows: list[dict[str, Any]] = []
    daily_rows: list[pd.DataFrame] = []
    fold_rows: list[pd.DataFrame] = []
    concentration_rows: list[dict[str, Any]] = []
    overlap_rows: list[dict[str, Any]] = []
    regime_rows: list[dict[str, Any]] = []

    baseline_by_mode = portfolio_d_best_by_mode(data["portfolio_d_results"])
    variant_orders = build_scheduler_variant_orders(selected_keys, module_meta, daily_matrix)
    filter_sessions = build_regime_filter_sessions(data["weak_fold_b_market_features"], overlap_days)

    for variant in SCHEDULER_VARIANTS:
        order_map = variant_orders[variant]
        for mode in MODES:
            for filter_name in REGIME_FILTERS:
                excluded = filter_sessions.get(filter_name, set())
                accepted, skipped_overlap, skipped_session, rejected = construct_scheduled_trades(trades, selected_keys, order_map, mode, excluded)
                daily = scheduled_daily_pnl(accepted, variant, mode, filter_name)
                metrics = scheduler_metrics(
                    variant,
                    mode,
                    filter_name,
                    selected_keys,
                    accepted,
                    daily,
                    skipped_overlap,
                    skipped_session,
                    rejected,
                    baseline_by_mode.get(mode, {}),
                )
                priority_rows.append(metrics)
                daily_rows.append(daily)
                folds = scheduler_folds(variant, mode, filter_name, daily)
                fold_rows.append(folds)
                concentration_rows.append({k: metrics[k] for k in ("scheduler_variant", "portfolio_mode", "regime_filter", "best_day_concentration", "best_trade_concentration", "top_3_day_concentration", "top_5_trade_concentration", "best_day_concentration_delta_vs_portfolio_audit_d_best", "best_trade_concentration_delta_vs_portfolio_audit_d_best")})
                overlap_rows.append(overlap_diagnostic_row(variant, mode, filter_name, accepted, rejected, skipped_overlap, skipped_session))
                if filter_name != "no_filter_baseline":
                    regime_rows.append(regime_filter_row(filter_name, variant, mode, accepted, rejected, daily, filter_sessions))

    priority_results = pd.DataFrame(priority_rows).sort_values(["scheduler_variant", "portfolio_mode", "regime_filter"]).reset_index(drop=True)
    daily_pnl = _concat(daily_rows)
    folds = _concat(fold_rows)
    concentration_df = pd.DataFrame(concentration_rows).sort_values(["scheduler_variant", "portfolio_mode", "regime_filter"]).reset_index(drop=True)
    overlap_df = pd.DataFrame(overlap_rows).sort_values(["scheduler_variant", "portfolio_mode", "regime_filter"]).reset_index(drop=True)
    regime_df = pd.DataFrame(regime_rows).sort_values(["regime_filter", "scheduler_variant", "portfolio_mode"]).reset_index(drop=True)
    recommendation = make_next_action_recommendation(priority_results, regime_df)
    return {
        "priority_results": priority_results,
        "regime_filter_results": regime_df,
        "overlap_diagnostics": overlap_df,
        "daily_pnl": daily_pnl,
        "walk_forward_folds": folds,
        "concentration": concentration_df,
        "next_action_recommendation": recommendation,
        "selected_signal_keys": selected_keys,
        "scheduler_variant_orders": variant_orders,
        "inputs_loaded": loaded_input_names(),
    }


def selected_portfolio_d_signal_keys(results: pd.DataFrame) -> list[str]:
    if results.empty:
        return []
    preferred = results[results["portfolio_mode"].astype(str).isin(MODES)].copy()
    seg = preferred if not preferred.empty else results.copy()
    sort_cols = [c for c in ["official_gates_passed", "net_pnl", "active_days", "portfolio_set", "portfolio_mode"] if c in seg.columns]
    ascending = [False if c in {"official_gates_passed", "net_pnl", "active_days"} else True for c in sort_cols]
    row = seg.sort_values(sort_cols, ascending=ascending).iloc[0]
    return [k for k in str(row.get("signal_keys", "")).split(";") if k]


def module_metadata(data: dict[str, Any], selected_keys: list[str]) -> pd.DataFrame:
    modules = data["playbook_module_registry"].copy()
    modules["phase"] = modules["phase"].astype(str)
    modules["candidate_id"] = modules["candidate_id"].astype(str)
    modules["signal_key"] = modules.apply(lambda r: signal_key(r["phase"], r["candidate_id"]), axis=1)
    for col in ("net_pnl", "validation_pnl", "holdout_pnl", "walk_forward_stress_pnl", "positive_wf_test_folds_pct", "active_days"):
        modules[col] = pd.to_numeric(modules[col], errors="coerce").fillna(0.0) if col in modules else 0.0
    modules = modules[modules["signal_key"].isin(selected_keys)].copy()
    modules["existing_priority"] = modules["phase"].map(EXISTING_PHASE_PRIORITY).fillna(99).astype(int)
    modules["selected_order"] = modules["signal_key"].map({key: i for i, key in enumerate(selected_keys)})
    return modules.sort_values(["existing_priority", "selected_order", "candidate_id"]).reset_index(drop=True)


def selected_trade_logs(data: dict[str, Any], selected_keys: list[str]) -> pd.DataFrame:
    selected = set(selected_keys)
    rows = []
    for phase in PHASES:
        trades = data.get(f"{phase}_trades", pd.DataFrame()).copy()
        if trades.empty or "candidate_id" not in trades.columns:
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
            if col in trades:
                trades[col] = pd.to_numeric(trades[col], errors="coerce").fillna(0.0)
        if "split" not in trades:
            trades["split"] = "not_available"
        rows.append(trades)
    out = _concat(rows)
    if out.empty:
        return pd.DataFrame(columns=["phase", "candidate_id", "signal_key", "entry_time", "exit_time", "trading_session", "net_pnl", "stress_pnl", "split"])
    return out.sort_values(["entry_time", "phase", "candidate_id", "exit_time"]).reset_index(drop=True)


def module_daily_matrix_from_trades(trades: pd.DataFrame) -> pd.DataFrame:
    if trades.empty:
        return pd.DataFrame(columns=["trading_session"])
    daily = trades.groupby(["trading_session", "signal_key"], as_index=False)["net_pnl"].sum()
    matrix = daily.pivot(index="trading_session", columns="signal_key", values="net_pnl").fillna(0.0).reset_index()
    return matrix.sort_values("trading_session").reset_index(drop=True)


def build_scheduler_variant_orders(selected_keys: list[str], meta: pd.DataFrame, daily_matrix: pd.DataFrame) -> dict[str, dict[str, int]]:
    base = {key: i for i, key in enumerate(selected_keys)}
    def phase_first_order(first_phase: str) -> dict[str, int]:
        ordered = sorted(selected_keys, key=lambda key: (0 if key.split("::", 1)[0] == first_phase else 1, EXISTING_PHASE_PRIORITY.get(key.split("::", 1)[0], 99), base[key], key))
        return {key: i for i, key in enumerate(ordered)}
    orders = {
        "existing_priority_baseline": {key: i for i, key in enumerate(sorted(selected_keys, key=lambda key: (EXISTING_PHASE_PRIORITY.get(key.split("::", 1)[0], 99), base[key], key)))},
        "phase15a_first": phase_first_order("phase15a"),
        "phase14a_first": phase_first_order("phase14a"),
        "phase13a_first": phase_first_order("phase13a"),
        "phase10b_first": phase_first_order("phase10b"),
    }
    track = meta.set_index("signal_key").get("research_track", pd.Series(dtype=str)).astype(str).to_dict() if not meta.empty else {}
    orders["rare_setup_first"] = {key: i for i, key in enumerate(sorted(selected_keys, key=lambda key: (0 if track.get(key) == "rare_setup_research_signal" else 1, EXISTING_PHASE_PRIORITY.get(key.split("::", 1)[0], 99), base[key], key)))}
    orders["lowest_correlation_first"] = lowest_correlation_order(selected_keys, daily_matrix, base)
    validation = meta.set_index("signal_key").get("validation_pnl", pd.Series(dtype=float)).to_dict() if not meta.empty else {}
    orders["highest_recent_validation_first"] = {key: i for i, key in enumerate(sorted(selected_keys, key=lambda key: (-float(validation.get(key, 0.0)), EXISTING_PHASE_PRIORITY.get(key.split("::", 1)[0], 99), base[key], key)))}
    return orders


def lowest_correlation_order(selected_keys: list[str], daily_matrix: pd.DataFrame, base: dict[str, int]) -> dict[str, int]:
    if daily_matrix.empty:
        return dict(base)
    cols = [k for k in selected_keys if k in daily_matrix.columns]
    if not cols:
        return dict(base)
    corr = daily_matrix[cols].corr().fillna(0.0).abs()
    avg = {key: float(corr.loc[key, [c for c in cols if c != key]].mean()) if len(cols) > 1 else 0.0 for key in cols}
    ordered = sorted(selected_keys, key=lambda key: (avg.get(key, 0.0), EXISTING_PHASE_PRIORITY.get(key.split("::", 1)[0], 99), base[key], key))
    return {key: i for i, key in enumerate(ordered)}


def build_regime_filter_sessions(features: pd.DataFrame, overlap_days: set[str]) -> dict[str, set[str]]:
    if features.empty:
        return {name: set() for name in REGIME_FILTERS}
    f = features.copy()
    f["trading_session"] = f["trading_session"].astype(str)
    high = _bool_series(f, "high_volatility_bucket")
    mixed = ~_bool_series(f, "full_day_trend_proxy") & ~_bool_series(f, "range_day_proxy")
    power = _bool_series(f, "power_hour_expansion")
    return {
        "exclude_high_vol_mixed_days": set(f.loc[high & mixed, "trading_session"]),
        "exclude_high_vol_mixed_power_expand_days": set(f.loc[high & mixed & power, "trading_session"]),
        "exclude_high_vol_mixed_no_power_expand_days": set(f.loc[high & mixed & ~power, "trading_session"]),
        "exclude_overlap_heavy_days": set(overlap_days),
        "no_filter_baseline": set(),
    }


def overlap_heavy_sessions(trades: pd.DataFrame) -> set[str]:
    if trades.empty:
        return set()
    counts = trades.groupby("trading_session")["signal_key"].nunique()
    return set(counts[counts > 1].index.astype(str))


def construct_scheduled_trades(trades: pd.DataFrame, signal_keys: list[str], order_map: dict[str, int], mode: str, excluded_sessions: set[str] | None = None) -> tuple[pd.DataFrame, int, int, pd.DataFrame]:
    excluded_sessions = excluded_sessions or set()
    seg = trades[trades["signal_key"].isin(signal_keys)].copy()
    if excluded_sessions:
        seg = seg[~seg["trading_session"].astype(str).isin(excluded_sessions)].copy()
    if seg.empty:
        return seg, 0, 0, pd.DataFrame(columns=list(trades.columns) + ["skip_reason"])
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
    return pd.DataFrame(accepted), skipped_overlap, skipped_session, pd.DataFrame(rejected)


def scheduled_daily_pnl(accepted: pd.DataFrame, variant: str, mode: str, filter_name: str) -> pd.DataFrame:
    if accepted.empty:
        daily = pd.DataFrame(columns=["trading_session", "net_pnl"])
    else:
        daily = accepted.groupby("trading_session", as_index=False)["net_pnl"].sum().sort_values("trading_session")
    daily.insert(0, "regime_filter", filter_name)
    daily.insert(0, "portfolio_mode", mode)
    daily.insert(0, "scheduler_variant", variant)
    return daily[["scheduler_variant", "portfolio_mode", "regime_filter", "trading_session", "net_pnl"]]


def scheduler_folds(variant: str, mode: str, filter_name: str, daily: pd.DataFrame) -> pd.DataFrame:
    base = daily.rename(columns={"scheduler_variant": "portfolio_set"}).copy()
    base["portfolio_set"] = variant
    folds = portfolio_folds(variant, mode, base[["portfolio_set", "portfolio_mode", "trading_session", "net_pnl"]])
    if folds.empty:
        return pd.DataFrame(columns=["scheduler_variant", "portfolio_mode", "regime_filter", "fold", "net_pnl", "stress_pnl", "active_days"])
    folds = folds.rename(columns={"portfolio_set": "scheduler_variant"})
    folds.insert(2, "regime_filter", filter_name)
    return folds[["scheduler_variant", "portfolio_mode", "regime_filter", "fold", "net_pnl", "stress_pnl", "active_days"]]


def scheduler_metrics(variant: str, mode: str, filter_name: str, signal_keys: list[str], accepted: pd.DataFrame, daily: pd.DataFrame, skipped_overlap: int, skipped_session: int, rejected: pd.DataFrame, baseline: dict[str, Any]) -> dict[str, Any]:
    net = round(float(daily["net_pnl"].sum()), 2) if not daily.empty else 0.0
    split = accepted.groupby("split")["net_pnl"].sum().to_dict() if not accepted.empty and "split" in accepted else {}
    validation = round(float(split.get("validation", 0.0)), 2) if split else None
    holdout = round(float(split.get("holdout", 0.0)), 2) if split else None
    folds = scheduler_folds(variant, mode, filter_name, daily)
    wf_stress = round(float(folds["stress_pnl"].sum()), 2) if not folds.empty else None
    pos_folds = round(safe_divide(int((folds["stress_pnl"] > 0).sum()), len(folds)), 6) if not folds.empty else None
    worst_fold = round(float(folds["stress_pnl"].min()), 2) if not folds.empty else None
    weak_fold_count = int((folds["stress_pnl"] <= 0).sum()) if not folds.empty else 0
    weak_fold_pnl = round(float(folds.loc[folds["stress_pnl"] <= 0, "stress_pnl"].sum()), 2) if not folds.empty else 0.0
    day_conc = concentration(daily["net_pnl"] if not daily.empty else pd.Series(dtype=float))
    trade_conc = concentration(accepted["net_pnl"] if not accepted.empty else pd.Series(dtype=float))
    active_days = int(daily["trading_session"].nunique()) if not daily.empty else 0
    baseline_net = _float_or_none(baseline.get("net_pnl"))
    return {
        "scheduler_variant": variant,
        "portfolio_mode": mode,
        "regime_filter": filter_name,
        "signals": len(signal_keys),
        "signal_keys": ";".join(signal_keys),
        "net_pnl": net,
        "validation_pnl": validation,
        "holdout_pnl": holdout,
        "walk_forward_stress_pnl": wf_stress,
        "positive_wf_test_folds_pct": pos_folds,
        "worst_wf_test_fold": worst_fold,
        "trades": int(len(accepted)),
        "active_days": active_days,
        "max_drawdown": max_drawdown(daily["net_pnl"] if not daily.empty else pd.Series(dtype=float)),
        "best_day_concentration": day_conc["best"],
        "best_trade_concentration": trade_conc["best"],
        "top_3_day_concentration": day_conc["top3"],
        "top_5_trade_concentration": trade_conc["top5"],
        "skipped_overlap_count": int(skipped_overlap),
        "skipped_session_count": int(skipped_session),
        "rejected_trade_count": int(len(rejected)),
        "weak_fold_count": weak_fold_count,
        "weak_fold_pnl": weak_fold_pnl,
        "improvement_vs_portfolio_audit_d_best": round(net - baseline_net, 2) if baseline_net is not None else None,
        "fold_delta_vs_portfolio_audit_d_best": _delta(pos_folds, baseline.get("positive_wf_test_folds_pct")),
        "best_day_concentration_delta_vs_portfolio_audit_d_best": _delta(day_conc["best"], baseline.get("best_day_concentration")),
        "best_trade_concentration_delta_vs_portfolio_audit_d_best": _delta(trade_conc["best"], baseline.get("best_trade_concentration")),
        "activity_delta_vs_portfolio_audit_d_best": active_days - int(baseline.get("active_days", 0)) if baseline else None,
        "official_gates_changed": False,
        "paper_trading_approved": False,
        "diagnostic_only_no_signals_generated": True,
    }


def portfolio_d_best_by_mode(results: pd.DataFrame) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for mode in MODES:
        seg = results[results["portfolio_mode"].astype(str).eq(mode)].copy()
        if seg.empty:
            continue
        row = seg.sort_values(["net_pnl", "active_days", "portfolio_set"], ascending=[False, False, True]).iloc[0]
        out[mode] = row.to_dict()
    return out


def overlap_diagnostic_row(variant: str, mode: str, filter_name: str, accepted: pd.DataFrame, rejected: pd.DataFrame, skipped_overlap: int, skipped_session: int) -> dict[str, Any]:
    early_loss_later_help = 0
    if not accepted.empty:
        for _, day in accepted.groupby("trading_session"):
            day = day.sort_values(["entry_time", "scheduler_priority", "candidate_id"])
            if len(day) > 1 and float(day.iloc[0].get("net_pnl", 0.0)) < 0 and float(day.iloc[1:]["net_pnl"].sum()) > 0:
                early_loss_later_help += 1
    rejected_positive = int((rejected["net_pnl"] > 0).sum()) if not rejected.empty and "net_pnl" in rejected else 0
    rejected_positive_pnl = round(float(rejected.loc[rejected["net_pnl"] > 0, "net_pnl"].sum()), 2) if not rejected.empty and "net_pnl" in rejected else 0.0
    return {
        "scheduler_variant": variant,
        "portfolio_mode": mode,
        "regime_filter": filter_name,
        "accepted_trades": int(len(accepted)),
        "skipped_overlap_count": int(skipped_overlap),
        "skipped_session_count": int(skipped_session),
        "rejected_positive_trade_count": rejected_positive,
        "rejected_positive_pnl": rejected_positive_pnl,
        "early_losing_module_when_later_module_helped_days": int(early_loss_later_help),
    }


def regime_filter_row(filter_name: str, variant: str, mode: str, accepted: pd.DataFrame, rejected: pd.DataFrame, daily: pd.DataFrame, filter_sessions: dict[str, set[str]]) -> dict[str, Any]:
    excluded = filter_sessions.get(filter_name, set())
    return {
        "regime_filter": filter_name,
        "scheduler_variant": variant,
        "portfolio_mode": mode,
        "excluded_day_count": int(len(excluded)),
        "accepted_trades_after_filter": int(len(accepted)),
        "active_days_after_filter": int(daily["trading_session"].nunique()) if not daily.empty else 0,
        "net_pnl_after_filter": round(float(daily["net_pnl"].sum()), 2) if not daily.empty else 0.0,
        "rejected_trade_count_after_scheduler": int(len(rejected)),
        "diagnostic_only_not_live_rule": True,
    }


def make_next_action_recommendation(priority_results: pd.DataFrame, regime_results: pd.DataFrame) -> dict[str, Any]:
    baseline = priority_results[priority_results["scheduler_variant"].eq("existing_priority_baseline") & priority_results["regime_filter"].eq("no_filter_baseline")]
    base_by_mode = {str(r["portfolio_mode"]): r for _, r in baseline.iterrows()}
    nonbase = priority_results[~priority_results["scheduler_variant"].eq("existing_priority_baseline") & priority_results["regime_filter"].eq("no_filter_baseline")]
    priority_help = False
    concentration_help = False
    if not nonbase.empty:
        for _, row in nonbase.iterrows():
            base = base_by_mode.get(str(row["portfolio_mode"]))
            if base is None:
                continue
            fold_delta = _delta(row.get("positive_wf_test_folds_pct"), base.get("positive_wf_test_folds_pct")) or 0.0
            conc_delta = _delta(row.get("best_day_concentration"), base.get("best_day_concentration")) or 0.0
            priority_help = priority_help or (fold_delta > 0 and float(row.get("weak_fold_count", 999)) <= float(base.get("weak_fold_count", 999)))
            concentration_help = concentration_help or conc_delta < 0
    filter_seg = priority_results[~priority_results["regime_filter"].eq("no_filter_baseline")]
    filter_help_low_activity = False
    if not filter_seg.empty:
        for _, row in filter_seg.iterrows():
            base = base_by_mode.get(str(row["portfolio_mode"]))
            if base is None:
                continue
            fold_delta = _delta(row.get("positive_wf_test_folds_pct"), base.get("positive_wf_test_folds_pct")) or 0.0
            activity_ratio = safe_divide(float(row.get("active_days", 0)), float(base.get("active_days", 0))) if float(base.get("active_days", 0)) else 0.0
            if fold_delta > 0 and activity_ratio < 0.70:
                filter_help_low_activity = True
    phase_bad = module_priority_clearly_hurts(priority_results)
    if phase_bad:
        action = "module_pruning_audit_a"
        rationale = "One module/phase-first priority variant clearly worsened scheduler diagnostics versus the existing baseline."
    elif priority_help or concentration_help:
        action = "playbook_scheduler_b_priority_retest"
        rationale = "At least one diagnostic priority change improved fold stability or concentration versus the Portfolio Audit D scheduler baseline."
    elif filter_help_low_activity:
        action = "regime_filter_b_diagnostic_review"
        rationale = "Diagnostic regime filters improved folds only while materially reducing activity; review as diagnostics only, not live rules."
    else:
        action = "phase16a_targeted_regime_module_scout"
        rationale = "Priority changes and diagnostic filters did not materially fix weak folds or concentration."
    return {
        "next_action": action,
        "rationale": rationale,
        "official_gates_changed": False,
        "paper_trading_approved": False,
        "diagnostic_only_no_signals_generated": True,
        "live_trading_approved": False,
    }


def module_priority_clearly_hurts(results: pd.DataFrame) -> bool:
    baseline = results[results["scheduler_variant"].eq("existing_priority_baseline") & results["regime_filter"].eq("no_filter_baseline")]
    if baseline.empty:
        return False
    for variant in ("phase15a_first", "phase14a_first", "phase13a_first", "phase10b_first"):
        seg = results[results["scheduler_variant"].eq(variant) & results["regime_filter"].eq("no_filter_baseline")]
        hurt = 0
        for _, row in seg.iterrows():
            base = baseline[baseline["portfolio_mode"].eq(row["portfolio_mode"])]
            if base.empty:
                continue
            b = base.iloc[0]
            if float(row["net_pnl"]) < float(b["net_pnl"]) and float(row["weak_fold_count"]) > float(b["weak_fold_count"]):
                hurt += 1
        if hurt >= len(MODES):
            return True
    return False


def render_playbook_scheduler_audit_a_report(result: dict[str, Any]) -> str:
    priority = result["priority_results"]
    regime = result["regime_filter_results"]
    overlap = result["overlap_diagnostics"]
    rec = result["next_action_recommendation"]
    best = best_result(priority)
    lines = [
        "# Playbook Scheduler Audit A — Priority / Overlap / Regime Filter Diagnostic",
        "",
        RESEARCH_ONLY_GUARDRAIL,
        "",
        "Diagnostic only. This audit uses existing module trade logs and Portfolio Audit D / Weak Fold Regime Audit B outputs only. It does not generate new signals, run strategy searches, change candidate results, change official gates, promote candidates, approve paper trading, or add live-trading functionality.",
        "",
        "## Summary",
        "",
        f"- Scheduler variants tested: `{', '.join(SCHEDULER_VARIANTS)}`",
        f"- Modes tested: `{', '.join(MODES)}`",
        f"- Diagnostic regime filters tested: `{', '.join(REGIME_FILTERS)}`",
        f"- Best scheduler/filter result: `{best.get('scheduler_variant')}` / `{best.get('portfolio_mode')}` / `{best.get('regime_filter')}` net `{float(best.get('net_pnl', 0.0)):.2f}` positive folds `{float(best.get('positive_wf_test_folds_pct') or 0.0):.3f}`",
        f"- Next action: `{rec['next_action']}`",
        f"- Rationale: {rec['rationale']}",
        "- Paper trading approved: `false`",
        "",
        "## Top scheduler/filter rows",
        "",
        "| Variant | Mode | Filter | Net | Active days | Trades | Pos folds | Worst fold | Max DD | Best-day conc | Best-trade conc | Skipped overlap | Skipped session | Weak folds | Δ vs Audit D best |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    if not priority.empty:
        for _, r in priority.sort_values(["positive_wf_test_folds_pct", "net_pnl", "best_day_concentration"], ascending=[False, False, True]).head(20).iterrows():
            lines.append(f"| {r['scheduler_variant']} | {r['portfolio_mode']} | {r['regime_filter']} | {float(r['net_pnl']):.2f} | {int(r['active_days'])} | {int(r['trades'])} | {float(r['positive_wf_test_folds_pct'] or 0):.3f} | {float(r['worst_wf_test_fold'] or 0):.2f} | {float(r['max_drawdown']):.2f} | {float(r['best_day_concentration']):.3f} | {float(r['best_trade_concentration']):.3f} | {int(r['skipped_overlap_count'])} | {int(r['skipped_session_count'])} | {int(r['weak_fold_count'])} | {_fmt(r['improvement_vs_portfolio_audit_d_best'])} |")
    lines += ["", "## Regime filter diagnostics", "", "Diagnostic filters are not promotion filters or live rules.", "", markdown_table(regime.head(30)) if not regime.empty else "No regime filter rows.", "", "## Overlap diagnostics", "", markdown_table(overlap.head(30)) if not overlap.empty else "No overlap diagnostics.", "", "## Guardrails", "", "Official gates changed: `false`.", "Paper trading approved: `false`.", "New strategy signals generated: `false`.", "Live trading approved: `false`.", ""]
    return "\n".join(lines)


def write_playbook_scheduler_audit_a_outputs(result: dict[str, Any], output_dir: Path, report_path: Path) -> dict[str, Path]:
    ensure_directory(output_dir)
    ensure_directory(report_path.parent)
    mapping = {
        "priority_results": output_dir / "playbook_scheduler_audit_a_priority_results.csv",
        "regime_filter_results": output_dir / "playbook_scheduler_audit_a_regime_filter_results.csv",
        "overlap_diagnostics": output_dir / "playbook_scheduler_audit_a_overlap_diagnostics.csv",
        "daily_pnl": output_dir / "playbook_scheduler_audit_a_daily_pnl.csv",
        "walk_forward_folds": output_dir / "playbook_scheduler_audit_a_walk_forward_folds.csv",
        "concentration": output_dir / "playbook_scheduler_audit_a_concentration.csv",
    }
    paths: dict[str, Path] = {}
    for key, path in mapping.items():
        write_csv_artifact(result[key], path)
        paths[key] = path
    rec_path = output_dir / "playbook_scheduler_audit_a_next_action_recommendation.json"
    write_json_artifact(result["next_action_recommendation"], rec_path)
    report_path.write_text(render_playbook_scheduler_audit_a_report(result), encoding="utf-8")
    paths["recommendation"] = rec_path
    paths["report"] = report_path
    return paths


def best_result(priority: pd.DataFrame) -> dict[str, Any]:
    if priority.empty:
        return {}
    row = priority.sort_values(["positive_wf_test_folds_pct", "net_pnl", "best_day_concentration", "scheduler_variant"], ascending=[False, False, True, True]).iloc[0]
    return row.to_dict()


def loaded_input_names() -> list[str]:
    return [
        "outputs/playbook_module_registry.csv",
        "outputs/research_signal_registry.csv",
        "outputs/portfolio_audit_d_portfolio_results.csv",
        "outputs/portfolio_audit_d_portfolio_daily_pnl.csv",
        "outputs/portfolio_audit_d_portfolio_walk_forward_folds.csv",
        "outputs/portfolio_audit_d_trade_overlap_summary.csv",
        "outputs/portfolio_audit_d_next_action_recommendation.json",
        "outputs/weak_fold_regime_audit_b_fold_summary.csv",
        "outputs/weak_fold_regime_audit_b_weak_fold_days.csv",
        "outputs/weak_fold_regime_audit_b_market_regime_features.csv",
        "outputs/weak_fold_regime_audit_b_regime_comparison.csv",
        "outputs/weak_fold_regime_audit_b_overlap_and_scheduler_diagnostics.csv",
        "outputs/weak_fold_regime_audit_b_bad_day_clusters.csv",
        *[f"outputs/{phase}_trade_logs.csv" for phase in PHASES],
    ]


def markdown_table(df: pd.DataFrame) -> str:
    if df.empty:
        return ""
    cols = list(df.columns)
    lines = ["| " + " | ".join(cols) + " |", "| " + " | ".join("---" for _ in cols) + " |"]
    for _, row in df.iterrows():
        lines.append("| " + " | ".join(str(row[c]) for c in cols) + " |")
    return "\n".join(lines)


def _bool_series(df: pd.DataFrame, col: str) -> pd.Series:
    if col not in df:
        return pd.Series(False, index=df.index)
    s = df[col]
    if s.dtype == bool:
        return s.fillna(False)
    return s.astype(str).str.lower().isin({"true", "1", "yes"})


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
