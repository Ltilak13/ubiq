---
term: goal evidence policy
ns: policy
---

# Goal evidence policy

This policy governs the [domain-schema goal](../goals/domain-schema-goal.md)
within the goal-assessment domain. It constrains how the goal records evidence.

A partial assessment must identify implementation evidence, a check, and a
nonempty remaining gap. Its support list must contain at least one entry.
Each implementation and check must name a repository-relative path and an anchor.
The assessment stays provisional. A partial assessment does not establish goal completion.

The [goal schema](../../.ubiq/schemas/goal.json) enforces the required fields,
the assessment values, and the review record that a `met` assessment needs. The [goal tests](../../tests/test_goals.py) check
criterion labels and evidence locations, and reject unsupported assessment values.
These checks do not establish that an implementation satisfies a criterion.

The [registered model](../../.ubiq/knowledge/goal-governance.yaml) declares the
policy-to-goal relationship. Its evidence snapshots identify the source text,
schema, and tests that support this declaration. A fresh snapshot establishes
that the cited bytes and anchor still match. It does not establish semantic truth.
