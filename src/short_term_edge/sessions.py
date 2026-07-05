from __future__ import annotations

from dataclasses import dataclass
from datetime import time
from zoneinfo import ZoneInfo

import pandas as pd


ET = ZoneInfo("America/New_York")
SESSION_OPEN = time(18, 0)
RTH_OPEN = time(9, 30)
RTH_CLOSE = time(16, 0)


@dataclass(frozen=True)
class SessionConfig:
    timezone: ZoneInfo = ET
    complete_session_min_bars: int = 1_000


def normalize_timestamps(series: pd.Series, timezone: ZoneInfo = ET) -> pd.Series:
    """Parse timestamp strings and convert them to the configured local timezone."""
    return pd.to_datetime(series, utc=True).dt.tz_convert(timezone)


def trading_session_dates(timestamps: pd.Series) -> pd.Series:
    """Map CME Globex bars at or after 18:00 local time to the next trade date."""
    local_dates = timestamps.dt.date
    next_dates = (timestamps + pd.Timedelta(days=1)).dt.date
    return pd.Series(
        pd.NA,
        index=timestamps.index,
        dtype="object",
    ).mask(timestamps.dt.time < SESSION_OPEN, local_dates).mask(
        timestamps.dt.time >= SESSION_OPEN,
        next_dates,
    )


def session_segment(timestamps: pd.Series) -> pd.Series:
    """Classify bars as RTH or ETH using the requested first-phase convention."""
    is_rth = (timestamps.dt.time >= RTH_OPEN) & (timestamps.dt.time < RTH_CLOSE)
    return pd.Series("ETH", index=timestamps.index).mask(is_rth, "RTH")

