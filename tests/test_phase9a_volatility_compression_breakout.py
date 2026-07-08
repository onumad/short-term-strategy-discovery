from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from short_term_edge.phase9a_volatility_compression_breakout import (  # noqa: E402
    Phase9AConfig,
    build_phase9a_specs,
    compute_compression_features,
    evaluate_phase9a_candidates,
    generate_phase9a_signals,
    render_phase9a_report,
    simulate_phase9a_trades,
)


class Phase9AVolatilityCompressionBreakoutTests(unittest.TestCase):
    def _bars(self) -> pd.DataFrame:
        rows = []
        sessions = ["2026-01-05", "2026-01-06", "2026-01-07", "2026-01-08", "2026-01-09", "2026-01-12"]
        for day_i, session in enumerate(sessions):
            price = 100.0 + day_i
            for idx, minute in enumerate(range(9 * 60 + 30, 11 * 60 + 30)):
                ts = pd.Timestamp(f"{session} {minute // 60:02d}:{minute % 60:02d}", tz="America/New_York")
                if 20 <= idx < 32:
                    high = price + 0.05
                    low = price - 0.05
                    close = price + 0.01
                elif idx == 32:
                    high = price + 1.2
                    low = price - 0.05
                    close = price + 1.0
                    price = close
                else:
                    price += 0.05
                    high = price + 0.25
                    low = price - 0.25
                    close = price
                rows.append({"timestamp": ts, "symbol": "MNQ", "open": price, "high": high, "low": low, "close": close, "volume": 100, "trading_session": session, "session_segment": "RTH"})
        return pd.DataFrame(rows)

    def test_compression_features_use_past_bars_and_box_is_shifted(self) -> None:
        bars = self._bars()
        featured = compute_compression_features(bars, timeframe=5, method="range_percentile", lookback=4, threshold=0.5)

        self.assertIn("box_high", featured.columns)
        formed = featured.dropna(subset=["box_high", "box_low"])
        self.assertTrue((formed["box_high"] >= formed["box_low"]).all())
        first = formed.iloc[0]
        prior = featured[(featured["trading_session"].eq(first["trading_session"])) & (featured["timestamp"] < first["timestamp"])].tail(4)
        self.assertEqual(float(first["box_high"]), float(prior["high"].max()))

    def test_generate_signals_requires_finished_box_and_enters_after_signal_bar(self) -> None:
        spec = build_phase9a_specs(Phase9AConfig(max_specs=1))[0]
        featured = compute_compression_features(self._bars(), timeframe=5, method=spec.compression_method, lookback=spec.compression_lookback, threshold=spec.compression_threshold)
        signals = generate_phase9a_signals(featured, spec)

        self.assertGreater(len(signals), 0)
        first = signals[0]
        self.assertGreater(pd.Timestamp(first["entry_time"]), pd.Timestamp(first["signal_time"]))
        self.assertGreater(first["box_high"], first["box_low"])

    def test_simulation_uses_conservative_same_bar_policy_and_session_risk_limits(self) -> None:
        spec = build_phase9a_specs(Phase9AConfig(max_specs=1))[0]
        featured = compute_compression_features(self._bars(), timeframe=5, method=spec.compression_method, lookback=spec.compression_lookback, threshold=spec.compression_threshold)
        signals = generate_phase9a_signals(featured, spec)
        trades = simulate_phase9a_trades(featured, signals, spec)

        self.assertFalse(trades.empty)
        self.assertLessEqual(trades.groupby("trading_session").size().max(), spec.max_trades_per_day)
        self.assertIn("same_bar_ambiguity", trades.columns)
        self.assertTrue((trades["entry_time"] > trades["signal_time"]).all())

    def test_evaluate_phase9a_outputs_results_folds_daily_concentration_and_specs(self) -> None:
        config = Phase9AConfig(max_specs=4, train_sessions=2, validation_sessions=1, test_sessions=1, step_sessions=1, min_folds=3, min_trades=2, min_active_session_pct=0.2, concentration_limit=1.0, trade_concentration_limit=1.0)
        specs = build_phase9a_specs(config)
        results, logs, folds, daily, concentration = evaluate_phase9a_candidates(self._bars(), specs, config)

        self.assertEqual(len(results), len(specs))
        self.assertFalse(logs.empty)
        self.assertFalse(folds.empty)
        self.assertFalse(daily.empty)
        self.assertFalse(concentration.empty)
        self.assertIn("phase9a_label", results.columns)
        self.assertIn("walk_forward_test_pnl", results.columns)

    def test_render_phase9a_report_includes_guardrails_outputs_and_labels(self) -> None:
        config = Phase9AConfig(max_specs=2, train_sessions=2, validation_sessions=1, test_sessions=1, step_sessions=1, min_folds=3, min_trades=2)
        specs = build_phase9a_specs(config)
        results, logs, folds, daily, concentration = evaluate_phase9a_candidates(self._bars(), specs, config)
        report = render_phase9a_report(
            results,
            config,
            results_path=Path("outputs/phase9a_candidate_results.csv"),
            trade_logs_path=Path("outputs/phase9a_trade_logs.csv"),
            folds_path=Path("outputs/phase9a_walk_forward_folds.csv"),
            daily_path=Path("outputs/phase9a_daily_pnl.csv"),
            concentration_path=Path("outputs/phase9a_concentration_diagnostics.csv"),
            specs_path=Path("outputs/phase9a_strategy_specs.json"),
            report_path=Path("reports/phase9a_mnq_volatility_compression_breakout_report.md"),
            run_artifact_dir=Path("artifacts/phase9a_mnq_volatility_compression_breakout/test"),
        )

        self.assertIn("# Phase 9A MNQ Volatility Compression Breakout", report)
        self.assertIn("Research/simulation only", report)
        self.assertIn("No live trading", report)
        self.assertIn("phase9a_candidate_results.csv", report)


if __name__ == "__main__":
    unittest.main()
