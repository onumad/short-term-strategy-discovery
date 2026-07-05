from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd

from .data_loader import REQUIRED_COLUMNS, discover_data_files, load_ohlcv_csv


EXPECTED_CLOSURES = [
    {
        "name": "Good Friday 2026",
        "start": "2026-04-03T09:15:00-04:00",
        "end": "2026-04-05T18:00:00-04:00",
    },
    {
        "name": "Juneteenth 2026 early close",
        "start": "2026-06-19T13:00:00-04:00",
        "end": "2026-06-21T18:00:00-04:00",
    },
]


@dataclass(frozen=True)
class AuditConfig:
    raw_dir: Path
    complete_session_min_bars: int = 1_000


def audit_project(config: AuditConfig) -> dict[str, Any]:
    files = discover_data_files(config.raw_dir)
    file_reports = [audit_file(path, config.complete_session_min_bars) for path in files]

    complete_sets = [
        set(report["complete_sessions"])
        for report in file_reports
        if report["complete_sessions"]
    ]
    shared_complete = sorted(set.intersection(*complete_sets)) if complete_sets else []
    recent_window = shared_complete[-63:] if len(shared_complete) >= 63 else shared_complete

    return {
        "raw_dir": str(config.raw_dir),
        "required_columns": REQUIRED_COLUMNS,
        "expected_closures": EXPECTED_CLOSURES,
        "files": file_reports,
        "shared_complete_sessions": shared_complete,
        "recent_window": recent_window,
    }


def audit_file(path: Path, complete_session_min_bars: int) -> dict[str, Any]:
    df = load_ohlcv_csv(path)
    symbols = sorted(df["symbol"].unique().tolist())
    timestamp_dupes = int(df.duplicated(subset=["timestamp", "symbol"]).sum())
    sorted_timestamps = bool(df["timestamp"].is_monotonic_increasing)
    bad_ohlc = int(
        (
            (df["low"] > df[["open", "close"]].min(axis=1))
            | (df["high"] < df[["open", "close"]].max(axis=1))
            | (df["low"] > df["high"])
        ).sum()
    )
    zero_volume = int((df["volume"] == 0).sum())
    negative_volume = int((df["volume"] < 0).sum())

    session_counts = df.groupby("trading_session").size().sort_index()
    rth_counts = (
        df[df["session_segment"] == "RTH"].groupby("trading_session").size().sort_index()
    )
    eth_counts = (
        df[df["session_segment"] == "ETH"].groupby("trading_session").size().sort_index()
    )
    complete_sessions = session_counts[
        session_counts >= complete_session_min_bars
    ].index.tolist()

    gaps = _gap_summary(df)

    return {
        "file": str(path),
        "name": path.name,
        "rows": int(len(df)),
        "symbols": symbols,
        "first_timestamp": _iso(df["timestamp"].iloc[0]) if len(df) else None,
        "last_timestamp": _iso(df["timestamp"].iloc[-1]) if len(df) else None,
        "sorted_timestamps": sorted_timestamps,
        "duplicate_timestamp_symbol_rows": timestamp_dupes,
        "bad_ohlc_rows": bad_ohlc,
        "zero_volume_rows": zero_volume,
        "negative_volume_rows": negative_volume,
        "min_price": float(df[["open", "high", "low", "close"]].min().min()),
        "max_price": float(df[["open", "high", "low", "close"]].max().max()),
        "session_count": int(len(session_counts)),
        "complete_session_count": int(len(complete_sessions)),
        "complete_sessions": complete_sessions,
        "latest_complete_session": complete_sessions[-1] if complete_sessions else None,
        "session_counts_tail": _series_tail(session_counts, 10),
        "latest_complete_rth_bars": _lookup_count(rth_counts, complete_sessions[-1] if complete_sessions else None),
        "latest_complete_eth_bars": _lookup_count(eth_counts, complete_sessions[-1] if complete_sessions else None),
        "gap_summary": gaps,
    }


def render_markdown(report: dict[str, Any]) -> str:
    files = report["files"]
    shared = report["shared_complete_sessions"]
    recent = report["recent_window"]
    latest_shared = shared[-1] if shared else "n/a"
    window_start = recent[0] if recent else "n/a"
    window_end = recent[-1] if recent else "n/a"

    lines = [
        "# Data Audit",
        "",
        f"Date generated: {datetime.now(ZoneInfo('America/New_York')).date()}",
        "",
        "## Summary",
        "",
        f"- Raw data directory: `{report['raw_dir']}`",
        "- Data source: local Databento CSV files only.",
        "- Active instruments discovered: "
        + ", ".join(sorted({symbol for item in files for symbol in item["symbols"]})),
        "- Detected schema: `timestamp,symbol,open,high,low,close,volume`.",
        "- Timezone assumption: `America/New_York` from timestamp offsets.",
        "- Trading session rule: bars at or after `18:00 ET` map to the next CME trade date.",
        "- RTH rule: `09:30-16:00 ET`; all other included bars are ETH.",
        f"- Latest complete shared trading session: `{latest_shared}`.",
        f"- Initial research window: last {len(recent)} shared complete sessions, `{window_start}` through `{window_end}`.",
        "- Partial sessions are excluded from first-pass strategy windows.",
        "",
        "## Files Discovered",
        "",
        "| File | Symbols | Rows | First Timestamp | Last Timestamp | Complete Sessions | Latest Complete Session |",
        "| --- | --- | ---: | --- | --- | ---: | --- |",
    ]
    for item in files:
        lines.append(
            f"| `{item['name']}` | {', '.join(item['symbols'])} | {item['rows']:,} | "
            f"`{item['first_timestamp']}` | `{item['last_timestamp']}` | "
            f"{item['complete_session_count']:,} | `{item['latest_complete_session']}` |"
        )

    lines.extend(
        [
            "",
            "## Integrity Checks",
            "",
            "| File | Sorted | Duplicate Timestamp-Symbol Rows | Bad OHLC Rows | Zero Volume Rows | Negative Volume Rows | Price Range |",
            "| --- | --- | ---: | ---: | ---: | ---: | --- |",
        ]
    )
    for item in files:
        lines.append(
            f"| `{item['name']}` | {str(item['sorted_timestamps']).lower()} | "
            f"{item['duplicate_timestamp_symbol_rows']:,} | {item['bad_ohlc_rows']:,} | "
            f"{item['zero_volume_rows']:,} | {item['negative_volume_rows']:,} | "
            f"{item['min_price']:,.2f} to {item['max_price']:,.2f} |"
        )

    lines.extend(
        [
            "",
            "## Session Coverage",
            "",
            "A complete session is currently defined as at least `1,000` one-minute bars. This threshold keeps normal Globex sessions while excluding known partial download edges and holiday fragments.",
            "",
        ]
    )
    for item in files:
        lines.extend(
            [
                f"### {', '.join(item['symbols'])}",
                "",
                f"- Sessions observed: `{item['session_count']}`.",
                f"- Complete sessions: `{item['complete_session_count']}`.",
                f"- Latest complete session: `{item['latest_complete_session']}`.",
                f"- Latest complete RTH bars: `{item['latest_complete_rth_bars']}`.",
                f"- Latest complete ETH bars: `{item['latest_complete_eth_bars']}`.",
                "- Last observed session counts:",
                "",
            ]
        )
        for date_value, count in item["session_counts_tail"]:
            marker = " partial" if count < 1_000 else ""
            lines.append(f"  - `{date_value}`: `{count}` bars{marker}")
        lines.append("")

    lines.extend(
        [
            "## Gap Summary",
            "",
            "Expected recurring gaps include the daily CME maintenance break, weekend closures, Good Friday 2026, and the Juneteenth 2026 early close configured in the recent download validation note.",
            "",
            "Configured closures:",
            "",
        ]
    )
    for closure in report["expected_closures"]:
        lines.append(f"- {closure['name']}: `{closure['start']}` through `{closure['end']}`")
    lines.append("")

    for item in files:
        gap = item["gap_summary"]
        lines.extend(
            [
                f"### {item['name']}",
                "",
                f"- Non-1-minute gap count: `{gap['total_gaps']}`.",
                "- Most common gap lengths:",
                "",
            ]
        )
        for minutes, count in gap["common_gap_minutes"]:
            lines.append(f"  - `{minutes}` minutes: `{count}` occurrences")
        lines.extend(["", "- Sample gaps:", ""])
        for sample in gap["sample_gaps"]:
            lines.append(
                f"  - `{sample['previous']}` to `{sample['current']}`: `{sample['minutes']}` minutes"
            )
        lines.append("")

    lines.extend(
        [
            "## Limitations And Uncertainties",
            "",
            "- This audit verifies structure and obvious data quality issues; it does not validate a trading edge.",
            "- `2026-07-03` contains only overnight bars through `00:00 ET` download cutoff mechanics and is excluded from complete-session analysis.",
            "- Continuous futures are suitable for tactical research, but rollover effects should still be monitored in later backtests.",
            "- No news calendar, prop-firm rule model, fees, commissions, or slippage model is applied in this first phase.",
            "",
            "## Readiness",
            "",
            "The recent MNQ and MGC files are good enough to start deterministic edge discovery after this audit phase. The next phase should begin with simple, manually tradable intraday families and rank candidates by recent expectancy, trade frequency, risk, and sensitivity to worse slippage.",
            "",
        ]
    )
    return "\n".join(lines)


def _gap_summary(df: pd.DataFrame) -> dict[str, Any]:
    deltas = df["timestamp"].diff().dt.total_seconds().div(60)
    gaps = deltas[deltas != 1].dropna().astype(int)
    samples = []
    for idx, minutes in gaps.head(10).items():
        samples.append(
            {
                "previous": _iso(df.loc[idx - 1, "timestamp"]) if idx > 0 else None,
                "current": _iso(df.loc[idx, "timestamp"]),
                "minutes": int(minutes),
            }
        )
    return {
        "total_gaps": int(len(gaps)),
        "common_gap_minutes": [
            (int(minutes), int(count)) for minutes, count in gaps.value_counts().head(8).items()
        ],
        "sample_gaps": samples,
    }


def _lookup_count(series: pd.Series, key: Any) -> int:
    if key is None or key not in series.index:
        return 0
    return int(series.loc[key])


def _series_tail(series: pd.Series, count: int) -> list[tuple[str, int]]:
    return [(str(index), int(value)) for index, value in series.tail(count).items()]


def _iso(value: Any) -> str:
    return value.isoformat()
