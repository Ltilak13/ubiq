---
name: restated-values
status: shipped
requires: [glossary]
codes: [W008]
config: [restated_values]
docs: docs/spec.md#diagnostics
summary: Warn when a record's prose restates the value of one of its own frontmatter fields.
pr: [60]
---

Warn when a record's prose restates the value of one of its own frontmatter fields.
Planned in PR #60; it ships `W008` and the `restated_values` setting. Its `docs` link
points at the diagnostics list until that PR adds the section.
