# Original buffered momentum: capital sizing diagnostic

Analysis date: 2026-09-29. Recipe e9a522bb24938501; historical fractional-unit return +304.77%, maximum drawdown -14.50%. This is a sizing calculation, not a new performance backtest or live allocation instruction.

## Latest saved basket

Frozen targets dated 2026-09-15, valued using saved closing quotes dated 2026-09-28. Fifteen target positions at 0.95 / 15 = 6.333333% each. Assumes 100 shares per lot and purchase friction factor 1.0026799 (base fees plus 10 bps slippage). Round each sleeve down independently; no redistribution of unused cash. Auction gaps and cash reservation can increase funding needs.

| Account THB | Target positions affordable | Value invested / account | Target exposure |
|---:|---:|---:|---:|
| 30,000 | 7 / 15 | 37.52% | 95% |
| 100,000 | 11 / 15 | 60.44% | 95% |
| 150,000 | 14 / 15 | 77.20% | 95% |
| 200,000 | 15 / 15 | 80.11% | 95% |
| 300,000 | 15 / 15 | 84.63% | 95% |
| 500,000 | 15 / 15 | 88.48% | 95% |
| 1,000,000 | 15 / 15 | 92.15% | 95% |

Largest minimum sleeve: KKP, saved close THB114, one 100-share lot THB11,400. Required account = 11,400 * 1.0026799 / (0.95/15) = THB180,482.38. Approximately THB200,000 affords one lot of each latest target within its sleeve, but does not closely reproduce equal weights. This is not a minimum that remains sufficient for future baskets.

## Historical conditional diagnostic

Use research.small_capital.LotData to reverse future provider split adjustments; corporate actions and historical lot-size exceptions remain unverified. At each original decision date, scale the frozen fractional backtest equity curve by hypothetical initial capital and floor target shares to 100-share lots. This assumes the idealized historical equity curve and does NOT simulate actual lot-constrained returns.

Across 1,138 positive target slots, hypothetical initial THB500,000 leaves 6 slots unaffordable; THB1,000,000 leaves none. At THB1,000,000, median aggregate allocation shortfall on active decisions is 2.48 percentage points, maximum 6.07 points. These statistics cannot establish the realized outcome of funding a real account with either amount.

## Interpretation

THB500,000–1,000,000 is a useful research/planning range for this 15-stock design; THB1,000,000 offers materially closer lot sizing in the saved baskets. It is not an investment recommendation or a promise to repeat the return. The original simulator started with THB1,000,000 but permitted fractional adjusted units. A complete whole-lot, capital-specific execution backtest is needed before estimating returns for a funded account. Historical membership bias, selected-on-history parameters, unverified corporate actions, and missing afternoon auction observations are unaffected by adding capital. +304.77% is cumulative over 2017-01-04 through 2026-09-28, not annual.

## Sources and inputs

- SET trading units: https://www.set.or.th/en/market/information/trading-procedure/trading-units — usually 100 shares, with a 50-share exception after a security has remained THB500 or above for six consecutive months. This diagnostic conservatively assumes 100 throughout; it does not infer eligibility from price alone.
- reports/momentum_reserve_20260929/reproduction_buffer5/experimental_buffered_momentum_targets.csv
- reports/momentum_reserve_20260929/e9a522bb24938501/full_base_equity.csv
- data/prices/*.csv
- configs/thai_trading_costs.json

Formula: lots = floor(account * target_weight / (100 * saved_price * 1.0026799)); invested value = sum(lots * 100 * saved_price). This snapshot calculation does not credit existing holdings, sales proceeds, or dividends.
