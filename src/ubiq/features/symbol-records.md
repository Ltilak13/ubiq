---
name: symbol-records
requires: [tracking-fields, plan-records, feature-planning]
codes: []
config: [symbols.coverage]
docs: docs/spec.md#python-symbol-records
summary: Check declared Python symbol contracts and resolve their owning features.
issue: 155
---

Covered Python modules carry adjacent Markdown records for their public
signatures. Each record names one owning feature.
