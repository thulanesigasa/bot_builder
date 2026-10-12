# V1.8.3.1 Contract Outcome Resolvers Audit

![Contract Resolvers](https://img.shields.io/badge/Resolvers-VERIFIED-brightgreen.svg)
![Rise/Fall](https://img.shields.io/badge/Rise%2FFall-STRICT%20INEQUALITY-blue.svg)
![Only Ups/Downs](https://img.shields.io/badge/Only%20Ups%2FDowns-MONOTONIC%20PATH-purple.svg)
![Golden Vectors](https://img.shields.io/badge/Vectors-8%2F8%20PASS-brightgreen.svg)

## 1. Executive Summary
This audit validates the mathematical outcome resolution implementations for both Deriv contract families:
1. **Rise/Fall (`CALL`, `PUT`)**
2. **Only Ups / Only Downs (`RUNHIGH`, `RUNLOW`)**

## 2. Rise/Fall Specification & Equality Semantics
Broker options contract semantics:
- `CALL`: Wins (1) if and only if `expiry_spot > entry_spot`.
- `PUT`: Wins (1) if and only if `expiry_spot < entry_spot`.
- **Tie / Equal Spot**: `expiry_spot == entry_spot` is an automatic LOSS (0) for both `CALL` and `PUT`.

```python
if expiry_spot == entry_spot:
    return 0, True  # Tie is a loss
if direction == "CALL":
    return (1 if expiry_spot > entry_spot else 0), False
elif direction == "PUT":
    return (1 if expiry_spot < entry_spot else 0), False
```

## 3. Only Ups / Only Downs Monotonic Path Specification
Monotonic contracts require successive movements on every individual intermediate tick:
- `RUNHIGH`: Every tick in the sequence must be strictly higher than the previous tick:
  $S_1 > S_{	ext{entry}}, S_2 > S_1, \dots, S_d > S_{d-1}$.
- `RUNLOW`: Every tick in the sequence must be strictly lower than the previous tick:
  $S_1 < S_{	ext{entry}}, S_2 < S_1, \dots, S_d < S_{d-1}$.
- Any reversal, downward tick, or equal tick at any step terminates the contract in an immediate LOSS (0).

## 4. Golden Test Vectors
Eight adversarial test vectors were constructed and verified:
1. Strict Rise: `[100.1, 100.2, 100.3]` -> CALL Win, RUNHIGH Win.
2. Strict Fall: `[99.9, 99.8, 99.7]` -> PUT Win, RUNLOW Win.
3. Reversal on Final Step: `[100.1, 100.2, 100.15]` -> CALL Win, RUNHIGH Loss (step 2 break).
4. Equality on Step 1: `[100.0, 100.1, 100.2]` -> RUNHIGH Loss (step 0 equal).
5. Expiry Equality: `entry = 100.0, expiry = 100.0` -> CALL Loss, PUT Loss.
6. Off-by-one Tick Expiry: 5-tick contract with 4 ticks fails closed with exception.
7. Insufficient Spots: Raises `ValueError`.
8. Invalid Direction: Raises `ValueError`.
