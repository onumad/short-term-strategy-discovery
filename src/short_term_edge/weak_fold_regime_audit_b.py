from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import json

import pandas as pd

from .data_loader import discover_data_files, load_ohlcv_csv
from .phase_common import ensure_directory, write_csv_artifact, write_json_artifact

RESEARCH_ONLY_GUARDRAIL = (
    "Research/simulation only. No live trading, broker adapters, order routing, webhooks, "
    "credential storage, automated execution, or LLM-driven trade decisions."
)
AUDITS = ("b", "c", "d")
PHASES = ("phase10b", "phase11a", "phase12a", "phase13a", "phase14a", "phase15a")
REALISTIC_MODES = ("one_trade_at_a_time_chronological", "max_one_trade_per_session")
PHASE_GROUP_LABELS = {
    "phase10b": "phase10b overnight/prior-level branch",
    "phase11a": "phase11a opening range fade",
    "phase12a": "phase12a opening-drive pullback",
    "phase13a": "phase13a prior RTH high/low breakout",
    "phase14a": "phase14a prior RTH midpoint/close reaction",
    "phase15a": "phase15a trend/power continuation",
}


@dataclass(frozen=True)
class WeakFoldRegimeAuditBConfig:
    weak_fold_threshold: float = 0.0
    large_negative_quantile: float = 0.10
    fold_count_default: int = 6


def load_weak_fold_regime_audit_b_inputs(project_root: Path) -> dict[str, Any]:
    output_dir = project_root / "outputs"
    required: dict[str, Path] = {
        "module_registry": output_dir / "playbook_module_registry.csv",
        "research_registry": output_dir / "research_signal_registry.csv",
    }
    for audit in AUDITS:
        prefix = f"portfolio_audit_{audit}"
        for suffix in (
            "portfolio_results",
            "portfolio_daily_pnl",
            "portfolio_walk_forward_folds",
            "portfolio_concentration",
            "portfolio_drawdown_summary",
            "incremental_contribution",
            "next_action_recommendation",
        ):
            ext = ".json" if suffix == "next_action_recommendation" else ".csv"
            required[f"audit_{audit}_{suffix}"] = output_dir / f"{prefix}_{suffix}{ext}"
    for phase in PHASES:
        required[f"{phase}_daily"] = output_dir / f"{phase}_daily_pnl.csv"
        required[f"{phase}_trades"] = output_dir / f"{phase}_trade_logs.csv"
    missing = [str(path) for path in required.values() if not path.exists()]
    if missing:
        raise FileNotFoundError(f"Missing Weak Fold Regime Audit B input(s): {missing}")
    data: dict[str, Any] = {}
    for key, path in required.items():
        data[key] = _read_json(path) if path.suffix == ".json" else pd.read_csv(path)
    data["market_features"] = build_market_regime_features(project_root / "data" / "raw")
    return data


def run_weak_fold_regime_audit_b(project_root: Path, config: WeakFoldRegimeAuditBConfig = WeakFoldRegimeAuditBConfig()) -> dict[str, Any]:
    data = load_weak_fold_regime_audit_b_inputs(project_root)
    selected = selected_module_keys(data)
    module_daily = build_selected_module_daily_matrix(data, selected)
    module_trades = build_selected_module_trade_matrix(data, selected)
    fold_summary = build_fold_failure_map(data, module_daily, config)
    weak_days = extract_weak_fold_days(data, fold_summary, module_daily, config)
    market_features = data["market_features"]
    portfolio_sessions = sessions_from_fold_summary(fold_summary, module_daily)
    regime_comparison = compare_weak_vs_non_weak_regimes(weak_days, market_features, module_trades, portfolio_sessions)
    contribution_by_fold = build_module_contribution_by_fold(fold_summary, module_daily)
    contribution_by_regime = build_module_contribution_by_regime(module_daily, market_features, weak_days, fold_summary)
    overlap_diag = build_overlap_and_scheduler_diagnostics(data, fold_summary, module_trades, module_daily)
    bad_clusters = build_bad_day_clusters(weak_days, market_features)
    remedies = build_candidate_remedies(fold_summary, weak_days, regime_comparison, contribution_by_regime, overlap_diag)
    recommendation = make_next_action_recommendation(fold_summary, weak_days, regime_comparison, contribution_by_regime, overlap_diag, remedies)
    return {
        "fold_summary": fold_summary,
        "weak_fold_days": weak_days,
        "market_regime_features": market_features,
        "regime_comparison": regime_comparison,
        "module_contribution_by_fold": contribution_by_fold,
        "module_contribution_by_regime": contribution_by_regime,
        "overlap_and_scheduler_diagnostics": overlap_diag,
        "bad_day_clusters": bad_clusters,
        "candidate_remedies": remedies,
        "next_action_recommendation": recommendation,
        "selected_modules": selected,
    }


def selected_module_keys(data: dict[str, Any]) -> pd.DataFrame:
    registry = data["module_registry"].copy()
    if "signal_key" not in registry.columns:
        registry["signal_key"] = registry.apply(lambda r: f"{r['phase']}::{r['candidate_id']}", axis=1)
    keys: set[str] = set()
    for audit in AUDITS:
        results = data[f"audit_{audit}_portfolio_results"]
        for value in results.get("signal_keys", pd.Series(dtype=str)).fillna(""):
            keys |= {k for k in str(value).split(";") if k}
    return registry[registry["signal_key"].isin(keys)].copy().sort_values(["phase", "candidate_id"]).reset_index(drop=True)


def build_selected_module_daily_matrix(data: dict[str, Any], selected: pd.DataFrame) -> pd.DataFrame:
    parts: list[pd.DataFrame] = []
    for _, row in selected.iterrows():
        phase, cid, key = str(row["phase"]), str(row["candidate_id"]), str(row["signal_key"])
        daily = data.get(f"{phase}_daily", pd.DataFrame())
        if daily.empty or "candidate_id" not in daily.columns:
            continue
        seg = daily[daily["candidate_id"].astype(str).eq(cid)].copy()
        if seg.empty:
            continue
        value_col = "net_pnl" if "net_pnl" in seg.columns else "pnl"
        grouped = seg.groupby("trading_session", as_index=False)[value_col].sum().rename(columns={value_col: key})
        parts.append(grouped)
    if not parts:
        return pd.DataFrame(columns=["trading_session"])
    out = parts[0]
    for part in parts[1:]:
        out = out.merge(part, on="trading_session", how="outer")
    return out.fillna(0.0).sort_values("trading_session").reset_index(drop=True)


def build_selected_module_trade_matrix(data: dict[str, Any], selected: pd.DataFrame) -> pd.DataFrame:
    rows: list[pd.DataFrame] = []
    selected_keys = set(selected["signal_key"].astype(str)) if not selected.empty else set()
    for phase in PHASES:
        trades = data.get(f"{phase}_trades", pd.DataFrame()).copy()
        if trades.empty or "candidate_id" not in trades.columns:
            continue
        trades["phase"] = phase
        trades["signal_key"] = trades["candidate_id"].astype(str).map(lambda cid: f"{phase}::{cid}")
        trades = trades[trades["signal_key"].isin(selected_keys)]
        if trades.empty:
            continue
        if "entry_time" in trades.columns:
            trades["entry_time_utc"] = pd.to_datetime(trades["entry_time"], utc=True, errors="coerce")
        if "exit_time" in trades.columns:
            trades["exit_time_utc"] = pd.to_datetime(trades["exit_time"], utc=True, errors="coerce")
        rows.append(trades)
    if not rows:
        return pd.DataFrame(columns=["trading_session", "phase", "signal_key", "net_pnl"])
    return pd.concat(rows, ignore_index=True, sort=False)


def build_fold_failure_map(data: dict[str, Any], module_daily: pd.DataFrame, config: WeakFoldRegimeAuditBConfig) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for audit in AUDITS:
        folds = data[f"audit_{audit}_portfolio_walk_forward_folds"]
        daily = data[f"audit_{audit}_portfolio_daily_pnl"]
        results = data[f"audit_{audit}_portfolio_results"]
        drawdowns = data[f"audit_{audit}_portfolio_drawdown_summary"]
        for _, fold in folds.iterrows():
            portfolio_set = str(fold["portfolio_set"])
            mode = str(fold["portfolio_mode"])
            fold_num = int(fold["fold"])
            pdaily = daily[(daily["portfolio_set"].astype(str).eq(portfolio_set)) & (daily["portfolio_mode"].astype(str).eq(mode))].sort_values("trading_session")
            sessions = fold_sessions_for(pdaily, fold_num, config.fold_count_default)
            contrib = module_contributions_for_sessions(module_daily, sessions, portfolio_keys_for(results, portfolio_set, mode))
            pos = [k for k, v in contrib.items() if v > 0]
            neg = [k for k, v in contrib.items() if v < 0]
            result_row = _single_match(results, portfolio_set, mode)
            dd_row = _single_match(drawdowns, portfolio_set, mode)
            stress = _float_or_none(fold.get("stress_pnl"))
            pnl = float(fold.get("net_pnl", 0.0))
            rows.append({
                "audit": audit.upper(),
                "portfolio_set": portfolio_set,
                "portfolio_mode": mode,
                "fold": fold_num,
                "fold_start": sessions[0] if sessions else None,
                "fold_end": sessions[-1] if sessions else None,
                "fold_pnl": pnl,
                "fold_stress_pnl": stress,
                "fold_active_days": int(fold.get("active_days", 0)),
                "fold_trade_count": int(result_row.get("trades", 0)) if result_row is not None else 0,
                "fold_drawdown": _float_or_none(dd_row.get("max_drawdown")) if dd_row is not None else None,
                "modules_positive_pnl": ";".join(sorted(pos)),
                "modules_negative_pnl": ";".join(sorted(neg)),
                "negative_module_count": len(neg),
                "positive_module_count": len(pos),
                "is_weak_fold": bool((stress is not None and stress <= config.weak_fold_threshold) or pnl <= config.weak_fold_threshold),
                "weak_fold_key": f"{portfolio_set}|{mode}|{fold_num}",
            })
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    weak_counts = out[out["is_weak_fold"]].groupby(["portfolio_mode", "fold"]).size().rename("same_mode_fold_weak_count_across_bcd").reset_index()
    out = out.merge(weak_counts, on=["portfolio_mode", "fold"], how="left")
    out["same_fold_remains_weak_across_bcd"] = out["same_mode_fold_weak_count_across_bcd"].fillna(0).ge(2)
    return out.sort_values(["is_weak_fold", "audit", "portfolio_mode", "fold"], ascending=[False, True, True, True]).reset_index(drop=True)


def extract_weak_fold_days(data: dict[str, Any], fold_summary: pd.DataFrame, module_daily: pd.DataFrame, config: WeakFoldRegimeAuditBConfig) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    weak = fold_summary[fold_summary["is_weak_fold"]].copy()
    for _, fold in weak.iterrows():
        audit = str(fold["audit"]).lower()
        daily = data[f"audit_{audit}_portfolio_daily_pnl"]
        results = data[f"audit_{audit}_portfolio_results"]
        portfolio_set = str(fold["portfolio_set"])
        mode = str(fold["portfolio_mode"])
        pdaily = daily[(daily["portfolio_set"].astype(str).eq(portfolio_set)) & (daily["portfolio_mode"].astype(str).eq(mode))].sort_values("trading_session")
        sessions = fold_sessions_for(pdaily, int(fold["fold"]), config.fold_count_default)
        if not sessions:
            continue
        seg = pdaily[pdaily["trading_session"].astype(str).isin(sessions)].copy().sort_values("trading_session")
        neg_values = seg[seg["net_pnl"] < 0]["net_pnl"]
        large_cutoff = float(neg_values.quantile(config.large_negative_quantile)) if not neg_values.empty else -999999.0
        keys = portfolio_keys_for(results, portfolio_set, mode)
        mod = module_daily[module_daily["trading_session"].astype(str).isin(sessions)].copy() if not module_daily.empty else pd.DataFrame()
        for _, day in seg.iterrows():
            session = str(day["trading_session"])
            pnl = float(day.get("net_pnl", 0.0))
            contrib = module_contributions_for_sessions(mod, [session], keys)
            phase_vals = phase_contribution_values(contrib)
            rows.append({
                "audit": str(fold["audit"]),
                "portfolio_set": portfolio_set,
                "portfolio_mode": mode,
                "fold": int(fold["fold"]),
                "trading_session": session,
                "daily_playbook_pnl": pnl,
                "day_classification": classify_day(pnl, large_cutoff),
                "phase10b_pnl": phase_vals["phase10b"],
                "phase11a_pnl": phase_vals["phase11a"],
                "phase12a_pnl": phase_vals["phase12a"],
                "phase13a_pnl": phase_vals["phase13a"],
                "phase14a_pnl": phase_vals["phase14a"],
                "phase15a_pnl": phase_vals["phase15a"],
                "phase13a_helped_or_hurt": helped_hurt(phase_vals["phase13a"]),
                "phase14a_helped_or_hurt": helped_hurt(phase_vals["phase14a"]),
                "phase15a_helped_or_hurt": helped_hurt(phase_vals["phase15a"]),
                "module_contribution_detail": ";".join(f"{k}={v:.2f}" for k, v in sorted(contrib.items()) if abs(v) > 1e-9),
                "module_overlap_count": int(sum(1 for v in contrib.values() if abs(v) > 1e-9)),
            })
    return pd.DataFrame(rows).sort_values(["audit", "portfolio_mode", "fold", "trading_session"]).reset_index(drop=True) if rows else pd.DataFrame()


def build_market_regime_features(raw_dir: Path) -> pd.DataFrame:
    files = [p for p in discover_data_files(raw_dir) if "mnq" in p.name.lower()]
    if not files:
        return pd.DataFrame(columns=["trading_session"])
    df = pd.concat([load_ohlcv_csv(path) for path in files], ignore_index=True)
    df = df[df["symbol"].astype(str).str.upper().str.contains("MNQ")]
    rth = df[df["session_segment"].eq("RTH")].sort_values(["trading_session", "timestamp"]).copy()
    if rth.empty:
        return pd.DataFrame(columns=["trading_session"])
    daily = rth.groupby("trading_session", sort=True).agg(
        rth_open=("open", "first"), rth_high=("high", "max"), rth_low=("low", "min"), rth_close=("close", "last")
    )
    daily["rth_range"] = daily["rth_high"] - daily["rth_low"]
    daily["prior_rth_close"] = daily["rth_close"].shift(1)
    daily["prior_rth_midpoint"] = ((daily["rth_high"] + daily["rth_low"]) / 2.0).shift(1)
    daily["prior_rth_high"] = daily["rth_high"].shift(1)
    daily["prior_rth_low"] = daily["rth_low"].shift(1)
    range_median = float(daily["rth_range"].median()) if not daily.empty else 0.0
    rows: list[dict[str, Any]] = []
    for session, day in rth.groupby("trading_session", sort=True):
        d = daily.loc[session]
        r = float(d["rth_range"])
        close_pos = float((d["rth_close"] - d["rth_low"]) / r) if r > 0 else 0.5
        first30 = time_slice(day, "09:30", "10:00")
        first60 = time_slice(day, "09:30", "10:30")
        morning = time_slice(day, "09:30", "12:00")
        afternoon = time_slice(day, "13:00", "16:00")
        lunch = time_slice(day, "11:30", "13:00")
        power = time_slice(day, "14:30", "15:45")
        prior_close_relation = relation(float(d["rth_open"]), d["prior_rth_close"])
        prior_mid_relation = relation(float(d["rth_open"]), d["prior_rth_midpoint"])
        prior_interaction = bool(
            (pd.notna(d["prior_rth_high"]) and float(d["rth_high"]) >= float(d["prior_rth_high"]))
            or (pd.notna(d["prior_rth_low"]) and float(d["rth_low"]) <= float(d["prior_rth_low"]))
        )
        lunch_range = segment_range(lunch)
        power_range = segment_range(power)
        rows.append({
            "trading_session": str(session),
            "rth_open": float(d["rth_open"]),
            "rth_high": float(d["rth_high"]),
            "rth_low": float(d["rth_low"]),
            "rth_close": float(d["rth_close"]),
            "rth_range": r,
            "rth_close_position": round(close_pos, 6),
            "first_30m_direction": direction(first30),
            "first_30m_range": segment_range(first30),
            "first_60m_direction": direction(first60),
            "first_60m_range": segment_range(first60),
            "morning_trend_proxy": bool(abs(segment_direction_value(morning)) >= max(r * 0.35, 1e-9)),
            "afternoon_trend_proxy": bool(abs(segment_direction_value(afternoon)) >= max(r * 0.35, 1e-9)),
            "full_day_trend_proxy": bool(close_pos >= 0.80 or close_pos <= 0.20),
            "intraday_reversal_proxy": bool(direction(first60) != "flat" and direction(first60) != direction(day) and abs(segment_direction_value(first60)) >= max(r * 0.20, 1e-9)),
            "range_day_proxy": bool(0.35 <= close_pos <= 0.65 and r <= range_median),
            "high_volatility_bucket": bool(r >= range_median * 1.25) if range_median else False,
            "low_volatility_bucket": bool(r <= range_median * 0.75) if range_median else False,
            "volatility_bucket": "high" if range_median and r >= range_median * 1.25 else "low" if range_median and r <= range_median * 0.75 else "normal",
            "power_hour_range": power_range,
            "power_hour_direction": direction(power),
            "power_hour_expansion": bool(power_range >= r * 0.35) if r else False,
            "lunch_range": lunch_range,
            "lunch_expansion": bool(lunch_range >= r * 0.35) if r else False,
            "lunch_compression": bool(lunch_range <= r * 0.15) if r else False,
            "prior_rth_close_relation": prior_close_relation,
            "prior_rth_midpoint_relation": prior_mid_relation,
            "prior_rth_high_low_interaction_flag": prior_interaction,
        })
    return pd.DataFrame(rows)


def compare_weak_vs_non_weak_regimes(weak_days: pd.DataFrame, market_features: pd.DataFrame, module_trades: pd.DataFrame, portfolio_sessions: set[str] | None = None) -> pd.DataFrame:
    if market_features.empty:
        return pd.DataFrame()
    weak_sessions = set(weak_days["trading_session"].astype(str)) if not weak_days.empty else set()
    traded_sessions = set(module_trades["trading_session"].astype(str)) if not module_trades.empty and "trading_session" in module_trades.columns else set()
    universe = portfolio_sessions if portfolio_sessions is not None else (weak_sessions | traded_sessions)
    if universe:
        market_features = market_features[market_features["trading_session"].astype(str).isin(universe)].copy()
    overlap_counts = module_trades.groupby("trading_session")["signal_key"].nunique().to_dict() if not module_trades.empty else {}
    rows = []
    for label, seg in (("weak_fold_days", market_features[market_features["trading_session"].astype(str).isin(weak_sessions)]), ("non_weak_fold_days", market_features[~market_features["trading_session"].astype(str).isin(weak_sessions)])):
        if seg.empty:
            rows.append(empty_regime_row(label))
            continue
        sessions = seg["trading_session"].astype(str).tolist()
        rows.append({
            "cohort": label,
            "day_count": int(len(seg)),
            "average_rth_range": round(float(seg["rth_range"].mean()), 6),
            "average_close_position": round(float(seg["rth_close_position"].mean()), 6),
            "trend_day_frequency": frequency(seg["full_day_trend_proxy"]),
            "reversal_day_frequency": frequency(seg["intraday_reversal_proxy"]),
            "range_day_frequency": frequency(seg["range_day_proxy"]),
            "high_vol_frequency": frequency(seg["high_volatility_bucket"]),
            "low_vol_frequency": frequency(seg["low_volatility_bucket"]),
            "power_hour_expansion_frequency": frequency(seg["power_hour_expansion"]),
            "lunch_compression_frequency": frequency(seg["lunch_compression"]),
            "lunch_expansion_frequency": frequency(seg["lunch_expansion"]),
            "prior_level_interaction_frequency": frequency(seg["prior_rth_high_low_interaction_flag"]),
            "no_trade_frequency": round(float(sum(1 for s in sessions if s not in traded_sessions) / len(sessions)), 6),
            "module_overlap_frequency": round(float(sum(1 for s in sessions if int(overlap_counts.get(s, 0)) > 1) / len(sessions)), 6),
        })
    return pd.DataFrame(rows)


def build_module_contribution_by_fold(fold_summary: pd.DataFrame, module_daily: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for _, fold in fold_summary.iterrows():
        sessions = sessions_between(str(fold.get("fold_start")), str(fold.get("fold_end")), module_daily)
        contrib = phase_contribution_values(module_contributions_for_sessions(module_daily, sessions, None))
        for phase, value in contrib.items():
            rows.append({
                "audit": fold["audit"],
                "portfolio_set": fold["portfolio_set"],
                "portfolio_mode": fold["portfolio_mode"],
                "fold": int(fold["fold"]),
                "is_weak_fold": bool(fold["is_weak_fold"]),
                "module_group": PHASE_GROUP_LABELS[phase],
                "phase": phase,
                "net_pnl_contribution": round(float(value), 6),
            })
    return pd.DataFrame(rows)


def build_module_contribution_by_regime(module_daily: pd.DataFrame, market_features: pd.DataFrame, weak_days: pd.DataFrame, fold_summary: pd.DataFrame | None = None) -> pd.DataFrame:
    if market_features.empty:
        return pd.DataFrame(columns=["regime", "phase", "module_group", "net_pnl_contribution", "active_days"])
    weak_sessions = set(weak_days["trading_session"].astype(str)) if not weak_days.empty else set()
    strong_sessions: set[str] = set()
    if fold_summary is not None and not fold_summary.empty:
        for _, row in fold_summary[~fold_summary["is_weak_fold"].fillna(False)].iterrows():
            strong_sessions.update(sessions_between(str(row.get("fold_start")), str(row.get("fold_end")), module_daily))
    regimes = {
        "weak_folds": market_features["trading_session"].astype(str).isin(weak_sessions),
        "strong_folds_or_nonweak_days": market_features["trading_session"].astype(str).isin(strong_sessions) if strong_sessions else ~market_features["trading_session"].astype(str).isin(weak_sessions),
        "high_vol_days": market_features["high_volatility_bucket"].fillna(False),
        "range_days": market_features["range_day_proxy"].fillna(False),
        "trend_days": market_features["full_day_trend_proxy"].fillna(False),
        "power_hour_expansion_days": market_features["power_hour_expansion"].fillna(False),
    }
    rows: list[dict[str, Any]] = []
    for regime, mask in regimes.items():
        sessions = market_features.loc[mask, "trading_session"].astype(str).tolist()
        contrib = phase_contribution_values(module_contributions_for_sessions(module_daily, sessions, None))
        active = phase_active_days(module_daily, sessions)
        for phase, value in contrib.items():
            rows.append({
                "regime": regime,
                "phase": phase,
                "module_group": PHASE_GROUP_LABELS[phase],
                "net_pnl_contribution": round(float(value), 6),
                "active_days": int(active.get(phase, 0)),
                "consistently_hurts_weak_folds": bool(regime == "weak_folds" and value < 0),
            })
    return pd.DataFrame(rows)


def build_overlap_and_scheduler_diagnostics(data: dict[str, Any], fold_summary: pd.DataFrame, module_trades: pd.DataFrame, module_daily: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    if module_trades.empty:
        return pd.DataFrame(columns=["audit", "portfolio_set", "portfolio_mode", "fold"])
    day_counts = module_trades.groupby("trading_session")["signal_key"].nunique().to_dict()
    for _, fold in fold_summary.iterrows():
        audit = str(fold["audit"]).lower()
        results = data[f"audit_{audit}_portfolio_results"]
        portfolio_set = str(fold["portfolio_set"])
        mode = str(fold["portfolio_mode"])
        sessions = sessions_between(str(fold.get("fold_start")), str(fold.get("fold_end")), module_daily)
        result_row = _single_match(results, portfolio_set, mode)
        trade_seg = module_trades[module_trades["trading_session"].astype(str).isin(sessions)].copy()
        overlap_days = [s for s in sessions if int(day_counts.get(s, 0)) > 1]
        high_move_no_trade_days = 0
        early_loss_later_help_count = 0
        for session, day in trade_seg.groupby("trading_session"):
            day = day.sort_values(["entry_time_utc", "phase", "candidate_id"], na_position="last")
            if len(day) > 1 and float(day.iloc[0].get("net_pnl", 0.0)) < 0 and float(day.iloc[1:]["net_pnl"].sum()) > 0:
                early_loss_later_help_count += 1
        rows.append({
            "audit": str(fold["audit"]),
            "portfolio_set": portfolio_set,
            "portfolio_mode": mode,
            "fold": int(fold["fold"]),
            "is_weak_fold": bool(fold["is_weak_fold"]),
            "overlap_days": int(len(overlap_days)),
            "overlap_day_frequency": round(float(len(overlap_days) / len(sessions)), 6) if sessions else 0.0,
            "avg_modules_firing_per_day": round(float(sum(int(day_counts.get(s, 0)) for s in sessions) / len(sessions)), 6) if sessions else 0.0,
            "trade_overlap_count_portfolio_level": int(result_row.get("trade_overlap_count", 0)) if result_row is not None else 0,
            "skipped_overlap_count_portfolio_level": int(result_row.get("skipped_overlap_count", 0)) if result_row is not None else 0,
            "skipped_session_count_portfolio_level": int(result_row.get("skipped_session_count", 0)) if result_row is not None else 0,
            "early_losing_module_when_later_module_helped_days": int(early_loss_later_help_count),
            "diagnosis_overlap_priority_risk": bool(len(overlap_days) > 0 or (result_row is not None and int(result_row.get("skipped_overlap_count", 0)) > 0)),
            "diagnosis_max_one_session_suppression_risk": bool(mode == "max_one_trade_per_session" and result_row is not None and int(result_row.get("skipped_session_count", 0)) > 0),
            "high_movement_no_trade_days": int(high_move_no_trade_days),
        })
    return pd.DataFrame(rows)


def build_bad_day_clusters(weak_days: pd.DataFrame, market_features: pd.DataFrame) -> pd.DataFrame:
    if weak_days.empty:
        return pd.DataFrame(columns=["cluster_key", "day_count", "total_pnl"])
    merged = weak_days.merge(market_features, on="trading_session", how="left") if not market_features.empty else weak_days.copy()
    keys = []
    for _, row in merged.iterrows():
        parts = []
        parts.append("high_vol" if bool(row.get("high_volatility_bucket", False)) else "low_vol" if bool(row.get("low_volatility_bucket", False)) else "normal_vol")
        parts.append("trend" if bool(row.get("full_day_trend_proxy", False)) else "range" if bool(row.get("range_day_proxy", False)) else "mixed")
        parts.append("power_expand" if bool(row.get("power_hour_expansion", False)) else "no_power_expand")
        keys.append("|".join(parts))
    merged["cluster_key"] = keys
    out = merged.groupby("cluster_key", as_index=False).agg(
        day_count=("trading_session", "nunique"),
        total_pnl=("daily_playbook_pnl", "sum"),
        avg_pnl=("daily_playbook_pnl", "mean"),
        large_negative_days=("day_classification", lambda s: int((s == "large_negative").sum())),
    )
    return out.sort_values(["total_pnl", "day_count"]).reset_index(drop=True)


def build_candidate_remedies(fold_summary: pd.DataFrame, weak_days: pd.DataFrame, regime_comparison: pd.DataFrame, contribution_by_regime: pd.DataFrame, overlap_diag: pd.DataFrame) -> list[dict[str, Any]]:
    remedies: list[dict[str, Any]] = []
    weak_regime_row = _cohort_row(regime_comparison, "weak_fold_days")
    nonweak_row = _cohort_row(regime_comparison, "non_weak_fold_days")
    if weak_regime_row and nonweak_row and regime_difference_signal(weak_regime_row, nonweak_row):
        remedies.append(remedy("no_trade_regime_filter", "Weak-fold market feature frequencies differ from non-weak days.", "weak-fold regime cluster", "Could avoid conditions where current playbook repeatedly loses.", "high; regime filters can overfit small fold samples", "phase16a_targeted_regime_module_scout", "strategy logic"))
        remedies.append(remedy("add_hedging/opposite-regime module", "Weak days show identifiable trend/range/volatility traits.", "dominant weak-fold market regime", "A module designed for the opposite payoff shape may reduce fold drawdowns.", "medium-high; future scout must be bounded and chronological", "phase16a_targeted_regime_module_scout", "strategy logic"))
    if not overlap_diag.empty and bool(overlap_diag["diagnosis_overlap_priority_risk"].fillna(False).any()):
        remedies.append(remedy("scheduler_priority_adjustment", "Weak folds include overlapping module fire-days and/or scheduler skipped overlaps.", "overlap-heavy weak folds", "Changing priority could let later helpful modules replace early losers.", "medium; must not be tuned to individual dates", "playbook_scheduler_a_priority_audit", "scheduler logic"))
    if not contribution_by_regime.empty:
        weak_contrib = contribution_by_regime[contribution_by_regime["regime"].eq("weak_folds")]
        for _, row in weak_contrib[weak_contrib["net_pnl_contribution"] < 0].iterrows():
            remedies.append(remedy("module_search_target", f"{row['module_group']} contributed {row['net_pnl_contribution']:.2f} in weak folds.", str(row["module_group"]), "A targeted replacement or complementary module might reduce the weak-fold drag.", "medium-high; contribution may reflect portfolio composition rather than durable regime edge", "module_pruning_audit_a", "strategy logic"))
            break
    if not weak_days.empty and float((weak_days["day_classification"] == "no_trade").mean()) >= 0.40:
        remedies.append(remedy("separate rare setup from core schedule", "No-trade days are common inside weak folds.", "no-trade weak-fold days", "Separating rare setups could expose whether core schedule lacks movement-day coverage.", "medium", "phase16a_no_trade_gap_module_scout", "reporting"))
    if len(remedies) < 2:
        remedies.append(remedy("collect more data", "Weak folds remain broad or low-sample after diagnostics.", "all weak folds", "More observations or manual examples may separate noise from robust regime failure.", "low; delays module search but avoids overfit", "pause_module_search_and_collect_more_data_or_review_manual_examples", "only reporting"))
    seen = set()
    unique = []
    for item in remedies:
        if item["remedy_name"] not in seen:
            unique.append(item)
            seen.add(item["remedy_name"])
    return unique


def make_next_action_recommendation(fold_summary: pd.DataFrame, weak_days: pd.DataFrame, regime_comparison: pd.DataFrame, contribution_by_regime: pd.DataFrame, overlap_diag: pd.DataFrame, remedies: list[dict[str, Any]]) -> dict[str, Any]:
    weak_regime_row = _cohort_row(regime_comparison, "weak_fold_days")
    nonweak_row = _cohort_row(regime_comparison, "non_weak_fold_days")
    action = "pause_module_search_and_collect_more_data_or_review_manual_examples"
    rationale = "Weak folds are broad across regimes and modules; avoid further module search until manual review or more data."
    if not weak_days.empty and float((weak_days["day_classification"] == "no_trade").mean()) >= 0.40:
        action = "phase16a_no_trade_gap_module_scout"
        rationale = "No-trade days dominate weak-fold day extraction."
    if not contribution_by_regime.empty:
        weak_contrib = contribution_by_regime[contribution_by_regime["regime"].eq("weak_folds")]
        if not weak_contrib.empty and float(weak_contrib["net_pnl_contribution"].min()) < 0 and abs(float(weak_contrib["net_pnl_contribution"].min())) > abs(float(weak_contrib["net_pnl_contribution"].sum())) * 0.40:
            action = "module_pruning_audit_a"
            worst = weak_contrib.sort_values("net_pnl_contribution").iloc[0]
            rationale = f"One module group consistently hurts weak folds: {worst['module_group']}."
    if not overlap_diag.empty and bool(overlap_diag[overlap_diag["is_weak_fold"]]["diagnosis_overlap_priority_risk"].fillna(False).any()):
        action = "playbook_scheduler_a_priority_audit"
        rationale = "Weak folds include overlap/priority suppression risk."
    if weak_regime_row and nonweak_row and regime_difference_signal(weak_regime_row, nonweak_row):
        action = "phase16a_targeted_regime_module_scout"
        rationale = "Weak folds cluster around identifiable market-regime feature differences."
    if fold_summary.empty or (not fold_summary.empty and fold_summary["same_fold_remains_weak_across_bcd"].fillna(False).mean() >= 0.60 and not weak_regime_row):
        action = "validation_framework_audit_c_fold_design"
        rationale = "Fold instability appears coarse or persistent without enough regime detail."
    return {
        "next_action": action,
        "rationale": rationale,
        "candidate_remedy_count": len(remedies),
        "official_gates_changed": False,
        "paper_trading_approved": False,
        "diagnostic_only_no_signals_generated": True,
        "live_trading_approved": False,
    }


def render_weak_fold_regime_audit_b_report(result: dict[str, Any]) -> str:
    rec = result["next_action_recommendation"]
    folds = result["fold_summary"]
    weak_days = result["weak_fold_days"]
    regime = result["regime_comparison"]
    overlap = result["overlap_and_scheduler_diagnostics"]
    contrib = result["module_contribution_by_regime"]
    remedies = result["candidate_remedies"]
    lines = [
        "# Weak Fold Regime Audit B — Portfolio Weak-Fold / Bad-Regime Diagnostic",
        "",
        RESEARCH_ONLY_GUARDRAIL,
        "",
        "Diagnostic only. No new signals generated, no strategy searches run, no candidate results changed, no official gates changed, no promotions, and no paper trading approval.",
        "",
        "## Summary",
        "",
        f"- Weak folds identified: `{int(folds['is_weak_fold'].sum()) if not folds.empty else 0}`",
        f"- Weak-fold day rows: `{len(weak_days)}`",
        f"- Candidate remedy briefs: `{len(remedies)}`",
        f"- Next action: `{rec['next_action']}`",
        f"- Rationale: {rec['rationale']}",
        "- Paper trading approved: `false`",
        "",
        "## Fold failure map",
        "",
        "| Audit | Portfolio | Mode | Fold | Start | End | PnL | Stress PnL | Active Days | Same fold weak across B/C/D |",
        "| --- | --- | --- | ---: | --- | --- | ---: | ---: | ---: | --- |",
    ]
    for _, row in folds[folds["is_weak_fold"]].head(30).iterrows():
        lines.append(f"| {row['audit']} | {row['portfolio_set']} | {row['portfolio_mode']} | {int(row['fold'])} | {row['fold_start']} | {row['fold_end']} | {float(row['fold_pnl']):.2f} | {_fmt(row['fold_stress_pnl'])} | {int(row['fold_active_days'])} | {bool(row['same_fold_remains_weak_across_bcd'])} |")
    lines += ["", "## Market-regime comparison", "", markdown_table(regime) if not regime.empty else "No market-regime comparison available.", "", "## Module contribution findings", ""]
    if not contrib.empty:
        for _, row in contrib[contrib["regime"].eq("weak_folds")].sort_values("net_pnl_contribution").iterrows():
            lines.append(f"- {row['module_group']}: weak-fold contribution `{float(row['net_pnl_contribution']):.2f}` across `{int(row['active_days'])}` active days.")
    lines += ["", "## Scheduler/overlap findings", ""]
    if not overlap.empty:
        weak_overlap = overlap[overlap["is_weak_fold"]]
        lines.append(f"- Weak-fold overlap-risk rows: `{int(weak_overlap['diagnosis_overlap_priority_risk'].fillna(False).sum())}`")
        lines.append(f"- Weak-fold early-loss/later-help days: `{int(weak_overlap['early_losing_module_when_later_module_helped_days'].sum())}`")
        lines.append(f"- Weak-fold skipped overlaps at portfolio level: `{int(weak_overlap['skipped_overlap_count_portfolio_level'].sum())}`")
    lines += ["", "## Candidate remedy briefs", ""]
    for item in remedies:
        lines.append(f"- `{item['remedy_name']}` -> `{item['recommended_next_task']}` ({item['changes']}); evidence: {item['evidence_from_audit']}")
    return "\n".join(lines) + "\n"


def write_weak_fold_regime_audit_b_outputs(result: dict[str, Any], output_dir: Path, report_path: Path) -> dict[str, Path]:
    ensure_directory(output_dir)
    ensure_directory(report_path.parent)
    mapping = {
        "fold_summary": output_dir / "weak_fold_regime_audit_b_fold_summary.csv",
        "weak_fold_days": output_dir / "weak_fold_regime_audit_b_weak_fold_days.csv",
        "market_regime_features": output_dir / "weak_fold_regime_audit_b_market_regime_features.csv",
        "regime_comparison": output_dir / "weak_fold_regime_audit_b_regime_comparison.csv",
        "module_contribution_by_fold": output_dir / "weak_fold_regime_audit_b_module_contribution_by_fold.csv",
        "module_contribution_by_regime": output_dir / "weak_fold_regime_audit_b_module_contribution_by_regime.csv",
        "overlap_and_scheduler_diagnostics": output_dir / "weak_fold_regime_audit_b_overlap_and_scheduler_diagnostics.csv",
        "bad_day_clusters": output_dir / "weak_fold_regime_audit_b_bad_day_clusters.csv",
    }
    paths: dict[str, Path] = {}
    for key, path in mapping.items():
        write_csv_artifact(result[key], path)
        paths[key] = path
    remedies_path = output_dir / "weak_fold_regime_audit_b_candidate_remedies.json"
    rec_path = output_dir / "weak_fold_regime_audit_b_next_action_recommendation.json"
    write_json_artifact(result["candidate_remedies"], remedies_path)
    write_json_artifact(result["next_action_recommendation"], rec_path)
    report_path.write_text(render_weak_fold_regime_audit_b_report(result), encoding="utf-8")
    paths["candidate_remedies"] = remedies_path
    paths["recommendation"] = rec_path
    paths["report"] = report_path
    return paths


# Helpers

def fold_sessions_for(pdaily: pd.DataFrame, fold: int, folds: int = 6) -> list[str]:
    ordered = pdaily.sort_values("trading_session").reset_index(drop=True)
    if ordered.empty:
        return []
    size = max(1, len(ordered) // folds)
    start = (fold - 1) * size
    end = len(ordered) if fold == folds else min(len(ordered), fold * size)
    return ordered.iloc[start:end]["trading_session"].astype(str).tolist()


def portfolio_keys_for(results: pd.DataFrame, portfolio_set: str, mode: str) -> set[str] | None:
    row = _single_match(results, portfolio_set, mode)
    if row is None:
        return None
    keys = {k for k in str(row.get("signal_keys", "")).split(";") if k}
    return keys or None


def module_contributions_for_sessions(module_daily: pd.DataFrame, sessions: list[str], keys: set[str] | None) -> dict[str, float]:
    if module_daily.empty or not sessions:
        return {}
    seg = module_daily[module_daily["trading_session"].astype(str).isin(set(sessions))]
    cols = [c for c in seg.columns if c != "trading_session" and (keys is None or c in keys)]
    return {c: float(seg[c].sum()) for c in cols if abs(float(seg[c].sum())) > 1e-9}


def phase_contribution_values(contrib: dict[str, float]) -> dict[str, float]:
    totals = {phase: 0.0 for phase in PHASES}
    for key, value in contrib.items():
        phase = key.split("::", 1)[0]
        if phase in totals:
            totals[phase] += float(value)
    return totals


def phase_active_days(module_daily: pd.DataFrame, sessions: list[str]) -> dict[str, int]:
    out = {phase: 0 for phase in PHASES}
    if module_daily.empty:
        return out
    seg = module_daily[module_daily["trading_session"].astype(str).isin(sessions)]
    for phase in PHASES:
        cols = [c for c in seg.columns if c.startswith(f"{phase}::")]
        if cols:
            out[phase] = int((seg[cols].abs().sum(axis=1) > 0).sum())
    return out


def classify_day(pnl: float, large_negative_cutoff: float) -> str:
    if abs(pnl) <= 1e-9:
        return "no_trade"
    if pnl > 0:
        return "positive"
    if pnl <= large_negative_cutoff:
        return "large_negative"
    return "negative"


def helped_hurt(value: float) -> str:
    if value > 0:
        return "helped"
    if value < 0:
        return "hurt"
    return "no_contribution"


def time_slice(day: pd.DataFrame, start: str, end: str) -> pd.DataFrame:
    times = day["timestamp"].dt.strftime("%H:%M")
    return day[(times >= start) & (times < end)]


def direction(seg: pd.DataFrame) -> str:
    diff = segment_direction_value(seg)
    if diff > 0:
        return "up"
    if diff < 0:
        return "down"
    return "flat"


def segment_direction_value(seg: pd.DataFrame) -> float:
    if seg.empty:
        return 0.0
    return float(seg.iloc[-1]["close"] - seg.iloc[0]["open"])


def segment_range(seg: pd.DataFrame) -> float:
    if seg.empty:
        return 0.0
    return float(seg["high"].max() - seg["low"].min())


def relation(value: float, prior: Any) -> str:
    if pd.isna(prior):
        return "unknown"
    prior_value = float(prior)
    if value > prior_value:
        return "above"
    if value < prior_value:
        return "below"
    return "at"


def frequency(series: pd.Series) -> float:
    return round(float(series.fillna(False).astype(bool).mean()), 6) if len(series) else 0.0


def empty_regime_row(label: str) -> dict[str, Any]:
    return {"cohort": label, "day_count": 0, "average_rth_range": 0.0, "average_close_position": 0.0, "trend_day_frequency": 0.0, "reversal_day_frequency": 0.0, "range_day_frequency": 0.0, "high_vol_frequency": 0.0, "low_vol_frequency": 0.0, "power_hour_expansion_frequency": 0.0, "lunch_compression_frequency": 0.0, "lunch_expansion_frequency": 0.0, "prior_level_interaction_frequency": 0.0, "no_trade_frequency": 0.0, "module_overlap_frequency": 0.0}


def sessions_between(start: str, end: str, module_daily: pd.DataFrame) -> list[str]:
    if not start or start == "None" or not end or end == "None" or module_daily.empty:
        return []
    sessions = module_daily["trading_session"].astype(str)
    return sessions[(sessions >= start) & (sessions <= end)].drop_duplicates().sort_values().tolist()


def sessions_from_fold_summary(fold_summary: pd.DataFrame, module_daily: pd.DataFrame) -> set[str]:
    sessions: set[str] = set()
    if fold_summary.empty:
        return sessions
    for _, row in fold_summary.iterrows():
        sessions.update(sessions_between(str(row.get("fold_start")), str(row.get("fold_end")), module_daily))
    return sessions


def _single_match(df: pd.DataFrame, portfolio_set: str, mode: str) -> pd.Series | None:
    if df.empty:
        return None
    seg = df[(df["portfolio_set"].astype(str).eq(portfolio_set)) & (df["portfolio_mode"].astype(str).eq(mode))]
    return None if seg.empty else seg.iloc[0]


def _float_or_none(value: Any) -> float | None:
    try:
        if pd.isna(value):
            return None
        return float(value)
    except Exception:
        return None


def _cohort_row(df: pd.DataFrame, cohort: str) -> dict[str, Any] | None:
    if df.empty or "cohort" not in df.columns:
        return None
    seg = df[df["cohort"].eq(cohort)]
    return None if seg.empty else seg.iloc[0].to_dict()


def regime_difference_signal(weak: dict[str, Any], nonweak: dict[str, Any]) -> bool:
    if int(weak.get("day_count", 0)) <= 0:
        return False
    checks = [
        "trend_day_frequency",
        "reversal_day_frequency",
        "range_day_frequency",
        "high_vol_frequency",
        "low_vol_frequency",
        "power_hour_expansion_frequency",
        "prior_level_interaction_frequency",
        "module_overlap_frequency",
    ]
    return any(abs(float(weak.get(c, 0.0)) - float(nonweak.get(c, 0.0))) >= 0.15 for c in checks)


def remedy(name: str, evidence: str, target: str, why: str, risk: str, task: str, changes: str) -> dict[str, Any]:
    return {
        "remedy_name": name,
        "evidence_from_audit": evidence,
        "target_weak_fold_or_regime": target,
        "why_it_might_help": why,
        "overfit_risk": risk,
        "recommended_next_task": task,
        "changes": changes,
        "diagnostic_only_no_implementation": True,
    }


def _fmt(value: Any) -> str:
    return "" if value is None or pd.isna(value) else f"{float(value):.2f}"


def markdown_table(df: pd.DataFrame) -> str:
    if df.empty:
        return ""
    cols = list(df.columns)
    lines = ["| " + " | ".join(cols) + " |", "| " + " | ".join("---" for _ in cols) + " |"]
    for _, row in df.iterrows():
        lines.append("| " + " | ".join(str(row[c]) for c in cols) + " |")
    return "\n".join(lines)


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))
