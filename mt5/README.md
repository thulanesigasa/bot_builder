# XAUUSD Hybrid Research EA — Deriv MT5

**Status:** Original MQL5 source implemented; Python static-safety validation included. **MQL5 compilation and MT5 Strategy Tester performance are NOT yet verified.** This is a research-only, non-order-submitting Expert Advisor, not an automated trading product.

## What it does

File: `mt5/XAUUSD_Hybrid_Research.mq5`.

- Runs only when the MT5 chart symbol contains `XAUUSD` or `GOLD` (to tolerate broker suffixes).
- H1: EMA 50 versus EMA 200 determines higher-timeframe trend.
- M15: EMA 20 proximity, RSI 14 direction/overbought-oversold bounds, ATR 14 volatility/stop distance.
- M5: closed bullish/bearish candle and close-versus-previous-close confirmation.
- Signals evaluated only at the first tick of a **new M5 bar**. All indicators read the last **closed** bar, not the forming bar.
- Two independent, virtual USD 50 accounts receive the identical signal: **BASELINE** (fixed 0.25% virtual equity risk) and **RECOVERY_1_5** (same base risk increased by 1.5^loss streak, max 3 increments). No averaging down into a live position, no broker orders, no CTrade or OrderSend.
- Virtual fills use the ask to open a simulated BUY/bid for SELL; exits evaluate the executable bid/ask side. For missing prices/contract specs, entry is rejected.
- Broker volume parameters, tick size and tick value are consulted, and lots are **rounded down** to allowed steps; if even the minimum lot exceeds the allowed risk budget, the signal is logged as `LOT_INFEASIBLE` rather than forced into an oversized trade.
- Virtual stop and take-profit default to 1.5 ATR and 1.5R respectively. Broker minimum stops distance is considered. Stop execution can occur beyond stop price on a fast tick (slippage).
- Virtual lockout thresholds: 2% daily balance decrease against day-opening balance, 10% from initial balance. Neither is guaranteed protection against slippage.
- Recovery progression resets on a profitable close or after reaching the fourth sequential loss; it never increases the number of concurrently held positions.
- Optional `InpJournalToCommonFiles` CSV export to terminal common files, plus terminal logs and an end-of-run win/loss/balance summary. Treat statistics as **virtual-only**.

## $50 account caveat

A hypothetical 0.25% base risk is **$0.125 per trade**. Most standard gold lot/stop-distance combinations may be too large, so the EA will appropriately skip many/all signals for a $50 balance. A larger virtual deposit should **not** be silently substituted without changing and rerunning the research protocol. The present version intentionally refuses `InpHypotheticalUSD != 50.0`.

Gold tick values, contract sizes, volume constraints, spreads, swaps and allowed stops are broker-specific; inspect Deriv MT5 Market Watch > Specification for the **exact account type and symbol**. Check with `SYMBOL_VOLUME_MIN`, `SYMBOL_VOLUME_STEP`, `SYMBOL_VOLUME_MAX`, `SYMBOL_TRADE_TICK_SIZE`, `SYMBOL_TRADE_TICK_VALUE` at runtime.

## How to test without trading

1. On Windows open MetaEditor from the **Deriv MT5 desktop terminal**; create an Expert Advisor file named `XAUUSD_Hybrid_Research.mq5` and paste the full repository source under `MQL5/Experts/`.
2. **Compile using F7 in MetaEditor**; record compiler errors/warnings and fix them before accepting any results. This repository environment cannot compile MQL5, so no successful MQL5 binary claim is made.
3. Open Strategy Tester and select the EA, the actual gold symbol in your Deriv account, a historical period with multiple gold regimes and **Every tick based on real ticks** where supported. The EA does not submit orders; inspect its virtual logs/CSV. Tester native performance charts may remain flat since the EA has no positions.
4. Capture a verifiable CSV and compare the BASELINE and RECOVERY_1_5 virtual balance and loss metrics. This version's logs provide counts and balances; a later analytics phase can add formal equity curves, drawdown trajectories, spread/slippage stress tests, out-of-sample selection and independent confirmation.
5. Test both low-liquidity/high-spread periods and high-volatility gold regimes, including gap/slippage scenarios. Check whether **either** variant can place a virtual position at the broker's minimum lot without violating 0.25% budget.
6. Do **not** enable AutoTrading or use this as a real-money strategy. There is deliberately no purchase path. Independent live or demo execution would require an entirely separate design review and user authorization.

## Risk comparison and validity

The two virtual books begin at $50, see exactly the same signals, and use different volume progression after losses. The baseline's lot sizing also adjusts as balance changes; it is *fixed fractional risk* rather than constant lots. A recovery multiplier increases dollar risk and does not improve a negative edge; quote friction and trading costs can worsen losses. Realistic commissions, swap/financing, margin availability, news slippage, position liquidity, and execution rejection are **not fully modelled** in this initial implementation. Win rates, drawdowns and return estimates require actual MT5 data and an independently fixed test protocol; no results are asserted here.

The repository's existing synthetic-index SHADOW validation and the incomplete eight-window October study are unchanged. **NO_VALIDATED_POSITIVE_EV_EDGE** remains the research verdict.

Technical reference: [MQL5 CopyBuffer documentation](https://www.mql5.com/en/docs/series/copybuffer), [MT5 symbol specification](https://www.metatrader5.com/en/terminal/help/trading/market_watch).
