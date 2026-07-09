from __future__ import annotations

import os
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from short_term_edge.data_loader import load_ohlcv_csv  # noqa: E402
from short_term_edge.phase10b_causal_v2_validation import (  # noqa: E402
    run_phase10b_causal_v2_validation,
    write_phase10b_causal_v2_outputs,
)


def main() -> None:
    run_id = os.environ.get("EXPERIMENT_RUN_ID", "phase10b-causal-v2-r1")
    minimum = int(os.environ.get("MINIMUM_PRIOR_SESSIONS", "20"))
    quarantine = pd.read_csv(PROJECT_ROOT / "outputs" / "module_registry_f_quarantined_modules.csv")
    candidates = quarantine["candidate_id"].astype(str).tolist()
    bars = load_ohlcv_csv(PROJECT_ROOT / "data" / "raw" / "mnq_1m_databento_20230101_20260703.csv")
    sessions = [s for s in sorted(bars["trading_session"].dropna().astype(str).unique()) if s != "2026-07-03"][-252:]
    bars = bars[bars["trading_session"].astype(str).isin(sessions)].copy()
    result = run_phase10b_causal_v2_validation(bars, candidates, minimum_prior_sessions=minimum)
    paths = write_phase10b_causal_v2_outputs(result, PROJECT_ROOT, run_id)
    recommendation = result["next_action_recommendation"]
    print("Phase 10B causal v2 validation complete.")
    print(f"Candidates: {len(result['candidate_results'])}")
    print(f"Trades: {len(result['trade_logs'])}")
    print(f"Full gate passes: {recommendation['full_gate_pass_count']}")
    print(f"Next action: {recommendation['next_action']}")
    print(f"Report: {paths['report']}")


if __name__ == "__main__":
    main()
