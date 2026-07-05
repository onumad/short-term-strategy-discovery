from __future__ import annotations

import argparse
import os
from pathlib import Path

import databento as db
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
HERMES_ENV = Path.home() / "AppData" / "Local" / "hermes" / ".env"
DATASET = "GLBX.MDP3"
SCHEMA = "ohlcv-1m"
TIMEZONE = "America/New_York"
SYMBOLS = {
    "MNQ": "MNQ.v.0",
    "MGC": "MGC.v.0",
}


def load_api_key() -> str:
    if key := os.environ.get("DATABENTO_API_KEY"):
        return key
    if HERMES_ENV.exists():
        for line in HERMES_ENV.read_text(encoding="utf-8", errors="ignore").splitlines():
            if line.startswith("DATABENTO_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise RuntimeError("DATABENTO_API_KEY is not set in the environment or Hermes .env")


def fetch_continuous_ohlcv(
    client: db.Historical,
    root_symbol: str,
    continuous_symbol: str,
    start: str,
    end: str,
) -> pd.DataFrame:
    store = client.timeseries.get_range(
        dataset=DATASET,
        schema=SCHEMA,
        stype_in="continuous",
        symbols=[continuous_symbol],
        start=start,
        end=end,
    )
    df = store.to_df()
    if df.empty:
        raise RuntimeError(f"Databento returned no rows for {continuous_symbol}")

    out = pd.DataFrame(
        {
            "timestamp": df.index.tz_convert(TIMEZONE).map(lambda ts: ts.isoformat()),
            "symbol": root_symbol,
            "open": df["open"].astype(float),
            "high": df["high"].astype(float),
            "low": df["low"].astype(float),
            "close": df["close"].astype(float),
            "volume": df["volume"].astype("int64"),
        }
    )
    return out.sort_values(["timestamp", "symbol"]).reset_index(drop=True)


def write_atomic_csv(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    df.to_csv(tmp_path, index=False)
    tmp_path.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser(description="Download Databento continuous 1-minute OHLCV futures data.")
    parser.add_argument("--start", default="2023-01-01")
    parser.add_argument("--end", default="2026-07-03")
    parser.add_argument("--raw-dir", type=Path, default=PROJECT_ROOT / "data" / "raw")
    args = parser.parse_args()

    client = db.Historical(load_api_key())
    start_tag = args.start[:10].replace("-", "")
    end_tag = args.end[:10].replace("-", "")

    for root_symbol, continuous_symbol in SYMBOLS.items():
        print(f"Downloading {root_symbol} ({continuous_symbol}) {args.start} through {args.end}...")
        df = fetch_continuous_ohlcv(client, root_symbol, continuous_symbol, args.start, args.end)
        output_path = args.raw_dir / f"{root_symbol.lower()}_1m_databento_{start_tag}_{end_tag}.csv"
        write_atomic_csv(df, output_path)
        print(
            f"Wrote {output_path} | rows={len(df):,} | "
            f"first={df['timestamp'].iloc[0]} | last={df['timestamp'].iloc[-1]}"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
