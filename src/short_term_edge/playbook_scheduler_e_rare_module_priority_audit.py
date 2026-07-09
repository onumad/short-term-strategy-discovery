from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from .phase_common import ensure_directory, safe_divide, write_csv_artifact, write_json_artifact
from .playbook_scheduler_b_priority_retest import PHASES, average_abs_correlation, module_daily_matrix_from_trades, selected_trade_logs
from .portfolio_audit_b import RESEARCH_ONLY_GUARDRAIL, concentration, max_drawdown, signal_key, split_signal_key, unique
from .portfolio_audit_c import phase_days_existing_condition, portfolio_folds

POLICIES = (
    "baseline_existing_priority",
    "rare_first",
    "rare_last",
    "rare_after_core",
    "rare_after_diversifiers",
    "phase16a_first_only",
    "phase16a_last",
    "rare_low_correlation_first",
    "rare_positive_validation_first",
    "rare_session_cap",
    "rare_only_if_no_prior_trade_in_session",
    "rare_only_if_no_overlap",
)
MODES = ("one_trade_at_a_time_chronological", "max_one_trade_per_session")
MAX_SELECTED_MODULES = 32
CANDIDATE_FOLD_GATE = 0.833
OFFICIAL_GATES_CHANGED = False
PAPER_TRADING_APPROVED = False
LIVE_TRADING_APPROVED = False
DIAGNOSTIC_ONLY_NO_SIGNALS_GENERATED = True
RAW_SUM_DIAGNOSTIC_USED_AS_CANDIDATE = False
REGISTRY_MUTATION = False


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_playbook_scheduler_e_inputs(output_dir: Path) -> dict[str, Any]:
    required: dict[str, Path] = {
        "research_signal_registry_csv": output_dir / "research_signal_registry.csv",
        "research_signal_registry_json": output_dir / "research_signal_registry.json",
        "module_registry_csv": output_dir / "playbook_module_registry.csv",
        "module_registry_json": output_dir / "playbook_module_registry.json",
        "rare_policy": output_dir / "playbook_rare_module_policy.json",
        "rare_audit_rules": output_dir / "playbook_rare_module_portfolio_audit_rules.json",
        "portfolio_e_selection": output_dir / "portfolio_audit_e_signal_selection.csv",
        "portfolio_e_correlation": output_dir / "portfolio_audit_e_signal_correlation.csv",
        "portfolio_e_daily_matrix": output_dir / "portfolio_audit_e_daily_pnl_matrix.csv",
        "portfolio_e_trade_overlap": output_dir / "portfolio_audit_e_trade_overlap_summary.csv",
        "portfolio_e_results": output_dir / "portfolio_audit_e_portfolio_results.csv",
        "portfolio_e_daily": output_dir / "portfolio_audit_e_portfolio_daily_pnl.csv",
        "portfolio_e_folds": output_dir / "portfolio_audit_e_portfolio_walk_forward_folds.csv",
        "portfolio_e_concentration": output_dir / "portfolio_audit_e_portfolio_concentration.csv",
        "portfolio_e_drawdown": output_dir / "portfolio_audit_e_portfolio_drawdown_summary.csv",
        "portfolio_e_incremental": output_dir / "portfolio_audit_e_incremental_contribution.csv",
        "portfolio_e_phase16a_impact": output_dir / "portfolio_audit_e_phase16a_rare_module_impact.csv",
        "portfolio_e_rare_summary": output_dir / "portfolio_audit_e_rare_module_contribution_summary.csv",
        "portfolio_e_weak_summary": output_dir / "portfolio_audit_e_weak_regime_coverage_summary.csv",
        "portfolio_e_recommendation": output_dir / "portfolio_audit_e_next_action_recommendation.json",
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
    }
    for phase in PHASES:
        required[f"{phase}_trades"] = output_dir / f"{phase}_trade_logs.csv"
    missing = [str(path) for path in required.values() if not path.exists()]
    if missing:
        raise FileNotFoundError(f"Missing Playbook Scheduler E input(s): {missing}")
    return {key: _read_json(path) if path.suffix == ".json" else pd.read_csv(path) for key, path in required.items()}


def validate_rare_policy_guardrails(policy: dict[str, Any], rules: dict[str, Any]) -> None:
    bad = []
    for name, obj in (("rare_policy", policy), ("rare_audit_rules", rules)):
        if bool(obj.get("official_gates_changed")):
            bad.append(f"{name}.official_gates_changed")
        if bool(obj.get("paper_trading_approved")):
            bad.append(f"{name}.paper_trading_approved")
        if bool(obj.get("live_trading_approved")):
            bad.append(f"{name}.live_trading_approved")
    if bad:
        raise ValueError(f"Rare-module policy guardrail violation(s): {bad}")


def run_playbook_scheduler_e_rare_module_priority_audit(output_dir: Path) -> dict[str, Any]:
    data = load_playbook_scheduler_e_inputs(output_dir)
    validate_rare_policy_guardrails(data["rare_policy"], data["rare_audit_rules"])
    selected = select_scheduler_e_modules(data)
    selected_keys = selected["signal_key"].astype(str).tolist()
    rare_keys = rare_module_keys(selected)
    phase16a_keys = phase16a_rare_module_keys(selected)
    trades = selected_trade_logs(data, selected_keys)
    daily_matrix = module_daily_matrix_from_trades(trades, selected_keys)
    avg_corr = average_abs_correlation(selected_keys, data["portfolio_e_correlation"], daily_matrix)
    orders = build_scheduler_e_policy_orders(selected, selected_keys, rare_keys, phase16a_keys, avg_corr, data)
    portfolio_e_best = best_portfolio_audit_e_row(data["portfolio_e_results"])
    scheduler_d_best = best_scheduler_d_row(data["scheduler_d_results"])

    result_rows: list[dict[str, Any]] = []
    daily_frames: list[pd.DataFrame] = []
    fold_frames: list[pd.DataFrame] = []
    concentration_rows: list[dict[str, Any]] = []
    overlap_rows: list[dict[str, Any]] = []
    acceptance_rows: list[dict[str, Any]] = []
    rare_impact_rows: list[dict[str, Any]] = []
    weak_rows: list[dict[str, Any]] = []

    for policy in POLICIES:
        order = orders[policy]
        for mode in MODES:
            accepted, rejected, skip_counts = construct_scheduler_e_trades(trades, selected_keys, order, mode, policy, rare_keys, phase16a_keys, selected)
            daily = scheduled_daily_e(accepted, policy, mode)
            folds = scheduler_e_folds(policy, mode, daily)
            metrics = scheduler_e_metrics(policy, mode, selected_keys, rare_keys, phase16a_keys, accepted, rejected, daily, folds, skip_counts, portfolio_e_best, scheduler_d_best, daily_matrix, data)
            result_rows.append(metrics)
            daily_frames.append(daily)
            fold_frames.append(folds)
            concentration_rows.append({k: metrics[k] for k in ("rare_priority_policy", "portfolio_mode", "best_day_concentration", "best_trade_concentration", "top_3_day_concentration", "top_5_trade_concentration")})
            overlap_rows.append(overlap_summary_e(policy, mode, accepted, rejected, skip_counts))
            acceptance_rows.extend(rare_acceptance_rows(policy, mode, selected, order, accepted, rejected, rare_keys, phase16a_keys))
            rare_impact_rows.append(rare_impact_row(policy, mode, accepted, rejected, rare_keys, phase16a_keys, daily_matrix, data))
            weak_rows.append(weak_regime_impact_row(policy, mode, accepted, rare_keys, phase16a_keys, data))

    policy_results = pd.DataFrame(result_rows).sort_values(["rare_priority_policy", "portfolio_mode"]).reset_index(drop=True)
    daily_pnl = _concat(daily_frames)
    folds = _concat(fold_frames)
    concentration_df = pd.DataFrame(concentration_rows).sort_values(["rare_priority_policy", "portfolio_mode"]).reset_index(drop=True)
    overlap_df = pd.DataFrame(overlap_rows).sort_values(["rare_priority_policy", "portfolio_mode"]).reset_index(drop=True)
    acceptance_df = pd.DataFrame(acceptance_rows).sort_values(["rare_priority_policy", "portfolio_mode", "priority_rank", "signal_key"]).reset_index(drop=True)
    rare_impact = pd.DataFrame(rare_impact_rows).sort_values(["rare_priority_policy", "portfolio_mode"]).reset_index(drop=True)
    weak_impact = pd.DataFrame(weak_rows).sort_values(["rare_priority_policy", "portfolio_mode"]).reset_index(drop=True)
    recommendation = make_scheduler_e_recommendation(policy_results, rare_impact, weak_impact)
    return {
        "policy_results": policy_results,
        "daily_pnl": daily_pnl,
        "walk_forward_folds": folds,
        "concentration": concentration_df,
        "overlap_summary": overlap_df,
        "rare_module_acceptance_summary": acceptance_df,
        "rare_module_impact": rare_impact,
        "weak_regime_impact": weak_impact,
        "next_action_recommendation": recommendation,
        "selected_modules": selected,
        "selected_signal_keys": selected_keys,
        "rare_signal_keys": rare_keys,
        "phase16a_rare_signal_keys": phase16a_keys,
        "portfolio_e_best": portfolio_e_best,
        "scheduler_d_best": scheduler_d_best,
        "inputs_loaded": loaded_input_names(),
    }


def select_scheduler_e_modules(data: dict[str, Any], cap: int = MAX_SELECTED_MODULES) -> pd.DataFrame:
    modules = data["module_registry_csv"].copy()
    modules["phase"] = modules["phase"].astype(str)
    modules["candidate_id"] = modules["candidate_id"].astype(str)
    modules["signal_key"] = modules.apply(lambda r: signal_key(r["phase"], r["candidate_id"]), axis=1)
    modules["research_track"] = modules.get("research_track", "").astype(str)
    modules["portfolio_role"] = modules.get("portfolio_role", "").astype(str)
    modules["rare_module_track_enabled"] = modules.get("rare_module_track_enabled", False)
    for col in ("net_pnl", "stress_pnl", "validation_pnl", "holdout_pnl", "walk_forward_stress_pnl", "positive_wf_test_folds_pct", "best_day_concentration", "best_trade_concentration", "average_correlation_to_registry"):
        modules[col] = pd.to_numeric(modules[col], errors="coerce").fillna(0.0) if col in modules else 0.0
    modules["prior_score"] = modules[["net_pnl", "stress_pnl", "validation_pnl", "holdout_pnl", "walk_forward_stress_pnl"]].sum(axis=1)
    rows: list[pd.Series] = []
    seen: set[str] = set()

    def append_row(row: pd.Series, reason: str) -> None:
        key = str(row["signal_key"])
        if key in seen or len(rows) >= cap:
            return
        item = row.copy()
        item["selection_reason_e"] = reason
        rows.append(item)
        seen.add(key)

    for phase in ("phase10b", "phase11a"):
        seg = modules[modules["phase"].eq(phase) & modules["research_track"].eq("parked_research_signal")].sort_values(["prior_score", "net_pnl", "candidate_id"], ascending=[False, False, True])
        if not seg.empty:
            append_row(seg.iloc[0], f"required_top_{phase}_parked_module")
    phase12 = modules[modules["phase"].eq("phase12a")].sort_values(["prior_score", "net_pnl", "candidate_id"], ascending=[False, False, True])
    if not phase12.empty:
        append_row(phase12.iloc[0], "required_phase12a_top_or_fallback_module")
    for phase in ("phase13a", "phase14a", "phase15a"):
        seg = modules[modules["phase"].eq(phase) & modules["portfolio_role"].eq("diversifier_module")].sort_values(["prior_score", "net_pnl", "candidate_id"], ascending=[False, False, True])
        for _, row in seg.iterrows():
            append_row(row, f"required_{phase}_diversifier_module")
    rare = modules[modules.apply(is_rare_module_row, axis=1)].sort_values(["phase", "prior_score", "candidate_id"], ascending=[True, False, True])
    for _, row in rare.iterrows():
        append_row(row, "required_rare_module")
    for reason, keys in (
        ("portfolio_audit_e_best_reconstructed", best_signal_keys(data.get("portfolio_e_results", pd.DataFrame()))),
        ("scheduler_d_best_reconstructed", best_signal_keys(data.get("scheduler_d_results", pd.DataFrame()))),
        ("scheduler_c_best_reconstructed", best_signal_keys(data.get("scheduler_c_results", pd.DataFrame()))),
    ):
        for key in keys:
            match = modules[modules["signal_key"].eq(key)]
            if not match.empty:
                append_row(match.iloc[0], reason)
            if len(rows) >= cap:
                break
    fill = modules[modules["research_track"].isin(["parked_research_signal", "rare_setup_research_signal"])].sort_values(["prior_score", "net_pnl", "candidate_id"], ascending=[False, False, True])
    for _, row in fill.iterrows():
        append_row(row, "registry_fill_under_cap")
        if len(rows) >= cap:
            break
    selected = pd.DataFrame([r.to_dict() for r in rows[:cap]])
    if selected.empty:
        return selected
    selected.insert(0, "selection_rank_e", range(1, len(selected) + 1))
    return selected.reset_index(drop=True)


def is_rare_module_row(row: pd.Series) -> bool:
    track = str(row.get("research_track", ""))
    enabled = str(row.get("rare_module_track_enabled", "")).lower() in {"true", "1", "yes"}
    return track == "rare_setup_research_signal" or enabled


def rare_module_keys(selected: pd.DataFrame) -> list[str]:
    rare = selected[selected.apply(is_rare_module_row, axis=1)].copy()
    return rare["signal_key"].astype(str).tolist()


def phase16a_rare_module_keys(selected: pd.DataFrame) -> list[str]:
    rare = selected[selected.apply(is_rare_module_row, axis=1) & selected["phase"].astype(str).eq("phase16a")]
    return rare.sort_values(["prior_score", "candidate_id"], ascending=[False, True])["signal_key"].astype(str).tolist()


def build_scheduler_e_policy_orders(selected: pd.DataFrame, selected_keys: list[str], rare_keys: list[str], phase16a_keys: list[str], avg_corr: dict[str, float], data: dict[str, Any]) -> dict[str, dict[str, int]]:
    base_keys = baseline_priority_keys(selected_keys, data)
    rare_set = set(rare_keys)
    p16 = set(phase16a_keys)
    meta = selected.set_index("signal_key") if not selected.empty else pd.DataFrame()

    def val(key: str, col: str, default: float = 0.0) -> float:
        try:
            return float(meta.loc[key].get(col, default)) if key in meta.index else default
        except Exception:
            return default

    core = [k for k in base_keys if split_signal_key(k)[0] in {"phase10b", "phase11a", "phase12a"}]
    diversifiers = [k for k in base_keys if split_signal_key(k)[0] in {"phase13a", "phase14a", "phase15a"}]
    rare = [k for k in base_keys if k in rare_set]
    nonrare = [k for k in base_keys if k not in rare_set]
    orders = {
        "baseline_existing_priority": base_keys,
        "rare_first": unique(rare + nonrare),
        "rare_last": unique(nonrare + rare),
        "rare_after_core": unique(core + rare + [k for k in base_keys if k not in set(core + rare)]),
        "rare_after_diversifiers": unique(diversifiers + rare + core + [k for k in base_keys if k not in set(diversifiers + rare + core)]),
        "phase16a_first_only": unique([k for k in base_keys if k in p16] + [k for k in base_keys if k not in p16]),
        "phase16a_last": unique([k for k in base_keys if k not in p16] + [k for k in base_keys if k in p16]),
        "rare_low_correlation_first": unique(sorted(rare, key=lambda k: (avg_corr.get(k, 0.0), k)) + nonrare),
        "rare_positive_validation_first": unique(sorted(rare, key=lambda k: (0 if val(k, "validation_pnl") > 0 and val(k, "holdout_pnl") > 0 and val(k, "walk_forward_stress_pnl") > 0 else 1, val(k, "best_day_concentration", 1.0), -val(k, "net_pnl"), k)) + nonrare),
        "rare_session_cap": base_keys,
        "rare_only_if_no_prior_trade_in_session": base_keys,
        "rare_only_if_no_overlap": base_keys,
    }
    return {name: {key: i for i, key in enumerate(keys)} for name, keys in orders.items()}


def baseline_priority_keys(selected_keys: list[str], data: dict[str, Any]) -> list[str]:
    for frame_name in ("portfolio_e_results", "scheduler_d_results", "scheduler_c_results"):
        keys = best_signal_keys(data.get(frame_name, pd.DataFrame()))
        filtered = [k for k in keys if k in set(selected_keys)]
        if filtered:
            return unique(filtered + selected_keys)
    return list(selected_keys)


def best_signal_keys(results: pd.DataFrame) -> list[str]:
    row = _best_result_row(results)
    return _split_modules(row.get("signal_keys", "")) if row else []


def best_portfolio_audit_e_row(results: pd.DataFrame) -> dict[str, Any]:
    return _best_result_row(results, mode_col="portfolio_mode")


def best_scheduler_d_row(results: pd.DataFrame) -> dict[str, Any]:
    return _best_result_row(results, mode_col="portfolio_mode")


def best_scheduler_e_result(results: pd.DataFrame) -> dict[str, Any]:
    if results.empty:
        return {}
    return results.sort_values(["positive_wf_test_folds_pct", "net_pnl", "best_day_concentration", "best_trade_concentration", "rare_priority_policy", "portfolio_mode"], ascending=[False, False, True, True, True, True]).iloc[0].to_dict()


def _best_result_row(results: pd.DataFrame, mode_col: str = "portfolio_mode") -> dict[str, Any]:
    if not isinstance(results, pd.DataFrame) or results.empty:
        return {}
    seg = results.copy()
    if mode_col in seg:
        non_raw = seg[~seg[mode_col].astype(str).eq("raw_sum_diagnostic")].copy()
        if not non_raw.empty:
            seg = non_raw
    cols = [c for c in ["positive_wf_test_folds_pct", "net_pnl", "best_day_concentration", "best_trade_concentration"] if c in seg]
    ascending = [False, False, True, True][: len(cols)]
    if not cols:
        return seg.iloc[0].to_dict()
    return seg.sort_values(cols, ascending=ascending).iloc[0].to_dict()


def construct_scheduler_e_trades(trades: pd.DataFrame, signal_keys: list[str], order_map: dict[str, int], mode: str, policy: str, rare_keys: list[str], phase16a_keys: list[str], selected: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, int]]:
    seg = trades[trades["signal_key"].isin(signal_keys)].copy()
    empty_rej = pd.DataFrame(columns=list(trades.columns) + ["skip_reason"])
    if seg.empty:
        return seg, empty_rej, {"skipped_overlap_count": 0, "skipped_session_count": 0, "rare_overlap_skipped": 0, "rare_session_skipped": 0}
    seg["scheduler_priority"] = seg["signal_key"].map(order_map).fillna(9999).astype(int)
    seg = seg.sort_values(["entry_time", "scheduler_priority", "candidate_id", "exit_time"]).reset_index(drop=True)
    rare_set = set(rare_keys)
    core_set = set(selected[selected["phase"].astype(str).isin(["phase10b", "phase11a", "phase12a"])]["signal_key"].astype(str))
    accepted: list[pd.Series] = []
    rejected: list[pd.Series] = []
    used_sessions: set[str] = set()
    rare_used_sessions: set[str] = set()
    last_exit = None
    skipped_overlap = skipped_session = rare_overlap_skipped = rare_session_skipped = 0
    for _, row in seg.iterrows():
        session = str(row["trading_session"])
        key = str(row["signal_key"])
        is_rare = key in rare_set
        item = row.copy()
        if policy == "rare_only_if_no_prior_trade_in_session" and is_rare and session in used_sessions:
            item["skip_reason"] = "rare_prior_trade_in_session"
            rejected.append(item)
            skipped_session += 1
            rare_session_skipped += 1
            continue
        if policy == "rare_session_cap" and is_rare and session in rare_used_sessions:
            item["skip_reason"] = "rare_session_cap_used"
            rejected.append(item)
            skipped_session += 1
            rare_session_skipped += 1
            continue
        if mode == "max_one_trade_per_session" and session in used_sessions:
            item["skip_reason"] = "session_already_used"
            rejected.append(item)
            skipped_session += 1
            if is_rare:
                rare_session_skipped += 1
            continue
        if policy in {"rare_only_if_no_overlap", "rare_after_core"} and is_rare:
            accepted_df = pd.DataFrame(accepted)
            overlap_df = accepted_df if policy == "rare_only_if_no_overlap" else accepted_df[accepted_df["signal_key"].isin(core_set)] if not accepted_df.empty else accepted_df
            if overlaps_any(row, overlap_df):
                item["skip_reason"] = "rare_overlaps_already_accepted_trade"
                rejected.append(item)
                skipped_overlap += 1
                rare_overlap_skipped += 1
                continue
        if mode == "one_trade_at_a_time_chronological" and last_exit is not None and row["entry_time"] < last_exit:
            item["skip_reason"] = "overlapping_holding_period"
            rejected.append(item)
            skipped_overlap += 1
            if is_rare:
                rare_overlap_skipped += 1
            continue
        accepted.append(row)
        used_sessions.add(session)
        if is_rare:
            rare_used_sessions.add(session)
        if mode == "one_trade_at_a_time_chronological":
            last_exit = row["exit_time"] if last_exit is None else max(last_exit, row["exit_time"])
    return pd.DataFrame(accepted), pd.DataFrame(rejected), {"skipped_overlap_count": int(skipped_overlap), "skipped_session_count": int(skipped_session), "rare_overlap_skipped": int(rare_overlap_skipped), "rare_session_skipped": int(rare_session_skipped)}


def overlaps_any(row: pd.Series, accepted: pd.DataFrame) -> bool:
    if accepted.empty:
        return False
    return bool(((accepted["entry_time"] < row["exit_time"]) & (accepted["exit_time"] > row["entry_time"])).any())


def scheduled_daily_e(accepted: pd.DataFrame, policy: str, mode: str) -> pd.DataFrame:
    daily = accepted.groupby("trading_session", as_index=False)["net_pnl"].sum().sort_values("trading_session") if not accepted.empty else pd.DataFrame(columns=["trading_session", "net_pnl"])
    daily.insert(0, "portfolio_mode", mode)
    daily.insert(0, "rare_priority_policy", policy)
    return daily[["rare_priority_policy", "portfolio_mode", "trading_session", "net_pnl"]]


def scheduler_e_folds(policy: str, mode: str, daily: pd.DataFrame) -> pd.DataFrame:
    base = daily.copy().rename(columns={"rare_priority_policy": "portfolio_set"})
    base["portfolio_set"] = policy
    folds = portfolio_folds(policy, mode, base[["portfolio_set", "portfolio_mode", "trading_session", "net_pnl"]])
    if folds.empty:
        return pd.DataFrame(columns=["rare_priority_policy", "portfolio_mode", "fold", "net_pnl", "stress_pnl", "active_days"])
    return folds.rename(columns={"portfolio_set": "rare_priority_policy"})[["rare_priority_policy", "portfolio_mode", "fold", "net_pnl", "stress_pnl", "active_days"]]


def scheduler_e_metrics(policy: str, mode: str, selected_keys: list[str], rare_keys: list[str], phase16a_keys: list[str], accepted: pd.DataFrame, rejected: pd.DataFrame, daily: pd.DataFrame, folds: pd.DataFrame, skip_counts: dict[str, int], portfolio_e_best: dict[str, Any], scheduler_d_best: dict[str, Any], daily_matrix: pd.DataFrame, data: dict[str, Any]) -> dict[str, Any]:
    net = round(float(daily["net_pnl"].sum()), 2) if not daily.empty else 0.0
    split = accepted.groupby("split")["net_pnl"].sum().to_dict() if not accepted.empty and "split" in accepted else {}
    validation = round(float(split.get("validation", 0.0)), 2) if split else None
    holdout = round(float(split.get("holdout", 0.0)), 2) if split else None
    wf_test = round(float(folds["net_pnl"].sum()), 2) if not folds.empty else None
    wf_stress = round(float(folds["stress_pnl"].sum()), 2) if not folds.empty else None
    pos_folds = round(safe_divide(int((folds["stress_pnl"] > 0).sum()), len(folds)), 6) if not folds.empty else None
    worst = round(float(folds["stress_pnl"].min()), 2) if not folds.empty else None
    weak_fold_count = int((folds["stress_pnl"] <= 0).sum()) if not folds.empty else 0
    weak_fold_pnl = round(float(folds.loc[folds["stress_pnl"] <= 0, "stress_pnl"].sum()), 2) if not folds.empty else 0.0
    day_conc = concentration(daily["net_pnl"] if not daily.empty else pd.Series(dtype=float))
    trade_conc = concentration(accepted["net_pnl"] if not accepted.empty else pd.Series(dtype=float))
    active_days = int(daily["trading_session"].nunique()) if not daily.empty else 0
    rare = accepted[accepted["signal_key"].isin(rare_keys)] if not accepted.empty else pd.DataFrame()
    phase16a = accepted[accepted["signal_key"].isin(phase16a_keys)] if not accepted.empty else pd.DataFrame()
    weak_hh = help_hurt_by_keys(accepted, rare_keys, data)
    label = scheduler_e_label(net, validation, holdout, wf_stress, pos_folds, day_conc["best"], trade_conc["best"], max_drawdown(daily["net_pnl"] if not daily.empty else pd.Series(dtype=float)), active_days, skip_counts, portfolio_e_best, scheduler_d_best)
    return {
        "rare_priority_policy": policy,
        "portfolio_mode": mode,
        "signals": len(selected_keys),
        "signal_keys": ";".join(selected_keys),
        "net_pnl": net,
        "validation_pnl": validation,
        "holdout_pnl": holdout,
        "walk_forward_test_pnl": wf_test,
        "walk_forward_stress_pnl": wf_stress,
        "positive_wf_test_folds_pct": pos_folds,
        "worst_wf_test_fold": worst,
        "trades": int(len(accepted)),
        "active_days": active_days,
        "trades_per_active_day": round(safe_divide(len(accepted), active_days), 6),
        "max_drawdown": max_drawdown(daily["net_pnl"] if not daily.empty else pd.Series(dtype=float)),
        "best_day_concentration": day_conc["best"],
        "best_trade_concentration": trade_conc["best"],
        "top_3_day_concentration": day_conc["top3"],
        "top_5_trade_concentration": trade_conc["top5"],
        "skipped_overlap_count": int(skip_counts.get("skipped_overlap_count", 0)),
        "skipped_session_count": int(skip_counts.get("skipped_session_count", 0)),
        "rare_trade_count": int(len(rare)),
        "rare_active_days": phase_active_days(rare),
        "rare_net_contribution": phase_net(rare),
        "rare_overlap_skipped": int(skip_counts.get("rare_overlap_skipped", 0)),
        "phase16a_trade_count": int(len(phase16a)),
        "phase16a_net_contribution": phase_net(phase16a),
        "phase16a_active_days": phase_active_days(phase16a),
        "phase16a_days_existing_no_trade": phase_days_existing_condition(phase16a, selected_keys, daily_matrix, "phase16a::", "no_trade"),
        "phase16a_days_existing_negative_pnl": phase_days_existing_condition(phase16a, selected_keys, daily_matrix, "phase16a::", "negative"),
        "weak_fold_count": weak_fold_count,
        "weak_fold_pnl": weak_fold_pnl,
        "weak_regime_days_helped_by_rare": weak_hh["helped"],
        "weak_regime_days_hurt_by_rare": weak_hh["hurt"],
        "improvement_vs_portfolio_audit_e_best": _delta(net, portfolio_e_best.get("net_pnl")),
        "improvement_vs_scheduler_d_best": _delta(net, scheduler_d_best.get("net_pnl")),
        "scheduler_e_label": label,
        "official_gates_changed": False,
        "paper_trading_approved": False,
        "diagnostic_only_no_signals_generated": True,
        "live_trading_approved": False,
        "raw_sum_diagnostic_used_as_candidate": False,
        "registry_mutation": False,
    }


def scheduler_e_label(net: float, validation: float | None, holdout: float | None, wf_stress: float | None, pos_folds: float | None, best_day: float, best_trade: float, drawdown: float, active_days: int, skip_counts: dict[str, int], portfolio_e_best: dict[str, Any], scheduler_d_best: dict[str, Any]) -> str:
    base_fold = _float_or_none(portfolio_e_best.get("positive_wf_test_folds_pct"))
    base_day = _float_or_none(portfolio_e_best.get("best_day_concentration"))
    base_trade = _float_or_none(portfolio_e_best.get("best_trade_concentration"))
    base_dd = _float_or_none(portfolio_e_best.get("max_drawdown"))
    base_active = _float_or_none(portfolio_e_best.get("active_days"))
    if net <= 0 or (base_active is not None and active_days < max(5, int(0.70 * base_active))):
        return "scheduler_e_negative_or_low_activity"
    fold_improves = pos_folds is not None and base_fold is not None and pos_folds > base_fold
    conc_improves = (base_day is not None and best_day < base_day) or (base_trade is not None and best_trade < base_trade)
    dd_improves = base_dd is not None and drawdown > base_dd
    overlap_improves = int(skip_counts.get("rare_overlap_skipped", 0)) > 0 or int(skip_counts.get("skipped_overlap_count", 0)) < int(float(portfolio_e_best.get("skipped_overlap_count", 0) or 0))
    candidate = (
        net > 0
        and (validation is None or validation > 0)
        and (holdout is None or holdout > 0)
        and (wf_stress is None or wf_stress > 0)
        and (pos_folds is None or pos_folds >= CANDIDATE_FOLD_GATE)
        and best_day <= 0.20
        and best_trade <= 0.15
        and (base_dd is None or drawdown >= base_dd)
        and PAPER_TRADING_APPROVED is False
    )
    if candidate:
        return "scheduler_e_candidate_for_rare_scheduler_review_only"
    if fold_improves and conc_improves:
        return "scheduler_e_improves_folds_and_concentration"
    if fold_improves:
        return "scheduler_e_improves_folds_only"
    if conc_improves:
        return "scheduler_e_improves_concentration_only"
    if dd_improves:
        return "scheduler_e_improves_drawdown_only"
    if overlap_improves:
        return "scheduler_e_improves_rare_overlap_only"
    return "scheduler_e_no_improvement"


def overlap_summary_e(policy: str, mode: str, accepted: pd.DataFrame, rejected: pd.DataFrame, skip_counts: dict[str, int]) -> dict[str, Any]:
    return {
        "rare_priority_policy": policy,
        "portfolio_mode": mode,
        "accepted_trades": int(len(accepted)),
        "skipped_overlap_count": int(skip_counts.get("skipped_overlap_count", 0)),
        "skipped_session_count": int(skip_counts.get("skipped_session_count", 0)),
        "rare_overlap_skipped": int(skip_counts.get("rare_overlap_skipped", 0)),
        "rare_session_skipped": int(skip_counts.get("rare_session_skipped", 0)),
        "rejected_positive_trade_count": int((rejected["net_pnl"] > 0).sum()) if not rejected.empty and "net_pnl" in rejected else 0,
        "rejected_positive_pnl": round(float(rejected.loc[rejected["net_pnl"] > 0, "net_pnl"].sum()), 2) if not rejected.empty and "net_pnl" in rejected else 0.0,
        "rejected_negative_trade_count": int((rejected["net_pnl"] < 0).sum()) if not rejected.empty and "net_pnl" in rejected else 0,
        "rejected_negative_pnl": round(float(rejected.loc[rejected["net_pnl"] < 0, "net_pnl"].sum()), 2) if not rejected.empty and "net_pnl" in rejected else 0.0,
    }


def rare_acceptance_rows(policy: str, mode: str, selected: pd.DataFrame, order: dict[str, int], accepted: pd.DataFrame, rejected: pd.DataFrame, rare_keys: list[str], phase16a_keys: list[str]) -> list[dict[str, Any]]:
    acc_counts = accepted.groupby("signal_key").size().to_dict() if not accepted.empty else {}
    acc_pnl = accepted.groupby("signal_key")["net_pnl"].sum().to_dict() if not accepted.empty else {}
    rej_counts = rejected.groupby("signal_key").size().to_dict() if not rejected.empty and "signal_key" in rejected else {}
    rej_reasons = rejected.groupby("signal_key")["skip_reason"].apply(lambda s: ";".join(sorted(set(map(str, s))))).to_dict() if not rejected.empty and "skip_reason" in rejected else {}
    rows = []
    rare_set, p16 = set(rare_keys), set(phase16a_keys)
    for _, row in selected.iterrows():
        key = str(row["signal_key"])
        rows.append({
            "rare_priority_policy": policy,
            "portfolio_mode": mode,
            "priority_rank": int(order.get(key, 9999)),
            "phase": str(row.get("phase", split_signal_key(key)[0])),
            "candidate_id": str(row.get("candidate_id", split_signal_key(key)[1])),
            "signal_key": key,
            "is_rare_module": bool(key in rare_set),
            "is_phase16a_rare_module": bool(key in p16),
            "selection_reason_e": str(row.get("selection_reason_e", "")),
            "accepted_trade_count": int(acc_counts.get(key, 0)),
            "accepted_net_pnl": round(float(acc_pnl.get(key, 0.0)), 2),
            "skipped_trade_count": int(rej_counts.get(key, 0)),
            "skip_reasons": str(rej_reasons.get(key, "")),
        })
    return rows


def rare_impact_row(policy: str, mode: str, accepted: pd.DataFrame, rejected: pd.DataFrame, rare_keys: list[str], phase16a_keys: list[str], daily_matrix: pd.DataFrame, data: dict[str, Any]) -> dict[str, Any]:
    rare = accepted[accepted["signal_key"].isin(rare_keys)] if not accepted.empty else pd.DataFrame()
    nonrare = accepted[~accepted["signal_key"].isin(rare_keys)] if not accepted.empty else pd.DataFrame()
    p16 = accepted[accepted["signal_key"].isin(phase16a_keys)] if not accepted.empty else pd.DataFrame()
    rare_rej = rejected[rejected["signal_key"].isin(rare_keys)] if not rejected.empty and "signal_key" in rejected else pd.DataFrame()
    return {
        "rare_priority_policy": policy,
        "portfolio_mode": mode,
        "rare_trade_count": int(len(rare)),
        "rare_active_days": phase_active_days(rare),
        "rare_net_contribution": phase_net(rare),
        "nonrare_trade_count": int(len(nonrare)),
        "nonrare_active_days": phase_active_days(nonrare),
        "nonrare_net_contribution": phase_net(nonrare),
        "rare_days_added_vs_nonrare": len(set(rare.get("trading_session", pd.Series(dtype=str)).astype(str)) - set(nonrare.get("trading_session", pd.Series(dtype=str)).astype(str))) if not rare.empty else 0,
        "rare_skipped_count": int(len(rare_rej)),
        "rare_overlap_skipped": int((rare_rej.get("skip_reason", pd.Series(dtype=str)).astype(str).str.contains("overlap|holding", case=False, regex=True)).sum()) if not rare_rej.empty else 0,
        "rare_session_skipped": int((rare_rej.get("skip_reason", pd.Series(dtype=str)).astype(str).str.contains("session|prior_trade", case=False, regex=True)).sum()) if not rare_rej.empty else 0,
        "phase16a_trade_count": int(len(p16)),
        "phase16a_active_days": phase_active_days(p16),
        "phase16a_net_contribution": phase_net(p16),
        "phase16a_days_existing_no_trade": phase_days_existing_condition(p16, list(daily_matrix.columns), daily_matrix, "phase16a::", "no_trade"),
        "phase16a_days_existing_negative_pnl": phase_days_existing_condition(p16, list(daily_matrix.columns), daily_matrix, "phase16a::", "negative"),
    }


def weak_regime_impact_row(policy: str, mode: str, accepted: pd.DataFrame, rare_keys: list[str], phase16a_keys: list[str], data: dict[str, Any]) -> dict[str, Any]:
    rare_hh = help_hurt_by_keys(accepted, rare_keys, data)
    p16_hh = help_hurt_by_keys(accepted, phase16a_keys, data)
    weak_days = weak_regime_days(data)
    rare = accepted[accepted["signal_key"].isin(rare_keys) & accepted["trading_session"].astype(str).isin(weak_days)] if not accepted.empty else pd.DataFrame()
    p16 = accepted[accepted["signal_key"].isin(phase16a_keys) & accepted["trading_session"].astype(str).isin(weak_days)] if not accepted.empty else pd.DataFrame()
    return {
        "rare_priority_policy": policy,
        "portfolio_mode": mode,
        "weak_regime_day_count": len(weak_days),
        "rare_weak_regime_trade_count": int(len(rare)),
        "rare_weak_regime_net_pnl": phase_net(rare),
        "weak_regime_days_helped_by_rare": rare_hh["helped"],
        "weak_regime_days_hurt_by_rare": rare_hh["hurt"],
        "phase16a_weak_regime_trade_count": int(len(p16)),
        "phase16a_weak_regime_net_pnl": phase_net(p16),
        "weak_regime_days_helped_by_phase16a": p16_hh["helped"],
        "weak_regime_days_hurt_by_phase16a": p16_hh["hurt"],
    }


def help_hurt_by_keys(accepted: pd.DataFrame, keys: list[str], data: dict[str, Any]) -> dict[str, int]:
    days = weak_regime_days(data)
    if accepted.empty or not keys or not days:
        return {"helped": 0, "hurt": 0}
    seg = accepted[accepted["signal_key"].isin(keys) & accepted["trading_session"].astype(str).isin(days)]
    if seg.empty:
        return {"helped": 0, "hurt": 0}
    daily = seg.groupby("trading_session")["net_pnl"].sum()
    return {"helped": int((daily > 0).sum()), "hurt": int((daily < 0).sum())}


def weak_regime_days(data: dict[str, Any]) -> set[str]:
    weak = data.get("weak_fold_days", pd.DataFrame())
    if isinstance(weak, pd.DataFrame) and "trading_session" in weak:
        return set(weak["trading_session"].astype(str))
    return set()


def make_scheduler_e_recommendation(results: pd.DataFrame, rare_impact: pd.DataFrame, weak_impact: pd.DataFrame) -> dict[str, Any]:
    base = {
        "official_gates_changed": False,
        "paper_trading_approved": False,
        "live_trading_approved": False,
        "diagnostic_only_no_signals_generated": True,
        "raw_sum_diagnostic_used_as_candidate": False,
        "registry_mutation": False,
    }
    best = best_scheduler_e_result(results)
    candidates = results[results["scheduler_e_label"].eq("scheduler_e_candidate_for_rare_scheduler_review_only")]
    folds_conc = bool(results["scheduler_e_label"].isin(["scheduler_e_improves_folds_and_concentration", "scheduler_e_candidate_for_rare_scheduler_review_only"]).any())
    severe_activity_loss = bool((results["active_days"] < results["active_days"].max() * 0.70).all()) if not results.empty else True
    rare_help_activity = bool((rare_impact.get("rare_days_added_vs_nonrare", pd.Series(dtype=float)) > 0).any()) if not rare_impact.empty else False
    overlap_skipped = bool((rare_impact.get("rare_overlap_skipped", pd.Series(dtype=float)) > 0).any()) if not rare_impact.empty else False
    drawdown_bad = bool((results.get("max_drawdown", pd.Series(dtype=float)) < float(best.get("max_drawdown", 0) or 0)).any()) if not results.empty else False
    phase16_help = bool((weak_impact.get("weak_regime_days_helped_by_phase16a", pd.Series(dtype=float)) > weak_impact.get("weak_regime_days_hurt_by_phase16a", pd.Series(dtype=float))).any()) if not weak_impact.empty else False
    any_help = bool(results["scheduler_e_label"].astype(str).str.startswith("scheduler_e_improves").any()) if not results.empty else False
    if not candidates.empty:
        action = "scheduler_e_rare_policy_review_packet_only"
        rationale = "At least one row met rare-scheduler-review-only criteria; paper trading remains false."
    elif folds_conc and not severe_activity_loss:
        action = "playbook_scheduler_f_rare_policy_retest"
        rationale = "A rare-module scheduling rule improved fold/concentration diagnostics without severe activity loss."
    elif rare_help_activity and (overlap_skipped or drawdown_bad):
        action = "park_rare_modules_in_registry_but_exclude_from_scheduler"
        rationale = "Rare modules helped activity but consistently carried overlap/drawdown diagnostic costs."
    elif phase16_help:
        action = "keep_phase16a_rare_modules_as_regime_diversifiers"
        rationale = "Phase 16A rare modules helped more weak-regime days than they hurt."
    elif not phase16_help:
        action = "park_phase16a_rare_modules_until_more_data" if any_help else "phase17a_next_gap_module_scout"
        rationale = "Phase 16A did not show net weak-regime help under Scheduler E priority rules."
    else:
        action = "phase17a_next_gap_module_scout"
        rationale = "No rare scheduling policy produced a useful diagnostic improvement."
    return {**base, "next_action": action, "rationale": rationale, "best_rare_priority_policy": best.get("rare_priority_policy"), "best_portfolio_mode": best.get("portfolio_mode"), "best_scheduler_e_label": best.get("scheduler_e_label"), "best_net_pnl": best.get("net_pnl"), "best_positive_wf_test_folds_pct": best.get("positive_wf_test_folds_pct"), "best_day_concentration": best.get("best_day_concentration"), "best_trade_concentration": best.get("best_trade_concentration"), "rare_scheduler_review_row_count": int(len(candidates)), "rare_modules_help_activity": rare_help_activity, "rare_modules_overlap_or_drawdown_cost": bool(overlap_skipped or drawdown_bad), "phase16a_helps_weak_regimes": phase16_help}


def render_playbook_scheduler_e_report(result: dict[str, Any]) -> str:
    rec = result["next_action_recommendation"]
    best = best_scheduler_e_result(result["policy_results"])
    lines = [
        "# Playbook Scheduler E — Rare Module Priority Audit",
        "",
        RESEARCH_ONLY_GUARDRAIL,
        "",
        "Research-only rare-module scheduler audit using existing local outputs only. No new signals, no strategy searches, no candidate result changes, no official gate changes, no promotions, no paper-trading approval, and no live-trading functionality were added.",
        "",
        "## Summary",
        "",
        f"- Selected modules: `{len(result['selected_signal_keys'])}` (hard cap <= `{MAX_SELECTED_MODULES}`)",
        f"- Rare modules: `{len(result['rare_signal_keys'])}`",
        f"- Phase 16A rare modules: `{len(result['phase16a_rare_signal_keys'])}`",
        f"- Policies tested: `{', '.join(POLICIES)}`",
        f"- Modes tested: `{', '.join(MODES)}`",
        f"- Best Scheduler E result: `{best.get('rare_priority_policy')}` / `{best.get('portfolio_mode')}` net `{float(best.get('net_pnl', 0.0)):.2f}` pos folds `{float(best.get('positive_wf_test_folds_pct') or 0.0):.3f}` day conc `{float(best.get('best_day_concentration') or 0.0):.3f}` trade conc `{float(best.get('best_trade_concentration') or 0.0):.3f}` label `{best.get('scheduler_e_label')}`",
        f"- Next action: `{rec.get('next_action')}`",
        f"- Rationale: {rec.get('rationale')}",
        "- Paper trading approved: `false`",
        "",
        "## Required diagnostics",
        "",
        compare_line(result["policy_results"], "rare_first", "rare_last"),
        compare_line(result["policy_results"], "rare_after_core", "rare_after_diversifiers"),
        compare_line(result["policy_results"], "phase16a_first_only", "phase16a_last"),
        compare_line(result["policy_results"], "rare_session_cap", "baseline_existing_priority"),
        compare_line(result["policy_results"], "rare_only_if_no_prior_trade_in_session", "baseline_existing_priority"),
        "",
        "## Rare module impact",
        "",
        markdown_table(result["rare_module_impact"]),
        "",
        "## Weak-regime impact",
        "",
        markdown_table(result["weak_regime_impact"]),
        "",
        "## Top Scheduler E rows",
        "",
        markdown_table(result["policy_results"].sort_values(["positive_wf_test_folds_pct", "net_pnl", "best_day_concentration"], ascending=[False, False, True]).head(25)),
        "",
        "## Guardrails",
        "",
        "Official gates changed: `false`.",
        "Paper trading approved: `false`.",
        "New strategy signals generated: `false`.",
        "Registry files mutated: `false`.",
        "Live trading approved: `false`.",
        "Raw-sum diagnostic used as scheduler candidate: `false`.",
        "",
    ]
    return "\n".join(lines)


def compare_line(results: pd.DataFrame, a: str, b: str) -> str:
    def best_for(policy: str) -> dict[str, Any]:
        return best_scheduler_e_result(results[results["rare_priority_policy"].eq(policy)])
    ra, rb = best_for(a), best_for(b)
    return f"- `{a}` vs `{b}`: net `{float(ra.get('net_pnl', 0) or 0):.2f}` / `{float(rb.get('net_pnl', 0) or 0):.2f}`, pos folds `{float(ra.get('positive_wf_test_folds_pct', 0) or 0):.3f}` / `{float(rb.get('positive_wf_test_folds_pct', 0) or 0):.3f}`, max DD `{float(ra.get('max_drawdown', 0) or 0):.2f}` / `{float(rb.get('max_drawdown', 0) or 0):.2f}`."


def write_playbook_scheduler_e_outputs(result: dict[str, Any], output_dir: Path, report_path: Path) -> dict[str, Path]:
    ensure_directory(output_dir)
    ensure_directory(report_path.parent)
    mapping = {
        "policy_results": output_dir / "playbook_scheduler_e_policy_results.csv",
        "daily_pnl": output_dir / "playbook_scheduler_e_daily_pnl.csv",
        "walk_forward_folds": output_dir / "playbook_scheduler_e_walk_forward_folds.csv",
        "concentration": output_dir / "playbook_scheduler_e_concentration.csv",
        "overlap_summary": output_dir / "playbook_scheduler_e_overlap_summary.csv",
        "rare_module_acceptance_summary": output_dir / "playbook_scheduler_e_rare_module_acceptance_summary.csv",
        "rare_module_impact": output_dir / "playbook_scheduler_e_rare_module_impact.csv",
        "weak_regime_impact": output_dir / "playbook_scheduler_e_weak_regime_impact.csv",
    }
    paths: dict[str, Path] = {}
    for key, path in mapping.items():
        write_csv_artifact(result[key], path)
        paths[key] = path
    rec_path = output_dir / "playbook_scheduler_e_next_action_recommendation.json"
    write_json_artifact(result["next_action_recommendation"], rec_path)
    report_path.write_text(render_playbook_scheduler_e_report(result), encoding="utf-8")
    paths["recommendation"] = rec_path
    paths["report"] = report_path
    return paths


def markdown_table(df: pd.DataFrame, max_cols: int = 16) -> str:
    if df.empty:
        return "_No rows._"
    show = df.copy().head(80)
    if len(show.columns) > max_cols:
        keep = list(show.columns[:max_cols])
        show = show[keep]
    cols = [str(c) for c in show.columns]
    rows = ["| " + " | ".join(cols) + " |", "| " + " | ".join(["---"] * len(cols)) + " |"]
    for _, row in show.iterrows():
        rows.append("| " + " | ".join(_md_cell(row[c]) for c in show.columns) + " |")
    return "\n".join(rows)


def _md_cell(value: Any) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    text = str(value).replace("\n", " ").replace("|", "\\|")
    return text[:180]


def loaded_input_names() -> list[str]:
    names = [
        "outputs/research_signal_registry.csv",
        "outputs/research_signal_registry.json",
        "outputs/playbook_module_registry.csv",
        "outputs/playbook_module_registry.json",
        "outputs/playbook_rare_module_policy.json",
        "outputs/playbook_rare_module_portfolio_audit_rules.json",
        "outputs/portfolio_audit_e_signal_selection.csv",
        "outputs/portfolio_audit_e_signal_correlation.csv",
        "outputs/portfolio_audit_e_daily_pnl_matrix.csv",
        "outputs/portfolio_audit_e_trade_overlap_summary.csv",
        "outputs/portfolio_audit_e_portfolio_results.csv",
        "outputs/portfolio_audit_e_portfolio_daily_pnl.csv",
        "outputs/portfolio_audit_e_portfolio_walk_forward_folds.csv",
        "outputs/portfolio_audit_e_portfolio_concentration.csv",
        "outputs/portfolio_audit_e_portfolio_drawdown_summary.csv",
        "outputs/portfolio_audit_e_incremental_contribution.csv",
        "outputs/portfolio_audit_e_phase16a_rare_module_impact.csv",
        "outputs/portfolio_audit_e_rare_module_contribution_summary.csv",
        "outputs/portfolio_audit_e_weak_regime_coverage_summary.csv",
        "outputs/portfolio_audit_e_next_action_recommendation.json",
        "outputs/playbook_scheduler_d_overlay_policy_results.csv",
        "outputs/playbook_scheduler_d_daily_pnl.csv",
        "outputs/playbook_scheduler_d_walk_forward_folds.csv",
        "outputs/playbook_scheduler_d_concentration.csv",
        "outputs/playbook_scheduler_d_next_action_recommendation.json",
        "outputs/playbook_scheduler_c_pruning_policy_results.csv",
        "outputs/playbook_scheduler_c_daily_pnl.csv",
        "outputs/playbook_scheduler_c_walk_forward_folds.csv",
        "outputs/playbook_scheduler_c_concentration.csv",
        "outputs/playbook_scheduler_c_next_action_recommendation.json",
        "outputs/weak_fold_regime_audit_b_market_regime_features.csv",
        "outputs/weak_fold_regime_audit_b_weak_fold_days.csv",
        "outputs/weak_fold_regime_audit_b_bad_day_clusters.csv",
        "outputs/weak_fold_regime_audit_b_regime_comparison.csv",
    ]
    return names + [f"outputs/{phase}_trade_logs.csv" for phase in PHASES]


def phase_net(trades: pd.DataFrame) -> float:
    return round(float(trades["net_pnl"].sum()), 2) if not trades.empty and "net_pnl" in trades else 0.0


def phase_active_days(trades: pd.DataFrame) -> int:
    return int(trades["trading_session"].nunique()) if not trades.empty and "trading_session" in trades else 0


def _split_modules(value: Any) -> list[str]:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return []
    return [v for v in str(value).split(";") if v and v.lower() != "nan"]


def _concat(frames: list[pd.DataFrame]) -> pd.DataFrame:
    frames = [f for f in frames if isinstance(f, pd.DataFrame) and not f.empty]
    return pd.concat(frames, ignore_index=True, sort=False) if frames else pd.DataFrame()


def _float_or_none(value: Any) -> float | None:
    try:
        if pd.isna(value):
            return None
        return float(value)
    except Exception:
        return None


def _delta(value: Any, base: Any) -> float | None:
    v = _float_or_none(value)
    b = _float_or_none(base)
    return None if v is None or b is None else round(v - b, 6)
