from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from short_term_edge.phase7d import Phase7DConfig, render_phase7d_report, run_phase7d_payout_diagnostic  # noqa: E402


def main() -> None:
    output_dir = PROJECT_ROOT / "outputs"
    report_dir = PROJECT_ROOT / "reports"
    output_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)

    trade_log_path = output_dir / "phase7b_mgc_combo_trades.csv"
    results_path = output_dir / "phase7d_payout_diagnostic_results.csv"
    report_path = report_dir / "phase7d_payout_diagnostic_report.md"
    config = Phase7DConfig()

    results = run_phase7d_payout_diagnostic(trade_log_path, config)
    results.to_csv(results_path, index=False)
    report_path.write_text(render_phase7d_report(results, config, results_path, report_path), encoding="utf-8")

    success_count = int(results["success"].sum()) if not results.empty else 0
    print("Phase 7D MGC payout-path / matched-window diagnostic complete.")
    print(f"Results: {results_path}")
    print(f"Report: {report_path}")
    print(f"Rows: {len(results)}; successful payout-path rows: {success_count}")
    if not results.empty:
        top = results.iloc[0]
        print(
            f"Top diagnostic row: combo={top['combo_id']} policy={top['policy_id']} "
            f"success={bool(top['success'])} est_payout={top['estimated_payout']:.2f} final_pnl={top['final_pnl']:.2f}"
        )


if __name__ == "__main__":
    main()
