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

## Declarations and checks

The [registered model](../../.ubiq/knowledge/goal-governance.yaml) is data. It
declares the policy and goal records, their governing relationship, and evidence
snapshots for the policy, goal, schema, and tests. It does not execute checks.
The [goal schema](../../.ubiq/schemas/goal.json) defines required fields and
permitted assessment values.

Run these commands from the repository root:

```sh
ubiq check
python3 -m pytest tests/test_goals.py -q
```

The CLI's `ubiq check` command applies the registered schemas and checks links,
relationship constraints, and evidence snapshots against their source files.
Pytest executes the [goal tests](../../tests/test_goals.py), which check criterion
labels and evidence locations and reject unsupported assessment values.
`ubiq check` does not run those tests. Listing a test in the model does not mean
that the test ran or passed.

A fresh snapshot means the cited source bytes and anchor still match. Neither
freshness nor passing structural checks establishes semantic truth or goal
completion. The goal's acceptance assessments remain authoritative.
