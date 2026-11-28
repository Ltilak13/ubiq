---
term: reservation
status: accepted
scenarios:
  - features/reservation.feature
---

# Reservation

A reservation holds stock for one customer. The numeric limits live in
[limits.yaml](../limits/limits.yaml), so this prose states none.

The behavior is the scenarios in `features/reservation.feature`. Cucumber runs
them. This record is the rationale: a reservation is rejected before it can
hold more stock than exists, so a customer is never promised what the shop
cannot ship.
