# V4 XAUUSD basket feasibility comparison (research-only)

## Why V4 was needed

The uploaded Deriv MT5 tester logs showed that the **standard XAUUSD symbol** accepts a 0.01 lot minimum and 0.01 step. However, the requested initial seven-leg basket had an estimated total stop-loss of approximately $81.38 and margin requirement of approximately $75.74 for a hypothetical $50 account, so the V3 basket was correctly rejected. The micro symbol differs and was not the basis for this V4 scenario.

## What V4 does

The EA now maintains four fully virtual books:

- `BASELINE`: original 0.25% fractional-risk strategy (broker-feasible).
- `RECOVERY_1_5`: original capped negative-progression baseline (broker-feasible).
- `ADAPTIVE`: the requested positive progression with **broker-feasible maximum leg count**; starts from a *requested* seven 0.01-lot positions and clips to the smaller of the available aggregate stop-loss budget and calculated margin capacity. If even one leg fails, it logs `NO_FEASIBLE_LEG` and skips.
- `THEORETICAL`: the same profit-up/loss-down progression without enforcing actual broker minimum volume or margin or the $35 initial stop budget **on entry**. Its positions and P&L are entirely fictional and must **never be described as broker-executable**.

For both adaptive books: initial 7 legs at 0.01; one positive completed basket moves 7→8→9→10 (at stage +3, each leg becomes 0.02); each negative completed basket moves down one stage, eventually to 4→3→1. There is no averaging down or escalating after losses. The theoretical and broker-feasible books can diverge because they close independently and thus may reach different stages.

For the broker-feasible book, lot increments and minimum volumes are checked using MT5 symbol specifications. At each valid signal, the EA uses `OrderCalcMargin` only to **estimate** margin for one leg and clips the number of legs to: desired stage ceiling, margin affordable from the current virtual balance, and aggregate stop-risk above the $15 capital floor. All positions have one common virtual entry/stop/target price; this is an aggregate-basket model, not independent execution of seven separate orders.

The comparison is logged as `XAU_V4_COMPARISON` and paper events as `XAU_RESEARCH|ADAPTIVE|...` and `XAU_RESEARCH|THEORETICAL|...`. For each paper basket, logs include the requested count, accepted count, per-leg volume, estimated stop risk and estimated margin. **No MT5 trades are submitted**; the native MT5 performance chart can remain flat.

## Limitations

- **No Strategy Tester results have been verified for V4.** Passing GitHub Python tests is not an MQL5 compile or an empirical edge.
- The `THEORETICAL` book ignores margin/lot and entry risk feasibility deliberately; its profits and losses are purely illustrative, and cannot be used to claim that seven 0.01-lot XAUUSD positions are viable with $50.
- Even the `ADAPTIVE` clipping estimate omits changing free margin, commissions, swap/financing, broker liquidations, imperfect liquidation fills and cross-position independent execution. On a fast market move, loss can exceed the estimated floor.
- The 70% capital drawdown ceiling is an *aggressive stress case*, not a risk recommendation or guaranteed maximum loss.
- The conservative books remain unchanged, and none of the four has been shown to have positive expectancy.

## Verification steps

1. Compile `mt5/XAUUSD_Hybrid_Research.mq5` with **MetaEditor F7**, fixing any reported errors. The repository CI cannot compile MQL5.
2. MT5 Strategy Tester: `XAUUSD` (not `XAUUSDmicro`), M5, deposit $50, real ticks when available, the same historical period as prior logs.
3. Export the Journal; look for `XAU_DIAG SYMBOL=`, `XAU_V4_COMPARISON`, `OPEN_VIRTUAL_BASKET`, `NO_FEASIBLE_LEG`, `XAU_FINAL`.
4. Compare virtual opened/closed baskets, wins/losses and balances, then implement an equity-curve/drawdown audit with deal-level records before any profitability interpretation.

This is a **paper model only** and has no order-submission code. Existing Deriv synthetic-index research remains unchanged.
