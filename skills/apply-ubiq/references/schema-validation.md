# Native schema validation

`ubiq check` validates explicitly selected files against JSON Schema Draft 2020-12.
Repositories without `schemas:` keep their existing behavior.

```yaml
schemas:
  - schema: .ubiq/schemas/domain.schema.json
    files: [.ubiq/knowledge/model.yaml]
    format: document
  - schema: .ubiq/schemas/frontmatter.json#/$defs/rule
    files: [rules/*.md]
    format: frontmatter
```

`schema` names a local JSON or YAML schema. An optional fragment selects a definition.
`files` is a nonempty list of repository glob patterns. Every pattern must match a file.
`format` is `document` (the default) or `frontmatter`.
Frontmatter mode requires a YAML mapping between opening and closing `---` markers.
All bindings that select a file apply to it.

Schemas can share definitions through same-document fragment references.
Fragments must select declared schema locations, such as `$defs`, `properties`, or `items`.
Annotation data in `examples`, `default`, or `const` cannot be a schema target.
External references, including remote URLs and other schema files, are unsupported and never fetched.
Bundle shared definitions into one schema file. An omitted `$schema` selects Draft 2020-12.
Other explicit dialects fail validation.

The schema parser preserves JSON value types. YAML `true` and `false` are booleans,
while legacy spellings such as `on` remain strings. Decimal integers and numbers
are numeric values. Duplicate keys, cyclic values, non-string object keys, and
non-finite numbers fail validation. The existing vocabulary parser still preserves
its lexical values: term names such as `No` and IDs such as `007` remain strings.

JSON Schema `format` remains annotation-only. Use explicit constraints for required guarantees.
Use `required`, `enum`, `const`, `if`/`then`, and composition to define each type's form.
The array's `items` reference selects its type definition. Keep one canonical definition
for each type and specialize it where the domain requires different fields.

## Record graph integrity

JSON Schema checks an individual document's shape. The optional root `x-ubiq`
extension adds cross-record checks and coverage against the registered glossary.
Its declarations belong to the schema and travel with the schema version.

```json
{
  "x-ubiq": {
    "collections": {"scripts": "script", "hooks": "hook"},
    "domains": "domains",
    "relationships": "relationships",
    "interactions": "interactions",
    "roles": {
      "invokes": {"from": ["hook"], "to": ["script"]}
    },
    "references": [
      {"kind": "hook", "field": "handler", "target_kind": "script", "relationship": "invokes"}
    ],
    "coverage": {"glossary": true, "exclude": []},
    "evidence": true
  }
}
```

Selectors name top-level arrays and must be distinct. A record contains `id`,
`kind`, `domain`, `source`, and nonempty `evidence`. A domain contains `id` and
nonempty `evidence`. A relationship contains `id`, `from`, `to`, `kind`, and one
evidence object. An interaction contains domain IDs in `from` and `to`, plus a
nonempty `via` array of relationship IDs. Schemas can require more fields.

The normal check enforces:

- Unique identities within records, domains, and relationships, plus unique record sources.
- Existing domains and relationship endpoints, with endpoint types permitted by `roles`.
- Each configured reference field resolves to its target type and has exactly one matching relationship.
- Each cross-domain relationship has an interaction with the same endpoint domains.
- Every registered glossary source has a typed record or an explicit coverage exclusion.
- Every record has evidence for its primary source. Evidence files remain within the repository.

Each evidence object contains `path`, a SHA-256 digest in `sha256`, and an exact
nonempty source excerpt in `anchor`. The check rejects missing files, changed digests,
and missing excerpts. Matching evidence proves source freshness, not the truth of an interpretation.

Coverage exclusions have this form:

```json
{"source": "skills/upstream/SKILL.md", "reason": "This repository does not own the upstream skill."}
```

Exclusions must identify registered sources. Stale exclusions and sources that
are both represented and excluded fail. Upstream symlinks can be excluded without
copying their records into the owned corpus. Coverage concerns registered sources;
it does not discover every unregistered file in a repository.

## Errors and maintenance

| Code | Meaning |
| --- | --- |
| E008 | Invalid binding, schema, or graph declaration |
| E009 | Unreadable or missing selected data, or a schema conformance failure |
| E010 | Record graph, source coverage, or evidence integrity failure |

Schema conformance errors include the file and JSON Pointer. These errors fail
`ubiq check`, including `--json`, pre-commit, and the GitHub action.

When a source changes, inspect its meaning before updating its evidence digest.
Stage the schema and corresponding metadata changes together. Use the
[schema change workflow](schema-workflow.md) for migration, review, and promotion.
The normal checker validates; it never rewrites source files or promotes a candidate.
