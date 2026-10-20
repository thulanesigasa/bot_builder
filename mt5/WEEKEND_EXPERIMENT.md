# Weekend-flat controlled comparison — research only

This is a **controlled experiment**, not a claim that weekend protection solves all losses. The original `ADAPTIVE` virtual strategy remains unchanged. A fifth independent paper book, `WEEKEND_FLAT`, follows the same signal rules, broker-feasible position clipping, and profit-up/loss-down progression as the `ADAPTIVE` book.

## Experimental policy

- The additional `WEEKEND_FLAT` book blocks new virtual entries on Saturday/Sunday and Friday from `InpFridayFlatHourServer` (default **20:00, broker server clock**). The input is validated 0–23.
- Any still-open weekend-policy virtual position is flattened at the **first observed tick at or after the cutoff** on Friday, using the executable bid/ask side. It cannot invent a fill at 20:00 if no quote is available then.
- `ADAPTIVE` serves as unchanged hold-through-weekend control. The `THEORETICAL`, `BASELINE`, and `RECOVERY_1_5` books are unchanged.
- The books trade **no real/demo orders**; there is no `OrderSend` or `CTrade`. The MT5 Tester account graph may remain flat.
- The Friday cutoff is experimental. **Deriv XAUUSD market hours must be checked against actual symbol sessions and broker server timezone before interpreting results.** An incorrect cutoff can materially distort profits, losses, and signal selection.

## Compare results

`XAU_WEEKEND_COMPARE` prints control / weekend-policy balances, weekend opens, exit-at-cutoff attempts, entries blocked, win/loss counts, stage and configured cutoff hour. Search Journal for `XAU_RESEARCH|WEEKEND_FLAT|FRIDAY_FLAT`, `POLICY_FLAT_AT_AVAILABLE_TICK`, and `EXECUTION_TRACE`.

The original replay of Jan 2–4, 2026 on standard `XAUUSD` showed a Friday stop-risk of about $34.88 for three minimum-volume legs, but the first quote after a long weekend crossed the stop with a modelled loss of ~$87.42. The weekend-flat experimental book should be compared against the control **using the same underlying tick data and date window**. It can still lose substantially on weekdays and does not simulate broker liquidation/fees/swap.

## Verification sequence

1. Compile the source in MetaEditor with F7. GitHub's Python tests cannot natively compile MQL5.
2. Run standard `XAUUSD`, M5, same broker account and original Jan–Oct historical range with every tick mode.
3. Verify `XAU_WEEKEND_COMPARE`, and inspect `FRIDAY_FLAT` events and any `EXECUTION_TRACE` records.
4. Repeat the August–October shorter window as a second controlled experiment. Assess whether the policy merely shifts losses rather than improving robust expectancy.
5. Review execution realism, total equity floor and broker margin model **before** any change to execution permissions.

No live/demo orders, profitability promises or claims of completed native MT5 tests.
