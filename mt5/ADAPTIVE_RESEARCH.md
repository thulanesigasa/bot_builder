# Adaptive anti-martingale research variant (V3)

This is **virtual-only**, not a trade-submitting Expert Advisor. The existing `mt5/XAUUSD_Hybrid_Research.mq5` now simulates **three** independent books receiving the same entry signals: fixed-fraction BASELINE, prior RECOVERY_1_5, and ADAPTIVE.

The ADAPTIVE variant is a **high-risk stress case** starting from hypothetical $50, not a recommendation for a live $50 gold account.

| Closed-cycle stage | Next virtual positions | Lot per virtual leg | Aggregate volume |
|---|---:|---:|---:|
| -3 | 1 | 0.01 | 0.01 |
| -2 | 3 | 0.01 | 0.03 |
| -1 | 4 | 0.01 | 0.04 |
| 0 (initial) | 7 | 0.01 | 0.07 |
| +1 | 8 | 0.01 | 0.08 |
| +2 | 9 | 0.01 | 0.09 |
| +3 | 10 | 0.02 | 0.20 |

The stage moves **exactly one step only when a whole virtual basket closes**. Positive net basket P&L raises the stage by one, negative lowers it by one; breakeven leaves stage unchanged. The stage does not increase because a component position is temporarily profitable. Each virtual basket is internally represented as **one aggregate book position** sharing one entry/stop/target; it is not a simulation of independently timed entry orders.

## Research risk boundary

- ADAPTIVE checks the sum of all virtual legs' stop-loss estimates against the equity above a **$15 virtual balance floor**, i.e. an illustrative **70% loss budget from the initial $50**. This is not a guaranteed fill-loss cap.
- Virtual initial entry uses the broker's **minimum 0.01 lot assumption**, but independently verifies `SYMBOL_VOLUME_MIN`, `SYMBOL_VOLUME_STEP`, stop and tick values.
- MT5 `OrderCalcMargin` is used **only to estimate margin**; it does not open positions. The basket is rejected if estimated required margin exceeds the virtual equity or aggregate stop estimate breaches the virtual floor.
- The original baseline/recovery books retain their stricter risk limits. No live/demo trading, `OrderSend` or `CTrade` was added.
- The ADAPTIVE stress-book applies its own $15 floor instead of the baseline's 2%-daily/10%-total locks so that a separate aggressive risk scenario can be observed. It remains unsuitable for live money and could lose the full deposit with real fills/gaps/margin changes.
- In real markets, seven legs might suffer correlated loss simultaneously. The `0.20` volume at stage +3 is particularly hazardous for a small account.

## Validation and interpretation

Build in **MetaEditor using F7**; the repository's Python regression suite cannot compile MQL5. Use the MT5 Strategy Tester on the actual **Deriv XAUUSDmicro** symbol with tick data. Find `XAU_ADAPTIVE_SUMMARY`, `XAU_RESEARCH|ADAPTIVE|OPEN_VIRTUAL_BASKET`, `XAU_RESEARCH|ADAPTIVE|SKIP`, and `XAU_RESEARCH|ADAPTIVE|STAGE`. If the margin estimator blocks all positions, report that finding rather than weakening the cap.

Be cautious comparing the variants: different volume policy and capital preservation thresholds imply different risk budgets. Simple final balances alone cannot establish superiority; measure drawdown, unclosed positions, financing, realistic broker costs, return distribution and out-of-sample performance. At present the adaptive basket has **no commissions/swap model**, partial fills or stop-out simulation. No proven positive expectancy is claimed.

The accompanying `research/xauusd_adaptive_progression.py` is a separately testable Python version of the stage policy, not a connection to MT5. Its `evaluate_basket` is an independent sanity-check risk/margin calculator.

**Status: implementation awaiting native MQL5 compilation and actual MT5 tick-run review.**
