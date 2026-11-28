---
name: frontmatter-tracking
status: active
issue: 118
priority: P1
trunk: main
steps:
  feature-records:
    issue: 70
    requires: []
    branch: claude/ecstatic-mendel-nkgz6t-issue-70
    base: main
    pr: 116
  goal-issue-hardening:
    requires: []
    branch: fix-goal-issue-sync-hardening
    base: main
    pr: 114
  sync-github:
    issue: 119
    requires: [feature-records, goal-issue-hardening]
    branch: claude/ecstatic-mendel-nkgz6t-sync-github
    base: claude/ecstatic-mendel-nkgz6t-issue-70
    pr: 132
  tracking-fields:
    issue: 120
    requires: [sync-github]
    branch: claude/ecstatic-mendel-nkgz6t-tracking-fields
    base: claude/ecstatic-mendel-nkgz6t-sync-github
    pr: 135
  requires-links:
    issue: 121
    requires: [tracking-fields]
    branch: claude/ecstatic-mendel-nkgz6t-requires-links
    base: claude/ecstatic-mendel-nkgz6t-tracking-fields
  part-of-sub-issues:
    issue: 122
    requires: [tracking-fields]
    branch: claude/ecstatic-mendel-nkgz6t-part-of
    base: claude/ecstatic-mendel-nkgz6t-tracking-fields
  feature-lifecycle:
    issue: 123
    requires: [tracking-fields]
    branch: claude/ecstatic-mendel-nkgz6t-feature-lifecycle
    base: claude/ecstatic-mendel-nkgz6t-tracking-fields
  plan-records:
    issue: 124
    requires: [tracking-fields]
    branch: claude/ecstatic-mendel-nkgz6t-plan-records
    base: claude/ecstatic-mendel-nkgz6t-tracking-fields
  detect-plan-step-cycles:
    issue: 149
    requires: [requires-links, plan-records]
    pr: 165
  pr-stacks:
    issue: 125
    requires: [requires-links]
    branch: claude/ecstatic-mendel-nkgz6t-pr-stacks
    base: claude/ecstatic-mendel-nkgz6t-requires-links
  schema-edge-diagrams:
    issue: 126
    requires: [tracking-fields, mermaid-blocks]
    branch: claude/ecstatic-mendel-nkgz6t-schema-edge-diagrams
    base: claude/ecstatic-mendel-nkgz6t-tracking-fields
  mermaid-blocks:
    issue: 59
    requires: [feature-records]
    branch: claude/ecstatic-mendel-nkgz6t-issue-59
    base: main
    pr: 117
  workflow-records:
    issue: 133
    requires: [tracking-fields, schema-edge-diagrams]
    branch: claude/ecstatic-mendel-nkgz6t-workflow-records
    base: claude/ecstatic-mendel-nkgz6t-tracking-fields
  view-sync:
    issue: 134
    requires: [tracking-fields, schema-edge-diagrams]
    branch: claude/ecstatic-mendel-nkgz6t-view-sync
    base: claude/ecstatic-mendel-nkgz6t-tracking-fields
  backfill:
    issue: 127
    requires: [feature-lifecycle, plan-records, pr-stacks, part-of-sub-issues]
    branch: claude/ecstatic-mendel-nkgz6t-backfill
    base: claude/ecstatic-mendel-nkgz6t-pr-stacks
---

# Plan: frontmatter tracking

This plan sequences the work in the frontmatter tracking spec (#118). Its
frontmatter is the source for the order, branches, and pull requests of each
step. GitHub's sub-issues and blocked-by links on the spec mirror it.

## How to read the steps

- `requires` names the steps that must finish first. A step's pull request is
  stacked on the branch of the step it requires, recorded as `base`.
- `pr` is the pull request that implements the step, once it is open.
- A step whose requirements live on different branches (`sync-github`) is based
  on one and merges the other in. Its pull request shows the merged commits
  until that branch reaches `main`.
- Workflow status is not stored here. An open pull request means the step is in
  review; a merged one means it is done.

## Status of this record

This is an interim plan record. Until the plan records step (#124) adds a
schema, the coordinator keeps it current by hand in the pull request that
changes these facts. Once the plan schema lands, `ubiq check` validates it and
`ubiq sync github` mirrors it.
