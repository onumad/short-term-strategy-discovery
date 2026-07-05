from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .backtest import Candidate, prepare_indicators, simulate_candidate, split_sessions
from .data_loader import discover_data_files, load_ohlcv_csv
from .instruments import get_instrument


RESEARCH_START = "2026-04-06"
RESEARCH_END = "2026-07-02"
TOP_COUNT = 8


def run_phase2(project_root: Path) -> dict[str, Any]:
    raw_dir = project_root / "data" / "raw"
    output_dir = project_root / "outputs"
    report_dir = project_root / "reports"
    log_dir = project_root / "trade_logs"
    chart_dir = project_root / "charts"
    for path in [output_dir, report_dir, log_dir, chart_dir]:
        path.mkdir(parents=True, exist_ok=True)

    frames = [load_ohlcv_csv(path) for path in discover_data_files(raw_dir)]
    if not frames:
        raise RuntimeError(f"No CSV files found in {raw_dir}")
    full_data = pd.concat(frames, ignore_index=True).sort_values(["symbol", "timestamp"])

    complete_sessions = _shared_complete_sessions(full_data)
    candidates = build_candidates()

    metrics_rows: list[dict[str, Any]] = []
    trade_logs: dict[str, pd.DataFrame] = {}
    for symbol, symbol_full in full_data.groupby("symbol", sort=True):
        spec = get_instrument(symbol)
        rth = prepare_indicators(symbol_full)
        rth = rth[rth["trading_session"].isin(complete_sessions)].copy()
        symbol_full = symbol_full[symbol_full["trading_session"].isin(complete_sessions)].copy()
        symbol_candidates = [candidate for candidate in candidates if candidate.instrument == symbol]
        for candidate in symbol_candidates:
            trades = simulate_candidate(rth, symbol_full, candidate, spec, complete_sessions)
            metrics = score_candidate(candidate, trades, complete_sessions)
            metrics_rows.append(metrics)
            if not trades.empty:
                trade_logs[candidate.candidate_id] = trades

    ranked = pd.DataFrame(metrics_rows).sort_values(
        ["ranking_score", "net_pnl", "trades_per_session"],
        ascending=[False, False, False],
    )
    ranked.to_csv(output_dir / "ranked_edges.csv", index=False)

    top = select_top_edges(ranked)
    top.to_csv(output_dir / "top_edges.csv", index=False)
    write_top_trade_logs(top, trade_logs, log_dir)
    write_charts(top, trade_logs, chart_dir)
    return {
        "ranked": ranked,
        "top": top,
        "trade_logs": trade_logs,
        "complete_sessions": complete_sessions,
        "paths": {
            "ranked": output_dir / "ranked_edges.csv",
            "top": output_dir / "top_edges.csv",
            "report": report_dir / "phase2_discovery_report.md",
            "trade_logs": log_dir,
            "charts": chart_dir,
        },
    }


def build_candidates() -> list[Candidate]:
    candidates: list[Candidate] = []
    for symbol in ["MGC", "MNQ"]:
        spec = get_instrument(symbol)
        tick = spec.tick_size
        stop_sets = {
            "MGC": [(12, 18), (18, 27), (24, 36)],
            "MNQ": [(40, 60), (60, 90), (80, 120)],
        }[symbol]
        min_range = {"MGC": 1.0, "MNQ": 10.0}[symbol]

        for minutes in [5, 15, 30]:
            for rr in [1.0, 1.5]:
                for filt in ["none", "vwap"]:
                    candidates.append(_candidate(symbol, "opening_range_breakout", f"or{minutes}_rr{rr}_{filt}", {
                        "or_minutes": minutes,
                        "rr": rr,
                        "filter": filt,
                        "side": "both",
                        "max_trades": 2,
                        "min_range": min_range,
                    }))
            for target in ["mid", "opposite"]:
                candidates.append(_candidate(symbol, "opening_range_failure", f"or{minutes}_fail_{target}", {
                    "or_minutes": minutes,
                    "target": target,
                    "max_trades": 2,
                    "min_range": min_range,
                }))

        for stop_ticks, target_ticks in stop_sets:
            for mode in ["reclaim", "failure", "both"]:
                candidates.append(_candidate(symbol, "vwap_reclaim_rejection", f"{mode}_{stop_ticks}x{target_ticks}", {
                    "mode": mode,
                    "stop_ticks": stop_ticks,
                    "target_ticks": target_ticks,
                    "tick_size": tick,
                    "max_trades": 3,
                }))
            for pullback_ticks in [8, 16]:
                candidates.append(_candidate(symbol, "vwap_pullback_trend", f"pb{pullback_ticks}_{stop_ticks}x{target_ticks}", {
                    "pullback_ticks": pullback_ticks,
                    "stop_ticks": stop_ticks,
                    "target_ticks": target_ticks,
                    "tick_size": tick,
                    "max_trades": 2,
                }))
            for mode in ["break_hold", "sweep_reverse", "prior_close_reclaim"]:
                candidates.append(_candidate(symbol, "prior_session_levels", f"{mode}_{stop_ticks}x{target_ticks}", {
                    "mode": mode,
                    "stop_ticks": stop_ticks,
                    "target_ticks": target_ticks,
                    "tick_size": tick,
                    "max_trades": 2,
                }))
            for mode in ["break_hold", "sweep_reverse"]:
                candidates.append(_candidate(symbol, "overnight_levels", f"{mode}_{stop_ticks}x{target_ticks}", {
                    "mode": mode,
                    "stop_ticks": stop_ticks,
                    "target_ticks": target_ticks,
                    "tick_size": tick,
                    "max_trades": 2,
                }))
            candidates.append(_candidate(symbol, "first_hour_continuation", f"fh_{stop_ticks}x{target_ticks}", {
                "stop_ticks": stop_ticks,
                "target_ticks": target_ticks,
                "tick_size": tick,
                "max_trades": 1,
            }))
            for mode in ["continuation", "reversal"]:
                candidates.append(_candidate(symbol, "power_hour", f"{mode}_{stop_ticks}x{target_ticks}", {
                    "mode": mode,
                    "stop_ticks": stop_ticks,
                    "target_ticks": target_ticks,
                    "tick_size": tick,
                    "max_trades": 1,
                }))
    return candidates


def score_candidate(candidate: Candidate, trades: pd.DataFrame, sessions: list[Any]) -> dict[str, Any]:
    base = {
        "candidate_id": candidate.candidate_id,
        "instrument": candidate.instrument,
        "strategy_family": candidate.family,
        "variant": candidate.variant,
        "params": ";".join(f"{k}={v}" for k, v in sorted(candidate.params.items())),
        "session_count": len(sessions),
    }
    if trades.empty:
        return {
            **base,
            **_empty_metrics(),
            "label": "rejected",
            "ranking_score": -999.0,
            "risk_notes": "No trades generated.",
        }

    trades = trades.sort_values("entry_time").copy()
    split_pnl = trades.groupby("split")["net_pnl"].sum().to_dict()
    day_pnl = trades.groupby("trading_session")["net_pnl"].sum()
    entry_times = _naive_entry_times(trades)
    week_pnl = trades.groupby(entry_times.dt.to_period("W"))["net_pnl"].sum()
    month_pnl = trades.groupby(entry_times.dt.to_period("M"))["net_pnl"].sum()
    equity = trades["net_pnl"].cumsum()
    stress_equity = trades["stress_net_pnl"].cumsum()
    drawdown = equity - equity.cummax()
    gross_positive = trades.loc[trades["gross_pnl"] > 0, "gross_pnl"].sum()
    gross_negative = trades.loc[trades["gross_pnl"] < 0, "gross_pnl"].sum()
    net_positive = trades.loc[trades["net_pnl"] > 0, "net_pnl"].sum()
    net_negative = trades.loc[trades["net_pnl"] < 0, "net_pnl"].sum()

    net_pnl = float(trades["net_pnl"].sum())
    stress_net_pnl = float(trades["stress_net_pnl"].sum())
    trade_count = int(len(trades))
    active_sessions = int(trades["trading_session"].nunique())
    active_pct = active_sessions / len(sessions)
    trades_per_session = trade_count / len(sessions)
    max_day = float(day_pnl.max()) if len(day_pnl) else 0.0
    best_trade = float(trades["net_pnl"].max())
    concentration_day = max_day / net_pnl if net_pnl > 0 else 1.0
    concentration_trade = best_trade / net_pnl if net_pnl > 0 else 1.0
    holdout_pnl = float(split_pnl.get("holdout", 0.0))
    validation_pnl = float(split_pnl.get("validation", 0.0))
    discovery_pnl = float(split_pnl.get("discovery", 0.0))
    profit_factor = _profit_factor(net_positive, net_negative)
    weekly_positive_pct = float((week_pnl > 0).mean()) if len(week_pnl) else 0.0
    max_drawdown = float(drawdown.min()) if len(drawdown) else 0.0

    score = _ranking_score(
        net_pnl=net_pnl,
        holdout_pnl=holdout_pnl,
        validation_pnl=validation_pnl,
        trades_per_session=trades_per_session,
        active_pct=active_pct,
        avg_trade=float(trades["net_pnl"].mean()),
        max_drawdown=max_drawdown,
        concentration_day=concentration_day,
        concentration_trade=concentration_trade,
        stress_net_pnl=stress_net_pnl,
    )
    notes = _risk_notes(
        net_pnl,
        holdout_pnl,
        stress_net_pnl,
        trades_per_session,
        active_pct,
        concentration_day,
        concentration_trade,
    )
    label = _label_candidate(score, net_pnl, holdout_pnl, stress_net_pnl, trade_count, active_pct, notes)

    return {
        **base,
        "trades": trade_count,
        "trades_per_session": trades_per_session,
        "active_sessions": active_sessions,
        "active_session_pct": active_pct,
        "gross_pnl": float(trades["gross_pnl"].sum()),
        "net_pnl": net_pnl,
        "stress_net_pnl": stress_net_pnl,
        "slippage_sensitivity": net_pnl - stress_net_pnl,
        "avg_trade": float(trades["net_pnl"].mean()),
        "median_trade": float(trades["net_pnl"].median()),
        "win_rate": float((trades["net_pnl"] > 0).mean()),
        "profit_factor": profit_factor,
        "gross_profit_factor": _profit_factor(gross_positive, gross_negative),
        "max_drawdown": max_drawdown,
        "worst_trade": float(trades["net_pnl"].min()),
        "best_trade": best_trade,
        "worst_day": float(day_pnl.min()),
        "best_day": max_day,
        "positive_week_pct": weekly_positive_pct,
        "weekly_pnl": _format_period_pnl(week_pnl),
        "monthly_pnl": _format_period_pnl(month_pnl),
        "discovery_pnl": discovery_pnl,
        "validation_pnl": validation_pnl,
        "holdout_pnl": holdout_pnl,
        "discovery_trades": int((trades["split"] == "discovery").sum()),
        "validation_trades": int((trades["split"] == "validation").sum()),
        "holdout_trades": int((trades["split"] == "holdout").sum()),
        "one_day_concentration": concentration_day,
        "one_trade_concentration": concentration_trade,
        "label": label,
        "ranking_score": score,
        "risk_notes": "; ".join(notes) if notes else "No major Phase 2 risk flags.",
    }


def select_top_edges(ranked: pd.DataFrame) -> pd.DataFrame:
    interesting = ranked[ranked["trades"] > 0].copy()
    if interesting.empty:
        return ranked.head(TOP_COUNT)
    picks = []
    for _, row in interesting.sort_values("net_pnl", ascending=False).head(2).iterrows():
        picks.append(row)
    for _, row in interesting.sort_values("trades_per_session", ascending=False).head(2).iterrows():
        picks.append(row)
    risk_sorted = interesting.assign(
        risk_adjusted=interesting["net_pnl"] / interesting["max_drawdown"].abs().replace(0, np.nan)
    ).sort_values(["risk_adjusted", "net_pnl"], ascending=False)
    for _, row in risk_sorted.head(2).iterrows():
        picks.append(row)
    for _, row in interesting.sort_values("ranking_score", ascending=False).head(TOP_COUNT).iterrows():
        picks.append(row)
    top = pd.DataFrame(picks).drop_duplicates("candidate_id").head(TOP_COUNT)
    return top.reset_index(drop=True)


def write_top_trade_logs(top: pd.DataFrame, trade_logs: dict[str, pd.DataFrame], log_dir: Path) -> None:
    for _, row in top.iterrows():
        candidate_id = row["candidate_id"]
        trades = trade_logs.get(candidate_id)
        if trades is None:
            continue
        trades.to_csv(log_dir / f"{candidate_id}.csv", index=False)


def write_charts(top: pd.DataFrame, trade_logs: dict[str, pd.DataFrame], chart_dir: Path) -> None:
    import matplotlib.pyplot as plt

    for _, row in top.iterrows():
        candidate_id = row["candidate_id"]
        trades = trade_logs.get(candidate_id)
        if trades is None or trades.empty:
            continue
        trades = trades.sort_values("entry_time").copy()
        equity = trades["net_pnl"].cumsum()
        plt.figure(figsize=(10, 4))
        plt.plot(pd.to_datetime(trades["entry_time"]), equity)
        plt.title(f"Equity Curve: {candidate_id}")
        plt.xlabel("Entry time")
        plt.ylabel("Net PnL ($)")
        plt.tight_layout()
        plt.savefig(chart_dir / f"{candidate_id}_equity.png")
        plt.close()

        entry_times = _naive_entry_times(trades)
        weekly = trades.groupby(entry_times.dt.to_period("W"))["net_pnl"].sum()
        plt.figure(figsize=(10, 4))
        weekly.plot(kind="bar")
        plt.title(f"Weekly PnL: {candidate_id}")
        plt.xlabel("Week")
        plt.ylabel("Net PnL ($)")
        plt.tight_layout()
        plt.savefig(chart_dir / f"{candidate_id}_weekly.png")
        plt.close()

        tod = trades.groupby("entry_hour")["net_pnl"].mean()
        plt.figure(figsize=(10, 4))
        tod.plot(kind="bar")
        plt.title(f"Average PnL By Entry Time: {candidate_id}")
        plt.xlabel("Entry time")
        plt.ylabel("Average net PnL ($)")
        plt.tight_layout()
        plt.savefig(chart_dir / f"{candidate_id}_time_of_day.png")
        plt.close()


def _shared_complete_sessions(full_data: pd.DataFrame) -> list[Any]:
    mask = (pd.to_datetime(full_data["trading_session"]) >= pd.Timestamp(RESEARCH_START)) & (
        pd.to_datetime(full_data["trading_session"]) <= pd.Timestamp(RESEARCH_END)
    )
    scoped = full_data[mask].copy()
    session_sets = []
    for _, symbol_df in scoped.groupby("symbol"):
        counts = symbol_df.groupby("trading_session").size()
        session_sets.append(set(counts[counts >= 1_000].index.tolist()))
    if not session_sets:
        return []
    return sorted(set.intersection(*session_sets))


def _candidate(symbol: str, family: str, variant: str, params: dict[str, Any]) -> Candidate:
    return Candidate(
        candidate_id=f"{symbol}_{family}_{variant}",
        instrument=symbol,
        family=family,
        variant=variant,
        params=params,
    )


def _empty_metrics() -> dict[str, Any]:
    return {
        "trades": 0,
        "trades_per_session": 0.0,
        "active_sessions": 0,
        "active_session_pct": 0.0,
        "gross_pnl": 0.0,
        "net_pnl": 0.0,
        "stress_net_pnl": 0.0,
        "slippage_sensitivity": 0.0,
        "avg_trade": 0.0,
        "median_trade": 0.0,
        "win_rate": 0.0,
        "profit_factor": 0.0,
        "gross_profit_factor": 0.0,
        "max_drawdown": 0.0,
        "worst_trade": 0.0,
        "best_trade": 0.0,
        "worst_day": 0.0,
        "best_day": 0.0,
        "positive_week_pct": 0.0,
        "weekly_pnl": "",
        "monthly_pnl": "",
        "discovery_pnl": 0.0,
        "validation_pnl": 0.0,
        "holdout_pnl": 0.0,
        "discovery_trades": 0,
        "validation_trades": 0,
        "holdout_trades": 0,
        "one_day_concentration": 0.0,
        "one_trade_concentration": 0.0,
    }


def _profit_factor(gross_win: float, gross_loss: float) -> float:
    if gross_loss == 0:
        return float("inf") if gross_win > 0 else 0.0
    return float(gross_win / abs(gross_loss))


def _ranking_score(
    net_pnl: float,
    holdout_pnl: float,
    validation_pnl: float,
    trades_per_session: float,
    active_pct: float,
    avg_trade: float,
    max_drawdown: float,
    concentration_day: float,
    concentration_trade: float,
    stress_net_pnl: float,
) -> float:
    score = 0.0
    score += np.tanh(net_pnl / 500.0) * 30
    score += np.tanh(holdout_pnl / 150.0) * 20
    score += np.tanh(validation_pnl / 150.0) * 10
    score += min(trades_per_session, 3.0) / 3.0 * 15
    score += min(active_pct, 1.0) * 15
    score += np.tanh(avg_trade / 15.0) * 10
    score -= min(abs(max_drawdown) / 500.0, 2.0) * 8
    score -= max(0.0, concentration_day - 0.45) * 20
    score -= max(0.0, concentration_trade - 0.35) * 20
    if stress_net_pnl < 0:
        score -= 12
    return round(float(score), 4)


def _risk_notes(
    net_pnl: float,
    holdout_pnl: float,
    stress_net_pnl: float,
    trades_per_session: float,
    active_pct: float,
    concentration_day: float,
    concentration_trade: float,
) -> list[str]:
    notes = []
    if net_pnl <= 0:
        notes.append("negative net PnL")
    if holdout_pnl < 0:
        notes.append("negative final holdout")
    if stress_net_pnl < 0:
        notes.append("fails worse-slippage stress")
    if trades_per_session < 1.0:
        notes.append("below 1 trade/session target")
    if active_pct < 0.70:
        notes.append("active on less than 70% of sessions")
    if concentration_day > 0.50:
        notes.append("one-day concentration risk")
    if concentration_trade > 0.35:
        notes.append("one-trade concentration risk")
    return notes


def _label_candidate(
    score: float,
    net_pnl: float,
    holdout_pnl: float,
    stress_net_pnl: float,
    trade_count: int,
    active_pct: float,
    notes: list[str],
) -> str:
    if trade_count < 10 or net_pnl <= 0:
        return "rejected"
    if score >= 45 and holdout_pnl >= 0 and stress_net_pnl >= 0 and active_pct >= 0.60:
        return "paper_trade_candidate"
    if score >= 25 and holdout_pnl >= -100:
        return "watchlist"
    if "fails worse-slippage stress" not in notes and net_pnl > 0:
        return "interesting_but_needs_validation"
    return "rejected"


def _naive_entry_times(trades: pd.DataFrame) -> pd.Series:
    return pd.to_datetime(trades["entry_time"], utc=True).dt.tz_convert("America/New_York").dt.tz_localize(None)


def _format_period_pnl(series: pd.Series) -> str:
    return ";".join(f"{period}={value:.2f}" for period, value in series.items())
