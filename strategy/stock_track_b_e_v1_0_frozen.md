# Stock Track B-E v1.0 — Frozen Candidate

Status: promoted after long-horizon research + independent-universe OOS validation.
Do not modify these rules without creating a new version.

## Market / execution architecture
- Signal source: US equity RTH price/volume structure
- Session used for setup and entry: official US RTH only
- Live execution may be routed to the corresponding supported stock-futures instrument, while the signal remains based on the underlying RTH equity chart.
- LONG only in v1.0.

## Base setup
Use TRACK_B_V1_0_FROZEN Wyckoff setup logic unchanged:
- local 4H trading range
- Spring penetration / reclaim
- low-spread, low-volume Test
- exact-touch trigger
- existing structural Entry / SL / TP1 / TP2 definitions
- conservative STOP-first same-15m-bar ordering

## Stock-specific pre-entry filter E
Use only prior completed RTH daily bars.

### 1. SPY bull regime
At least 2 of 3:
- SPY close > EMA50
- SPY EMA20 > EMA50
- SPY 20-session return > 0

### 2. Relative strength
- stock 20-session return >= SPY 20-session return

### 3. Market breadth
- >= 50% of the available monitored equity universe closes above EMA50

All three filters are required.

## Management — frozen
- TP1: 15% of initial position
- after TP1: move remaining stop to break-even
- TP2: 25% of initial position
- after TP2: move remaining stop to TP1
- Runner: 60%
- runner stop: existing confirmed RTH 4H three-bar pivot trailing stop +/- 0.30 ATR

## Costs used in validation
- fee: 4 bps per fill
- slippage: 2 bps per fill
- reference risk: $400/trade
- reference capital: $20,000

## Research evidence

### Current-53 research universe, 2006-04 to 2026-04
Stock-specific E filter, 15/25/60 management:
- 325 trades
- net +80.8395R
- avg +0.2487R
- PF 1.5780
- max DD 14.2947% on fixed-$20k / $400-risk reference
- max losing streak 6

Original current-53 unfiltered Track B baseline:
- 816 trades
- +41.8149R
- PF 1.1096
- max DD 53.1675%

Thus market regime + relative strength + breadth are essential parts of the stock strategy.

### Independent Dow2000 frozen-universe OOS, 2000-01 to 2026-01
Universe: DJIA constituents frozen at 2000-01.
Same E concept and same 15/25/60 management; no OOS parameter tuning.
- 303 trades
- win rate 68.32%
- net +99.2129R
- avg +0.3274R
- PF 2.0386
- max DD 11.2515% on fixed-$20k / $400-risk reference
- max DD about 5.63R
- max losing streak 6
- all six pre-registered major time blocks positive

OOS blocks:
- 2000-2005: +7.9186R, PF 1.6339
- 2005-2010: +14.8236R, PF 1.5828
- 2010-2015: +23.1654R, PF 2.4438
- 2015-2020: +17.3501R, PF 1.5978
- 2020-2024: +23.8566R, PF 3.8675
- 2024-2026: +12.0985R, PF 3.8735

Pre-registered Dow2000 OOS survival criteria all passed:
- net R > 0
- PF > 1.30
- max DD < 25R
- >=4/6 major blocks positive (observed 6/6)

## Known limitations
- Dow2000 membership is frozen at 2000-01 rather than historically reconstituted through time.
- Historical ticker continuity around mergers, reorganizations and delistings can be imperfect.
- The current-53 research universe has survivorship/post-selection bias.
- Filter E is applied to completed Track-B trade candidates in the historical research pipeline; future engine versions should integrate eligibility before order creation and verify parity.
- Historical performance is not a guarantee of future profitability.
