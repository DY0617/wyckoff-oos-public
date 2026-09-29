# US Stocks Track-B E 15/25/60 — Dow2000 OOS v1

Frozen before results are inspected.

## Purpose
Independent-universe validation of the stock-specific Track-B E strategy and the selected 15/25/60 management.

## OOS universe
DJIA constituents frozen at 2000-01:
MMM, AA, MO, AXP, BA, CAT, C, KO, DD, EK, XOM, GE, GM, HPQ,
HD, HON, INTC, IBM, IP, JNJ, JPM, MCD, MRK, MSFT, PG, SBC, UTX,
WMT, DIS, T.

This reduces survivorship bias versus the current 53-stock research universe.
SPY is used only as the market-regime benchmark, not as a traded constituent.

## Signal
Existing frozen Track-B exact-touch signal logic.
- LONG only
- US RTH structure and entry only
- one position per symbol
- conservative STOP-first same-bar handling

## Stock filter E
At entry, using only prior completed RTH daily bars:
1. SPY bull regime = at least 2 of 3:
   - SPY close > EMA50
   - SPY EMA20 > EMA50
   - SPY 20-session return > 0
2. Stock 20-session return >= SPY 20-session return
3. Breadth >= 50% of available Dow2000 universe closes above EMA50

## Management
- TP1 15% -> remaining stop to break-even
- TP2 25% -> remaining stop to TP1
- Runner 60% -> existing confirmed RTH 4H pivot trailing stop +/- 0.30 ATR

Entry, initial SL, TP1, TP2 and runner logic are unchanged.

## Data / period
- Historical US RTH 1-minute data -> 15m / 4H / daily
- Evaluation: 2000-01-01 through 2026-01-01
- Fee 4 bps + slippage 2 bps per fill
- Fixed reference capital $20,000
- Fixed risk $400/trade

## Pre-registered survival criteria
- combined net R > 0
- combined PF > 1.30
- max drawdown < 25R
- at least 4 of the 6 major time blocks positive:
  2000-2005, 2005-2010, 2010-2015, 2015-2020, 2020-2024, 2024-2026

No post-result parameter tuning is allowed inside this OOS version.
