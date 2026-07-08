# Portfolio Audit C — Playbook With Phase 14A Prior-Level Reaction Modules

Research/simulation only. No live trading, broker adapters, order routing, webhooks, credential storage, automated execution, or LLM-driven trade decisions.

## Scope

Diagnostic portfolio audit only. It uses existing registry, Portfolio Audit B, and phase outputs; it does not generate signals, run searches, change official gates, promote candidates, or approve paper trading.

## Summary

- Selected modules: `24`
- Portfolio rows: `24`
- Next action: `keep_phase14a_as_diversifier_and_search_more_uncorrelated_modules`
- Rationale: Phase 14A improves activity or correlation, but fold/concentration gates remain insufficient.
- Paper trading approved: `false`

## Phase 14A Impact Versus Portfolio Audit B Best

| Mode | Active days Δ | Fold Δ | Best-day conc Δ | Best-trade conc Δ | Drawdown Δ | Correlation Δ | Gap days | PnL | Trades | Active days | No-trade days | Negative-PnL days | Role |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| raw_sum_diagnostic | 21 | 0.000 | 0.010 | -0.009 | -379.42 | -0.012 | 1 | 797.97 | 141 | 108 | 21 | 43 | diversifier_module |
| one_trade_at_a_time_chronological | 21 | 0.000 | -0.010 | -0.010 | -362.68 | -0.012 | 1 | 581.99 | 115 | 94 | 21 | 38 | diversifier_module |
| max_one_trade_per_session | 21 | 0.000 | 0.038 | 0.038 | -4.74 | -0.012 | 1 | -753.41 | 49 | 49 | 21 | 15 | diversifier_module |

## Phase 13A vs Phase 14A

| Set | Mode | Phase13A net | Phase14A net | Phase13A trades | Phase14A trades | Phase13A days | Phase14A days | Net Δ | Day Δ |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| audit_b_best_plus_phase13a_and_phase14a | max_one_trade_per_session | 1228.82 | -343.85 | 87 | 37 | 87 | 37 | -1572.67 | -50 |
| audit_b_best_plus_phase13a_and_phase14a | one_trade_at_a_time_chronological | 763.31 | 499.93 | 115 | 109 | 111 | 88 | -263.38 | -23 |
| audit_b_best_plus_phase13a_and_phase14a | raw_sum_diagnostic | 1762.00 | 797.97 | 246 | 141 | 123 | 108 | -964.03 | -15 |
| diversifier_only_13a_14a | max_one_trade_per_session | 754.70 | 365.52 | 108 | 77 | 108 | 77 | -389.18 | -31 |
| diversifier_only_13a_14a | one_trade_at_a_time_chronological | 407.66 | 673.63 | 125 | 132 | 121 | 100 | 265.97 | -21 |
| diversifier_only_13a_14a | raw_sum_diagnostic | 1762.00 | 797.97 | 246 | 141 | 123 | 108 | -964.03 | -15 |
| prior_level_diversifiers_only | max_one_trade_per_session | 754.70 | 365.52 | 108 | 77 | 108 | 77 | -389.18 | -31 |
| prior_level_diversifiers_only | one_trade_at_a_time_chronological | 407.66 | 673.63 | 125 | 132 | 121 | 100 | 265.97 | -21 |
| prior_level_diversifiers_only | raw_sum_diagnostic | 1762.00 | 797.97 | 246 | 141 | 123 | 108 | -964.03 | -15 |

## Portfolio Results

| Set | Mode | Net | Active days | Best-day conc | Best-trade conc | Positive folds | Label | Status |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- | --- |
| all_parked_modules_with_13a_14a | one_trade_at_a_time_chronological | -3772.54 | 243 | 1.000 | 1.000 | 0.333 | portfolio_c_failed_negative | no_portfolio_benefit |
| all_parked_modules_with_13a_14a | raw_sum_diagnostic | 31684.14 | 243 | 0.158 | 0.029 | 0.833 | portfolio_c_positive_but_concentrated | portfolio_still_nontradable |
| audit_b_best_plus_phase13a_and_phase14a | raw_sum_diagnostic | 11284.12 | 244 | 0.132 | 0.080 | 0.833 | portfolio_c_positive_but_concentrated | portfolio_still_nontradable |
| audit_b_best_plus_phase14a | raw_sum_diagnostic | 9522.12 | 220 | 0.114 | 0.095 | 0.833 | portfolio_c_positive_but_concentrated | portfolio_still_nontradable |
| greedy_low_correlation_with_14a | raw_sum_diagnostic | 9269.82 | 242 | 0.117 | 0.098 | 0.667 | portfolio_c_positive_but_concentrated | portfolio_still_nontradable |
| audit_b_best_reconstructed | raw_sum_diagnostic | 8724.15 | 199 | 0.104 | 0.104 | 0.833 | portfolio_c_positive_but_concentrated | portfolio_still_nontradable |
| top_cross_family_plus_13a_14a | raw_sum_diagnostic | 7239.88 | 243 | 0.141 | 0.125 | 0.500 | portfolio_c_positive_but_concentrated | portfolio_still_nontradable |
| greedy_low_correlation_with_14a | one_trade_at_a_time_chronological | 7211.25 | 242 | 0.127 | 0.126 | 0.667 | portfolio_c_positive_but_concentrated | phase14a_reduces_concentration |
| audit_b_best_plus_phase13a_and_phase14a | one_trade_at_a_time_chronological | 7133.22 | 244 | 0.123 | 0.127 | 0.667 | portfolio_c_positive_but_concentrated | phase14a_reduces_concentration |
| audit_b_best_plus_phase14a | one_trade_at_a_time_chronological | 6911.09 | 220 | 0.131 | 0.131 | 0.833 | portfolio_c_positive_but_concentrated | phase14a_reduces_concentration |
| audit_b_best_reconstructed | one_trade_at_a_time_chronological | 6408.14 | 199 | 0.141 | 0.141 | 0.833 | portfolio_c_positive_but_concentrated | portfolio_still_nontradable |
| top_cross_family_plus_13a_14a | one_trade_at_a_time_chronological | 5721.91 | 243 | 0.160 | 0.158 | 0.667 | portfolio_c_positive_but_concentrated | portfolio_still_nontradable |
| audit_b_best_reconstructed | max_one_trade_per_session | 5529.25 | 199 | 0.164 | 0.164 | 0.833 | portfolio_c_positive_but_concentrated | portfolio_still_nontradable |
| audit_b_best_plus_phase14a | max_one_trade_per_session | 4479.69 | 220 | 0.202 | 0.202 | 0.833 | portfolio_c_positive_but_concentrated | portfolio_still_nontradable |
| audit_b_best_plus_phase13a_and_phase14a | max_one_trade_per_session | 3685.60 | 244 | 0.158 | 0.158 | 0.667 | portfolio_c_positive_but_concentrated | phase14a_reduces_concentration |
| greedy_low_correlation_with_14a | max_one_trade_per_session | 2774.53 | 242 | 0.263 | 0.263 | 0.500 | portfolio_c_positive_but_concentrated | portfolio_still_nontradable |
| top_cross_family_plus_13a_14a | max_one_trade_per_session | 2564.75 | 243 | 0.242 | 0.242 | 0.500 | portfolio_c_positive_but_concentrated | portfolio_still_nontradable |
| diversifier_only_13a_14a | raw_sum_diagnostic | 2559.97 | 185 | 0.399 | 0.242 | 0.500 | portfolio_c_positive_but_concentrated | portfolio_still_nontradable |
| prior_level_diversifiers_only | raw_sum_diagnostic | 2559.97 | 185 | 0.399 | 0.242 | 0.500 | portfolio_c_positive_but_concentrated | portfolio_still_nontradable |
| all_parked_modules_with_13a_14a | max_one_trade_per_session | 1348.25 | 243 | 0.431 | 0.431 | 0.500 | portfolio_c_positive_but_concentrated | portfolio_still_nontradable |
| diversifier_only_13a_14a | max_one_trade_per_session | 1120.22 | 185 | 0.554 | 0.554 | 0.500 | portfolio_c_positive_but_concentrated | portfolio_still_nontradable |
| prior_level_diversifiers_only | max_one_trade_per_session | 1120.22 | 185 | 0.554 | 0.554 | 0.500 | portfolio_c_positive_but_concentrated | portfolio_still_nontradable |
| diversifier_only_13a_14a | one_trade_at_a_time_chronological | 1081.29 | 185 | 0.760 | 0.574 | 0.500 | portfolio_c_positive_but_concentrated | portfolio_still_nontradable |
| prior_level_diversifiers_only | one_trade_at_a_time_chronological | 1081.29 | 185 | 0.760 | 0.574 | 0.500 | portfolio_c_positive_but_concentrated | portfolio_still_nontradable |

## Interpretation

Phase 14A remains research-only. Portfolio Audit C reports diagnostic gate status only; no portfolio is paper-trading approved.
