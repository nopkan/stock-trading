# Thai commission and trading-cost assumptions

Researched September 29, 2026. We use **representative published retail online cash-balance rates**, not a measured market-wide average. Negotiated rates, promotions, monthly memberships, account types and trading tiers differ. A current rate is applied consistently to every historical period for comparability; historical fee changes are not reconstructed.

| Component | Base assumption, per side |
|---|---:|
| Brokerage commission | 0.15000% |
| Exchange trading fee | 0.00500% |
| Clearing fee | 0.00100% |
| Regulatory fee | 0.00100% |
| Subtotal | 0.15700% |
| VAT, 7% of the above fees | 0.01099% of trade value |
| **Total explicit fees** | **0.16799%** |
| Additional modeled slippage | **0.10000%** |

The approximate one-way friction is **0.26799%**; a buy-and-sell round trip at unchanged prices is about **0.536%**, with the exact compounding calculated by the engine. Slippage adjusts the fill price; commissions and the other fees are separately deducted from cash. Slippage is a research assumption, not a broker charge.

[Kasikorn Securities](https://www.kasikornsecurities.com/en/startinvesting/fee/thai-stocks) publishes online cash-balance commission of 0.15% for daily turnover up to THB5 million, with the additional 0.005%, 0.001%, 0.001% fees and 7% VAT. Its page describes a zero-minimum option. This is the basis for the zero-minimum base scenario.

[DBS Vickers Thailand](https://login.settrade.com/brokerpage/004/web/Commission-General.html) also lists 0.15% for online cash-balance trading up to THB5 million daily. Minimum charges depend on account/service conditions; do not assume every broker waives them.

[Bualuang Securities](https://www.bualuang.co.th/article/whychoosebualuangsecurities) publishes 0.157% plus VAT7%, consistent with the same combined fee assumption. Its cited explanatory article is older, so it corroborates the representative level rather than establishing a new personalized quote.

## Higher-cost scenario

The stress test uses 0.25% commission, the same 0.007% additional charges, 7% VAT, **0.20% slippage per side**, and a **THB50 daily minimum commission before VAT**. The explicit percentage fee is 0.27499%; approximate one-way friction is 0.47499%, before any minimum top-up.

Starting capital is THB1 million. The minimum is applied to aggregate daily commission, not independently to each fill, and applies only on a trading day. Higher-tier discounts are not assumed when capital grows, which is conservative. Baseline and candidates pay their own actual modeled transaction costs using the same schedule. A buy-and-hold strategy naturally pays fewer fees.

These assumptions model a funded cash-balance account. Cash-account ATS charges, margin interest, subscription fees, dividend withholding, personal taxes, board lots, tick-size rounding and actual order-book impact are not included. The engine trades fractional adjusted units. See `configs/thai_trading_costs.json` for editable parameters and source URLs.
