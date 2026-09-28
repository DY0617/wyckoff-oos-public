# LDFR v1.0 Structural Liquidity — Discovery Freeze

This is a root redesign after v0.2 failed cross-symbol robustness. It is **not** a parameter-tuned v0.3.

## Thesis

The earlier prototype treated every 20-bar extreme as liquidity. That generated thousands of noisy "sweeps." v1.0 instead requires a still-intact, objectively confirmed swing-liquidity level and a market-structure shift before an FVG retest can be traded.

## Frozen discovery rules

- Universe: BTC, ETH, BNB, SOL, XRP, ADA, DOGE, LINK USDT-M perpetuals.
- Regime: same closed-4H EMA20/EMA50 regime used in v0.x.
- Entry timeframe: closed 1H candles.
- Liquidity:
  - 2-left / 2-right confirmed swing.
  - most recent intact swing within 72 bars.
  - no revisit of that swing level before the sweep.
- Sweep:
  - penetrate swing by 0.05 to 1.00 ATR14,
  - close back through the swept level.
- Displacement within 3 bars:
  - range >= 1.50 ATR14,
  - body/range >= 0.60,
  - directional CLV threshold unchanged,
  - close must break the pre-sweep 5-bar local structure (MSS).
- FVG:
  - minimum 0.15 ATR,
  - may form on displacement bar or next 2 bars.
- Entry:
  - first valid FVG midpoint retest within 8 bars,
  - higher-timeframe regime must still agree,
  - limit entry at FVG midpoint.
- Stop:
  - sweep extreme +/- 0.15 ATR from the sweep bar.
- Management:
  - TP1 1.5R, take 50%, remainder to BE.
  - TP2 3.0R, exit remaining 50%.
- Intrabar ambiguity:
  - with only 1H path information, STOP is assumed before targets on ambiguous candles, including the entry candle.
- Costs:
  - 4 bps fee + 2 bps slippage per fill, charged once per fill.
- One open position per symbol.

## Validation warning

The architecture was designed after inspecting v0.x results on these same eight symbols, so this 8-symbol run is a **discovery/development test, not untouched OOS**. If the result is promising, freeze v1.0 and test it on symbols/markets not used in the redesign.
