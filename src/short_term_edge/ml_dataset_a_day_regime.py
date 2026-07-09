from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .data_loader import load_ohlcv_csv
from .phase_common import ensure_directory, write_csv_artifact, write_json_artifact

RESEARCH_ONLY_GUARDRAIL = (
    "Research/simulation only. No live trading, broker adapters, order routing, webhooks, "
    "credential storage, automated execution, or LLM-driven trade decisions."
)
PARTIAL_SESSIONS = {"2026-07-03"}
PHASES = ("phase10b", "phase11a", "phase12a", "phase13a", "phase14a", "phase15a", "phase16a", "phase17a")
FEATURE_GROUPS = {
    "pre_rth": [
        "prior_rth_close",
        "prior_rth_high",
        "prior_rth_low",
        "prior_rth_midpoint",
        "prior_rth_range",
        "gap_from_prior_rth_close",
        "prior_day_direction",
        "prior_day_close_position",
        "prior_day_range_percentile",
    ],
    "early_rth": [
        "first_5m_direction",
        "first_15m_direction",
        "first_30m_direction",
        "first_30m_range",
        "first_30m_close_position",
        "first_30m_range_percentile",
    ],
    "morning": [
        "morning_0930_1130_direction",
        "morning_0930_1130_range",
        "morning_close_position",
        "morning_range_percentile",
        "morning_high_low_break_flag",
        "morning_direction_flip_flag",
        "broad_high_vol_mixed_flag",
        "strict_high_vol_mixed_flag",
    ],
    "midday": [
        "lunch_1130_1330_range",
        "lunch_range_percentile",
        "lunch_direction",
        "lunch_compression_flag",
        "midday_inside_morning_range_flag",
        "midday_breakout_from_morning_range_flag",
    ],
    "late_session_diagnostic": [
        "power_hour_range",
        "power_hour_direction",
        "power_hour_expansion_flag",
        "rth_close_position",
        "full_rth_range",
        "full_day_trend_proxy",
        "full_day_reversal_proxy",
        "full_day_range_proxy",
    ],
}
AVAILABILITY_TIME = {
    **{name: "pre_rth" for name in FEATURE_GROUPS["pre_rth"]},
    **{name: "10:00" for name in FEATURE_GROUPS["early_rth"]},
    **{name: "11:30" for name in FEATURE_GROUPS["morning"]},
    **{name: "13:30" for name in FEATURE_GROUPS["midday"]},
    **{name: "post_session_diagnostic" for name in FEATURE_GROUPS["late_session_diagnostic"]},
}
TARGET_COLUMNS = [
    "target_bad_playbook_day",
    "target_good_playbook_day",
    "target_no_trade_or_reduce_risk_day",
    "target_best_phase_group",
    "target_worst_phase_group",
    "target_high_vol_mixed_weak_day",
    "target_prior_level_interaction_day",
    "target_power_hour_expansion_day",
]


@dataclass(frozen=True)
class MlDatasetAConfig:
    raw_path: Path
    output_dir: Path
    report_dir: Path
    artifact_dir: Path
    run_id: str = "ml-dataset-a-r1"


def load_mnq_raw_data(raw_path: Path) -> pd.DataFrame:
    bars = load_ohlcv_csv(raw_path)
    bars = bars[bars["symbol"].astype(str).str.upper().str.contains("MNQ")].copy()
    return bars.sort_values(["trading_session", "timestamp"]).reset_index(drop=True)


def complete_rth_sessions(bars: pd.DataFrame, partial_sessions: set[str] | None = None) -> list[str]:
    partial = partial_sessions or PARTIAL_SESSIONS
    rth = bars[bars["session_segment"].eq("RTH")].copy()
    if rth.empty:
        return []
    rth["time_str"] = rth["timestamp"].dt.strftime("%H:%M")
    grouped = rth.groupby("trading_session", sort=True).agg(first_time=("time_str", "min"), last_time=("time_str", "max"), bars=("timestamp", "size"))
    good = grouped[(grouped["first_time"].le("09:30")) & (grouped["last_time"].ge("15:59")) & (grouped["bars"].ge(360))]
    return [str(s) for s in good.index.astype(str) if str(s) not in partial]


def build_day_regime_features(raw_path: Path, partial_sessions: set[str] | None = None) -> pd.DataFrame:
    bars = load_mnq_raw_data(raw_path)
    sessions = complete_rth_sessions(bars, partial_sessions)
    session_set = set(sessions)
    rth = bars[bars["session_segment"].eq("RTH") & bars["trading_session"].astype(str).isin(session_set)].copy()
    rth["time_str"] = rth["timestamp"].dt.strftime("%H:%M")
    daily = rth.groupby("trading_session", sort=True).agg(
        rth_open=("open", "first"),
        rth_high=("high", "max"),
        rth_low=("low", "min"),
        rth_close=("close", "last"),
    )
    daily["rth_range"] = daily["rth_high"] - daily["rth_low"]
    daily["rth_close_position"] = _close_position(daily["rth_close"], daily["rth_low"], daily["rth_high"])
    rows: list[dict[str, Any]] = []
    daily_by_str = daily.copy()
    daily_by_str.index = daily_by_str.index.astype(str)
    daily_session_set = set(daily_by_str.index.astype(str))
    ordered_sessions = [s for s in sessions if s in daily_session_set]
    grouped_days = {str(session): day.sort_values("timestamp") for session, day in rth.groupby("trading_session", sort=True)}
    prior_first30_ranges: list[float] = []
    prior_morning_ranges: list[float] = []
    prior_lunch_ranges: list[float] = []
    for idx, session in enumerate(ordered_sessions):
        day = grouped_days[session]
        d = daily_by_str.loc[session]
        prior = daily_by_str.iloc[idx - 1] if idx > 0 else None
        prior_ranges = daily_by_str.iloc[:idx]["rth_range"].astype(float).tolist()
        first5 = _time_slice(day, "09:30", "09:35")
        first15 = _time_slice(day, "09:30", "09:45")
        first30 = _time_slice(day, "09:30", "10:00")
        morning = _time_slice(day, "09:30", "11:30")
        lunch = _time_slice(day, "11:30", "13:30")
        first60 = _time_slice(day, "09:30", "10:30")
        power = _time_slice(day, "15:00", "16:00")
        full_range = float(d["rth_range"])
        morning_range = _segment_range(morning)
        lunch_range = _segment_range(lunch)
        first30_range = _segment_range(first30)
        morning_close_pos = _segment_close_position(morning)
        first30_close_pos = _segment_close_position(first30)
        lunch_compression_cutoff = _prior_percentile(prior_lunch_ranges, 0.25)
        first30_pct = _prior_rank_percentile(first30_range, prior_first30_ranges)
        morning_pct = _prior_rank_percentile(morning_range, prior_morning_ranges)
        lunch_pct = _prior_rank_percentile(lunch_range, prior_lunch_ranges)
        prior_range_pct = _prior_rank_percentile(float(prior["rth_range"]) if prior is not None else np.nan, prior_ranges[:-1]) if idx > 1 else np.nan
        morning_break = bool(prior is not None and (float(morning["high"].max()) >= float(prior["rth_high"]) or float(morning["low"].min()) <= float(prior["rth_low"]))) if not morning.empty else False
        direction_flip = bool(_direction(first60) not in ("flat", _direction(morning)) and _direction(morning) != "flat")
        broad_high_vol_mixed = bool((morning_pct >= 0.70 if pd.notna(morning_pct) else False) and direction_flip)
        strict_high_vol_mixed = bool((morning_pct >= 0.80 if pd.notna(morning_pct) else False) and direction_flip and 0.25 <= morning_close_pos <= 0.75)
        row = {
            "trading_session": session,
            "prior_rth_close": float(prior["rth_close"]) if prior is not None else np.nan,
            "prior_rth_high": float(prior["rth_high"]) if prior is not None else np.nan,
            "prior_rth_low": float(prior["rth_low"]) if prior is not None else np.nan,
            "prior_rth_midpoint": float((prior["rth_high"] + prior["rth_low"]) / 2.0) if prior is not None else np.nan,
            "prior_rth_range": float(prior["rth_range"]) if prior is not None else np.nan,
            "gap_from_prior_rth_close": float(d["rth_open"] - prior["rth_close"]) if prior is not None else np.nan,
            "prior_day_direction": _direction_from_values(float(prior["rth_open"]), float(prior["rth_close"])) if prior is not None else "unknown",
            "prior_day_close_position": float(prior["rth_close_position"]) if prior is not None else np.nan,
            "prior_day_range_percentile": prior_range_pct,
            "first_5m_direction": _direction(first5),
            "first_15m_direction": _direction(first15),
            "first_30m_direction": _direction(first30),
            "first_30m_range": first30_range,
            "first_30m_close_position": first30_close_pos,
            "first_30m_range_percentile": first30_pct,
            "morning_0930_1130_direction": _direction(morning),
            "morning_0930_1130_range": morning_range,
            "morning_close_position": morning_close_pos,
            "morning_range_percentile": morning_pct,
            "morning_high_low_break_flag": morning_break,
            "morning_direction_flip_flag": direction_flip,
            "broad_high_vol_mixed_flag": broad_high_vol_mixed,
            "strict_high_vol_mixed_flag": strict_high_vol_mixed,
            "lunch_1130_1330_range": lunch_range,
            "lunch_range_percentile": lunch_pct,
            "lunch_direction": _direction(lunch),
            "lunch_compression_flag": bool(pd.notna(lunch_compression_cutoff) and lunch_range <= lunch_compression_cutoff),
            "midday_inside_morning_range_flag": bool(not lunch.empty and not morning.empty and float(lunch["high"].max()) <= float(morning["high"].max()) and float(lunch["low"].min()) >= float(morning["low"].min())),
            "midday_breakout_from_morning_range_flag": bool(not lunch.empty and not morning.empty and (float(lunch["high"].max()) > float(morning["high"].max()) or float(lunch["low"].min()) < float(morning["low"].min()))),
            "power_hour_range": _segment_range(power),
            "power_hour_direction": _direction(power),
            "power_hour_expansion_flag": bool(full_range > 0 and _segment_range(power) >= full_range * 0.30),
            "rth_close_position": float(d["rth_close_position"]),
            "full_rth_range": full_range,
            "full_day_trend_proxy": bool(float(d["rth_close_position"]) >= 0.80 or float(d["rth_close_position"]) <= 0.20),
            "full_day_reversal_proxy": bool(_direction(first60) != "flat" and _direction(first60) != _direction(day) and abs(_segment_direction_value(first60)) >= max(full_range * 0.20, 1e-9)),
            "full_day_range_proxy": bool(0.35 <= float(d["rth_close_position"]) <= 0.65 and (_prior_rank_percentile(full_range, prior_ranges) <= 0.50 if prior_ranges else False)),
        }
        rows.append(row)
        prior_first30_ranges.append(first30_range)
        prior_morning_ranges.append(morning_range)
        prior_lunch_ranges.append(lunch_range)
    return pd.DataFrame(rows)


def build_ml_dataset_a(project_root: Path, run_id: str = "ml-dataset-a-r1") -> dict[str, Any]:
    config = MlDatasetAConfig(
        raw_path=project_root / "data" / "raw" / "mnq_1m_databento_20230101_20260703.csv",
        output_dir=project_root / "outputs",
        report_dir=project_root / "reports",
        artifact_dir=project_root / "artifacts" / "ml_dataset_a_day_regime" / run_id,
        run_id=run_id,
    )
    ensure_directory(config.output_dir)
    ensure_directory(config.report_dir)
    ensure_directory(config.artifact_dir)
    warnings: list[str] = []
    features = build_day_regime_features(config.raw_path)
    dataset = features.copy()
    dataset = add_playbook_labels(dataset, config.output_dir, warnings)
    dataset = add_scheduler_labels(dataset, config.output_dir, warnings)
    dataset = add_phase_labels(dataset, config.output_dir, warnings)
    dataset = add_target_columns(dataset)
    dataset = add_split_columns(dataset)
    feature_dictionary = build_feature_dictionary()
    label_dictionary = build_label_dictionary(dataset)
    quality_report = build_quality_report(dataset, feature_dictionary)
    split_summary = build_split_summary(dataset)
    recommendation = build_next_action_recommendation(dataset, quality_report, warnings)
    paths = write_ml_dataset_a_outputs(config, dataset, feature_dictionary, label_dictionary, quality_report, split_summary, recommendation, warnings)
    return {
        "dataset": dataset,
        "feature_dictionary": feature_dictionary,
        "label_dictionary": label_dictionary,
        "quality_report": quality_report,
        "split_summary": split_summary,
        "next_action_recommendation": recommendation,
        "warnings": warnings,
        "paths": paths,
    }


def add_playbook_labels(dataset: pd.DataFrame, output_dir: Path, warnings: list[str]) -> pd.DataFrame:
    out = dataset.copy()
    daily_path = output_dir / "portfolio_audit_e_portfolio_daily_pnl.csv"
    results_path = output_dir / "portfolio_audit_e_portfolio_results.csv"
    if not daily_path.exists() or not results_path.exists():
        warnings.append("missing Portfolio Audit E playbook daily/results files; playbook labels defaulted to no-trade/zero pnl")
        out["playbook_daily_pnl"] = 0.0
    else:
        daily = pd.read_csv(daily_path)
        results = pd.read_csv(results_path)
        best = _best_row(results, ["portfolio_set", "portfolio_mode"])
        playbook_name = {"portfolio_set": str(best.get("portfolio_set", "")), "portfolio_mode": str(best.get("portfolio_mode", ""))}
        seg = daily[(daily["portfolio_set"].astype(str).eq(playbook_name["portfolio_set"])) & (daily["portfolio_mode"].astype(str).eq(playbook_name["portfolio_mode"]))]
        pnl = seg.groupby("trading_session")["net_pnl"].sum().rename("playbook_daily_pnl").reset_index()
        out = out.merge(pnl, on="trading_session", how="left")
        out["playbook_policy_name"] = f"{playbook_name['portfolio_set']}|{playbook_name['portfolio_mode']}"
    out["playbook_daily_pnl"] = pd.to_numeric(out.get("playbook_daily_pnl", 0.0), errors="coerce").fillna(0.0)
    out["playbook_active_day"] = out["playbook_daily_pnl"].ne(0.0)
    out["playbook_no_trade_day"] = ~out["playbook_active_day"]
    out["playbook_positive_day"] = out["playbook_daily_pnl"].gt(0.0)
    out["playbook_negative_day"] = out["playbook_daily_pnl"].lt(0.0)
    neg = out.loc[out["playbook_daily_pnl"].lt(0.0), "playbook_daily_pnl"]
    cutoff = float(neg.quantile(0.10)) if not neg.empty else -np.inf
    out["playbook_large_loss_day"] = out["playbook_daily_pnl"].le(cutoff) & out["playbook_daily_pnl"].lt(0.0)
    weak_path = output_dir / "weak_fold_regime_audit_b_weak_fold_days.csv"
    if weak_path.exists():
        weak = pd.read_csv(weak_path, usecols=["trading_session"])
        weak_sessions = set(weak["trading_session"].astype(str))
    else:
        warnings.append("missing weak_fold_regime_audit_b_weak_fold_days.csv; weak-fold labels defaulted false")
        weak_sessions = set()
    out["playbook_weak_fold_day"] = out["trading_session"].astype(str).isin(weak_sessions)
    return out


def add_scheduler_labels(dataset: pd.DataFrame, output_dir: Path, warnings: list[str]) -> pd.DataFrame:
    out = dataset.copy()
    candidates = [
        ("Scheduler E", output_dir / "playbook_scheduler_e_daily_pnl.csv", output_dir / "playbook_scheduler_e_policy_results.csv", ["rare_priority_policy", "portfolio_mode"]),
        ("Scheduler D", output_dir / "playbook_scheduler_d_daily_pnl.csv", output_dir / "playbook_scheduler_d_overlay_policy_results.csv", ["overlay_policy", "portfolio_mode"]),
        ("Portfolio Audit E", output_dir / "portfolio_audit_e_portfolio_daily_pnl.csv", output_dir / "portfolio_audit_e_portfolio_results.csv", ["portfolio_set", "portfolio_mode"]),
    ]
    selected = None
    for name, daily_path, results_path, keys in candidates:
        if daily_path.exists() and results_path.exists():
            selected = (name, daily_path, results_path, keys)
            break
    if selected is None:
        warnings.append("missing scheduler/portfolio daily/results files; scheduler labels defaulted to no-trade/zero pnl")
        out["scheduler_policy_name"] = "missing"
        out["scheduler_daily_pnl"] = 0.0
    else:
        name, daily_path, results_path, keys = selected
        daily = pd.read_csv(daily_path)
        results = pd.read_csv(results_path)
        usable_keys = [k for k in keys if k in daily.columns and k in results.columns]
        best = _best_row(results, usable_keys)
        mask = pd.Series(True, index=daily.index)
        policy_bits = [name]
        for key in usable_keys:
            val = str(best.get(key, ""))
            mask &= daily[key].astype(str).eq(val)
            policy_bits.append(f"{key}={val}")
        pnl = daily[mask].groupby("trading_session")["net_pnl"].sum().rename("scheduler_daily_pnl").reset_index()
        out = out.merge(pnl, on="trading_session", how="left")
        out["scheduler_policy_name"] = "|".join(policy_bits)
    out["scheduler_daily_pnl"] = pd.to_numeric(out.get("scheduler_daily_pnl", 0.0), errors="coerce").fillna(0.0)
    out["scheduler_positive_day"] = out["scheduler_daily_pnl"].gt(0.0)
    out["scheduler_negative_day"] = out["scheduler_daily_pnl"].lt(0.0)
    out["scheduler_no_trade_day"] = out["scheduler_daily_pnl"].eq(0.0)
    neg = out.loc[out["scheduler_daily_pnl"].lt(0.0), "scheduler_daily_pnl"]
    cutoff = float(neg.quantile(0.10)) if not neg.empty else -np.inf
    out["scheduler_large_loss_day"] = out["scheduler_daily_pnl"].le(cutoff) & out["scheduler_daily_pnl"].lt(0.0)
    return out


def add_phase_labels(dataset: pd.DataFrame, output_dir: Path, warnings: list[str]) -> pd.DataFrame:
    out = dataset.copy()
    for phase in PHASES:
        path = output_dir / f"{phase}_daily_pnl.csv"
        if not path.exists():
            warnings.append(f"missing optional phase daily file: {path.name}; {phase} labels defaulted inactive/zero pnl")
            out[f"{phase}_daily_pnl"] = 0.0
            out[f"{phase}_active"] = False
            continue
        daily = pd.read_csv(path)
        if "trading_session" not in daily.columns or "net_pnl" not in daily.columns:
            warnings.append(f"optional phase file lacks required columns and was skipped: {path.name}")
            out[f"{phase}_daily_pnl"] = 0.0
            out[f"{phase}_active"] = False
            continue
        grouped = daily.groupby("trading_session", as_index=False).agg(**{f"{phase}_daily_pnl": ("net_pnl", "sum"), f"{phase}_active": ("net_pnl", "size")})
        grouped[f"{phase}_active"] = grouped[f"{phase}_active"].gt(0)
        out = out.merge(grouped, on="trading_session", how="left")
        out[f"{phase}_daily_pnl"] = pd.to_numeric(out[f"{phase}_daily_pnl"], errors="coerce").fillna(0.0)
        out[f"{phase}_active"] = out[f"{phase}_active"].fillna(False).astype(bool)
    return out


def add_target_columns(dataset: pd.DataFrame) -> pd.DataFrame:
    out = dataset.copy()
    out["target_bad_playbook_day"] = out["playbook_negative_day"] | out["playbook_large_loss_day"] | out["playbook_weak_fold_day"]
    out["target_good_playbook_day"] = out["playbook_positive_day"] & ~out["playbook_large_loss_day"]
    out["target_no_trade_or_reduce_risk_day"] = out["playbook_no_trade_day"] | out["playbook_large_loss_day"] | out["playbook_weak_fold_day"]
    phase_pnl_cols = [f"{phase}_daily_pnl" for phase in PHASES]
    out["target_best_phase_group"] = out[phase_pnl_cols].idxmax(axis=1).str.replace("_daily_pnl", "", regex=False)
    out["target_worst_phase_group"] = out[phase_pnl_cols].idxmin(axis=1).str.replace("_daily_pnl", "", regex=False)
    all_zero = out[phase_pnl_cols].abs().sum(axis=1).eq(0.0)
    out.loc[all_zero, ["target_best_phase_group", "target_worst_phase_group"]] = "none_active"
    out["target_high_vol_mixed_weak_day"] = out["playbook_weak_fold_day"] & out["broad_high_vol_mixed_flag"]
    out["target_prior_level_interaction_day"] = out["morning_high_low_break_flag"]
    out["target_power_hour_expansion_day"] = out["power_hour_expansion_flag"]
    return out


def add_split_columns(dataset: pd.DataFrame) -> pd.DataFrame:
    out = dataset.sort_values("trading_session").reset_index(drop=True).copy()
    n = len(out)
    discovery_end = int(n * 0.60)
    validation_end = int(n * 0.80)
    out["chronological_split"] = "holdout"
    out.loc[: max(discovery_end - 1, -1), "chronological_split"] = "discovery"
    out.loc[discovery_end : max(validation_end - 1, discovery_end - 1), "chronological_split"] = "validation"
    dates = pd.to_datetime(out["trading_session"])
    recent_start = dates.max() - pd.DateOffset(months=6) if n else pd.NaT
    out["recent_oos_like"] = dates.ge(recent_start) if n else False
    out["existing_project_fold"] = out["chronological_split"]
    out["calendar_year_fold"] = dates.dt.year.astype(str)
    out["half_year_fold"] = dates.dt.year.astype(str) + "H" + np.where(dates.dt.month.le(6), "1", "2")
    out["rolling_6_month_fold"] = dates.dt.to_period("2Q").astype(str)
    out["rolling_3_month_fold"] = dates.dt.to_period("Q").astype(str)
    return out


def build_feature_dictionary() -> dict[str, Any]:
    return {
        column: {
            "role": "feature",
            "feature_group": next(group for group, cols in FEATURE_GROUPS.items() if column in cols),
            "availability_time": AVAILABILITY_TIME[column],
            "leakage_rule": "uses only data available at or before availability_time" if AVAILABILITY_TIME[column] != "post_session_diagnostic" else "post-session diagnostic; exclude from intraday pre-close training features unless explicitly allowed",
        }
        for column in AVAILABILITY_TIME
    }


def build_label_dictionary(dataset: pd.DataFrame) -> dict[str, Any]:
    labels: dict[str, Any] = {}
    feature_cols = set(AVAILABILITY_TIME)
    for column in dataset.columns:
        if column in ("trading_session", *feature_cols):
            continue
        if column in TARGET_COLUMNS:
            role = "target"
        elif column.endswith("_fold") or column in {"chronological_split", "recent_oos_like"}:
            role = "split_metadata"
        else:
            role = "diagnostic_label"
        labels[column] = {"role": role, "is_target": role == "target", "is_feature": False}
    return labels


def build_quality_report(dataset: pd.DataFrame, feature_dictionary: dict[str, Any]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    rows.append({"check": "row_count", "value": len(dataset), "status": "pass" if len(dataset) > 0 else "fail", "detail": "one row per complete MNQ trading session"})
    rows.append({"check": "date_range", "value": f"{dataset['trading_session'].min()} to {dataset['trading_session'].max()}", "status": "pass", "detail": "known partial 2026-07-03 excluded"})
    rows.append({"check": "complete_sessions", "value": dataset["trading_session"].nunique(), "status": "pass" if dataset["trading_session"].is_unique else "fail", "detail": "unique complete sessions"})
    rows.append({"check": "partial_session_exclusion", "value": int(dataset["trading_session"].astype(str).eq("2026-07-03").sum()), "status": "pass" if not dataset["trading_session"].astype(str).eq("2026-07-03").any() else "fail", "detail": "2026-07-03 must be absent"})
    for group, cols in FEATURE_GROUPS.items():
        present = [c for c in cols if c in dataset.columns]
        missing_cells = int(dataset[present].isna().sum().sum()) if present else 0
        rows.append({"check": f"missing_values_{group}", "value": missing_cells, "status": "pass" if present else "fail", "detail": f"{len(present)}/{len(cols)} feature columns present"})
    for target in TARGET_COLUMNS:
        counts = dataset[target].fillna("missing").astype(str).value_counts().sort_index().to_dict()
        rows.append({"check": f"target_balance_{target}", "value": json.dumps({k: int(v) for k, v in counts.items()}, sort_keys=True), "status": "pass", "detail": "target class balance"})
    rows.extend([
        {"check": "playbook_active_day_count", "value": int(dataset["playbook_active_day"].sum()), "status": "pass", "detail": "active playbook days"},
        {"check": "bad_day_count", "value": int(dataset["target_bad_playbook_day"].sum()), "status": "pass", "detail": "target_bad_playbook_day positives"},
        {"check": "no_trade_day_count", "value": int(dataset["playbook_no_trade_day"].sum()), "status": "pass", "detail": "playbook no-trade days"},
        {"check": "target_leakage_check_summary", "value": 0, "status": "pass" if not (set(TARGET_COLUMNS) & set(feature_dictionary)) else "fail", "detail": "target columns are absent from feature dictionary"},
        {"check": "availability_time_coverage", "value": len(feature_dictionary), "status": "pass" if all(v.get("availability_time") for v in feature_dictionary.values()) else "fail", "detail": "every feature has availability_time"},
    ])
    return pd.DataFrame(rows)


def build_split_summary(dataset: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for column in ["chronological_split", "recent_oos_like", "existing_project_fold", "calendar_year_fold", "half_year_fold", "rolling_6_month_fold", "rolling_3_month_fold"]:
        for value, seg in dataset.groupby(column, dropna=False, sort=True):
            rows.append({
                "split_column": column,
                "split_value": str(value),
                "rows": int(len(seg)),
                "start_session": str(seg["trading_session"].min()),
                "end_session": str(seg["trading_session"].max()),
                "bad_playbook_days": int(seg["target_bad_playbook_day"].sum()),
                "playbook_active_days": int(seg["playbook_active_day"].sum()),
            })
    return pd.DataFrame(rows)


def build_next_action_recommendation(dataset: pd.DataFrame, quality_report: pd.DataFrame, warnings: list[str]) -> dict[str, Any]:
    quality_poor = bool((quality_report["status"] == "fail").any()) or len(warnings) > 3
    target_counts = dataset["target_bad_playbook_day"].value_counts().to_dict()
    false_count = int(target_counts.get(False, 0))
    true_count = int(target_counts.get(True, 0))
    if quality_poor:
        action = "improve_ml_dataset_a_feature_quality"
        rationale = "Feature/target quality checks produced failures or excessive input warnings."
    elif len(dataset) >= 500 and false_count >= 50 and true_count >= 50:
        action = "ml_baseline_a_train_regime_classifier"
        rationale = "Dataset has at least 500 rows and target_bad_playbook_day has at least 50 examples in both classes."
    elif min(false_count, true_count) < 50:
        action = "insufficient_targets_for_ml_training"
        rationale = "target_bad_playbook_day is too sparse for the requested baseline rule."
    else:
        action = "pause_ml_until_more_data"
        rationale = "Dataset does not yet meet the row-count rule for ML baseline training."
    return {
        "next_action": action,
        "rationale": rationale,
        "dataset_rows": int(len(dataset)),
        "target_bad_playbook_day_balance": {"false": false_count, "true": true_count},
        "research_only": True,
        "model_trained": False,
        "official_gates_changed": False,
        "paper_trading_approved": False,
        "live_trading_approved": False,
        "warnings": warnings,
    }


def write_ml_dataset_a_outputs(config: MlDatasetAConfig, dataset: pd.DataFrame, feature_dictionary: dict[str, Any], label_dictionary: dict[str, Any], quality_report: pd.DataFrame, split_summary: pd.DataFrame, recommendation: dict[str, Any], warnings: list[str]) -> dict[str, Path]:
    paths = {
        "dataset": config.output_dir / "ml_dataset_a_day_regime.csv",
        "feature_dictionary": config.output_dir / "ml_dataset_a_feature_dictionary.json",
        "label_dictionary": config.output_dir / "ml_dataset_a_label_dictionary.json",
        "quality_report": config.output_dir / "ml_dataset_a_quality_report.csv",
        "split_summary": config.output_dir / "ml_dataset_a_split_summary.csv",
        "report": config.report_dir / "ml_dataset_a_day_regime_report.md",
        "recommendation": config.output_dir / "ml_dataset_a_next_action_recommendation.json",
    }
    write_csv_artifact(dataset, paths["dataset"])
    write_json_artifact(feature_dictionary, paths["feature_dictionary"])
    write_json_artifact(label_dictionary, paths["label_dictionary"])
    write_csv_artifact(quality_report, paths["quality_report"])
    write_csv_artifact(split_summary, paths["split_summary"])
    write_json_artifact(recommendation, paths["recommendation"])
    paths["report"].write_text(render_ml_dataset_a_report(dataset, quality_report, split_summary, recommendation, warnings), encoding="utf-8")
    for key, path in paths.items():
        if path.suffix == ".csv":
            target = config.artifact_dir / path.name
            write_csv_artifact(pd.read_csv(path), target)
        elif path.suffix == ".json":
            write_json_artifact(json.loads(path.read_text(encoding="utf-8")), config.artifact_dir / path.name)
        elif path.suffix == ".md":
            (config.artifact_dir / path.name).write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    write_json_artifact({"run_id": config.run_id, "research_only": True, "model_trained": False, "official_gates_changed": False, "paper_trading_approved": False, "warnings": warnings}, config.artifact_dir / "manifest.json")
    return paths


def render_ml_dataset_a_report(dataset: pd.DataFrame, quality_report: pd.DataFrame, split_summary: pd.DataFrame, recommendation: dict[str, Any], warnings: list[str]) -> str:
    balance = dataset["target_bad_playbook_day"].value_counts().to_dict()
    split_counts = dataset["chronological_split"].value_counts().sort_index().to_dict()
    return "\n".join([
        "# ML Dataset A — Day-Level Regime / Playbook Outcome Dataset",
        "",
        RESEARCH_ONLY_GUARDRAIL,
        "No model training was performed. No strategy signals were generated. Official promotion gates are unchanged and paper_trading_approved remains false.",
        "",
        f"Rows: {len(dataset)}",
        f"Date range: {dataset['trading_session'].min()} to {dataset['trading_session'].max()}",
        f"Target_bad_playbook_day balance: {balance}",
        f"Chronological split counts: {split_counts}",
        f"Next action: {recommendation['next_action']}",
        f"Warnings: {warnings if warnings else 'none'}",
        "",
        "## Feature availability",
        "- pre_rth, 10:00, 11:30, 13:30, and post_session_diagnostic columns are documented in outputs/ml_dataset_a_feature_dictionary.json.",
        "- Target and diagnostic label roles are documented in outputs/ml_dataset_a_label_dictionary.json.",
        "",
        "## Leakage checks",
        "Feature columns exclude target columns. Prior-session percentiles are computed from prior sessions only. Early/morning/midday features use bars no later than their stated availability windows. Late-session fields are marked post_session_diagnostic.",
        "",
        "## Quality checks",
        quality_report.to_string(index=False),
        "",
        "## Split summary",
        split_summary.head(40).to_string(index=False),
        "",
    ])


def _best_row(results: pd.DataFrame, keys: list[str]) -> pd.Series:
    frame = results.copy()
    if "net_pnl" in frame.columns:
        frame["net_pnl"] = pd.to_numeric(frame["net_pnl"], errors="coerce").fillna(-1e18)
        sort_cols = ["net_pnl", *[k for k in keys if k in frame.columns]]
        ascending = [False] + [True] * (len(sort_cols) - 1)
        return frame.sort_values(sort_cols, ascending=ascending).iloc[0]
    return frame.sort_values([k for k in keys if k in frame.columns]).iloc[0]


def _time_slice(day: pd.DataFrame, start: str, end: str) -> pd.DataFrame:
    return day[(day["time_str"] >= start) & (day["time_str"] < end)]


def _segment_range(seg: pd.DataFrame) -> float:
    return float(seg["high"].max() - seg["low"].min()) if not seg.empty else np.nan


def _segment_close_position(seg: pd.DataFrame) -> float:
    if seg.empty:
        return np.nan
    return float(_close_position(pd.Series([seg["close"].iloc[-1]]), pd.Series([seg["low"].min()]), pd.Series([seg["high"].max()])).iloc[0])


def _close_position(close: pd.Series, low: pd.Series, high: pd.Series) -> pd.Series:
    rng = high - low
    return ((close - low) / rng.where(rng.ne(0), np.nan)).fillna(0.5).clip(0, 1)


def _direction(seg: pd.DataFrame) -> str:
    if seg.empty:
        return "unknown"
    return _direction_from_values(float(seg["open"].iloc[0]), float(seg["close"].iloc[-1]))


def _direction_from_values(open_value: float, close_value: float) -> str:
    if close_value > open_value:
        return "up"
    if close_value < open_value:
        return "down"
    return "flat"


def _segment_direction_value(seg: pd.DataFrame) -> float:
    if seg.empty:
        return 0.0
    return float(seg["close"].iloc[-1] - seg["open"].iloc[0])


def _prior_rank_percentile(value: float, prior_values: list[float]) -> float:
    vals = [float(v) for v in prior_values if pd.notna(v)]
    if not vals or pd.isna(value):
        return np.nan
    return round(float(sum(v <= float(value) for v in vals) / len(vals)), 6)


def _prior_percentile(prior_values: list[float], q: float) -> float:
    vals = [float(v) for v in prior_values if pd.notna(v)]
    if not vals:
        return np.nan
    return float(np.quantile(vals, q))
