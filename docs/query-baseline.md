# Typed repository queries: baseline

## Released starting point

The first query slice starts at v0.10.0, commit
`644a13bd194aebb23e0af19e7c040ddd6a7c3c93`. The
[release](https://github.com/Ltilak13/ubiq/releases/tag/v0.10.0)
was published on November 25, 2026. Its ancestry includes composition commit
`2ae82dc`. The installed CLI version does not select the implementation baseline.

S1 establishes the questions and evidence. S2 adds read-only local selection by
kind, domain, and identity, with complete records and provenance. Relationship
traversal and dependency selection remain S3 and S4. Real-repository acceptance
across both repository types remains S5, followed by independent milestone review.

## Questions and available declarations

The skill repository's accepted `.ubiq/knowledge/model.yaml` is selected by its
configured schema. The schema's `x-ubiq.collections` declares six kinds: `skill`,
`rule`, `script`, `hook`, `configuration`, and `concept`. Proposals outside those
configured collections are not query inputs.

The inspected skill repository revision is
`90fcb7c27fdb474ee9dc75446646ec9494b86df1`. The active model, schema, and configuration
were clean at inspection. Released schema assessment found no conformance or
integrity findings. Evidence freshness describes that observation, not semantic truth.

| Question | Declared answer and evidence | Slice or gap |
| --- | --- | --- |
| Which records belong to a domain? | `change-delivery` has 29 records: 11 skills, 10 scripts, 8 concepts. Every record carries `source` and evidence snapshots. | S2 exact domain selection |
| What inputs, outputs, and contracts does a record declare? | `ai:publish-changes`, at `/skills/13`, includes `inputs`, `outputs`, and `publication_contract`. Its source is `skills/push-slices/SKILL.md`, with evidence anchor `## Commit, then push`. | S2 complete record selection |
| Which rules constrain a workflow? | `/relationships/2` declares `ai:memory-rule` (`/rules/5`) `governs` `ai:memory-workflow` (`/skills/9`). | S3 traversal. `constrains` is not a declared role. |
| Which records implement or support a responsibility? | The inspected schema has no `implements` or `supports` role. | Missing declarations. Do not infer these relationships from prose. |
| What evidence supports a fact? | Records include source paths and evidence with a path, SHA-256, and anchor. The selected record's JSON Pointer identifies its declaration. | S2 provenance and complete records |
| Which matching records have stale or missing evidence? | All 96 inspected records passed evidence checks at inspection. | S2 status reporting, with regression tests for stale and missing snapshots |

Useful S2 commands, with `SKILL_REPO` set to the inspected repository checkout:

```sh
ubiq query --root "$SKILL_REPO" --domain change-delivery --json
ubiq query --root "$SKILL_REPO" --kind rule --domain instruction-policy
ubiq query --root "$SKILL_REPO" --id ai:publish-changes --json
ubiq query --root "$SKILL_REPO" --kind script --domain capability-distribution --json
```

Expected selection sizes at the inspected revision are 29, 11, 1, and 13.
`--kind rule --domain change-delivery` legitimately returns zero records.
These commands describe the S2 interface; v0.10.0 itself does not provide `query`.

## Ordinary software repository prerequisite

Ubiq itself is the selected accessible ordinary software repository. At v0.10.0,
its configured schemas validate owned assets, but none declares `x-ubiq.collections`.
It therefore cannot supply accepted domain records to this query slice. Its
ordinary-software coverage fixture is useful for regression checks only.

S5 needs source-reviewed domain declarations in an ordinary software repository
before it can demonstrate useful nonempty answers there. The integration maintainer
owns that prerequisite. Adding those declarations is outside S1–S2. A bounded
inspection of other available application checkouts found no configured ubiq corpus.
No application source or metadata was changed for this investigation.

## S2 contract decisions

Filters use exact values and combine with AND. Unknown kind or domain values
produce a successful empty selection. Unknown options remain CLI usage errors.
An explicit missing identity has a distinct not-found outcome. Duplicate IDs in
separate documents retain separate identities. An unqualified identity with more
than one candidate is ambiguous, even when other filters could hide candidates.
A document qualifier can select one candidate.

Only configured collections supply records. Readable records retain their declared
fields, including evidence. Schema conformance, integrity findings, and evidence
freshness remain separate. Invalid or unreadable selected corpora make results
explicitly partial and return nonzero. Stale evidence stays visible and does not
by itself make selection incomplete. `ubiq check` remains the validation authority.

The JSON envelope is versioned and deterministically ordered. Repository identity,
observed revision when available, metadata document, and JSON Pointer accompany
records. A revision identifies HEAD, while query results describe the working tree.
S2 does not load dependency repositories. Missing optional dependency checkouts
must not break local selection. No accepted metadata, schema migration, index,
or dependency installation is part of the slice.
