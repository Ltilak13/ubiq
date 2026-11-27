# jsonpath-ng, python-jsonpath, and JsonLogic for rule selection

Research for ticket #154 on wayfinder map #137. Follows up decision 0001
(`docs/decisions/0001-rule-language.md`, ticket #138) and its research note
`docs/research/rule-language-for-interpreted-checks.md`, both on branches
`claude/ecstatic-mendel-nkgz6t-code-records-goal` and
`claude/ecstatic-mendel-nkgz6t-research-rule-language`. The support matrix is
ticket #153.

Question: with per-feature runtime requirements (#153), a rule feature could
need Python 3.11 through an optional extra while Ubiq keeps 3.10. Do
`jsonpath-ng`, `python-jsonpath`, or JsonLogic (`panzi-json-logic`) express
Ubiq's interpreted checks better than decision 0001's JSON Schema 2020-12 plus
the selector form (`unique-by`, `resolves-to`, `absent-in`)?

## Recommendation

**Keep decision 0001. Do not supersede it.** None of the three candidates
expresses the joins that decision 0001's selector form exists for, in the form
the library's own standard defines:

- **JsonLogic** (`panzi-json-logic`) cannot join. Every iterating operator
  rebinds the data to the current element, so a rule cannot see the id list
  while it walks the refs (verified). It also has no maintainer activity since
  2021.
- **`jsonpath-ng`** cannot express set membership or any join. The `in`
  operator fails to parse on 1.16.0 (verified). A root path on the right of a
  comparison parses only on 1.16.0, and compares against one fixed node, not a
  set. It is also the only candidate that raises the Python floor.
- **`python-jsonpath`** can express the joins, but only through its
  non-standard `in` extension. In its RFC 9535 strict mode the anti-join forms
  of E006 and E007 do not run (verified). A rule written that way is a
  `python-jsonpath` rule, not a JSONPath rule.

So the join problem stays with the selector form, and the candidates add a
dependency without removing it.

**If a JSONPath node selector is wanted later** (for the `scope` of a rule, the
"which nodes does this rule look at" half), use **`python-jsonpath`**, not
`jsonpath-ng`. It runs on Python 3.10 today, is pure Python, has no required
dependencies, and its strict mode selects the nodes with RFC 9535 syntax. The
joins stay in the selector form. That is an amendment to decision 0001, not a
supersession, and it is not needed for the first tracer (W003 or E006), which
runs on JSON Schema plus the selector form with no new dependency.

### Runtime and extra implication (#153)

- **Winner is not a 3.11+ library**, so no `runtime: {python: ">=3.11"}` record
  is needed for rule evaluation. Ubiq keeps `requires-python = ">=3.10"`.
- If `python-jsonpath` is adopted for node selection, the feature record needs
  no `runtime` field, because the library supports 3.8 and up (PyPI
  `requires_python`; also verified by installing and running on 3.10.20). Put
  it under an optional extra `ubiq[jsonpath]` (dependency `python-jsonpath>=2.3,<3`)
  rather than a core dependency, so the default install stays at two
  dependencies. The extra only matters for disk and import cost, not Python
  version.
- If someone still picks `jsonpath-ng`, the record would be
  `runtime: {python: ">=3.11"}`, `extra: jsonpath`. The 3.11 floor starts at
  1.9.1 (2026-10-06). On 3.10, pip resolves `jsonpath-ng` 1.8.0, an older
  release that lacks the root-path comparison (verified below). The extra would
  therefore install a different feature set per Python version, which is the
  drift the support records are meant to prevent. Another reason against.

## What was run

Throwaway venvs in the worktree (not committed): `.venv-r` on Python 3.13.18
and `.venv-310` on Python 3.10.20, installed with
`pip install jsonpath-ng python-jsonpath panzi-json-logic` (3.13) and the same
list through `uv` (3.10). Versions resolved: `jsonpath-ng` 1.16.0 (3.13) and
1.8.0 (3.10), `python-jsonpath` 2.3.0 (both), `panzi-json-logic` 1.0.1 (both).
The script ran over a small facts document in the shape decision 0001 calls for:

```python
FACTS = {
 "ids": ["feat:a", "feat:b", "step:c"],
 "ref_fields": [  # E006: value of a ref field must resolve to a record id
  {"record": "feat:a", "field": "owner", "value": "feat:b",   "file": "r/a.md", "line": 4},
  {"record": "feat:b", "field": "owner", "value": "feat:zzz", "file": "r/b.md", "line": 5}],
 "edges": [       # W003: an edge whose target is blocked_by
  {"from": "feat:a", "to": "step:c", "blocked_by": True,  "file": "r/a.md", "line": 7},
  {"from": "feat:b", "to": "feat:a", "blocked_by": False, "file": "r/b.md", "line": 9}],
 "cover_matches": ["r/a.md", "r/b.md", "r/c.md"],   # E007: paths matching `cover`
 "catalog":       ["r/a.md", "r/b.md"],             # minus the catalog's entries
}
```

The expected results are: W003 reports edge 0; E006 reports `feat:zzz` only;
E007 reports `r/c.md` only. The three rules by candidate, with what actually
happened:

| Rule | `python-jsonpath` 2.3.0 | `jsonpath-ng` 1.16.0 / 1.8.0 | `panzi-json-logic` 1.0.1 |
| --- | --- | --- | --- |
| W003 (filter, no join) | `$.edges[?@.blocked_by == true]` works in strict and default modes. | `$.edges[?(@.blocked_by == true)]` works. | `{"filter":[{"var":"edges"},{"var":"blocked_by"}]}` works. |
| E006 (anti-join to ids) | Default mode: `$.ref_fields[?!(@.value in $.ids)]` returns only `feat:zzz`. Strict mode: syntax error `unexpected '('`. The RFC-only form `count($.records[?@.id == @.value]) == 0` runs but returns **both** refs (wrong, see below). | `in` fails: `Parse error ... near token in`. `@.value == $.ids[0]` parses on 1.16.0 and compares to one fixed node, not the set; it fails to parse on 1.8.0 (Python 3.10). | Naive `!(in value ids)` returns **both** refs (wrong). Works only if the engine pre-joins a `resolved` flag into each fact, or inlines the id list as a literal in the rule. |
| E007 (anti-join of two lists) | Default mode: `$.cover_matches[?!(@ in $.catalog)]` returns `r/c.md`. Strict: same syntax error. | `not in` fails to parse. | Naive version returns all three paths (wrong): `catalog` is out of scope inside `filter`. |

Why the strict form returns both refs: in RFC 9535 the `@` of a nested filter
is the nested query's own current node, so `@.value` inside
`$.records[?@.id == @.value]` is a member of the record, not of the outer ref.
The correlated comparison cannot be written. (Reading of RFC 9535 sections on
filter selectors from memory; RFC text not fetched, see "Source quality". The
behavior itself was observed.)

Why JsonLogic fails: `apply.py` evaluates `filter`, `map`, `all`, `some`,
`none` with `data` set to the current item, and `reduce` with data set to
`{accumulator, current}`. There is no way back to the root document, and no
`let`. The `var` operator reads only from that rebound data. (Read from
`json_logic/apply.py` in the installed package, 146 lines.)

## Comparison

| Criterion | `jsonpath-ng` | `python-jsonpath` | JsonLogic (`panzi-json-logic`) |
| --- | --- | --- | --- |
| Version tested | 1.16.0 (3.13), 1.8.0 (3.10) | 2.3.0 | 1.0.1 |
| RFC 9535 conformance | README says it "aims to be" RFC 9535 compliant (README, line 4). Filter syntax is the older `?(@.x == v)` form; `count()` and other RFC functions fail to parse (verified: `count(@.x)` raises `JsonPathParserError`). No conformance suite claim found. | README: "We follow RFC 9535 and test against the JSONPath Compliance Test Suite." `strict=True` restricts syntax and registered functions to the RFC (docs, `syntax.md`). Suite pass rate not rerun here. | Not applicable. JsonLogic is a different language, not JSONPath. |
| Filter capability | Compare a field to a literal. Plus `&&`, `||`, `!`, `=~`. | RFC filters, plus (non-strict) `in`, `contains`, `=~`, list literals, root and current refs. | `==`, `<`, `in`, `and`, `or`, `if`, `var`, `filter`, `map`, `reduce`, `all`, `some`, `none`, `missing`, `merge`, `cat`, `substr` (25 table built-ins in `BUILTINS`, plus `if`, `and`, `or`, and the iterating operators handled in `apply.py`). |
| Join / anti-join | No (no set membership, no correlated compare). | Only through the non-standard `in` against a root path. Not in strict mode. Not by nested queries (RFC scoping). | No, without pre-joined facts or literals inlined in the rule. |
| `unique-by`, aggregation | No. | No built-in; `count()` exists but cannot group. | `reduce` can build counts, but the result is an algorithm body in a record, out of scope per #137. |
| Error location (query side) | Line and column of the parse error, in the form `Parse error at 1:23 near token in (ID)`. | `JSONPathSyntaxError` with a source excerpt and a caret, for example `'$.a[?@.x ==]' 1:11 ... unexpected end of expression`. | Raises `ReferenceError: Unrecognized operation: 'nope'`. No position. |
| Error location (result side) | `full_path` gives `edges.[0]`. A dotted path, no file or line. | `match.path` gives the normalized path `$['edges'][0]`; `match.obj` is the node. | A returned list of nodes, no path at all. |
| Mapping to file and line | Needs the engine to carry `file` and `line` in each fact (as in the sample). | Same. | Same. |
| Python floor | **3.11** from 1.9.1 (2026-10-06). 1.9.0 and older have no `requires_python`; 1.8.0 installed and ran on 3.10.20. 1.16.0 refuses 3.10 (`uv` reported the requirement unsatisfiable). Reason for the floor not verified. | **3.8**; classifiers list 3.8 to 3.15, CPython and PyPy. Ran on 3.10.20 and 3.13.18. | **3.6** (`requires_python`), no classifiers for versions. Ran on 3.10.20 and 3.13.18. |
| Dependencies | None declared (`Requires:` empty on 1.16.0). | None required. Optional extra `strict` brings `regex`. Wheel 68.5 KB, MIT. | None. Wheel 14.9 KB. Pure Python. |
| License | Apache-2.0 (PyPI). | MIT (PyPI). | MIT per classifier and `LICENSE` file; PyPI `license` field reads `UNKNOWN`. |
| Maintenance (PyPI upload dates) | 21 releases since 2017-03. 1.7.0 on 2024-11-20, then 1.8.0 on 2026-02-28, then 1.9.0 to 1.16.0 (8 releases) between 2026-10-05 and 2026-11-04. Active now, after a 15-month gap. | 33 releases since 2023-03-28. 2.0.2 on 2026-01-06, 2.1.0 on 2026-06-26, 2.2.x in July and October, 2.3.0 on 2026-11-22. Steady. | 2 releases, 2021-09-11 and 2021-09-12. Nothing since. Repository activity not checked (GitHub API returned 403). |
| Determinism | Pure query. Order is the document's dict order (observed). | Pure query. Registered functions: `count`, `length`, `match`, `search`, `value`, `startswith`, `type`, `typeof`, `is`, `isinstance`; none touch time or the environment. `match` and `search` use Python `re` unless the `strict` extra supplies `regex` (I-Regexp, RFC 9485). Result order is the document's dict order (observed). | Built-ins are pure. `extras.py` defines a `now` operation (clock) but it is not in the default `BUILTINS`; keep the default table to stay deterministic. Unknown operations raise. |
| Writes / updates | Yes (`update`, `filter`, `remove`). Not wanted: rules must not mutate facts. | JSON Patch and Pointer included. Not needed. | None. |

## Fit to decision 0001

Decision 0001's engine builds a facts document and evaluates three relational
primitives over it. Each candidate fits as follows.

- **As the rule language**: no candidate replaces the selector form. The
  `resolves-to` and `absent-in` primitives are exactly the joins the candidates
  cannot write in a portable way. `unique-by` (E001) is a grouping, and none of
  the three can group.
- **As a node selector inside the selector form**: only `python-jsonpath` in
  strict mode is a clean fit, with the nodes' normalized paths available to feed
  the line mapping the earlier research already calls engine work.
  `jsonpath-ng` offers the same selection with a smaller RFC surface and a
  higher Python floor. JsonLogic selects by `var` paths, which JSON Schema
  instance paths already cover.
- **Records stay data**: a JSONPath string is a string in a record, so it is
  data. A JsonLogic rule is a nested JSON tree and is also data, but writing
  `reduce` with an accumulator puts an algorithm body in frontmatter. That is
  out of scope per #137. Using only `filter`, `var`, `in`, and comparisons keeps
  it declarative, and that subset is what failed the join test.

## Source quality and gaps

Verified in this session:

- PyPI JSON metadata for `jsonpath-ng`, `python-jsonpath`, `panzi-json-logic`,
  and (looked up, rejected as a different, abandoned project) `json-logic`,
  retrieved 2026-11-27: versions, upload dates, `requires_python`,
  `requires_dist`, wheel sizes, licenses, classifiers.
- Installation and execution on Python 3.13.18 and 3.10.20. The results in the
  table above come from running the sample rules, not from the docs.
- `python-jsonpath` README and `docs/syntax.md` from the project repository
  (`jg-rp/python-jsonpath`, `main`): the RFC 9535 statement, the strict mode,
  and the `in`/`contains` extension.
- `jsonpath-ng` README (`jsonpath-ng/jsonpath-ng`, `master`) and
  `panzi-json-logic` README and source (`json_logic/apply.py`,
  `builtins.py`, `extras.py` as installed).

Not verified:

- **RFC 9535 text.** `rfc-editor.org` and `datatracker.ietf.org` were not
  reachable from this session. Statements about nested-filter scoping and
  object-member order rest on observed behavior and the `python-jsonpath`
  documentation, not on the RFC itself. Recheck section 2.3.5 (filter
  selector) before relying on them.
- The `python-jsonpath` documentation site (`jg-rp.github.io`) was not
  reachable; the repository's `docs/syntax.md` was used instead.
- The JsonLogic specification site (`jsonlogic.com`) was not reachable; the
  `panzi-json-logic` README and source stood in. Behavior of the reference
  JavaScript implementation is not compared.
- The Compliance Test Suite pass rate for either JSONPath library was not run.
- Why `jsonpath-ng` raised its floor to 3.11 at 1.9.1: no changelog read.
- Repository activity for `panzi-json-logic` (GitHub API returned 403); only
  PyPI release dates support the "unmaintained" reading.
- `jsonpath-ng` 1.9.0 through 1.15.0 behavior was not tested; only 1.8.0
  (Python 3.10) and 1.16.0 (Python 3.13).

## Follow-ups for the map

- Decide whether the selector form's `scope` needs JSONPath at all. JSON Schema
  plus the engine's facts shape may already cover it. If so, add nothing.
- If `python-jsonpath` is adopted for `scope`, pin to the strict environment so
  rule records cannot use non-standard syntax, and record the `ubiq[jsonpath]`
  extra in the #153 feature record. No `runtime` restriction is needed.
- Amend decision 0001's "Open follow-up (#154)" paragraph to point at this file
  and close it as "keep".
