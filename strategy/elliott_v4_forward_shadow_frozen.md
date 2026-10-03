# Elliott v4 Forward Shadow Monitor

Purpose: collect pristine forward evidence for Elliott v4 without placing any order or allocating any live risk.

## Frozen trading logic
- US RTH 1H, LONG only.
- Exact Elliott v3/v4 structure: confirmed five-wave impulse + ABC correction, B-wave high breakout after C confirmation.
- Same ATR ZigZag, SL, TP1, TP2, 12-signal-bar entry validity, 48-signal-bar max hold.
- 15m RTH execution replay, conservative stop-first convention.
- Same research costs: 4 bp fee + 2 bp slippage per fill.

## Forward-only rule
The first run is bootstrap only:
- Existing historical signals are registered as already seen.
- No historical trade result is inserted into forward performance.
- Only signals with activation after the monitor's started_ms can enter the shadow journal.

## Safety / live-order isolation
- This script contains no brokerage/Binance order API.
- It does not import or invoke Stock Track B-E execution code.
- Mode is explicitly SHADOW_ONLY_NO_ORDERS.
- Track B-E production behavior is unchanged.

## Universe
All existing Stock53 monitored tickers are observed.
Forward validation summary excludes ETFs/leveraged products and obvious crypto proxies; they may remain visible for research but do not count toward Elliott validation metrics.

## Data
Yahoo Finance 15m chart data, regular session only, 60-day rolling fetch.
The monitor replays the frozen strategy over recent tape and persists only forward events/state.
