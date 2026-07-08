from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from .phase5n import Phase5NResult, _finite_float, score_prefilter_specs
from .phase7a import Phase7AConfig, _prepare_phase7a_data
from .strategy_spec import EntryRule, ExitRule, RiskRule, StrategySpec

PHASE8A_FAMILIES = ("opening_range_breakout", "vwap_reclaim_rejection", "prior_session_levels")


@dataclass(frozen=True)
class Phase8AConfig:
    symbol: str = "MGC"
    max_specs: int = 12
    min_specs: int = 6
    batch_size: int = 1
    max_new_specs_per_run: int | None = None
    timeframes: tuple[int, ...] = (1, 3)

    def validate(self) -> "Phase8AConfig":
        if self.symbol != "MGC":
            raise ValueError("Phase 8A is intentionally MGC-only")
        if self.min_specs < 1:
            raise ValueError("min_specs must be positive")
        if self.max_specs < self.min_specs:
            raise ValueError("max_specs must be greater than or equal to min_specs")
        if self.batch_size < 1:
            raise ValueError("batch_size must be positive")
        if self.max_new_specs_per_run is not None and self.max_new_specs_per_run < 0:
            raise ValueError("max_new_specs_per_run must be non-negative when provided")
        if any(int(tf) <= 0 for tf in self.timeframes):
            raise ValueError("timeframes must be positive")
        return self


def select_mgc_clean_family_specs(config: Phase8AConfig = Phase8AConfig()) -> list[StrategySpec]:
    """Select a bounded deterministic MGC family sweep after failed legacy-combo transfer."""
    config.validate()
    specs: list[StrategySpec] = []
    symbol = config.symbol
    min_range = 1.0
    for timeframe in config.timeframes:
        for minutes in (15, 30):
            for target in ("1R", "2R"):
                specs.append(
                    StrategySpec(
                        instrument=symbol,
                        family="opening_range_breakout",
                        timeframe=int(timeframe),
                        entry=EntryRule("close_outside_range", {"or_minutes": minutes, "min_range": min_range}),
                        exit=ExitRule("r_multiple", {"target": target, "stop_mode": "half_range"}),
                        risk=RiskRule("one_open_position", {"max_trades_per_day": 1}),
                        notes="Phase 8A MGC clean-family pivot: opening-range breakout away from failed legacy combo legs.",
                    ).validate()
                )
        for mode in ("reclaim", "rejection", "both"):
            for stop_ticks, target_ticks in ((12, 18), (18, 27)):
                specs.append(
                    StrategySpec(
                        instrument=symbol,
                        family="vwap_reclaim_rejection",
                        timeframe=int(timeframe),
                        entry=EntryRule("vwap_cross", {"mode": mode}),
                        exit=ExitRule("fixed_ticks", {"stop_ticks": stop_ticks, "target_ticks": target_ticks}),
                        risk=RiskRule("one_open_position", {"max_trades_per_day": 2}),
                        notes="Phase 8A MGC clean-family pivot: VWAP reclaim/rejection without Phase 7 pullback leg.",
                    ).validate()
                )
        for mode in ("break_hold", "sweep_reverse", "prior_close_reclaim"):
            specs.append(
                StrategySpec(
                    instrument=symbol,
                    family="prior_session_levels",
                    timeframe=int(timeframe),
                    entry=EntryRule("prior_level_reaction", {"mode": mode}),
                    exit=ExitRule("fixed_ticks", {"stop_ticks": 12, "target_ticks": 18}),
                    risk=RiskRule("one_open_position", {"max_trades_per_day": 2}),
                    notes="Phase 8A MGC clean-family pivot: prior-session level reaction.",
                ).validate()
            )
    ordered = sorted(
        {spec.canonical_id(): spec for spec in specs}.values(),
        key=lambda spec: (
            spec.family,
            int(spec.timeframe),
            json.dumps(spec.entry.params, sort_keys=True),
            json.dumps(spec.exit.params, sort_keys=True),
            json.dumps(spec.risk.params, sort_keys=True),
            spec.canonical_id(),
        ),
    )
    selected = _round_robin_by_family(ordered, config.max_specs)
    if len(selected) < config.min_specs:
        raise ValueError(f"Phase 8A expected at least {config.min_specs} specs, selected {len(selected)}")
    return selected


def run_phase8a_mgc_clean_family_search(project_root: Path, config: Phase8AConfig = Phase8AConfig(), checkpoint_path: Path | None = None) -> Phase5NResult:
    config.validate()
    specs = select_mgc_clean_family_specs(config)
    checkpoint_rows = _refresh_phase8a_checkpoint(checkpoint_path, specs)
    if config.max_new_specs_per_run == 0:
        return Phase5NResult(search_results=rank_phase8a_results(checkpoint_rows), specs=specs, complete_sessions=[])
    specs_for_run = _limit_specs_for_run(specs, checkpoint_path, config.max_new_specs_per_run)
    prepared, complete_sessions = _prepare_phase7a_data(
        project_root,
        Phase7AConfig(symbol=config.symbol, max_specs=max(len(specs), 1), min_specs=1, timeframes=config.timeframes),
    )
    scored = score_prefilter_specs(specs_for_run, prepared, complete_sessions, checkpoint_path=checkpoint_path, batch_size=config.batch_size)
    return Phase5NResult(search_results=rank_phase8a_results(_filter_phase8a_rows(scored, specs)), specs=specs, complete_sessions=complete_sessions)


def write_phase8a_specs(specs: list[StrategySpec], path: Path) -> None:
    path.write_text(json.dumps([json.loads(spec.to_json()) | {"canonical_id": spec.canonical_id()} for spec in specs], indent=2, sort_keys=True), encoding="utf-8")


def render_phase8a_report(
    config: Phase8AConfig,
    results: pd.DataFrame,
    *,
    selected_specs_count: int,
    complete_sessions_count: int,
    results_path: Path,
    specs_path: Path,
    report_path: Path,
    repro_command: str | None = None,
) -> str:
    label_counts = results["phase8a_label"].value_counts().to_dict() if not results.empty and "phase8a_label" in results.columns else {}
    family_counts = results["family"].value_counts().to_dict() if not results.empty and "family" in results.columns else {}
    lines = [
        "# Phase 8A MGC Clean-Family Prefilter Report",
        "",
        "Generated by: `./.venv/Scripts/python.exe scripts/run_phase8a_mgc_clean_family_search.py`",
        "",
        "## Scope And Guardrails",
        "",
        "- Research/simulation only. No live trading, broker adapters, API-key storage, webhooks, order routing, or automated execution were added.",
        "- Phase 8A pivots away from the failed Phase 7 legacy combo and tests deterministic non-legacy MGC families.",
        "- Candidate labels are prefilter research labels only; survivors require walk-forward validation before paper-test consideration.",
        "",
        "## Configuration",
        "",
        f"- Symbol: `{config.symbol}`",
        f"- Selected specs: `{selected_specs_count}`",
        f"- Rows scored: `{len(results)}` / selected specs: `{selected_specs_count}`",
        f"- Timeframes: `{config.timeframes}`",
        f"- Max new specs this invocation: `{config.max_new_specs_per_run}` (set `PHASE8A_MAX_NEW_SPECS` to adjust bounded batches)",
        f"- Complete MGC sessions: `{complete_sessions_count}`" if complete_sessions_count else "- Complete MGC sessions: not reloaded during checkpoint-only refresh",
        f"- Label counts: `{label_counts}`",
        f"- Family counts in scored rows: `{family_counts}`",
        "",
        "## Cost assumptions",
        "",
        _cost_assumption_line(results),
        "",
        "## Outputs",
        "",
        f"- Search results: `{_display_path(results_path)}`",
        f"- Candidate specs: `{_display_path(specs_path)}`",
        f"- Report: `{_display_path(report_path)}`",
        "",
        "## Top Ranked Results",
        "",
        "| Rank | Candidate | Family | Label | Score | Net PnL | 4-Tick Slip | Trades | Active % | Max DD | Day Conc. | Trade Conc. | Ambiguity | Notes |",
        "| ---: | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    if not results.empty:
        for _, row in results.head(12).iterrows():
            lines.append(
                f"| {int(row['phase8a_rank'])} | `{row.get('candidate_id', 'unknown')}` | {row.get('family', 'unknown')} | {row['phase8a_label']} | {row['phase8a_score']:.2f} | ${row['net_pnl']:.2f} | ${row['slippage_4_ticks_net_pnl']:.2f} | {int(row['trades'])} | {row['active_session_pct'] * 100:.1f}% | ${row['max_drawdown']:.2f} | {row['best_day_concentration'] * 100:.1f}% | {row['best_trade_concentration'] * 100:.1f}% | {int(row.get('same_bar_stop_target_ambiguity_count', 0))} | {row['phase8a_notes']} |"
            )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- `mgc_clean_family_prefilter_survivor` means a candidate survived the cheap full-history Phase 8A gates and needs walk-forward validation.",
            "- `mgc_clean_family_watchlist` means core gates passed but validation/holdout split behavior was weak.",
            "- `rejected` means the candidate failed one or more strict robustness gates.",
            "",
            "## Repro Command",
            "",
            "```bash",
            repro_command or _phase8a_repro_command(config),
            "```",
            "",
        ]
    )
    return "\n".join(lines)


def _phase8a_repro_command(config: Phase8AConfig) -> str:
    max_new = 1 if config.max_new_specs_per_run is None else int(config.max_new_specs_per_run)
    return f"PHASE8A_MAX_NEW_SPECS={max_new} ./.venv/Scripts/python.exe scripts/run_phase8a_mgc_clean_family_search.py"


def _display_path(path: Path) -> str:
    return path.as_posix()


def _cost_assumption_line(results: pd.DataFrame) -> str:
    base_cost = _first_numeric_value(results, "base_cost")
    stress_cost = _first_numeric_value(results, "stress_cost")
    if base_cost is None and stress_cost is None:
        return "- Cost columns unavailable in current scored rows; rerun scoring to include base and stress costs."
    base_text = "unavailable" if base_cost is None else f"${base_cost:.2f}"
    stress_text = "unavailable" if stress_cost is None else f"${stress_cost:.2f}"
    return f"- Reported PnL uses base cost `{base_text}` and 4-tick stress cost `{stress_text}` per trade when available."


def _first_numeric_value(results: pd.DataFrame, column: str) -> float | None:
    if results.empty or column not in results.columns:
        return None
    values = pd.to_numeric(results[column], errors="coerce").dropna()
    return None if values.empty else float(values.iloc[0])


def _refresh_phase8a_checkpoint(checkpoint_path: Path | None, specs: list[StrategySpec]) -> pd.DataFrame:
    if checkpoint_path is None or not checkpoint_path.exists():
        return pd.DataFrame()
    existing = pd.read_csv(checkpoint_path)
    filtered = _filter_phase8a_rows(existing, specs)
    if len(filtered) != len(existing):
        filtered.to_csv(checkpoint_path, index=False)
    return filtered


def _filter_phase8a_rows(candidate_summary: pd.DataFrame, specs: list[StrategySpec]) -> pd.DataFrame:
    if candidate_summary.empty:
        return candidate_summary.copy()
    if "candidate_id" not in candidate_summary.columns:
        return candidate_summary.iloc[0:0].copy()
    allowed_ids = {spec.canonical_id() for spec in specs}
    filtered = candidate_summary[candidate_summary["candidate_id"].astype(str).isin(allowed_ids)].copy()
    if "instrument" in filtered.columns:
        filtered = filtered[filtered["instrument"].astype(str).eq("MGC")]
    if "family" in filtered.columns:
        filtered = filtered[filtered["family"].astype(str).isin(PHASE8A_FAMILIES)]
    return filtered.reset_index(drop=True)


def _limit_specs_for_run(specs: list[StrategySpec], checkpoint_path: Path | None, max_new_specs: int | None) -> list[StrategySpec]:
    if max_new_specs is None:
        return specs
    completed_ids: set[str] = set()
    if checkpoint_path is not None and checkpoint_path.exists():
        existing = pd.read_csv(checkpoint_path)
        if not existing.empty and "candidate_id" in existing.columns:
            completed_ids = {str(candidate_id) for candidate_id in existing["candidate_id"]}
    completed = [spec for spec in specs if spec.canonical_id() in completed_ids]
    pending = [spec for spec in specs if spec.canonical_id() not in completed_ids]
    return completed + pending[:max_new_specs]


def rank_phase8a_results(candidate_summary: pd.DataFrame) -> pd.DataFrame:
    if candidate_summary.empty:
        return candidate_summary.copy()
    reusable = candidate_summary.drop(
        columns=[column for column in candidate_summary.columns if column.startswith(("phase8a_", "phase5n_"))]
    )
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
        score -= min(ambiguity, 10) * 5.0
        if slippage <= 0:
            score -= 55.0
        if active < 0.10:
            score -= 20.0
        if trades < 30:
            score -= 22.0
        if validation < 0 or holdout < 0:
            score -= 16.0
        out["phase8a_score"] = round(float(score), 4)
        out["phase8a_label"] = _phase8a_label(out)
        out["phase8a_notes"] = _phase8a_notes(out)
        rows.append(out)
    ranked = pd.DataFrame(rows).sort_values(["phase8a_score", "slippage_4_ticks_net_pnl", "net_pnl"], ascending=[False, False, False]).reset_index(drop=True)
    ranked.insert(0, "phase8a_rank", range(1, len(ranked) + 1))
    return ranked


def _phase8a_label(row: dict[str, Any]) -> str:
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
        return "mgc_clean_family_watchlist"
    return "mgc_clean_family_prefilter_survivor"


def _phase8a_notes(row: dict[str, Any]) -> str:
    notes: list[str] = []
    if _finite_float(row.get("slippage_4_ticks_net_pnl", 0.0), 0.0) <= 0:
        notes.append("fails aggregate 4-tick slippage stress")
    if int(_finite_float(row.get("trades", 0), 0.0)) < 30:
        notes.append("too few trades")
    if _finite_float(row.get("active_session_pct", 0.0), 0.0) < 0.10:
        notes.append("insufficient active-day coverage")
    if _finite_float(row.get("best_day_concentration", 1.0), 1.0) > 0.25:
        notes.append("one-day concentration risk")
    if _finite_float(row.get("best_trade_concentration", 1.0), 1.0) > 0.16:
        notes.append("one-trade concentration risk")
    if _finite_float(row.get("max_drawdown", 0.0), 0.0) < -1_500.0:
        notes.append("drawdown exceeds Phase 8A cap")
    if int(_finite_float(row.get("same_bar_stop_target_ambiguity_count", 0), 0.0)) > 0:
        notes.append("same-bar stop/target ambiguity remains")
    if _finite_float(row.get("validation_pnl", 0.0), 0.0) < 0:
        notes.append("negative validation split")
    if _finite_float(row.get("holdout_pnl", 0.0), 0.0) < 0:
        notes.append("negative holdout split")
    return "; ".join(notes) if notes else "Survives Phase 8A MGC clean-family prefilter gates; requires walk-forward validation."


def _round_robin_by_family(specs: list[StrategySpec], max_specs: int) -> list[StrategySpec]:
    timeframes = tuple(sorted({int(spec.timeframe) for spec in specs}))
    buckets = {
        (family, timeframe): [spec for spec in specs if spec.family == family and int(spec.timeframe) == timeframe]
        for timeframe in timeframes
        for family in PHASE8A_FAMILIES
    }
    selected: list[StrategySpec] = []
    while len(selected) < max_specs and any(buckets.values()):
        for timeframe in timeframes:
            for family in PHASE8A_FAMILIES:
                bucket = buckets[(family, timeframe)]
                if bucket and len(selected) < max_specs:
                    selected.append(bucket.pop(0))
    return selected
