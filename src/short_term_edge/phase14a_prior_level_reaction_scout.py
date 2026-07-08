from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from .backtest import split_sessions
from .instruments import get_instrument
from .phase_common import (
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

PARTIAL_SESSIONS = {"2026-07-03"}
RESEARCH_ONLY_GUARDRAIL = "Research/simulation only. No live trading, broker adapters, order routing, webhooks, credential storage, automated execution, or LLM-driven trade decisions."
LEVEL_TYPES = ("prior_rth_close", "prior_rth_midpoint")
INTERACTION_FAMILIES = ("reclaim_after_breach", "rejection_from_level", "breakout_hold")
SIDES = ("long", "short")
CONFIRMATION_MODELS = ("close_confirm_fill_next_open", "two_bar_confirm_fill_next_open")
EXIT_VARIANTS = ("hard_stop_time_exit", "structure_target_time_exit")


@dataclass(frozen=True)
class Phase14AConfig:
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
    registry_avg_corr_limit: float = 0.35
    registry_max_corr_limit: float = 0.60
    narrow_watch_miss: float = 0.05


@dataclass(frozen=True)
class Phase14ASpec:
    level_type: str
    interaction_family: str
    side: str
    confirmation_model: str
    exit_variant: str
    timeframe: int = 5
    atr_cap_multiple: float = 1.25
    buffer_ticks: int = 1
    time_stop_minutes: int = 30
    max_trades_per_day: int = 1
    trade_start: str = "10:00"
    trade_end: str = "15:30"
    flatten_time: str = "15:45"

    @property
    def candidate_id(self) -> str:
        return f"MNQ_14a_{self.level_type}_{self.interaction_family}_{self.side}_{self.confirmation_model}_{self.exit_variant}"

    def to_dict(self) -> dict[str, Any]:
        return {"candidate_id": self.candidate_id, "instrument": "MNQ", **self.__dict__, "traded_level_source": self.level_type, "level_source": "prior_complete_rth_session"}


def build_phase14a_specs(config: Phase14AConfig = Phase14AConfig()) -> list[Phase14ASpec]:
    specs: list[Phase14ASpec] = []
    for level_type in LEVEL_TYPES:
        for family in INTERACTION_FAMILIES:
            for side in SIDES:
                for confirm in CONFIRMATION_MODELS:
                    for exit_variant in EXIT_VARIANTS:
                        specs.append(Phase14ASpec(level_type, family, side, confirm, exit_variant))
    return specs[: max(int(config.max_specs), 0)]


def compute_prior_rth_close_midpoint_levels(bars: pd.DataFrame) -> pd.DataFrame:
    rth = bars[bars["session_segment"].eq("RTH")].sort_values("timestamp").copy()
    if rth.empty:
        return pd.DataFrame(columns=["trading_session", "prior_rth_close", "prior_rth_midpoint", "prior_rth_session"])
    daily = rth.groupby("trading_session", sort=True).agg(
        source_rth_high=("high", "max"),
        source_rth_low=("low", "min"),
        source_rth_close=("close", "last"),
    ).reset_index()
    daily["prior_rth_close"] = daily["source_rth_close"].shift(1)
    daily["prior_rth_midpoint"] = ((daily["source_rth_high"] + daily["source_rth_low"]) / 2.0).shift(1)
    daily["prior_rth_session"] = daily["trading_session"].shift(1)
    return daily[["trading_session", "prior_rth_close", "prior_rth_midpoint", "prior_rth_session"]].dropna().reset_index(drop=True)


def build_phase14a_feature_bars(bars: pd.DataFrame, spec: Phase14ASpec) -> pd.DataFrame:
    rth = bars[bars["session_segment"].eq("RTH")].sort_values("timestamp").copy()
    frames = []
    for _, day in rth.groupby("trading_session", sort=True):
        res = (
            day.set_index("timestamp")
            .resample("5min", origin="start_day", offset="30min", label="left", closed="left")
            .agg({"symbol": "last", "open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum", "trading_session": "last", "session_segment": "last"})
            .dropna(subset=["open", "high", "low", "close"])
            .reset_index()
        )
        frames.append(res)
    if not frames:
        return pd.DataFrame()
    out = pd.concat(frames, ignore_index=True).merge(compute_prior_rth_close_midpoint_levels(bars), on="trading_session", how="left")
    out = out.dropna(subset=["prior_rth_close", "prior_rth_midpoint"]).sort_values(["trading_session", "timestamp"]).reset_index(drop=True)
    out["selected_prior_level"] = out[spec.level_type]
    tr = (out["high"] - out["low"]).abs()
    out["atr"] = tr.groupby(out["trading_session"]).transform(lambda s: s.rolling(14, min_periods=3).mean()).fillna(tr)
    return out


def generate_phase14a_signals(features: pd.DataFrame, spec: Phase14ASpec) -> list[dict[str, Any]]:
    if features.empty:
        return []
    start = _hhmm(spec.trade_start)
    end = _hhmm(spec.trade_end)
    tick = get_instrument("MNQ").tick_size
    tol = tick
    signals: list[dict[str, Any]] = []
    for _, day in features.groupby("trading_session", sort=True):
        day = day.sort_values("timestamp").reset_index(drop=True)
        candidates = []
        breach_seen = False
        for i in range(1, len(day) - 2):
            row = day.iloc[i]
            prev = day.iloc[i - 1]
            minute = _minute(row["timestamp"])
            if minute < start or minute >= end:
                continue
            level = float(row["selected_prior_level"])
            high, low, close, open_ = map(float, (row["high"], row["low"], row["close"], row["open"]))
            prev_close = float(prev["close"])
            if spec.interaction_family == "reclaim_after_breach":
                if spec.side == "long":
                    breach_seen = breach_seen or low < level - tick
                    ok = breach_seen and close > level
                else:
                    breach_seen = breach_seen or high > level + tick
                    ok = breach_seen and close < level
            elif spec.interaction_family == "rejection_from_level":
                if spec.side == "long":
                    ok = open_ > level and low <= level + tol and close > level
                else:
                    ok = open_ < level and high >= level - tol and close < level
            else:  # breakout_hold
                if spec.side == "long":
                    ok = close > level and prev_close <= level
                else:
                    ok = close < level and prev_close >= level
            if not ok:
                continue
            confirmation_time = row["timestamp"]
            entry_idx = i + 1
            if spec.confirmation_model == "two_bar_confirm_fill_next_open":
                confirm = day.iloc[i + 1]
                cclose = float(confirm["close"])
                confirm_ok = cclose > level if spec.side == "long" else cclose < level
                if not confirm_ok:
                    continue
                confirmation_time = confirm["timestamp"]
                entry_idx = i + 2
            if entry_idx >= len(day):
                continue
            entry = day.iloc[entry_idx]
            entry_minute = _minute(entry["timestamp"])
            if entry_minute < start or entry_minute >= end:
                continue
            candidates.append({
                "candidate_id": spec.candidate_id,
                "signal_time": row["timestamp"],
                "confirmation_time": confirmation_time,
                "entry_time": entry["timestamp"],
                "trading_session": str(row["trading_session"]),
                "level_type": spec.level_type,
                "interaction_family": spec.interaction_family,
                "side": spec.side,
                "confirmation_model": spec.confirmation_model,
                "exit_variant": spec.exit_variant,
                "selected_prior_level": level,
                "prior_rth_close": float(row["prior_rth_close"]),
                "prior_rth_midpoint": float(row["prior_rth_midpoint"]),
                "prior_rth_session": str(row["prior_rth_session"]),
                "signal_open": open_,
                "signal_close": close,
                "signal_high": high,
                "signal_low": low,
                "atr": float(row.get("atr", 0.0) or 0.0),
            })
        if candidates:
            first = dict(candidates[0])
            first["skipped_extra_signals_same_day"] = len(candidates) - 1
            signals.append(first)
    return signals


def simulate_phase14a_trades(features: pd.DataFrame, signals: list[dict[str, Any]], spec: Phase14ASpec) -> tuple[pd.DataFrame, int]:
    if features.empty or not signals:
        return pd.DataFrame(), 0
    inst = get_instrument("MNQ")
    day_map = {str(s): d.sort_values("timestamp").reset_index(drop=True) for s, d in features.groupby("trading_session", sort=True)}
    rows: list[dict[str, Any]] = []
    counts: dict[str, int] = {}
    invalid = 0
    for signal in sorted(signals, key=lambda x: x["entry_time"]):
        session = str(signal["trading_session"])
        if counts.get(session, 0) >= spec.max_trades_per_day:
            continue
        day = day_map.get(session)
        if day is None:
            continue
        matches = day.index[day["timestamp"].eq(pd.Timestamp(signal["entry_time"]))].tolist()
        if not matches:
            continue
        trade = _simulate_one(day, matches[0], signal, spec, inst)
        if trade is None:
            invalid += 1
            continue
        rows.append({**signal, **trade, **spec.to_dict()})
        counts[session] = counts.get(session, 0) + 1
    return pd.DataFrame(rows), invalid


def _simulate_one(day: pd.DataFrame, entry_pos: int, signal: dict[str, Any], spec: Phase14ASpec, inst) -> dict[str, Any] | None:
    entry = day.iloc[entry_pos]
    entry_price = float(entry["open"])
    tick = inst.tick_size
    atr = max(float(signal.get("atr", 0.0)), tick * 8)
    risk_cap = atr * spec.atr_cap_multiple
    if spec.side == "long":
        structural_stop = float(signal["signal_low"]) - tick
        atr_cap_stop = entry_price - risk_cap
        actual_stop = max(structural_stop, atr_cap_stop)
        if actual_stop >= entry_price:
            return None
        risk = entry_price - actual_stop
        recent = float(day.iloc[max(0, entry_pos - 6) : entry_pos + 1]["high"].max())
        target = max(recent, entry_price + 1.5 * risk)
    else:
        structural_stop = float(signal["signal_high"]) + tick
        atr_cap_stop = entry_price + risk_cap
        actual_stop = min(structural_stop, atr_cap_stop)
        if actual_stop <= entry_price:
            return None
        risk = actual_stop - entry_price
        recent = float(day.iloc[max(0, entry_pos - 6) : entry_pos + 1]["low"].min())
        target = min(recent, entry_price - 1.5 * risk)
    max_exit = pd.Timestamp(entry["timestamp"]) + pd.Timedelta(minutes=spec.time_stop_minutes)
    flatten_minute = _hhmm(spec.flatten_time)
    exit_price = float(entry["close"])
    exit_time = entry["timestamp"]
    exit_reason = "time_stop"
    mfe = mae = 0.0
    ambiguity = 0
    target_enabled = spec.exit_variant == "structure_target_time_exit"
    for pos in range(entry_pos, len(day)):
        row = day.iloc[pos]
        ts = pd.Timestamp(row["timestamp"])
        if spec.side == "long":
            fav = float(row["high"]) - entry_price
            adv = entry_price - float(row["low"])
            stop_hit = float(row["low"]) <= actual_stop
            target_hit = float(row["high"]) >= target if target_enabled else False
        else:
            fav = entry_price - float(row["low"])
            adv = float(row["high"]) - entry_price
            stop_hit = float(row["high"]) >= actual_stop
            target_hit = float(row["low"]) <= target if target_enabled else False
        mfe = max(mfe, fav * inst.point_value)
        mae = max(mae, adv * inst.point_value)
        if stop_hit:
            exit_price = actual_stop
            exit_time = ts
            exit_reason = "stop_same_bar_conservative" if target_hit else "stop"
            ambiguity = int(target_hit)
            break
        if target_hit:
            exit_price = target
            exit_time = ts
            exit_reason = "target"
            break
        if ts >= max_exit or _minute(ts) >= flatten_minute:
            exit_price = float(row["close"])
            exit_time = ts
            exit_reason = "session_flatten" if _minute(ts) >= flatten_minute else "time_stop"
            break
    gross = (exit_price - entry_price) * (1 if spec.side == "long" else -1) * inst.point_value
    return {
        "entry_price": round(entry_price, 4),
        "exit_time": exit_time,
        "exit_price": round(exit_price, 4),
        "exit_reason": exit_reason,
        "structural_stop": round(structural_stop, 4),
        "atr_cap_stop": round(atr_cap_stop, 4),
        "actual_stop": round(actual_stop, 4),
        "target_price": round(target, 4),
        "gross_pnl": round(gross, 2),
        "net_pnl": round(gross - inst.base_cost, 2),
        "stress_pnl": round(gross - inst.stress_cost, 2),
        "mfe": round(mfe, 2),
        "mae": round(mae, 2),
        "same_bar_ambiguity": ambiguity,
        "stop_hit": int(exit_reason in {"stop", "stop_same_bar_conservative"}),
        "target_hit": int(exit_reason == "target"),
        "time_stop": int(exit_reason in {"time_stop", "session_flatten"}),
    }


def run_phase14a_scout(bars: pd.DataFrame, registry_matrix: pd.DataFrame, playbook_daily: pd.DataFrame, gap_features: pd.DataFrame, config: Phase14AConfig = Phase14AConfig()) -> dict[str, pd.DataFrame]:
    specs = build_phase14a_specs(config)
    scoped = bars[~bars["trading_session"].astype(str).isin(PARTIAL_SESSIONS)].copy()
    sessions = sorted(scoped["trading_session"].dropna().astype(str).unique().tolist())
    split_map = split_sessions(sessions)
    rows: list[dict[str, Any]] = []
    trade_frames = []
    fold_frames = []
    feature_cache: dict[str, pd.DataFrame] = {}
    gap_sessions = set(gap_features[gap_features.get("prior_rth_high_low_interaction", False).astype(bool)]["trading_session"].astype(str)) if not gap_features.empty and "prior_rth_high_low_interaction" in gap_features else set()
    current_covered = set(playbook_daily[playbook_daily["net_pnl"].ne(0.0)]["trading_session"].astype(str)) if not playbook_daily.empty and "net_pnl" in playbook_daily else set()
    for spec in specs:
        if spec.level_type not in feature_cache:
            feature_cache[spec.level_type] = build_phase14a_feature_bars(scoped, spec)
        features = feature_cache[spec.level_type]
        signals = generate_phase14a_signals(features, spec)
        trades, invalid = simulate_phase14a_trades(features, signals, spec)
        if not trades.empty:
            trades["split"] = trades["trading_session"].astype(str).map(split_map)
            trade_frames.append(trades)
            fold_frames.append(_fold_rows(trades, spec, sessions, config))
        rows.append(_candidate_row(spec, trades, invalid, signals, sessions, split_map, registry_matrix, playbook_daily, gap_sessions, current_covered, config))
    trade_logs = pd.concat(trade_frames, ignore_index=True) if trade_frames else pd.DataFrame()
    folds = pd.concat(fold_frames, ignore_index=True) if fold_frames else pd.DataFrame()
    candidates = pd.DataFrame(rows).sort_values(["phase14a_score", "stress_pnl"], ascending=[False, False]).reset_index(drop=True)
    candidates.insert(0, "phase14a_rank", range(1, len(candidates) + 1))
    daily = daily_pnl_summary(trade_logs)
    return {
        "candidate_results": candidates,
        "trade_logs": trade_logs,
        "daily_pnl": daily,
        "walk_forward_folds": folds,
        "concentration_diagnostics": concentration_diagnostics(trade_logs),
        "level_summary": grouped_trade_summary(trade_logs, "level_type", include_gross=True),
        "interaction_family_summary": grouped_trade_summary(trade_logs, "interaction_family", include_gross=True),
        "side_summary": grouped_trade_summary(trade_logs, "side", include_gross=True),
        "confirmation_summary": grouped_trade_summary(trade_logs, "confirmation_model", include_gross=True),
        "exit_variant_summary": grouped_trade_summary(trade_logs, "exit_variant", include_gross=True),
        "correlation_to_registry": _correlation_rows(candidates, "registry"),
        "correlation_to_playbook": _correlation_rows(candidates, "playbook"),
        "gap_coverage_summary": _gap_coverage_summary(candidates),
        "specs": pd.DataFrame([s.to_dict() for s in specs]),
    }


def _candidate_row(spec: Phase14ASpec, trades: pd.DataFrame, invalid: int, signals: list[dict[str, Any]], sessions: list[str], split_map: dict[Any, str], registry_matrix: pd.DataFrame, playbook_daily: pd.DataFrame, gap_sessions: set[str], current_covered: set[str], config: Phase14AConfig) -> dict[str, Any]:
    row = spec.to_dict()
    daily = pd.DataFrame(columns=["trading_session", "net_pnl"])
    if trades.empty:
        row.update(_zero_metrics())
    else:
        t = trades.copy()
        t["split"] = t["trading_session"].astype(str).map(split_map)
        net = float(t["net_pnl"].sum())
        equity = t["net_pnl"].cumsum()
        daily = t.groupby("trading_session", as_index=False)["net_pnl"].sum()
        daily_series = daily.set_index("trading_session")["net_pnl"]
        folds = _fold_rows(t, spec, sessions, config)
        row.update({
            "trades": len(t),
            "active_days": int(t["trading_session"].nunique()),
            "trades_per_active_day": safe_divide(len(t), t["trading_session"].nunique()),
            "gross_pnl": round(float(t["gross_pnl"].sum()), 2),
            "net_pnl": round(net, 2),
            "stress_pnl": round(float(t["stress_pnl"].sum()), 2),
            "validation_pnl": round(float(t.loc[t["split"].eq("validation"), "net_pnl"].sum()), 2),
            "holdout_pnl": round(float(t.loc[t["split"].eq("holdout"), "net_pnl"].sum()), 2),
            "max_drawdown": round(float((equity - equity.cummax()).min()), 2),
            "best_day_concentration": positive_concentration(float(daily_series.max()), net),
            "best_trade_concentration": positive_concentration(float(t["net_pnl"].max()), net),
            "avg_mfe": round(float(t["mfe"].mean()), 2),
            "avg_mae": round(float(t["mae"].mean()), 2),
            **fold_summary(folds),
        })
    reg = daily_correlation_to_matrix(daily, registry_matrix)
    play = daily_correlation_to_matrix(daily, _playbook_matrix(playbook_daily))
    trade_sessions = set(trades["trading_session"].astype(str)) if not trades.empty else set()
    row.update({
        "average_correlation_to_registry": reg["average_abs_correlation"],
        "max_correlation_to_registry": reg["max_abs_correlation"],
        "average_correlation_to_playbook": play["average_abs_correlation"],
        "max_correlation_to_playbook": play["max_abs_correlation"],
        "gap_days_covered": len(trade_sessions & gap_sessions),
        "incremental_gap_days_covered": len((trade_sessions & gap_sessions) - current_covered),
        "invalid_risk_skipped_count": int(invalid),
        "signals_found": len(signals),
        "paper_trading_approved": False,
        "official_gates_passed": False,
    })
    row["phase14a_label"] = _label(row, config)
    row["signal_evidence_status"] = _signal_evidence(row)
    row["tradability_status"] = _tradability(row, config)
    row["research_track"] = _research_track(row)
    row["portfolio_role"] = _portfolio_role(row)
    row["reject_reasons"] = _reasons(row, config)
    row["phase14a_score"] = round(float(row.get("stress_pnl", 0)) + float(row.get("walk_forward_stress_pnl", 0)) + 25 * float(row.get("incremental_gap_days_covered", 0)) - abs(float(row.get("max_drawdown", 0))) - 1000 * max(float(row.get("average_correlation_to_registry", 1)) - config.registry_avg_corr_limit, 0), 4)
    return row


def daily_correlation_to_matrix(candidate_daily: pd.DataFrame, matrix: pd.DataFrame) -> dict[str, float]:
    if candidate_daily.empty or matrix.empty:
        return {"average_abs_correlation": 0.0, "max_abs_correlation": 0.0}
    base = matrix.copy()
    cand = candidate_daily.groupby("trading_session", as_index=False)["net_pnl"].sum().rename(columns={"net_pnl": "candidate_net_pnl"})
    merged = base.merge(cand, on="trading_session", how="outer").fillna(0.0)
    vals = [abs(_corr(merged["candidate_net_pnl"], merged[col])) for col in merged.columns if col not in {"trading_session", "candidate_net_pnl"}]
    return {"average_abs_correlation": round(sum(vals) / len(vals), 6) if vals else 0.0, "max_abs_correlation": round(max(vals), 6) if vals else 0.0}


def make_phase14a_recommendation(result: dict[str, pd.DataFrame]) -> dict[str, Any]:
    c = result["candidate_results"]
    if c.empty:
        return {"next_action": "phase14b_target_next_gap_power_hour_or_lunch_expansion", "official_gates_changed": False, "paper_trading_approved": False, "rationale": "No Phase 14A candidates were produced."}
    paper = c[c["phase14a_label"].eq("phase14a_candidate_for_paper_review")]
    if not paper.empty:
        return {"next_action": "phase14a_review_packet_only", "official_gates_changed": False, "paper_trading_approved": False, "rationale": "A candidate reached review-packet diagnostics only; paper trading remains false.", "top_candidate": paper.iloc[0].to_dict()}
    uncorr = c[c["phase14a_label"].eq("phase14a_positive_uncorrelated_research_signal")]
    if not uncorr.empty:
        return {"next_action": "add_to_registry_and_run_portfolio_audit_c", "official_gates_changed": False, "paper_trading_approved": False, "rationale": "A positive prior-level reaction signal was uncorrelated to existing registry/playbook diagnostics.", "top_candidate": uncorr.iloc[0].to_dict()}
    watch = c[c["phase14a_label"].eq("phase14a_watchlist_needs_more_history")]
    if not watch.empty or ((c["stress_pnl"] > 0) & (c["gap_days_covered"] > 0)).any():
        return {"next_action": "phase14b_targeted_prior_level_diagnostic", "official_gates_changed": False, "paper_trading_approved": False, "rationale": "A prior-level reaction candidate improved gap coverage but missed tradability gates.", "top_candidate": c.iloc[0].to_dict()}
    positive = c[(c["stress_pnl"] > 0) & (c["validation_pnl"] > 0) & (c["holdout_pnl"] > 0)]
    if not positive.empty:
        return {"next_action": "add_to_registry_as_parked_prior_level_signal", "official_gates_changed": False, "paper_trading_approved": False, "rationale": "Positive prior-level reaction axes remained correlated/concentrated.", "top_candidate": positive.iloc[0].to_dict()}
    return {"next_action": "phase14b_target_next_gap_power_hour_or_lunch_expansion", "official_gates_changed": False, "paper_trading_approved": False, "rationale": "No positive prior-level reaction axis survived stress/validation/holdout diagnostics."}


def render_phase14a_report(result: dict[str, pd.DataFrame], recommendation: dict[str, Any], report_path: Path) -> str:
    c = result["candidate_results"]
    counts = c["phase14a_label"].value_counts().to_dict() if not c.empty else {}
    lines = [
        "# Phase 14A — Prior RTH Close / Midpoint Reaction Scout",
        "",
        RESEARCH_ONLY_GUARDRAIL,
        "",
        "Bounded 48-spec MNQ-only module scout. No prior RTH high/low breakout, overnight, opening range, opening-drive, VWAP, volatility compression, gate changes, promotions, or paper trading approval.",
        "",
        "## Summary",
        "",
        f"- Specs evaluated: `{len(c)}`",
        f"- Trade rows: `{len(result['trade_logs'])}`",
        f"- Label counts: `{counts}`",
        f"- Next action: `{recommendation.get('next_action')}`",
        f"- Rationale: {recommendation.get('rationale')}",
        "- Paper trading approved: `false`",
        "",
        "## Top Candidates",
        "",
        "| Candidate | Label | Net | Stress | Val | Holdout | WF Stress | Avg reg corr | Avg playbook corr | Gap days | Incremental gap days | Reasons |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for _, r in c.head(12).iterrows():
        lines.append(f"| `{r['candidate_id']}` | {r['phase14a_label']} | {float(r['net_pnl']):.2f} | {float(r['stress_pnl']):.2f} | {float(r['validation_pnl']):.2f} | {float(r['holdout_pnl']):.2f} | {float(r['walk_forward_stress_pnl']):.2f} | {float(r['average_correlation_to_registry']):.3f} | {float(r['average_correlation_to_playbook']):.3f} | {int(r['gap_days_covered'])} | {int(r['incremental_gap_days_covered'])} | {r['reject_reasons']} |")
    lines += ["", "## Outputs", "", f"- `{report_path.as_posix()}`", "- `outputs/phase14a_candidate_results.csv`", "- `outputs/phase14a_trade_logs.csv`", "- `outputs/phase14a_gap_coverage_summary.csv`", "- `outputs/phase14a_next_action_recommendation.json`"]
    return "\n".join(lines) + "\n"


def _label(r: dict[str, Any], c: Phase14AConfig) -> str:
    adequate = r.get("trades", 0) >= c.min_trades and r.get("active_days", 0) >= c.min_active_days and 1 <= r.get("trades_per_active_day", 0) <= 3
    econ = r.get("net_pnl", 0) > 0 and r.get("stress_pnl", 0) > 0 and r.get("validation_pnl", 0) > 0 and r.get("holdout_pnl", 0) > 0 and r.get("walk_forward_stress_pnl", 0) > 0
    fold_ok = r.get("positive_wf_test_folds_pct", 0) >= 0.9 and r.get("worst_wf_test_fold", 0) >= c.worst_fold_limit
    conc_ok = r.get("best_day_concentration", 1) <= c.concentration_limit and r.get("best_trade_concentration", 1) <= c.trade_concentration_limit
    corr_ok = r.get("average_correlation_to_registry", 1) <= c.registry_avg_corr_limit and r.get("max_correlation_to_registry", 1) <= c.registry_max_corr_limit
    if adequate and econ and fold_ok and conc_ok:
        return "phase14a_candidate_for_paper_review"
    if econ and corr_ok:
        return "phase14a_positive_uncorrelated_research_signal"
    if econ:
        return "phase14a_positive_specialized_research_signal"
    if r.get("stress_pnl", 0) > 0 and r.get("gap_days_covered", 0) > 0:
        return "phase14a_watchlist_needs_more_history"
    if r.get("net_pnl", 0) <= 0 or r.get("stress_pnl", 0) <= 0:
        return "phase14a_rejected_negative_stress"
    if r.get("validation_pnl", 0) <= 0:
        return "phase14a_rejected_negative_validation"
    if r.get("holdout_pnl", 0) <= 0:
        return "phase14a_rejected_negative_holdout"
    if not corr_ok:
        return "phase14a_rejected_high_correlation"
    if not adequate:
        return "phase14a_rejected_low_activity"
    if not fold_ok:
        return "phase14a_rejected_fold_instability"
    if not conc_ok:
        return "phase14a_rejected_concentration"
    return "phase14a_rejected_fold_instability"


def _signal_evidence(r: dict[str, Any]) -> str:
    label = str(r.get("phase14a_label"))
    if label in {"phase14a_candidate_for_paper_review", "phase14a_positive_uncorrelated_research_signal", "phase14a_positive_specialized_research_signal"}:
        return "positive_research_signal"
    if label == "phase14a_watchlist_needs_more_history" or r.get("stress_pnl", 0) > 0:
        return "weak_research_signal"
    return "no_signal"


def _tradability(r: dict[str, Any], c: Phase14AConfig) -> str:
    label = str(r.get("phase14a_label"))
    if label == "phase14a_candidate_for_paper_review":
        return "review_packet_candidate"
    if label == "phase14a_watchlist_needs_more_history":
        return "watchlist_needs_more_history"
    if r.get("net_pnl", 0) <= 0 or r.get("stress_pnl", 0) <= 0:
        return "not_tradable_negative"
    if r.get("trades", 0) < c.min_trades or r.get("active_days", 0) < c.min_active_days:
        return "not_tradable_low_activity"
    if r.get("best_day_concentration", 1) > c.concentration_limit or r.get("best_trade_concentration", 1) > c.trade_concentration_limit:
        return "not_tradable_concentrated"
    return "not_tradable_fold_unstable"


def _research_track(r: dict[str, Any]) -> str:
    return "priority_research_signal_for_more_data" if r.get("phase14a_label") in {"phase14a_candidate_for_paper_review", "phase14a_watchlist_needs_more_history"} else "parked_research_signal"


def _portfolio_role(r: dict[str, Any]) -> str:
    if r.get("phase14a_label") == "phase14a_positive_uncorrelated_research_signal":
        return "diversifier_module"
    if r.get("trades", 0) < 60:
        return "rare_setup_module"
    return "parked_module"


def _reasons(r: dict[str, Any], c: Phase14AConfig) -> str:
    checks = [
        ("negative stress", r.get("net_pnl", 0) <= 0 or r.get("stress_pnl", 0) <= 0),
        ("negative validation", r.get("validation_pnl", 0) <= 0),
        ("negative holdout", r.get("holdout_pnl", 0) <= 0),
        ("high correlation", r.get("average_correlation_to_registry", 1) > c.registry_avg_corr_limit or r.get("max_correlation_to_registry", 1) > c.registry_max_corr_limit),
        ("low activity", r.get("trades", 0) < c.min_trades or r.get("active_days", 0) < c.min_active_days or not (1 <= r.get("trades_per_active_day", 0) <= 3)),
        ("fold instability", r.get("walk_forward_stress_pnl", 0) <= 0 or r.get("positive_wf_test_folds_pct", 0) < 0.9 or r.get("worst_wf_test_fold", 0) < c.worst_fold_limit),
        ("concentration", r.get("best_day_concentration", 1) > c.concentration_limit or r.get("best_trade_concentration", 1) > c.trade_concentration_limit),
    ]
    return "; ".join(name for name, bad in checks if bad) or "survived Phase 14A diagnostic gates; review packet only"


def _fold_rows(trades: pd.DataFrame, spec: Phase14ASpec, sessions: list[str], c: Phase14AConfig) -> pd.DataFrame:
    rows = []
    window = c.train_sessions + c.validation_sessions + c.test_sessions
    start = 0
    fold = 1
    while start + window <= len(sessions):
        test = sessions[start + c.train_sessions + c.validation_sessions : start + window]
        seg = trades[trades["trading_session"].astype(str).isin(test)]
        rows.append({"candidate_id": spec.candidate_id, "fold": fold, "net_pnl": round(float(seg["net_pnl"].sum()), 2), "stress_pnl": round(float(seg["stress_pnl"].sum()), 2), "trades": len(seg)})
        start += c.step_sessions
        fold += 1
    return pd.DataFrame(rows)


def _gap_coverage_summary(candidates: pd.DataFrame) -> pd.DataFrame:
    if candidates.empty:
        return pd.DataFrame()
    return candidates.groupby(["level_type", "interaction_family", "side"], as_index=False).agg(candidates=("candidate_id", "count"), total_gap_days_covered=("gap_days_covered", "sum"), max_incremental_gap_days_covered=("incremental_gap_days_covered", "max"), best_stress_pnl=("stress_pnl", "max"))


def _correlation_rows(candidates: pd.DataFrame, target: str) -> pd.DataFrame:
    avg = "average_correlation_to_registry" if target == "registry" else "average_correlation_to_playbook"
    mx = "max_correlation_to_registry" if target == "registry" else "max_correlation_to_playbook"
    return candidates[["candidate_id", "level_type", "interaction_family", "side", avg, mx]].copy() if not candidates.empty else pd.DataFrame(columns=["candidate_id", avg, mx])


def _playbook_matrix(portfolio_daily: pd.DataFrame) -> pd.DataFrame:
    if portfolio_daily.empty:
        return pd.DataFrame()
    if {"portfolio_set", "portfolio_mode", "net_pnl"} <= set(portfolio_daily.columns):
        pivot = portfolio_daily.pivot_table(index="trading_session", columns=["portfolio_set", "portfolio_mode"], values="net_pnl", aggfunc="sum", fill_value=0.0).reset_index()
        pivot.columns = ["trading_session" if c == ("trading_session", "") or c == "trading_session" else "::".join(map(str, c)) for c in pivot.columns]
        return pivot
    return portfolio_daily


def _zero_metrics() -> dict[str, Any]:
    metrics = standard_zero_metrics(include_gross_waterfall=False)
    metrics.update({"gross_pnl": 0.0, "walk_forward_test_pnl": 0.0, "avg_mfe": 0.0, "avg_mae": 0.0})
    return metrics


def _corr(a: pd.Series, b: pd.Series) -> float:
    if len(a) < 2 or float(a.std()) == 0.0 or float(b.std()) == 0.0:
        return 0.0
    value = a.corr(b)
    return 0.0 if pd.isna(value) else float(value)


def serialize_phase14a_specs(specs: list[Phase14ASpec]) -> str:
    return serialize_specs(specs)


def recommendation_to_json(rec: dict[str, Any]) -> str:
    return deterministic_json(rec)


def _hhmm(value: str) -> int:
    h, m = value.split(":")
    return int(h) * 60 + int(m)


def _minute(ts: Any) -> int:
    ts = pd.Timestamp(ts)
    return ts.hour * 60 + ts.minute
