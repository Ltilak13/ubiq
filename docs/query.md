# Query typed repository records

`ubiq query` selects complete records from the local repository's configured
`x-ubiq.collections`. It uses the existing schema and integrity assessments.
Markdown prose, unconfigured YAML, and domain proposals are not query inputs.

```sh
ubiq query --root "$SKILL_REPO" --domain change-delivery --json
ubiq query --root "$SKILL_REPO" --kind rule --domain instruction-policy
ubiq query --root "$SKILL_REPO" --id ai:publish-changes --json
ubiq query --root "$SKILL_REPO" --kind script --domain capability-distribution --json
```

These examples use declarations inspected in the skill repository. See the
[baseline and question matrix](query-baseline.md) for expected results and gaps.
The command does not require those particular kinds, domains, or IDs.

## Selection and identity

Filters combine with AND and match exact declared values. An unknown kind or
domain returns an empty successful selection. Unknown command options are usage
errors. With no filters, the command returns all selected local records.

An identity consists of the repository, metadata document, and declared ID.
Records with the same ID in different documents remain separate. Use
`--id ID --document PATH` to select an ID within one metadata document.
A bare ID with multiple candidates is ambiguous. Kind and domain filters cannot
hide that ambiguity. A requested ID that does not exist has a distinct not-found
outcome. The JSON Pointer identifies the record's position within its document.

Each result includes the complete declared record, including source, evidence,
and any domain-specific fields. Consumers can read declared inputs, outputs,
and contracts without extracting them from prose. Identical locations selected
by overlapping schema bindings appear once, with all binding assessments retained.

## Declared relationships

Use `--id` with `--incoming` or `--outgoing` to follow one hop. `--relation`
filters the exact declared relationship kind and implies outgoing when neither
direction is given. Plain `--id` still selects the record itself.

```sh
ubiq query --root "$SKILL_REPO" --id ai:memory-workflow --incoming --relation governs --json
ubiq query --root "$SKILL_REPO" --id ai:memory-rule --outgoing --relation governs --json
```

The first command returns `ai:memory-rule`. The second returns
`ai:memory-workflow`. Both carry the declared
`memory-rule--governs--memory-workflow` edge and its evidence from
`cursor/rules/project-memory.mdc`. The role is `governs`, as declared in the
metadata; the command does not translate it to another relationship name.

Relationship queries read only the collection named by `x-ubiq.relationships`.
They do not convert reference fields, prose mentions, or composition links into
edges. Endpoints resolve within the declaring metadata document and its binding.
An ID in another document cannot repair a missing endpoint. Cycles and self-links
remain one-hop results.

`results` contains unique neighboring records. Kind and domain filters apply to
those neighbors. `--document` qualifies the starting ID. The `relationships`
array retains full edge declarations and their provenance. Each edge includes
`endpoints`, with each endpoint's resolution status and, when resolved, its
identity and metadata location. `resolution` describes the whole edge.
`selection` includes the direction, relation filter, and resolved starting record.

Missing or ambiguous endpoints remain visible as broken edges with diagnostics,
even when neighbor filters are present. They make the response partial and exit 1.
Resolved edges appear only when their neighbor passes the filters. An unknown
relationship filter returns an empty successful result when the corpus is complete.

Edge `evidence_status` uses the existing assessment for its source record, which
can include other edges from that source. `evidence_scope: source_record` states
this limit. The status does not claim a separate assessment of each edge snapshot.
Record selection is available in v0.11.0; relationship queries are unreleased.

## Evidence and failure behavior

A declared fact, a structurally conforming record, and fresh evidence are separate
properties. A snapshot hash and anchor can match a source without establishing
that the declaration is semantically true. `ubiq check` remains the validation
authority.

Invalid or unreadable selected corpora produce explicitly partial results and a
nonzero exit. Available readable records remain visible. Stale evidence remains
visible on readable records and does not by itself make selection incomplete.
Diagnostics explain missing evidence and invalid declarations.

Repository revision records the observed HEAD when Git can provide it. Results
come from the working tree, including local modifications, rather than a frozen
commit snapshot. A repository without configured collections has no queryable
records. An empty answer there does not establish that its software has no
responsibilities or relationships.

## JSON output and exit codes

`--json` returns envelope version `1`. `results` contains record wrappers,
`diagnostics` contains assessment findings, and `complete` states whether the
selected corpus was fully available. `scope` identifies the repository, metadata
documents, and collection count. `selection` records the filters and identity
resolution result. Output ordering is deterministic for unchanged inputs.

Each result has these fields:

| Field | Meaning |
| --- | --- |
| `identity` | Repository, metadata document, and declared ID |
| `repository` | Root, observed revision when available, and `working_tree` state |
| `metadata` | Metadata file and escaped JSON Pointer |
| `record` | Complete declared record |
| `conformance` | Structural conformance across applicable bindings |
| `evidence_status` | `fresh`, `stale`, `missing`, `invalid`, or `not_assessed` |
| `assessments` | Every applicable binding, schema, conformance, evidence status, and categorized findings |

Evidence status follows native integrity findings for the record's owner ID.
That can include evidence carried by declared edges from the record. It does
not claim to assess each snapshot separately. When structural errors prevent
integrity assessment, evidence status is `not_assessed`.

| Exit | Envelope status | Meaning |
| --- | --- | --- |
| 0 | `ok` | Complete selection, including zero matches or visible evidence drift |
| 1 | `partial` or `unavailable` | A selected corpus or prerequisite could not be fully assessed |
| 3 | `not_found` | An explicit identity does not resolve in a complete corpus |
| 4 | `ambiguous` | An explicit identity has multiple candidates |

CLI usage errors exit 2. When the corpus is incomplete, the result must not
claim that an unobserved identity is conclusively absent.

## Current limits

This command selects local records only. It does not load configured dependencies,
so an unavailable optional dependency does not break a local query. Dependency selection and projections are outside this slice.
The existing `graph` command retains multi-hop composition traversal.

The command reads accepted metadata without changing it. Adoption requires no
index, service, migration, or new dependency. Removing query usage leaves the
metadata corpus intact. Ubiq's released repository has no `x-ubiq` collections;
its real-software usefulness demonstration requires accepted declarations in S5.
