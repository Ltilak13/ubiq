---
term: tracking field
ns: core
---

A frontmatter field that says what a record of work waits on and where it is mirrored:
`issue`, `priority` (`P1`, `P2`, `P3`), `requires`, `part_of`, and `pr`. The fields are one
shared fragment that goal criteria and feature records both use, so a fact about the
work has one home, the record. [[x-ubiq-ref]] annotates the ones that name other records
(`requires`, `part_of`). `ubiq sync github` mirrors them to GitHub issues, and the
mirror is checked, never the source. See [tracking fields](../docs/spec.md#tracking-fields-and-x-ubiq-ref).
