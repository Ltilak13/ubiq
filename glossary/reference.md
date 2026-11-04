---
term: reference
ns: core
aliases:
  - ref
id: UB-4
---

A use of a [[term]] in a document. Explicit references (`[[term]]`, `[[ns:term]]`,
configured [[delimiter]]s), id references, `ref_fields`, and [[catalog]] entries
must resolve to a [[glossary record]] or the check fails. Wiki-links that look
like file paths (`[[GLOSSARY.md]]`, `[[dir/x]]`) are not term references unless
that name is a defined term. If the target exists in-repo as markdown, it is
pulled into the scan (`docs:` globs are roots; links are followed). A missing
file is not an error. Relative markdown links are followed the same way.
Plain-prose mentions of defined terms are indexed but never fail — they make
traceability searchable. Unresolved refs in `historical` docs (typically
`CHANGELOG.md`) are indexed but do not fail the build.
