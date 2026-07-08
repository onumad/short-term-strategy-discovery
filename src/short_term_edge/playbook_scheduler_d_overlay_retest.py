from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from .module_pruning_audit_a import (
    SEED_SUSPECT_MODULE,
    folds_with_variant,
    identify_seed_suspect,
    overlap_summary,
    scheduled_daily_with_variant,
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

OVERLAY_VARIANTS = (
    "no_overlay_baseline",
    "overlay_priority_only",
    "overlay_deprioritize_only",
    "overlay_exclude_parked",
    "overlay_keep_representatives_plus_diversifiers",
    "overlay_keep_representatives_only",
    "overlay_seed_cluster_deprioritized",
    "overlay_seed_cluster_excluded",
)
PRIORITY_POLICIES = (
    "hybrid_validation_then_correlation",
    "concentration_adjusted_priority",
    "lowest_correlation_first",
    "rare_setup_first",
)
MODES = ("one_trade_at_a_time_chronological", "max_one_trade_per_session")
CANDIDATE_FOLD_GATE = 0.833
OFFICIAL_GATES_CHANGED = False
PAPER_TRADING_APPROVED = False
DIAGNOSTIC_ONLY_NO_SIGNALS_GENERATED = True
LIVE_TRADING_APPROVED = False
REGISTRY_MUTATION = False
SEED_CLUSTER_TOKENS = (
    "all_ranges_all_gaps_all_touches_mt1",
    "all_ranges_all_gaps_all_touches_mt2",
    "all_ranges_all_gaps_first_touch_only_mt1",
    "all_ranges_all_gaps_first_touch_only_mt2",
)


def load_playbook_scheduler_d_inputs(output_dir: Path) -> dict[str, Any]:
    required: dict[str, Path] = {
        "playbook_module_registry": output_dir / "playbook_module_registry.csv",
        "research_signal_registry": output_dir / "research_signal_registry.csv",
        "dedup_overlay": output_dir / "playbook_module_deduplication_b_scheduler_overlay.json",
        "dedup_clusters": output_dir / "playbook_module_deduplication_b_redundancy_clusters.csv",
        "dedup_module_review": output_dir / "playbook_module_deduplication_b_module_review.csv",
        "dedup_representatives": output_dir / "playbook_module_deduplication_b_representative_modules.csv",
        "dedup_deprioritization": output_dir / "playbook_module_deduplication_b_deprioritization_candidates.csv",
        "dedup_recommendation": output_dir / "playbook_module_deduplication_b_next_action_recommendation.json",
        "scheduler_c_results": output_dir / "playbook_scheduler_c_pruning_policy_results.csv",
        "scheduler_c_daily": output_dir / "playbook_scheduler_c_daily_pnl.csv",
        "scheduler_c_folds": output_dir / "playbook_scheduler_c_walk_forward_folds.csv",
        "scheduler_c_concentration": output_dir / "playbook_scheduler_c_concentration.csv",
        "scheduler_c_overlap": output_dir / "playbook_scheduler_c_overlap_summary.csv",
        "scheduler_c_acceptance": output_dir / "playbook_scheduler_c_module_acceptance_summary.csv",
        "scheduler_c_pruned": output_dir / "playbook_scheduler_c_pruned_module_summary.csv",
        "scheduler_c_recommendation": output_dir / "playbook_scheduler_c_next_action_recommendation.json",
        "scheduler_b_results": output_dir / "playbook_scheduler_b_priority_policy_results.csv",
        "scheduler_b_daily": output_dir / "playbook_scheduler_b_daily_pnl.csv",
        "scheduler_b_folds": output_dir / "playbook_scheduler_b_walk_forward_folds.csv",
        "scheduler_b_concentration": output_dir / "playbook_scheduler_b_concentration.csv",
        "scheduler_b_acceptance": output_dir / "playbook_scheduler_b_module_acceptance_summary.csv",
        "module_pruning_a_results": output_dir / "module_pruning_audit_a_portfolio_results.csv",
    }
    for phase in PHASES:
        required[f"{phase}_trades"] = output_dir / f"{phase}_trade_logs.csv"
    missing = [str(path) for path in required.values() if not path.exists()]
    if missing:
        raise FileNotFoundError(f"Missing Playbook Scheduler D input(s): {missing}")
    return {key: _read_json(path) if path.suffix == ".json" else pd.read_csv(path) for key, path in required.items()}


def run_playbook_scheduler_d_overlay_retest(output_dir: Path) -> dict[str, Any]:
    data = load_playbook_scheduler_d_inputs(output_dir)
    overlay = data["dedup_overlay"]
    validate_overlay_guardrails(overlay)
    selected_keys = scheduler_c_baseline_universe(data["scheduler_c_results"])
    selected = selected_modules_from_registry(data["playbook_module_registry"], data["dedup_module_review"], selected_keys)
    selected_keys = selected["signal_key"].astype(str).tolist()
    identify_seed_suspect(selected_keys)
    trades = selected_trade_logs(data, selected_keys)
    daily_matrix = module_daily_matrix_from_trades(trades, selected_keys)
    avg_corr = average_abs_correlation(selected_keys, pd.DataFrame(), daily_matrix)
    seed_cluster = identify_seed_suspect_cluster(selected_keys)
    variants = build_scheduler_d_overlay_variants(selected, selected_keys, overlay, seed_cluster)
    scheduler_b_best = scheduler_b_best_priority_row(data["scheduler_b_results"])
    scheduler_c_best = best_scheduler_c_baseline(data["scheduler_c_results"])
    module_pruning_a_best = best_module_pruning_a_result(data["module_pruning_a_results"])

    result_rows: list[dict[str, Any]] = []
    daily_frames: list[pd.DataFrame] = []
    fold_frames: list[pd.DataFrame] = []
    concentration_rows: list[dict[str, Any]] = []
    overlap_rows: list[dict[str, Any]] = []
    acceptance_rows: list[dict[str, Any]] = []
    overlay_effect_rows: list[dict[str, Any]] = []

    for variant_name in OVERLAY_VARIANTS:
        keep_keys = variants[variant_name]
        removed = [k for k in selected_keys if k not in keep_keys]
        deprioritized = deprioritized_for_variant(variant_name, selected_keys, overlay, seed_cluster, selected)
        parked = [k for k in _overlay_list(overlay, "modules_to_park") if k in selected_keys]
        overlay_effect_rows.append({
            "overlay_variant": variant_name,
            "kept_module_count": len(keep_keys),
            "overlay_removed_module_count": len(removed),
            "overlay_deprioritized_module_count": len(deprioritized),
            "overlay_parked_module_count": len(parked),
            "removed_modules": ";".join(removed),
            "deprioritized_modules": ";".join(deprioritized),
            "parked_modules": ";".join(parked),
            "registry_mutation": False,
        })
        sub_selected = selected[selected["signal_key"].isin(keep_keys)].copy().reset_index(drop=True)
        sub_avg = {k: avg_corr.get(k, 0.0) for k in keep_keys}
        base_orders = build_priority_policy_orders(sub_selected, keep_keys, sub_avg) if keep_keys else {p: {} for p in PRIORITY_POLICIES}
        orders = {p: apply_overlay_priority(order, variant_name, overlay, seed_cluster, selected) for p, order in base_orders.items()}
        for policy in PRIORITY_POLICIES:
            order = orders.get(policy, {})
            for mode in MODES:
                accepted, skipped_overlap, skipped_session, rejected, _ = construct_scheduled_trades(trades, keep_keys, order, mode)
                daily = scheduled_daily_with_variant(accepted, variant_name, policy, mode)
                folds = folds_with_variant(variant_name, policy, mode, daily)
                metrics = scheduler_d_metrics(
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
                    scheduler_c_best,
                    module_pruning_a_best,
                    deprioritized,
                    parked,
                )
                result_rows.append(metrics)
                daily_frames.append(daily)
                fold_frames.append(folds)
                concentration_rows.append({k: metrics[k] for k in ("overlay_variant", "priority_policy", "portfolio_mode", "best_day_concentration", "best_trade_concentration", "top_3_day_concentration", "top_5_trade_concentration")})
                overlap = overlap_summary(variant_name, policy, mode, accepted, rejected, skipped_overlap, skipped_session)
                if "pruning_variant" in overlap:
                    overlap["overlay_variant"] = overlap.pop("pruning_variant")
                overlap_rows.append(overlap)
                acceptance_rows.extend(module_acceptance_rows(variant_name, policy, mode, selected, keep_keys, order, accepted, rejected, deprioritized, parked))

    policy_results = pd.DataFrame(result_rows).sort_values(["overlay_variant", "priority_policy", "portfolio_mode"]).reset_index(drop=True)
    daily_pnl = _concat(daily_frames)
    folds = _concat(fold_frames)
    concentration_df = pd.DataFrame(concentration_rows).sort_values(["overlay_variant", "priority_policy", "portfolio_mode"]).reset_index(drop=True)
    overlap_df = pd.DataFrame(overlap_rows).sort_values(["overlay_variant", "priority_policy", "portfolio_mode"]).reset_index(drop=True)
    acceptance_df = pd.DataFrame(acceptance_rows).sort_values(["overlay_variant", "priority_policy", "portfolio_mode", "priority_rank", "signal_key"]).reset_index(drop=True)
    overlay_effect_summary = pd.DataFrame(overlay_effect_rows).sort_values("overlay_variant").reset_index(drop=True)
    recommendation = make_next_action_recommendation(policy_results, scheduler_b_best, scheduler_c_best, module_pruning_a_best)
    return {
        "policy_results": policy_results,
        "daily_pnl": daily_pnl,
        "walk_forward_folds": folds,
        "concentration": concentration_df,
        "overlap_summary": overlap_df,
        "module_acceptance_summary": acceptance_df,
        "overlay_effect_summary": overlay_effect_summary,
        "selected_modules": selected,
        "selected_signal_keys": selected_keys,
        "seed_suspect_module": SEED_SUSPECT_MODULE,
        "seed_cluster_modules": seed_cluster,
        "next_action_recommendation": recommendation,
        "inputs_loaded": loaded_input_names(),
        "dedup_overlay": overlay,
        "scheduler_b_best": scheduler_b_best,
        "scheduler_c_best": scheduler_c_best,
        "module_pruning_a_best": module_pruning_a_best,
    }


def validate_overlay_guardrails(overlay: dict[str, Any]) -> None:
    expected_false = ("registry_mutation", "official_gates_changed", "paper_trading_approved", "live_trading_approved")
    bad = [key for key in expected_false if bool(overlay.get(key))]
    if bad:
        raise ValueError(f"Deduplication overlay violates Scheduler D guardrails: {bad}")


def scheduler_c_baseline_universe(results: pd.DataFrame) -> list[str]:
    base = results[results["pruning_variant"].astype(str).eq("no_pruning_baseline")].copy()
    if base.empty:
        raise ValueError("Scheduler C no_pruning_baseline row not found; cannot reconstruct Scheduler C universe")
    row = best_scheduler_c_baseline(base)
    keys = _split_modules(row.get("signal_keys", ""))
    if not keys:
        raise ValueError("Scheduler C baseline signal_keys are empty")
    return keys


def selected_modules_from_registry(module_registry: pd.DataFrame, module_review: pd.DataFrame, selected_keys: list[str]) -> pd.DataFrame:
    registry = module_registry.copy()
    if "signal_key" not in registry.columns:
        registry["signal_key"] = registry["phase"].astype(str) + "::" + registry["candidate_id"].astype(str)
    selected = registry[registry["signal_key"].isin(selected_keys)].copy()
    missing = [key for key in selected_keys if key not in set(selected["signal_key"].astype(str))]
    if missing:
        raise ValueError(f"Scheduler C universe module(s) missing from playbook registry: {missing}")
    review_cols = [c for c in ("signal_key", "average_correlation", "scheduler_b_accepted_net_pnl", "scheduler_c_accepted_net_pnl", "weak_fold_harm") if c in module_review.columns]
    if review_cols:
        selected = selected.merge(module_review[review_cols].drop_duplicates("signal_key"), on="signal_key", how="left")
    selected["selection_rank"] = selected["signal_key"].map({key: i for i, key in enumerate(selected_keys)})
    selected["scheduler_b_best_rank"] = selected["selection_rank"]
    return selected.sort_values("selection_rank").reset_index(drop=True)


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


def build_scheduler_d_overlay_variants(selected: pd.DataFrame, selected_keys: list[str], overlay: dict[str, Any], seed_cluster: list[str]) -> dict[str, list[str]]:
    all_keys = list(selected_keys)
    keep = set(_overlay_list(overlay, "modules_to_keep")) & set(all_keys)
    deprioritize = set(_overlay_list(overlay, "modules_to_deprioritize")) & set(all_keys)
    park = set(_overlay_list(overlay, "modules_to_park")) & set(all_keys)
    diversifiers = {k for k in all_keys if split_signal_key(k)[0] in {"phase13a", "phase14a", "phase15a"}}
    rep_plus_div = [k for k in all_keys if (k in keep or (k in diversifiers and k not in deprioritize and k not in park))]
    variants = {
        "no_overlay_baseline": all_keys,
        "overlay_priority_only": all_keys,
        "overlay_deprioritize_only": all_keys,
        "overlay_exclude_parked": [k for k in all_keys if k not in park],
        "overlay_keep_representatives_plus_diversifiers": rep_plus_div,
        "overlay_keep_representatives_only": [k for k in all_keys if k in keep],
        "overlay_seed_cluster_deprioritized": all_keys,
        "overlay_seed_cluster_excluded": [k for k in all_keys if k not in set(seed_cluster)],
    }
    return variants


def deprioritized_for_variant(variant: str, selected_keys: list[str], overlay: dict[str, Any], seed_cluster: list[str], selected: pd.DataFrame) -> list[str]:
    selected_set = set(selected_keys)
    deprioritize = [k for k in _overlay_list(overlay, "modules_to_deprioritize") if k in selected_set]
    park = [k for k in _overlay_list(overlay, "modules_to_park") if k in selected_set]
    if variant == "overlay_priority_only":
        return deprioritize + [k for k in park if k not in deprioritize]
    if variant == "overlay_deprioritize_only":
        diversifiers = {k for k in selected_keys if split_signal_key(k)[0] in {"phase13a", "phase14a", "phase15a"}}
        return [k for k in deprioritize if k not in diversifiers] + [k for k in deprioritize if k in diversifiers]
    if variant == "overlay_seed_cluster_deprioritized":
        return [k for k in seed_cluster if k in selected_set]
    return []


def apply_overlay_priority(order: dict[str, int], variant: str, overlay: dict[str, Any], seed_cluster: list[str], selected: pd.DataFrame) -> dict[str, int]:
    if not order:
        return order
    ordered = [k for k, _ in sorted(order.items(), key=lambda kv: (kv[1], kv[0]))]
    selected_set = set(ordered)
    keep = [k for k in _overlay_list(overlay, "modules_to_keep") if k in selected_set]
    deprioritize = [k for k in _overlay_list(overlay, "modules_to_deprioritize") if k in selected_set]
    park = [k for k in _overlay_list(overlay, "modules_to_park") if k in selected_set]
    diversifiers = [k for k in ordered if split_signal_key(k)[0] in {"phase13a", "phase14a", "phase15a"}]
    if variant == "no_overlay_baseline":
        shifted = ordered
    elif variant == "overlay_priority_only":
        shifted = _stable_unique(keep + diversifiers + [k for k in ordered if k not in set(keep + diversifiers + deprioritize + park)] + deprioritize + park)
    elif variant == "overlay_deprioritize_only":
        park_div = [k for k in park if k in set(diversifiers)]
        low = [k for k in deprioritize if k not in set(park_div)]
        shifted = _stable_unique([k for k in ordered if k not in set(park_div + low)] + park_div + low)
    elif variant == "overlay_seed_cluster_deprioritized":
        shifted = _stable_unique([k for k in ordered if k not in set(seed_cluster)] + [k for k in ordered if k in set(seed_cluster)])
    elif variant in {"overlay_exclude_parked", "overlay_keep_representatives_plus_diversifiers", "overlay_keep_representatives_only", "overlay_seed_cluster_excluded"}:
        shifted = _stable_unique(keep + [k for k in ordered if k not in set(keep + deprioritize)] + deprioritize)
    else:
        shifted = ordered
    return {k: i for i, k in enumerate(shifted)}


def scheduler_d_metrics(variant: str, policy: str, mode: str, keep_keys: list[str], removed: list[str], accepted: pd.DataFrame, rejected: pd.DataFrame, daily: pd.DataFrame, folds: pd.DataFrame, skipped_overlap: int, skipped_session: int, scheduler_b_best: dict[str, Any], scheduler_c_best: dict[str, Any], module_pruning_a_best: dict[str, Any], deprioritized: list[str], parked: list[str]) -> dict[str, Any]:
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
    label = scheduler_d_label(net, validation, holdout, wf_stress, pos_folds, day_conc["best"], trade_conc["best"], active_days, scheduler_c_best)
    phase_counts = accepted.groupby("phase").size().sort_index().to_dict() if not accepted.empty else {}
    module_counts = accepted.groupby("signal_key").size().sort_index().to_dict() if not accepted.empty else {}
    return {
        "overlay_variant": variant,
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
        "accepted_trade_count_by_phase": json.dumps({str(k): int(v) for k, v in phase_counts.items()}, sort_keys=True),
        "accepted_trade_count_by_module": json.dumps({str(k): int(v) for k, v in module_counts.items()}, sort_keys=True),
        "overlay_removed_module_count": len(removed),
        "overlay_deprioritized_module_count": len(deprioritized),
        "overlay_parked_module_count": len(parked),
        "removed_modules": ";".join(removed),
        "deprioritized_modules": ";".join(deprioritized),
        "improvement_vs_scheduler_b_best": _delta(net, scheduler_b_best.get("net_pnl")),
        "improvement_vs_scheduler_c_best": _delta(net, scheduler_c_best.get("net_pnl")),
        "improvement_vs_module_pruning_a_best": _delta(net, module_pruning_a_best.get("net_pnl")),
        "positive_wf_test_folds_delta_vs_scheduler_c_best": _delta(pos_folds, scheduler_c_best.get("positive_wf_test_folds_pct")),
        "best_day_concentration_delta_vs_scheduler_c_best": _delta(day_conc["best"], scheduler_c_best.get("best_day_concentration")),
        "best_trade_concentration_delta_vs_scheduler_c_best": _delta(trade_conc["best"], scheduler_c_best.get("best_trade_concentration")),
        "active_days_delta_vs_scheduler_c_best": _delta(active_days, scheduler_c_best.get("active_days")),
        "skipped_overlap_delta_vs_scheduler_c_best": _delta(skipped_overlap, scheduler_c_best.get("skipped_overlap_count")),
        "weak_fold_pnl_delta_vs_scheduler_c_best": _delta(weak_pnl, scheduler_c_best.get("weak_fold_pnl")),
        "scheduler_d_label": label,
        "official_gates_changed": False,
        "paper_trading_approved": False,
        "diagnostic_only_no_signals_generated": True,
        "live_trading_approved": False,
        "raw_sum_diagnostic_used_as_candidate": False,
        "weak_fold_regime_filters_used": False,
        "registry_mutation": False,
    }


def scheduler_d_label(net: float, validation: float | None, holdout: float | None, wf_stress: float | None, pos_folds: float | None, best_day: float, best_trade: float, active_days: int, scheduler_c_best: dict[str, Any]) -> str:
    base_fold = _float_or_none(scheduler_c_best.get("positive_wf_test_folds_pct"))
    base_day = _float_or_none(scheduler_c_best.get("best_day_concentration"))
    base_trade = _float_or_none(scheduler_c_best.get("best_trade_concentration"))
    base_active_days = _float_or_none(scheduler_c_best.get("active_days"))
    if net <= 0 or (base_active_days is not None and active_days < max(5, int(0.80 * base_active_days))):
        return "scheduler_d_negative_or_low_activity"
    fold_improves = pos_folds is not None and base_fold is not None and pos_folds > base_fold
    conc_improves = base_day is not None and base_trade is not None and best_day < base_day and best_trade < base_trade
    severe_activity_loss = base_active_days is not None and active_days < int(0.80 * base_active_days)
    candidate = (
        net > 0
        and (validation is None or validation > 0)
        and (holdout is None or holdout > 0)
        and (wf_stress is None or wf_stress > 0)
        and (pos_folds is None or pos_folds >= CANDIDATE_FOLD_GATE)
        and best_day <= 0.20
        and best_trade <= 0.15
        and not severe_activity_loss
        and PAPER_TRADING_APPROVED is False
    )
    if candidate:
        return "scheduler_d_candidate_for_overlay_review_only"
    if fold_improves and conc_improves:
        return "scheduler_d_improves_folds_and_concentration"
    if fold_improves:
        return "scheduler_d_improves_folds_only"
    if conc_improves:
        return "scheduler_d_improves_concentration_only"
    return "scheduler_d_no_improvement"


def module_acceptance_rows(variant: str, policy: str, mode: str, selected: pd.DataFrame, keep_keys: list[str], order: dict[str, int], accepted: pd.DataFrame, rejected: pd.DataFrame, deprioritized: list[str], parked: list[str]) -> list[dict[str, Any]]:
    rows = []
    keep = set(keep_keys)
    deprio = set(deprioritized)
    park = set(parked)
    acc_counts = accepted.groupby("signal_key").size().to_dict() if not accepted.empty else {}
    acc_pnl = accepted.groupby("signal_key")["net_pnl"].sum().to_dict() if not accepted.empty else {}
    rej_counts = rejected.groupby("signal_key").size().to_dict() if not rejected.empty and "signal_key" in rejected else {}
    rej_pnl = rejected.groupby("signal_key")["net_pnl"].sum().to_dict() if not rejected.empty and "signal_key" in rejected else {}
    for _, row in selected.iterrows():
        key = str(row["signal_key"])
        rows.append({
            "overlay_variant": variant,
            "priority_policy": policy,
            "portfolio_mode": mode,
            "priority_rank": int(order.get(key, 9999)),
            "phase": str(row.get("phase", split_signal_key(key)[0])),
            "candidate_id": str(row.get("candidate_id", split_signal_key(key)[1])),
            "signal_key": key,
            "module_kept": bool(key in keep),
            "module_removed": bool(key not in keep),
            "module_deprioritized": bool(key in deprio),
            "module_parked_by_overlay": bool(key in park),
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


def best_scheduler_c_baseline(results: pd.DataFrame) -> dict[str, Any]:
    if results.empty:
        return {}
    frame = results.copy()
    return frame.sort_values(["positive_wf_test_folds_pct", "net_pnl", "best_day_concentration", "pruning_variant", "priority_policy"], ascending=[False, False, True, True, True]).iloc[0].to_dict()


def best_scheduler_d_result(results: pd.DataFrame) -> dict[str, Any]:
    if results.empty:
        return {}
    return results.sort_values(["positive_wf_test_folds_pct", "net_pnl", "best_day_concentration", "overlay_variant", "priority_policy"], ascending=[False, False, True, True, True]).iloc[0].to_dict()


def make_next_action_recommendation(results: pd.DataFrame, scheduler_b_best: dict[str, Any], scheduler_c_best: dict[str, Any], module_pruning_a_best: dict[str, Any]) -> dict[str, Any]:
    non_base = results[~results["overlay_variant"].eq("no_overlay_baseline")].copy()
    candidates = non_base[non_base["scheduler_d_label"].eq("scheduler_d_candidate_for_overlay_review_only")]
    best = best_scheduler_d_result(results)
    best_non_base = best_scheduler_d_result(non_base) if not non_base.empty else {}
    rep_div = non_base[non_base["overlay_variant"].eq("overlay_keep_representatives_plus_diversifiers")]
    exclude_parked = non_base[non_base["overlay_variant"].eq("overlay_exclude_parked")]
    priority_only = non_base[non_base["overlay_variant"].eq("overlay_priority_only")]
    deprio_only = non_base[non_base["overlay_variant"].eq("overlay_deprioritize_only")]
    seed_deprio = non_base[non_base["overlay_variant"].eq("overlay_seed_cluster_deprioritized")]
    seed_excl = non_base[non_base["overlay_variant"].eq("overlay_seed_cluster_excluded")]

    def has_fold_and_conc(frame: pd.DataFrame) -> bool:
        return bool(frame["scheduler_d_label"].isin(["scheduler_d_improves_folds_and_concentration", "scheduler_d_candidate_for_overlay_review_only"]).any()) if not frame.empty else False

    def best_net(frame: pd.DataFrame) -> float:
        row = best_scheduler_d_result(frame) if not frame.empty else {}
        return float(row.get("net_pnl", 0.0) or 0.0)

    exclusion_better = best_net(pd.concat([exclude_parked, rep_div, seed_excl], ignore_index=True)) > best_net(pd.concat([priority_only, deprio_only, seed_deprio], ignore_index=True))
    deprioritization_nearly = best_net(pd.concat([priority_only, deprio_only], ignore_index=True)) >= 0.90 * max(best_net(exclude_parked), best_net(rep_div), 1.0)
    broad_weak = int((results["weak_fold_count"] > 1).sum()) > len(results) // 2

    if not candidates.empty:
        action = "scheduler_d_overlay_review_packet_only"
        rationale = "At least one Scheduler D row met scheduler-overlay-review-only criteria; paper trading remains false."
    elif has_fold_and_conc(rep_div) or has_fold_and_conc(exclude_parked):
        action = "module_registry_c_apply_deprioritization_after_manual_review"
        rationale = "Representative/diversifier or parked-exclusion overlay improved folds and concentration without severe activity loss."
    elif deprioritization_nearly:
        action = "playbook_scheduler_e_deprioritization_policy_review"
        rationale = "Priority-only/deprioritization-only overlay performed nearly as well as exclusion."
    elif best_non_base.get("overlay_variant") in {"overlay_seed_cluster_deprioritized", "overlay_seed_cluster_excluded"} and str(best_non_base.get("scheduler_d_label", "")).startswith("scheduler_d_improves"):
        action = "mark_phase10b_seed_cluster_for_deprioritization_review"
        rationale = "Only Phase 10B seed-cluster overlay produced a material Scheduler D improvement."
    elif broad_weak:
        action = "validation_framework_audit_c_fold_design"
        rationale = "Fold instability remains broad across overlay variants."
    else:
        action = "phase16a_targeted_regime_module_scout"
        rationale = "Deduplication overlay did not replicate pruning improvement strongly enough."

    return {
        "next_action": action,
        "rationale": rationale,
        "best_overlay_variant": best.get("overlay_variant"),
        "best_priority_policy": best.get("priority_policy"),
        "best_portfolio_mode": best.get("portfolio_mode"),
        "best_scheduler_d_label": best.get("scheduler_d_label"),
        "best_net_pnl": best.get("net_pnl"),
        "folds_improved_vs_scheduler_c_best": bool((_float_or_none(best.get("positive_wf_test_folds_delta_vs_scheduler_c_best")) or 0.0) > 0),
        "concentration_improved_vs_scheduler_c_best": bool(((_float_or_none(best.get("best_day_concentration_delta_vs_scheduler_c_best")) or 0.0) < 0) and ((_float_or_none(best.get("best_trade_concentration_delta_vs_scheduler_c_best")) or 0.0) < 0)),
        "exclusion_worked_better_than_deprioritization": bool(exclusion_better),
        "deprioritization_worked_nearly_as_well_as_exclusion": bool(deprioritization_nearly),
        "scheduler_review_row_count": int(len(candidates)),
        "seed_suspect_module": SEED_SUSPECT_MODULE,
        "seed_cluster_decision": seed_cluster_decision(results),
        "official_gates_changed": False,
        "paper_trading_approved": False,
        "diagnostic_only_no_signals_generated": True,
        "live_trading_approved": False,
        "raw_sum_diagnostic_used_as_candidate": False,
        "weak_fold_regime_filters_used": False,
        "registry_mutation": False,
    }


def seed_cluster_decision(results: pd.DataFrame) -> str:
    seed_rows = results[results["overlay_variant"].isin(["overlay_seed_cluster_deprioritized", "overlay_seed_cluster_excluded"])]
    if seed_rows.empty:
        return "manually_reviewed"
    best = best_scheduler_d_result(seed_rows)
    label = str(best.get("scheduler_d_label", ""))
    if best.get("overlay_variant") == "overlay_seed_cluster_excluded" and label.startswith("scheduler_d_improves"):
        return "excluded"
    if best.get("overlay_variant") == "overlay_seed_cluster_deprioritized" and label.startswith("scheduler_d_improves"):
        return "deprioritized"
    if float(best.get("net_pnl", 0.0) or 0.0) > 0:
        return "manually_reviewed"
    return "retained"


def render_playbook_scheduler_d_report(result: dict[str, Any]) -> str:
    rec = result["next_action_recommendation"]
    best = best_scheduler_d_result(result["policy_results"])
    baseline = result["scheduler_c_best"]
    lines = [
        "# Playbook Scheduler D — Overlay Retest",
        "",
        RESEARCH_ONLY_GUARDRAIL,
        "",
        "Research-only scheduler-overlay retest using existing Deduplication B overlay, Scheduler C/B outputs, registries, and phase trade logs only. No new signals, no strategy searches, no candidate-result changes, no registry mutation, no official gate changes, no promotions, no paper-trading approval, and no live-trading functionality were added.",
        "",
        "## Summary",
        "",
        f"- Selected Scheduler C module universe: `{len(result['selected_signal_keys'])}`",
        f"- Seed suspect: `{result['seed_suspect_module']}`",
        f"- Seed cluster: `{';'.join(result['seed_cluster_modules'])}`",
        f"- Overlay variants tested: `{', '.join(OVERLAY_VARIANTS)}`",
        f"- Priority policies tested: `{', '.join(PRIORITY_POLICIES)}`",
        f"- Modes tested: `{', '.join(MODES)}`",
        f"- Best Scheduler C baseline: `{baseline.get('pruning_variant')}` / `{baseline.get('priority_policy')}` / `{baseline.get('portfolio_mode')}` net `{float(baseline.get('net_pnl', 0.0)):.2f}` pos folds `{float(baseline.get('positive_wf_test_folds_pct') or 0.0):.3f}` day conc `{float(baseline.get('best_day_concentration') or 0.0):.3f}` trade conc `{float(baseline.get('best_trade_concentration') or 0.0):.3f}`",
        f"- Best Scheduler D result: `{best.get('overlay_variant')}` / `{best.get('priority_policy')}` / `{best.get('portfolio_mode')}` net `{float(best.get('net_pnl', 0.0)):.2f}` pos folds `{float(best.get('positive_wf_test_folds_pct') or 0.0):.3f}` day conc `{float(best.get('best_day_concentration') or 0.0):.3f}` trade conc `{float(best.get('best_trade_concentration') or 0.0):.3f}` label `{best.get('scheduler_d_label')}`",
        f"- Next action: `{rec['next_action']}`",
        f"- Rationale: {rec['rationale']}",
        "- Paper trading approved: `false`",
        "",
        "## Required diagnostics",
        "",
        f"- Overlay improved folds vs Scheduler C best: `{rec['folds_improved_vs_scheduler_c_best']}`",
        f"- Overlay improved concentration vs Scheduler C best: `{rec['concentration_improved_vs_scheduler_c_best']}`",
        f"- Exclusion worked better than deprioritization: `{rec['exclusion_worked_better_than_deprioritization']}`",
        f"- Seed cluster decision: `{rec['seed_cluster_decision']}`",
        "- Registries were not mutated: `true`",
        "",
        "## Top Scheduler D rows",
        "",
        markdown_table(result["policy_results"].sort_values(["positive_wf_test_folds_pct", "net_pnl", "best_day_concentration"], ascending=[False, False, True]).head(25)),
        "",
        "## Overlay effect summary",
        "",
        markdown_table(result["overlay_effect_summary"]),
        "",
        "## Accepted/skipped modules under best overlay",
        "",
        markdown_table(best_overlay_acceptance(result).head(80)),
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


def best_overlay_acceptance(result: dict[str, Any]) -> pd.DataFrame:
    best = best_scheduler_d_result(result["policy_results"])
    acc = result["module_acceptance_summary"]
    return acc[
        acc["overlay_variant"].eq(best.get("overlay_variant"))
        & acc["priority_policy"].eq(best.get("priority_policy"))
        & acc["portfolio_mode"].eq(best.get("portfolio_mode"))
    ].copy()


def write_playbook_scheduler_d_outputs(result: dict[str, Any], output_dir: Path, report_path: Path) -> dict[str, Path]:
    ensure_directory(output_dir)
    ensure_directory(report_path.parent)
    mapping = {
        "policy_results": output_dir / "playbook_scheduler_d_overlay_policy_results.csv",
        "daily_pnl": output_dir / "playbook_scheduler_d_daily_pnl.csv",
        "walk_forward_folds": output_dir / "playbook_scheduler_d_walk_forward_folds.csv",
        "concentration": output_dir / "playbook_scheduler_d_concentration.csv",
        "overlap_summary": output_dir / "playbook_scheduler_d_overlap_summary.csv",
        "module_acceptance_summary": output_dir / "playbook_scheduler_d_module_acceptance_summary.csv",
        "overlay_effect_summary": output_dir / "playbook_scheduler_d_overlay_effect_summary.csv",
    }
    paths: dict[str, Path] = {}
    for key, path in mapping.items():
        write_csv_artifact(result[key], path)
        paths[key] = path
    rec_path = output_dir / "playbook_scheduler_d_next_action_recommendation.json"
    write_json_artifact(result["next_action_recommendation"], rec_path)
    report_path.write_text(render_playbook_scheduler_d_report(result), encoding="utf-8")
    paths["recommendation"] = rec_path
    paths["report"] = report_path
    return paths


def loaded_input_names() -> list[str]:
    return [
        "outputs/playbook_module_registry.csv",
        "outputs/research_signal_registry.csv",
        "outputs/playbook_module_deduplication_b_scheduler_overlay.json",
        "outputs/playbook_module_deduplication_b_redundancy_clusters.csv",
        "outputs/playbook_module_deduplication_b_module_review.csv",
        "outputs/playbook_module_deduplication_b_representative_modules.csv",
        "outputs/playbook_module_deduplication_b_deprioritization_candidates.csv",
        "outputs/playbook_module_deduplication_b_next_action_recommendation.json",
        "outputs/playbook_scheduler_c_pruning_policy_results.csv",
        "outputs/playbook_scheduler_c_daily_pnl.csv",
        "outputs/playbook_scheduler_c_walk_forward_folds.csv",
        "outputs/playbook_scheduler_c_concentration.csv",
        "outputs/playbook_scheduler_c_overlap_summary.csv",
        "outputs/playbook_scheduler_c_module_acceptance_summary.csv",
        "outputs/playbook_scheduler_c_pruned_module_summary.csv",
        "outputs/playbook_scheduler_c_next_action_recommendation.json",
        "outputs/playbook_scheduler_b_priority_policy_results.csv",
        "outputs/playbook_scheduler_b_daily_pnl.csv",
        "outputs/playbook_scheduler_b_walk_forward_folds.csv",
        "outputs/playbook_scheduler_b_concentration.csv",
        "outputs/playbook_scheduler_b_module_acceptance_summary.csv",
        "outputs/module_pruning_audit_a_portfolio_results.csv",
        *[f"outputs/{phase}_trade_logs.csv" for phase in PHASES],
    ]


def _overlay_list(overlay: dict[str, Any], key: str) -> list[str]:
    value = overlay.get(key, [])
    if not isinstance(value, list):
        return []
    return [str(v) for v in value if str(v)]


def _split_modules(value: Any) -> list[str]:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return []
    return [v for v in str(value).split(";") if v and v.lower() != "nan"]


def _stable_unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out


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
