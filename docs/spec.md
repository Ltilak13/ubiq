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
exactly one [[record]]. Markdown links to registered records or configured
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

A source path is registered once, including symlink aliases. Equivalent matching
glossary rules deduplicate; conflicting effective `term_field` or `ns` rules
report E008 with both rules. A file's own namespace does not override a conflict
between its selection rules. Distinct overlays targeting one resolved source
report E005; consolidate them instead of relying on filename order. Malformed
overlay metadata and missing sources also report E005.

An overlay on a source without a defining term is valid when it contains at least
one configured `ref_fields` key and no `term`, `ns`, `aliases`, or `id` keys.
This applies whether a glossary glob selects the source or not. An empty reference
list is valid. The overlay creates no term. Its reference fields are checked
normally, so unresolved targets report E006. Other overlays still require a
defining term in the source or a nonempty `term` in the overlay.

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
  Unreadable records/catalogs, malformed overlays, and duplicate overlay sources also use E005.
- `E006` unresolved field ref — a value in a configured `ref_fields` frontmatter field
  or a [[catalog]] entry with no defining [[record]] by id or name;
  `external_id_patterns` whitelists ids defined outside records.
- `E007` catalog cover gap — a [[record]] matching a [[catalog]]'s `cover` globs is
  not listed in the inventory.
- `E008` invalid configuration — invalid YAML, field shapes, regular expressions,
  delimiter settings, or conflicting glossary rules. The message names the field or rules.
- `W001` orphan term — a [[term]] defined but never used outside its own record. Warning,
  not error: new terms are born orphaned.
- `W002` unlinked mention — a section mentions a [[term]] but no wiki-link, delimiter,
  Markdown vocabulary link, or id reference in that section resolves to it. Reported
  once per term per section, at the first mention. A section starts at an ATX heading
  or the top of the file. Mentions on heading lines, in historical docs, in the term's
  own record, and in overlay sidecars are not reported. Link destinations, URLs,
  emails, HTML tags, and HTML comments are never mentions; a mention in another
  link's label counts as linked. Off unless `unlinked_mentions: warn`;
  `unlinked_except` lists terms by name or qualified name.

## Invariants

Fenced code blocks are never scanned, so documentation of syntax and shell
`[[` tests cannot trip the linker. Wiki-links, id patterns, and mentions skip
inline code as well. Markdown vocabulary links also skip code and images.
Fences may have up to three leading spaces and at least three backticks or tildes.
The closing marker must use the same character and be at least as long. An unclosed
fence hides the remaining document. Inline code spans use matching backtick runs.
Configured [[delimiter]]s *do* match inside backticks —
that is how slash-commands are written. They skip Markdown link and image
destinations, bare URLs, and raw HTML tags, which hold paths such as `(/setup.md)` and
`href="/install"`, not commands. Id patterns skip the same addresses, so
a ticket URL is not an id reference. Frontmatter is never scanned as prose,
so field names are not mentions. Record, overlay, reference-field, and catalog
YAML keeps scalars as text: `No`, `007`, and `1.10` stay strings rather than
becoming a boolean or numbers. Null still reads as absent. Plain-prose mentions of a defined [[term]] are
indexed for search and orphan detection but can never fail the build — the
error surface is exactly what the author explicitly marked (wiki-links, Markdown
vocabulary links, delimiters, id patterns, `ref_fields`, and catalogs).
A mention matches a name as written: a name with no spaces (`grill-me`) needs a
hyphen or underscore between its words, so the phrase "grill me" is prose; a
spaced name (`issue tracker`) matches with any of space, hyphen, or underscore.
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
destinations, and link titles are supported. Full `[label][id]`, collapsed `[id][]`,
and shortcut `[id]` links use document-local definitions of the form
`[id]: destination "optional title"`. Definitions must fit on one line, with at
most three leading spaces. Labels ignore case and collapse whitespace; the first
definition wins. A usage without a definition remains plain prose. Definition
lines are metadata: they produce no references, and unused definitions do not
cause traversal. Checked references report the usage line, not the definition
line. Nested link labels and multiline definitions are outside the supported
Markdown subset. Historical docs are the exception: they are
scanned, but unresolved explicit/Markdown/id/field refs do not fail.

Checks, orphan detection, and `ubiq refs` use the same resolution rules. A
qualified reference credits only the selected namespace. Markdown vocabulary
links count once, without also indexing their label or destination as mentions.
Plain mentions with multiple possible definitions remain searchable in each
namespace. Context output qualifies names when the glossary contains a collision.


## Command output

`refs TERM --json` returns `query`, `definitions`, `references`, and `count`.
Definitions include the canonical term, namespace, qualified name, optional ID,
aliases, and file. References include kind, file, line, raw text, target,
optional Markdown destination, and historical status. Repeatable `--kind`
selects the union of the named kinds. An unknown query exits 1 with empty arrays
and an `error` message. Without flags, text output retains its existing format.
Catalog locations retain their existing one-based inventory index; they are not
source-file line numbers.

`explain --json` returns `files`, `unmatched`, and assembly `diagnostics`.
Each file has its path, inclusion status, existence, scanned-document status,
historical classification, and discovery reasons. Reasons identify the matching
pattern or source link/overlay; ignored candidates name the ignore rule.
Unmatched patterns have no file matches, including before ignore filtering.
Discovery records all encountered reasons, including links back to already
visited files, without rescanning cycles. It does not enumerate unrelated files.
Reference errors belong to `check`; `explain` fails on configuration or assembly
errors.

`candidates --json` returns `min_files`, `count`, and `candidates`. A candidate
is an inline code span, outside fences and frontmatter, whose whole content is a
hyphenated lowercase identifier (`[a-z][a-z0-9]*(-[a-z0-9]+)+`) that resolves to
no term or alias, used in at least `min_files` scanned non-historical docs. Each
has `name`, `files`, `occurrences`, and `locations` (each file and line once).
Candidates sort by file count, descending, then name. The command exits 0
unless configuration or assembly fails, and never writes files.

All JSON commands use root-relative paths inside the repository and
absolute paths outside it. Configuration failures use the check diagnostic
JSON envelope and exit 1.
