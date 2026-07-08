from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from pathlib import Path
from typing import Any

import pandas as pd

from .phase_common import ensure_directory, safe_divide, write_csv_artifact, write_json_artifact

PHASES = ("phase10b", "phase11a", "phase12a")
PHASE_PRIORITY = {"phase10b": 0, "phase11a": 1, "phase12a": 2}
RESEARCH_ONLY_GUARDRAIL = "Research/simulation only. No live trading, broker adapters, order routing, webhooks, credential storage, automated execution, or LLM-driven trade decisions."
OFFICIAL_GATES = {
    "best_day_concentration": 0.15,
    "best_trade_concentration": 0.08,
    "positive_wf_test_folds_pct": 0.90,
    "min_active_days": 60,
}


@dataclass(frozen=True)
class PortfolioAuditAConfig:
    max_selected_signals: int = 20
    real_but_nontradable_cap: int = 12
    rare_setup_cap: int = 8


def load_portfolio_audit_inputs(output_dir: Path) -> dict[str, Any]:
    required = {
        "registry_csv": output_dir / "research_signal_registry.csv",
        "registry_json": output_dir / "research_signal_registry.json",
        "registry_recommendation": output_dir / "research_signal_registry_next_action_recommendation.json",
        "audit_c_selection": output_dir / "framework_audit_c_candidate_selection.csv",
        "audit_c_family_comparison": output_dir / "framework_audit_c_family_comparison.csv",
        "audit_c_recommendation": output_dir / "framework_audit_c_next_action_recommendation.json",
    }
    for phase in PHASES:
        required[f"{phase}_candidates"] = output_dir / f"{phase}_candidate_results.csv"
        required[f"{phase}_trades"] = output_dir / f"{phase}_trade_logs.csv"
        required[f"{phase}_daily"] = output_dir / f"{phase}_daily_pnl.csv"
        required[f"{phase}_folds"] = output_dir / f"{phase}_walk_forward_folds.csv"
    missing = [str(path) for path in required.values() if not path.exists()]
    if missing:
        raise FileNotFoundError(f"Missing Portfolio Audit A input(s): {missing}")
    data: dict[str, Any] = {}
    for key, path in required.items():
        data[key] = _read_json(path) if path.suffix == ".json" else pd.read_csv(path)
    return data


def run_portfolio_audit_a(output_dir: Path, config: PortfolioAuditAConfig = PortfolioAuditAConfig()) -> dict[str, pd.DataFrame | dict[str, Any]]:
    data = load_portfolio_audit_inputs(output_dir)
    selected = select_portfolio_signals(data, config)
    trades = _selected_trade_logs(data, selected)
    daily_matrix = build_daily_pnl_matrix(data, selected)
    correlation = signal_correlation(daily_matrix)
    overlap = trade_overlap_summary(trades)
    portfolio_results, portfolio_daily, portfolio_folds, portfolio_conc, portfolio_dd = build_portfolios(selected, trades, daily_matrix, correlation)
    recommendation = make_portfolio_recommendation(portfolio_results)
    return {
        "signal_selection": selected,
        "signal_correlation": correlation,
        "daily_pnl_matrix": daily_matrix,
        "trade_overlap_summary": overlap,
        "portfolio_results": portfolio_results,
        "portfolio_daily_pnl": portfolio_daily,
        "portfolio_walk_forward_folds": portfolio_folds,
        "portfolio_concentration": portfolio_conc,
        "portfolio_drawdown_summary": portfolio_dd,
        "next_action_recommendation": recommendation,
    }


def select_portfolio_signals(data: dict[str, Any], config: PortfolioAuditAConfig = PortfolioAuditAConfig()) -> pd.DataFrame:
    registry = data["registry_csv"].copy()
    audit_c = data["audit_c_selection"][["phase", "candidate_id", "phase_rank", "phase_score", "audit_c_rank"]].copy()
    enriched = registry.merge(audit_c, on=["phase", "candidate_id"], how="left")
    enriched["phase_rank"] = enriched["phase_rank"].fillna(9999)
    enriched["phase_score"] = enriched["phase_score"].fillna(enriched["stress_pnl"])
    enriched["audit_c_rank"] = enriched["audit_c_rank"].fillna(9999)
    rows: list[pd.Series] = []
    seen: set[tuple[str, str]] = set()

    for phase in PHASES:
        phase_rows = enriched[enriched["phase"].eq(phase)].sort_values(["audit_c_rank", "phase_rank", "candidate_id"])
        if not phase_rows.empty:
            _append_signal(rows, seen, phase_rows.iloc[0], "top_phase_parked_signal")

    real = enriched[enriched["signal_evidence_status"].eq("real_but_nontradable_signal")].sort_values(["phase_rank", "audit_c_rank", "candidate_id"], ascending=[True, True, True]).head(config.real_but_nontradable_cap)
    for _, row in real.iterrows():
        _append_signal(rows, seen, row, "real_but_nontradable_signal")

    rare = enriched[enriched["research_track"].eq("rare_setup_research_signal")].sort_values(["phase_rank", "audit_c_rank", "candidate_id"], ascending=[True, True, True]).head(config.rare_setup_cap)
    for _, row in rare.iterrows():
        _append_signal(rows, seen, row, "rare_setup_research_signal")

    selected = pd.DataFrame([r.to_dict() for r in rows[: config.max_selected_signals]])
    if selected.empty:
        return selected
    selected.insert(0, "selection_rank", range(1, len(selected) + 1))
    return selected


def build_daily_pnl_matrix(data: dict[str, Any], selected: pd.DataFrame) -> pd.DataFrame:
    parts = []
    for _, row in selected.iterrows():
        phase = str(row["phase"])
        cid = str(row["candidate_id"])
        daily = data[f"{phase}_daily"]
        seg = daily[daily["candidate_id"].astype(str).eq(cid)][["trading_session", "net_pnl"]].copy()
        if seg.empty:
            continue
        col = _signal_key(phase, cid)
        seg = seg.groupby("trading_session", as_index=False)["net_pnl"].sum().rename(columns={"net_pnl": col})
        parts.append(seg)
    if not parts:
        return pd.DataFrame(columns=["trading_session"])
    matrix = parts[0]
    for part in parts[1:]:
        matrix = matrix.merge(part, on="trading_session", how="outer")
    return matrix.fillna(0.0).sort_values("trading_session").reset_index(drop=True)


def signal_correlation(daily_matrix: pd.DataFrame) -> pd.DataFrame:
    value_cols = [c for c in daily_matrix.columns if c != "trading_session"]
    if not value_cols:
        return pd.DataFrame(columns=["signal_a", "signal_b", "daily_pnl_correlation"])
    corr = daily_matrix[value_cols].corr().fillna(0.0)
    rows = []
    for a in value_cols:
        for b in value_cols:
            rows.append({"signal_a": a, "signal_b": b, "daily_pnl_correlation": round(float(corr.loc[a, b]), 6)})
    return pd.DataFrame(rows)


def trade_overlap_summary(trades: pd.DataFrame) -> pd.DataFrame:
    if trades.empty:
        return pd.DataFrame(columns=["signal_key", "same_timestamp_overlap", "overlapping_holding_periods", "same_session_overlap"])
    rows = []
    for key, seg in trades.groupby("signal_key"):
        other = trades[~trades["signal_key"].eq(key)]
        same_ts = int(seg["entry_time"].isin(other["entry_time"]).sum())
        same_session = int(seg["trading_session"].isin(other["trading_session"]).sum())
        overlap = 0
        for _, t in seg.iterrows():
            mask = (other["entry_time"] < t["exit_time"]) & (other["exit_time"] > t["entry_time"])
            overlap += int(mask.sum())
        rows.append({"signal_key": key, "same_timestamp_overlap": same_ts, "overlapping_holding_periods": overlap, "same_session_overlap": same_session})
    return pd.DataFrame(rows).sort_values("signal_key").reset_index(drop=True)


def build_portfolios(selected: pd.DataFrame, trades: pd.DataFrame, daily_matrix: pd.DataFrame, correlation: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    sets = portfolio_sets(selected, daily_matrix, correlation)
    result_rows: list[dict[str, Any]] = []
    daily_rows: list[pd.DataFrame] = []
    fold_rows: list[pd.DataFrame] = []
    conc_rows: list[dict[str, Any]] = []
    dd_rows: list[dict[str, Any]] = []
    individual = _individual_baselines(selected)
    for set_name, signal_keys in sets.items():
        for mode in ("raw_sum_diagnostic", "one_trade_at_a_time_chronological", "max_one_trade_per_session"):
            accepted, skipped_overlap, skipped_session = construct_portfolio_trades(trades, signal_keys, mode)
            daily = _portfolio_daily_from_mode(daily_matrix, accepted, signal_keys, set_name, mode)
            metrics = portfolio_metrics(set_name, mode, signal_keys, accepted, daily, skipped_overlap, skipped_session, correlation, individual)
            result_rows.append(metrics)
            daily_rows.append(daily)
            fold_rows.append(_portfolio_folds(set_name, mode, daily))
            conc_rows.append(_portfolio_concentration_row(metrics))
            dd_rows.append({"portfolio_set": set_name, "portfolio_mode": mode, "max_drawdown": metrics["max_drawdown"]})
    return pd.DataFrame(result_rows), _concat(daily_rows), _concat(fold_rows), pd.DataFrame(conc_rows), pd.DataFrame(dd_rows)


def portfolio_sets(selected: pd.DataFrame, daily_matrix: pd.DataFrame, correlation: pd.DataFrame) -> dict[str, list[str]]:
    selected = selected.copy()
    selected["signal_key"] = selected.apply(lambda r: _signal_key(r["phase"], r["candidate_id"]), axis=1)
    sets: dict[str, list[str]] = {}
    top3 = []
    for phase in PHASES:
        seg = selected[selected["phase"].eq(phase)].sort_values(["selection_rank"])
        if not seg.empty:
            top3.append(str(seg.iloc[0]["signal_key"]))
    sets["top3_cross_family"] = top3
    for phase in PHASES:
        sets[f"{phase}_only_top_signals"] = selected[selected["phase"].eq(phase)]["signal_key"].astype(str).tolist()
    sets["parked_research_signals_all"] = selected[selected["research_track"].eq("parked_research_signal")]["signal_key"].astype(str).tolist()
    sets["rare_setup_research_signals_all"] = selected[selected["research_track"].eq("rare_setup_research_signal")]["signal_key"].astype(str).tolist()
    sets["diversified_low_correlation_top5"] = _greedy_low_corr(selected, correlation, limit=5)
    cross = []
    for phase in PHASES:
        phase_rows = selected[selected["phase"].eq(phase)].copy()
        phase_rows["evidence_priority"] = phase_rows["signal_evidence_status"].map({"real_but_nontradable_signal": 0}).fillna(1)
        cross.extend(phase_rows.sort_values(["evidence_priority", "selection_rank", "candidate_id"])["signal_key"].astype(str).head(2).tolist())
    sets["diversified_cross_family_top6"] = cross[:6]
    return sets


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


def portfolio_metrics(set_name: str, mode: str, signal_keys: list[str], trades: pd.DataFrame, daily: pd.DataFrame, skipped_overlap: int, skipped_session: int, correlation: pd.DataFrame, individual: pd.DataFrame) -> dict[str, Any]:
    net = round(float(daily["net_pnl"].sum()), 2) if not daily.empty else 0.0
    gross = round(float(trades["gross_pnl"].sum()), 2) if "gross_pnl" in trades else None
    stress = round(float(trades["stress_pnl"].sum()), 2) if "stress_pnl" in trades else None
    split = trades.groupby("split")["net_pnl"].sum().to_dict() if "split" in trades else {}
    validation = round(float(split.get("validation", 0.0)), 2) if split else None
    holdout = round(float(split.get("holdout", 0.0)), 2) if split else None
    folds = _portfolio_folds(set_name, mode, daily)
    wf_test = round(float(folds["net_pnl"].sum()), 2) if not folds.empty else None
    wf_stress = round(float(folds["stress_pnl"].sum()), 2) if not folds.empty else None
    pos_folds = round(safe_divide(int((folds["stress_pnl"] > 0).sum()), len(folds)), 6) if not folds.empty else None
    worst_fold = round(float(folds["stress_pnl"].min()), 2) if not folds.empty else None
    trade_conc = concentration(trades["net_pnl"] if not trades.empty else pd.Series(dtype=float))
    day_conc = concentration(daily["net_pnl"] if not daily.empty else pd.Series(dtype=float))
    corr_vals = _pairwise_corr_for(signal_keys, correlation)
    active_days = int(daily["trading_session"].nunique()) if not daily.empty else 0
    component = individual[individual["signal_key"].isin(signal_keys)]
    label, status = _portfolio_label_status(net, validation, holdout, wf_stress, pos_folds, day_conc["best"], trade_conc["best"], active_days, component)
    return {
        "portfolio_set": set_name,
        "portfolio_mode": mode,
        "signals": len(signal_keys),
        "signal_keys": ";".join(signal_keys),
        "gross_pnl": gross,
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
        "max_drawdown": max_drawdown(daily["net_pnl"] if not daily.empty else pd.Series(dtype=float)),
        "best_day_concentration": day_conc["best"],
        "best_trade_concentration": trade_conc["best"],
        "top_3_day_concentration": day_conc["top3"],
        "top_5_trade_concentration": trade_conc["top5"],
        "average_pairwise_daily_correlation": round(float(corr_vals.mean()), 6) if len(corr_vals) else 0.0,
        "max_pairwise_daily_correlation": round(float(corr_vals.max()), 6) if len(corr_vals) else 0.0,
        "trade_overlap_count": int(_overlap_count(trades)),
        "skipped_overlap_count": int(skipped_overlap),
        "skipped_session_count": int(skipped_session),
        "improves_concentration": bool(not component.empty and day_conc["best"] < float(component["best_day_concentration"].min())),
        "improves_folds": bool(pos_folds is not None and not component.empty and pos_folds > float(component["positive_wf_test_folds_pct"].max())),
        "improves_active_days": bool(not component.empty and active_days > int(component["active_days"].max())),
        "improves_drawdown": None,
        "portfolio_label": label,
        "research_status": status,
        "paper_trading_approved": False,
    }


def make_portfolio_recommendation(results: pd.DataFrame) -> dict[str, Any]:
    if results.empty:
        return {"next_action": "improve_standard_trade_log_schema_before_portfolio_work", "rationale": "No portfolio metrics were computable from existing outputs.", "paper_trading_approved": False}
    if bool(results["research_status"].eq("portfolio_candidate_for_future_review_packet").any()):
        return {"next_action": "portfolio_review_packet_only", "rationale": "At least one diagnostic portfolio passed portfolio gates, but paper trading is not approved.", "paper_trading_approved": False}
    conc_fold = results["improves_concentration"].astype(bool) & results["improves_folds"].astype(bool)
    if bool(conc_fold.any()):
        return {"next_action": "portfolio_audit_b_review_packet_only", "rationale": "Diversification improved concentration and fold stability but still misses at least one gate.", "paper_trading_approved": False}
    activity_only = bool(results["improves_active_days"].astype(bool).any())
    if activity_only:
        return {"next_action": "keep_registry_and_search_new_uncorrelated_families", "rationale": "Some combinations improve activity, but concentration/fold gates remain weak.", "paper_trading_approved": False}
    return {"next_action": "resume_new_family_research_after_framework_checkpoint", "rationale": "No diagnostic portfolio improved concentration, folds, or activity enough to justify portfolio follow-up.", "paper_trading_approved": False}


def render_portfolio_audit_report(result: dict[str, pd.DataFrame | dict[str, Any]], report_path: Path) -> str:
    results = result["portfolio_results"]
    rec = result["next_action_recommendation"]
    lines = ["# Portfolio Audit A — Research Signal Combination / Diversification Audit", "", RESEARCH_ONLY_GUARDRAIL, "", "## Summary", "", f"- Selected signals: `{len(result['signal_selection'])}`", f"- Portfolio rows: `{len(results)}`", f"- Next action: `{rec.get('next_action')}`", f"- Rationale: {rec.get('rationale')}", "- Paper trading approved: `false`", "", "## Portfolio Results", "", "| Set | Mode | Net | Active days | Best-day concentration | Positive folds | Label | Status |", "| --- | --- | ---: | ---: | ---: | ---: | --- | --- |"]
    if isinstance(results, pd.DataFrame) and not results.empty:
        for _, r in results.sort_values(["portfolio_label", "net_pnl"], ascending=[True, False]).head(20).iterrows():
            lines.append(f"| {r['portfolio_set']} | {r['portfolio_mode']} | {float(r['net_pnl']):.2f} | {int(r['active_days'])} | {float(r['best_day_concentration']):.3f} | {float(r['positive_wf_test_folds_pct'] or 0):.3f} | {r['portfolio_label']} | {r['research_status']} |")
    return "\n".join(lines) + "\n"


def write_portfolio_audit_outputs(result: dict[str, pd.DataFrame | dict[str, Any]], output_dir: Path, report_path: Path) -> dict[str, Path]:
    ensure_directory(output_dir)
    ensure_directory(report_path.parent)
    mapping = {
        "signal_selection": output_dir / "portfolio_audit_a_signal_selection.csv",
        "signal_correlation": output_dir / "portfolio_audit_a_signal_correlation.csv",
        "daily_pnl_matrix": output_dir / "portfolio_audit_a_daily_pnl_matrix.csv",
        "trade_overlap_summary": output_dir / "portfolio_audit_a_trade_overlap_summary.csv",
        "portfolio_results": output_dir / "portfolio_audit_a_portfolio_results.csv",
        "portfolio_daily_pnl": output_dir / "portfolio_audit_a_portfolio_daily_pnl.csv",
        "portfolio_walk_forward_folds": output_dir / "portfolio_audit_a_portfolio_walk_forward_folds.csv",
        "portfolio_concentration": output_dir / "portfolio_audit_a_portfolio_concentration.csv",
        "portfolio_drawdown_summary": output_dir / "portfolio_audit_a_portfolio_drawdown_summary.csv",
    }
    paths = {}
    for key, path in mapping.items():
        write_csv_artifact(result[key], path)  # type: ignore[arg-type]
        paths[key] = path
    rec = output_dir / "portfolio_audit_a_next_action_recommendation.json"
    write_json_artifact(result["next_action_recommendation"], rec)
    report_path.write_text(render_portfolio_audit_report(result, report_path), encoding="utf-8")
    paths["recommendation"] = rec
    paths["report"] = report_path
    return paths


def _selected_trade_logs(data: dict[str, Any], selected: pd.DataFrame) -> pd.DataFrame:
    parts = []
    for _, row in selected.iterrows():
        phase, cid = str(row["phase"]), str(row["candidate_id"])
        trades = data[f"{phase}_trades"]
        seg = trades[trades["candidate_id"].astype(str).eq(cid)].copy()
        if seg.empty:
            continue
        seg["phase"] = phase
        seg["family"] = row.get("family", phase)
        seg["signal_key"] = _signal_key(phase, cid)
        seg["phase_priority"] = PHASE_PRIORITY[phase]
        for col in ("entry_time", "exit_time"):
            seg[col] = pd.to_datetime(seg[col], errors="coerce", utc=True)
        parts.append(seg)
    return _concat(parts)


def _portfolio_daily_from_mode(daily_matrix: pd.DataFrame, accepted: pd.DataFrame, signal_keys: list[str], set_name: str, mode: str) -> pd.DataFrame:
    if mode == "raw_sum_diagnostic":
        cols = [c for c in signal_keys if c in daily_matrix.columns]
        daily = daily_matrix[["trading_session", *cols]].copy() if cols else pd.DataFrame(columns=["trading_session"])
        daily["net_pnl"] = daily[cols].sum(axis=1) if cols else 0.0
    else:
        daily = accepted.groupby("trading_session", as_index=False)["net_pnl"].sum() if not accepted.empty else pd.DataFrame(columns=["trading_session", "net_pnl"])
    daily["portfolio_set"] = set_name
    daily["portfolio_mode"] = mode
    return daily[["portfolio_set", "portfolio_mode", "trading_session", "net_pnl"]].sort_values("trading_session").reset_index(drop=True)


def _portfolio_folds(set_name: str, mode: str, daily: pd.DataFrame, folds: int = 6) -> pd.DataFrame:
    if daily.empty:
        return pd.DataFrame(columns=["portfolio_set", "portfolio_mode", "fold", "net_pnl", "stress_pnl", "active_days"])
    ordered = daily.sort_values("trading_session").reset_index(drop=True)
    chunks = []
    size = max(1, len(ordered) // folds)
    for idx in range(folds):
        start = idx * size
        end = len(ordered) if idx == folds - 1 else min(len(ordered), (idx + 1) * size)
        seg = ordered.iloc[start:end]
        if seg.empty:
            continue
        net = round(float(seg["net_pnl"].sum()), 2)
        chunks.append({"portfolio_set": set_name, "portfolio_mode": mode, "fold": idx + 1, "net_pnl": net, "stress_pnl": round(net - len(seg), 2), "active_days": int(seg["trading_session"].nunique())})
    return pd.DataFrame(chunks)


def _portfolio_label_status(net: float, validation: float | None, holdout: float | None, wf_stress: float | None, pos_folds: float | None, best_day: float, best_trade: float, active_days: int, component: pd.DataFrame) -> tuple[str, str]:
    if net <= 0:
        return "portfolio_audit_failed_negative", "no_portfolio_benefit"
    if best_day > OFFICIAL_GATES["best_day_concentration"] or best_trade > OFFICIAL_GATES["best_trade_concentration"]:
        status = "diversification_reduces_concentration" if not component.empty and best_day < float(component["best_day_concentration"].min()) else "portfolio_still_nontradable"
        return "portfolio_audit_positive_but_concentrated", status
    if pos_folds is not None and pos_folds < OFFICIAL_GATES["positive_wf_test_folds_pct"]:
        return "portfolio_audit_positive_but_fold_unstable", "diversification_improves_folds" if not component.empty and pos_folds > float(component["positive_wf_test_folds_pct"].max()) else "portfolio_still_nontradable"
    if active_days < OFFICIAL_GATES["min_active_days"]:
        return "portfolio_audit_positive_but_low_activity", "diversification_improves_activity"
    if (validation is None or validation > 0) and (holdout is None or holdout > 0) and (wf_stress is None or wf_stress > 0):
        return "portfolio_audit_improves_diversification_needs_review", "portfolio_candidate_for_future_review_packet"
    return "portfolio_audit_no_improvement", "portfolio_still_nontradable"


def _individual_baselines(selected: pd.DataFrame) -> pd.DataFrame:
    out = selected.copy()
    out["signal_key"] = out.apply(lambda r: _signal_key(r["phase"], r["candidate_id"]), axis=1)
    return out


def _greedy_low_corr(selected: pd.DataFrame, correlation: pd.DataFrame, limit: int) -> list[str]:
    eligible = selected[(selected["stress_pnl"] > 0) & (selected["validation_pnl"] > 0) & (selected["holdout_pnl"] > 0)].sort_values(["phase_rank", "audit_c_rank", "candidate_id"]).copy()
    if eligible.empty:
        return []
    chosen = [str(eligible.iloc[0]["signal_key"])]
    remaining = [str(v) for v in eligible["signal_key"].iloc[1:].tolist()]
    while remaining and len(chosen) < limit:
        remaining.sort(key=lambda sig: (_avg_abs_corr(sig, chosen, correlation), sig))
        chosen.append(remaining.pop(0))
    return chosen


def _avg_abs_corr(sig: str, chosen: list[str], correlation: pd.DataFrame) -> float:
    vals = []
    for other in chosen:
        row = correlation[correlation["signal_a"].eq(sig) & correlation["signal_b"].eq(other)]
        vals.append(abs(float(row.iloc[0]["daily_pnl_correlation"]))) if not row.empty else vals.append(1.0)
    return sum(vals) / len(vals) if vals else 0.0


def _pairwise_corr_for(signal_keys: list[str], correlation: pd.DataFrame) -> pd.Series:
    vals = []
    for a, b in combinations(signal_keys, 2):
        row = correlation[correlation["signal_a"].eq(a) & correlation["signal_b"].eq(b)]
        if not row.empty:
            vals.append(float(row.iloc[0]["daily_pnl_correlation"]))
    return pd.Series(vals, dtype=float)


def _overlap_count(trades: pd.DataFrame) -> int:
    count = 0
    rows = list(trades.itertuples())
    for i, a in enumerate(rows):
        for b in rows[i + 1 :]:
            if a.entry_time < b.exit_time and b.entry_time < a.exit_time:
                count += 1
    return count


def _portfolio_concentration_row(metrics: dict[str, Any]) -> dict[str, Any]:
    return {k: metrics[k] for k in ("portfolio_set", "portfolio_mode", "best_day_concentration", "best_trade_concentration", "top_3_day_concentration", "top_5_trade_concentration")}


def _append_signal(rows: list[pd.Series], seen: set[tuple[str, str]], row: pd.Series, reason: str) -> None:
    key = (str(row["phase"]), str(row["candidate_id"]))
    if key in seen:
        return
    item = row.copy()
    item["selection_reason"] = reason
    rows.append(item)
    seen.add(key)


def _signal_key(phase: str, candidate_id: str) -> str:
    return f"{phase}::{candidate_id}"


def _concat(parts: list[pd.DataFrame]) -> pd.DataFrame:
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()


def _read_json(path: Path) -> dict[str, Any]:
    import json

    return json.loads(path.read_text(encoding="utf-8"))
