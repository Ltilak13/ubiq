---
term: overlay
ns: core
aliases: [sidecar]
id: UB-7
---

A sidecar markdown file that attaches metadata to a source file without editing it.
The overlay identifies the source with `source:`. It can modify a [[glossary record]]
with `term`, `ns`, `aliases`, or `id`.

For an ordinary document without a term, include at least one configured
`ref_fields` key and omit those term metadata keys. The reference fields are
checked without adding a glossary record. Empty reference lists are valid.
Use `source:` instead of `on:`, which YAML 1.1 loads as a boolean.
