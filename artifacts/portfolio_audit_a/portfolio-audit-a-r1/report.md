# Portfolio Audit A — Research Signal Combination / Diversification Audit

Research/simulation only. No live trading, broker adapters, order routing, webhooks, credential storage, automated execution, or LLM-driven trade decisions.

## Summary

- Selected signals: `15`
- Portfolio rows: `24`
- Next action: `keep_registry_and_search_new_uncorrelated_families`
- Rationale: Some combinations improve activity, but concentration/fold gates remain weak.
- Paper trading approved: `false`

## Portfolio Results

| Set | Mode | Net | Active days | Best-day concentration | Positive folds | Label | Status |
| --- | --- | ---: | ---: | ---: | ---: | --- | --- |
| parked_research_signals_all | one_trade_at_a_time_chronological | -1334.29 | 148 | 1.000 | 0.333 | portfolio_audit_failed_negative | no_portfolio_benefit |
| phase10b_only_top_signals | one_trade_at_a_time_chronological | -4942.88 | 109 | 1.000 | 0.333 | portfolio_audit_failed_negative | no_portfolio_benefit |
| phase10b_only_top_signals | raw_sum_diagnostic | 30025.66 | 200 | 0.241 | 0.833 | portfolio_audit_positive_but_concentrated | portfolio_still_nontradable |
| parked_research_signals_all | raw_sum_diagnostic | 17322.91 | 200 | 0.314 | 0.667 | portfolio_audit_positive_but_concentrated | portfolio_still_nontradable |
| rare_setup_research_signals_all | raw_sum_diagnostic | 15075.85 | 200 | 0.168 | 0.833 | portfolio_audit_positive_but_concentrated | diversification_reduces_concentration |
| diversified_low_correlation_top5 | raw_sum_diagnostic | 8724.15 | 200 | 0.104 | 0.833 | portfolio_audit_positive_but_concentrated | diversification_reduces_concentration |
| diversified_cross_family_top6 | raw_sum_diagnostic | 8283.38 | 200 | 0.219 | 0.833 | portfolio_audit_positive_but_concentrated | diversification_reduces_concentration |
| diversified_low_correlation_top5 | one_trade_at_a_time_chronological | 6408.14 | 199 | 0.141 | 0.833 | portfolio_audit_positive_but_concentrated | diversification_reduces_concentration |
| diversified_low_correlation_top5 | max_one_trade_per_session | 5529.25 | 199 | 0.164 | 0.833 | portfolio_audit_positive_but_concentrated | diversification_reduces_concentration |
| top3_cross_family | raw_sum_diagnostic | 5328.24 | 200 | 0.170 | 0.667 | portfolio_audit_positive_but_concentrated | diversification_reduces_concentration |
| top3_cross_family | one_trade_at_a_time_chronological | 5295.96 | 182 | 0.171 | 0.833 | portfolio_audit_positive_but_concentrated | diversification_reduces_concentration |
| top3_cross_family | max_one_trade_per_session | 5129.89 | 182 | 0.177 | 0.833 | portfolio_audit_positive_but_concentrated | diversification_reduces_concentration |
| diversified_cross_family_top6 | max_one_trade_per_session | 5129.89 | 182 | 0.177 | 0.833 | portfolio_audit_positive_but_concentrated | diversification_reduces_concentration |
| diversified_cross_family_top6 | one_trade_at_a_time_chronological | 4309.48 | 182 | 0.210 | 0.667 | portfolio_audit_positive_but_concentrated | diversification_reduces_concentration |
| parked_research_signals_all | max_one_trade_per_session | 3870.62 | 148 | 0.234 | 0.833 | portfolio_audit_positive_but_concentrated | diversification_reduces_concentration |
| rare_setup_research_signals_all | max_one_trade_per_session | 2661.84 | 132 | 0.340 | 0.833 | portfolio_audit_positive_but_concentrated | portfolio_still_nontradable |
| phase10b_only_top_signals | max_one_trade_per_session | 2256.64 | 109 | 0.401 | 0.667 | portfolio_audit_positive_but_concentrated | portfolio_still_nontradable |
| rare_setup_research_signals_all | one_trade_at_a_time_chronological | 2196.40 | 132 | 0.412 | 0.500 | portfolio_audit_positive_but_concentrated | portfolio_still_nontradable |
| phase11a_only_top_signals | raw_sum_diagnostic | 1366.61 | 200 | 0.264 | 0.500 | portfolio_audit_positive_but_concentrated | portfolio_still_nontradable |
| phase11a_only_top_signals | one_trade_at_a_time_chronological | 1366.61 | 98 | 0.264 | 0.667 | portfolio_audit_positive_but_concentrated | portfolio_still_nontradable |
