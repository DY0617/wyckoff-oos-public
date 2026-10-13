# A/B/C/D entry comparison v1 — frozen before candidate execution

Primary evaluation is TRAIN 2020–2022 and VALIDATION 2023–2024 only. Candidate retrospective holdout 2025–2026 remains unopened. No parameter search in this version. Futures 4H features, spot daily regime available by execution open, completed bars only. First 200 futures 4H bars are warmup. No volume conditions because source anomalies are unresolved.

All flags are computed on closed 4H bar i; entry occurs at i+1 traded open with adverse 2 bps slippage. Regime must still be true at execution. Long-only, one position, no pyramiding. ATR14 and ADX14 use Wilder smoothing; EMA20/50 use recursive close values with 200-bar warmup.

- A pullback: EMA20 > EMA50; signal low <= EMA20; signal close > EMA20 and > immediately prior bar high. This is a deliberately narrow confirmed pullback definition.
- B breakout/retest: close breaks above prior 20-bar high. Freeze that level, allow retest in the following 6 bars. Retest low <= level + 0.25 ATR, bullish close above level. Cancel if close < level - 0.5 ATR; no same-bar breakout/retest entry. Expire after 6 bars; do not keep replacing the level during a pending retest.
- C sweep/recovery: low below prior 20-bar low, close back above it, bullish close, EMA20 > EMA50 and close > EMA20.
- C simple comparator: low below prior 20-bar low and close back above it, with the same daily regime and shared management. This isolates added recovery filters, not a separately optimized system.
- D volatility breakout: close > prior 20-bar high, ADX14 >= 20, ATR14 > mean of prior 20 ATR observations.

Shared management: initial stop next-open reference price minus 2 × signal ATR14; no fixed TP. After each completed bar, raise stop to max(old stop, highest high since entry - 3 × current ATR14). Stop updates become active only in the next bar. Exit at next open if daily regime false. Gap below stop exits at adverse open, otherwise low touching stop exits at stop minus slippage. Intrabar stop precedes any positive trail changes. If entry and stop occur in the same bar, assume stop reachable after entry, conservatively. Terminal forced liquidation is labeled. Four-hour execution is provisional; 1H or finer validation is mandatory before a live verdict.

Position size: actual initial planned loss (including both entry/stop commissions and adverse fills) <= 0.5% current equity. Cap entry notional after commission at 1x equity. Continuous quantity; historical exchange precision and liquidation tiers are not implemented. Compare 1% risk and doubled execution costs as sensitivities, not selection retuning. Funding uses acquired rates and mark-open proxy, with boundary payment before orders.

No streak/DD filter is tuned in this pass. Freeze entry selection before testing additional exits or safety rules. Required gate for promotion: at least 20 completed validation trades, positive net validation expectancy, PF > 1, MDD < 15% at 0.5% risk, and nonnegative doubled-cost validation expectancy. These are minimum screening conditions, not proof of edge. If none pass, record that no candidate passed; do not optimize thresholds to rescue it. Rank eligible candidates by validation net R per trade, then discuss trade count and uncertainty. 2025+ candidates stay unevaluated until robustness and execution validation are complete.
