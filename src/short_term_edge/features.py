from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from .data_loader import discover_data_files, load_ohlcv_csv
from .sessions import RTH_OPEN

PHASE5B_FEATURE_SCHEMA = [
    "timestamp", "symbol", "trading_session", "session_segment", "open", "high", "low", "close", "volume",
    "bar_index", "day_of_week", "month", "session_vwap", "ema9", "ema20", "sma20", "realized_range_20m",
    "realized_volatility_20m", "trend_slope_20m", "cumulative_rth_volume", "relative_volume_vs_prior_median",
    "volume_regime", "prior_session_high", "prior_session_low", "prior_session_close", "prior_session_range",
    "prior_session_return", "overnight_high", "overnight_low", "overnight_range", "gap_from_prior_close",
    "rth_open", "rth_cumulative_high", "rth_cumulative_low", "rth_cumulative_range", "or_high_30m",
    "or_low_30m", "or_width_30m", "label_forward_close_5m", "label_forward_return_5m",
]


def build_feature_frame(bars: pd.DataFrame, *, opening_range_minutes: int = 30, forward_minutes: int = 5) -> pd.DataFrame:
    """Build deterministic no-lookahead research features from 1-minute RTH bars."""
    if opening_range_minutes < 1:
        raise ValueError("opening_range_minutes must be positive")
    if forward_minutes < 1:
        raise ValueError("forward_minutes must be positive")
    required = {"timestamp", "symbol", "open", "high", "low", "close", "volume", "trading_session", "session_segment"}
    missing = sorted(required.difference(bars.columns))
    if missing:
        raise ValueError(f"missing required columns: {', '.join(missing)}")

    out = bars[bars["session_segment"] == "RTH"].sort_values(["symbol", "trading_session", "timestamp"]).copy()
    out["bar_index"] = out.groupby(["symbol", "trading_session"]).cumcount()
    typical = (out["high"] + out["low"] + out["close"]) / 3.0
    pv = typical * out["volume"]
    session_key = [out["symbol"], out["trading_session"]]
    out["session_vwap"] = pv.groupby(session_key).cumsum() / out["volume"].groupby(session_key).cumsum()
    out["ema9"] = out.groupby(session_key)["close"].transform(lambda s: s.ewm(span=9, adjust=False).mean())
    out["ema20"] = out.groupby(session_key)["close"].transform(lambda s: s.ewm(span=20, adjust=False).mean())
    out["sma20"] = out.groupby(session_key)["close"].transform(lambda s: s.rolling(20, min_periods=5).mean())
    minute_range = out["high"] - out["low"]
    out["realized_range_20m"] = minute_range.groupby(session_key).transform(lambda s: s.rolling(20, min_periods=5).mean())
    daily = out.groupby(["symbol", "trading_session"], sort=True).agg(session_high=("high", "max"), session_low=("low", "min"), session_close=("close", "last"))
    prior = daily.groupby(level=0).shift(1).rename(columns={"session_high": "prior_session_high", "session_low": "prior_session_low", "session_close": "prior_session_close"})
    out = out.merge(prior, left_on=["symbol", "trading_session"], right_index=True, how="left")

    out[f"or_high_{opening_range_minutes}m"] = pd.NA
    out[f"or_low_{opening_range_minutes}m"] = pd.NA
    for _, idx in out.groupby(["symbol", "trading_session"], sort=True).groups.items():
        ordered_idx = list(idx)
        if len(ordered_idx) <= opening_range_minutes:
            continue
        opening_idx = ordered_idx[:opening_range_minutes]
        available_idx = ordered_idx[opening_range_minutes:]
        out.loc[available_idx, f"or_high_{opening_range_minutes}m"] = float(out.loc[opening_idx, "high"].max())
        out.loc[available_idx, f"or_low_{opening_range_minutes}m"] = float(out.loc[opening_idx, "low"].min())
    forward_close = out.groupby(session_key)["close"].shift(-forward_minutes)
    out[f"label_forward_close_{forward_minutes}m"] = forward_close
    out[f"label_forward_return_{forward_minutes}m"] = forward_close - out["close"]
    return out.reset_index(drop=True)


def load_project_bars(project_root: Path) -> pd.DataFrame:
    files = discover_data_files(project_root / "data" / "raw")
    if not files:
        raise FileNotFoundError(f"No local raw CSV files found under {project_root / 'data' / 'raw'}")
    return pd.concat([load_ohlcv_csv(path) for path in files], ignore_index=True).sort_values(["symbol", "timestamp"]).reset_index(drop=True)


def build_phase5b_feature_dataset(bars: pd.DataFrame, *, symbols: tuple[str, ...] = ("MNQ", "MGC"), opening_range_minutes: int = 30, forward_minutes: int = 5) -> pd.DataFrame:
    """Build Phase 5B deterministic regime/features. Rows are RTH bars; labels are explicit label_* columns."""
    if opening_range_minutes != 30 or forward_minutes != 5:
        raise ValueError("Phase 5B stable schema requires opening_range_minutes=30 and forward_minutes=5")
    required = {"timestamp", "symbol", "open", "high", "low", "close", "volume", "trading_session", "session_segment"}
    missing = sorted(required.difference(bars.columns))
    if missing:
        raise ValueError(f"missing required columns: {', '.join(missing)}")

    scoped = bars[bars["symbol"].isin(symbols)].sort_values(["symbol", "trading_session", "timestamp"]).copy()
    rth = scoped[scoped["session_segment"] == "RTH"].copy()
    if rth.empty:
        return pd.DataFrame(columns=PHASE5B_FEATURE_SCHEMA)
    base = build_feature_frame(rth, opening_range_minutes=30, forward_minutes=5)
    key_cols = ["symbol", "trading_session"]
    session_key = [base["symbol"], base["trading_session"]]
    base["day_of_week"] = pd.to_datetime(base["trading_session"]).dt.dayofweek.astype(int)
    base["month"] = pd.to_datetime(base["trading_session"]).dt.month.astype(int)
    returns = base.groupby(key_cols)["close"].pct_change()
    base["realized_volatility_20m"] = returns.groupby(session_key).transform(lambda s: s.rolling(20, min_periods=5).std())
    base["trend_slope_20m"] = base["close"] - base.groupby(key_cols)["close"].shift(20)
    base["cumulative_rth_volume"] = base.groupby(key_cols)["volume"].cumsum()
    base["rth_cumulative_high"] = base.groupby(key_cols)["high"].cummax()
    base["rth_cumulative_low"] = base.groupby(key_cols)["low"].cummin()
    base["rth_cumulative_range"] = base["rth_cumulative_high"] - base["rth_cumulative_low"]

    rth_daily = rth.groupby(key_cols, sort=True).agg(rth_open=("open", "first"), rth_close=("close", "last"), rth_high=("high", "max"), rth_low=("low", "min"), rth_volume=("volume", "sum"))
    prior_daily = rth_daily.groupby(level=0).shift(1)
    prior_volume_median = rth_daily.groupby(level=0)["rth_volume"].transform(lambda s: s.shift(1).rolling(20, min_periods=1).median())
    prior_context = pd.DataFrame({
        "prior_session_range": prior_daily["rth_high"] - prior_daily["rth_low"],
        "prior_session_return": prior_daily["rth_close"] - prior_daily["rth_open"],
        "prior_median_rth_volume_20d": prior_volume_median,
        "rth_open": rth_daily["rth_open"],
    })
    base = base.merge(prior_context, left_on=key_cols, right_index=True, how="left")
    base["relative_volume_vs_prior_median"] = base["cumulative_rth_volume"] / base["prior_median_rth_volume_20d"]
    base["volume_regime"] = pd.cut(base["relative_volume_vs_prior_median"], bins=[-float("inf"), 0.33, 0.66, float("inf")], labels=["low", "normal", "high"]).astype("object")
    overnight = _overnight_summary(scoped)
    base = base.merge(overnight, left_on=key_cols, right_index=True, how="left")
    base["overnight_range"] = base["overnight_high"] - base["overnight_low"]
    base["gap_from_prior_close"] = base["rth_open"] - base["prior_session_close"]
    base["or_width_30m"] = base["or_high_30m"] - base["or_low_30m"]
    for column in PHASE5B_FEATURE_SCHEMA:
        if column not in base.columns:
            base[column] = pd.NA
    return base[PHASE5B_FEATURE_SCHEMA].sort_values(["symbol", "trading_session", "timestamp"]).reset_index(drop=True)


def export_phase5b_features(features: pd.DataFrame, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.suffix == ".parquet":
        features.to_parquet(output_path, index=False)
    elif output_path.suffix == ".csv":
        features.to_csv(output_path, index=False)
    else:
        raise ValueError("Phase 5B feature export path must end in .parquet or .csv")
    return output_path


def summarize_phase5b_features(features: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for symbol, group in features.groupby("symbol", sort=True):
        rows.append({
            "symbol": symbol,
            "rows": int(len(group)),
            "sessions": int(group["trading_session"].nunique()),
            "first_timestamp": str(group["timestamp"].min()),
            "last_timestamp": str(group["timestamp"].max()),
            "schema_columns": int(len(features.columns)),
            "nonnull_prior_session_range": int(group["prior_session_range"].notna().sum()),
            "nonnull_overnight_range": int(group["overnight_range"].notna().sum()),
            "nonnull_or_width_30m": int(group["or_width_30m"].notna().sum()),
        })
    return pd.DataFrame(rows)


def _overnight_summary(scoped: pd.DataFrame) -> pd.DataFrame:
    eth = scoped[(scoped["session_segment"] == "ETH") & (scoped["timestamp"].dt.time < RTH_OPEN)].copy()
    if eth.empty:
        return pd.DataFrame(columns=["overnight_high", "overnight_low"])
    return eth.groupby(["symbol", "trading_session"], sort=True).agg(overnight_high=("high", "max"), overnight_low=("low", "min"))
