# Goal: domain-aware frontmatter and a knowledge tree

Status: planned. The current implementation discovers file groups and naming-field
mappings. It does not validate arbitrary frontmatter against per-type schemas.

## Objective

Make Ubiq discern a repository's domains, explain what each domain does and how
it interacts with others, and use that evidence to design explicit frontmatter
schemas. Those schemas should capture nearly all stable, relevant facts needed
to identify, understand, query, validate, and connect each file.

Frontmatter should have the quality of a completed form: named fields, clear
instructions, typed answers, required information, and checkable constraints.
Markdown should explain rationale, examples, and nuance that do not fit structured
fields. Avoid maintaining the same fact independently in both places.

## Discover domains and responsibilities

Use file structure as an initial clue. Inspect file contents, existing glossaries,
metadata, code interfaces, ownership, and dependencies to establish domain boundaries.
Preserve distinctions when the same word has different meanings in different domains.

For each domain, identify:

- Its purpose, responsibilities, and concepts.
- Its inputs, outputs, contracts, and invariants.
- The other domains it depends on or serves.
- How those interactions occur, including calls, events, data exchange, and workflows where applicable.
- The files and observations that support these conclusions, plus unresolved ambiguity.

Separate observed facts from inferred proposals. Missing evidence must remain
visible. A directory name or a plausible description is not sufficient evidence
for a domain boundary or relationship.

## Derive explicit schemas from the files

Distinguish three dimensions: record type controls structure, domain context
controls meaning, and folder location organizes files. Catalog arrays inventory
records and bind them to types. They do not independently duplicate schema definitions.

Provide reusable, versioned schema definitions for each record type, with domain
specializations where the same type needs different fields or constraints.
Keep shared identity and relationship fields consistent across types.
Use an established machine-readable schema standard where it fits.

Inspect representative files and exceptional cases before proposing a schema.
The proposal must identify required and optional fields, data types, descriptions,
allowed values, defaults where justified, and constraints. It must also identify
relationship targets, cardinality, and cross-field or cross-record rules that need
validation beyond individual field types.

Examples of type-specific facts include skill inputs and outputs, rule scope and
enforcement, script arguments and side effects, and hook events and conditions.
Business-domain types need their own vocabulary and constraints. These examples
are starting points, not a closed list of supported types.

Aim for broad semantic coverage through composable schemas. Avoid one oversized
schema filled with fields that do not apply to most records. Unknown information
and intentionally absent information must have distinguishable representations.

## Build the knowledge tree and its relationships

Organize records by domain and type, with stable identities independent of paths.
Represent cross-domain relationships as explicit, typed references. The hierarchy
provides navigation; relationships form a graph across that hierarchy.

Make it possible to answer which records implement a responsibility, which rules
constrain them, what they consume and produce, and what depends on them without
extracting those facts from free prose on every query.

Check missing targets, invalid target types, and incompatible relationships.
Treat cycles according to the relationship's semantics rather than rejecting
all cycles. Preserve identities and reference integrity when files move.

## Make quality measurable

Report schema conformance separately from completeness and semantic coverage.
A populated field is not proof that its value is correct.

Measure at least:

- Record coverage: eligible files assigned to an appropriate type and domain.
- Completeness: required values supplied, with unknown values reported separately.
- Conformance: field types, allowed values, and constraints satisfied.
- Relationship integrity: references resolve and meet target and cardinality rules.
- Evidence coverage: domain and interaction claims trace to supporting sources.
- Semantic coverage: agreed questions about representative files can be answered from frontmatter.
- Drift: structured facts that conflict with their canonical source or schema version.

Define denominators, exclusions, and acceptance targets before evaluating a
representative repository. Do not claim near-complete coverage from a high count
of fields or a single successful example.

## Staged improvement loop

Use the [schema change workflow](schema-workflow.md) for [[schema-staging]].
The setup or maintenance skill inspects repository changes and selects useful,
evidence-backed additions. It stages each schema change with the corresponding
record migration and tests. The skill tries the candidate against affected
records and invalid cases, then repairs or rejects unsupported changes.

A candidate becomes active through [[schema-promotion]] only when its migration
passes and the normal checker enforces the new [[domain-schema]]. Preserve prior
versions for recovery. Sample success alone does not authorize or establish promotion.

## Acceptance evidence

The goal is achieved when:

1. Setup can propose evidenced domains, responsibilities, interactions, and record types from repository files.
2. Each proposed type has an explicit, versioned schema with domain-specific differences where justified.
3. Users can review uncertain classifications and schema proposals before migration changes existing records.
4. A record author can use schema descriptions and constraints as a form, with actionable field-level validation errors.
5. Validation checks individual records and their relationships, with reproducible quality measurements.
6. Representative queries demonstrate that frontmatter captures most agreed facts about each file without reparsing its Markdown body.
7. Maintenance detects new types, missing records, schema drift, and changed domain relationships without silently reclassifying existing records.
8. Migration preserves file content, identities, aliases, and references, and reports unsupported cases explicitly.
9. Tests cover multiple domains, different schemas within a domain, shared types across domains, mixed file formats, and ambiguous evidence.
10. Setup and maintenance discover staged candidates, test useful additions, and distinguish rejected, staged, and successfully promoted changes.

Set the numerical coverage targets and representative repositories during design.
The measurements and acceptance criteria must stay visible when the implementation
is evaluated. This document defines the goal; it does not claim that these
capabilities are available today.
