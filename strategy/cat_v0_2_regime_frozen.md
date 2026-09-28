# CAT v0.2 — Cross-Asset Trend + Market Regime

Frozen before first v0.2 result.

Single structural change from CAT v0.1:

- Crypto LONG entries require completed BTC daily close > BTC EMA200.
- Crypto SHORT entries require completed BTC daily close < BTC EMA200.
- U.S. stock LONG entries require completed SPY RTH daily close > SPY EMA200.
- U.S. stock SHORT entries require completed SPY RTH daily close < SPY EMA200.

The benchmark regime is evaluated on the completed signal day; entry remains the next session/day open.

Everything else is unchanged:
- 2-of-3 sign agreement across 20/60/120-day returns
- symbol EMA200 directional filter
- prior-20-day Donchian breakout on the signal close
- next-session open entry
- 2 ATR initial stop
- 3 ATR trailing stop based only on completed closes
- no fixed TP
- no pyramiding
- one open trade per symbol
- 4 bps fee + 2 bps slippage per fill

Reason:
v0.1 showed positive long expectancy in both asset classes but negative short expectancy in both. v0.2 tests a cross-asset market-regime explanation rather than deleting the short side.
