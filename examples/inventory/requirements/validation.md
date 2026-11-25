---
term: Validate quantities
id: REQ-VALIDATION
---

# Validate quantities

A [[reservation]] quantity must be a positive safe integer.
Identifiers must contain a non-whitespace character.
The service rejects invalid inputs before it writes data.
The database rejects invalid quantities, statuses, and missing item references.
