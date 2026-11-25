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
exactly one [[record]]. A colon qualifies a reference only when the text before it
names a [[namespace]] in the glossary; otherwise the colon is part of the name, so a
term such as `ratio:2` stays linkable. Markdown links to registered records or configured
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

## Reference kinds

Each kind of [[reference]] has one policy: the regions it matches in, how it
resolves, what it reports, and whether it links its term for W002.

| Kind | Reported as | Resolves by | Reports | Scans by default | Can scan |
|---|---|---|---|---|---|
| `wiki` | explicit | name, then id | E002 | address, comment | inline_code, address, comment |
| `delimiter` | explicit | name, then id | E002 | inline_code, comment | inline_code, address, comment |
| `markdown` | markdown | destination | E002 | comment | comment |
| `id` | id | id | E004 | comment | inline_code, address, comment |
| `field` | field | id, then name | E006 | frontmatter only | nothing |
| `catalog` | catalog | id, then name | E006, E007 | inventory only | nothing |
| `mention` | mention | name | W002 | prose only | inline_code, address, comment |

Every prose kind also matches plain prose. An address is a link or image
destination, a bare URL or email, or a raw HTML tag. `references:` composes
overrides onto the table, per kind: `severity` (`error`, `warn`, or `off`) and
`scans` (the list of regions, replacing the default). A `warn` kind reports its
codes as warnings, which never fail the check, and an ambiguous ref (E003) takes
its kind's severity too. An `off` kind reports nothing, and its refs stay indexed
for `ubiq refs`. `unlinked_mentions` is shorthand for the mention severity, off by default.

No configuration can contradict a guarantee: a setting that would is E008, and a
test fails if this spec stops stating one. The guarantees are that fenced code
blocks are never scanned, frontmatter is never scanned as prose, definition lines
produce no references, a plain-prose mention can never fail the build, and an
include link that resolves nowhere always fails it (see Composition edges).

## Diagnostics

- `E001` duplicate definition — one name (canonical or alias) claimed by two records in the
  same [[namespace]], or one id claimed twice. The report is the consolidation work order.
- `E002` unresolved reference — an explicit [[reference]] with no defining [[record]].
  Similar known names produce a suggestion for unresolved wiki-links or delimiters.
- `E003` ambiguous reference — a reference resolves to records with different qualified
  names. Records that share one qualified name are E001 instead, since qualifying cannot help.
  Qualify names in wiki-links, frontmatter fields, and catalog entries with a namespace.
- `E004` unresolved id — an id-pattern match with no record carrying that id.
- `E005` invalid record — a [[record]] file exists but its frontmatter cannot be parsed
  (strict mode; `frontmatter: lenient` opts into line-based parsing for non-YAML dialects).
  Unreadable records/catalogs, malformed overlays, duplicate overlay sources, and
  term, alias, `id`, or `ns` values that are not nonempty strings also use E005.
  A null value reads as absent. Malformed declarations never disappear silently:
  a `ref_fields` value that is not a string or list of strings, unparsable
  frontmatter in a document scanned for `ref_fields` (strict mode), and a catalog
  entry that is not a string or number are E005 too.
- `E006` unresolved field ref — a value in a configured `ref_fields` frontmatter field
  or a [[catalog]] entry with no defining [[record]] by id or name;
  `external_id_patterns` whitelists ids defined outside records.
- `E007` catalog cover gap — a [[record]] matching a [[catalog]]'s `cover` globs is
  not listed in the inventory.
- `E008` invalid configuration — invalid YAML, unknown settings, field shapes, regular
  expressions, delimiter or `references:` settings, conflicting glossary rules, or a setting
  that contradicts a guarantee. The message names the field or rules.
- `E009` schema conformance failure — selected frontmatter or structured data violates its declared JSON Schema, or a target is missing.
- `E010` graph integrity failure — declared record coverage, relationships, or source evidence is invalid.
- `W001` orphan term — a [[term]] defined but never used outside its own record. Warning,
  not error: new terms are born orphaned.
- `W002` unlinked mention — a section mentions a [[term]] but no wiki-link, delimiter,
  Markdown vocabulary link, or id reference in that section resolves to it. Reported
  once per term per section, at the first mention. A section starts at an ATX heading
  or the top of the file. Mentions on heading lines, in historical docs, in the term's
  own record, and in overlay sidecars are not reported. Plain-mention suggestions
  apply only to documents whose resolved paths are inside the checked repository.
  Dependency prose reached through symlinks or external paths belongs to its source
  repository. Explicit references in those documents are still checked. By default, link destinations,
  URLs, emails, HTML tags, and HTML comments are not mentions; a mention in another
  link's label counts as linked. Off unless `unlinked_mentions: warn`;
  `unlinked_except` lists terms by name or qualified name.
- `W006` coverage scope — a `coverage.files` pattern matches no file, or a
  `coverage.exclude` glob matches no selected file. Only `ubiq coverage` reports it.
- `E011` include cycle — a [[shared part]] includes itself through Markdown links
  to other parts. The agent would read the same files forever.
- `E012` part input — an include names no value, or an undeclared value, for an
  input its part declares; or a part's `edges.include.inputs` field is not a
  mapping of input names to lists of values.
- `W003` blocked invoke — an invoke edge targets a record whose
  `edges.invoke.blocked_by` field is true, so the model cannot invoke it.
- `W004` install layout — a link that leaves an `edges.install` directory resolves
  in the source tree or in the installed layout, but not both; a link into another
  repository's installed directory resolves in neither; a `#fragment` names no
  heading in the installed target; or an `edges.external` repository cannot be read.
- `W005` drift — a record in an `edges.drift.ns` namespace explicitly references
  another such record without an edge between them, or declares an invoke, route, or
  reference edge to one its text never names.

`references:` sets the severity of the codes a reference kind reports, and
`edges.<kind>.severity` that of an edge kind's constraints: E011, E012, W003, and
W005 for a declared edge (see Composition edges).

## Composition edges

A [[composition edge]] connects the record that owns a document to a record it reuses.
A document's owner is the record defined in it, the record its overlay sources,
or the single record defined directly in an enclosing directory (a skill's sibling files).
The repository root never owns by directory. When `edges.install` is set, only
installed directories do.
Documents with no owner contribute no edges.

| Kind | Comes from | Constraint |
| --- | --- | --- |
| `invoke` | a value in an `edges.invoke.fields` field (default: `ref_fields` minus route and reference fields) | W003 when the target sets `blocked_by`; W005 when the source's text never names the target |
| `route` | a value in an `edges.route.fields` field (default: none) | W005 when the source's text never names the target |
| `reference` | a value in an `edges.reference.fields` field (default: none) | W005 when the source's text never names the target |
| `include` | a Markdown link to a record in an `edges.include.ns` namespace (default: `part`), or one that lands on another repository's record once installed | E011 on a cycle; E012 on a part input |

Invoke and include edges are dependencies: the source needs the target to run.
A route edge points elsewhere without depending on the target, as in "not for X;
use Y". A reference edge identifies an informational example, comparison, or caller
without declaring a dependency or directing the reader to another workflow.
Route and reference edges are shown in graph walks but are not followed.
Each configured edge field must also be in `ref_fields`, so every target resolves
(E006). A field may have only one edge kind; either
mistake is E008. Unresolved and ambiguous references make no edge. Invoke cycles
are allowed: two workflows can hand off to each other.

`edges.invoke.severity`, `edges.route.severity`, `edges.reference.severity`, and `edges.include.severity`
(`error`, `warn`, or `off`) set the severity of the codes in that kind's
Constraint column, the way `references:` does for a reference kind. Unset, each
code keeps its letter: E codes fail the build and W codes warn. A code moved off
its letter shows its severity next to it, as in `W003 (error)`. W004, and W005
for a missing edge, check links rather than edges, so no edge kind sets them.

A Markdown link from a live document is an include link when its destination is
a record in an `edges.include.ns` namespace or a path that a glossary rule with
such an `ns` matches. An include link that resolves nowhere fails the build
under any configuration. It is E002 at the `markdown` kind's severity, so while a
glossary rule sets an include namespace, `references.markdown.severity` other
than `error` is E008. No edge kind sets E002.

A part lists enumerated inputs in its `edges.include.inputs` field (default
`inputs`), such as `inputs: {mode: [new, existing]}`. Each include of that part
names one value per input as a code span followed by the input name, after the
link and before the next link or the end of the line: ``Follow
[checkout](../_shared/checkout.md) in `existing` mode.`` A missing or undeclared
value is E012.

`edges.drift.ns` turns on W005 for records in those namespaces. Only wiki-links,
delimiters, and Markdown links count as references for a missing edge; plain
mentions satisfy a declared edge but never require one. An edge in either
direction counts, so a skill may name its callers. Overlay prose describes edges,
so it counts for neither direction.

`edges.install` globs select files whose directory installs as a sibling under
one root, keeping its name. A link leaving such a directory is resolved twice:
in the source tree, and textually from the installed path, the way an agent
normalizes `..`. Links inside the directory are the same in both layouts. W004
covers every Markdown link to a Markdown document, part or not; links to scripts
and other files, and paths written in code spans, are not checked. Two installed
directories with the same name would install at one path, which is also W004.
When such a link resolves once installed and has a `#fragment`, the fragment must
match a heading slug (GitHub style) of the installed target.

`edges.external` lists other repositories (paths relative to the root, absolute,
or starting with `~`) whose own `edges.install` directories join the same install
root. A local directory wins a name over an external one, the way installers let
a personal skill override a clone. A relative link can reach another repository
only once installed, so W004 checks links that land in an external directory
instead of E002, and reports them only when they resolve in neither layout. An
external repository that is missing, has invalid configuration, or installs
nothing is one W004; while it is unreadable, links to directory names that nothing
here installs are not checked, so CI without the other checkout does not fail.
Include links are the exception: one that does not resolve in the source tree
stays E002 unless it resolves once installed.

A link that lands, once installed, on a file that another repository's record
owns (by that repository's own owner rules) is an include edge to that record,
with or without a `#fragment`. No field here can name that record, so the link
is the only declaration, and it resolves only once installed, where the agent
reads the text in place. Because it is an include, the target's `blocked_by`
setting does not apply. Inside one repository, a link to a record outside
`edges.include.ns` stays a reference even with a `#fragment`: files often link
each other's sections without a loop, and a record-level edge cannot tell which
section the agent reads, so E011 and overlap's `restates_include` would report
relations that do not hold. Another repository's records are named
`<repository>/<ns>:<term>`, where `<repository>` is its directory name, or its
full path when two `edges.external` entries share one, so they never collide with
a record here. Ubiq reads only that repository's glossary rules and overlays, one
frontmatter per record: not its other documents, and not its edges, so a walk
ends at its record. E011 therefore finds no cycle through it, and E012 checks the
inputs of parts here only. W005 counts the edge as declared, but references here
resolve only to records here, so it never asks for an edge to another
repository's record; a glossary stub that stands for an upstream skill is a
separate record. While a repository is unreadable, links into it make no edge.

`graph --json` returns `target`, `view` (`dependencies` or `callers`), `count`,
and `edges`, each with `kind`, `source`, `target`, `file`, and `line`. Without a
target it lists every edge. `--callers` follows incoming edges; `--depth` limits
hops; `--kind` filters by kind. A walk shows route edges where it reaches them
but does not follow them. A target that names no single record exits 1. A name
defined here wins, the way a local directory wins once installed; a name nothing
here defines resolves in `edges.external` repositories, and `<repository>/<name>`
names a record there directly. `--callers` from such a record lists the records
here that include it, then their callers.

`overlap --json` returns `unit`, `min_similarity`, `count`, and `clusters`. Live
documents with an owner split into paragraphs, or lines with `--unit line`,
skipping frontmatter, fences, and headings. Blocks with fewer than 10 words (7 for
lines) are skipped. Two blocks from different owners join when their 4-word
shingle Jaccard similarity reaches `--min-similarity` (default 0.5) or one
contains 80% of the other's shingles. Clusters with the same set of owners merge.
Links to shared parts are blanked before comparison: an include is the call,
not repeated prose, so callers of one part do not cluster with each other.
Each cluster has `records`, `restates_include` (one owner includes another
owner's part), `restates_composite`, and `blocks` with `record`, `file`, `line`,
and `text`. `restates_composite` lists the composites in the cluster: owners with
invoke edges whose compared blocks are all in the cluster. Each suggested caller
must directly match every compared block of the composite. Each entry has `composite`, `records` (the other owners whose
invoke edges contain all of the composite's and that do not invoke it yet, so
they could invoke it instead), and `blocked`. `blocked` is true when the
composite sets its `edges.invoke.blocked_by` field, so an invoke edge to it
would report W003 and the fix is the author's call. The list is empty when no
composite applies. The command exits 0 unless configuration or assembly fails,
and never writes files.

## Invariants

Fenced code blocks are never scanned, so documentation of syntax and shell
`[[` tests cannot trip the linker. By default, wiki-links, id patterns, and mentions
skip inline code as well. Markdown vocabulary links also skip code and images.
Fences may have up to three leading spaces and at least three backticks or tildes.
The closing marker must use the same character and be at least as long. An unclosed
fence hides the remaining document. Inline code spans use matching backtick runs.
By default, configured [[delimiter]]s *do* match inside backticks —
that is how slash-commands are written. They skip Markdown link and image
destinations, bare URLs, and raw HTML tags, which hold paths such as `(/setup.md)` and
`href="/install"`, not commands. Id patterns skip the same addresses, so
a ticket URL is not an id reference. Frontmatter is never scanned as prose,
so field names are not mentions. Record, overlay, reference-field, and catalog
YAML keeps scalars as text: `No`, `007`, and `1.10` stay strings rather than
becoming a boolean or numbers. Null still reads as absent. Plain-prose mentions of a defined [[term]] are
indexed for search and orphan detection but can never fail the build — the
error surface is exactly what the author explicitly marked (wiki-links, Markdown
vocabulary links, delimiters, id patterns, `ref_fields`, catalogs, and configured schemas).
A mention matches a name as written: a name with no spaces (`grill-me`) needs a
hyphen or underscore between its words, so the phrase "grill me" is prose; a
spaced name (`issue tracker`) matches with any of space, hyphen, or underscore.
A name that starts or ends in punctuation, such as `C++` or `.NET`, matches where no
letter, digit, or underscore touches it, so `ASP.NET` is not a mention of `.NET`.
Wiki-links that look like
file paths (`[[GLOSSARY.md]]`, `[[dir/file]]`, `[[./x]]`) are not term
references unless that name is a defined [[term]]. If the target exists in-repo
as markdown, it is pulled into the scan (the `docs:` globs are roots; links are
followed to a fixpoint). Missing wiki-link file targets are not errors because
workspace templates name files outside this repo. Relative markdown links (`[x](./a.md)`)
are followed the same way. Links into configured glossary globs are checked even when
the target no longer exists. Every path setting uses one pattern language: a
pattern starts at the repository root unless it is absolute; `*`, `?`, and `[...]`
match within one path segment, dotfiles and dot-directories included; and `**`
matches zero or more directories. Ignore patterns follow the same rules, so
`**/node_modules/**` ignores every copy and `node_modules/**` only the one at the
root. A configured `ignore` list replaces the defaults (`**/.git/**`, `**/node_modules/**`,
and `**/.venv/**`). A repository that sets its own list must repeat each default it still needs. Unknown settings are E008 at any level, with a
suggestion for a likely typo. A link
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
aliases, and file. References include kind, policy (the kind's row in the
reference-kind table), file, line, raw text, target, optional Markdown
destination, and historical status. Repeatable `--kind` selects the union of the
named kinds; it accepts reported kinds and policy names, so `explicit` selects
both `wiki` and `delimiter`. An unknown query exits 1 with empty arrays
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
is a name that the docs mark as vocabulary, that resolves to no term or alias,
and that is used in at least `min_files` scanned non-historical docs.
`candidate_shapes` selects the markup; the default is `[code]`:

- `code`: an inline code span, outside fences and frontmatter, whose whole
  content is a hyphenated lowercase identifier (`[a-z][a-z0-9]*(-[a-z0-9]+)+`).
- `bold`: a one-line `**…**` or `__…__` span in prose (outside fences,
  frontmatter, reference definitions, and inline code) whose content, minus a
  trailing `:` or `.`, is one to four words of letters and digits joined by
  spaces or hyphens. `__` with a word character on its outer side is literal.

Names that normalize alike are one candidate, named by the first spelling found
(by path, then shape). Each has `name`, `files`, `occurrences`, and `locations`
(each file and line once). Candidates sort by file count, descending, then
normalized name. An unknown shape or an empty list is E008. The command exits 0
unless configuration or assembly fails, and never writes files.

All JSON commands use root-relative paths inside the repository and
absolute paths outside it. Configuration failures use the check diagnostic
JSON envelope and exit 1.

## Change review

`ubiq impact --since <rev>` and `ubiq compare --since <rev>` review a change
against a baseline. Neither changes the working tree, the index, or refs, and
neither replaces `ubiq check`: CI keeps
running the full checker on the head.

**Baseline.** The baseline is the committed tree at `git merge-base <rev> HEAD`,
the base a pull request diff uses, checked out with the same filters as a
working tree. Export attributes such as `export-ignore` do not apply. The head is the working tree, including
uncommitted and untracked files. Ubiq builds each side with that side's own
`ubiq.yaml`. Files git ignores exist only at the head and are never changes.
Paths outside the repository are read in their current state for both sides:
`edges.external` repositories, and the targets of committed symlinks that leave it.
A `<rev>` that names no commit, a root outside a git work tree, or a side whose
configuration cannot load is an invalid review: the command prints an
`error` and exits 2. It never reports an empty change or zero findings instead.

**Changed files.** Git's name-status diff from the baseline to the working
tree, with rename detection, plus untracked files. Each has `status` (`added`,
`modified`, `deleted`, or `renamed`), `file`, and, for a rename, `from`. A file
moved into the root from outside it is `added`; one moved out is `deleted`.

**Changed records.** A record changes when a changed file is its record file,
its overlay, or a file it owns by directory (see Composition edges). Records
are identified by qualified name. A changed record has `record`, `change`, and
`files`, the changed files it owns:

- `added`: only the head defines it.
- `deleted`: only the baseline defines it.
- `edited`: both sides define it.
- `renamed`: the baseline record is gone, and the head record that replaces it
  is defined in the same file, or in the file git reports as its rename. It
  carries `from`, the baseline qualified name, and is not also added or deleted.
- `unknown`: a changed file defines the record on one side and reports E005
  on the other, so ubiq cannot tell what that side defines. It is never
  reported as added or deleted.

**Affected records.** An affected record is not changed itself but depends on
a changed record through invoke or include edges, at any depth (`--depth`
limits hops). Route and reference edges declare no dependency, so they never
make a record affected. Callers of an added or edited record come from the head
graph; callers of a deleted record come from the baseline graph, since no head
edge can reach it. A renamed record is walked in both: head callers of its new
name, and baseline callers of its old name, which a rename can break. An
`unknown` record is walked in both graphs under its name. Each affected record has `record` and `via`, the
shortest edge path from it to a changed record. Each edge has `kind`, `source`,
`target`, `file`, `line`, and `side` (`head` or `baseline`). Among equally
short paths, the head graph wins, then the path whose records nearest the
change sort first by qualified name.

**Completeness.** `complete` is false when dependency data is missing on either
side: an `edges.external` repository is unreadable, or a document or record
reports E005, so its edges are unknown. `incomplete` lists each reason with
`side`, `file`, and `reason`. Missing data is reported, never read as "no
callers".

`impact --json` returns `baseline` (`rev` and `commit`), `complete`,
`incomplete`, `changed_files`, `changed`, and `affected`. Changed files sort by
`file`; changed and affected records sort by qualified name. The readable output
lists the changed records, then each affected record with its path. It exits 0
unless the review is invalid.

**Finding comparison.** `compare` runs the checker on both sides. A finding's
identity is its `code`, its `file`, and its `message`, not its line, so moved
text stays the same finding. A baseline file that git reports as renamed takes
its head path, a file outside the root is named by its resolved absolute path,
and absolute baseline paths in messages are rewritten to the head
root. Identical findings are counted: two at the baseline and three at the head
are two unchanged and one new. Occurrences pair in line order, so the extra ones are the latest lines. Each finding is `new` (head only), `resolved`
(baseline only), or `unchanged`. If either side fails before checking (an
invalid baseline, or configuration that cannot load), `status` is
`unavailable` with a `reason`, the command exits 2, and no finding lists are
printed. A failed check is never zero findings.

`compare --json` returns `baseline`, `status` (`ok` or `unavailable`), `counts`
(`new`, `resolved`, `unchanged`), and `new`, `resolved`, and `unchanged`, each a
list of findings with `code`, `severity`, `file`, `line` (the head line, or the
baseline line for a resolved finding), and `message`. Lists sort by file, line, code,
then message. `compare --markdown`
prints a PR-ready summary: one line of counts, then new and resolved findings.
Unchanged findings appear only as a count. `compare` exits 1 when a new finding
is an error, 2 when unavailable, and 0 otherwise.

## Explicit type schemas

The opt-in `schemas` list binds local Draft 2020-12 schemas to document or frontmatter globs.
Invalid schemas and bindings report E008. Instance failures report E009.
The optional `x-ubiq` extension checks graph integrity and registered source coverage with E010.
These explicit contracts add validation without changing lexical vocabulary parsing or reference policies.
See [native schema validation](schema-validation.md) for the contract and limits.

## Coverage

`ubiq coverage` reports how much explicitly selected repository content has
typed metadata. It measures declared coverage and integrity, not semantic
correctness. `ubiq check` remains the validation gate.

```yaml
coverage:
  files: ["src/**/*.py", "services/*.yaml"]   # required, nonempty
  exclude:
    - glob: "src/vendor/**"
      reason: "Vendored upstream copy"         # required
  min_typed_percent: 100                       # optional, 0 through 100
  no_regression: true                          # optional, default false
```

Patterns are repository-relative. A missing `reason`, a repeated exclusion
glob, or any other malformed field is E008. Without a `coverage` section the
command reports `unavailable` with setup guidance and exits 2; every other
command behaves as before.

**Scope.** Selected files are the unique existing files that `files` matches,
minus `ignore` and files git ignores. Excluded files are selected files that
an `exclude` glob matches; each keeps every matching glob and reason. Eligible
files are selected files that are not excluded. They are the denominator. A
file is identified by its resolved repository-relative path, so overlapping
globs and in-repository links count it once. A link that resolves outside the
repository is listed under `scope.outside` and never counted. A pattern or
exclusion that matches nothing is W006. `suggestions` lists discovered assets
(`ubiq discover`) outside the selection; they never join the denominator.

**Typed files.** An eligible file is typed when a `schemas` binding selects it
directly, or when a record in an `x-ubiq` collection names it as `source`. Each
typed file lists its supporting locations in `via`: the binding, or the data
file, JSON pointer, and record id. A glossary record is not typed by being
registered. `conformance` is `invalid` when any supporting file fails its
schema, so a typed but invalid file never reads as healthy. E008, E009, and
E010 diagnostics for the bindings appear under `diagnostics`.

**Completeness.** A measurement is incomplete when typing cannot be known: a
bound schema cannot load, an `x-ubiq` data file cannot load, or a collection or
record source cannot be read. `incomplete` lists each `file` and `reason`, the
status is `incomplete`, and the command exits 2. Missing data never counts as
untyped or as passing.

`coverage --json` returns `version` (1), `status` (`ok`, `incomplete`, or
`unavailable` with a `reason`), `complete`, `incomplete`, `scope` (`files`,
`exclude` with per-glob file counts, `outside`), `counts` (`selected`,
`excluded`, `eligible`, `typed`, `untyped`, `nonconforming`), `ratio` (`typed`
and `eligible`), `typed_percent`, `files`, `suggestions`, and `diagnostics`.
`typed_percent` is null when no file is eligible, and is truncated, not
rounded, to two decimals. Each file has `file` and `classification` (`typed`,
`untyped`, or `excluded`); excluded files carry `exclusions`, and the others
`via` and `conformance`. Files, locations, and diagnostics sort
deterministically.
