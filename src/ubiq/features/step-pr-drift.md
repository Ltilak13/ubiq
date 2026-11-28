---
name: step-pr-drift
status: planned
requires: [plan-records, github-sync]
codes: []
config: []
docs: docs/github-sync.md
summary: Report plan steps whose branch has a pull request that the step does not list.
issue: 184
priority: P2
---

Planned in #184. A plan step records its pull request in `pr` by hand, and merged steps have
drifted. The sync reads pull requests by head branch for each step that names a `branch`.
