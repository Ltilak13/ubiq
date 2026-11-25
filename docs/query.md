# Query typed repository records

`ubiq query` selects complete records from configured
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
errors. With no filters, the command returns all records in the selected repositories.
Local records remain the default scope.

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

## Configured repositories

`--repository NAME` selects one dependency with that declared name in
`edges.external`. `--all-repositories` includes the local repository and its
available direct configured dependencies. The two options are mutually exclusive.
Default local queries do not load or validate dependency checkouts.

For a dependency declared with `name: shared`, use:

```sh
ubiq query --repository shared --kind script --json
ubiq query --repository shared --id RECORD_ID --incoming --relation RELATION --json
ubiq query --all-repositories --domain DOMAIN --json
```

Replace the filter values with declarations from the selected metadata. The
command never clones repositories or fetches revisions. Dependency paths must
already be available locally. Transitive dependency traversal remains a `graph`
capability; this query scope includes only direct declarations.

Explicit repository selection requires a configured name. Legacy path-only
entries participate in `--all-repositories` with no name. The command does not
invent names from directory basenames. Repository identity remains the canonical
physical root. Two aliases for the same checkout return its records once, after
each selected declaration's policy is checked.

Identity resolution occurs across the selected repositories before kind and
domain filters. Duplicate IDs in different repositories are ambiguous. Use
`--repository` to select a repository, and `--document` when needed to select a
metadata document within it. Relationship endpoints remain local to their
metadata document and binding. Records in another repository cannot repair a
missing endpoint.

| Repository condition | Explicit selection | All-repository selection |
| --- | --- | --- |
| Available, valid checkout | Query its records | Include its records |
| Absent named optional checkout | Unavailable, nonzero | Report as skipped; query available repositories |
| Absent required checkout | Unavailable, nonzero | Partial, nonzero; retain other repositories' records |
| Absent legacy path-only checkout | Not selectable by name | Partial, nonzero |
| Existing invalid checkout, pin mismatch, or dirty pinned input | Unavailable, nonzero | Partial, nonzero; retain healthy repositories |
| Readable but malformed selected metadata | Partial with readable records | Partial with readable records |
| Unknown configured name | Unavailable, nonzero | Not applicable |

In all-repository mode, `complete` describes the available configured corpora.
Skipped optional repositories remain explicit in repository scope information;
a successful answer does not claim that they contain no matching records.

Revision pins use the existing dependency policy. Validation includes metadata,
schemas, configuration, glossary and overlay inputs, linked documents, and all
declared source and evidence paths. It includes record, domain, and relationship
evidence even when a filter would omit them from the answer. Validation checks
declared paths, symlink components along those paths, and resolved targets.
Dirty pinned inputs,
wrong revisions, and inputs that escape the checkout are failures. Unpinned
repositories retain working-tree semantics and visible evidence drift.

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
documents, and collection count. With a repository selector, it also includes
`mode`, `requested_repository`, and `repositories`. Each repository entry records
its declared name (or null), canonical root, local/required flags, configured
`revision`, `observed_revision`, and status. Loaded entries also include documents
and collection count. Unavailable or skipped entries include a reason.
Repository status is `available`, `partial`, `unavailable`, or `skipped_optional`.

For repository selection, aggregate `scope.documents` uses absolute paths to
avoid collisions. Result metadata paths remain relative to each result's
repository. Aggregate diagnostics include their repository. Default local output
retains its existing relative scope paths. `selection` records the filters and identity
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

Projection syntax and multi-hop typed relationship queries remain outside this
slice. The existing `graph` command retains multi-hop composition traversal.
Relationship queries and repository selection are unreleased additions to the
v0.11.0 local record interface.

The command reads accepted metadata without changing it. Adoption requires no
index, service, migration, or new dependency. Removing query usage leaves the
metadata corpus intact. Ubiq's released repository has no `x-ubiq` collections;
its real-software usefulness demonstration requires accepted declarations in S5.
