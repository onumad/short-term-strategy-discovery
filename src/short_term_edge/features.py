from __future__ import annotations

import pandas as pd


def build_feature_frame(
    bars: pd.DataFrame,
    *,
    opening_range_minutes: int = 30,
    forward_minutes: int = 5,
) -> pd.DataFrame:
    """Build deterministic no-lookahead research features from 1-minute RTH bars.

    Feature columns use only current/prior information. Future outcomes are exposed
    only in `label_*` columns so they cannot be mistaken for live signal inputs.
    """
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

    daily = out.groupby(["symbol", "trading_session"], sort=True).agg(
        session_high=("high", "max"),
        session_low=("low", "min"),
        session_close=("close", "last"),
    )
    prior = daily.groupby(level=0).shift(1).rename(
        columns={
            "session_high": "prior_session_high",
            "session_low": "prior_session_low",
            "session_close": "prior_session_close",
        }
    )
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
