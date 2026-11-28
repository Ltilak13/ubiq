---
name: met-at-backfill
status: planned
requires: [criterion-scenarios, github-sync]
codes: []
config: []
docs: docs/github-sync.md
summary: Record "met at" on the issue of a met criterion that GitHub closed before the sync could.
issue: 190
priority: P2
---

Tracked by #190. The sync posts the comment once for an issue that closed first, and finds
implementing pull requests from `Refs #n` and branch names. The issue stays open until the
comments on the affected criterion issues exist.
