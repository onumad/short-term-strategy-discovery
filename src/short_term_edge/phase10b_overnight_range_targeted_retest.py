from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from .backtest import split_sessions
from .phase_common import (
    add_cost_waterfall,
    concentration_diagnostics,
    daily_pnl_summary,
    deterministic_json,
    fold_summary,
    grouped_trade_summary,
    positive_concentration,
    safe_divide,
    serialize_specs,
    standard_zero_metrics,
)
from .phase10a_overnight_range_breakout_fade import (
    Phase10ASpec,
    _feature_bars,
    _simulate_trades,
    compute_overnight_levels,
    generate_phase10a_signals,
)


@dataclass(frozen=True)
class Phase10BConfig:
    max_specs: int = 48
    recent_sessions: int = 252
    train_sessions: int = 75
    validation_sessions: int = 25
    test_sessions: int = 25
    step_sessions: int = 25
    min_trades: int = 60
    min_active_days: int = 35
    drawdown_limit: float = -6_000.0
    worst_fold_limit: float = -1_500.0
    concentration_limit: float = 0.15
    trade_concentration_limit: float = 0.08


@dataclass(frozen=True)
class Phase10BSpec:
    axis: str
    branch: str
    side: str
    timeframe: int
    entry_window: str
    entry_start: str
    entry_end: str
    execution_exit_variant: str
    range_filter: str
    gap_filter: str
    touch_filter: str
    max_trades_per_day: int
    atr_cap_multiple: float = 1.25
    buffer_ticks: int = 1
    target_r: float = 1.5
    min_minutes_between_entries: int = 60
    time_stop_minutes: int = 45

    @property
    def candidate_id(self) -> str:
        return (
            f"MNQ_10b_{self.axis}_{self.branch}_{self.side}_tf{self.timeframe}_{self.entry_window}_"
            f"{self.range_filter}_{self.gap_filter}_{self.touch_filter}_mt{self.max_trades_per_day}"
        )

    def to_dict(self) -> dict[str, Any]:
        return {"candidate_id": self.candidate_id, "instrument": "MNQ", **self.__dict__}


def build_phase10b_specs(config: Phase10BConfig = Phase10BConfig()) -> list[Phase10BSpec]:
    specs: list[Phase10BSpec] = []
    for range_filter in ("all_ranges", "exclude_narrowest_20", "exclude_widest_20", "middle_60_only"):
        for gap_filter in ("all_gaps", "gap_down_or_flat"):
            for touch_filter in ("all_touches", "first_touch_only"):
                for max_trades in (1, 2):
                    specs.append(Phase10BSpec("primary_short_midday_breakout", "overnight_range_breakout", "short", 15, "midday_response", "10:30", "13:30", "next_bar_open_hard_stop_time_exit", range_filter, gap_filter, touch_filter, max_trades))
    for timeframe in (5, 15):
        for range_filter in ("all_ranges", "exclude_narrowest_20"):
            for touch_filter in ("all_touches", "first_touch_only"):
                for max_trades in (1, 2):
                    specs.append(Phase10BSpec("secondary_long_opening_fade", "overnight_range_fade", "long", timeframe, "opening_response", "09:35", "10:30", "next_bar_open_hard_stop_time_exit", range_filter, "all_gaps", touch_filter, max_trades, min_minutes_between_entries=30 if timeframe == 5 else 60, time_stop_minutes=30 if timeframe == 5 else 45))
    return specs[: max(int(config.max_specs), 0)]


def _as_10a_spec(spec: Phase10BSpec) -> Phase10ASpec:
    return Phase10ASpec(branch=spec.branch, side=spec.side, timeframe=spec.timeframe, entry_window=spec.entry_window, entry_start=spec.entry_start, entry_end=spec.entry_end, execution_exit_variant=spec.execution_exit_variant, atr_cap_multiple=spec.atr_cap_multiple, buffer_ticks=spec.buffer_ticks, target_r=spec.target_r, max_trades_per_day=spec.max_trades_per_day, min_minutes_between_entries=spec.min_minutes_between_entries, time_stop_minutes=spec.time_stop_minutes)


def apply_phase10b_pre_entry_filters(trades: pd.DataFrame, spec: Phase10BSpec) -> pd.DataFrame:
    if trades.empty:
        return trades.copy()
    out = trades.copy()
    if spec.range_filter == "exclude_narrowest_20":
        out = out[out["overnight_range_percentile"] > 0.20]
    elif spec.range_filter == "exclude_widest_20":
        out = out[out["overnight_range_percentile"] < 0.80]
    elif spec.range_filter == "middle_60_only":
        out = out[(out["overnight_range_percentile"] > 0.20) & (out["overnight_range_percentile"] < 0.80)]
    if spec.gap_filter == "gap_down_or_flat":
        out = out[out["gap_from_prior_rth_close"].fillna(0.0) <= 0.0]
    if spec.touch_filter == "first_touch_only":
        out = out[out["first_touch"].eq(1)]
    return out.reset_index(drop=True)


def run_phase10b_retest(bars_or_trades: pd.DataFrame, config: Phase10BConfig = Phase10BConfig()) -> dict[str, pd.DataFrame]:
    specs = build_phase10b_specs(config)
    if {"timestamp", "session_segment", "open", "high", "low", "close"}.issubset(bars_or_trades.columns):
        base_trades = _build_base_trade_pool(bars_or_trades, specs)
        sessions = sorted(bars_or_trades["trading_session"].dropna().astype(str).unique().tolist())
        level_diagnostics = compute_overnight_levels(bars_or_trades)
    else:
        base_trades = bars_or_trades.copy()
        if "base_candidate_id" not in base_trades.columns:
            base_trades["base_candidate_id"] = _as_10a_spec(build_phase10b_specs(config)[0]).candidate_id
        sessions = sorted(base_trades["trading_session"].dropna().astype(str).unique().tolist())
        level_diagnostics = pd.DataFrame()
    split_map = split_sessions(sessions)
    rows = []
    trade_frames = []
    fold_frames = []
    for spec in specs:
        trades = apply_phase10b_pre_entry_filters(base_trades[base_trades["base_candidate_id"].eq(_as_10a_spec(spec).candidate_id)], spec)
        if not trades.empty:
            trades = trades.copy()
            trades["candidate_id"] = spec.candidate_id
            trades["split"] = trades["trading_session"].astype(str).map(split_map)
            trades.update(pd.DataFrame([spec.to_dict()] * len(trades), index=trades.index))
            _add_cost_waterfall(trades)
            trade_frames.append(trades)
            fold_frames.append(_fold_rows(trades, spec, sessions, config))
        rows.append(_candidate_row(spec, trades, sessions, split_map, config))
    trade_logs = pd.concat(trade_frames, ignore_index=True) if trade_frames else pd.DataFrame()
    folds = pd.concat(fold_frames, ignore_index=True) if fold_frames else pd.DataFrame()
    candidates = pd.DataFrame(rows).sort_values(["phase10b_score", "stress_pnl"], ascending=[False, False]).reset_index(drop=True)
    candidates.insert(0, "phase10b_rank", range(1, len(candidates) + 1))
    return {
        "candidate_results": candidates,
        "trade_logs": trade_logs,
        "walk_forward_folds": folds,
        "daily_pnl": _daily_pnl(trade_logs),
        "concentration_diagnostics": _concentration(trade_logs),
        "validation_failure_attribution": _validation_attribution(trade_logs),
        "range_regime_summary": _summary(trade_logs, "range_filter"),
        "gap_regime_summary": _summary(trade_logs, "gap_filter"),
        "touch_sequence_summary": _summary(trade_logs, "touch_filter"),
        "branch_summary": _summary(trade_logs, "axis"),
        "exit_reason_summary": _summary(trade_logs, "exit_reason"),
        "mfe_mae_summary": _mfe_mae_summary(trade_logs),
        "level_diagnostics": level_diagnostics,
        "specs": pd.DataFrame([s.to_dict() for s in specs]),
    }


def _build_base_trade_pool(bars: pd.DataFrame, specs: list[Phase10BSpec]) -> pd.DataFrame:
    frames = []
    seen: set[str] = set()
    for spec in specs:
        base = _as_10a_spec(spec)
        if base.candidate_id in seen:
            continue
        seen.add(base.candidate_id)
        featured = _feature_bars(bars, base)
        trades = _simulate_trades(featured, generate_phase10a_signals(bars, base), base)
        if not trades.empty:
            trades = trades.copy()
            trades["base_candidate_id"] = base.candidate_id
            frames.append(trades)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def _add_cost_waterfall(trades: pd.DataFrame) -> None:
    add_cost_waterfall(trades, instrument_symbol="MNQ", inplace=True)


def _candidate_row(spec: Phase10BSpec, trades: pd.DataFrame, sessions: list[str], split_map: dict[Any, str], config: Phase10BConfig) -> dict[str, Any]:
    row = spec.to_dict()
    if trades.empty:
        row.update(_zero_metrics())
    else:
        t = trades.copy()
        t["split"] = t["trading_session"].astype(str).map(split_map)
        _add_cost_waterfall(t)
        net = float(t["net_pnl"].sum())
        equity = t["net_pnl"].cumsum()
        daily = t.groupby("trading_session")["net_pnl"].sum()
        folds = _fold_rows(t, spec, sessions, config)
        row.update({"trades": len(t), "active_days": int(t["trading_session"].nunique()), "trades_per_active_day": _div(len(t), t["trading_session"].nunique()), "gross_pnl": round(float(t["gross_pnl"].sum()), 2), "fees_only_pnl": round(float(t["fees_only_pnl"].sum()), 2), "normal_slippage_pnl": round(float(t["normal_slippage_pnl"].sum()), 2), "net_pnl": round(net, 2), "stress_pnl": round(float(t["stress_pnl"].sum()), 2), "validation_pnl": round(float(t.loc[t["split"].eq("validation"), "net_pnl"].sum()), 2), "holdout_pnl": round(float(t.loc[t["split"].eq("holdout"), "net_pnl"].sum()), 2), "max_drawdown": round(float((equity - equity.cummax()).min()), 2), "best_day_concentration": _conc(float(daily.max()), net), "best_trade_concentration": _conc(float(t["net_pnl"].max()), net), "avg_mfe": round(float(t["mfe"].mean()), 2), "avg_mae": round(float(t["mae"].mean()), 2), **_fold_summary(folds)})
    row["phase10b_label"] = _label(row, config)
    row["research_axis_status"] = _axis_status(row)
    row["phase10b_score"] = round(float(row.get("stress_pnl", 0)) + float(row.get("walk_forward_stress_pnl", 0)) - abs(float(row.get("max_drawdown", 0))), 4)
    row["reject_reasons"] = _reasons(row, config)
    return row


def _label(r: dict[str, Any], c: Phase10BConfig) -> str:
    if r.get("trades", 0) < c.min_trades or r.get("active_days", 0) < c.min_active_days or not (1 <= r.get("trades_per_active_day", 0) <= 3): return "phase10b_rejected_low_activity"
    if r.get("net_pnl", 0) <= 0 or r.get("stress_pnl", 0) <= 0: return "phase10b_rejected_negative_stress"
    if r.get("validation_pnl", 0) <= 0: return "phase10b_rejected_negative_validation"
    if r.get("holdout_pnl", 0) <= 0: return "phase10b_rejected_negative_holdout"
    if r.get("max_drawdown", 0) < c.drawdown_limit: return "phase10b_rejected_drawdown"
    if r.get("walk_forward_stress_pnl", 0) <= 0 or r.get("positive_wf_test_folds_pct", 0) < .9 or r.get("worst_wf_test_fold", 0) < c.worst_fold_limit: return "phase10b_rejected_fold_instability"
    if r.get("best_day_concentration", 1) > c.concentration_limit or r.get("best_trade_concentration", 1) > c.trade_concentration_limit: return "phase10b_rejected_concentration"
    return "phase10b_candidate_for_paper_review"


def _axis_status(r: dict[str, Any]) -> str:
    if r.get("phase10b_label") == "phase10b_candidate_for_paper_review": return "axis_review_packet_candidate"
    if r.get("stress_pnl", 0) > 0 and r.get("holdout_pnl", 0) > 0 and r.get("best_day_concentration", 1) <= .15: return "axis_targeted_retest_candidate"
    if r.get("stress_pnl", 0) > 0 and r.get("holdout_pnl", 0) > 0 and (r.get("best_day_concentration", 1) > .15 or r.get("best_trade_concentration", 1) > .08): return "axis_positive_but_concentrated"
    if r.get("gross_pnl", 0) > 0 and r.get("stress_pnl", 0) <= 0: return "axis_positive_but_cost_sensitive"
    if r.get("stress_pnl", 0) > 0: return "axis_positive_but_unstable"
    return "axis_failed"


def _reasons(r: dict[str, Any], c: Phase10BConfig) -> str:
    checks = [("low activity", r.get("trades", 0) < c.min_trades), ("negative stress", r.get("stress_pnl", 0) <= 0), ("negative validation", r.get("validation_pnl", 0) <= 0), ("negative holdout", r.get("holdout_pnl", 0) <= 0), ("fold instability", r.get("positive_wf_test_folds_pct", 0) < .9), ("concentration", r.get("best_day_concentration", 1) > c.concentration_limit or r.get("best_trade_concentration", 1) > c.trade_concentration_limit)]
    return "; ".join(name for name, bad in checks if bad) or "survived Phase 10B gates; review packet only"


def make_phase10b_recommendation(result: dict[str, pd.DataFrame]) -> dict[str, Any]:
    c = result["candidate_results"]
    if c.empty:
        return {"next_action": "phase11a_opening_range_fade_stricter_confirmation", "rationale": "No Phase 10B candidates were produced."}
    paper = c[c["phase10b_label"].eq("phase10b_candidate_for_paper_review")]
    if not paper.empty:
        return {"next_action": "prepare_phase10b_review_packet", "rationale": "One candidate passed strict gates; review packet only, not paper approval.", "top_candidate": paper.iloc[0].to_dict()}
    positive = c[(c["stress_pnl"] > 0) & (c["holdout_pnl"] > 0)]
    if not positive.empty:
        return {"next_action": "park_overnight_range_as_research_signal", "rationale": "Phase 10B remained positive on some axes but failed promotion gates, usually concentration/fold/validation.", "top_candidate": positive.iloc[0].to_dict()}
    return {"next_action": "phase11a_opening_range_fade_stricter_confirmation", "rationale": "Both targeted overnight range axes failed; pivot."}


def render_phase10b_report(result: dict[str, pd.DataFrame], recommendation: dict[str, Any], report_path: Path) -> str:
    c = result["candidate_results"]
    counts = c["phase10b_label"].value_counts().to_dict() if not c.empty else {}
    status = c["research_axis_status"].value_counts().to_dict() if not c.empty else {}
    lines = ["# Phase 10B Overnight Range Targeted Diagnostic Retest", "", "Research/simulation only. No live trading, broker adapters, order routing, webhooks, credential storage, automated execution, or LLM-driven trade decisions.", "", "## Summary", "", f"- Specs evaluated: `{len(c)}`", f"- Trade rows: `{len(result['trade_logs'])}`", f"- Label counts: `{counts}`", f"- Research axis status counts: `{status}`", f"- Next action: `{recommendation.get('next_action')}`", f"- Rationale: {recommendation.get('rationale')}", "", "## Attribution Then Retest", "", "Part A attributes Phase 10A-like targeted axes by validation, range/gap/touch, branch, exit reason, and MFE/MAE. Part B retests only pre-entry no-lookahead controls.", "", "| Candidate | Status | Label | Net | Stress | Val | Holdout | WF Stress | Notes |", "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- |"]
    for _, r in c.head(12).iterrows():
        lines.append(f"| `{r['candidate_id']}` | {r['research_axis_status']} | {r['phase10b_label']} | ${float(r['net_pnl']):.2f} | ${float(r['stress_pnl']):.2f} | ${float(r['validation_pnl']):.2f} | ${float(r['holdout_pnl']):.2f} | ${float(r['walk_forward_stress_pnl']):.2f} | {r['reject_reasons']} |")
    return "\n".join(lines) + "\n"


def _fold_rows(trades: pd.DataFrame, spec: Phase10BSpec, sessions: list[str], c: Phase10BConfig) -> pd.DataFrame:
    rows=[]; window=c.train_sessions+c.validation_sessions+c.test_sessions; start=0; fold=1
    while start+window <= len(sessions):
        test=sessions[start+c.train_sessions+c.validation_sessions:start+window]; seg=trades[trades["trading_session"].astype(str).isin(test)]
        rows.append({"candidate_id":spec.candidate_id,"fold":fold,"net_pnl":round(float(seg["net_pnl"].sum()),2),"stress_pnl":round(float(seg["stress_pnl"].sum()),2),"trades":len(seg)})
        start += c.step_sessions; fold += 1
    return pd.DataFrame(rows)

def _fold_summary(f: pd.DataFrame) -> dict[str, Any]:
    return fold_summary(f)

def _zero_metrics() -> dict[str, Any]:
    return standard_zero_metrics(include_gross_waterfall=True)

def _daily_pnl(t): return daily_pnl_summary(t)
def _concentration(t): return concentration_diagnostics(t)
def _summary(t, col):
    return grouped_trade_summary(t, col, include_gross=True)
def _validation_attribution(t): return pd.DataFrame() if t.empty else t.groupby(["candidate_id","split"]).agg(trades=("net_pnl","size"),net_pnl=("net_pnl","sum"),stress_pnl=("stress_pnl","sum")).reset_index()
def _mfe_mae_summary(t):
    if t.empty: return pd.DataFrame()
    d=t.copy(); d["mfe_mae_bucket"]=(d["mfe"]>=d["mae"]).map({True:"mfe_ge_mae",False:"mae_dominates"}); return _summary(d,"mfe_mae_bucket")
def _div(a,b): return safe_divide(a, b)
def _conc(best,total): return positive_concentration(best, total)
def serialize_phase10b_specs(specs): return serialize_specs(specs)
def recommendation_to_json(rec): return deterministic_json(rec)
