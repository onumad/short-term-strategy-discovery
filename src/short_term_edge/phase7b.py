from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from .ai_search import spec_to_phase4_candidate
from .instruments import get_instrument
from .phase3 import longest_losing_streak, slippage_net_pnl
from .phase4a import generate_phase4a_signals, simulate_phase4a_candidate
from .phase5n import _finite_float, filter_signals_by_side
from .phase7a import Phase7AConfig, _limit_specs_for_run, _prepare_phase7a_data, select_mgc_reproduction_specs
from .strategy_spec import EntryRule, ExitRule, RiskRule, StrategySpec


@dataclass(frozen=True)
class Phase7BConfig:
    symbol: str = "MGC"
    max_combos: int = 6
    min_combos: int = 4
    max_new_combos_per_run: int | None = None
    timeframes: tuple[int, ...] = (1,)

    def validate(self) -> "Phase7BConfig":
        if self.symbol != "MGC":
            raise ValueError("Phase 7B is intentionally MGC-only")
        if self.min_combos < 1:
            raise ValueError("min_combos must be positive")
        if self.max_combos < self.min_combos:
            raise ValueError("max_combos must be greater than or equal to min_combos")
        if self.max_new_combos_per_run is not None and self.max_new_combos_per_run < 0:
            raise ValueError("max_new_combos_per_run must be non-negative when provided")
        if any(int(tf) <= 0 for tf in self.timeframes):
            raise ValueError("timeframes must be positive")
        return self


@dataclass(frozen=True)
class ComboSpec:
    symbol: str
    components: tuple[StrategySpec, ...]
    max_trades_per_day: int
    daily_loss_limit: float
    daily_profit_target: float | None
    include_opening_range_breakout: bool
    priority: str

    @property
    def component_families(self) -> tuple[str, ...]:
        return tuple(spec.family for spec in self.components)

    @property
    def combo_id(self) -> str:
        payload = json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":")).encode("utf-8")
        return f"{self.symbol}_combo_risk_gated_{hashlib.sha1(payload).hexdigest()[:10]}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "component_ids": [spec.canonical_id() for spec in self.components],
            "component_families": list(self.component_families),
            "max_trades_per_day": int(self.max_trades_per_day),
            "daily_loss_limit": float(self.daily_loss_limit),
            "daily_profit_target": self.daily_profit_target,
            "include_opening_range_breakout": bool(self.include_opening_range_breakout),
            "priority": self.priority,
        }


@dataclass(frozen=True)
class Phase7BResult:
    combo_results: pd.DataFrame
    combos: list[ComboSpec]
    trade_log: pd.DataFrame
    complete_sessions: list[Any]


def select_mgc_combo_specs(config: Phase7BConfig = Phase7BConfig()) -> list[ComboSpec]:
    config.validate()
    phase7a_specs = select_mgc_reproduction_specs(Phase7AConfig(max_specs=6, min_specs=6, timeframes=config.timeframes))
    vwap = next(spec for spec in phase7a_specs if spec.family == "vwap_pullback_continuation")
    drive = next(spec for spec in phase7a_specs if spec.family == "opening_drive_continuation")
    orb = StrategySpec(
        instrument=config.symbol,
        family="opening_range_breakout",
        timeframe=1,
        entry=EntryRule("close_outside_range", {"or_minutes": 5, "min_range": 0.8}),
        exit=ExitRule("r_multiple", {"stop_mode": "inside", "target": "2R"}),
        risk=RiskRule("one_open_position", {"max_trades_per_day": 1}),
        notes="Phase 7B optional old-project MGC opening-range breakout combo leg.",
    ).validate()
    combos: list[ComboSpec] = []
    for include_orb in (False, True):
        components = (vwap, drive, orb) if include_orb else (vwap, drive)
        for priority in ("vwap_first", "drive_first"):
            for max_trades in (3, 4):
                combos.append(
                    ComboSpec(
                        symbol=config.symbol,
                        components=components,
                        max_trades_per_day=max_trades,
                        daily_loss_limit=250.0,
                        daily_profit_target=500.0,
                        include_opening_range_breakout=include_orb,
                        priority=priority,
                    )
                )
    selected = sorted(combos, key=lambda combo: (combo.include_opening_range_breakout, combo.priority, combo.max_trades_per_day, combo.combo_id))[: config.max_combos]
    if len(selected) < config.min_combos:
        raise ValueError(f"Phase 7B expected at least {config.min_combos} combos, selected {len(selected)}")
    return selected


def run_phase7b_combo_reproduction(project_root: Path, config: Phase7BConfig = Phase7BConfig(), checkpoint_path: Path | None = None, trade_log_path: Path | None = None) -> Phase7BResult:
    config.validate()
    combos = select_mgc_combo_specs(config)
    if config.max_new_combos_per_run == 0:
        existing = pd.read_csv(checkpoint_path) if checkpoint_path is not None and checkpoint_path.exists() else pd.DataFrame()
        trade_log = pd.read_csv(trade_log_path) if trade_log_path is not None and trade_log_path.exists() else pd.DataFrame()
        return Phase7BResult(rank_phase7b_results(existing), combos, trade_log, [])
    combos_for_run = _limit_combos_for_run(combos, checkpoint_path, config.max_new_combos_per_run)
    prepared, complete_sessions = _prepare_phase7a_data(project_root, Phase7AConfig(symbol=config.symbol, max_specs=6, min_specs=6, timeframes=config.timeframes))
    component_trades = _component_trade_cache(combos_for_run, prepared, complete_sessions)
    rows: list[dict[str, Any]] = []
    trade_rows: list[pd.DataFrame] = []
    if checkpoint_path is not None and checkpoint_path.exists():
        existing = pd.read_csv(checkpoint_path)
        if not existing.empty:
            rows.extend(existing.to_dict("records"))
    if trade_log_path is not None and trade_log_path.exists():
        existing_trades = pd.read_csv(trade_log_path)
        if not existing_trades.empty:
            trade_rows.append(existing_trades)
    completed = {str(row.get("combo_id")) for row in rows}
    for combo in combos_for_run:
        if combo.combo_id in completed:
            continue
        trades = _simulate_combo(combo, component_trades)
        rows.append(_score_combo(combo, trades, complete_sessions).to_dict())
        if not trades.empty:
            trade_rows.append(trades)
        if checkpoint_path is not None:
            checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
            rank_phase7b_results(pd.DataFrame(rows)).drop_duplicates("combo_id", keep="first").to_csv(checkpoint_path, index=False)
        if trade_log_path is not None:
            trade_log_path.parent.mkdir(parents=True, exist_ok=True)
            (pd.concat(trade_rows, ignore_index=True) if trade_rows else pd.DataFrame()).to_csv(trade_log_path, index=False)
    summary = rank_phase7b_results(pd.DataFrame(rows)).drop_duplicates("combo_id", keep="first")
    trade_log = pd.concat(trade_rows, ignore_index=True) if trade_rows else pd.DataFrame()
    return Phase7BResult(summary, combos, trade_log, complete_sessions)


def apply_daily_risk_gates(
    trades: pd.DataFrame,
    *,
    max_trades_per_day: int,
    daily_loss_limit: float,
    daily_profit_target: float | None,
    one_open_position: bool = True,
) -> pd.DataFrame:
    if trades.empty:
        return trades.copy()
    ordered = trades.copy()
    ordered["entry_time"] = pd.to_datetime(ordered["entry_time"])
    ordered["exit_time"] = pd.to_datetime(ordered["exit_time"])
    ordered = ordered.sort_values(["trading_session", "entry_time", "component_priority", "exit_time"] if "component_priority" in ordered.columns else ["trading_session", "entry_time", "exit_time"])
    kept: list[dict[str, Any]] = []
    for session, day in ordered.groupby("trading_session", sort=True):
        realized = 0.0
        accepted = 0
        available_after: pd.Timestamp | None = None
        for row in day.to_dict("records"):
            if accepted >= max_trades_per_day:
                continue
            if realized <= -abs(daily_loss_limit):
                continue
            if daily_profit_target is not None and realized >= float(daily_profit_target):
                continue
            entry_time = pd.Timestamp(row["entry_time"])
            if one_open_position and available_after is not None and entry_time < available_after:
                continue
            out = dict(row)
            out["daily_trade_number"] = accepted + 1
            out["daily_realized_pnl_before_trade"] = round(float(realized), 8)
            out["lockout_status"] = "active"
            kept.append(out)
            accepted += 1
            realized += float(row.get("net_pnl", 0.0))
            available_after = pd.Timestamp(row["exit_time"])
    return pd.DataFrame(kept)


def rank_phase7b_results(combo_summary: pd.DataFrame) -> pd.DataFrame:
    if combo_summary.empty:
        return combo_summary.copy()
    reusable = combo_summary.drop(columns=[col for col in ("phase7b_rank", "phase7b_score", "phase7b_label", "phase7b_notes") if col in combo_summary.columns])
    rows: list[dict[str, Any]] = []
    for _, row in reusable.iterrows():
        out = row.to_dict()
        net = _finite_float(out.get("net_pnl", 0.0), 0.0)
        slippage = _finite_float(out.get("slippage_4_ticks_net_pnl", 0.0), 0.0)
        active = _finite_float(out.get("active_session_pct", 0.0), 0.0)
        trades = int(_finite_float(out.get("trades", 0), 0.0))
        drawdown = _finite_float(out.get("max_drawdown", 0.0), 0.0)
        day = _finite_float(out.get("best_day_concentration", 1.0), 1.0)
        trade = _finite_float(out.get("best_trade_concentration", 1.0), 1.0)
        validation = _finite_float(out.get("validation_pnl", 0.0), 0.0)
        holdout = _finite_float(out.get("holdout_pnl", 0.0), 0.0)
        ambiguity = int(_finite_float(out.get("same_bar_stop_target_ambiguity_count", 0), 0.0))
        score = 0.0
        score += min(max(net / 2_500.0, -2.0), 2.0) * 8.0
        score += min(max(slippage / 2_500.0, -2.0), 2.0) * 36.0
        score += min(max(validation / 1_000.0, -2.0), 2.0) * 10.0
        score += min(max(holdout / 1_000.0, -2.0), 2.0) * 16.0
        score += min(active, 0.40) * 10.0
        score += min(trades / 80.0, 1.0) * 8.0
        score -= min(abs(drawdown) / 1_500.0, 2.5) * 18.0
        score -= max(day - 0.25, 0.0) * 220.0
        score -= max(trade - 0.16, 0.0) * 220.0
        score -= min(ambiguity, 10) * 3.0
        if slippage <= 0:
            score -= 55.0
        if active < 0.10:
            score -= 20.0
        if trades < 30:
            score -= 22.0
        if validation < 0 or holdout < 0:
            score -= 16.0
        out["phase7b_score"] = round(float(score), 4)
        out["phase7b_label"] = _phase7b_label(out)
        out["phase7b_notes"] = _phase7b_notes(out)
        rows.append(out)
    ranked = pd.DataFrame(rows).sort_values(["phase7b_score", "slippage_4_ticks_net_pnl", "net_pnl"], ascending=[False, False, False]).reset_index(drop=True)
    ranked.insert(0, "phase7b_rank", range(1, len(ranked) + 1))
    return ranked


def write_phase7b_combos(combos: list[ComboSpec], path: Path) -> None:
    path.write_text(json.dumps([combo.to_dict() | {"combo_id": combo.combo_id} for combo in combos], indent=2, sort_keys=True), encoding="utf-8")


def _component_trade_cache(combos: list[ComboSpec], prepared: dict[str, dict[str, Any]], complete_sessions: list[Any]) -> dict[str, pd.DataFrame]:
    symbol_data = prepared["MGC"]
    instrument = get_instrument("MGC")
    cache: dict[str, pd.DataFrame] = {}
    for spec in {spec.canonical_id(): spec for combo in combos for spec in combo.components}.values():
        candidate = spec_to_phase4_candidate(spec)
        signal_bars = symbol_data["timeframes"][spec.timeframe]
        signals = generate_phase4a_signals(signal_bars, symbol_data["full"], candidate)
        signals = filter_signals_by_side(signals, str(candidate.params.get("side_filter", "both")))
        trades = simulate_phase4a_candidate(symbol_data["one_minute"], signals, candidate, instrument, complete_sessions)
        if not trades.empty:
            trades = trades.copy()
            trades["component_candidate_id"] = spec.canonical_id()
            trades["component_family"] = spec.family
        cache[spec.canonical_id()] = trades
    return cache


def _simulate_combo(combo: ComboSpec, component_trades: dict[str, pd.DataFrame]) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    priority = _priority_map(combo)
    for spec in combo.components:
        trades = component_trades.get(spec.canonical_id(), pd.DataFrame())
        if trades.empty:
            continue
        out = trades.copy()
        out["combo_id"] = combo.combo_id
        out["combo_priority"] = combo.priority
        out["component_priority"] = priority.get(spec.family, 99)
        frames.append(out)
    merged = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    return apply_daily_risk_gates(
        merged,
        max_trades_per_day=combo.max_trades_per_day,
        daily_loss_limit=combo.daily_loss_limit,
        daily_profit_target=combo.daily_profit_target,
    )


def _score_combo(combo: ComboSpec, trades: pd.DataFrame, complete_sessions: list[Any]) -> pd.Series:
    instrument = get_instrument(combo.symbol)
    base = combo.to_dict() | {"combo_id": combo.combo_id, "instrument": combo.symbol}
    if trades.empty:
        return pd.Series(base | _empty_combo_metrics())
    ordered = trades.sort_values(["entry_time", "exit_time"]).copy()
    net = float(ordered["net_pnl"].sum())
    validation = float(ordered.loc[ordered["split"] == "validation", "net_pnl"].sum()) if "split" in ordered.columns else 0.0
    holdout = float(ordered.loc[ordered["split"] == "holdout", "net_pnl"].sum()) if "split" in ordered.columns else 0.0
    day_pnl = ordered.groupby("trading_session")["net_pnl"].sum()
    equity = ordered["net_pnl"].cumsum()
    drawdown = equity - equity.cummax()
    wins = float(ordered.loc[ordered["net_pnl"] > 0, "net_pnl"].sum())
    losses = float(ordered.loc[ordered["net_pnl"] < 0, "net_pnl"].sum())
    return pd.Series(
        base
        | {
            "net_pnl": net,
            "validation_pnl": validation,
            "holdout_pnl": holdout,
            "slippage_4_ticks_net_pnl": float(slippage_net_pnl(ordered, instrument, 4)),
            "trades": int(len(ordered)),
            "active_sessions": int(ordered["trading_session"].nunique()),
            "active_session_pct": float(ordered["trading_session"].nunique() / len(complete_sessions)) if complete_sessions else 0.0,
            "win_rate": float((ordered["net_pnl"] > 0).mean()),
            "avg_trade": float(ordered["net_pnl"].mean()),
            "profit_factor": _profit_factor(wins, losses),
            "max_drawdown": float(drawdown.min()) if len(drawdown) else 0.0,
            "worst_day": float(day_pnl.min()) if len(day_pnl) else 0.0,
            "longest_losing_streak": longest_losing_streak(ordered["net_pnl"]),
            "best_day_concentration": _concentration(float(day_pnl.max()) if len(day_pnl) else 0.0, net),
            "best_trade_concentration": _concentration(float(ordered["net_pnl"].max()), net),
            "same_bar_stop_target_ambiguity_count": int(ordered.get("same_bar_stop_target_ambiguity", pd.Series(dtype=int)).fillna(0).sum()),
            "component_trade_counts": json.dumps(ordered["component_family"].value_counts().to_dict(), sort_keys=True),
        }
    )


def _limit_combos_for_run(combos: list[ComboSpec], checkpoint_path: Path | None, max_new_combos: int | None) -> list[ComboSpec]:
    if max_new_combos is None:
        return combos
    completed_ids: set[str] = set()
    if checkpoint_path is not None and checkpoint_path.exists():
        existing = pd.read_csv(checkpoint_path)
        if not existing.empty and "combo_id" in existing.columns:
            completed_ids = {str(combo_id) for combo_id in existing["combo_id"]}
    completed = [combo for combo in combos if combo.combo_id in completed_ids]
    pending = [combo for combo in combos if combo.combo_id not in completed_ids]
    return completed + pending[:max_new_combos]


def _priority_map(combo: ComboSpec) -> dict[str, int]:
    if combo.priority == "drive_first":
        order = ("opening_drive_continuation", "vwap_pullback_continuation", "opening_range_breakout")
    else:
        order = ("vwap_pullback_continuation", "opening_drive_continuation", "opening_range_breakout")
    return {family: idx for idx, family in enumerate(order)}


def _phase7b_label(row: dict[str, Any]) -> str:
    if _finite_float(row.get("slippage_4_ticks_net_pnl", 0.0), 0.0) <= 0:
        return "rejected"
    if int(_finite_float(row.get("trades", 0), 0.0)) < 30:
        return "rejected"
    if _finite_float(row.get("active_session_pct", 0.0), 0.0) < 0.10:
        return "rejected"
    if _finite_float(row.get("best_day_concentration", 1.0), 1.0) > 0.25:
        return "rejected"
    if _finite_float(row.get("best_trade_concentration", 1.0), 1.0) > 0.16:
        return "rejected"
    if _finite_float(row.get("max_drawdown", 0.0), 0.0) < -1_500.0:
        return "rejected"
    if int(_finite_float(row.get("same_bar_stop_target_ambiguity_count", 0), 0.0)) > 0:
        return "rejected"
    if _finite_float(row.get("validation_pnl", 0.0), 0.0) < 0 or _finite_float(row.get("holdout_pnl", 0.0), 0.0) < 0:
        return "mgc_combo_watchlist"
    return "mgc_combo_prefilter_survivor"


def _phase7b_notes(row: dict[str, Any]) -> str:
    notes: list[str] = []
    if _finite_float(row.get("slippage_4_ticks_net_pnl", 0.0), 0.0) <= 0:
        notes.append("fails aggregate 4-tick slippage stress")
    if int(_finite_float(row.get("trades", 0), 0.0)) < 30:
        notes.append("too few combo trades")
    if _finite_float(row.get("active_session_pct", 0.0), 0.0) < 0.10:
        notes.append("insufficient active-day coverage")
    if _finite_float(row.get("best_day_concentration", 1.0), 1.0) > 0.25:
        notes.append("one-day concentration risk")
    if _finite_float(row.get("best_trade_concentration", 1.0), 1.0) > 0.16:
        notes.append("one-trade concentration risk")
    if _finite_float(row.get("max_drawdown", 0.0), 0.0) < -1_500.0:
        notes.append("drawdown exceeds Phase 7B cap")
    if int(_finite_float(row.get("same_bar_stop_target_ambiguity_count", 0), 0.0)) > 0:
        notes.append("same-bar stop/target ambiguity remains")
    if _finite_float(row.get("validation_pnl", 0.0), 0.0) < 0:
        notes.append("negative validation split")
    if _finite_float(row.get("holdout_pnl", 0.0), 0.0) < 0:
        notes.append("negative holdout split")
    return "; ".join(notes) if notes else "Survives Phase 7B MGC combo prefilter gates; requires walk-forward validation."


def _empty_combo_metrics() -> dict[str, Any]:
    return {
        "net_pnl": 0.0,
        "validation_pnl": 0.0,
        "holdout_pnl": 0.0,
        "slippage_4_ticks_net_pnl": 0.0,
        "trades": 0,
        "active_sessions": 0,
        "active_session_pct": 0.0,
        "win_rate": 0.0,
        "avg_trade": 0.0,
        "profit_factor": 0.0,
        "max_drawdown": 0.0,
        "worst_day": 0.0,
        "longest_losing_streak": 0,
        "best_day_concentration": 0.0,
        "best_trade_concentration": 0.0,
        "same_bar_stop_target_ambiguity_count": 0,
        "component_trade_counts": "{}",
    }


def _profit_factor(wins: float, losses: float) -> float:
    if losses == 0:
        return float("inf") if wins > 0 else 0.0
    return float(wins / abs(losses))


def _concentration(value: float, total: float) -> float:
    if total <= 0 or value <= 0:
        return 1.0 if total <= 0 else 0.0
    return float(value / total)
