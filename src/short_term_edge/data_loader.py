from __future__ import annotations

from pathlib import Path

import pandas as pd

from .sessions import ET, normalize_timestamps, session_segment, trading_session_dates


REQUIRED_COLUMNS = ["timestamp", "symbol", "open", "high", "low", "close", "volume"]


def discover_data_files(raw_dir: Path) -> list[Path]:
    return sorted(path for path in raw_dir.glob("*.csv") if path.is_file())


def load_ohlcv_csv(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    missing = [column for column in REQUIRED_COLUMNS if column not in df.columns]
    if missing:
        raise ValueError(f"{path} is missing required columns: {', '.join(missing)}")

    df = df[REQUIRED_COLUMNS].copy()
    df["timestamp"] = normalize_timestamps(df["timestamp"], ET)
    df["symbol"] = df["symbol"].astype(str)

    for column in ["open", "high", "low", "close"]:
        df[column] = pd.to_numeric(df[column], errors="raise")
    df["volume"] = pd.to_numeric(df["volume"], errors="raise")

    df["trading_session"] = trading_session_dates(df["timestamp"])
    df["session_segment"] = session_segment(df["timestamp"])
    return df

