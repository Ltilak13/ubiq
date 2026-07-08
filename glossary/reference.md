---
term: reference
ns: core
aliases:
  - ref
id: UB-4
---

A use of a [[term]] in a document. Explicit references (`[[term]]`, `[[ns:term]]`) and id
references (matches of configured `id_patterns`) must resolve to a [[glossary record]] or the
check fails. Plain-prose mentions of defined terms are indexed but never fail — they make
traceability searchable.
