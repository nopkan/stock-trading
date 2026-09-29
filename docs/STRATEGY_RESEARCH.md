# Original five indicator strategies — historical research record

Status: these original five modules were rejected and removed from the active strategy folder after their definitions/results were archived. See [the new retained strategies](../reports/strategy_search_20260929_v2/RESULTS.md) and [the full strategy ledger](../research/experiments/STRATEGY_LEDGER.md). The remainder of this document preserves the original research rationale.

Research date: September 29, 2026. These are testable starting hypotheses, not established profitable systems. All implementations are daily, long-only and unlevered. Calculate signals after the close; submit hypothetical trades at the next observed tradable open. Parameters below are fixed starting values, not optimized results.

Evaluation update: at the user's request, all five defaults have now been run over 2017–September 2026 and separately over 2024–September 2026. See [results](../reports/strategy_comparison_20260929/RESULTS.md). The previously reserved 2024–2026 period is no longer untouched; any subsequent parameter selection must account for this.

| Strategy / Python module | Entry / holding rule | Exit rule | Why test it in Thailand? | Main weakness |
|---|---|---|---|---|
| SMA trend — `sma_trend.py` | Hold when SMA(50) > SMA(200); first eligible bullish state can enter | SMA(50) ≤ SMA(200) | Simple low-turnover baseline; Thai studies have examined moving-average trading | Lags turns and whipsaws in sideways markets |
| RSI pullback — `rsi_pullback.py` | RSI(14) < 30 and close > SMA(200) | RSI ≥ 55, close < SMA(200), or 20 signal bars held | Tests buying weakness within an uptrend; Thai crisis research suggests RSI performance depends on regime | Few qualifying trades; oversold can persist |
| Bollinger reversal — `bollinger_reversion.py` | Yesterday close below its lower band; today close recovers to or above its lower band; 20-day mean ± 2 population standard deviations | Close ≥ middle band, or 20 signal bars held | A Thai SET50 study reported encouraging bottom-reversal results | Persistent downtrends, gap losses and frequent trading costs |
| MACD trend — `macd_trend.py` | Hold when MACD(12,26) > signal EMA(9), MACD > 0, and close > SMA(200) | Any holding condition fails | Widely taught by SET; provides a faster momentum/trend comparison | Correlated with SMA, higher turnover and false signals |
| Donchian + volume — `donchian_breakout.py` | Close > highest high of the **previous** 55 bars and volume > 1.5 × previous 20-bar mean volume | Close < lowest low of previous 20 bars | A transparent breakout hypothesis with volume confirmation | False breakouts, large opening gaps; direct Thai evidence for this exact rule has not been established here |

Time exits are generated at a close and executed later; they are not intraday stop orders. Entry and exit conditions conflicting at one close resolve to exit. No fixed loss stop is included in these baseline rules. Adding one is a separate experiment and needs explicit gap-fill assumptions.

## What the research actually establishes

Chaysiri, Jeenanunta and Senanayake Ihala Gamage (2020) studied moving averages, CCI and Bollinger rules on **19 stocks continuously listed in SET50 during 2007–2017**. They report favorable Bollinger bottom-reversal and CCI results across their defined asset conditions, and conditional moving-average performance. That selected sample, older period and different rule specifications do not validate our exact implementations or the full SET100 universe. [Original research](https://so01.tci-thaijo.org/index.php/buacademicreview/article/view/240412).

Boonpong and Vajiramedhin (2023) examined RSI and SMA during Thai market crises. Their abstract reports changing effectiveness across crises, including reduced SMA and improved RSI effectiveness during COVID-19. This motivates testing separate market periods, not assuming a permanent edge. [Original research](https://so05.tci-thaijo.org/index.php/RMUTI_SS/article/view/262231).

SET's technical-analysis course covers moving averages, MACD, RSI, volume and OBV. This supports their relevance as familiar indicator families, not a profitability claim. [SET course](https://elearning.set.or.th/SETGroup/courses/375/info?pid=2).

Donchian channels use trailing high/low extremes. The breakout implementation shifts those thresholds by one bar so the current high is never used as a threshold it must exceed. Our volume multiplier and 55/20 windows are experiment choices. [Trading Technologies indicator documentation](https://library.tradingtechnologies.com/trade/analytics/charts/technical-indicators/donchian-channel/).

## How to choose a strategy gradually

1. Keep the downloaded dataset and versioned parameters fixed for the initial comparison. Inspect data gaps and problematic symbols before interpreting returns.
2. Use 2017–2023 for development, retaining earlier data for indicator warmup. Within development, use chronological folds: train 2017–2019 / validate 2020; train 2018–2020 / validate 2021; train 2019–2021 / validate 2022; train 2020–2022 / validate 2023. The runner's `--start` / `--end` options define each evaluation window; parameter selection is manual.
3. Start with a small, declared parameter grid. Examples: SMA 20/100, 50/150, 50/200; RSI entry 25/30/35; Bollinger width 1.5/2/2.5; Donchian lookback 20/55/100. Keep a record of every trial, including failures. A broad search can discover noise.
4. Compare net CAGR, maximum drawdown, Sharpe, exposure, completed trades and turnover. Inspect individual-stock results: a portfolio result can be dominated by a few winners. Win rate alone is not enough.
5. Repeat promising rules with higher fees and slippage. The supplied default is **20 bps fee + 10 bps slippage per side**; these are configurable research assumptions, not a quote of current broker charges. Cash earns zero and Sharpe uses zero risk-free rate.
6. Freeze a candidate before evaluating a new forward period. The original reserved 2024–September 2026 period has now been evaluated at the user's request; it is no longer untouched. Repeatedly choosing parameters after seeing a period turns it into development data. Today’s constituent selection still leaks later information even when price periods are held out; fix historical membership before treating a result as investment evidence.
7. For a live-trading project, next add historical eligibility, corporate-action reconciliation, realistic THB portfolio sizing, a licensed/broker data feed and paper execution. Connect a broker only after those stages.

## Thai execution considerations

SET describes a normal board lot of 100 shares, with a 50-share exception for securities meeting its high-price condition. Tick size varies by price band, and price limits and trading halts affect fills. The present adjusted-unit simulator does not reproduce these mechanics; costs approximate friction only. [SET trading units and price rules](https://www.set.or.th/en/trading-units-tick-sizes-price-limits).

Short selling, margin, borrow availability, settlement, order queuing, minimum commissions, taxes specific to an account, dividend withholding, partial fills and market impact are outside this first research engine. Consequently, a backtest result is not a deployable broker order plan.
