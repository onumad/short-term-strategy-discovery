from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd


@dataclass(frozen=True)
class Phase8KConfig:
    concentration_limit: float = 0.35
    trade_concentration_limit: float = 0.20
    top_action_count: int = 8
    min_test_trades_for_filter_retest: int = 25


def tag_phase8k_trades_with_folds(trades: pd.DataFrame, fold_results: pd.DataFrame, config: Phase8KConfig = Phase8KConfig()) -> pd.DataFrame:
    """Tag each Phase 8J trade with rolling fold/segment membership."""
    if trades.empty:
        return pd.DataFrame(columns=_tagged_columns())
    if fold_results.empty:
        raise ValueError("Phase 8K requires non-empty Phase 8J fold results")

    prepared = _prepare_trades(trades)
    rows: list[pd.DataFrame] = []
    for _, fold in fold_results.iterrows():
        start = pd.Timestamp(str(fold["segment_start"])).date()
        end = pd.Timestamp(str(fold["segment_end"])).date()
        mask = (prepared["_session_date"] >= start) & (prepared["_session_date"] <= end)
        segment_trades = prepared.loc[mask].copy()
        if segment_trades.empty:
            continue
        segment_net = float(fold.get("net_pnl", segment_trades["net_pnl"].sum()))
        segment_stress = float(fold.get("stress_net_pnl", segment_trades["stress_net_pnl"].sum()))
        segment_trades["fold"] = int(fold["fold"])
        segment_trades["segment"] = str(fold["segment"])
        segment_trades["segment_start"] = str(fold["segment_start"])
        segment_trades["segment_end"] = str(fold["segment_end"])
        segment_trades["segment_session_count"] = int(fold.get("segment_session_count", segment_trades["trading_session"].nunique()))
        segment_trades["segment_net_pnl"] = round(segment_net, 2)
        segment_trades["segment_stress_net_pnl"] = round(segment_stress, 2)
        segment_trades["segment_trade_count"] = int(fold.get("trades", len(segment_trades)))
        segment_trades["segment_best_day_concentration"] = float(fold.get("best_day_concentration", 0.0))
        segment_trades["segment_best_trade_concentration"] = float(fold.get("best_trade_concentration", 0.0))
        segment_trades["fold_segment_label"] = _fold_segment_label(str(fold["segment"]), segment_net, segment_trades.iloc[0], config)
        segment_trades["phase8k_step"] = "1_fold_failure_attribution"
        rows.append(segment_trades)

    if not rows:
        return pd.DataFrame(columns=_tagged_columns())
    out = pd.concat(rows, ignore_index=True)
    out = out.drop(columns=["_session_date"], errors="ignore")
    sort_cols = [column for column in ["fold", "segment_order", "trading_session", "entry_time"] if column in out.columns]
    return out.sort_values(sort_cols).drop(columns=["segment_order"], errors="ignore").reset_index(drop=True)[_available_columns(out, _tagged_columns())]


def summarize_phase8k_sessions(tagged_trades: pd.DataFrame, fold_results: pd.DataFrame, config: Phase8KConfig = Phase8KConfig()) -> pd.DataFrame:
    """Summarize session-level contributors inside each fold/segment."""
    del fold_results
    if tagged_trades.empty:
        return pd.DataFrame(columns=_session_columns())

    group_cols = ["fold", "segment", "trading_session"]
    grouped = tagged_trades.groupby(group_cols, dropna=False).agg(
        segment_start=("segment_start", "first"),
        segment_end=("segment_end", "first"),
        segment_net_pnl=("segment_net_pnl", "first"),
        segment_stress_net_pnl=("segment_stress_net_pnl", "first"),
        fold_segment_label=("fold_segment_label", "first"),
        trades=("net_pnl", "size"),
        net_pnl=("net_pnl", "sum"),
        stress_net_pnl=("stress_net_pnl", "sum"),
        first_entry_time=("entry_time", "min"),
        last_entry_time=("entry_time", "max"),
        best_trade_pnl=("net_pnl", "max"),
        worst_trade_pnl=("net_pnl", "min"),
    )
    out = grouped.reset_index()
    out["loss_share_of_segment"] = out.apply(lambda row: _loss_share(float(row["net_pnl"]), float(row["segment_net_pnl"])), axis=1)
    out["gain_share_of_segment"] = out.apply(lambda row: _gain_share(float(row["net_pnl"]), float(row["segment_net_pnl"])), axis=1)
    out["abs_contribution"] = out.apply(lambda row: _abs_contribution(float(row["net_pnl"]), float(row["segment_net_pnl"])), axis=1)
    out["session_label"] = _session_labels(out, config)
    out["phase8k_step"] = "2_session_concentration_decomposition"
    numeric = ["net_pnl", "stress_net_pnl", "segment_net_pnl", "segment_stress_net_pnl", "loss_share_of_segment", "gain_share_of_segment", "abs_contribution", "best_trade_pnl", "worst_trade_pnl"]
    for column in numeric:
        out[column] = out[column].astype(float).round(6 if column.endswith("segment") or "share" in column or "contribution" in column else 2)
    return out.sort_values(["session_label", "segment", "net_pnl"], ascending=[True, True, True]).reset_index(drop=True)[_session_columns()]


def summarize_phase8k_buckets(tagged_trades: pd.DataFrame, config: Phase8KConfig = Phase8KConfig()) -> pd.DataFrame:
    """Summarize no-lookahead pre-entry buckets across fold segments."""
    if tagged_trades.empty:
        return pd.DataFrame(columns=_bucket_columns())
    rows: list[dict[str, Any]] = []
    for axis in ["rth_bucket", "weekday", "minute_bucket"]:
        if axis not in tagged_trades.columns:
            continue
        for bucket, bucket_rows in tagged_trades.groupby(axis, dropna=False):
            row = {
                "diagnostic_axis": axis,
                "bucket": str(bucket),
                "trades": int(len(bucket_rows)),
                "active_sessions": int(bucket_rows["trading_session"].nunique()),
                "net_pnl": round(float(bucket_rows["net_pnl"].sum()), 2),
                "stress_net_pnl": round(float(bucket_rows["stress_net_pnl"].sum()), 2),
                "train_net_pnl": round(_segment_sum(bucket_rows, "train"), 2),
                "validation_net_pnl": round(_segment_sum(bucket_rows, "validation"), 2),
                "test_net_pnl": round(_segment_sum(bucket_rows, "test"), 2),
                "test_trades": int(len(bucket_rows[bucket_rows["segment"].eq("test")])),
                "negative_test_folds": _negative_segment_count(bucket_rows, "test"),
                "negative_validation_folds": _negative_segment_count(bucket_rows, "validation"),
                "lookahead_guardrail": "uses entry timestamp/session metadata only; diagnostic bucket, not promotion",
            }
            row["bucket_label"] = _bucket_label(row, config)
            row["phase8k_step"] = "3_pre_entry_bucket_decomposition"
            row["bucket_score"] = round(_bucket_score(row), 4)
            rows.append(row)
    if not rows:
        return pd.DataFrame(columns=_bucket_columns())
    out = pd.DataFrame(rows)
    out["_priority"] = out["bucket_label"].map({"phase8k_negative_test_bucket": 0, "phase8k_negative_validation_bucket": 1, "phase8k_concentrated_positive_bucket": 2}).fillna(3)
    out = out.sort_values(["_priority", "test_net_pnl", "validation_net_pnl", "diagnostic_axis", "bucket"], ascending=[True, True, True, True, True])
    return out.drop(columns=["_priority"]).reset_index(drop=True)[_bucket_columns()]


def build_phase8k_candidate_actions(session_diagnostics: pd.DataFrame, bucket_diagnostics: pd.DataFrame, config: Phase8KConfig = Phase8KConfig()) -> pd.DataFrame:
    """Build diagnostic-only follow-up actions from Phase 8K evidence."""
    rows: list[dict[str, Any]] = []
    negative_buckets = bucket_diagnostics[bucket_diagnostics["bucket_label"].isin(["phase8k_negative_test_bucket", "phase8k_negative_validation_bucket"])].copy()
    for _, bucket in negative_buckets.head(config.top_action_count).iterrows():
        rows.append(
            {
                "candidate_action_id": f"phase8k_retest_exclude_{_slug(str(bucket['diagnostic_axis']))}_{_slug(str(bucket['bucket']))}",
                "action_type": "fixed_filter_retest",
                "action_rule": f"exclude {bucket['diagnostic_axis']}={bucket['bucket']}",
                "evidence": f"test_pnl={float(bucket['test_net_pnl']):.2f}; validation_pnl={float(bucket['validation_net_pnl']):.2f}; test_trades={int(bucket['test_trades'])}",
                "source_axis": str(bucket["diagnostic_axis"]),
                "source_bucket": str(bucket["bucket"]),
                "expected_next_phase": "Phase 8L fixed no-lookahead retest",
                "phase8k_action_label": "diagnostic_only_retest_required",
                "promotion_allowed": False,
                "phase8k_step": "4_diagnostic_rescue_candidate_generation",
            }
        )
    losing_sessions = session_diagnostics[session_diagnostics["session_label"].eq("phase8k_losing_fold_worst_session")]
    for _, session in losing_sessions.head(3).iterrows():
        rows.append(
            {
                "candidate_action_id": f"phase8k_review_session_{_slug(str(session['trading_session']))}_fold_{int(session['fold'])}_{session['segment']}",
                "action_type": "failure_attribution",
                "action_rule": f"review session {session['trading_session']} in fold {int(session['fold'])} {session['segment']}",
                "evidence": f"session_pnl={float(session['net_pnl']):.2f}; loss_share={float(session['loss_share_of_segment']):.2%}",
                "source_axis": "trading_session",
                "source_bucket": str(session["trading_session"]),
                "expected_next_phase": "Phase 8K/8L evidence review",
                "phase8k_action_label": "diagnostic_only_retest_required",
                "promotion_allowed": False,
                "phase8k_step": "4_diagnostic_rescue_candidate_generation",
            }
        )
    if not rows:
        rows.append(
            {
                "candidate_action_id": "phase8k_no_rescue_filter_require_more_history",
                "action_type": "decision_checkpoint",
                "action_rule": "require more independent history before deepening the VWAP path",
                "evidence": "no negative no-lookahead bucket stood out",
                "source_axis": "none",
                "source_bucket": "none",
                "expected_next_phase": "Phase 8O decision checkpoint",
                "phase8k_action_label": "diagnostic_only_retest_required",
                "promotion_allowed": False,
                "phase8k_step": "4_diagnostic_rescue_candidate_generation",
            }
        )
    out = pd.DataFrame(rows).drop_duplicates(subset=["candidate_action_id"]).reset_index(drop=True)
    out.insert(0, "phase8k_action_rank", range(1, len(out) + 1))
    return out[_action_columns()]


def build_phase8k_next_step_queue(candidate_actions: pd.DataFrame, session_diagnostics: pd.DataFrame, bucket_diagnostics: pd.DataFrame, config: Phase8KConfig = Phase8KConfig()) -> pd.DataFrame:
    """Return exactly five deterministic follow-up steps after Phase 8J."""
    top_action = candidate_actions.iloc[0]["action_rule"] if not candidate_actions.empty else "require more history"
    losing_fold_count = int(session_diagnostics[session_diagnostics["fold_segment_label"].isin(["phase8k_losing_test_fold", "phase8k_losing_validation_fold"])][["fold", "segment"]].drop_duplicates().shape[0]) if not session_diagnostics.empty else 0
    negative_bucket_count = int(bucket_diagnostics[bucket_diagnostics["bucket_label"].isin(["phase8k_negative_test_bucket", "phase8k_negative_validation_bucket"])].shape[0]) if not bucket_diagnostics.empty else 0
    rows = [
        {
            "step_number": 1,
            "next_phase": "Phase 8K",
            "objective": "Finish fold/session/bucket attribution for the weak Phase 8J fold.",
            "trigger": f"{losing_fold_count} losing validation/test fold segments detected.",
            "output": "phase8k diagnostics and action queue",
            "promotion_allowed": False,
            "phase8k_step_label": "completed_diagnostic_step",
        },
        {
            "step_number": 2,
            "next_phase": "Phase 8L fixed no-lookahead filter retest",
            "objective": f"Retest the top diagnostic rule as fixed before looking at holdout: {top_action}.",
            "trigger": f"{negative_bucket_count} negative pre-entry bucket diagnostics found.",
            "output": "chronological split and walk-forward retest of fixed filter candidates",
            "promotion_allowed": False,
            "phase8k_step_label": "planned_retest_step",
        },
        {
            "step_number": 3,
            "next_phase": "Phase 8M StrategySpec remap",
            "objective": "Only if Phase 8L survives, remap the fixed filter into StrategySpec and rerun rolling folds.",
            "trigger": "Phase 8L must be positive in validation, holdout, stress, and concentration gates.",
            "output": "single fixed StrategySpec diagnostic, no paper promotion",
            "promotion_allowed": False,
            "phase8k_step_label": "conditional_retest_step",
        },
        {
            "step_number": 4,
            "next_phase": "Phase 8N risk overlay stress",
            "objective": "Stress boring daily lockout/trade-cap overlays only after fixed-filter survival.",
            "trigger": f"Concentration limit remains {config.concentration_limit:.0%}; no risk gate can rescue a bad edge alone.",
            "output": "risk overlay diagnostic with component attribution",
            "promotion_allowed": False,
            "phase8k_step_label": "conditional_risk_step",
        },
        {
            "step_number": 5,
            "next_phase": "Phase 8O decision checkpoint",
            "objective": "Reject, require more independent history, or broaden away from this VWAP path.",
            "trigger": "No promotion until every independent fold/concentration gate is clean.",
            "output": "research decision memo and next hypothesis queue",
            "promotion_allowed": False,
            "phase8k_step_label": "decision_checkpoint_step",
        },
    ]
    return pd.DataFrame(rows)[_queue_columns()]


def render_phase8k_report(
    session_diagnostics: pd.DataFrame,
    bucket_diagnostics: pd.DataFrame,
    candidate_actions: pd.DataFrame,
    next_step_queue: pd.DataFrame,
    config: Phase8KConfig,
    *,
    tagged_trades_path: Path,
    session_diagnostics_path: Path,
    bucket_diagnostics_path: Path,
    candidate_actions_path: Path,
    next_step_queue_path: Path,
    report_path: Path,
    run_artifact_dir: Path | None = None,
) -> str:
    del config
    losing = session_diagnostics[session_diagnostics["session_label"].eq("phase8k_losing_fold_worst_session")].head(5) if not session_diagnostics.empty else pd.DataFrame()
    top_buckets = bucket_diagnostics.head(8) if not bucket_diagnostics.empty else pd.DataFrame()
    lines = [
        "# Phase 8K Fold Failure Diagnostic",
        "",
        "Generated by: `./.venv/Scripts/python.exe scripts/run_phase8k_fold_failure_diagnostic.py`",
        "",
        "## Scope And Guardrails",
        "",
        "- Research/simulation only. No live trading, broker adapters, order routing, API-key storage, webhooks, or automated execution were added.",
        "- Phase 8K diagnoses the Phase 8J weak fold and concentration failures using only Phase 8J artifacts and pre-entry metadata.",
        "- No paper-trading promotion: all candidate actions are diagnostic-only and require later fixed retests.",
        "",
        "## Next Five Steps",
        "",
        "| Step | Next Phase | Objective | Trigger | Promotion Allowed |",
        "| ---: | --- | --- | --- | --- |",
    ]
    for _, row in next_step_queue.iterrows():
        lines.append(f"| {int(row['step_number'])} | {row['next_phase']} | {row['objective']} | {row['trigger']} | {bool(row['promotion_allowed'])} |")
    lines.extend(["", "## Losing/Concentration Sessions", "", "| Fold | Segment | Session | PnL | Loss Share | Label |", "| ---: | --- | --- | ---: | ---: | --- |"])
    for _, row in losing.iterrows():
        lines.append(f"| {int(row['fold'])} | {row['segment']} | {row['trading_session']} | ${float(row['net_pnl']):.2f} | {float(row['loss_share_of_segment']) * 100:.1f}% | {row['session_label']} |")
    lines.extend(["", "## Top Bucket Diagnostics", "", "| Axis | Bucket | Label | Test PnL | Validation PnL | Test Trades |", "| --- | --- | --- | ---: | ---: | ---: |"])
    for _, row in top_buckets.iterrows():
        lines.append(f"| {row['diagnostic_axis']} | `{row['bucket']}` | {row['bucket_label']} | ${float(row['test_net_pnl']):.2f} | ${float(row['validation_net_pnl']):.2f} | {int(row['test_trades'])} |")
    lines.extend(["", "## Candidate Actions", "", "| Rank | Action | Rule | Evidence | Label |", "| ---: | --- | --- | --- | --- |"])
    for _, row in candidate_actions.head(10).iterrows():
        lines.append(f"| {int(row['phase8k_action_rank'])} | {row['action_type']} | `{row['action_rule']}` | {row['evidence']} | {row['phase8k_action_label']} |")
    lines.extend(
        [
            "",
            "## Outputs",
            "",
            f"- Tagged trades CSV: `{tagged_trades_path.as_posix()}`",
            f"- Session diagnostics CSV: `{session_diagnostics_path.as_posix()}`",
            f"- Bucket diagnostics CSV: `{bucket_diagnostics_path.as_posix()}`",
            f"- Candidate actions CSV: `{candidate_actions_path.as_posix()}`",
            f"- Next step queue CSV: `{next_step_queue_path.as_posix()}`",
            f"- Report: `{report_path.as_posix()}`",
        ]
    )
    if run_artifact_dir is not None:
        lines.append(f"- Run-scoped artifacts: `{run_artifact_dir.as_posix()}`")
    lines.extend(["", "## Repro Command", "", "```bash", "./.venv/Scripts/python.exe scripts/run_phase8k_fold_failure_diagnostic.py", "```", ""])
    return "\n".join(lines)


def _prepare_trades(trades: pd.DataFrame) -> pd.DataFrame:
    out = trades.copy()
    out["entry_time"] = pd.to_datetime(out["entry_time"], utc=True).dt.tz_convert("America/New_York")
    if "exit_time" in out.columns:
        out["exit_time"] = pd.to_datetime(out["exit_time"], utc=True).dt.tz_convert("America/New_York")
    out["trading_session"] = out["trading_session"].astype(str)
    out["_session_date"] = pd.to_datetime(out["trading_session"]).dt.date
    minutes = out["entry_time"].dt.hour * 60 + out["entry_time"].dt.minute
    out["minute_bucket"] = minutes.map(_minute_bucket)
    if "rth_bucket" not in out.columns:
        out["rth_bucket"] = out["minute_bucket"]
    if "weekday" not in out.columns:
        out["weekday"] = out["entry_time"].dt.day_name()
    if "stress_net_pnl" not in out.columns:
        out["stress_net_pnl"] = out["net_pnl"]
    out["segment_order"] = 9
    return out


def _fold_segment_label(segment: str, segment_net: float, fold: pd.Series, config: Phase8KConfig) -> str:
    if segment == "test" and segment_net < 0:
        return "phase8k_losing_test_fold"
    if segment == "validation" and segment_net < 0:
        return "phase8k_losing_validation_fold"
    if float(fold.get("segment_best_day_concentration", fold.get("best_day_concentration", 0.0))) > config.concentration_limit:
        return "phase8k_concentrated_fold"
    if float(fold.get("segment_best_trade_concentration", fold.get("best_trade_concentration", 0.0))) > config.trade_concentration_limit:
        return "phase8k_concentrated_fold"
    return "phase8k_reference_fold"


def _session_labels(out: pd.DataFrame, config: Phase8KConfig) -> list[str]:
    labels: list[str] = []
    worst_loss_keys = set()
    for key, group in out.groupby(["fold", "segment"]):
        segment_net = float(group.iloc[0]["segment_net_pnl"])
        if segment_net < 0:
            idx = group["net_pnl"].astype(float).idxmin()
            worst_loss_keys.add(idx)
    for idx, row in out.iterrows():
        segment_net = float(row["segment_net_pnl"])
        net = float(row["net_pnl"])
        if idx in worst_loss_keys and str(row["segment"]) in {"validation", "test"}:
            labels.append("phase8k_losing_fold_worst_session")
        elif segment_net > 0 and _gain_share(net, segment_net) > config.concentration_limit:
            labels.append("phase8k_positive_fold_concentration_driver")
        elif net < 0:
            labels.append("phase8k_loss_contributor")
        else:
            labels.append("phase8k_reference_session")
    return labels


def _bucket_label(row: dict[str, Any], config: Phase8KConfig) -> str:
    del config
    if int(row["test_trades"]) >= 1 and float(row["test_net_pnl"]) < 0:
        return "phase8k_negative_test_bucket"
    if float(row["validation_net_pnl"]) < 0:
        return "phase8k_negative_validation_bucket"
    if float(row["test_net_pnl"]) > 0 and int(row["negative_test_folds"]) == 0:
        return "phase8k_positive_test_bucket"
    return "phase8k_reference_bucket"


def _bucket_score(row: dict[str, Any]) -> float:
    return float(row["test_net_pnl"]) + 0.5 * float(row["validation_net_pnl"]) - 25.0 * int(row["negative_test_folds"])


def _segment_sum(rows: pd.DataFrame, segment: str) -> float:
    return float(rows.loc[rows["segment"].eq(segment), "net_pnl"].sum())


def _negative_segment_count(rows: pd.DataFrame, segment: str) -> int:
    if rows.empty:
        return 0
    segment_rows = rows[rows["segment"].eq(segment)]
    if segment_rows.empty:
        return 0
    by_fold = segment_rows.groupby("fold")["net_pnl"].sum()
    return int((by_fold < 0).sum())


def _loss_share(net: float, segment_net: float) -> float:
    if segment_net >= 0 or net >= 0:
        return 0.0
    return float(abs(net) / abs(segment_net)) if segment_net else 0.0


def _gain_share(net: float, segment_net: float) -> float:
    if segment_net <= 0 or net <= 0:
        return 0.0
    return float(net / segment_net) if segment_net else 0.0


def _abs_contribution(net: float, segment_net: float) -> float:
    return float(abs(net) / abs(segment_net)) if segment_net else 0.0


def _minute_bucket(minute_of_day: int) -> str:
    width = 30
    start = int(minute_of_day // width * width)
    end = start + width
    return f"{start // 60:02d}:{start % 60:02d}-{end // 60:02d}:{end % 60:02d}"


def _slug(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "_", value.lower()).strip("_")
    return cleaned or "none"


def _available_columns(frame: pd.DataFrame, columns: list[str]) -> list[str]:
    return [column for column in columns if column in frame.columns]


def _tagged_columns() -> list[str]:
    return [
        "fold",
        "segment",
        "fold_segment_label",
        "phase8k_step",
        "segment_start",
        "segment_end",
        "segment_session_count",
        "segment_net_pnl",
        "segment_stress_net_pnl",
        "segment_trade_count",
        "segment_best_day_concentration",
        "segment_best_trade_concentration",
        "trading_session",
        "entry_time",
        "exit_time",
        "rth_bucket",
        "weekday",
        "minute_bucket",
        "net_pnl",
        "stress_net_pnl",
    ]


def _session_columns() -> list[str]:
    return [
        "phase8k_step",
        "fold",
        "segment",
        "fold_segment_label",
        "trading_session",
        "session_label",
        "segment_start",
        "segment_end",
        "trades",
        "net_pnl",
        "stress_net_pnl",
        "segment_net_pnl",
        "segment_stress_net_pnl",
        "loss_share_of_segment",
        "gain_share_of_segment",
        "abs_contribution",
        "first_entry_time",
        "last_entry_time",
        "best_trade_pnl",
        "worst_trade_pnl",
    ]


def _bucket_columns() -> list[str]:
    return [
        "phase8k_step",
        "diagnostic_axis",
        "bucket",
        "bucket_label",
        "bucket_score",
        "trades",
        "active_sessions",
        "net_pnl",
        "stress_net_pnl",
        "train_net_pnl",
        "validation_net_pnl",
        "test_net_pnl",
        "test_trades",
        "negative_test_folds",
        "negative_validation_folds",
        "lookahead_guardrail",
    ]


def _action_columns() -> list[str]:
    return [
        "phase8k_action_rank",
        "phase8k_step",
        "candidate_action_id",
        "action_type",
        "action_rule",
        "evidence",
        "source_axis",
        "source_bucket",
        "expected_next_phase",
        "phase8k_action_label",
        "promotion_allowed",
    ]


def _queue_columns() -> list[str]:
    return ["step_number", "next_phase", "objective", "trigger", "output", "promotion_allowed", "phase8k_step_label"]
