---
term: overlay
ns: core
aliases: [sidecar]
id: UB-7
---

A sidecar markdown file that attaches frontmatter to a source file the linter
does not own. The overlay points at the source with `source:`; optional `ns`,
`aliases`, `id`, and `ref_fields` values merge onto the source [[glossary record]].
The source file is never edited. (Do not use `on:` as the key — YAML 1.1 loads
it as a boolean.)
