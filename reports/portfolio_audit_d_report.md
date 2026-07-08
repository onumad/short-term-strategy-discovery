# Portfolio Audit D — Playbook With Phase 15A Trend/Power Diversifier Modules

Research/simulation only. No live trading, broker adapters, order routing, webhooks, credential storage, automated execution, or LLM-driven trade decisions.

## Scope

Diagnostic portfolio audit only. It uses existing registries, Portfolio Audit C, and phase outputs; it does not generate signals, run searches, change official gates, promote candidates, or approve paper trading.

## Summary

- Selected modules: `28`
- Portfolio rows: `27`
- Next action: `weak_fold_regime_audit_b_before_more_module_search`
- Rationale: Portfolio Audits B/C/D show activity or concentration improvement without enough fold improvement.
- Paper trading approved: `false`

## Phase 15A Impact Versus Portfolio Audit C Best

| Mode | Active days Δ | Fold Δ | Best-day conc Δ | Best-trade conc Δ | Drawdown Δ | Correlation Δ | Gap days | PnL | Trades | Active days | Overlap skipped | Session skipped | No-trade days | Negative-PnL days | Role |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| raw_sum_diagnostic | 1 | 0.000 | 0.009 | -0.001 | -409.98 | -0.050 | 4 | 1259.11 | 154 | 102 | 0 | 0 | 1 | 48 | diversifier_module |
| one_trade_at_a_time_chronological | 1 | 0.000 | 0.000 | 0.000 | 331.52 | -0.050 | 4 | 813.21 | 114 | 102 | 896 | 0 | 1 | 48 | diversifier_module |
| max_one_trade_per_session | 1 | 0.000 | -0.023 | -0.023 | 0.00 | -0.050 | 4 | 77.26 | 1 | 1 | 0 | 1667 | 1 | 0 | diversifier_module |

## Phase 13A vs Phase 14A vs Phase 15A

| Set | Mode | Phase13A net | Phase14A net | Phase15A net | Phase13A trades | Phase14A trades | Phase15A trades | Phase13A days | Phase14A days | Phase15A days | 15A-13A net | 15A-14A net |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| audit_c_best_plus_13a_14a_15a | max_one_trade_per_session | 208.59 | -316.59 | 77.26 | 45 | 13 | 1 | 45 | 13 | 1 | -131.33 | 393.85 |
| audit_c_best_plus_13a_14a_15a | one_trade_at_a_time_chronological | 840.39 | 1008.87 | 813.21 | 91 | 103 | 114 | 89 | 83 | 102 | -27.18 | -195.66 |
| audit_c_best_plus_13a_14a_15a | raw_sum_diagnostic | 1762.00 | 797.97 | 1259.11 | 246 | 141 | 154 | 123 | 108 | 102 | -502.89 | 461.14 |
| top_cross_family_plus_13a_14a_15a | max_one_trade_per_session | -153.60 | 788.72 | -125.35 | 47 | 19 | 4 | 47 | 19 | 4 | 28.25 | -914.07 |
| top_cross_family_plus_13a_14a_15a | one_trade_at_a_time_chronological | 415.93 | 829.21 | 813.21 | 95 | 115 | 114 | 93 | 87 | 102 | 397.28 | -16.00 |
| top_cross_family_plus_13a_14a_15a | raw_sum_diagnostic | 1762.00 | 797.97 | 1259.11 | 246 | 141 | 154 | 123 | 108 | 102 | -502.89 | 461.14 |
| diversifier_only_13a_14a_15a | max_one_trade_per_session | 754.70 | 386.50 | 128.59 | 108 | 75 | 27 | 108 | 75 | 27 | -626.11 | -257.91 |
| diversifier_only_13a_14a_15a | one_trade_at_a_time_chronological | 407.66 | 820.35 | 813.21 | 125 | 129 | 114 | 121 | 97 | 102 | 405.55 | -7.14 |
| diversifier_only_13a_14a_15a | raw_sum_diagnostic | 1762.00 | 797.97 | 1259.11 | 246 | 141 | 154 | 123 | 108 | 102 | -502.89 | 461.14 |

## Portfolio Results

| Set | Mode | Net | Active days | Max DD | Avg corr | Best-day conc | Best-trade conc | Positive folds | Label | Status |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| all_parked_modules_with_13a_14a_15a | one_trade_at_a_time_chronological | -2558.91 | 244 | -7932.55 | 0.214 | 1.000 | 1.000 | 0.333 | portfolio_d_failed_negative | no_portfolio_benefit |
| audit_c_best_plus_phase15a | one_trade_at_a_time_chronological | -2812.61 | 244 | -7144.63 | 0.238 | 1.000 | 1.000 | 0.333 | portfolio_d_failed_negative | no_portfolio_benefit |
| audit_c_best_plus_13a_14a_15a | one_trade_at_a_time_chronological | -2812.61 | 244 | -7144.63 | 0.238 | 1.000 | 1.000 | 0.333 | portfolio_d_failed_negative | no_portfolio_benefit |
| audit_c_best_reconstructed | one_trade_at_a_time_chronological | -3772.54 | 243 | -7476.15 | 0.287 | 1.000 | 1.000 | 0.333 | portfolio_d_failed_negative | no_portfolio_benefit |
| all_parked_modules_with_13a_14a_15a | raw_sum_diagnostic | 33655.02 | 244 | -6484.58 | 0.214 | 0.161 | 0.027 | 0.833 | portfolio_d_positive_but_concentrated | phase15a_reduces_correlation |
| audit_c_best_plus_phase15a | raw_sum_diagnostic | 32943.25 | 244 | -5898.46 | 0.238 | 0.167 | 0.027 | 0.833 | portfolio_d_positive_but_concentrated | phase15a_reduces_correlation |
| audit_c_best_plus_13a_14a_15a | raw_sum_diagnostic | 32943.25 | 244 | -5898.46 | 0.238 | 0.167 | 0.027 | 0.833 | portfolio_d_positive_but_concentrated | phase15a_reduces_correlation |
| audit_c_best_reconstructed | raw_sum_diagnostic | 31684.14 | 243 | -5488.48 | 0.287 | 0.158 | 0.029 | 0.833 | portfolio_d_positive_but_concentrated | portfolio_still_nontradable |
| top_cross_family_plus_13a_14a_15a | raw_sum_diagnostic | 8498.99 | 247 | -2774.83 | 0.116 | 0.117 | 0.107 | 0.667 | portfolio_d_positive_but_concentrated | phase15a_reduces_concentration |
| greedy_low_correlation_with_15a | one_trade_at_a_time_chronological | 8066.61 | 245 | -1643.27 | 0.068 | 0.109 | 0.092 | 0.667 | portfolio_d_positive_but_concentrated | phase15a_reduces_concentration |
| greedy_low_correlation_with_15a | raw_sum_diagnostic | 7468.64 | 245 | -2289.09 | 0.068 | 0.126 | 0.099 | 0.500 | portfolio_d_positive_but_concentrated | phase15a_reduces_concentration |
| rare_setup_plus_15a | raw_sum_diagnostic | 6975.62 | 164 | -2424.68 | 0.193 | 0.332 | 0.130 | 0.667 | portfolio_d_positive_but_concentrated | phase15a_reduces_correlation |
| top_cross_family_plus_13a_14a_15a | one_trade_at_a_time_chronological | 6681.84 | 247 | -1759.09 | 0.116 | 0.212 | 0.136 | 0.667 | portfolio_d_positive_but_concentrated | phase15a_reduces_concentration |
| diversifier_only_13a_14a_15a | raw_sum_diagnostic | 3819.08 | 210 | -3014.63 | 0.167 | 0.244 | 0.163 | 0.667 | portfolio_d_positive_but_concentrated | phase15a_reduces_correlation |
| greedy_low_correlation_with_15a | max_one_trade_per_session | 3708.52 | 245 | -2585.66 | 0.068 | 0.200 | 0.200 | 0.333 | portfolio_d_positive_but_concentrated | phase15a_reduces_concentration |
| rare_setup_plus_15a | max_one_trade_per_session | 3585.01 | 164 | -1194.37 | 0.193 | 0.253 | 0.253 | 0.667 | portfolio_d_positive_but_concentrated | phase15a_reduces_concentration |
| rare_setup_plus_15a | one_trade_at_a_time_chronological | 3256.75 | 164 | -1853.69 | 0.193 | 0.432 | 0.278 | 0.667 | portfolio_d_positive_but_concentrated | phase15a_reduces_concentration |
| top_cross_family_plus_13a_14a_15a | max_one_trade_per_session | 2439.40 | 247 | -1564.49 | 0.116 | 0.254 | 0.254 | 0.500 | portfolio_d_positive_but_concentrated | phase15a_reduces_concentration |
| all_parked_modules_with_13a_14a_15a | max_one_trade_per_session | 2421.26 | 244 | -1518.39 | 0.214 | 0.306 | 0.306 | 0.500 | portfolio_d_positive_but_concentrated | phase15a_reduces_concentration |
| diversifier_only_13a_14a_15a | one_trade_at_a_time_chronological | 2041.22 | 210 | -1735.01 | 0.167 | 0.381 | 0.304 | 0.500 | portfolio_d_positive_but_concentrated | phase15a_reduces_concentration |
| audit_c_best_plus_phase15a | max_one_trade_per_session | 1425.51 | 244 | -1583.20 | 0.238 | 0.407 | 0.407 | 0.500 | portfolio_d_positive_but_concentrated | phase15a_reduces_concentration |
| audit_c_best_plus_13a_14a_15a | max_one_trade_per_session | 1425.51 | 244 | -1583.20 | 0.238 | 0.407 | 0.407 | 0.500 | portfolio_d_positive_but_concentrated | phase15a_reduces_concentration |
| audit_c_best_reconstructed | max_one_trade_per_session | 1348.25 | 243 | -1583.20 | 0.287 | 0.431 | 0.431 | 0.500 | portfolio_d_positive_but_concentrated | portfolio_still_nontradable |
| diversifier_only_13a_14a_15a | max_one_trade_per_session | 1269.79 | 210 | -1173.11 | 0.167 | 0.489 | 0.489 | 0.667 | portfolio_d_positive_but_concentrated | phase15a_reduces_correlation |
| trend_power_only_phase15a | raw_sum_diagnostic | 1259.11 | 102 | -1080.92 | 0.336 | 0.614 | 0.399 | 0.667 | portfolio_d_positive_but_concentrated | portfolio_still_nontradable |
| trend_power_only_phase15a | max_one_trade_per_session | 1135.09 | 102 | -741.38 | 0.336 | 0.442 | 0.442 | 0.667 | portfolio_d_positive_but_concentrated | portfolio_still_nontradable |
| trend_power_only_phase15a | one_trade_at_a_time_chronological | 813.21 | 102 | -876.08 | 0.336 | 0.618 | 0.618 | 0.667 | portfolio_d_positive_but_concentrated | phase15a_reduces_concentration |

## Interpretation

Phase 15A remains research-only. Portfolio Audit D reports diagnostic gate status only; no portfolio is paper-trading approved and no live-trading functionality is added.
