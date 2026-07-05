from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from .backtest import split_sessions
from .instruments import InstrumentSpec
from .phase3 import longest_losing_streak, slippage_net_pnl
from .strategy_spec import StrategySpec


@dataclass(frozen=True)
class CandidateScore:
    candidate_id: str
    spec_json: str
    instrument: str
    family: str
    timeframe: int
    label: str
    ranking_score: float
    risk_notes: str
    net_pnl: float
    validation_pnl: float
    holdout_pnl: float
    slippage_4_ticks_net_pnl: float
    trades: int
    active_sessions: int
    active_session_pct: float
    win_rate: float
    avg_trade: float
    profit_factor: float
    max_drawdown: float
    worst_day: float
    longest_losing_streak: int
    best_day_concentration: float
    best_trade_concentration: float
    same_bar_stop_target_ambiguity_count: int
    base_cost: float
    stress_cost: float

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


def score_candidate_trades(
    spec: StrategySpec,
    trades: pd.DataFrame,
    instrument: InstrumentSpec,
    complete_sessions: list[Any],
) -> CandidateScore:
    spec.validate()
    base = _base_score(spec, instrument)
    if trades.empty:
        return CandidateScore(
            **base,
            label="rejected",
            ranking_score=-999.0,
            risk_notes="No trades generated.",
            net_pnl=0.0,
            validation_pnl=0.0,
            holdout_pnl=0.0,
            slippage_4_ticks_net_pnl=0.0,
            trades=0,
            active_sessions=0,
            active_session_pct=0.0,
            win_rate=0.0,
            avg_trade=0.0,
            profit_factor=0.0,
            max_drawdown=0.0,
            worst_day=0.0,
            longest_losing_streak=0,
            best_day_concentration=0.0,
            best_trade_concentration=0.0,
            same_bar_stop_target_ambiguity_count=0,
        )

    ordered = trades.sort_values(["entry_time", "exit_time"]).copy()
    if "split" not in ordered.columns:
        ordered["split"] = ordered["trading_session"].map(split_sessions(complete_sessions))
    net_pnl = float(ordered["net_pnl"].sum())
    validation_pnl = float(ordered.loc[ordered["split"] == "validation", "net_pnl"].sum())
    holdout_pnl = float(ordered.loc[ordered["split"] == "holdout", "net_pnl"].sum())
    day_pnl = ordered.groupby("trading_session")["net_pnl"].sum()
    equity = ordered["net_pnl"].cumsum()
    drawdown = equity - equity.cummax()
    wins = float(ordered.loc[ordered["net_pnl"] > 0, "net_pnl"].sum())
    losses = float(ordered.loc[ordered["net_pnl"] < 0, "net_pnl"].sum())
    active_sessions = int(ordered["trading_session"].nunique())
    active_pct = active_sessions / len(complete_sessions) if complete_sessions else 0.0
    best_day_conc = _concentration(float(day_pnl.max()) if len(day_pnl) else 0.0, net_pnl)
    best_trade_conc = _concentration(float(ordered["net_pnl"].max()), net_pnl)
    strict_slippage = slippage_net_pnl(ordered, instrument, 4)
    max_drawdown = float(drawdown.min()) if len(drawdown) else 0.0
    ambiguity_count = int(ordered.get("same_bar_stop_target_ambiguity", pd.Series(dtype=int)).fillna(0).sum())
    score = _ranking_score(net_pnl, validation_pnl, holdout_pnl, strict_slippage, active_pct, len(ordered), max_drawdown, best_day_conc, best_trade_conc)
    notes = _risk_notes(net_pnl, validation_pnl, holdout_pnl, strict_slippage, active_pct, best_day_conc, best_trade_conc, len(ordered), ambiguity_count)
    label = _label(net_pnl, validation_pnl, holdout_pnl, strict_slippage, active_pct, best_day_conc, best_trade_conc, len(ordered), score)
    return CandidateScore(
        **base,
        label=label,
        ranking_score=score,
        risk_notes="; ".join(notes) if notes else "No major Phase 5A risk flags.",
        net_pnl=net_pnl,
        validation_pnl=validation_pnl,
        holdout_pnl=holdout_pnl,
        slippage_4_ticks_net_pnl=float(strict_slippage),
        trades=int(len(ordered)),
        active_sessions=active_sessions,
        active_session_pct=float(active_pct),
        win_rate=float((ordered["net_pnl"] > 0).mean()),
        avg_trade=float(ordered["net_pnl"].mean()),
        profit_factor=_profit_factor(wins, losses),
        max_drawdown=max_drawdown,
        worst_day=float(day_pnl.min()) if len(day_pnl) else 0.0,
        longest_losing_streak=longest_losing_streak(ordered["net_pnl"]),
        best_day_concentration=best_day_conc,
        best_trade_concentration=best_trade_conc,
        same_bar_stop_target_ambiguity_count=ambiguity_count,
    )


def _base_score(spec: StrategySpec, instrument: InstrumentSpec) -> dict[str, Any]:
    return {
        "candidate_id": spec.canonical_id(),
        "spec_json": spec.to_json(),
        "instrument": spec.instrument,
        "family": spec.family,
        "timeframe": int(spec.timeframe),
        "base_cost": float(instrument.base_cost),
        "stress_cost": float(instrument.stress_cost),
    }


def _ranking_score(net_pnl: float, validation_pnl: float, holdout_pnl: float, strict_slippage: float, active_pct: float, trades: int, max_drawdown: float, day_conc: float, trade_conc: float) -> float:
    score = 0.0
    score += np.tanh(net_pnl / 2_500.0) * 25
    score += np.tanh(validation_pnl / 750.0) * 10
    score += np.tanh(holdout_pnl / 750.0) * 20
    score += np.tanh(strict_slippage / 2_500.0) * 15
    score += min(active_pct, 1.0) * 15
    score += min(trades / 120.0, 1.0) * 10
    score -= min(abs(max_drawdown) / 2_500.0, 2.0) * 8
    score -= max(day_conc - 0.40, 0.0) * 30
    score -= max(trade_conc - 0.25, 0.0) * 30
    return round(float(score), 4)


def _label(net_pnl: float, validation_pnl: float, holdout_pnl: float, strict_slippage: float, active_pct: float, day_conc: float, trade_conc: float, trades: int, score: float) -> str:
    if trades < 12 or net_pnl <= 0:
        return "rejected"
    # Phase 5A promotion is intentionally conservative: positive net alone is
    # not enough when the validation or holdout split is negative.
    if strict_slippage > 0 and validation_pnl >= 0 and holdout_pnl >= 0 and active_pct >= 0.45 and day_conc <= 0.40 and trade_conc <= 0.25 and score >= 35:
        return "paper_research_candidate"
    if strict_slippage > 0 and net_pnl > 0:
        return "watchlist"
    return "interesting_but_needs_validation" if net_pnl > 0 else "rejected"


def _risk_notes(net_pnl: float, validation_pnl: float, holdout_pnl: float, strict_slippage: float, active_pct: float, day_conc: float, trade_conc: float, trades: int, ambiguity_count: int) -> list[str]:
    notes = []
    if trades < 12:
        notes.append("too few trades")
    if net_pnl <= 0:
        notes.append("negative net PnL")
    if validation_pnl < 0:
        notes.append("negative validation PnL")
    if holdout_pnl < 0:
        notes.append("negative holdout PnL")
    if strict_slippage < 0:
        notes.append("fails 4-tick slippage")
    if active_pct < 0.45:
        notes.append("low active-session coverage")
    if day_conc > 0.40:
        notes.append("one-day concentration risk")
    if trade_conc > 0.25:
        notes.append("one-trade concentration risk")
    if ambiguity_count:
        notes.append("same-bar stop/target ambiguity present")
    return notes


def _profit_factor(wins: float, losses: float) -> float:
    if losses == 0:
        return float("inf") if wins > 0 else 0.0
    return float(wins / abs(losses))


def _concentration(value: float, net_pnl: float) -> float:
    return float(value / net_pnl) if net_pnl > 0 else 1.0
