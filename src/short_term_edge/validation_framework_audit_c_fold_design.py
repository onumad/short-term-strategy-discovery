from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable
import json

import pandas as pd

from .phase_common import ensure_directory, safe_divide, write_csv_artifact, write_json_artifact

RESEARCH_ONLY_GUARDRAIL = (
    "Research/simulation only. No live trading, broker adapters, order routing, webhooks, "
    "credential storage, automated execution, or LLM-driven trade decisions."
)
PHASES = ("phase10b", "phase11a", "phase12a", "phase13a", "phase14a", "phase15a")
FOLD_DESIGNS = (
    "existing_project_folds",
    "calendar_year_folds",
    "half_year_folds",
    "quarterly_folds",
    "rolling_6_month_test_folds",
    "rolling_3_month_test_folds",
    "expanding_train_recent_test_style",
)
OFFICIAL_POSITIVE_FOLD_GATE = 0.90
OFFICIAL_GATES_CHANGED = False
PAPER_TRADING_APPROVED = False
DIAGNOSTIC_ONLY_NO_SIGNALS_GENERATED = True
LOW_ACTIVITY_ACTIVE_DAYS_MIN = 5
LOW_ACTIVITY_TRADES_MIN = 10
DOMINATED_BY_ONE_DAY_THRESHOLD = 0.50


@dataclass(frozen=True)
class DailySeries:
    source: str
    label: str
    daily: pd.DataFrame
    folds: pd.DataFrame
    results: pd.DataFrame
    concentration: pd.DataFrame
    keys: dict[str, Any]


def load_validation_framework_audit_c_inputs(project_root: Path) -> dict[str, Any]:
    out = project_root / "outputs"
    required: dict[str, Path] = {
        "playbook_module_registry": out / "playbook_module_registry.csv",
        "research_signal_registry": out / "research_signal_registry.csv",
        "weak_fold_summary": out / "weak_fold_regime_audit_b_fold_summary.csv",
        "weak_fold_days": out / "weak_fold_regime_audit_b_weak_fold_days.csv",
        "market_regime_features": out / "weak_fold_regime_audit_b_market_regime_features.csv",
        "regime_comparison": out / "weak_fold_regime_audit_b_regime_comparison.csv",
        "weak_fold_recommendation": out / "weak_fold_regime_audit_b_next_action_recommendation.json",
    }
    for name in ("b", "c", "d"):
        required[f"scheduler_{name}_results"] = out / scheduler_result_file(name)
        required[f"scheduler_{name}_daily"] = out / f"playbook_scheduler_{name}_daily_pnl.csv"
        required[f"scheduler_{name}_folds"] = out / f"playbook_scheduler_{name}_walk_forward_folds.csv"
        required[f"scheduler_{name}_concentration"] = out / f"playbook_scheduler_{name}_concentration.csv"
        required[f"scheduler_{name}_recommendation"] = out / f"playbook_scheduler_{name}_next_action_recommendation.json"
    for name in ("b", "c", "d"):
        required[f"portfolio_{name}_daily"] = out / f"portfolio_audit_{name}_portfolio_daily_pnl.csv"
        required[f"portfolio_{name}_folds"] = out / f"portfolio_audit_{name}_portfolio_walk_forward_folds.csv"
    for phase in PHASES:
        required[f"{phase}_daily"] = out / f"{phase}_daily_pnl.csv"
    missing = [str(path) for path in required.values() if not path.exists()]
    if missing:
        raise FileNotFoundError(f"Missing Validation Framework Audit C input(s): {missing}")
    return {key: (_read_json(path) if path.suffix == ".json" else pd.read_csv(path)) for key, path in required.items()}


def run_validation_framework_audit_c_fold_design(project_root: Path) -> dict[str, Any]:
    data = load_validation_framework_audit_c_inputs(project_root)
    series = build_daily_series(data)
    current = current_fold_boundary_summary(series)
    base_series = choose_primary_playbook_series(series)
    existing_folds = existing_fold_windows(base_series.daily, base_series.folds)
    module_activity = module_activity_by_fold(data, existing_folds)
    playbook_activity = playbook_activity_by_fold(series, current)
    alt = alternative_fold_results(series)
    sensitivity = fold_sensitivity_summary(alt)
    regime = fold_regime_composition(base_series, data["market_regime_features"], existing_folds)
    gate = gate_sensitivity_by_fold_design(alt)
    policy = recommended_validation_policy(module_activity, sensitivity, regime)
    recommendation = make_next_action_recommendation(module_activity, sensitivity, regime, policy)
    return {
        "fold_boundary_summary": current,
        "alternative_fold_results": alt,
        "fold_sensitivity_summary": sensitivity,
        "module_activity_by_fold": module_activity,
        "playbook_activity_by_fold": playbook_activity,
        "fold_regime_composition": regime,
        "gate_sensitivity_by_fold_design": gate,
        "recommended_validation_policy": policy,
        "next_action_recommendation": recommendation,
        "inputs_loaded": loaded_input_names(),
        "primary_playbook_source": base_series.source,
        "primary_playbook_label": base_series.label,
    }


def scheduler_result_file(name: str) -> str:
    return {
        "b": "playbook_scheduler_b_priority_policy_results.csv",
        "c": "playbook_scheduler_c_pruning_policy_results.csv",
        "d": "playbook_scheduler_d_overlay_policy_results.csv",
    }[name]


def build_daily_series(data: dict[str, Any]) -> list[DailySeries]:
    specs: list[tuple[str, str, str, list[str]]] = [
        ("scheduler_b", "scheduler_b_results", "scheduler_b_daily", ["priority_policy", "portfolio_mode", "diagnostic_filter"]),
        ("scheduler_c", "scheduler_c_results", "scheduler_c_daily", ["pruning_variant", "priority_policy", "portfolio_mode"]),
        ("scheduler_d", "scheduler_d_results", "scheduler_d_daily", ["pruning_variant", "priority_policy", "portfolio_mode"]),
        ("portfolio_b", "", "portfolio_b_daily", ["portfolio_set", "portfolio_mode"]),
        ("portfolio_c", "", "portfolio_c_daily", ["portfolio_set", "portfolio_mode"]),
        ("portfolio_d", "", "portfolio_d_daily", ["portfolio_set", "portfolio_mode"]),
    ]
    out: list[DailySeries] = []
    for source, result_key, daily_key, dims in specs:
        daily_all = data[daily_key].copy()
        folds_all = data.get(f"{source.split('_')[0]}_{source.split('_')[1]}_folds", data.get(f"{source}_folds", pd.DataFrame())).copy()
        # Scheduler D retained the inherited column name pruning_variant; label it as overlay_variant in summaries.
        results_all = data[result_key].copy() if result_key else pd.DataFrame()
        concentration = data.get(f"{source}_concentration", pd.DataFrame()).copy()
        existing_dims = [d for d in dims if d in daily_all.columns]
        if not existing_dims:
            continue
        for keys, daily in daily_all.groupby(existing_dims, dropna=False, sort=True):
            keys_tuple = keys if isinstance(keys, tuple) else (keys,)
            key_map = {col: val for col, val in zip(existing_dims, keys_tuple)}
            label = entity_label(source, key_map)
            fold_seg = filter_by_keys(folds_all, key_map)
            result_seg = filter_by_keys(results_all, key_map) if not results_all.empty else pd.DataFrame()
            conc_seg = filter_by_keys(concentration, key_map) if not concentration.empty else pd.DataFrame()
            out.append(DailySeries(source=source, label=label, daily=normalize_daily(daily), folds=fold_seg.copy(), results=result_seg.copy(), concentration=conc_seg.copy(), keys=key_map))
    return out


def normalize_daily(daily: pd.DataFrame) -> pd.DataFrame:
    out = daily.copy()
    out["trading_session"] = pd.to_datetime(out["trading_session"], errors="coerce").dt.strftime("%Y-%m-%d")
    out = out.dropna(subset=["trading_session"]).sort_values("trading_session")
    return out.groupby("trading_session", as_index=False).agg(net_pnl=("net_pnl", "sum"))


def entity_label(source: str, key_map: dict[str, Any]) -> str:
    return source + "|" + "|".join(f"{k}={key_map[k]}" for k in sorted(key_map))


def filter_by_keys(df: pd.DataFrame, key_map: dict[str, Any]) -> pd.DataFrame:
    if df.empty:
        return df.copy()
    mask = pd.Series(True, index=df.index)
    for key, value in key_map.items():
        if key in df.columns:
            mask &= df[key].astype(str).eq(str(value))
    return df[mask].copy()


def choose_primary_playbook_series(series: list[DailySeries]) -> DailySeries:
    preferred = [s for s in series if s.source == "scheduler_d" and not s.results.empty]
    candidates = preferred or [s for s in series if s.source.startswith("scheduler") and not s.results.empty] or series
    if not candidates:
        raise ValueError("No daily playbook series available")
    return sorted(candidates, key=lambda s: (series_positive_fold_pct(s), float(s.daily["net_pnl"].sum())), reverse=True)[0]


def series_positive_fold_pct(series: DailySeries) -> float:
    if not series.results.empty and "positive_wf_test_folds_pct" in series.results.columns:
        return float(series.results.iloc[0].get("positive_wf_test_folds_pct", 0.0) or 0.0)
    if not series.folds.empty and "stress_pnl" in series.folds.columns:
        return safe_divide(int((series.folds["stress_pnl"] > 0).sum()), len(series.folds))
    return 0.0


def current_fold_boundary_summary(series: list[DailySeries]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for item in series:
        windows = existing_fold_windows(item.daily, item.folds)
        for window in windows:
            fold_id = int(window["fold"])
            fold_row = item.folds[item.folds.get("fold", pd.Series(dtype=int)).astype(str).eq(str(fold_id))].head(1)
            seg = item.daily[item.daily["trading_session"].isin(window["sessions"])]
            fold_pnl = float(fold_row.iloc[0].get("net_pnl", seg["net_pnl"].sum())) if not fold_row.empty else float(seg["net_pnl"].sum())
            stress = _float_or_none(fold_row.iloc[0].get("stress_pnl")) if not fold_row.empty else None
            active_days = int(fold_row.iloc[0].get("active_days", (seg["net_pnl"].abs() > 1e-9).sum())) if not fold_row.empty else int((seg["net_pnl"].abs() > 1e-9).sum())
            trades = trades_for_entity_result(item.results, active_days)
            rows.append({
                "source": item.source,
                "entity_label": item.label,
                "fold_id": fold_id,
                "fold_start": window["start"],
                "fold_end": window["end"],
                "days_in_fold": int(len(window["sessions"])),
                "active_days_in_fold": active_days,
                "trades_in_fold": trades,
                "fold_pnl": round(fold_pnl, 6),
                "fold_stress_pnl": stress,
                "weak_or_positive_status": "weak" if ((stress is not None and stress <= 0) or fold_pnl <= 0) else "positive",
                "calendar_region_key": f"fold_{fold_id}",
            })
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    weak_counts = out[out["weak_or_positive_status"].eq("weak")].groupby("calendar_region_key")["source"].nunique().rename("weak_source_count_same_calendar_region").reset_index()
    out = out.merge(weak_counts, on="calendar_region_key", how="left")
    out["weak_source_count_same_calendar_region"] = out["weak_source_count_same_calendar_region"].fillna(0).astype(int)
    out["same_calendar_region_weak_across_b_c_d_scheduler_b_c_d"] = out["weak_source_count_same_calendar_region"].ge(4)
    return out.sort_values(["source", "entity_label", "fold_id"]).reset_index(drop=True)


def existing_fold_windows(daily: pd.DataFrame, folds: pd.DataFrame) -> list[dict[str, Any]]:
    sessions = daily["trading_session"].astype(str).drop_duplicates().sort_values().tolist()
    if not sessions:
        return []
    fold_count = int(folds["fold"].max()) if not folds.empty and "fold" in folds.columns else 6
    return equal_count_windows(sessions, fold_count, "existing_project_folds")


def equal_count_windows(sessions: list[str], fold_count: int, design: str) -> list[dict[str, Any]]:
    if not sessions:
        return []
    fold_count = max(1, int(fold_count))
    size = max(1, len(sessions) // fold_count)
    rows = []
    for idx in range(fold_count):
        start = idx * size
        end = len(sessions) if idx == fold_count - 1 else min(len(sessions), (idx + 1) * size)
        chunk = sessions[start:end]
        if chunk:
            rows.append({"fold_design": design, "fold": idx + 1, "start": chunk[0], "end": chunk[-1], "sessions": chunk})
    return rows


def build_calendar_windows(daily: pd.DataFrame, design: str) -> list[dict[str, Any]]:
    frame = daily.copy()
    frame["date"] = pd.to_datetime(frame["trading_session"], errors="coerce")
    frame = frame.dropna(subset=["date"])
    if frame.empty:
        return []
    if design == "calendar_year_folds":
        frame["period"] = frame["date"].dt.year.astype(str)
    elif design == "half_year_folds":
        frame["period"] = frame["date"].dt.year.astype(str) + "H" + (((frame["date"].dt.month - 1) // 6) + 1).astype(str)
    elif design == "quarterly_folds":
        frame["period"] = frame["date"].dt.to_period("Q").astype(str)
    else:
        raise ValueError(design)
    rows = []
    for idx, (_, seg) in enumerate(frame.groupby("period", sort=True), start=1):
        sessions = seg["trading_session"].astype(str).tolist()
        rows.append({"fold_design": design, "fold": idx, "start": sessions[0], "end": sessions[-1], "sessions": sessions})
    return rows


def build_rolling_windows(daily: pd.DataFrame, months: int, design: str) -> list[dict[str, Any]]:
    frame = daily.copy()
    frame["date"] = pd.to_datetime(frame["trading_session"], errors="coerce")
    frame = frame.dropna(subset=["date"]).sort_values("date")
    if frame.empty:
        return []
    periods = sorted(frame["date"].dt.to_period("M").unique())
    rows = []
    for idx in range(0, max(0, len(periods) - months + 1)):
        keep = set(periods[idx : idx + months])
        seg = frame[frame["date"].dt.to_period("M").isin(keep)]
        sessions = seg["trading_session"].astype(str).tolist()
        if sessions:
            rows.append({"fold_design": design, "fold": len(rows) + 1, "start": sessions[0], "end": sessions[-1], "sessions": sessions})
    return rows


def expanding_train_recent_test_windows(daily: pd.DataFrame) -> list[dict[str, Any]]:
    # Diagnostic test windows only: recent quarters after an expanding history exists. Training rows are not used for scoring.
    q = build_calendar_windows(daily, "quarterly_folds")
    if len(q) <= 2:
        return q
    out = []
    for idx, window in enumerate(q[2:], start=1):
        row = dict(window)
        row["fold_design"] = "expanding_train_recent_test_style"
        row["fold"] = idx
        out.append(row)
    return out


def all_fold_windows(daily: pd.DataFrame, folds: pd.DataFrame, design: str) -> list[dict[str, Any]]:
    if design == "existing_project_folds":
        return existing_fold_windows(daily, folds)
    if design in {"calendar_year_folds", "half_year_folds", "quarterly_folds"}:
        return build_calendar_windows(daily, design)
    if design == "rolling_6_month_test_folds":
        return build_rolling_windows(daily, 6, design)
    if design == "rolling_3_month_test_folds":
        return build_rolling_windows(daily, 3, design)
    if design == "expanding_train_recent_test_style":
        return expanding_train_recent_test_windows(daily)
    raise ValueError(design)


def alternative_fold_results(series: list[DailySeries]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for item in series:
        for design in FOLD_DESIGNS:
            for window in all_fold_windows(item.daily, item.folds, design):
                seg = item.daily[item.daily["trading_session"].isin(window["sessions"])].copy()
                rows.append(fold_metric_row(item.source, item.label, item.keys, design, window, seg, item.results))
    return pd.DataFrame(rows).sort_values(["source", "entity_label", "fold_design", "fold_id"]).reset_index(drop=True)


def fold_metric_row(source: str, label: str, keys: dict[str, Any], design: str, window: dict[str, Any], seg: pd.DataFrame, results: pd.DataFrame) -> dict[str, Any]:
    pnl = float(seg["net_pnl"].sum()) if not seg.empty else 0.0
    active_days = int((seg["net_pnl"].abs() > 1e-9).sum()) if not seg.empty else 0
    trades = trades_for_entity_result(results, active_days)
    max_abs = float(seg["net_pnl"].abs().max()) if not seg.empty else 0.0
    abs_sum = float(seg["net_pnl"].abs().sum()) if not seg.empty else 0.0
    concentration = safe_divide(max_abs, abs_sum)
    row = {
        "source": source,
        "entity_label": label,
        "fold_design": design,
        "fold_id": int(window["fold"]),
        "fold_start": window["start"],
        "fold_end": window["end"],
        "days_in_fold": int(len(window["sessions"])),
        "active_days": active_days,
        "trades": int(trades),
        "fold_pnl": round(pnl, 6),
        "positive_fold": bool(pnl > 0),
        "too_few_trades": bool(trades < LOW_ACTIVITY_TRADES_MIN or active_days < LOW_ACTIVITY_ACTIVE_DAYS_MIN),
        "one_day_concentration": concentration,
        "dominated_by_one_day": bool(concentration >= DOMINATED_BY_ONE_DAY_THRESHOLD),
    }
    row.update({f"key_{k}": v for k, v in keys.items()})
    return row


def trades_for_entity_result(results: pd.DataFrame, active_days: int) -> int:
    if not results.empty and "trades" in results.columns:
        try:
            total = int(float(results.iloc[0].get("trades", 0) or 0))
            return max(total, active_days) if total else active_days
        except Exception:
            return active_days
    return active_days


def fold_sensitivity_summary(alt: pd.DataFrame) -> pd.DataFrame:
    rows = []
    if alt.empty:
        return pd.DataFrame()
    for (source, label, design), seg in alt.groupby(["source", "entity_label", "fold_design"], sort=True):
        rows.append({
            "source": source,
            "entity_label": label,
            "fold_design": design,
            "fold_count": int(len(seg)),
            "positive_fold_pct": safe_divide(int(seg["positive_fold"].sum()), len(seg)),
            "worst_fold_pnl": round(float(seg["fold_pnl"].min()), 6),
            "median_fold_pnl": round(float(seg["fold_pnl"].median()), 6),
            "fold_pnl_standard_deviation": round(float(seg["fold_pnl"].std(ddof=0) or 0.0), 6),
            "median_active_days_per_fold": round(float(seg["active_days"].median()), 6),
            "median_trades_per_fold": round(float(seg["trades"].median()), 6),
            "folds_with_too_few_trades": int(seg["too_few_trades"].sum()),
            "folds_dominated_by_one_day": int(seg["dominated_by_one_day"].sum()),
            "median_one_day_concentration": round(float(seg["one_day_concentration"].median()), 6),
        })
    summary = pd.DataFrame(rows)
    # Does design choice materially change this entity's conclusion?
    rng = summary.groupby(["source", "entity_label"])["positive_fold_pct"].agg(lambda x: float(x.max() - x.min())).rename("positive_fold_pct_range").reset_index()
    summary = summary.merge(rng, on=["source", "entity_label"], how="left")
    summary["conclusion_materially_changes"] = summary["positive_fold_pct_range"].ge(0.25)
    return summary.sort_values(["source", "entity_label", "fold_design"]).reset_index(drop=True)


def module_activity_by_fold(data: dict[str, Any], windows: list[dict[str, Any]]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for phase in PHASES:
        daily = data[f"{phase}_daily"].copy()
        if daily.empty:
            continue
        daily["trading_session"] = pd.to_datetime(daily["trading_session"], errors="coerce").dt.strftime("%Y-%m-%d")
        grouped = daily.groupby("trading_session", as_index=False).agg(trades=("trades", "sum"), net_pnl=("net_pnl", "sum"))
        for window in windows:
            seg = grouped[grouped["trading_session"].isin(window["sessions"])]
            active_days = int((seg["trades"] > 0).sum()) if not seg.empty else 0
            trades = int(seg["trades"].sum()) if not seg.empty else 0
            rows.append({
                "module_group": phase,
                "fold_design": window["fold_design"],
                "fold_id": int(window["fold"]),
                "fold_start": window["start"],
                "fold_end": window["end"],
                "days_in_fold": int(len(window["sessions"])),
                "active_days": active_days,
                "trades": trades,
                "pnl": round(float(seg["net_pnl"].sum()) if not seg.empty else 0.0, 6),
                "enough_observations": bool(active_days >= LOW_ACTIVITY_ACTIVE_DAYS_MIN and trades >= LOW_ACTIVITY_TRADES_MIN),
                "low_activity_makes_pass_fail_noisy": bool(active_days < LOW_ACTIVITY_ACTIVE_DAYS_MIN or trades < LOW_ACTIVITY_TRADES_MIN),
            })
    return pd.DataFrame(rows).sort_values(["module_group", "fold_id"]).reset_index(drop=True)


def playbook_activity_by_fold(series: list[DailySeries], current: pd.DataFrame) -> pd.DataFrame:
    if current.empty:
        return current.copy()
    cols = ["source", "entity_label", "fold_id", "fold_start", "fold_end", "days_in_fold", "active_days_in_fold", "trades_in_fold", "fold_pnl", "weak_or_positive_status"]
    return current[cols].copy().rename(columns={"active_days_in_fold": "active_days", "trades_in_fold": "trades", "weak_or_positive_status": "fold_status"})


def fold_regime_composition(base_series: DailySeries, features: pd.DataFrame, windows: list[dict[str, Any]]) -> pd.DataFrame:
    if features.empty:
        return pd.DataFrame(columns=["fold_id"])
    feats = features.copy()
    feats["trading_session"] = pd.to_datetime(feats["trading_session"], errors="coerce").dt.strftime("%Y-%m-%d")
    active_sessions = set(base_series.daily.loc[base_series.daily["net_pnl"].abs() > 1e-9, "trading_session"].astype(str))
    rows = []
    for window in windows:
        seg = feats[feats["trading_session"].isin(window["sessions"])]
        pnl = float(base_series.daily[base_series.daily["trading_session"].isin(window["sessions"])]["net_pnl"].sum())
        high_movement_no_trade = [s for s in seg.loc[seg.get("high_volatility_bucket", False).fillna(False).astype(bool), "trading_session"].astype(str) if s not in active_sessions]
        rows.append({
            "source": base_series.source,
            "entity_label": base_series.label,
            "fold_design": window["fold_design"],
            "fold_id": int(window["fold"]),
            "fold_start": window["start"],
            "fold_end": window["end"],
            "day_count_with_features": int(len(seg)),
            "fold_pnl": round(pnl, 6),
            "is_weak_fold": bool(pnl <= 0),
            "high_vol_frequency": frequency(seg, "high_volatility_bucket"),
            "trend_day_frequency": frequency(seg, "full_day_trend_proxy"),
            "range_day_frequency": frequency(seg, "range_day_proxy"),
            "power_hour_expansion_frequency": frequency(seg, "power_hour_expansion"),
            "prior_level_interaction_frequency": frequency(seg, "prior_rth_high_low_interaction_flag"),
            "no_trade_high_movement_day_frequency": safe_divide(len(high_movement_no_trade), len(seg)),
            "diagnosis_regime_heavy": bool(len(seg) and (frequency(seg, "high_volatility_bucket") >= 0.50 or frequency(seg, "full_day_trend_proxy") >= 0.50)),
            "diagnosis_low_sample": bool(len(window["sessions"]) < 20 or int(base_series.daily[base_series.daily["trading_session"].isin(window["sessions"])] ["net_pnl"].abs().gt(1e-9).sum()) < LOW_ACTIVITY_ACTIVE_DAYS_MIN),
        })
    out = pd.DataFrame(rows)
    if not out.empty:
        out["diagnosis_outlier_affected"] = out["fold_id"].map(lambda _: False)
        out["diagnosis_broadly_weak_across_conditions"] = out["is_weak_fold"] & ~out["diagnosis_regime_heavy"] & ~out["diagnosis_low_sample"]
    return out


def frequency(seg: pd.DataFrame, col: str) -> float:
    if seg.empty or col not in seg.columns:
        return 0.0
    return safe_divide(int(seg[col].fillna(False).astype(bool).sum()), len(seg))


def gate_sensitivity_by_fold_design(alt: pd.DataFrame) -> pd.DataFrame:
    rows = []
    thresholds = [0.90, 0.833, 0.75, 0.667]
    worst_thresholds = [0.0, -250.0, -500.0, -1000.0]
    active_mins = [1, 5, 10, 20]
    for (source, label, design), seg in alt.groupby(["source", "entity_label", "fold_design"], sort=True):
        pct = safe_divide(int(seg["positive_fold"].sum()), len(seg))
        worst = float(seg["fold_pnl"].min())
        row = {
            "source": source,
            "entity_label": label,
            "fold_design": design,
            "positive_fold_pct": pct,
            "worst_fold_pnl": round(worst, 6),
            "official_positive_wf_test_folds_pct_gate": OFFICIAL_POSITIVE_FOLD_GATE,
            "official_gates_changed": False,
        }
        for t in thresholds:
            row[f"positive_wf_test_folds_pct_ge_{str(t).replace('.', '_')}"] = bool(pct >= t)
        for t in worst_thresholds:
            row[f"worst_fold_pnl_ge_{str(t).replace('-', 'neg_').replace('.', '_')}"] = bool(worst >= t)
        for m in active_mins:
            row[f"all_folds_active_days_ge_{m}"] = bool((seg["active_days"] >= m).all())
        rows.append(row)
    return pd.DataFrame(rows).sort_values(["source", "entity_label", "fold_design"]).reset_index(drop=True)


def recommended_validation_policy(module_activity: pd.DataFrame, sensitivity: pd.DataFrame, regime: pd.DataFrame) -> dict[str, Any]:
    rare_sparse = bool(not module_activity.empty and module_activity["low_activity_makes_pass_fail_noisy"].mean() >= 0.25)
    material_changes = bool(not sensitivity.empty and sensitivity["conclusion_materially_changes"].any())
    weak_regime_heavy = bool(not regime.empty and regime.loc[regime["is_weak_fold"], "diagnosis_regime_heavy"].mean() >= 0.5) if not regime.empty and regime["is_weak_fold"].any() else False
    all_designs_unstable = bool(not sensitivity.empty and (sensitivity.groupby("fold_design")["positive_fold_pct"].median() < 0.667).all())
    return {
        "diagnostic_only": True,
        "official_gates_changed": False,
        "paper_trading_approved": False,
        "live_trading_approved": False,
        "new_strategy_signals_generated": False,
        "keep_official_gates_unchanged": True,
        "add_rare_module_fold_adequacy_diagnostics": True,
        "report_module_and_playbook_fold_stability_separately": True,
        "require_minimum_fold_activity_before_interpreting_module_fold_result": True,
        "minimum_module_active_days_per_fold_for_interpretation": LOW_ACTIVITY_ACTIVE_DAYS_MIN,
        "minimum_module_trades_per_fold_for_interpretation": LOW_ACTIVITY_TRADES_MIN,
        "alternative_fold_designs_are_diagnostic_companion_only": True,
        "require_out_of_sample_future_data_before_promotion": True,
        "do_not_loosen_paper_review_gates": True,
        "rare_modules_too_sparse_for_module_level_fold_gates": rare_sparse,
        "fold_conclusions_change_by_design": material_changes,
        "weak_folds_regime_composition_driven": weak_regime_heavy,
        "fold_instability_consistent_across_designs": all_designs_unstable,
    }


def make_next_action_recommendation(module_activity: pd.DataFrame, sensitivity: pd.DataFrame, regime: pd.DataFrame, policy: dict[str, Any]) -> dict[str, Any]:
    if policy["fold_conclusions_change_by_design"]:
        action = "validation_framework_d_standardize_playbook_folds"
        rationale = "Diagnostic conclusions materially change under deterministic fold-design alternatives."
    elif policy["rare_modules_too_sparse_for_module_level_fold_gates"]:
        action = "create_rare_module_validation_track"
        rationale = "Rare specialized modules often have too few active days/trades per fold for meaningful module-level fold gates."
    elif policy["weak_folds_regime_composition_driven"]:
        action = "phase16a_targeted_regime_module_scout"
        rationale = "Weak folds are materially regime-composition heavy."
    elif policy["fold_instability_consistent_across_designs"]:
        action = "phase16a_targeted_regime_module_scout"
        rationale = "Fold instability remains consistent across deterministic fold designs."
    else:
        action = "pause_strategy_search_and_review_manual_examples"
        rationale = "No single fold-design, sparse-module, regime, or scheduler/overlap diagnosis clearly dominates."
    return {
        "next_action": action,
        "rationale": rationale,
        "diagnostic_only": True,
        "official_gates_changed": False,
        "paper_trading_approved": False,
        "live_trading_approved": False,
        "diagnostic_only_no_signals_generated": True,
        "new_strategy_signals_generated": False,
        "strategy_searches_run": False,
        "candidate_results_changed": False,
        "candidates_promoted": False,
        "policy_summary": policy,
    }


def render_validation_framework_audit_c_report(result: dict[str, Any]) -> str:
    rec = result["next_action_recommendation"]
    policy = result["recommended_validation_policy"]
    sensitivity = result["fold_sensitivity_summary"]
    modules = result["module_activity_by_fold"]
    regime = result["fold_regime_composition"]
    current = result["fold_boundary_summary"]
    lines = [
        "# Validation Framework Audit C — Fold Design",
        "",
        RESEARCH_ONLY_GUARDRAIL,
        "",
        "Diagnostic fold-design audit only. No new signals, no strategy searches, no candidate-result changes, no official gate changes, no promotions, no paper-trading approval, and no live-trading functionality were added.",
        "",
        "## Summary",
        "",
        f"- Primary playbook series for fold-regime diagnostics: `{result['primary_playbook_source']}` / `{result['primary_playbook_label']}`",
        f"- Current fold rows audited: `{len(current)}`",
        f"- Alternative fold rows computed: `{len(result['alternative_fold_results'])}`",
        f"- Module activity rows computed: `{len(modules)}`",
        f"- Fold conclusions change by design: `{policy['fold_conclusions_change_by_design']}`",
        f"- Rare modules too sparse for module-level fold gates: `{policy['rare_modules_too_sparse_for_module_level_fold_gates']}`",
        f"- Weak folds regime-composition driven: `{policy['weak_folds_regime_composition_driven']}`",
        f"- Fold instability consistent across designs: `{policy['fold_instability_consistent_across_designs']}`",
        f"- Next action: `{rec['next_action']}`",
        f"- Rationale: {rec['rationale']}",
        "",
        "## Current fold boundary findings",
        "",
        markdown_table(current.head(40)),
        "",
        "## Alternative fold design findings",
        "",
        markdown_table(sensitivity.sort_values(["conclusion_materially_changes", "positive_fold_pct_range", "source"], ascending=[False, False, True]).head(50)),
        "",
        "## Rare-module fold adequacy",
        "",
        markdown_table(modules.groupby("module_group", as_index=False).agg(folds=("fold_id", "count"), low_activity_folds=("low_activity_makes_pass_fail_noisy", "sum"), median_active_days=("active_days", "median"), median_trades=("trades", "median"), total_pnl=("pnl", "sum")) if not modules.empty else modules),
        "",
        "## Fold regime composition",
        "",
        markdown_table(regime),
        "",
        "## Recommended validation policy",
        "",
    ]
    for key, value in policy.items():
        lines.append(f"- `{key}`: `{value}`")
    lines += [
        "",
        "## Guardrails",
        "",
        "Official gates changed: `false`.",
        "Paper trading approved: `false`.",
        "New strategy signals generated: `false`.",
        "Strategy searches run: `false`.",
        "Live trading approved: `false`.",
        "",
    ]
    return "\n".join(lines)


def write_validation_framework_audit_c_outputs(result: dict[str, Any], output_dir: Path, report_path: Path) -> dict[str, Path]:
    ensure_directory(output_dir)
    ensure_directory(report_path.parent)
    mapping = {
        "fold_boundary_summary": output_dir / "validation_framework_audit_c_fold_boundary_summary.csv",
        "alternative_fold_results": output_dir / "validation_framework_audit_c_alternative_fold_results.csv",
        "fold_sensitivity_summary": output_dir / "validation_framework_audit_c_fold_sensitivity_summary.csv",
        "module_activity_by_fold": output_dir / "validation_framework_audit_c_module_activity_by_fold.csv",
        "playbook_activity_by_fold": output_dir / "validation_framework_audit_c_playbook_activity_by_fold.csv",
        "fold_regime_composition": output_dir / "validation_framework_audit_c_fold_regime_composition.csv",
        "gate_sensitivity_by_fold_design": output_dir / "validation_framework_audit_c_gate_sensitivity_by_fold_design.csv",
    }
    paths: dict[str, Path] = {}
    for key, path in mapping.items():
        write_csv_artifact(result[key], path)
        paths[key] = path
    policy_path = output_dir / "validation_framework_audit_c_recommended_validation_policy.json"
    rec_path = output_dir / "validation_framework_audit_c_next_action_recommendation.json"
    write_json_artifact(result["recommended_validation_policy"], policy_path)
    write_json_artifact(result["next_action_recommendation"], rec_path)
    report_path.write_text(render_validation_framework_audit_c_report(result), encoding="utf-8")
    paths["recommended_validation_policy"] = policy_path
    paths["recommendation"] = rec_path
    paths["report"] = report_path
    return paths


def markdown_table(df: pd.DataFrame, max_rows: int = 30) -> str:
    if df is None or df.empty:
        return "_No rows._"
    view = df.head(max_rows).copy()
    cols = list(view.columns)
    lines = ["| " + " | ".join(cols) + " |", "| " + " | ".join(["---"] * len(cols)) + " |"]
    for _, row in view.iterrows():
        lines.append("| " + " | ".join(str(row.get(c, "")).replace("\n", " ") for c in cols) + " |")
    return "\n".join(lines)


def loaded_input_names() -> list[str]:
    names = [
        "outputs/playbook_module_registry.csv",
        "outputs/research_signal_registry.csv",
        "outputs/weak_fold_regime_audit_b_fold_summary.csv",
        "outputs/weak_fold_regime_audit_b_weak_fold_days.csv",
        "outputs/weak_fold_regime_audit_b_market_regime_features.csv",
        "outputs/weak_fold_regime_audit_b_regime_comparison.csv",
        "outputs/weak_fold_regime_audit_b_next_action_recommendation.json",
    ]
    for name in ("b", "c", "d"):
        names.extend([
            f"outputs/playbook_scheduler_{name}_daily_pnl.csv",
            f"outputs/playbook_scheduler_{name}_walk_forward_folds.csv",
            f"outputs/playbook_scheduler_{name}_concentration.csv",
            f"outputs/playbook_scheduler_{name}_next_action_recommendation.json",
        ])
    names.extend([
        "outputs/playbook_scheduler_b_priority_policy_results.csv",
        "outputs/playbook_scheduler_c_pruning_policy_results.csv",
        "outputs/playbook_scheduler_d_overlay_policy_results.csv",
    ])
    for name in ("b", "c", "d"):
        names.extend([f"outputs/portfolio_audit_{name}_portfolio_daily_pnl.csv", f"outputs/portfolio_audit_{name}_portfolio_walk_forward_folds.csv"])
    for phase in PHASES:
        names.append(f"outputs/{phase}_daily_pnl.csv")
    return names


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _float_or_none(value: Any) -> float | None:
    try:
        if pd.isna(value):
            return None
        return float(value)
    except Exception:
        return None
