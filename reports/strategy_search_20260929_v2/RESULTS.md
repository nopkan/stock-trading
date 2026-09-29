# Five retained SET100 research strategies

**276 new portfolio configurations tested across 12 rule families; all five original failed rules also recorded. Five retained after chronological, higher-cost and sensitivity checks.** These are retrospective fixed-membership backtest outperformers, not proof of future market-beating performance.

Evaluation: January 4, 2017–September 28, 2026. Starting capital: THB1,000,000. All reported returns are after the modeled fees and slippage. Explicit fees are 0.16799% per side; slippage is 0.10%. The benchmark uses the same fee schedule. BANPU stays cash.

| Strategy | Net total return | CAGR | Max drawdown | 2024–Sep 2026 total return | Higher-cost full CAGR |
|---|---:|---:|---:|---:|---:|
| Multi-horizon momentum | 262.29% | 14.14% | -14.79% | 54.19% | 12.69% |
| Volume-flow leaders | 203.91% | 12.10% | -16.99% | 51.26% | 10.90% |
| Consistent trend | 216.36% | 12.57% | -17.36% | 32.49% | 11.22% |
| Downside-adjusted momentum | 227.02% | 12.95% | -15.01% | 61.66% | 11.72% |
| Six-month high leaders | 182.68% | 11.27% | -15.82% | 29.37% | 10.38% |
| **Buy-and-hold benchmark** | **99.67%** | **7.37%** | **-37.98%** | **22.50%** | **7.34%** |

![Equity and drawdown](equity_and_drawdown.png)

## Exact retained rules

All five require positive momentum excluding the latest 21 sessions, the stock above SMA200, and the equal-weight market proxy above SMA200. They buy the highest-ranked eligible names. At rebalancing, absent qualifying names leave their slots in cash. Filters are evaluated only at scheduled rebalance closes.

| Module | Ranking | Names | Rebalance interval | ID |
|---|---|---:|---:|---|
| `rank_multi_horizon.py` | Rank mean percentile of skipped-month 3-, 6-, 12-month returns. Lookback: 252 sessions. | 20 | 21 sessions | `f4f96d173a82b60a` |
| `rank_volume_flow.py` | Rank mean signed-volume pressure, require positive trailing return. Lookback: 252 sessions. | 20 | 21 sessions | `8052992d1be308f6` |
| `rank_consistent_trend.py` | Rank trailing proportion of positive sessions multiplied by momentum. Lookback: 126 sessions. | 20 | 21 sessions | `f397049c64b94cab` |
| `rank_downside_momentum.py` | Rank skipped-month return / trailing downside deviation. Lookback: 252 sessions. | 20 | 21 sessions | `bcdf16e650eee927` |
| `rank_high_proximity.py` | Rank closeness to trailing high; require positive trailing return. Lookback: 126 sessions. | 10 | 63 sessions | `48544834d3c5f35b` |

The multi-horizon score combines 63/126/252-session ranks. The downside-adjusted score divides momentum by 63-session downside deviation. Volume flow is trailing signed volume divided by total volume. Consistent trend multiplies momentum by the fraction of positive-return sessions. High proximity ranks close divided by its trailing 126-session maximum.

## What was rejected and why

23 of 276 configurations passed discovery and validation; 19 were locked for later testing. 17 configurations passed the later and full-period base/stress return-and-drawdown checks. The sensitivity audit rejected two of those. Family/return-similarity filtering and the original discovery/validation score selected the final five. Other passing candidates are recorded as not selected, not incorrectly labeled failures.

The initially higher-ranked downside-momentum variant failed an additional-delay/exclusion audit; the retained downside variant has different predeclared parameters. Ordinary momentum variants were near-duplicates of retained trend strategies. The original five single-stock strategy files were deleted from the active folder; their source definitions and results remain in the audit trail.

## Files that prevent repeated experiments

- [Every distinct hypothesis and result](../../research/experiments/STRATEGY_LEDGER.md)
- [Machine-readable strategy ledger](../../research/experiments/STRATEGY_LEDGER.csv)
- [All individual evaluation records](../../research/experiments/all_trials.csv)
- [Predeclared search plan](search_plan.json) and [locked shortlist](locked_shortlist.json)
- [Final retained strategies](retained_strategies.csv), [sensitivity results](sensitivity_results.csv), and [audit dispositions](audit_dispositions.csv)
- [Independent trade-ledger accounting checks](independent_ledger_verification.json)
- [Thai cost sources and calculation](../../docs/THAI_TRADING_COSTS.md)
- [Search protocol and limitations](../../docs/SEARCH_PROTOCOL.md)

## Interpretation and limits

Multi-horizon momentum had the highest full-period return of the retained five. Downside-adjusted momentum had the highest recent-period return. These are not five independent bets: they share equity momentum and trend filters. The maximum pairwise daily-return correlation is below the chosen 0.95 near-duplicate threshold, but correlations remain substantial.

All five exceed their matching benchmark with higher costs, one additional execution session of delay, DELTA excluded, and THAI excluded. This does not resolve survivorship bias, multiple-testing bias, incomplete historical company identities, delayed/stale price marks or the lack of a new untouched holdout. The benchmark is the original equal-initial-allocation basket, not the official capitalization-weighted SET100 index.

The engine uses fractional adjusted units. Board lots, exact opening liquidity, tick-size rounding and a historical suspension feed are not modeled. The daily minimum commission is included in the higher-cost scenario. Portfolio values include open positions at the final close, with no forced final liquidation fee. A paper/live-execution model and historical constituent data remain the next evidence needed before deployment.

Verification: 34 automated tests passed. Independent replays reconstruct all ten retained full-period base/stress equity curves from exported fills, including commission, exchange charges, VAT and stress minimums. The writable-array fix was verified under a separate code context with unchanged selected results. This verification rerun is not counted as new strategy discovery.
