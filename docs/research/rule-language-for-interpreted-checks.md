# Which rule language should interpreted checks use?

Research for ticket #138 on wayfinder map #137 (code-as-records goal, AC4).
Question: which language defines a `ubiq check` rule entirely as record data?

## Recommendation

Use **JSON Schema (Draft 2020-12) plus a small relational selector form**, not
JSONPath, jq, CUE, regex-only, or Semgrep patterns.

- JSON Schema is already a runtime dependency (`jsonschema>=4.18,<5`) and already
  runs `E009` and the shape half of `E010` in `src/ubiq/integrity.py`. It adds no
  dependency and no second evaluator.
- It cannot say "this value resolves to a record in another collection" or "this
  key is unique across records". The core spec notes that none of its vocabularies
  define a keyword that reads other parts of the instance (section 7.9). Add a
  small declarative form, in the style of the existing `x-ubiq` extension, with
  three primitives: `unique-by`, `resolves-to`, and `absent-in` (anti-join). The
  engine evaluates them over a **facts document** it builds (records, refs, edges,
  file set). The rule never walks files itself.
- A rule is then one record: `{code, severity, message, scope, schema, relations}`.
  Changing the record changes `ubiq check` with no code edit, which is what AC4
  asks for.

Candidate first tracers for AC4: `W003` (blocked invoke) or `E006` (field ref) as
a `resolves-to` rule, and the `E010` shape check as pure JSON Schema.

## Diagnostics no candidate can express as pure data

These need facts a record cannot hold. They stay bound code whichever language
wins. The limit is the missing facts and algorithms, not the language.

| Code | Why it stays code |
| --- | --- |
| `E005` | Fires before a record exists (frontmatter will not parse). |
| `E002` (wiki-link and delimiter forms) | Needs a lexer for prose. Once the engine extracts refs as facts, it becomes a `resolves-to` rule. |
| `E011` | Cycle detection over the include graph. Only jq (recursion) could write it, and that is an algorithm body, out of scope per #137. |
| `W001` | Aggregation: count of uses outside the defining record. |
| `W002` | Section-scoped text scan for mentions. |
| `W004` | Filesystem layout resolution across source and install trees. |
| `W006` | Glob versus file-set emptiness. Needs the file set as a fact, then possible as `absent-in`, but the glob engine stays code. |
| `W007` | Filesystem existence of link targets. |
| `E010` evidence checks (stale hash, missing anchor) | Needs `sha256` and file reads. Pure only if the engine supplies digests as facts. |
| `E008` contradiction cases | Shape is pure JSON Schema; "setting contradicts a guarantee" is cross-setting logic. |

## Classification of the existing diagnostics

Source: `docs/spec.md` (Diagnostics section) and `src/ubiq/check.py`, `graph.py`,
`integrity.py`.

Tiers:

- **A. Per-document constraint**: one record, file, or config object decides it.
- **B. Relational over facts**: needs a uniqueness, join, or anti-join across
  records, given a facts document.
- **C. Not data**: needs lexing, filesystem, hashing, or a graph algorithm.

| Code | Tier | Notes |
| --- | --- | --- |
| `E001` | B | Duplicate name or id within a namespace: `unique-by(ns, name-or-alias)`. |
| `E002` | C, then B | C for prose lexing; B once refs are facts. |
| `E003` | B | Join with a count above 1 on qualified names. |
| `E004` | B | Id-pattern match with no record carrying it: anti-join. |
| `E005` | C | Its "not a nonempty string" sub-cases are A. |
| `E006` | B | `ref_fields` value resolves by id, then name. |
| `E007` | B | Records matching `cover` globs minus the catalog's entries. Needs the glob match as a fact. |
| `E008` | A (mostly) | Unknown settings, shapes, regex validity: schema over `ubiq.yaml`. |
| `E009` | A | Already JSON Schema. |
| `E010` | A + B + C | Shape is A (already `_shape`). Domain, relationship, role, and interaction checks are B. Evidence hash is C. |
| `E011` | C | Cycle detection. |
| `E012` | B | Include names a declared input value: join to the part's input map. |
| `W001` | C | Aggregation. |
| `W002` | C | Text scan. |
| `W003` | B | Edge target has `blocked_by: true`: join plus predicate. The smallest rule. |
| `W004` | C | Filesystem. |
| `W005` | B, partly C | Anti-join of link edges against declared edges. "Text never names the target" needs text. |
| `W006` | B or C | See above. |
| `W007` | C | Filesystem. |

Of the 19 codes, `E008`, `E009`, and the shape part of `E010` are tier A. Eight
more are tier B (`E001`, `E003`, `E004`, `E006`, `E007`, `E012`, `W003`, `W005`),
plus `E010` relationships. The rest stay C. The recommended language covers A
natively and B through the relational form. No candidate does more than that,
and that is the finding that matters.

## Comparison

| Language | Tier A | Tier B | Error location | Dependency (pure-Python package) | Determinism |
| --- | --- | --- | --- | --- | --- |
| JSON Schema 2020-12 + selector form | Yes, fully | Only through the added form. `uniqueItems` alone fires on one array and names the array, not the duplicates (local test). | Instance path per error, for example `$.sev` (local test, `jsonschema` 4.26.0 `json_path`). Mapping the path to file and line is engine work. | None added; already required. `jsonschema` 4.26.0 is MIT, py>=3.10, pulls `attrs`, `referencing`, `rpds-py` (compiled wheel). | Pure keywords. Keep `format` assertion off or fixed, and no remote `$ref` retrieval (core spec 8.2.3: implementations should not assume network operations). |
| JSONPath (RFC 9535) | Selects nodes; filters compare them, so most of A | Filters see the current node and root only; no joins | Normalized paths identify matched nodes; a "no match" violation has no location | `python-jsonpath` 2.3.0: pure wheel, 66 KB, MIT, py>=3.8, optional `regex`. `jsonpath-ng` 1.16.0 needs py>=3.11 but Ubiq supports py>=3.10, so it is out. | Deterministic query; implementations differ on extensions and member order (RFC 9535, from memory) |
| jq | Yes | Yes (`group_by`, `index`, `any`) | Error text only, no structured instance path | `jq` 1.13.0: C extension wheels of 0.4 to 0.75 MB per platform. Not pure Python; sdist needs a C build. | Turing complete through recursion. Impure builtins exist (`now`, `env`, `$ENV`, `input`; jq manual, from memory). Needs a banned-builtin allowlist. |
| CUE | Yes (unification, disjunction) | Limited | Good: file, line, and column of conflicting values (from memory) | No PyPI package from the CUE project (PyPI lookup found none; `cuepy` is unrelated). Needs the Go `cue` binary as a subprocess. | Hermetic and non-Turing-complete by design (from memory) |
| Regex + field selectors | Weak: single-field string shape | No | Field plus offset | stdlib `re` | Backtracking can blow up; a subset of JSON Schema `pattern` anyway |
| Semgrep patterns | Wrong tool: matches code syntax trees | No | Excellent for code (line and column) | `semgrep` 1.187.0: wheels of 52 to 82 MB, about 25 dependencies, LGPL-2.1-or-later | Deterministic, but a large native engine |

## Error-location notes

Whichever language wins, a diagnostic needs `file:line`. A language that returns
an instance path (JSON Schema, JSONPath) maps to a line by walking the YAML node
tree of the original document; Ubiq must do that once and share it across rules.
An "absent" violation (anti-join) has no node to point at; point at the owning
record's first line, as `E007` does today. `unique-by` should report each
duplicate member, matching `E001`'s per-file report, rather than the array.

## Dependency and determinism summary

- Only JSON Schema adds zero dependencies and shares an evaluator with `E009`.
- jq and CUE reach relational rules without a custom form, but both bring a
  non-Python runtime (C extension, Go binary).
- jq is a programming language. Allowing it conflicts with #137's out-of-scope
  statement that a record constrains a bound function and does not contain one.
- Semgrep targets source code, which is the "bound" form of the goal, not the
  "interpreted" one.

## Source quality and gaps

Verified in this session:

- JSON Schema 2020-12 Validation and Core on `json-schema.org` (sections 6.1.2,
  6.1.3, 6.3.3, 6.4.3, 6.5.3, 6.5.4, 7.9, 8.2.3, 9.4.1). The Core fetch was
  truncated before section 12 (output) and 13 (security), so output-format claims
  rest on the local `jsonschema` run.
- PyPI JSON metadata for `python-jsonpath`, `jsonpath-ng`, `jq`, `semgrep`,
  `jsonschema`, and a lookup for a CUE package, retrieved 2026-11-27.
- This repository: `docs/spec.md`, `src/ubiq/check.py`, `graph.py`,
  `integrity.py`, `pyproject.toml`.
- A local run of `jsonschema` 4.26.0 for `uniqueItems`, `enum`, and `json_path`.

Not verified: RFC 9535, the jq manual, the CUE documentation, and the Semgrep
documentation. The session's network allowlist blocks `rfc-editor.org`,
`datatracker.ietf.org`, `jqlang.github.io`, `cuelang.org`, and `semgrep.dev`.
Claims marked "from memory" need a recheck before they decide anything beyond
this recommendation. The recommendation does not rest on them: it rests on the
dependency already present and on the tier analysis from this repository's code.

## Follow-ups for the map

- Specify the relational form's keys and the facts document shape (depends on the
  diagnostics-as-records tracer).
- Decide how `unique-by` reports per-duplicate locations.
- Decide whether tier C codes become bound records or stay outside the vocabulary.
