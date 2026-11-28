---
term: x-ubiq-ref
ns: core
aliases:
  - edge name
---

A JSON Schema annotation, `{ns, edge, acyclic?, single?}`, on a property whose values
name records. Each value must resolve to a record in `ns` (E006), and each makes a
[[composition edge]] whose kind is `edge`, the edge name, so `ubiq graph --kind <edge>`
selects it. The relationship is declared once, in the schema, instead of in a list of
fields in `ubiq.yaml`; `ref_fields` keeps working beside it. A [[tracking field]] such as
`requires` is typically annotated. See
[tracking fields and x-ubiq-ref](../docs/spec.md#tracking-fields-and-x-ubiq-ref).
