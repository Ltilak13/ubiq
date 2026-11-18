# ubiq spec (stage 1 — deterministic linker)

This document is itself checked. Its explicit references must resolve, or
`ubiq check` fails this repo.

## Model

The vocabulary is a set of terms. Each [[term]] (UB-1) is defined by exactly one
[[glossary record]] (UB-2) within its [[namespace]] (UB-3). Documents use terms via
references (UB-4); the linker resolves every [[reference]] against the glossary and emits a
[[diagnostic]] (UB-5) for anything broken. A [[delimiter]] (UB-6) is an extra explicit
wrapper; an [[overlay]] (UB-7) is sidecar frontmatter for a file the linter does not own;
a [[catalog]] (UB-8) is a JSON/YAML inventory of terms that is not itself a glossary.

Resolution rules, in order: an explicit qualified reference resolves within its namespace
only; an explicit unqualified reference resolves across all namespaces and must land on
exactly one [[record]]. Inline Markdown links to registered records or configured
glossary locations resolve by destination, regardless of the visible label.
A missing destination or a file without a defining record is E002.
An id reference resolves against record `id:` fields. Configured
[[delimiter]]s (UB-6) are explicit references with the same rules. An [[overlay]] (UB-7)
is sidecar frontmatter linked to a source file the linter does not own. A [[catalog]]
is an inventory (not a second glossary): entries must resolve, and optional `cover`
globs require every matching record to be listed. Catalog entries resolve by ID
before name; coverage credits only a uniquely resolved record. An ambiguous entry
can produce E003 and leave its candidate records uncovered (E007). Docs listed under `historical`
are scanned for mentions and resolved refs. Unresolved vocabulary links,
`[[old]]`, and `/old-name` do not fail the build.

A glossary glob may set `ns` and `term_field` for every file it matches, so existing
frontmatter (`name:`) can be a record without adding fields to those files.
`only_known: true` on a [[delimiter]] matches a token only if it is already a
glossary name.

## Diagnostics

- `E001` duplicate definition — one name (canonical or alias) claimed by two records in the
  same [[namespace]], or one id claimed twice. The report is the consolidation work order.
- `E002` unresolved reference — an explicit [[reference]] with no defining [[record]].
  Similar known names produce a suggestion for unresolved wiki-links or delimiters.
- `E003` ambiguous reference — a reference resolves to multiple records.
  Qualify names in wiki-links, frontmatter fields, and catalog entries with a namespace.
- `E004` unresolved id — an id-pattern match with no record carrying that id.
- `E005` invalid record — a [[record]] file exists but its frontmatter cannot be parsed
  (strict mode; `frontmatter: lenient` opts into line-based parsing for non-YAML dialects).
- `E006` unresolved field ref — a value in a configured `ref_fields` frontmatter field
  or a [[catalog]] entry with no defining [[record]] by id or name;
  `external_id_patterns` whitelists ids defined outside records.
- `E007` catalog cover gap — a [[record]] matching a [[catalog]]'s `cover` globs is
  not listed in the inventory.
- `W001` orphan term — a [[term]] defined but never used outside its own record. Warning,
  not error: new terms are born orphaned.

## Invariants

Fenced code blocks are never scanned, so documentation of syntax and shell
`[[` tests cannot trip the linker. Wiki-links, id patterns, and mentions skip
inline code as well. Inline Markdown vocabulary links also skip code and images.
Configured [[delimiter]]s *do* match inside backticks —
that is how slash-commands are written. Frontmatter is never scanned as prose,
so field names are not mentions. Plain-prose mentions of a defined [[term]] are
indexed for search and orphan detection but can never fail the build — the
error surface is exactly what the author explicitly marked (wiki-links, Markdown
vocabulary links, delimiters, id patterns, `ref_fields`, and catalogs).
Wiki-links that look like
file paths (`[[GLOSSARY.md]]`, `[[dir/file]]`, `[[./x]]`) are not term
references unless that name is a defined [[term]]. If the target exists in-repo
as markdown, it is pulled into the scan (the `docs:` globs are roots; links are
followed to a fixpoint). Missing wiki-link file targets are not errors because
workspace templates name files outside this repo. Relative markdown links (`[x](./a.md)`)
are followed the same way. Links into configured glossary globs are checked even when
the target no longer exists. Glob `**` matches zero or more directories. A link
to a registered record can follow a symlink outside the repo. Ordinary link
traversal stays inside the repo. URL-encoded paths, fragments, angle-bracket
destinations, and link titles are supported. Reference-style Markdown links
are not vocabulary references. Historical docs are the exception: they are
scanned, but unresolved explicit/Markdown/id/field refs do not fail.

Checks, orphan detection, and `ubiq refs` use the same resolution rules. A
qualified reference credits only the selected namespace. Markdown vocabulary
links count once, without also indexing their label or destination as mentions.
Plain mentions with multiple possible definitions remain searchable in each
namespace. Context output qualifies names when the glossary contains a collision.
