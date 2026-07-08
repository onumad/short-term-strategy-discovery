from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
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
}


@dataclass(frozen=True)
class FrameworkAuditCConfig:
    iterations: int = 10_000
    top3_iterations: int = 50_000
    max_candidates: int = 20
    seed: int = 12_120
    use_top3_iterations: bool = True


def load_framework_audit_c_inputs(output_dir: Path, phases: tuple[str, ...] = PHASES) -> dict[str, dict[str, Any]]:
    loaded: dict[str, dict[str, Any]] = {}
    for phase in phases:
        files = {
            "candidate_results": output_dir / f"{phase}_candidate_results.csv",
            "trade_logs": output_dir / f"{phase}_trade_logs.csv",
            "daily_pnl": output_dir / f"{phase}_daily_pnl.csv",
            "walk_forward_folds": output_dir / f"{phase}_walk_forward_folds.csv",
            "recommendation": output_dir / f"{phase}_next_action_recommendation.json",
        }
        missing = [str(path) for path in files.values() if not path.exists()]
        if missing:
            raise FileNotFoundError(f"Missing Framework Audit C input(s) for {phase}: {missing}")
        loaded[phase] = {
            "candidate_results": pd.read_csv(files["candidate_results"]),
            "trade_logs": pd.read_csv(files["trade_logs"]),
            "daily_pnl": pd.read_csv(files["daily_pnl"]),
            "walk_forward_folds": pd.read_csv(files["walk_forward_folds"]),
            "recommendation": _read_json(files["recommendation"]),
        }
    audit_b_summary = output_dir / "framework_audit_b_research_signal_summary.csv"
    audit_b_rec = output_dir / "framework_audit_b_next_action_recommendation.json"
    if audit_b_summary.exists():
        loaded["framework_audit_b"] = {"research_signal_summary": pd.read_csv(audit_b_summary), "recommendation": _read_json(audit_b_rec) if audit_b_rec.exists() else {}}
    return loaded


def run_framework_audit_c(output_dir: Path, config: FrameworkAuditCConfig = FrameworkAuditCConfig()) -> dict[str, pd.DataFrame | dict[str, Any]]:
    data = load_framework_audit_c_inputs(output_dir)
    selected = select_audit_c_candidates(data, config.max_candidates)
    trade_boot = _bootstrap_summary(selected, data, config, level="trade")
    daily_boot = _bootstrap_summary(selected, data, config, level="daily")
    weekly_boot = _block_bootstrap_summary(selected, data, config, period="W")
    monthly_boot = _block_bootstrap_summary(selected, data, config, period="M")
    outlier = outlier_removal_summary(selected, data)
    gate_prob = gate_probability_summary(selected, trade_boot, daily_boot, weekly_boot, monthly_boot)
    nulls = null_baseline_summary(selected, data, config)
    family = family_comparison(selected, trade_boot, daily_boot, outlier, nulls)
    classified = classify_candidates(selected, trade_boot, daily_boot, outlier, nulls)
    recommendation = make_framework_audit_c_recommendation(classified, outlier, gate_prob, nulls)
    return {
        "candidate_selection": classified,
        "trade_bootstrap_summary": trade_boot,
        "daily_bootstrap_summary": daily_boot,
        "weekly_block_bootstrap_summary": weekly_boot,
        "monthly_block_bootstrap_summary": monthly_boot,
        "outlier_removal_summary": outlier,
        "gate_probability_summary": gate_prob,
        "null_baseline_summary": nulls,
        "family_comparison": family,
        "next_action_recommendation": recommendation,
    }


def select_audit_c_candidates(data: dict[str, dict[str, Any]], max_candidates: int = 20) -> pd.DataFrame:
    forced: list[dict[str, Any]] = []
    positive: list[dict[str, Any]] = []
    for phase in PHASES:
        c = data[phase]["candidate_results"].copy()
        c["phase"] = phase
        c["phase_rank"] = c.get(f"{phase}_rank", pd.Series(range(1, len(c) + 1))).astype(float)
        c["phase_score"] = _score_series(c, phase)
        c["phase_label"] = c.get(f"{phase}_label", "")
        rec_id = data[phase]["recommendation"].get("top_candidate", {}).get("candidate_id")
        top = c[c["candidate_id"].astype(str).eq(str(rec_id))].head(1) if rec_id else c.head(1)
        if top.empty:
            top = c.head(1)
        if not top.empty:
            item = top.iloc[0].to_dict()
            item["selected_reason"] = "recommendation_top_candidate"
            forced.append(item)
        mask = (c["stress_pnl"] > 0) & (c["validation_pnl"] > 0) & (c["holdout_pnl"] > 0) & (c["walk_forward_stress_pnl"] > 0)
        for _, row in c[mask].iterrows():
            item = row.to_dict()
            item["selected_reason"] = "positive_stress_validation_holdout_wf"
            positive.append(item)
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for item in forced:
        key = (str(item["phase"]), str(item["candidate_id"]))
        if key not in seen:
            seen.add(key)
            rows.append(item)
    positive_sorted = sorted(positive, key=lambda r: (-_f(r.get("phase_score")), _f(r.get("phase_rank")), str(r.get("phase"))))
    for item in positive_sorted:
        key = (str(item["phase"]), str(item["candidate_id"]))
        if key in seen:
            continue
        rows.append(item)
        seen.add(key)
        if len(rows) >= max_candidates:
            break
    out = pd.DataFrame(rows[:max_candidates])
    if not out.empty:
        out.insert(0, "audit_c_rank", range(1, len(out) + 1))
        cols = [
            "audit_c_rank",
            "phase",
            "candidate_id",
            "selected_reason",
            "phase_rank",
            "phase_score",
            "phase_label",
            "research_axis_status",
            "net_pnl",
            "stress_pnl",
            "validation_pnl",
            "holdout_pnl",
            "walk_forward_stress_pnl",
            "positive_wf_test_folds_pct",
            "trades",
            "active_days",
            "best_day_concentration",
            "best_trade_concentration",
            "reject_reasons",
        ]
        out = out[[c for c in cols if c in out.columns]]
    return out


def trade_bootstrap(values: list[float] | np.ndarray, *, iterations: int, seed: int, concentration_limit: float = 0.08) -> dict[str, Any]:
    return _bootstrap_values(np.asarray(values, dtype=float), iterations=iterations, seed=seed, concentration_limit=concentration_limit, active_limit=1)


def daily_bootstrap(values: list[float] | np.ndarray, *, iterations: int, seed: int, concentration_limit: float = 0.15, active_limit: int = 35) -> dict[str, Any]:
    return _bootstrap_values(np.asarray(values, dtype=float), iterations=iterations, seed=seed, concentration_limit=concentration_limit, active_limit=active_limit)


def outlier_removal_for_values(trades: pd.Series, daily: pd.Series) -> dict[str, Any]:
    trade_values = pd.Series(trades, dtype=float).sort_values(ascending=False)
    daily_values = pd.Series(daily, dtype=float).sort_values(ascending=False)
    net = round(float(trade_values.sum()), 2)
    return {
        "net_pnl": net,
        "pnl_without_best_trade": round(net - float(trade_values.head(1).sum()), 2),
        "pnl_without_top3_trades": round(net - float(trade_values.head(3).sum()), 2),
        "pnl_without_top5_trades": round(net - float(trade_values.head(5).sum()), 2),
        "pnl_without_best_day": round(net - float(daily_values.head(1).sum()), 2),
        "pnl_without_top3_days": round(net - float(daily_values.head(3).sum()), 2),
        "pnl_without_top5_days": round(net - float(daily_values.head(5).sum()), 2),
    }


def gate_probability(summary: dict[str, Any], *, pnl_threshold: float = 0.0, concentration_probability_floor: float = 0.5) -> bool:
    return bool(float(summary.get("prob_pnl_gt_0", 0.0)) > pnl_threshold and float(summary.get("prob_concentration_within_limit", 0.0)) >= concentration_probability_floor)


def null_baseline_for_values(candidate_value: float, distribution: list[float] | np.ndarray) -> dict[str, Any]:
    values = np.asarray(distribution, dtype=float)
    if values.size == 0:
        return {"candidate_value": candidate_value, "null_percentile": 0.0, "beats_null_median": False, "beats_null_75th": False}
    percentile = float((values <= candidate_value).mean())
    return {
        "candidate_value": round(float(candidate_value), 2),
        "null_percentile": round(percentile, 6),
        "beats_null_median": bool(candidate_value > np.percentile(values, 50)),
        "beats_null_75th": bool(candidate_value > np.percentile(values, 75)),
    }


def _bootstrap_summary(selected: pd.DataFrame, data: dict[str, dict[str, Any]], config: FrameworkAuditCConfig, *, level: str) -> pd.DataFrame:
    rows = []
    for _, r in selected.iterrows():
        phase = str(r["phase"])
        cid = str(r["candidate_id"])
        iterations = _iterations_for_rank(int(r["audit_c_rank"]), config)
        if level == "trade":
            values = _candidate_trades(data, phase, cid)["net_pnl"].to_numpy(dtype=float)
            stats = trade_bootstrap(values, iterations=iterations, seed=config.seed + int(r["audit_c_rank"]), concentration_limit=OFFICIAL_GATES["best_trade_concentration"])
        else:
            values = _candidate_daily(data, phase, cid).to_numpy(dtype=float)
            stats = daily_bootstrap(values, iterations=iterations, seed=config.seed + 1000 + int(r["audit_c_rank"]), concentration_limit=OFFICIAL_GATES["best_day_concentration"], active_limit=OFFICIAL_GATES["min_active_days"])
        rows.append({"phase": phase, "candidate_id": cid, "iterations": iterations, **stats})
    return pd.DataFrame(rows)


def _block_bootstrap_summary(selected: pd.DataFrame, data: dict[str, dict[str, Any]], config: FrameworkAuditCConfig, *, period: str) -> pd.DataFrame:
    rows = []
    for _, r in selected.iterrows():
        phase = str(r["phase"])
        cid = str(r["candidate_id"])
        daily = _candidate_daily_frame(data, phase, cid)
        if daily.empty:
            blocks = np.asarray([], dtype=float)
        else:
            dates = pd.to_datetime(daily["trading_session"], errors="coerce")
            key = dates.dt.to_period(period).astype(str)
            blocks = daily.assign(block=key).groupby("block")["net_pnl"].sum().to_numpy(dtype=float)
        iterations = _iterations_for_rank(int(r["audit_c_rank"]), config)
        stats = _bootstrap_values(blocks, iterations=iterations, seed=config.seed + (2000 if period == "W" else 3000) + int(r["audit_c_rank"]), concentration_limit=1.0, active_limit=1)
        rows.append({"phase": phase, "candidate_id": cid, "period": "weekly" if period == "W" else "monthly", "iterations": iterations, "blocks": len(blocks), **stats, "fold_like_stability_prob": stats["prob_pnl_gt_0"]})
    return pd.DataFrame(rows)


def outlier_removal_summary(selected: pd.DataFrame, data: dict[str, dict[str, Any]]) -> pd.DataFrame:
    rows = []
    for _, r in selected.iterrows():
        phase = str(r["phase"])
        cid = str(r["candidate_id"])
        trades = _candidate_trades(data, phase, cid)["net_pnl"]
        daily = _candidate_daily(data, phase, cid)
        vals = outlier_removal_for_values(trades, daily)
        rows.append(
            {
                "phase": phase,
                "candidate_id": cid,
                **vals,
                "positive_without_best_trade": vals["pnl_without_best_trade"] > 0,
                "positive_without_top3_trades": vals["pnl_without_top3_trades"] > 0,
                "positive_without_top5_trades": vals["pnl_without_top5_trades"] > 0,
                "positive_without_best_day": vals["pnl_without_best_day"] > 0,
                "positive_without_top3_days": vals["pnl_without_top3_days"] > 0,
                "positive_without_top5_days": vals["pnl_without_top5_days"] > 0,
            }
        )
    return pd.DataFrame(rows)


def gate_probability_summary(selected: pd.DataFrame, trade_boot: pd.DataFrame, daily_boot: pd.DataFrame, weekly_boot: pd.DataFrame, monthly_boot: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, r in selected.iterrows():
        phase = str(r["phase"])
        cid = str(r["candidate_id"])
        t = trade_boot[trade_boot["candidate_id"].eq(cid)].iloc[0]
        d = daily_boot[daily_boot["candidate_id"].eq(cid)].iloc[0]
        w = weekly_boot[weekly_boot["candidate_id"].eq(cid)].iloc[0]
        m = monthly_boot[monthly_boot["candidate_id"].eq(cid)].iloc[0]
        rows.append(
            {
                "phase": phase,
                "candidate_id": cid,
                "trade_positive_prob": float(t["prob_pnl_gt_0"]),
                "daily_positive_prob": float(d["prob_pnl_gt_0"]),
                "weekly_positive_prob": float(w["prob_pnl_gt_0"]),
                "monthly_positive_prob": float(m["prob_pnl_gt_0"]),
                "trade_concentration_gate_prob": float(t["prob_concentration_within_limit"]),
                "daily_concentration_gate_prob": float(d["prob_concentration_within_limit"]),
                "active_day_gate_prob": float(d["prob_active_count_ge_limit"]),
                "all_bootstrap_positive_prob_min": min(float(t["prob_pnl_gt_0"]), float(d["prob_pnl_gt_0"]), float(w["prob_pnl_gt_0"]), float(m["prob_pnl_gt_0"])),
                "diagnostic_gate_probability_pass": bool(float(t["prob_pnl_gt_0"]) >= 0.70 and float(d["prob_pnl_gt_0"]) >= 0.70 and float(d["prob_active_count_ge_limit"]) >= 0.50),
            }
        )
    return pd.DataFrame(rows)


def null_baseline_summary(selected: pd.DataFrame, data: dict[str, dict[str, Any]], config: FrameworkAuditCConfig) -> pd.DataFrame:
    rows = []
    for _, r in selected.iterrows():
        phase = str(r["phase"])
        cid = str(r["candidate_id"])
        cands = data[phase]["candidate_results"]
        phase_dist = cands["stress_pnl"].to_numpy(dtype=float)
        phase_null = null_baseline_for_values(float(r["stress_pnl"]), phase_dist)
        trades = data[phase]["trade_logs"]
        side = r.get("side", None)
        pool = trades.copy()
        if side is not None and "side" in pool.columns:
            side_pool = pool[pool["side"].astype(str).eq(str(side))]
            if not side_pool.empty:
                pool = side_pool
        n_trades = max(1, int(_f(r.get("trades"))))
        trade_null = _pool_null(pool.get("net_pnl", pd.Series(dtype=float)).to_numpy(dtype=float), n_trades, config.seed + 4000 + int(r["audit_c_rank"]), min(config.iterations, 10_000), float(r["net_pnl"]))
        daily_pool = data[phase]["daily_pnl"].get("net_pnl", pd.Series(dtype=float)).to_numpy(dtype=float)
        n_days = max(1, int(_f(r.get("active_days"))))
        daily_null = _pool_null(daily_pool, n_days, config.seed + 5000 + int(r["audit_c_rank"]), min(config.iterations, 10_000), float(r["net_pnl"]))
        rows.append(
            {
                "phase": phase,
                "candidate_id": cid,
                "phase_stress_null_percentile": phase_null["null_percentile"],
                "beats_phase_stress_median": phase_null["beats_null_median"],
                "beats_phase_stress_75th": phase_null["beats_null_75th"],
                "trade_pool_null_pnl_gt_candidate_prob": trade_null["prob_null_ge_candidate"],
                "daily_pool_null_pnl_gt_candidate_prob": daily_null["prob_null_ge_candidate"],
                "beats_trade_pool_null_95": trade_null["beats_null_95"],
                "beats_daily_pool_null_95": daily_null["beats_null_95"],
                "matched_random_entry_skipped": True,
                "matched_random_entry_skip_reason": "Random-entry raw-bar backtester intentionally skipped; audit uses existing phase trade/daily pools only.",
            }
        )
    return pd.DataFrame(rows)


def family_comparison(selected: pd.DataFrame, trade_boot: pd.DataFrame, daily_boot: pd.DataFrame, outlier: pd.DataFrame, nulls: pd.DataFrame) -> pd.DataFrame:
    if selected.empty:
        return pd.DataFrame()
    merged = selected.merge(trade_boot[["candidate_id", "prob_pnl_gt_0"]].rename(columns={"prob_pnl_gt_0": "trade_positive_prob"}), on="candidate_id", how="left")
    merged = merged.merge(daily_boot[["candidate_id", "prob_pnl_gt_0"]].rename(columns={"prob_pnl_gt_0": "daily_positive_prob"}), on="candidate_id", how="left")
    merged = merged.merge(outlier[["candidate_id", "positive_without_top3_trades", "positive_without_top3_days"]], on="candidate_id", how="left")
    merged = merged.merge(nulls[["candidate_id", "phase_stress_null_percentile"]], on="candidate_id", how="left")
    return (
        merged.groupby("phase")
        .agg(
            candidates=("candidate_id", "size"),
            avg_stress_pnl=("stress_pnl", "mean"),
            avg_validation_pnl=("validation_pnl", "mean"),
            avg_holdout_pnl=("holdout_pnl", "mean"),
            avg_trade_positive_prob=("trade_positive_prob", "mean"),
            avg_daily_positive_prob=("daily_positive_prob", "mean"),
            positive_without_top3_trades_count=("positive_without_top3_trades", "sum"),
            positive_without_top3_days_count=("positive_without_top3_days", "sum"),
            avg_phase_null_percentile=("phase_stress_null_percentile", "mean"),
        )
        .reset_index()
        .sort_values("avg_daily_positive_prob", ascending=False)
    )


def classify_candidates(selected: pd.DataFrame, trade_boot: pd.DataFrame, daily_boot: pd.DataFrame, outlier: pd.DataFrame, nulls: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, r in selected.iterrows():
        cid = str(r["candidate_id"])
        t = trade_boot[trade_boot["candidate_id"].eq(cid)].iloc[0]
        d = daily_boot[daily_boot["candidate_id"].eq(cid)].iloc[0]
        o = outlier[outlier["candidate_id"].eq(cid)].iloc[0]
        n = nulls[nulls["candidate_id"].eq(cid)].iloc[0]
        classification = _classification(r, t, d, o, n)
        rows.append({**r.to_dict(), "audit_c_classification": classification})
    return pd.DataFrame(rows)


def make_framework_audit_c_recommendation(classified: pd.DataFrame, outlier: pd.DataFrame, gate_prob: pd.DataFrame, nulls: pd.DataFrame) -> dict[str, Any]:
    if classified.empty:
        return {"next_action": "pause_strategy_search_and_build_null_baseline_framework", "rationale": "No candidates available for Framework Audit C."}
    beats_null = bool((nulls["beats_phase_stress_75th"] | nulls["beats_trade_pool_null_95"] | nulls["beats_daily_pool_null_95"]).any())
    if not beats_null:
        return {"next_action": "pause_strategy_search_and_build_null_baseline_framework", "rationale": "No audited signal beats the available within-phase or pool null baselines."}
    robust = outlier["positive_without_top3_trades"].astype(bool) & outlier["positive_without_top3_days"].astype(bool)
    if not bool(robust.any()) and float(gate_prob["all_bootstrap_positive_prob_min"].max()) < 0.55:
        return {"next_action": "pause_strategy_search_and_review_framework", "rationale": "All candidates fail outlier removal and bootstrap odds are weak."}
    class_counts = classified["audit_c_classification"].value_counts().to_dict()
    if class_counts.get("priority_research_signal_for_more_data", 0) >= 2 or class_counts.get("real_but_nontradable_signal", 0) >= 3:
        return {"next_action": "create_two_tier_research_signal_labeling", "rationale": "Several signals remain positive under bootstrap/outlier diagnostics but fail concentration, activity, or fold gates."}
    if class_counts.get("framework_gate_too_strict_possible", 0) > 0:
        return {"next_action": "revise_research_labels_not_promotion_gates", "rationale": "Bootstrap evidence is stronger than official research labels for at least one signal; promotion gates remain unchanged."}
    by_phase = classified.groupby("phase")["audit_c_classification"].apply(lambda s: int(s.isin(["priority_research_signal_for_more_data", "real_but_nontradable_signal"]).sum()))
    if not by_phase.empty and by_phase.max() > 0 and (by_phase == by_phase.max()).sum() == 1:
        return {"next_action": "preserve_priority_family_for_more_data", "rationale": f"{by_phase.idxmax()} dominates the audited candidates under bootstrap/outlier classification."}
    return {"next_action": "pause_strategy_search_and_review_framework", "rationale": "Bootstrap evidence is mixed and does not justify further strategy expansion."}


def render_framework_audit_c_report(result: dict[str, pd.DataFrame | dict[str, Any]], report_path: Path) -> str:
    selected = result["candidate_selection"]
    rec = result["next_action_recommendation"]
    lines = [
        "# Framework Audit C — Null / Bootstrap Research Signal Audit",
        "",
        RESEARCH_ONLY_GUARDRAIL,
        "",
        "## Summary",
        "",
        f"- Audit candidates: `{len(selected) if isinstance(selected, pd.DataFrame) else 0}`",
        f"- Next action: `{rec.get('next_action')}`",
        f"- Rationale: {rec.get('rationale')}",
        "- Matched random-entry raw-bar backtester: skipped; existing trade/daily pools used for null baselines.",
        "",
        "## Candidate Classifications",
        "",
        "| Phase | Candidate | Classification | Net | Stress | Val | Holdout |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: |",
    ]
    if isinstance(selected, pd.DataFrame) and not selected.empty:
        for _, r in selected.iterrows():
            lines.append(f"| {r['phase']} | `{r['candidate_id']}` | {r['audit_c_classification']} | {float(r['net_pnl']):.2f} | {float(r['stress_pnl']):.2f} | {float(r['validation_pnl']):.2f} | {float(r['holdout_pnl']):.2f} |")
    lines += [
        "",
        "## Outputs",
        "",
        "- `outputs/framework_audit_c_candidate_selection.csv`",
        "- `outputs/framework_audit_c_trade_bootstrap_summary.csv`",
        "- `outputs/framework_audit_c_daily_bootstrap_summary.csv`",
        "- `outputs/framework_audit_c_weekly_block_bootstrap_summary.csv`",
        "- `outputs/framework_audit_c_monthly_block_bootstrap_summary.csv`",
        "- `outputs/framework_audit_c_outlier_removal_summary.csv`",
        "- `outputs/framework_audit_c_gate_probability_summary.csv`",
        "- `outputs/framework_audit_c_null_baseline_summary.csv`",
        "- `outputs/framework_audit_c_family_comparison.csv`",
        "- `outputs/framework_audit_c_next_action_recommendation.json`",
        f"- `{report_path.as_posix()}`",
    ]
    return "\n".join(lines) + "\n"


def write_framework_audit_c_outputs(result: dict[str, pd.DataFrame | dict[str, Any]], output_dir: Path, report_path: Path) -> dict[str, Path]:
    ensure_directory(output_dir)
    ensure_directory(report_path.parent)
    mapping = {
        "candidate_selection": output_dir / "framework_audit_c_candidate_selection.csv",
        "trade_bootstrap_summary": output_dir / "framework_audit_c_trade_bootstrap_summary.csv",
        "daily_bootstrap_summary": output_dir / "framework_audit_c_daily_bootstrap_summary.csv",
        "weekly_block_bootstrap_summary": output_dir / "framework_audit_c_weekly_block_bootstrap_summary.csv",
        "monthly_block_bootstrap_summary": output_dir / "framework_audit_c_monthly_block_bootstrap_summary.csv",
        "outlier_removal_summary": output_dir / "framework_audit_c_outlier_removal_summary.csv",
        "gate_probability_summary": output_dir / "framework_audit_c_gate_probability_summary.csv",
        "null_baseline_summary": output_dir / "framework_audit_c_null_baseline_summary.csv",
        "family_comparison": output_dir / "framework_audit_c_family_comparison.csv",
    }
    paths: dict[str, Path] = {}
    for key, path in mapping.items():
        write_csv_artifact(result[key], path)  # type: ignore[arg-type]
        paths[key] = path
    rec_path = output_dir / "framework_audit_c_next_action_recommendation.json"
    write_json_artifact(result["next_action_recommendation"], rec_path)
    report_path.write_text(render_framework_audit_c_report(result, report_path), encoding="utf-8")
    paths["recommendation"] = rec_path
    paths["report"] = report_path
    return paths


def create_research_signal_registry(output_dir: Path, report_dir: Path) -> dict[str, Path]:
    audit_c = pd.read_csv(output_dir / "framework_audit_c_candidate_selection.csv")
    top = audit_c.sort_values(["phase", "audit_c_rank"]).groupby("phase", as_index=False).head(3).copy()
    rows = []
    for _, r in top.iterrows():
        rows.append(
            {
                "phase": r["phase"],
                "candidate_id": r["candidate_id"],
                "family": _family(r),
                "plain_english_rule": _plain_english_rule(r),
                "net_pnl": r["net_pnl"],
                "stress_pnl": r["stress_pnl"],
                "validation_pnl": r["validation_pnl"],
                "holdout_pnl": r["holdout_pnl"],
                "walk_forward_stress_pnl": r["walk_forward_stress_pnl"],
                "positive_wf_test_folds_pct": r["positive_wf_test_folds_pct"],
                "trades": r["trades"],
                "active_days": r["active_days"],
                "best_day_concentration": r["best_day_concentration"],
                "best_trade_concentration": r["best_trade_concentration"],
                "signal_evidence_status": _signal_evidence_status(r),
                "tradability_status": _tradability_status(r),
                "research_track": _research_track(r),
                "revisit_condition": _revisit_condition(r),
                "source_report": f"reports/{r['phase']}_research_signal_packet.md",
            }
        )
    registry = pd.DataFrame(rows)
    reg_path = output_dir / "research_signal_registry.csv"
    write_csv_artifact(registry, reg_path)
    report_path = report_dir / "research_signal_registry_report.md"
    report_path.write_text(_registry_report(registry), encoding="utf-8")
    for phase in PHASES:
        packet_path = report_dir / f"{phase}_research_signal_packet.md"
        phase_rows = registry[registry["phase"].eq(phase)]
        packet_path.write_text(_packet_report(phase, phase_rows), encoding="utf-8")
    return {"registry": reg_path, "report": report_path, **{f"{phase}_packet": report_dir / f"{phase}_research_signal_packet.md" for phase in PHASES}}


def recommendation_to_json(recommendation: dict[str, Any]) -> str:
    return deterministic_json(recommendation)


def _bootstrap_values(values: np.ndarray, *, iterations: int, seed: int, concentration_limit: float, active_limit: int) -> dict[str, Any]:
    values = values[np.isfinite(values)]
    if values.size == 0:
        return _empty_bootstrap(iterations)
    rng = np.random.default_rng(seed)
    draws = rng.choice(values, size=(int(iterations), int(values.size)), replace=True)
    totals = draws.sum(axis=1)
    positives = np.where(draws > 0, draws, 0.0)
    positive_sum = positives.sum(axis=1)
    max_positive = positives.max(axis=1)
    concentration = np.divide(max_positive, positive_sum, out=np.ones_like(max_positive), where=positive_sum > 0)
    active_count = (draws != 0).sum(axis=1)
    return {
        "sample_count": int(values.size),
        "observed_pnl": round(float(values.sum()), 2),
        "prob_pnl_gt_0": round(float((totals > 0).mean()), 6),
        "p05": round(float(np.percentile(totals, 5)), 2),
        "p25": round(float(np.percentile(totals, 25)), 2),
        "p50": round(float(np.percentile(totals, 50)), 2),
        "p75": round(float(np.percentile(totals, 75)), 2),
        "p95": round(float(np.percentile(totals, 95)), 2),
        "mean_pnl": round(float(totals.mean()), 2),
        "prob_concentration_within_limit": round(float((concentration <= concentration_limit).mean()), 6),
        "prob_active_count_ge_limit": round(float((active_count >= active_limit).mean()), 6),
    }


def _pool_null(pool: np.ndarray, sample_size: int, seed: int, iterations: int, candidate_value: float) -> dict[str, Any]:
    pool = pool[np.isfinite(pool)]
    if pool.size == 0:
        return {"prob_null_ge_candidate": 1.0, "beats_null_95": False}
    rng = np.random.default_rng(seed)
    draws = rng.choice(pool, size=(int(iterations), int(sample_size)), replace=True).sum(axis=1)
    return {"prob_null_ge_candidate": round(float((draws >= candidate_value).mean()), 6), "beats_null_95": bool(candidate_value > np.percentile(draws, 95))}


def _empty_bootstrap(iterations: int) -> dict[str, Any]:
    return {"sample_count": 0, "observed_pnl": 0.0, "prob_pnl_gt_0": 0.0, "p05": 0.0, "p25": 0.0, "p50": 0.0, "p75": 0.0, "p95": 0.0, "mean_pnl": 0.0, "prob_concentration_within_limit": 0.0, "prob_active_count_ge_limit": 0.0}


def _iterations_for_rank(rank: int, config: FrameworkAuditCConfig) -> int:
    if config.use_top3_iterations and rank <= 3:
        return max(int(config.iterations), int(config.top3_iterations))
    return int(config.iterations)


def _candidate_trades(data: dict[str, dict[str, Any]], phase: str, cid: str) -> pd.DataFrame:
    trades = data[phase]["trade_logs"]
    return trades[trades["candidate_id"].astype(str).eq(str(cid))].copy()


def _candidate_daily_frame(data: dict[str, dict[str, Any]], phase: str, cid: str) -> pd.DataFrame:
    daily = data[phase]["daily_pnl"]
    return daily[daily["candidate_id"].astype(str).eq(str(cid))].copy()


def _candidate_daily(data: dict[str, dict[str, Any]], phase: str, cid: str) -> pd.Series:
    daily = _candidate_daily_frame(data, phase, cid)
    return daily.get("net_pnl", pd.Series(dtype=float))


def _score_series(c: pd.DataFrame, phase: str) -> pd.Series:
    col = f"{phase}_score"
    if col in c.columns:
        return c[col]
    return c.get("stress_pnl", pd.Series([0] * len(c)))


def _classification(r: pd.Series, trade_boot: pd.Series, daily_boot: pd.Series, outlier: pd.Series, nulls: pd.Series) -> str:
    if min(_f(r.get("stress_pnl")), _f(r.get("validation_pnl")), _f(r.get("holdout_pnl"))) <= 0:
        return "likely_noise" if _f(trade_boot.get("prob_pnl_gt_0")) < 0.60 else "weak_research_signal"
    robust_outlier = bool(outlier.get("positive_without_top3_trades")) and bool(outlier.get("positive_without_top3_days"))
    boot_ok = _f(trade_boot.get("prob_pnl_gt_0")) >= 0.70 and _f(daily_boot.get("prob_pnl_gt_0")) >= 0.70
    null_ok = bool(nulls.get("beats_phase_stress_75th")) or bool(nulls.get("beats_trade_pool_null_95")) or bool(nulls.get("beats_daily_pool_null_95"))
    concentration_ok = _f(r.get("best_day_concentration")) <= 0.20 and _f(r.get("best_trade_concentration")) <= 0.12
    activity_ok = _f(r.get("active_days")) >= 60 and _f(r.get("trades")) >= 60
    if robust_outlier and boot_ok and null_ok and concentration_ok and activity_ok:
        return "priority_research_signal_for_more_data"
    if robust_outlier and boot_ok and null_ok:
        return "real_but_nontradable_signal"
    if boot_ok and null_ok and concentration_ok:
        return "framework_gate_too_strict_possible"
    return "weak_research_signal"


def _family(r: pd.Series) -> str:
    if "phase10b" == str(r.get("phase")):
        return "overnight_range"
    if "phase11a" == str(r.get("phase")):
        return "opening_range_fade"
    return "opening_drive_pullback"


def _plain_english_rule(r: pd.Series) -> str:
    phase = str(r.get("phase"))
    if phase == "phase10b":
        return "MNQ overnight-range breakout/fade research signal using existing Phase 10B deterministic filters."
    if phase == "phase11a":
        return "MNQ opening-range fade after stricter inside-confirmation with next-open entry semantics."
    return "MNQ RTH opening-drive continuation after the first deterministic pullback with next-open entry semantics."


def _signal_evidence_status(r: pd.Series) -> str:
    if _f(r.get("stress_pnl")) <= 0:
        return "no_signal"
    if str(r.get("audit_c_classification")) == "priority_research_signal_for_more_data":
        return "robust_research_signal"
    if min(_f(r.get("validation_pnl")), _f(r.get("holdout_pnl")), _f(r.get("walk_forward_stress_pnl"))) > 0:
        return "positive_research_signal"
    return "weak_signal"


def _tradability_status(r: pd.Series) -> str:
    if _f(r.get("stress_pnl")) <= 0:
        return "not_tradable_negative"
    if _f(r.get("active_days")) < 60 or _f(r.get("trades")) < 60:
        return "not_tradable_low_activity"
    if _f(r.get("best_day_concentration")) > 0.15 or _f(r.get("best_trade_concentration")) > 0.08:
        return "not_tradable_concentrated"
    if _f(r.get("positive_wf_test_folds_pct")) < 0.90:
        return "not_tradable_fold_unstable"
    return "watchlist_needs_more_history"


def _research_track(r: pd.Series) -> str:
    if str(r.get("audit_c_classification")) == "priority_research_signal_for_more_data":
        return "priority_research_signal_for_more_data"
    if _f(r.get("active_days")) < 75:
        return "rare_setup_research_signal"
    if min(_f(r.get("stress_pnl")), _f(r.get("validation_pnl")), _f(r.get("holdout_pnl"))) > 0:
        return "parked_research_signal"
    return "regular_practice_candidate"


def _revisit_condition(r: pd.Series) -> str:
    if _f(r.get("active_days")) < 75:
        return "Revisit only after materially more sessions increase active-day sample without changing rules."
    if _f(r.get("best_day_concentration")) > 0.15 or _f(r.get("best_trade_concentration")) > 0.08:
        return "Revisit only if additional data reduces top-day/trade concentration under official gates."
    return "Revisit only after fold stability improves under unchanged official gates."


def _registry_report(registry: pd.DataFrame) -> str:
    lines = ["# Research Signal Registry", "", RESEARCH_ONLY_GUARDRAIL, "", f"Signals tracked: `{len(registry)}`", "", "| Phase | Candidate | Evidence | Tradability | Track |", "| --- | --- | --- | --- | --- |"]
    for _, r in registry.iterrows():
        lines.append(f"| {r['phase']} | `{r['candidate_id']}` | {r['signal_evidence_status']} | {r['tradability_status']} | {r['research_track']} |")
    return "\n".join(lines) + "\n"


def _packet_report(phase: str, rows: pd.DataFrame) -> str:
    lines = [f"# {phase.upper()} Research Signal Packet", "", RESEARCH_ONLY_GUARDRAIL, ""]
    if rows.empty:
        lines.append("No registry rows available for this phase.\n")
        return "\n".join(lines)
    top = rows.iloc[0]
    lines += [
        "## Plain-English Rule",
        "",
        str(top["plain_english_rule"]),
        "",
        "## Key Metrics",
        "",
        f"- Candidate: `{top['candidate_id']}`",
        f"- Net / Stress / Validation / Holdout / WF Stress: `{top['net_pnl']} / {top['stress_pnl']} / {top['validation_pnl']} / {top['holdout_pnl']} / {top['walk_forward_stress_pnl']}`",
        f"- Trades / active days: `{top['trades']} / {top['active_days']}`",
        f"- Concentration day/trade: `{top['best_day_concentration']} / {top['best_trade_concentration']}`",
        "",
        "## What Worked",
        "",
        "Positive research evidence exists only where shown by unchanged historical outputs and bootstrap audit artifacts.",
        "",
        "## Why It Failed Promotion",
        "",
        str(top["tradability_status"]),
        "",
        "## Signal Evidence Status",
        "",
        str(top["signal_evidence_status"]),
        "",
        "## Tradability Status",
        "",
        str(top["tradability_status"]),
        "",
        "## Research Track",
        "",
        str(top["research_track"]),
        "",
        "## Conditions Required Before Revisiting",
        "",
        str(top["revisit_condition"]),
    ]
    return "\n".join(lines) + "\n"


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
