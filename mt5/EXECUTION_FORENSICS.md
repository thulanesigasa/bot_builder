# MT5 V4 execution tracing: 2–4 January 2026

This change is **diagnostics-only**: no adjustments to entry criteria, sizing, broker rules, theoretical accounting, or first-quote stop exit. It does not submit any live/demo orders.

## Observed regression case

From the user's Deriv MT5 journal for `XAUUSD`:

| Variant | Entered | Stopped | Entry stop-risk estimate | Quote-marked P&L | Virtual end balance |
|---|---|---|---:|---:|---:|
| ADAPTIVE | 2026-01-02 20:35 | 2026-01-04 23:05 | $34.8782 | -$87.42 | -$37.42 |
| THEORETICAL | 2026-01-02 20:35 | 2026-01-04 23:05 | $81.3825 | -$203.98 | -$153.98 |

The first available stop-crossing quote on Sunday was worse than the stop budget implied by the Friday entry. The log by itself does **not** prove the cause was only spread widening, broker slippage, a genuine quote gap, or a simulation defect.

## Trace added

For each virtual stop exit, the journal now emits an `EXECUTION_TRACE` record **immediately before** `CLOSE` containing:

- original entry price and intended stop price
- first sampled stop-crossing quote
- intended-stop P&L versus first-quote P&L
- dollar loss overshoot versus the intended stop
- stop-risk estimate saved at entry
- virtual entry time, latest prior non-exit tick time and stop-crossing time
- seconds since the latest prior non-exit tick

This is forensic evidence for the next replay. It should be interpreted carefully: MT5's `OnTick` event stream and historical mode determine how many quotes can be observed. The EA still does not simulate a broker stop-out at margin levels or impose a guaranteed floor on negative balance.

## Repeatable targeted test

`pytest -q tests/test_xauusd_stop_forensics.py` checks the factual arithmetic of the Jan 2/4 failure and inspects source-level instrumentation/no-order constraints. It is **not** an executable MT5 tick replay or native MQL5 compilation. The user must compile in MetaEditor (F7) and rerun the same gold symbol in MT5 to obtain the new `EXECUTION_TRACE` entries.

## Next decisions after trace evidence

If the time-gap is weekend-sized, a separate proposal can test weekend flat-by-close policy, while maintaining a control variant to avoid lookahead. If the gap is short and quote overshoot remains large, inspect spread and bid/ask history plus assumed executable fills. Reconcile the virtual risk locks separately from broker margin/stop-out; no profitability claim is justified from these runs.
