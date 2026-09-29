# Stock Track B-E Cash-Signal -> Binance TradFi Futures Execution v1 — Frozen

Frozen before result inspection.

## Purpose
Test the real deployment architecture, not a new signal strategy:
1. build Track B-E from the underlying US cash equity RTH chart,
2. validate E at the actual cash entry trigger,
3. execute and manage the position on the corresponding Binance USD-M TradFi perpetual.

The futures chart MUST NOT generate its own Wyckoff setup.

## Signal
- TRACK_B_V1_0_FROZEN on underlying cash-equity RTH data
- LONG only
- E filter checked at the actual trigger:
  - SPY bull regime: >=2/3 of close>EMA50, EMA20>EMA50, ret20>0
  - stock ret20 >= SPY ret20
  - >=50% of available stock50 breadth universe above EMA50
- Entry / initial SL / TP1 / TP2 come from the cash setup
- Management allocation: 15% TP1 / 25% TP2 / 60% runner

## Execution domain
- Binance USD-M TradFi perpetual for symbols available in exchangeInfo and in the stock50 research universe
- Cash entry is allowed only during US RTH because the signal engine is RTH-only
- After entry, futures SL / TP / runner stops are active on ALL available futures 15m bars, including outside US RTH

## Basis mapping
At execution, compute basis_ratio = futures_reference_price / cash_reference_price.
Map structural cash levels into the futures price domain:
- futures SL = cash SL * basis_ratio
- futures TP1 = cash TP1 * basis_ratio
- futures TP2 = cash TP2 * basis_ratio

This treats persistent fair-value premium/discount as basis rather than as slippage.

## Execution timing modes
A. SAME_BAR_CLOSE
- cash setup first touches Entry during an RTH 15m bar
- enter futures at the close of the matching futures 15m bar
- basis uses futures close / cash close
- management starts from the next futures 15m bar

B. NEXT_BAR_OPEN
- enter at the next matching RTH 15m bar open
- basis uses futures open / cash open
- management starts in that futures bar
- skip if there is no next same-session cash RTH bar

Both modes are reported; no mode is selected after looking at results.

## Late-entry validity
Skip an execution when, at the execution timestamp:
- mapped initial stop is not below the futures entry, or
- mapped TP1/TP2 is not above the futures entry.

## Runner
After futures TP2:
- cash RTH confirmed 3-bar 4H pivot trail remains the strategy source
- long trail = cash pivot low - 0.30 ATR
- each newly confirmed cash trail is mapped into futures price space using the contemporaneous cash/futures RTH close basis
- trail only tightens
- between cash trail updates, the last mapped futures stop remains active 24h

## Costs / risk
- fee: 4 bps per fill
- slippage: 2 bps per fill
- fixed reference risk: $400 per executed trade
- fixed reference capital: $20,000
- conservative same-15m-bar ordering: STOP first, then TP1, then TP2

## Data window
- recent overlap only, ending 2026-09-29T00:00:00Z (complete sessions through 2026-09-28)
- cash warmup: HF/Finnhub historical RTH data plus recent public 15m cash samples
- E daily state: public daily US equity data; only prior completed sessions
- futures: Binance USD-M TradFi 15m data via the existing export proxy

## Interpretation
This is an execution-domain calibration with a short futures history.
It does NOT replace the 20–26 year cash-equity strategy validation.
Primary outputs are:
- eligible cash signals
- matched futures executions
- execution coverage
- cash benchmark R on matched signals
- futures R by timing mode
- PF / DD / losing streak
- outside-RTH exit share
- divergence in outcome versus the cash benchmark
- basis at entry
