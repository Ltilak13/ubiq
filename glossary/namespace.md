---
term: namespace
ns: core
aliases:
  - ns
id: UB-3
---

A bounded context for the vocabulary. The same [[term]] may be defined in different
namespaces with different meanings; an unqualified [[reference]] to such a term is ambiguous
and must be qualified (`ns:term`). Namespaces exist because a single global vocabulary
collapses under polysemy — this is DDD's bounded-context lesson.
