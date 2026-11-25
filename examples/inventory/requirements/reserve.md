---
term: Reserve stock
id: REQ-RESERVE
---

# Reserve stock

The service reserves units from an [[item]].
A successful [[reservation]] reduces available stock by its quantity.
The service rejects unknown items, duplicate reservation identifiers, and quantities above available stock.
A failed operation does not change stock or reservations.
