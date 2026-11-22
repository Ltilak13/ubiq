# ubiq

A linker for prose. Explicit vocabulary references must resolve to exactly one
defining record, or the check fails.

Define a term once, link to its definition from your docs, and check those links
in CI. Ubiq reports missing references, duplicate definitions, and ambiguous names.
It also indexes ordinary mentions for search. It doesn't rewrite your docs or
check whether every word belongs in the glossary.

## Quick start

Install from a Ubiq checkout:

```bash
pip install -e .
```

Then initialize the repository you want to check:

```bash
cd /path/to/your/repo
ubiq init
ubiq check
```

Add a record at `.ubiq/glossary/session.md`:

```markdown
---
term: session
---

A period of play.
```

Reference it from your README with an ordinary Markdown link:

```markdown
Start a [session](.ubiq/glossary/session.md).
```

That link is a checked vocabulary reference. If the file disappears or no longer
defines a record, `ubiq check` fails with `E002` and the source location.
Link the first useful mention in a section and leave repeated mentions plain.
Those plain mentions still appear in `ubiq refs session`.

To find sections that skip the link, turn on the unlinked-mention warning:

```yaml
unlinked_mentions: warn       # W002, once per term per section; never fails the check
unlinked_except: [pr]         # terms that are ordinary words here ("PR")
```

Headings, historical docs, a term's own record, and overlay sidecars are not
reported. The [maintain skill](skills/maintain-ubiq/SKILL.md) works through
these warnings.

Wiki-links remain available. A typo such as `[[sesion]]` reports:

```text
E002 unresolved reference [[sesion]] — no defining record. Did you mean [[session]]?
```

## References

- Inline Markdown links to registered records or paths matching configured
  glossary globs must resolve. The destination selects the record, so the label
  can be natural prose. Fragments and link titles are allowed. Other local links
  keep their existing traversal behavior. Full `[label][id]`, collapsed `[id][]`,
  and shortcut `[id]` links work with a single-line `[id]: path/to/record.md`
  definition. Labels ignore case and repeated whitespace; the first definition wins.
- Wiki-links such as `[[session]]` and `[[game:session]]` resolve by name, alias,
  or record ID. Qualify a name when multiple namespaces define it.
- Configured delimiters support slash-commands such as `/tdd`. With
  `only_known: true`, unknown names, including typos, are ignored.
- Configured ID patterns and frontmatter reference fields must resolve too.
  Plain mentions are indexed for search and never fail the check.

Each kind has a policy you can tune per repository: how severe its failures are
and which regions it scans besides plain prose (`inline_code`, `address`,
`comment`):

```yaml
references:
  id: {severity: warn}       # report unknown ids without failing the check
  delimiter: {severity: off} # keep /commands searchable, report nothing
  wiki: {scans: []}          # ignore [[links]] in URLs and HTML comments
```

Settings that would break a spec guarantee, such as scanning fenced code or
letting a plain mention fail the build, are rejected with `E008`. The
[spec](docs/spec.md#reference-kinds) lists every kind's defaults.

Records use YAML frontmatter with `term`, optional `ns`, `aliases`, and `id`.
The body contains the definition. Existing schemas can use another term field,
including skill `name:` fields. Sidecar overlays attach metadata and dependencies
without editing the source files. Equivalent glossary globs register each file
once. Conflicting namespace or term-field rules report `E008`; two overlays
for one source report `E005` and must be consolidated.

An overlay can declare dependencies for an ordinary document such as `README.md`.
Include a field listed in `ref_fields`, such as `uses`, and omit term metadata
(`term`, `ns`, `aliases`, and `id`). An empty dependency list is valid.
The document stays outside the glossary, and each dependency must resolve.

## Commands and CI

```bash
ubiq check                             # exit 1 on errors, 0 otherwise
ubiq check --json                      # diagnostics for CI and agents
ubiq terms                             # list the glossary
ubiq terms --format context --ns repo   # emit a CONTEXT.md Language section
ubiq refs session                      # find links and ordinary mentions
ubiq refs game:session                 # restrict the query to a namespace
ubiq refs session --json               # structured definitions and references
ubiq refs session --kind explicit --kind markdown
ubiq explain                          # show why files were discovered
ubiq explain --json                    # the same discovery evidence as JSON
ubiq candidates                        # backticked names in 2+ docs with no record
ubiq candidates --json --min-files 3
```

`--kind` is repeatable: results include any selected kind (`explicit`, `id`,
`field`, `mention`, `catalog`, or `markdown`) or policy (`wiki` or `delimiter`,
the two halves of `explicit`). Without filters, `refs` includes all kinds. Its JSON output contains `query`, `definitions`, `references`, and
`count`; an unknown query returns an empty result with `error` and exits 1.
Paths inside the repository are relative to its root; external paths are absolute.

`explain` shows matching globs, followed links, overlays, and historical rules.
It reports ignored candidates encountered during discovery and globs with no
matching files. Every path setting shares one pattern language: patterns start at
the repository root, `**` enters dot-directories, and `**/node_modules/**` (a
default) ignores nested copies. An `ignore:` list you set replaces the defaults,
so keep the ones your repository still needs. It doesn't search other directories just to explain exclusions.
The JSON output distinguishes files selected for discovery from documents actually
scanned. Use `check` to validate references; `explain` reports discovery and
assembly errors. Invalid configuration reports `E008` instead of a traceback.

`candidates` lists possible missing terms: inline-code spans that are a whole
hyphenated lowercase identifier (`ready-for-agent`), match no term or alias, and
appear in at least `--min-files` live docs (default 2). It reads the same docs as
`check`, minus historical ones, and never writes. Deciding what becomes a record
or an alias is left to the [maintenance skill](skills/maintain-ubiq/SKILL.md).

Use the bundled GitHub Action (`uses: Ltilak13/ubiq@main`) or the
[pre-commit](https://pre-commit.com) hook in `.pre-commit-hooks.yaml`; Markdown, YAML, and JSON changes trigger it.
The [integration skill](skills/apply-ubiq/SKILL.md) covers setup in another repo.

The [spec](docs/spec.md) defines the resolution rules and diagnostics, including
catalog checks and historical-document exceptions. Ubiq checks its own docs.

## Roadmap

The current focus is deterministic checks: readable Markdown, consistent
resolution, and errors that explain how to fix a broken reference.

Later options include a code-symbol map, advisory semantic checks, external-doc
adapters, and editor navigation. Each needs useful results on real repositories
before it becomes a required check.
