from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from .module_pruning_audit_a import (
    SEED_SUSPECT_MODULE,
    calculate_redundancy_pairs,
    identify_seed_suspect,
    identify_sibling_duplicate_variants,
    max_abs_correlation,
    scheduled_daily_with_variant,
    folds_with_variant,
    overlap_summary,
    scheduler_b_best_priority_universe,
    scheduler_b_best_priority_row,
)
from .phase_common import ensure_directory, safe_divide, write_csv_artifact, write_json_artifact
from .playbook_scheduler_b_priority_retest import (
    PHASES,
    average_abs_correlation,
    build_priority_policy_orders,
    construct_scheduled_trades,
    markdown_table,
    module_daily_matrix_from_trades,
    selected_trade_logs,
)
from .portfolio_audit_b import RESEARCH_ONLY_GUARDRAIL, concentration, max_drawdown, split_signal_key

PRUNING_VARIANTS = (
    "no_pruning_baseline",
    "remove_seed_suspect_only",
    "remove_seed_suspect_cluster",
    "remove_high_redundancy_pairs",
    "deprioritize_seed_cluster",
    "keep_only_deduped_representatives",
)
PRIORITY_POLICIES = (
    "concentration_adjusted_priority",
    "hybrid_validation_then_correlation",
    "lowest_correlation_first",
    "rare_setup_first",
)
MODES = ("one_trade_at_a_time_chronological", "max_one_trade_per_session")
MAX_SELECTED_MODULES = 28
CANDIDATE_FOLD_GATE = 0.833
OFFICIAL_GATES_CHANGED = False
PAPER_TRADING_APPROVED = False
DIAGNOSTIC_ONLY_NO_SIGNALS_GENERATED = True
LIVE_TRADING_APPROVED = False
SEED_CLUSTER_TOKENS = (
    "all_ranges_all_gaps_all_touches_mt1",
    "all_ranges_all_gaps_all_touches_mt2",
    "all_ranges_all_gaps_first_touch_only_mt1",
    "all_ranges_all_gaps_first_touch_only_mt2",
)


def load_playbook_scheduler_c_inputs(output_dir: Path) -> dict[str, Any]:
    required: dict[str, Path] = {
        "playbook_module_registry": output_dir / "playbook_module_registry.csv",
        "research_signal_registry": output_dir / "research_signal_registry.csv",
        "module_pruning_diagnostics": output_dir / "module_pruning_audit_a_module_diagnostics.csv",
        "module_pruning_variants": output_dir / "module_pruning_audit_a_pruning_variants.csv",
        "module_pruning_results": output_dir / "module_pruning_audit_a_portfolio_results.csv",
        "module_pruning_daily": output_dir / "module_pruning_audit_a_daily_pnl.csv",
        "module_pruning_folds": output_dir / "module_pruning_audit_a_walk_forward_folds.csv",
        "module_pruning_concentration": output_dir / "module_pruning_audit_a_concentration.csv",
        "module_pruning_overlap": output_dir / "module_pruning_audit_a_overlap_summary.csv",
        "module_pruning_redundancy_pairs": output_dir / "module_pruning_audit_a_redundancy_pairs.csv",
        "module_pruning_recommendation": output_dir / "module_pruning_audit_a_next_action_recommendation.json",
        "scheduler_b_results": output_dir / "playbook_scheduler_b_priority_policy_results.csv",
        "scheduler_b_daily": output_dir / "playbook_scheduler_b_daily_pnl.csv",
        "scheduler_b_folds": output_dir / "playbook_scheduler_b_walk_forward_folds.csv",
        "scheduler_b_concentration": output_dir / "playbook_scheduler_b_concentration.csv",
        "scheduler_b_overlap": output_dir / "playbook_scheduler_b_overlap_summary.csv",
        "scheduler_b_acceptance": output_dir / "playbook_scheduler_b_module_acceptance_summary.csv",
        "scheduler_b_recommendation": output_dir / "playbook_scheduler_b_next_action_recommendation.json",
    }
    # Scheduler C intentionally uses only existing phase trade logs and existing audit outputs.
    for phase in PHASES:
        required[f"{phase}_trades"] = output_dir / f"{phase}_trade_logs.csv"
    missing = [str(path) for path in required.values() if not path.exists()]
    if missing:
        raise FileNotFoundError(f"Missing Playbook Scheduler C input(s): {missing}")
    return {key: _read_json(path) if path.suffix == ".json" else pd.read_csv(path) for key, path in required.items()}


def run_playbook_scheduler_c_pruning_retest(output_dir: Path) -> dict[str, Any]:
    data = load_playbook_scheduler_c_inputs(output_dir)
    selected = scheduler_b_best_priority_universe(data["scheduler_b_results"], data["module_pruning_diagnostics"])
    if len(selected) > MAX_SELECTED_MODULES:
        selected = selected.sort_values(["scheduler_b_best_rank", "selection_rank", "signal_key"]).head(MAX_SELECTED_MODULES).copy()
    selected_keys = selected["signal_key"].astype(str).tolist()
    identify_seed_suspect(selected_keys)
    trades = selected_trade_logs(data, selected_keys)
    daily_matrix = module_daily_matrix_from_trades(trades, selected_keys)
    avg_corr = average_abs_correlation(selected_keys, data["module_pruning_redundancy_pairs"], daily_matrix)
    max_corr = max_abs_correlation(selected_keys, daily_matrix=daily_matrix, corr=data["module_pruning_redundancy_pairs"])
    redundancy_pairs = reconstruct_high_redundancy_pairs(selected, daily_matrix, data["module_pruning_redundancy_pairs"])
    seed_cluster = identify_seed_suspect_cluster(selected_keys)
    variants = build_scheduler_c_pruning_variants(selected, selected_keys, redundancy_pairs, seed_cluster, avg_corr, data["module_pruning_variants"])
    scheduler_b_best = scheduler_b_best_priority_row(data["scheduler_b_results"])
    module_pruning_a_best = best_module_pruning_a_result(data["module_pruning_results"])

    result_rows: list[dict[str, Any]] = []
    daily_frames: list[pd.DataFrame] = []
    fold_frames: list[pd.DataFrame] = []
    concentration_rows: list[dict[str, Any]] = []
    overlap_rows: list[dict[str, Any]] = []
    acceptance_rows: list[dict[str, Any]] = []
    pruned_rows: list[dict[str, Any]] = []

    for variant_name in PRUNING_VARIANTS:
        keep_keys = variants[variant_name]
        removed = [k for k in selected_keys if k not in keep_keys]
        pruned_rows.append({
            "pruning_variant": variant_name,
            "kept_module_count": len(keep_keys),
            "removed_module_count": len(removed),
            "deprioritized_module_count": len(seed_cluster) if variant_name == "deprioritize_seed_cluster" else 0,
            "removed_modules": ";".join(removed),
            "deprioritized_modules": ";".join(seed_cluster) if variant_name == "deprioritize_seed_cluster" else "",
            "registry_files_mutated": False,
        })
        sub_selected = selected[selected["signal_key"].isin(keep_keys)].copy().reset_index(drop=True)
        sub_avg = {k: avg_corr.get(k, 0.0) for k in keep_keys}
        orders = build_priority_policy_orders(sub_selected, keep_keys, sub_avg) if keep_keys else {p: {} for p in PRIORITY_POLICIES}
        if variant_name == "deprioritize_seed_cluster":
            orders = {p: deprioritize_modules(order, seed_cluster) for p, order in orders.items()}
        for policy in PRIORITY_POLICIES:
            order = orders.get(policy, {})
            for mode in MODES:
                accepted, skipped_overlap, skipped_session, rejected, _ = construct_scheduled_trades(trades, keep_keys, order, mode)
                daily = scheduled_daily_with_variant(accepted, variant_name, policy, mode)
                folds = folds_with_variant(variant_name, policy, mode, daily)
                metrics = scheduler_c_metrics(
                    variant_name,
                    policy,
                    mode,
                    keep_keys,
                    removed,
                    accepted,
                    rejected,
                    daily,
                    folds,
                    skipped_overlap,
                    skipped_session,
                    scheduler_b_best,
                    module_pruning_a_best,
                )
                result_rows.append(metrics)
                daily_frames.append(daily)
                fold_frames.append(folds)
                concentration_rows.append({k: metrics[k] for k in ("pruning_variant", "priority_policy", "portfolio_mode", "best_day_concentration", "best_trade_concentration", "top_3_day_concentration", "top_5_trade_concentration")})
                overlap_rows.append(overlap_summary(variant_name, policy, mode, accepted, rejected, skipped_overlap, skipped_session))
                acceptance_rows.extend(module_acceptance_rows(variant_name, policy, mode, selected, keep_keys, order, accepted, rejected, seed_cluster))

    policy_results = pd.DataFrame(result_rows).sort_values(["pruning_variant", "priority_policy", "portfolio_mode"]).reset_index(drop=True)
    daily_pnl = _concat(daily_frames)
    folds = _concat(fold_frames)
    concentration_df = pd.DataFrame(concentration_rows).sort_values(["pruning_variant", "priority_policy", "portfolio_mode"]).reset_index(drop=True)
    overlap_df = pd.DataFrame(overlap_rows).sort_values(["pruning_variant", "priority_policy", "portfolio_mode"]).reset_index(drop=True)
    acceptance_df = pd.DataFrame(acceptance_rows).sort_values(["pruning_variant", "priority_policy", "portfolio_mode", "priority_rank", "signal_key"]).reset_index(drop=True)
    pruned_summary = pd.DataFrame(pruned_rows).sort_values("pruning_variant").reset_index(drop=True)
    recommendation = make_next_action_recommendation(policy_results, scheduler_b_best, module_pruning_a_best)
    return {
        "policy_results": policy_results,
        "daily_pnl": daily_pnl,
        "walk_forward_folds": folds,
        "concentration": concentration_df,
        "overlap_summary": overlap_df,
        "module_acceptance_summary": acceptance_df,
        "pruned_module_summary": pruned_summary,
        "redundancy_pairs": redundancy_pairs,
        "selected_modules": selected,
        "selected_signal_keys": selected_keys,
        "seed_suspect_module": SEED_SUSPECT_MODULE,
        "seed_cluster_modules": seed_cluster,
        "next_action_recommendation": recommendation,
        "inputs_loaded": loaded_input_names(),
    }


def identify_seed_suspect_cluster(selected_keys: list[str]) -> list[str]:
    identify_seed_suspect(selected_keys)
    seed_phase, seed_cid = split_signal_key(SEED_SUSPECT_MODULE)
    seed_family_prefix = seed_cid.split("first_touch_only_mt1", 1)[0]
    cluster = [
        k
        for k in selected_keys
        if split_signal_key(k)[0] == seed_phase
        and split_signal_key(k)[1].startswith(seed_family_prefix)
        and any(token in split_signal_key(k)[1] for token in SEED_CLUSTER_TOKENS)
    ]
    if SEED_SUSPECT_MODULE not in cluster:
        cluster.append(SEED_SUSPECT_MODULE)
    token_order = {token: i for i, token in enumerate(SEED_CLUSTER_TOKENS)}
    return sorted(set(cluster), key=lambda k: (token_order.get(next((t for t in SEED_CLUSTER_TOKENS if t in k), ""), 99), k))


def reconstruct_high_redundancy_pairs(selected: pd.DataFrame, daily_matrix: pd.DataFrame, prior_pairs: pd.DataFrame) -> pd.DataFrame:
    keys = set(selected["signal_key"].astype(str))
    if not prior_pairs.empty and "lower_ranked_module" in prior_pairs:
        pairs = prior_pairs.copy()
        pairs = pairs[pairs["signal_a"].astype(str).isin(keys) & pairs["signal_b"].astype(str).isin(keys)].copy()
        if not pairs.empty:
            return pairs.sort_values(["daily_pnl_correlation", "signal_a", "signal_b"], ascending=[False, True, True]).reset_index(drop=True)
    return calculate_redundancy_pairs(selected, daily_matrix, pd.DataFrame())


def build_scheduler_c_pruning_variants(selected: pd.DataFrame, selected_keys: list[str], redundancy_pairs: pd.DataFrame, seed_cluster: list[str], avg_corr: dict[str, float], pruning_a_variants: pd.DataFrame) -> dict[str, list[str]]:
    all_keys = list(selected_keys)
    seed_set = set(seed_cluster)
    high_redundancy_remove = set(redundancy_pairs["lower_ranked_module"].astype(str)) if not redundancy_pairs.empty and "lower_ranked_module" in redundancy_pairs else set()
    # Do not exceed the exact Module Pruning Audit A remove_high_redundancy_pairs removal set when available.
    prior = pruning_a_variants[pruning_a_variants["pruning_variant"].astype(str).eq("remove_high_redundancy_pairs")]
    if not prior.empty:
        prior_removed = set(_split_modules(prior.iloc[0].get("removed_modules", "")))
        if prior_removed:
            high_redundancy_remove = high_redundancy_remove.intersection(prior_removed) if high_redundancy_remove else prior_removed
    dedup_keep = deduped_representatives(selected, redundancy_pairs, avg_corr)
    variants = {
        "no_pruning_baseline": all_keys,
        "remove_seed_suspect_only": [k for k in all_keys if k != SEED_SUSPECT_MODULE],
        "remove_seed_suspect_cluster": [k for k in all_keys if k not in seed_set],
        "remove_high_redundancy_pairs": [k for k in all_keys if k not in high_redundancy_remove],
        "deprioritize_seed_cluster": all_keys,
        "keep_only_deduped_representatives": [k for k in all_keys if k in dedup_keep],
    }
    return variants


def deduped_representatives(selected: pd.DataFrame, redundancy_pairs: pd.DataFrame, avg_corr: dict[str, float]) -> set[str]:
    keys = selected["signal_key"].astype(str).tolist()
    parent = {k: k for k in keys}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    if not redundancy_pairs.empty:
        for _, row in redundancy_pairs.iterrows():
            a, b = str(row["signal_a"]), str(row["signal_b"])
            if a in parent and b in parent:
                union(a, b)
    clusters: dict[str, list[str]] = {}
    for key in keys:
        clusters.setdefault(find(key), []).append(key)
    meta = selected.set_index("signal_key")
    phase_rank = {"phase10b": 0, "phase11a": 1, "phase12a": 2, "phase13a": 3, "phase14a": 4, "phase15a": 5}

    def score(key: str) -> tuple[float, float, float, float, str]:
        row = meta.loc[key]
        validation = float(pd.to_numeric(row.get("validation_pnl", 0.0), errors="coerce") or 0.0)
        positive_validation = 0 if validation > 0 else 1
        best_conc = float(pd.to_numeric(row.get("best_day_concentration", 1.0), errors="coerce") or 1.0)
        corr = float(avg_corr.get(key, 0.0))
        existing_rank = float(pd.to_numeric(row.get("scheduler_b_best_rank", row.get("selection_rank", 9999)), errors="coerce") or 9999)
        phase = split_signal_key(key)[0]
        return (positive_validation, best_conc, corr, existing_rank + phase_rank.get(phase, 99) / 1000.0, key)

    keep = set()
    for members in clusters.values():
        keep.add(sorted(members, key=score)[0])
    return keep


def deprioritize_modules(order: dict[str, int], deprioritized: list[str]) -> dict[str, int]:
    low = set(deprioritized)
    ordered = [k for k, _ in sorted(order.items(), key=lambda kv: (kv[1], kv[0]))]
    shifted = [k for k in ordered if k not in low] + [k for k in ordered if k in low]
    return {k: i for i, k in enumerate(shifted)}


def scheduler_c_metrics(variant: str, policy: str, mode: str, keep_keys: list[str], removed: list[str], accepted: pd.DataFrame, rejected: pd.DataFrame, daily: pd.DataFrame, folds: pd.DataFrame, skipped_overlap: int, skipped_session: int, scheduler_b_best: dict[str, Any], module_pruning_a_best: dict[str, Any]) -> dict[str, Any]:
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
    label = scheduler_c_label(net, validation, holdout, wf_stress, pos_folds, day_conc["best"], trade_conc["best"], active_days, scheduler_b_best)
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
        "removed_module_count": len(removed),
        "removed_modules": ";".join(removed),
        "improvement_vs_scheduler_b_best": _delta(net, scheduler_b_best.get("net_pnl")),
        "improvement_vs_module_pruning_a_best": _delta(net, module_pruning_a_best.get("net_pnl")),
        "positive_wf_test_folds_delta_vs_scheduler_b_best": _delta(pos_folds, scheduler_b_best.get("positive_wf_test_folds_pct")),
        "best_day_concentration_delta_vs_scheduler_b_best": _delta(day_conc["best"], scheduler_b_best.get("best_day_concentration")),
        "best_trade_concentration_delta_vs_scheduler_b_best": _delta(trade_conc["best"], scheduler_b_best.get("best_trade_concentration")),
        "scheduler_c_label": label,
        "official_gates_changed": False,
        "paper_trading_approved": False,
        "diagnostic_only_no_signals_generated": True,
        "live_trading_approved": False,
        "raw_sum_diagnostic_used_as_candidate": False,
    }


def scheduler_c_label(net: float, validation: float | None, holdout: float | None, wf_stress: float | None, pos_folds: float | None, best_day: float, best_trade: float, active_days: int, scheduler_b_best: dict[str, Any]) -> str:
    if net <= 0 or active_days < 5:
        return "scheduler_c_negative_or_low_activity"
    base_fold = _float_or_none(scheduler_b_best.get("positive_wf_test_folds_pct"))
    base_day = _float_or_none(scheduler_b_best.get("best_day_concentration"))
    base_trade = _float_or_none(scheduler_b_best.get("best_trade_concentration"))
    fold_improves = pos_folds is not None and base_fold is not None and pos_folds > base_fold
    conc_improves = base_day is not None and base_trade is not None and best_day < base_day and best_trade < base_trade
    candidate = net > 0 and (validation is None or validation > 0) and (holdout is None or holdout > 0) and (wf_stress is None or wf_stress > 0) and (pos_folds is None or pos_folds >= CANDIDATE_FOLD_GATE) and conc_improves and PAPER_TRADING_APPROVED is False
    if candidate:
        return "scheduler_c_candidate_for_scheduler_review_only"
    if fold_improves and conc_improves:
        return "scheduler_c_improves_folds_and_concentration"
    if fold_improves:
        return "scheduler_c_improves_folds_only"
    if conc_improves:
        return "scheduler_c_improves_concentration_only"
    return "scheduler_c_no_improvement"


def module_acceptance_rows(variant: str, policy: str, mode: str, selected: pd.DataFrame, keep_keys: list[str], order: dict[str, int], accepted: pd.DataFrame, rejected: pd.DataFrame, seed_cluster: list[str]) -> list[dict[str, Any]]:
    rows = []
    keep = set(keep_keys)
    seed = set(seed_cluster)
    acc_counts = accepted.groupby("signal_key").size().to_dict() if not accepted.empty else {}
    acc_pnl = accepted.groupby("signal_key")["net_pnl"].sum().to_dict() if not accepted.empty else {}
    rej_counts = rejected.groupby("signal_key").size().to_dict() if not rejected.empty and "signal_key" in rejected else {}
    rej_pnl = rejected.groupby("signal_key")["net_pnl"].sum().to_dict() if not rejected.empty and "signal_key" in rejected else {}
    for _, row in selected.iterrows():
        key = str(row["signal_key"])
        rows.append({
            "pruning_variant": variant,
            "priority_policy": policy,
            "portfolio_mode": mode,
            "priority_rank": int(order.get(key, 9999)),
            "phase": str(row.get("phase", split_signal_key(key)[0])),
            "candidate_id": str(row.get("candidate_id", split_signal_key(key)[1])),
            "signal_key": key,
            "module_kept": bool(key in keep),
            "module_removed": bool(key not in keep),
            "module_deprioritized": bool(variant == "deprioritize_seed_cluster" and key in seed),
            "accepted_trade_count": int(acc_counts.get(key, 0)),
            "accepted_net_pnl": round(float(acc_pnl.get(key, 0.0)), 2),
            "skipped_trade_count": int(rej_counts.get(key, 0)),
            "skipped_net_pnl": round(float(rej_pnl.get(key, 0.0)), 2),
        })
    return rows


def best_module_pruning_a_result(results: pd.DataFrame) -> dict[str, Any]:
    if results.empty:
        return {}
    return results.sort_values(["positive_wf_test_folds_pct", "net_pnl", "best_day_concentration", "pruning_variant", "priority_policy"], ascending=[False, False, True, True, True]).iloc[0].to_dict()


def best_scheduler_c_result(results: pd.DataFrame) -> dict[str, Any]:
    if results.empty:
        return {}
    return results.sort_values(["positive_wf_test_folds_pct", "net_pnl", "best_day_concentration", "pruning_variant", "priority_policy"], ascending=[False, False, True, True, True]).iloc[0].to_dict()


def make_next_action_recommendation(results: pd.DataFrame, scheduler_b_best: dict[str, Any], module_pruning_a_best: dict[str, Any]) -> dict[str, Any]:
    non_base = results[~results["pruning_variant"].eq("no_pruning_baseline")].copy()
    candidates = non_base[non_base["scheduler_c_label"].eq("scheduler_c_candidate_for_scheduler_review_only")]
    high_redundancy = non_base[non_base["pruning_variant"].eq("remove_high_redundancy_pairs")]
    deprio = non_base[non_base["pruning_variant"].eq("deprioritize_seed_cluster")]
    seed_cluster = non_base[non_base["pruning_variant"].eq("remove_seed_suspect_cluster")]
    best = best_scheduler_c_result(results)
    high_rep = bool(high_redundancy["scheduler_c_label"].isin(["scheduler_c_improves_folds_and_concentration", "scheduler_c_candidate_for_scheduler_review_only"]).any()) if not high_redundancy.empty else False
    best_non_base = best_scheduler_c_result(non_base) if not non_base.empty else {}
    seed_best = best_scheduler_c_result(seed_cluster) if not seed_cluster.empty else {}
    deprio_best = best_scheduler_c_result(deprio) if not deprio.empty else {}
    deprio_nearly = False
    if seed_best and deprio_best:
        deprio_nearly = float(deprio_best.get("net_pnl", 0.0) or 0.0) >= 0.90 * float(seed_best.get("net_pnl", 0.0) or 0.0) and float(deprio_best.get("positive_wf_test_folds_pct", 0.0) or 0.0) >= float(seed_best.get("positive_wf_test_folds_pct", 0.0) or 0.0) - 0.167
    if not candidates.empty:
        action = "scheduler_c_review_packet_only"
        rationale = "At least one Scheduler C retest row met scheduler-review-only criteria; paper trading remains false."
    elif high_rep:
        action = "playbook_module_deduplication_b_review"
        rationale = "remove_high_redundancy_pairs replicated fold and concentration improvement under Scheduler C."
    elif deprio_nearly:
        action = "scheduler_priority_d_deprioritize_redundant_cluster"
        rationale = "Deprioritizing the seed cluster performed nearly as well as removal in Scheduler C."
    elif best_non_base.get("pruning_variant") == "remove_seed_suspect_cluster" and str(best_non_base.get("scheduler_c_label", "")).startswith("scheduler_c_improves"):
        action = "mark_phase10b_seed_cluster_for_deprioritization_review"
        rationale = "Removing the Phase 10B seed cluster was the strongest replicated pruning path."
    else:
        action = "phase16a_targeted_regime_module_scout"
        rationale = "Scheduler C pruning improvements did not replicate strongly enough versus Scheduler B and Module Pruning Audit A."
    return {
        "next_action": action,
        "rationale": rationale,
        "best_pruning_variant": best.get("pruning_variant"),
        "best_priority_policy": best.get("priority_policy"),
        "best_portfolio_mode": best.get("portfolio_mode"),
        "best_scheduler_c_label": best.get("scheduler_c_label"),
        "best_net_pnl": best.get("net_pnl"),
        "folds_improved_vs_scheduler_b_best": bool((_float_or_none(best.get("positive_wf_test_folds_delta_vs_scheduler_b_best")) or 0.0) > 0),
        "concentration_improved_vs_scheduler_b_best": bool(((_float_or_none(best.get("best_day_concentration_delta_vs_scheduler_b_best")) or 0.0) < 0) and ((_float_or_none(best.get("best_trade_concentration_delta_vs_scheduler_b_best")) or 0.0) < 0)),
        "module_pruning_a_improvement_replicated": bool((_float_or_none(best.get("improvement_vs_module_pruning_a_best")) or 0.0) >= 0 or high_rep),
        "scheduler_review_row_count": int(len(candidates)),
        "seed_suspect_module": SEED_SUSPECT_MODULE,
        "official_gates_changed": False,
        "paper_trading_approved": False,
        "diagnostic_only_no_signals_generated": True,
        "live_trading_approved": False,
        "raw_sum_diagnostic_used_as_candidate": False,
        "registry_files_mutated": False,
    }


def render_playbook_scheduler_c_report(result: dict[str, Any]) -> str:
    rec = result["next_action_recommendation"]
    best = best_scheduler_c_result(result["policy_results"])
    lines = [
        "# Playbook Scheduler C — Pruning Retest",
        "",
        RESEARCH_ONLY_GUARDRAIL,
        "",
        "Research-only pruning/deprioritization retest using existing Module Pruning Audit A outputs, Scheduler B outputs, registries, and phase trade logs only. No new signals, no strategy searches, no candidate-result changes, no registry mutation, no official gate changes, no promotions, no paper-trading approval, and no live-trading functionality were added.",
        "",
        "## Summary",
        "",
        f"- Selected module universe: `{len(result['selected_signal_keys'])}` (hard cap `{MAX_SELECTED_MODULES}`)",
        f"- Seed suspect: `{result['seed_suspect_module']}`",
        f"- Seed cluster: `{';'.join(result['seed_cluster_modules'])}`",
        f"- Pruning/deprioritization variants tested: `{', '.join(PRUNING_VARIANTS)}`",
        f"- Priority policies tested: `{', '.join(PRIORITY_POLICIES)}`",
        f"- Modes tested: `{', '.join(MODES)}`",
        f"- Best Scheduler C result: `{best.get('pruning_variant')}` / `{best.get('priority_policy')}` / `{best.get('portfolio_mode')}` net `{float(best.get('net_pnl', 0.0)):.2f}` pos folds `{float(best.get('positive_wf_test_folds_pct') or 0.0):.3f}` day conc `{float(best.get('best_day_concentration') or 0.0):.3f}` trade conc `{float(best.get('best_trade_concentration') or 0.0):.3f}` label `{best.get('scheduler_c_label')}`",
        f"- Next action: `{rec['next_action']}`",
        f"- Rationale: {rec['rationale']}",
        "- Paper trading approved: `false`",
        "",
        "## Top Scheduler C rows",
        "",
        markdown_table(result["policy_results"].sort_values(["positive_wf_test_folds_pct", "net_pnl", "best_day_concentration"], ascending=[False, False, True]).head(25)),
        "",
        "## Pruned/deprioritized module summary",
        "",
        markdown_table(result["pruned_module_summary"]),
        "",
        "## Module acceptance summary",
        "",
        markdown_table(result["module_acceptance_summary"].head(40)),
        "",
        "## Guardrails",
        "",
        "Official gates changed: `false`.",
        "Paper trading approved: `false`.",
        "New strategy signals generated: `false`.",
        "Registry files mutated: `false`.",
        "Live trading approved: `false`.",
        "Raw-sum diagnostic used as candidate mode: `false`.",
        "Weak-fold-derived regime filters used: `false`.",
        "",
    ]
    return "\n".join(lines)


def write_playbook_scheduler_c_outputs(result: dict[str, Any], output_dir: Path, report_path: Path) -> dict[str, Path]:
    ensure_directory(output_dir)
    ensure_directory(report_path.parent)
    mapping = {
        "policy_results": output_dir / "playbook_scheduler_c_pruning_policy_results.csv",
        "daily_pnl": output_dir / "playbook_scheduler_c_daily_pnl.csv",
        "walk_forward_folds": output_dir / "playbook_scheduler_c_walk_forward_folds.csv",
        "concentration": output_dir / "playbook_scheduler_c_concentration.csv",
        "overlap_summary": output_dir / "playbook_scheduler_c_overlap_summary.csv",
        "module_acceptance_summary": output_dir / "playbook_scheduler_c_module_acceptance_summary.csv",
        "pruned_module_summary": output_dir / "playbook_scheduler_c_pruned_module_summary.csv",
    }
    paths: dict[str, Path] = {}
    for key, path in mapping.items():
        write_csv_artifact(result[key], path)
        paths[key] = path
    rec_path = output_dir / "playbook_scheduler_c_next_action_recommendation.json"
    write_json_artifact(result["next_action_recommendation"], rec_path)
    report_path.write_text(render_playbook_scheduler_c_report(result), encoding="utf-8")
    paths["recommendation"] = rec_path
    paths["report"] = report_path
    return paths


def loaded_input_names() -> list[str]:
    return [
        "outputs/playbook_module_registry.csv",
        "outputs/research_signal_registry.csv",
        "outputs/module_pruning_audit_a_module_diagnostics.csv",
        "outputs/module_pruning_audit_a_pruning_variants.csv",
        "outputs/module_pruning_audit_a_portfolio_results.csv",
        "outputs/module_pruning_audit_a_daily_pnl.csv",
        "outputs/module_pruning_audit_a_walk_forward_folds.csv",
        "outputs/module_pruning_audit_a_concentration.csv",
        "outputs/module_pruning_audit_a_overlap_summary.csv",
        "outputs/module_pruning_audit_a_redundancy_pairs.csv",
        "outputs/module_pruning_audit_a_next_action_recommendation.json",
        "outputs/playbook_scheduler_b_priority_policy_results.csv",
        "outputs/playbook_scheduler_b_daily_pnl.csv",
        "outputs/playbook_scheduler_b_walk_forward_folds.csv",
        "outputs/playbook_scheduler_b_concentration.csv",
        "outputs/playbook_scheduler_b_overlap_summary.csv",
        "outputs/playbook_scheduler_b_module_acceptance_summary.csv",
        "outputs/playbook_scheduler_b_next_action_recommendation.json",
        *[f"outputs/{phase}_trade_logs.csv" for phase in PHASES],
    ]


def _split_modules(value: Any) -> list[str]:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return []
    return [v for v in str(value).split(";") if v and v.lower() != "nan"]


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
