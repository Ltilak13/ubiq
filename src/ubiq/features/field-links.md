---
name: field-links
status: planned
requires: [field-refs, markdown-references]
codes: [E013]
config: [references.value.severity]
docs: docs/spec.md#diagnostics
summary: Link prose to a frontmatter field and fail when the label no longer matches its value.
pr: [61]
---

Link prose to a frontmatter field and fail when the label no longer matches its value.
Planned in PR #61; it ships the `value` reference kind and `E013`. Its `docs` link
points at the diagnostics list until that PR adds the section.
