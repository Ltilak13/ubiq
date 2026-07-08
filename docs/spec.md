# ubiq spec (stage 1 — deterministic linker)

This document is itself linted: every bracketed use below is a real [[reference]] that must
resolve, or `ubiq check` fails this repo.

## Model

The vocabulary is a set of terms. Each [[term]] (UB-1) is defined by exactly one
[[glossary record]] (UB-2) within its [[namespace]] (UB-3). Documents use terms via
references (UB-4); the linker resolves every [[reference]] against the glossary and emits a
[[diagnostic]] (UB-5) for anything broken.

Resolution rules, in order: an explicit qualified reference resolves within its namespace
only; an explicit unqualified reference resolves across all namespaces and must land on
exactly one [[record]]; an id reference resolves against record `id:` fields.

## Diagnostics

- `E001` duplicate definition — one name (canonical or alias) claimed by two records in the
  same [[namespace]], or one id claimed twice. The report is the consolidation work order.
- `E002` unresolved reference — an explicit [[reference]] with no defining [[record]].
- `E003` ambiguous reference — an unqualified reference to a [[term]] defined in more than
  one [[namespace]]; qualify it.
- `E004` unresolved id — an id-pattern match with no record carrying that id.
- `W001` orphan term — a [[term]] defined but never used outside its own record. Warning,
  not error: new terms are born orphaned.

## Invariants

Code spans and fenced blocks are never scanned, so documentation of the syntax cannot trip
the linker. Frontmatter is never scanned, so field names are not mentions. Plain-prose
mentions of a defined [[term]] are indexed for search and orphan detection but can never
fail the build — the error surface is exactly what the author explicitly marked plus the
configured id patterns.
