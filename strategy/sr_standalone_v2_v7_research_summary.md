# Horizontal S/R Standalone Research — v2 to v7 Summary

Date: 2026-10-04

This document freezes the outcome of the standalone S/R research sequence. Do not tune these failed versions to make their historical results look positive.

## Common execution

- Binance USDT-M perpetual
- BTCUSDT, ETHUSDT, BNBUSDT, SOLUSDT research universe
- Five-year evaluation window used by the repository
- 15m execution
- Existing 4 bps fee + 2 bps slippage model
- Conservative STOP-first same-bar convention
- No lookahead: only confirmed levels/events available at signal time

## v2 — SR Flip / breakout-retest

Architecture:
- Legacy 4H/1D S/R zones
- Strong 1H breakout
- First retest from new side
- 4H EMA regime
- Fixed-R exits

Result:
- 858 trades
- -54.59R
- avg -0.064R
- PF 0.878
- Long PF 0.978
- Short PF 0.794

Decision: reject.

## v3 — SR Trend Pullback

Architecture:
- 1D + 4H EMA trend agreement
- Pullback into HTF zone
- 1H rejection/reclaim
- Fixed-R exits

Result:
- 72 trades
- -10.47R
- avg -0.145R
- PF 0.738

Decision: reject.

## v4 — SR Sweep Failure / SFP

Architecture:
- Sweep beyond far HTF-zone edge
- Full 1H reclaim
- Wick/CLV confirmation
- Fixed-R exits

Result:
- 26 trades
- -3.06R
- avg -0.118R
- PF 0.790
- ETH and SOL were positive, but BTC/BNB were negative and the total sample was small.

Decision: reject; do not select winning symbols post hoc.

## v5 — SR Range Reversion

Architecture:
- 4H low-efficiency / low-EMA-gap range regime
- Active support/resistance pair
- Boundary rejection
- Mid-range TP1 / opposite-zone TP2

Result:
- Only 1 trade in five years across Core4
- Pair construction was too sparse to evaluate.

Decision: invalid architecture for this zone representation; reject baseline.

## SR Engine v2

Changed the level detector itself:
- 4H/1D body fractals instead of ATR ZigZag
- known-time reaction-strength scoring
- 1D weighting
- clustered body-price levels
- distinct-event and minimum-score requirements

The new engine was then tested in v6 and v7.

## v6 — Scored-Zone Reaction

Architecture:
- SR Engine v2
- 1H penetration/reclaim of scored HTF zone
- Fixed-R exits

Result:
- 522 trades
- -92.75R
- avg -0.178R
- PF 0.697

Decision: reject. Better level scoring did not rescue reaction trading.

## v7 — SR Momentum Breakout

Architecture:
- SR Engine v2
- 1D + 4H trend agreement
- 1H breakout body >=0.80 ATR
- volume >=1.30x SMA20
- strong CLV
- fixed-R exits

Result:
- 365 trades
- -53.00R
- avg -0.145R
- PF 0.737
- SOL approximately breakeven; remaining Core4 negative.

Decision: reject.

## Research conclusion

Across materially different architectures, horizontal support/resistance did not demonstrate robust standalone alpha under the repository's conservative execution assumptions.

Tested and rejected:
1. direct reaction/reclaim
2. breakout + retest
3. trend pullback to S/R
4. failed breakout / liquidity sweep
5. range mean reversion
6. reaction to reaction-scored body levels
7. trend + volume momentum breakout through scored levels

This is stronger evidence than a single failed parameter set. Continuing to tune thresholds inside these same architectures would materially increase overfitting risk.

## Next research direction

For a new standalone strategy, make the primary signal independent of horizontal S/R:

1. classify market state (trend / compression / expansion / transition);
2. detect a structural state change using price and volatility;
3. require directional momentum / participation confirmation;
4. use S/R only as spatial context for entry quality, invalidation, or target placement;
5. freeze the architecture before Core4 results;
6. if promising, immediately test unseen-symbol and time OOS.

Existing Track B remains unchanged.
