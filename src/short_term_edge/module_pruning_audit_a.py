from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pandas as pd

from .phase_common import ensure_directory, safe_divide, write_csv_artifact, write_json_artifact
from .portfolio_audit_b import RESEARCH_ONLY_GUARDRAIL, concentration, max_drawdown, signal_key, split_signal_key
from .playbook_scheduler_b_priority_retest import (
    PHASES,
    average_abs_correlation,
    build_priority_policy_orders,
    construct_scheduled_trades,
    markdown_table,
    module_daily_matrix_from_trades,
    scheduler_folds,
    selected_trade_logs,
)

SEED_SUSPECT_MODULE = "phase10b::MNQ_10b_primary_short_midday_breakout_overnight_range_breakout_short_tf15_midday_response_all_ranges_all_gaps_first_touch_only_mt1"
PRUNING_VARIANTS = (
    "no_pruning_baseline",
    "remove_seed_suspect_only",
    "remove_seed_suspect_pair",
    "remove_all_consistently_skipped_modules",
    "remove_harmful_in_weak_folds",
    "remove_high_redundancy_pairs",
    "keep_only_diversifiers_plus_top_core",
    "keep_only_positive_accepted_contributors",
)
PRIORITY_POLICIES = (
    "hybrid_validation_then_correlation",
    "lowest_correlation_first",
    "rare_setup_first",
    "concentration_adjusted_priority",
)
MODES = ("one_trade_at_a_time_chronological", "max_one_trade_per_session")
OFFICIAL_GATES_CHANGED = False
PAPER_TRADING_APPROVED = False
DIAGNOSTIC_ONLY_NO_SIGNALS_GENERATED = True
LIVE_TRADING_APPROVED = False
CANDIDATE_FOLD_GATE = 0.833


def load_module_pruning_audit_a_inputs(output_dir: Path) -> dict[str, Any]:
    required: dict[str, Path] = {
        "playbook_module_registry": output_dir / "playbook_module_registry.csv",
        "research_signal_registry": output_dir / "research_signal_registry.csv",
        "scheduler_b_results": output_dir / "playbook_scheduler_b_priority_policy_results.csv",
        "scheduler_b_daily": output_dir / "playbook_scheduler_b_daily_pnl.csv",
        "scheduler_b_folds": output_dir / "playbook_scheduler_b_walk_forward_folds.csv",
        "scheduler_b_concentration": output_dir / "playbook_scheduler_b_concentration.csv",
        "scheduler_b_overlap": output_dir / "playbook_scheduler_b_overlap_summary.csv",
        "scheduler_b_acceptance": output_dir / "playbook_scheduler_b_module_acceptance_summary.csv",
        "scheduler_b_recommendation": output_dir / "playbook_scheduler_b_next_action_recommendation.json",
        "portfolio_d_selection": output_dir / "portfolio_audit_d_signal_selection.csv",
        "portfolio_d_correlation": output_dir / "portfolio_audit_d_signal_correlation.csv",
        "portfolio_d_daily_matrix": output_dir / "portfolio_audit_d_daily_pnl_matrix.csv",
        "portfolio_d_results": output_dir / "portfolio_audit_d_portfolio_results.csv",
        "portfolio_d_daily": output_dir / "portfolio_audit_d_portfolio_daily_pnl.csv",
        "portfolio_d_folds": output_dir / "portfolio_audit_d_portfolio_walk_forward_folds.csv",
        "portfolio_d_overlap": output_dir / "portfolio_audit_d_trade_overlap_summary.csv",
        "portfolio_d_recommendation": output_dir / "portfolio_audit_d_next_action_recommendation.json",
        "weak_fold_contribution_by_fold": output_dir / "weak_fold_regime_audit_b_module_contribution_by_fold.csv",
        "weak_fold_contribution_by_regime": output_dir / "weak_fold_regime_audit_b_module_contribution_by_regime.csv",
        "weak_fold_overlap_diagnostics": output_dir / "weak_fold_regime_audit_b_overlap_and_scheduler_diagnostics.csv",
        "weak_fold_bad_day_clusters": output_dir / "weak_fold_regime_audit_b_bad_day_clusters.csv",
    }
    for phase in PHASES:
        required[f"{phase}_trades"] = output_dir / f"{phase}_trade_logs.csv"
    missing = [str(p) for p in required.values() if not p.exists()]
    if missing:
        raise FileNotFoundError(f"Missing Module Pruning Audit A input(s): {missing}")
    return {k: _read_json(p) if p.suffix == ".json" else pd.read_csv(p) for k, p in required.items()}


def run_module_pruning_audit_a(output_dir: Path) -> dict[str, Any]:
    data = load_module_pruning_audit_a_inputs(output_dir)
    selected = scheduler_b_best_priority_universe(data["scheduler_b_results"], data["portfolio_d_selection"])
    selected_keys = selected["signal_key"].astype(str).tolist()
    trades = selected_trade_logs(data, selected_keys)
    daily_matrix = module_daily_matrix_from_trades(trades, selected_keys)
    avg_corr = average_abs_correlation(selected_keys, data["portfolio_d_correlation"], daily_matrix)
    max_corr = max_abs_correlation(selected_keys, data["portfolio_d_correlation"], daily_matrix)
    redundancy_pairs = calculate_redundancy_pairs(selected, daily_matrix, data["portfolio_d_correlation"])
    seed_siblings = identify_sibling_duplicate_variants(SEED_SUSPECT_MODULE, selected, daily_matrix, data["portfolio_d_correlation"])

    # Baseline schedule used for accepted/weak-fold contribution diagnostics.
    baseline_row = scheduler_b_best_priority_row(data["scheduler_b_results"])
    baseline_policy = str(baseline_row.get("priority_policy", PRIORITY_POLICIES[0]))
    baseline_mode = str(baseline_row.get("portfolio_mode", MODES[0]))
    base_orders_all = build_priority_policy_orders(selected, selected_keys, avg_corr)
    base_order = base_orders_all.get(baseline_policy, build_priority_policy_orders(selected, selected_keys, avg_corr)[PRIORITY_POLICIES[0]])
    base_accepted, _, _, base_rejected, _ = construct_scheduled_trades(trades, selected_keys, base_order, baseline_mode)
    baseline_daily = scheduled_daily_with_variant(base_accepted, "scheduler_b_best_reference", baseline_policy, baseline_mode)
    baseline_folds = folds_with_variant("scheduler_b_best_reference", baseline_policy, baseline_mode, baseline_daily)

    module_diagnostics = build_module_diagnostics(
        selected=selected,
        selected_keys=selected_keys,
        trades=trades,
        accepted=base_accepted,
        rejected=base_rejected,
        folds=baseline_folds,
        scheduler_b_acceptance=data["scheduler_b_acceptance"],
        scheduler_b_results=data["scheduler_b_results"],
        avg_corr=avg_corr,
        max_corr=max_corr,
        redundancy_pairs=redundancy_pairs,
        seed_siblings=seed_siblings,
        weak_regime=data["weak_fold_contribution_by_regime"],
    )
    variants = build_pruning_variants(selected, selected_keys, module_diagnostics, redundancy_pairs, seed_siblings)
    baseline_metrics = scheduler_b_best_baseline_metrics(data["scheduler_b_results"])

    result_rows: list[dict[str, Any]] = []
    daily_frames: list[pd.DataFrame] = []
    fold_frames: list[pd.DataFrame] = []
    conc_rows: list[dict[str, Any]] = []
    overlap_rows: list[dict[str, Any]] = []
    variant_rows: list[dict[str, Any]] = []

    for variant_name, keep_keys in variants.items():
        removed = [k for k in selected_keys if k not in keep_keys]
        variant_rows.append({"pruning_variant": variant_name, "kept_module_count": len(keep_keys), "removed_module_count": len(removed), "removed_modules": ";".join(removed)})
        if keep_keys:
            sub_selected = selected[selected["signal_key"].isin(keep_keys)].copy().reset_index(drop=True)
            sub_avg = {k: avg_corr.get(k, 0.0) for k in keep_keys}
            orders = build_priority_policy_orders(sub_selected, keep_keys, sub_avg)
        else:
            orders = {p: {} for p in PRIORITY_POLICIES}
        for policy in PRIORITY_POLICIES:
            order = orders.get(policy, {})
            for mode in MODES:
                accepted, skipped_overlap, skipped_session, rejected, _ = construct_scheduled_trades(trades, keep_keys, order, mode)
                daily = scheduled_daily_with_variant(accepted, variant_name, policy, mode)
                folds = folds_with_variant(variant_name, policy, mode, daily)
                metrics = pruning_metrics(variant_name, policy, mode, keep_keys, removed, accepted, rejected, daily, folds, skipped_overlap, skipped_session, baseline_metrics)
                result_rows.append(metrics)
                daily_frames.append(daily)
                fold_frames.append(folds)
                conc_rows.append({k: metrics[k] for k in ("pruning_variant", "priority_policy", "portfolio_mode", "best_day_concentration", "best_trade_concentration", "top_3_day_concentration", "top_5_trade_concentration")})
                overlap_rows.append(overlap_summary(variant_name, policy, mode, accepted, rejected, skipped_overlap, skipped_session))

    portfolio_results = pd.DataFrame(result_rows).sort_values(["pruning_variant", "priority_policy", "portfolio_mode"]).reset_index(drop=True)
    pruning_variants = pd.DataFrame(variant_rows).sort_values("pruning_variant").reset_index(drop=True)
    daily_pnl = _concat(daily_frames)
    folds = _concat(fold_frames)
    concentration_df = pd.DataFrame(conc_rows).sort_values(["pruning_variant", "priority_policy", "portfolio_mode"]).reset_index(drop=True)
    overlap_df = pd.DataFrame(overlap_rows).sort_values(["pruning_variant", "priority_policy", "portfolio_mode"]).reset_index(drop=True)
    recommendation = make_next_action_recommendation(portfolio_results, module_diagnostics, redundancy_pairs, baseline_metrics)
    return {
        "module_diagnostics": module_diagnostics,
        "pruning_variants": pruning_variants,
        "portfolio_results": portfolio_results,
        "daily_pnl": daily_pnl,
        "walk_forward_folds": folds,
        "concentration": concentration_df,
        "overlap_summary": overlap_df,
        "redundancy_pairs": redundancy_pairs,
        "next_action_recommendation": recommendation,
        "selected_modules": selected,
        "selected_signal_keys": selected_keys,
        "seed_suspect_module": SEED_SUSPECT_MODULE,
        "seed_sibling_modules": seed_siblings,
        "inputs_loaded": loaded_input_names(),
    }


def scheduler_b_best_priority_row(results: pd.DataFrame) -> dict[str, Any]:
    seg = results[results["diagnostic_filter"].astype(str).eq("no_filter_baseline")].copy()
    if seg.empty:
        return {}
    return seg.sort_values(["positive_wf_test_folds_pct", "net_pnl", "best_day_concentration", "priority_policy", "portfolio_mode"], ascending=[False, False, True, True, True]).iloc[0].to_dict()


def scheduler_b_best_priority_universe(results: pd.DataFrame, selection: pd.DataFrame) -> pd.DataFrame:
    row = scheduler_b_best_priority_row(results)
    keys = [k for k in str(row.get("signal_keys", "")).split(";") if k]
    selected = selection.copy()
    if "signal_key" not in selected:
        selected["signal_key"] = selected.apply(lambda r: signal_key(str(r["phase"]), str(r["candidate_id"])), axis=1)
    selected["signal_key"] = selected["signal_key"].astype(str)
    selected["phase"] = selected["phase"].astype(str)
    selected["candidate_id"] = selected["candidate_id"].astype(str)
    for col in ("selection_rank", "prior_score", "net_pnl", "validation_pnl", "holdout_pnl", "best_day_concentration", "best_trade_concentration"):
        selected[col] = pd.to_numeric(selected[col], errors="coerce").fillna(0.0) if col in selected else 0.0
    if not keys:
        keys = selected.sort_values(["selection_rank", "prior_score", "signal_key"], ascending=[True, False, True])["signal_key"].tolist()
    rank = {k: i for i, k in enumerate(keys)}
    selected = selected[selected["signal_key"].isin(keys)].copy()
    selected["scheduler_b_best_rank"] = selected["signal_key"].map(rank).fillna(9999).astype(int)
    return selected.sort_values(["scheduler_b_best_rank", "selection_rank", "signal_key"]).reset_index(drop=True)


def identify_seed_suspect(selected_keys: list[str]) -> str:
    if SEED_SUSPECT_MODULE not in set(selected_keys):
        raise ValueError(f"Seed suspect module not present in Scheduler B best universe: {SEED_SUSPECT_MODULE}")
    return SEED_SUSPECT_MODULE


def identify_sibling_duplicate_variants(seed_key: str, selected: pd.DataFrame, daily_matrix: pd.DataFrame, corr: pd.DataFrame) -> list[str]:
    identify_seed_suspect(selected["signal_key"].astype(str).tolist())
    seed_phase, seed_cid = split_signal_key(seed_key)
    seed_norm = duplicate_base(seed_cid)
    siblings: set[str] = {seed_key}
    for _, row in selected.iterrows():
        key = str(row["signal_key"])
        phase, cid = split_signal_key(key)
        if phase == seed_phase and duplicate_base(cid) == seed_norm:
            siblings.add(key)
    pair_corr = pairwise_corr_lookup(corr, daily_matrix)
    for key in selected["signal_key"].astype(str):
        phase, cid = split_signal_key(key)
        if phase == seed_phase and abs(float(pair_corr.get(tuple(sorted((seed_key, key))), 0.0))) >= 0.999:
            siblings.add(key)
    return sorted(siblings)


def duplicate_base(candidate_id: str) -> str:
    text = re.sub(r"_mt\d+", "_mtX", str(candidate_id))
    text = text.replace("all_touches", "TOUCH_VARIANT").replace("first_touch_only", "TOUCH_VARIANT")
    return text


def calculate_redundancy_pairs(selected: pd.DataFrame, daily_matrix: pd.DataFrame, corr: pd.DataFrame) -> pd.DataFrame:
    keys = selected["signal_key"].astype(str).tolist()
    meta = selected.set_index("signal_key")
    lookup = pairwise_corr_lookup(corr, daily_matrix)
    rows = []
    for i, a in enumerate(keys):
        for b in keys[i + 1 :]:
            phase_a, cid_a = split_signal_key(a)
            phase_b, cid_b = split_signal_key(b)
            c = abs(float(lookup.get(tuple(sorted((a, b))), 0.0)))
            paired_duplicate = phase_a == phase_b and duplicate_base(cid_a) == duplicate_base(cid_b)
            high_corr = c >= 0.95
            if not (paired_duplicate or high_corr):
                continue
            rank_a = float(meta.loc[a].get("scheduler_b_best_rank", meta.loc[a].get("selection_rank", 9999)))
            rank_b = float(meta.loc[b].get("scheduler_b_best_rank", meta.loc[b].get("selection_rank", 9999)))
            lower = b if rank_a <= rank_b else a
            rows.append({
                "signal_a": a,
                "signal_b": b,
                "daily_pnl_correlation": round(c, 6),
                "paired_duplicate_variant": bool(paired_duplicate),
                "high_redundancy_pair": bool(high_corr or paired_duplicate),
                "lower_ranked_module": lower,
                "dedupe_reason": "paired_duplicate_variant" if paired_duplicate else "high_daily_pnl_correlation",
            })
    return pd.DataFrame(rows).sort_values(["daily_pnl_correlation", "signal_a", "signal_b"], ascending=[False, True, True]).reset_index(drop=True) if rows else pd.DataFrame(columns=["signal_a", "signal_b", "daily_pnl_correlation", "paired_duplicate_variant", "high_redundancy_pair", "lower_ranked_module", "dedupe_reason"])


def pairwise_corr_lookup(corr: pd.DataFrame, daily_matrix: pd.DataFrame) -> dict[tuple[str, str], float]:
    out: dict[tuple[str, str], float] = {}
    if not corr.empty and {"signal_a", "signal_b", "daily_pnl_correlation"}.issubset(corr.columns):
        for _, r in corr.iterrows():
            out[tuple(sorted((str(r["signal_a"]), str(r["signal_b"]))))] = float(pd.to_numeric(r["daily_pnl_correlation"], errors="coerce") or 0.0)
    cols = [c for c in daily_matrix.columns if c != "trading_session"] if not daily_matrix.empty else []
    if cols:
        cm = daily_matrix[cols].corr().fillna(0.0)
        for a in cols:
            for b in cols:
                out.setdefault(tuple(sorted((a, b))), float(cm.loc[a, b]))
    return out


def max_abs_correlation(selected_keys: list[str], corr: pd.DataFrame, daily_matrix: pd.DataFrame) -> dict[str, float]:
    lookup = pairwise_corr_lookup(corr, daily_matrix)
    out = {k: 0.0 for k in selected_keys}
    for k in selected_keys:
        vals = [abs(v) for pair, v in lookup.items() if k in pair and pair[0] != pair[1] and all(p in selected_keys for p in pair)]
        out[k] = round(max(vals), 6) if vals else 0.0
    return out


def build_module_diagnostics(selected: pd.DataFrame, selected_keys: list[str], trades: pd.DataFrame, accepted: pd.DataFrame, rejected: pd.DataFrame, folds: pd.DataFrame, scheduler_b_acceptance: pd.DataFrame, scheduler_b_results: pd.DataFrame, avg_corr: dict[str, float], max_corr: dict[str, float], redundancy_pairs: pd.DataFrame, seed_siblings: list[str], weak_regime: pd.DataFrame) -> pd.DataFrame:
    fold_map = session_to_fold_map(accepted, folds)
    accepted = accepted.copy()
    if not accepted.empty:
        accepted["fold"] = accepted["trading_session"].astype(str).map(fold_map)
        weak_folds = set(folds.loc[pd.to_numeric(folds.get("stress_pnl"), errors="coerce") <= 0, "fold"].astype(int)) if not folds.empty else set()
        accepted["is_weak_fold"] = accepted["fold"].isin(weak_folds)
    acc_counts = accepted.groupby("signal_key").size().to_dict() if not accepted.empty else {}
    acc_pnl = accepted.groupby("signal_key")["net_pnl"].sum().to_dict() if not accepted.empty else {}
    weak_pnl = accepted[accepted.get("is_weak_fold", False)].groupby("signal_key")["net_pnl"].sum().to_dict() if not accepted.empty and "is_weak_fold" in accepted else {}
    strong_pnl = accepted[~accepted.get("is_weak_fold", False)].groupby("signal_key")["net_pnl"].sum().to_dict() if not accepted.empty and "is_weak_fold" in accepted else {}
    rej_by_reason = rejected.groupby(["signal_key", "skip_reason"]).size().to_dict() if not rejected.empty and "skip_reason" in rejected else {}
    all_trade_counts = trades.groupby("signal_key").size().to_dict() if not trades.empty else {}
    module_net_sched = scheduler_b_acceptance[(scheduler_b_acceptance["diagnostic_filter"].astype(str).eq("no_filter_baseline"))].groupby("signal_key")["accepted_net_pnl"].sum().to_dict() if not scheduler_b_acceptance.empty else {}
    acceptance_agg = scheduler_b_acceptance[scheduler_b_acceptance["diagnostic_filter"].astype(str).eq("no_filter_baseline")].groupby("signal_key").agg(accepted=("accepted_trade_count", "sum"), skipped=("skipped_trade_count", "sum"), accepted_pnl=("accepted_net_pnl", "sum")) if not scheduler_b_acceptance.empty else pd.DataFrame()
    redundant = set(redundancy_pairs["signal_a"].astype(str)).union(set(redundancy_pairs["signal_b"].astype(str))) if not redundancy_pairs.empty else set()
    lower_ranked = set(redundancy_pairs["lower_ranked_module"].astype(str)) if not redundancy_pairs.empty else set()
    high_vol_mixed = weak_high_vol_mixed_contribution_by_phase(weak_regime)
    rows = []
    for _, r in selected.iterrows():
        key = str(r["signal_key"])
        phase = str(r.get("phase", split_signal_key(key)[0]))
        accepted_count = int(acc_counts.get(key, 0))
        all_count = int(all_trade_counts.get(key, 0))
        sched = acceptance_agg.loc[key].to_dict() if key in acceptance_agg.index else {"accepted": accepted_count, "skipped": 0, "accepted_pnl": acc_pnl.get(key, 0.0)}
        sched_accept = int(sched.get("accepted", 0))
        sched_skip = int(sched.get("skipped", 0))
        skipped_overlap = int(rej_by_reason.get((key, "overlapping_holding_period"), 0))
        skipped_session = int(rej_by_reason.get((key, "session_already_used"), 0))
        skip_rate = safe_divide(sched_skip, sched_skip + sched_accept)
        accepted_net = round(float(acc_pnl.get(key, 0.0)), 2)
        rows.append({
            "signal_key": key,
            "phase": phase,
            "candidate_id": str(r.get("candidate_id", split_signal_key(key)[1])),
            "scheduler_b_net_contribution": round(float(module_net_sched.get(key, 0.0)), 2),
            "accepted_trade_count": accepted_count,
            "all_trade_count": all_count,
            "skipped_overlap_count": skipped_overlap,
            "skipped_session_count": skipped_session,
            "scheduler_b_accepted_trade_count": sched_accept,
            "scheduler_b_skipped_trade_count": sched_skip,
            "scheduler_b_skip_rate": round(skip_rate, 6),
            "accepted_net_pnl": accepted_net,
            "contribution_in_weak_folds": round(float(weak_pnl.get(key, 0.0)), 2),
            "contribution_in_strong_folds": round(float(strong_pnl.get(key, 0.0)), 2),
            "contribution_on_high_vol_mixed_weak_regime_days": high_vol_mixed.get(phase),
            "average_daily_correlation_to_other_modules": round(float(avg_corr.get(key, 0.0)), 6),
            "max_daily_correlation_to_other_modules": round(float(max_corr.get(key, 0.0)), 6),
            "overlap_rate_with_other_modules": round(safe_divide(skipped_overlap + skipped_session, max(all_count, 1)), 6),
            "consistently_skipped": bool(skip_rate >= 0.80 and sched_skip >= max(3, sched_accept)),
            "harmful_when_accepted": bool(accepted_count > 0 and accepted_net < 0),
            "redundant_with_another_module": bool(key in redundant),
            "paired_duplicate_variant": bool(key in seed_siblings or key in lower_ranked),
            "seed_suspect": bool(key == SEED_SUSPECT_MODULE),
        })
    return pd.DataFrame(rows).sort_values(["seed_suspect", "harmful_when_accepted", "consistently_skipped", "signal_key"], ascending=[False, False, False, True]).reset_index(drop=True)


def weak_high_vol_mixed_contribution_by_phase(weak_regime: pd.DataFrame) -> dict[str, float | None]:
    if weak_regime.empty or "regime" not in weak_regime:
        return {}
    seg = weak_regime[weak_regime["regime"].astype(str).str.contains("high_vol", case=False, na=False) & weak_regime["regime"].astype(str).str.contains("mixed", case=False, na=False)]
    if seg.empty:
        seg = weak_regime[weak_regime["regime"].astype(str).eq("weak_folds")]
    if seg.empty or "phase" not in seg or "net_pnl_contribution" not in seg:
        return {}
    return {str(k): round(float(v), 2) for k, v in seg.groupby("phase")["net_pnl_contribution"].sum().items()}


def session_to_fold_map(accepted: pd.DataFrame, folds: pd.DataFrame) -> dict[str, int]:
    # Reconstruct deterministic chronological fold buckets from accepted sessions and fold active-day counts.
    if accepted.empty or folds.empty or "active_days" not in folds:
        return {}
    sessions = sorted(accepted["trading_session"].astype(str).unique())
    out: dict[str, int] = {}
    cursor = 0
    for _, row in folds.sort_values("fold").iterrows():
        fold = int(row["fold"])
        count = int(row.get("active_days", 0) or 0)
        for session in sessions[cursor : cursor + count]:
            out[session] = fold
        cursor += count
    return out


def build_pruning_variants(selected: pd.DataFrame, selected_keys: list[str], diagnostics: pd.DataFrame, redundancy_pairs: pd.DataFrame, seed_siblings: list[str]) -> dict[str, list[str]]:
    identify_seed_suspect(selected_keys)
    all_keys = list(selected_keys)
    remove_consistently = set(diagnostics.loc[(diagnostics["consistently_skipped"]) & (diagnostics["scheduler_b_net_contribution"] <= 0), "signal_key"].astype(str))
    remove_weak = set(diagnostics.loc[pd.to_numeric(diagnostics["contribution_in_weak_folds"], errors="coerce") < 0, "signal_key"].astype(str))
    remove_redundant = set(redundancy_pairs["lower_ranked_module"].astype(str)) if not redundancy_pairs.empty else set()
    diversifiers = set(selected.loc[selected["phase"].astype(str).isin(["phase13a", "phase14a", "phase15a"]), "signal_key"].astype(str))
    core = selected[selected["phase"].astype(str).isin(["phase10b", "phase11a", "phase12a"])].copy()
    core["core_score"] = pd.to_numeric(core.get("prior_score", core.get("net_pnl", 0)), errors="coerce").fillna(0.0)
    top_core = set(core.sort_values(["phase", "core_score", "scheduler_b_best_rank", "signal_key"], ascending=[True, False, True, True]).groupby("phase").head(1)["signal_key"].astype(str)) if not core.empty else set()
    positive = set(diagnostics.loc[pd.to_numeric(diagnostics["accepted_net_pnl"], errors="coerce") > 0, "signal_key"].astype(str))
    variants = {
        "no_pruning_baseline": all_keys,
        "remove_seed_suspect_only": [k for k in all_keys if k != SEED_SUSPECT_MODULE],
        "remove_seed_suspect_pair": [k for k in all_keys if k not in set(seed_siblings)],
        "remove_all_consistently_skipped_modules": [k for k in all_keys if k not in remove_consistently],
        "remove_harmful_in_weak_folds": [k for k in all_keys if k not in remove_weak],
        "remove_high_redundancy_pairs": [k for k in all_keys if k not in remove_redundant],
        "keep_only_diversifiers_plus_top_core": [k for k in all_keys if k in diversifiers.union(top_core)],
        "keep_only_positive_accepted_contributors": [k for k in all_keys if k in positive],
    }
    return {name: keys for name, keys in variants.items()}


def scheduled_daily_with_variant(accepted: pd.DataFrame, variant: str, policy: str, mode: str) -> pd.DataFrame:
    daily = accepted.groupby("trading_session", as_index=False)["net_pnl"].sum().sort_values("trading_session") if not accepted.empty else pd.DataFrame(columns=["trading_session", "net_pnl"])
    daily.insert(0, "portfolio_mode", mode)
    daily.insert(0, "priority_policy", policy)
    daily.insert(0, "pruning_variant", variant)
    return daily[["pruning_variant", "priority_policy", "portfolio_mode", "trading_session", "net_pnl"]]


def folds_with_variant(variant: str, policy: str, mode: str, daily: pd.DataFrame) -> pd.DataFrame:
    base = daily.rename(columns={"pruning_variant": "portfolio_set"}).copy()
    base["portfolio_set"] = f"{variant}::{policy}"
    folds = scheduler_folds(policy, mode, "no_filter_baseline", base[["portfolio_set", "portfolio_mode", "trading_session", "net_pnl"]].rename(columns={"portfolio_set": "priority_policy"}))
    if folds.empty:
        return pd.DataFrame(columns=["pruning_variant", "priority_policy", "portfolio_mode", "fold", "net_pnl", "stress_pnl", "active_days"])
    folds["pruning_variant"] = variant
    folds["priority_policy"] = policy
    return folds[["pruning_variant", "priority_policy", "portfolio_mode", "fold", "net_pnl", "stress_pnl", "active_days"]]


def pruning_metrics(variant: str, policy: str, mode: str, keep_keys: list[str], removed: list[str], accepted: pd.DataFrame, rejected: pd.DataFrame, daily: pd.DataFrame, folds: pd.DataFrame, skipped_overlap: int, skipped_session: int, baseline: dict[str, Any]) -> dict[str, Any]:
    net = round(float(daily["net_pnl"].sum()), 2) if not daily.empty else 0.0
    split = accepted.groupby("split")["net_pnl"].sum().to_dict() if not accepted.empty and "split" in accepted else {}
    validation = round(float(split.get("validation", 0.0)), 2) if split else None
    holdout = round(float(split.get("holdout", 0.0)), 2) if split else None
    wf_test = round(float(folds["net_pnl"].sum()), 2) if not folds.empty else None
    wf_stress = round(float(folds["stress_pnl"].sum()), 2) if not folds.empty else None
    pos_folds = round(safe_divide(int((folds["stress_pnl"] > 0).sum()), len(folds)), 6) if not folds.empty else None
    worst = round(float(folds["stress_pnl"].min()), 2) if not folds.empty else None
    weak_count = int((folds["stress_pnl"] <= 0).sum()) if not folds.empty else 0
    weak_pnl = round(float(folds.loc[folds["stress_pnl"] <= 0, "stress_pnl"].sum()), 2) if not folds.empty else 0.0
    day_conc = concentration(daily["net_pnl"] if not daily.empty else pd.Series(dtype=float))
    trade_conc = concentration(accepted["net_pnl"] if not accepted.empty else pd.Series(dtype=float))
    active_days = int(daily["trading_session"].nunique()) if not daily.empty else 0
    label = pruning_label(net, validation, holdout, wf_stress, pos_folds, day_conc["best"], trade_conc["best"], active_days, baseline)
    return {
        "pruning_variant": variant,
        "priority_policy": policy,
        "portfolio_mode": mode,
        "signals": len(keep_keys),
        "signal_keys": ";".join(keep_keys),
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
        "skipped_overlap_count": int(skipped_overlap),
        "skipped_session_count": int(skipped_session),
        "weak_fold_count": weak_count,
        "weak_fold_pnl": weak_pnl,
        "improvement_vs_scheduler_b_best": _delta(net, baseline.get("net_pnl")),
        "positive_wf_test_folds_delta_vs_scheduler_b_best": _delta(pos_folds, baseline.get("positive_wf_test_folds_pct")),
        "best_day_concentration_delta_vs_scheduler_b_best": _delta(day_conc["best"], baseline.get("best_day_concentration")),
        "best_trade_concentration_delta_vs_scheduler_b_best": _delta(trade_conc["best"], baseline.get("best_trade_concentration")),
        "removed_module_count": len(removed),
        "removed_modules": ";".join(removed),
        "pruning_a_label": label,
        "official_gates_changed": False,
        "paper_trading_approved": False,
        "diagnostic_only_no_signals_generated": True,
        "live_trading_approved": False,
        "raw_sum_diagnostic_used_as_candidate": False,
    }


def pruning_label(net: float, validation: float | None, holdout: float | None, wf_stress: float | None, pos_folds: float | None, best_day: float, best_trade: float, active_days: int, baseline: dict[str, Any]) -> str:
    if net <= 0 or active_days < 5:
        return "pruning_a_negative_or_low_activity"
    fold_improves = (pos_folds is not None and _float_or_none(baseline.get("positive_wf_test_folds_pct")) is not None and pos_folds > float(baseline["positive_wf_test_folds_pct"]))
    conc_improves = (best_day < float(baseline.get("best_day_concentration", 1.0)) and best_trade < float(baseline.get("best_trade_concentration", 1.0)))
    candidate = net > 0 and (validation is None or validation > 0) and (holdout is None or holdout > 0) and (wf_stress is None or wf_stress > 0) and (pos_folds is None or pos_folds >= CANDIDATE_FOLD_GATE) and conc_improves
    if candidate:
        return "pruning_a_candidate_for_scheduler_review_only"
    if fold_improves and conc_improves:
        return "pruning_a_improves_folds_and_concentration"
    if fold_improves:
        return "pruning_a_improves_folds_only"
    if conc_improves:
        return "pruning_a_improves_concentration_only"
    return "pruning_a_no_improvement"


def overlap_summary(variant: str, policy: str, mode: str, accepted: pd.DataFrame, rejected: pd.DataFrame, skipped_overlap: int, skipped_session: int) -> dict[str, Any]:
    return {
        "pruning_variant": variant,
        "priority_policy": policy,
        "portfolio_mode": mode,
        "accepted_trades": int(len(accepted)),
        "skipped_overlap_count": int(skipped_overlap),
        "skipped_session_count": int(skipped_session),
        "rejected_positive_trade_count": int((rejected["net_pnl"] > 0).sum()) if not rejected.empty and "net_pnl" in rejected else 0,
        "rejected_positive_pnl": round(float(rejected.loc[rejected["net_pnl"] > 0, "net_pnl"].sum()), 2) if not rejected.empty and "net_pnl" in rejected else 0.0,
        "rejected_negative_trade_count": int((rejected["net_pnl"] < 0).sum()) if not rejected.empty and "net_pnl" in rejected else 0,
        "rejected_negative_pnl": round(float(rejected.loc[rejected["net_pnl"] < 0, "net_pnl"].sum()), 2) if not rejected.empty and "net_pnl" in rejected else 0.0,
    }


def scheduler_b_best_baseline_metrics(results: pd.DataFrame) -> dict[str, Any]:
    return scheduler_b_best_priority_row(results)


def make_next_action_recommendation(results: pd.DataFrame, diagnostics: pd.DataFrame, redundancy_pairs: pd.DataFrame, baseline: dict[str, Any]) -> dict[str, Any]:
    non_base = results[~results["pruning_variant"].eq("no_pruning_baseline")].copy()
    fold_and_conc = non_base[non_base["pruning_a_label"].eq("pruning_a_improves_folds_and_concentration") | non_base["pruning_a_label"].eq("pruning_a_candidate_for_scheduler_review_only")]
    seed_only = non_base[non_base["pruning_variant"].eq("remove_seed_suspect_only")]
    seed_helps = bool((seed_only["pruning_a_label"].isin(["pruning_a_improves_folds_only", "pruning_a_improves_folds_and_concentration", "pruning_a_candidate_for_scheduler_review_only"])).any())
    harmful_group = bool((pd.to_numeric(diagnostics["contribution_in_weak_folds"], errors="coerce") < 0).any())
    redundancy_main = bool(not redundancy_pairs.empty and (non_base[non_base["pruning_variant"].eq("remove_high_redundancy_pairs")]["pruning_a_label"].str.contains("improves|candidate", regex=True)).any())
    if not fold_and_conc.empty:
        action = "playbook_scheduler_c_pruning_retest"
        rationale = "At least one diagnostic pruning variant improved both fold stability and concentration versus Scheduler B best."
    elif seed_helps:
        action = "mark_seed_module_for_deprioritization_review"
        rationale = "Only removing the seed suspect showed a fold-stability improvement in diagnostic retests."
    elif harmful_group:
        action = "module_pruning_b_group_review"
        rationale = "At least one module showed negative accepted contribution in weak folds; review is diagnostic-only."
    elif redundancy_main:
        action = "playbook_module_deduplication_audit"
        rationale = "High-redundancy pair removal was the main diagnostic improvement path."
    else:
        action = "phase16a_targeted_regime_module_scout"
        rationale = "Diagnostic pruning did not improve fold stability and concentration versus Scheduler B best."
    best = best_pruning_result(results)
    return {
        "next_action": action,
        "rationale": rationale,
        "best_pruning_variant": best.get("pruning_variant"),
        "best_priority_policy": best.get("priority_policy"),
        "best_portfolio_mode": best.get("portfolio_mode"),
        "best_pruning_label": best.get("pruning_a_label"),
        "folds_improved_vs_scheduler_b_best": bool((_float_or_none(best.get("positive_wf_test_folds_delta_vs_scheduler_b_best")) or 0.0) > 0),
        "concentration_improved_vs_scheduler_b_best": bool(((_float_or_none(best.get("best_day_concentration_delta_vs_scheduler_b_best")) or 0.0) < 0) and ((_float_or_none(best.get("best_trade_concentration_delta_vs_scheduler_b_best")) or 0.0) < 0)),
        "seed_suspect_module": SEED_SUSPECT_MODULE,
        "official_gates_changed": False,
        "paper_trading_approved": False,
        "diagnostic_only_no_signals_generated": True,
        "live_trading_approved": False,
        "raw_sum_diagnostic_used_as_candidate": False,
        "registry_files_mutated": False,
    }


def best_pruning_result(results: pd.DataFrame) -> dict[str, Any]:
    if results.empty:
        return {}
    return results.sort_values(["positive_wf_test_folds_pct", "net_pnl", "best_day_concentration", "pruning_variant", "priority_policy"], ascending=[False, False, True, True, True]).iloc[0].to_dict()


def render_module_pruning_audit_a_report(result: dict[str, Any]) -> str:
    rec = result["next_action_recommendation"]
    best = best_pruning_result(result["portfolio_results"])
    lines = [
        "# Module Pruning Audit A — Harmful / Redundant Module Diagnostic",
        "",
        RESEARCH_ONLY_GUARDRAIL,
        "",
        "Research-only diagnostic audit using existing Scheduler B, Portfolio Audit D, Weak Fold Audit B, registries, and existing module trade logs only. No new signals, no strategy searches, no candidate-result changes, no registry removals, no official gate changes, no promotions, no paper-trading approval, and no live-trading functionality were added.",
        "",
        "## Summary",
        "",
        f"- Seed suspect: `{result['seed_suspect_module']}`",
        f"- Seed sibling/duplicate variants: `{';'.join(result['seed_sibling_modules'])}`",
        f"- Selected Scheduler B best universe modules: `{len(result['selected_signal_keys'])}`",
        f"- Pruning variants tested: `{', '.join(PRUNING_VARIANTS)}`",
        f"- Priority policies tested: `{', '.join(PRIORITY_POLICIES)}`",
        f"- Modes tested: `{', '.join(MODES)}`",
        f"- Best pruning result: `{best.get('pruning_variant')}` / `{best.get('priority_policy')}` / `{best.get('portfolio_mode')}` net `{float(best.get('net_pnl', 0.0)):.2f}` pos folds `{float(best.get('positive_wf_test_folds_pct') or 0.0):.3f}` day conc `{float(best.get('best_day_concentration') or 0.0):.3f}` trade conc `{float(best.get('best_trade_concentration') or 0.0):.3f}` label `{best.get('pruning_a_label')}`",
        f"- Next action: `{rec['next_action']}`",
        f"- Rationale: {rec['rationale']}",
        "- Paper trading approved: `false`",
        "",
        "## Top pruning rows",
        "",
        markdown_table(result["portfolio_results"].sort_values(["positive_wf_test_folds_pct", "net_pnl", "best_day_concentration"], ascending=[False, False, True]).head(25)),
        "",
        "## Module diagnostics",
        "",
        markdown_table(result["module_diagnostics"].head(40)),
        "",
        "## Redundancy pairs",
        "",
        markdown_table(result["redundancy_pairs"].head(40)),
        "",
        "## Guardrails",
        "",
        "Official gates changed: `false`.",
        "Paper trading approved: `false`.",
        "New strategy signals generated: `false`.",
        "Registry modules removed: `false`.",
        "Live trading approved: `false`.",
        "Raw-sum diagnostic used as candidate mode: `false`.",
        "",
    ]
    return "\n".join(lines)


def write_module_pruning_audit_a_outputs(result: dict[str, Any], output_dir: Path, report_path: Path) -> dict[str, Path]:
    ensure_directory(output_dir)
    ensure_directory(report_path.parent)
    mapping = {
        "module_diagnostics": output_dir / "module_pruning_audit_a_module_diagnostics.csv",
        "pruning_variants": output_dir / "module_pruning_audit_a_pruning_variants.csv",
        "portfolio_results": output_dir / "module_pruning_audit_a_portfolio_results.csv",
        "daily_pnl": output_dir / "module_pruning_audit_a_daily_pnl.csv",
        "walk_forward_folds": output_dir / "module_pruning_audit_a_walk_forward_folds.csv",
        "concentration": output_dir / "module_pruning_audit_a_concentration.csv",
        "overlap_summary": output_dir / "module_pruning_audit_a_overlap_summary.csv",
        "redundancy_pairs": output_dir / "module_pruning_audit_a_redundancy_pairs.csv",
    }
    paths: dict[str, Path] = {}
    for key, path in mapping.items():
        write_csv_artifact(result[key], path)
        paths[key] = path
    rec_path = output_dir / "module_pruning_audit_a_next_action_recommendation.json"
    write_json_artifact(result["next_action_recommendation"], rec_path)
    report_path.write_text(render_module_pruning_audit_a_report(result), encoding="utf-8")
    paths["recommendation"] = rec_path
    paths["report"] = report_path
    return paths


def loaded_input_names() -> list[str]:
    return [
        "outputs/playbook_module_registry.csv",
        "outputs/research_signal_registry.csv",
        "outputs/playbook_scheduler_b_priority_policy_results.csv",
        "outputs/playbook_scheduler_b_daily_pnl.csv",
        "outputs/playbook_scheduler_b_walk_forward_folds.csv",
        "outputs/playbook_scheduler_b_concentration.csv",
        "outputs/playbook_scheduler_b_overlap_summary.csv",
        "outputs/playbook_scheduler_b_module_acceptance_summary.csv",
        "outputs/playbook_scheduler_b_next_action_recommendation.json",
        "outputs/portfolio_audit_d_signal_selection.csv",
        "outputs/portfolio_audit_d_signal_correlation.csv",
        "outputs/portfolio_audit_d_daily_pnl_matrix.csv",
        "outputs/portfolio_audit_d_portfolio_results.csv",
        "outputs/portfolio_audit_d_portfolio_daily_pnl.csv",
        "outputs/portfolio_audit_d_portfolio_walk_forward_folds.csv",
        "outputs/portfolio_audit_d_trade_overlap_summary.csv",
        "outputs/portfolio_audit_d_next_action_recommendation.json",
        "outputs/weak_fold_regime_audit_b_module_contribution_by_fold.csv",
        "outputs/weak_fold_regime_audit_b_module_contribution_by_regime.csv",
        "outputs/weak_fold_regime_audit_b_overlap_and_scheduler_diagnostics.csv",
        "outputs/weak_fold_regime_audit_b_bad_day_clusters.csv",
        *[f"outputs/{phase}_trade_logs.csv" for phase in PHASES],
    ]


def _concat(frames: list[pd.DataFrame]) -> pd.DataFrame:
    frames = [f for f in frames if isinstance(f, pd.DataFrame) and not f.empty]
    return pd.concat(frames, ignore_index=True, sort=False) if frames else pd.DataFrame()


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


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
