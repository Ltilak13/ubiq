---
term: Release stock
id: REQ-RELEASE
---

# Release stock

The service releases an active [[reservation]].
Release restores its quantity to the [[item]] and changes its status to released.
Repeated release succeeds without changing stock.
The service rejects an unknown reservation.
