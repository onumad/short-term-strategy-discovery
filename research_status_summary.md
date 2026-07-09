# Research Status Summary

The long-term goal of this repository is a production-grade hybrid ML/LLM automated intraday futures trading bot built around deterministic, independently validated playbook modules and risk controls.

The current stage is research and simulation for short-term intraday futures edge discovery. It does not currently approve paper trading, shadow execution, or live trading; moving to any later stage requires an explicit project policy change.

Current direction: build a diversified playbook of specialized deterministic MNQ intraday modules and the point-in-time datasets needed for validated ML scores and bounded LLM proposals. Individual modules may be rare when they have signal evidence and clear market logic; portfolio/playbook evaluation handles combined opportunity, diversification, concentration, and fold stability.

Current evidence: six historical Phase 10B percentile-filter modules are quarantined for noncausal definitions. The remaining 16-module default scheduler universe was faithfully replayed across 869 sessions, and coverage-aligned ML Baseline B found stable diagnostic improvement for large-loss classification. The model remains research-only and is not approved as a signal input pending calibration, drift, abstention, and counterfactual policy-impact validation.

Planned authority boundary: deterministic policy combines playbook state, ML outputs, and schema-constrained LLM proposals; an independent risk engine retains final approval; only the isolated execution process may hold broker credentials or route orders.

Official promotion gates are unchanged. Passing them does not automatically authorize paper or live trading, and paper trading is not currently approved.

Generated/raw research artifacts are intentionally ignored and should not be committed going forward, including local raw data, outputs, reports, artifacts, charts, and trade logs. These files may remain on a local machine for inspection and regeneration, but they are not source-of-truth repository content.

The latest committed research state should be represented by source code, tests, scripts, configuration, and curated documentation. Generated reports, outputs, and artifacts can be regenerated locally from the committed scripts plus local licensed data.
