# SET100 strategy comparison — September 29, 2026

All five strategies ran with their original default parameters. No parameters were optimized for these results. The full-period run evaluates January 2017 through September 28, 2026; 2016 is used for indicator warmup. A second run starts afresh in January 2024 and ends September 28, 2026.

**Scope:** 100 equal initial capital allocations using the retrieved current SET100 snapshot. BANPU’s allocation remains cash because its data is quarantined. The other 99 stocks become eligible when their individual history and indicators are available. This is not a historical-membership SET100 simulation.

**Costs and execution:** 0.20% fee plus 0.10% slippage per side, close-generated signals executed at the next available positive-volume open, fractional adjusted units, zero cash interest and no leverage. Open positions remain marked to the final close without an exit fee.

## Full period: 2017–September 2026

| Strategy | Total return | Annualized return | Maximum drawdown | Sharpe (RF=0) | Closed trades | Win rate | Average allocation exposure |
|---|---:|---:|---:|---:|---:|---:|---:|
| SMA trend (50/200) | 62.79% | 5.14% | -20.61% | 0.65 | 609 | 31.53% | 44.69% |
| RSI pullback | 1.19% | 0.12% | -0.80% | 0.33 | 184 | 45.11% | 0.90% |
| Bollinger reversal | -26.65% | -3.14% | -29.44% | -0.46 | 3,893 | 60.44% | 18.72% |
| MACD trend | 0.25% | 0.03% | -16.22% | 0.03 | 5,022 | 28.95% | 18.88% |
| Donchian + volume | 43.22% | 3.76% | -11.20% | 0.64 | 1,315 | 35.82% | 27.06% |
| Buy-and-hold benchmark | 99.61% | 7.36% | -37.98% | 0.52 | 0 | N/A | 89.69% |

[Complete comparison](full_period/comparison.csv) · [Per-stock results](full_period/per_symbol.csv) · [Annual returns](full_period/annual_returns.csv) · [Equity history](full_period/equity.csv) · [Run metadata](full_period/run.json)

## Recent period: 2024–September 2026

| Strategy | Total return | Annualized return | Maximum drawdown | Sharpe (RF=0) | Closed trades | Win rate | Average allocation exposure |
|---|---:|---:|---:|---:|---:|---:|---:|
| SMA trend (50/200) | 15.84% | 5.52% | -10.91% | 0.73 | 173 | 12.14% | 44.73% |
| RSI pullback | -0.17% | -0.06% | -0.72% | -0.15 | 57 | 43.86% | 1.01% |
| Bollinger reversal | -6.75% | -2.52% | -10.66% | -0.46 | 1,166 | 59.61% | 20.19% |
| MACD trend | 3.34% | 1.21% | -6.31% | 0.28 | 1,480 | 30.74% | 20.08% |
| Donchian + volume | 15.19% | 5.31% | -10.04% | 0.77 | 402 | 40.30% | 30.41% |
| Buy-and-hold benchmark | 22.46% | 7.69% | -29.43% | 0.55 | 0 | N/A | 96.50% |

[Complete comparison](recent_period/comparison.csv) · [Per-stock results](recent_period/per_symbol.csv) · [Annual returns](recent_period/annual_returns.csv) · [Equity history](recent_period/equity.csv) · [Run metadata](recent_period/run.json)

## Interpretation

- SMA trend produced the highest total return among the five indicator strategies in both runs. Its full-period maximum drawdown was smaller than the benchmark’s, but its total return was lower.
- Donchian was second among the indicator strategies by total return in both runs. Its full-period drawdown was smaller than SMA’s. These comparisons reflect different market exposure as well as different signals.
- RSI returned little and averaged only about 0.9% of allocations invested in the full-period run. Its small drawdown mainly reflects cash holdings, not demonstrated superior loss control.
- Bollinger reversal lost money after the modeled costs in both periods. MACD was approximately flat over the full period despite more than 5,000 completed trades.
- Buy-and-hold returned more than every indicator strategy in both runs, while experiencing a larger maximum drawdown. The benchmark is this fixed stock basket, not the official capitalization-weighted SET100 index.

Win rate counts closed trades only. Open trades contribute to equity and total return but not win rate. For buy-and-hold, zero completed trades means positions remain open; it does not mean nothing was purchased. Exposure is the average fraction of initial stock allocations holding a position, not a capital-weighted exposure measure. Annualized return is geometric CAGR. Drawdown is the greatest observed peak-to-trough decline. Sharpe uses 252 sessions and a zero risk-free rate.

The recent-period run begins with fresh equal allocations and cash, using earlier bars only for indicators. It is not a simple slice of the full-period equity curve; consequently returns should not be chained to the earlier development run.

## Limitations and evaluation status

The current constituent list introduces survivorship and selection bias. Missing historical members and delistings, short histories, suspension handling, merger adjustments, fractional units and simplified execution constrain the interpretation. Lower drawdowns are not guarantees. No strategy is established as best for future trading by this comparison.

The user requested these runs after the original development comparison. The previously reserved 2024–2026 period has now been evaluated for all five defaults. It must not be described as untouched in subsequent parameter searches. New selection decisions need a new forward evaluation window or a clearly documented walk-forward design.

Validation: both runs exited successfully; each comparison contains six methods, each per-stock report contains 600 rows, all equity values are finite and positive, reported total returns agree with the final equity values, and all 99 input price-file hashes match their run manifests. No strategy or simulator code was changed for these runs.
