---
name: composable-knowledge-goal
status: in-progress
criteria:
  AC1:
    assessment: partial
    support:
    - feature: Registered shared parts
      implementation:
        path: src/ubiq/graph.py
        anchor: def build_edges(
      check:
        path: tests/test_graph.py
        anchor: def test_invoke_and_include_edges_with_callers(
    gap: Existing tests support this criterion. This migration does not re-audit the complete
      goal.
  AC2:
    assessment: partial
    support:
    - feature: Typed composition edges
      implementation:
        path: src/ubiq/graph.py
        anchor: def build_edges(
      check:
        path: tests/test_graph.py
        anchor: def test_route_edges_are_shown_but_not_followed(
    gap: Graph behavior has tests. Full criterion review remains pending.
  AC3:
    assessment: partial
    support:
    - feature: Pinned overlap survey
      implementation:
        path: src/ubiq/overlap.py
        anchor: def find_overlap(
      check:
        path: tests/test_survey.py
        anchor: def test_public_collection_overlap_is_pinned(
    gap: The personal repository case depends on a separate local checkout.
  AC4:
    assessment: partial
    support:
    - feature: Installed link validation
      implementation:
        path: src/ubiq/graph.py
        anchor: def _install_layout(
      check:
        path: tests/test_graph.py
        anchor: def test_links_that_resolve_in_only_one_layout_warn(
    gap: This test covers layout differences. Invocation policy also needs review.
  AC5:
    assessment: unassessed
    support: []
    gap: Criterion needs a recorded review against its acceptance text.
  AC6:
    assessment: partial
    support:
    - feature: Composition constraints
      implementation:
        path: src/ubiq/graph.py
        anchor: def _include_cycles(
      check:
        path: tests/test_graph.py
        anchor: def test_include_cycle_fails(
    gap: Cycle evidence is partial. Review the remaining nested and threshold cases.
  AC7:
    assessment: unassessed
    support: []
    gap: Broader composition needs implementation evidence and a recorded review.
  AC8:
    assessment: unassessed
    support: []
    gap: Broader composition needs implementation evidence and a recorded review.
  AC9:
    assessment: unassessed
    support: []
    gap: Broader composition needs implementation evidence and a recorded review.
---

# Goal: composable knowledge

Prior acceptance evidence is recorded; see the last section. Shared parts
register as records with configuration alone. `ubiq graph` shows invoke, include,
and route edges, and `ubiq overlap` reports repeated text. `ubiq check` reports
include cycles (E011), part inputs that an include does not name (E012), invokes
the model can't follow (W003), links that break once installed, across
repositories too (W004), and drift between references and edges (W005).

## Objective

Let repositories compose knowledge from records with stable identities, explicit
contracts, and typed relationships. Keep each shared rule in one authoritative
place. Skills are one application alongside goals, policies, decisions, and ideas.

Ubiq stays deterministic. It checks declared structure and reports broken edges
and repeated text. Maintainers decide what becomes a shared part.

## Scope and relationship semantics

The skill examples and AC1–AC6 retain their original scope and evidence.
They establish a concrete foundation, not proof of support for every record type.
AC7–AC9 define the broader outcomes and remain unassessed.

A [[composition edge]] must define its meaning and which constraints apply. Other relationships can organize knowledge without implying reuse or execution.
The following relationships are proposed domain semantics, not new built-in edge kinds:

| Source | Relationship | Target | Meaning |
| --- | --- | --- | --- |
| Goal | Decomposes into | Subgoal | Part of the desired outcome, with an explicit completion rule |
| Goal | Is constrained by | Principle or policy | A condition that applies while pursuing the outcome |
| Goal | Requires | Quality or trait | A property with observable acceptance criteria |
| Goal | Is motivated by | Idea or hypothesis | Rationale that does not establish completion |
| Acceptance criterion | Is supported by | Evidence | Grounds an assessment within a stated scope |
| Skill | Contributes to | Goal | A procedure that can help achieve the outcome |

A moral commitment can be recorded as a principle. Checks can establish declared
constraints and evidence links, but cannot establish moral correctness.
The [contracts and evidence goal](checkable-contracts-evidence-goal.md) owns that validation boundary.

Records resemble objects, schemas resemble contracts, and shared procedures resemble
functions with inputs. Links do not execute prose. Inclusion, invocation, and an
informational reference require different rules. Decomposition does not imply that
completing all children automatically completes the parent.

The [domain model goal](domain-schema-goal.md) owns identities, types, and format support.
A file extension does not determine whether a record can participate in composition.

## Vocabulary

A skill reuses other logic in one of three ways:

| Way | Example | Ubiq today |
| --- | --- | --- |
| Invoke another skill | "call the Skill tool for `grilling`", `/commit-slices` | Invoke edge when the record or its overlay declares it in `uses` |
| Include a shared part | `[PR scope](../_shared/pr-scope.md)` | Include edge from the link to a registered part; inputs checked |
| Copy the text | the same precondition pasted into six skills | `ubiq overlap` clusters it |

Text can also point at a skill without reusing it: "not for X; use Y". A route
edge, declared in a field such as `routes`, records that relation so it is
neither mistaken for a dependency nor reported as drift.

A [[shared part]] holds one procedure, policy, or precondition that several skills
follow. Skills include it by link. Nobody invokes it on its own.

A [[composition edge]] connects a skill or part to what it reuses. An invoke edge
runs another skill as its own step, so the target's invocation policy applies.
An include edge tells the agent to read a part and follow it in place, so the
link has to resolve wherever the skill is installed. Copying is what this goal
removes.

## Evidence from two repositories

In November 2026 we surveyed two skill repositories that already pass
`ubiq check`: a personal repository that keeps shared parts in `skills/_shared/`,
and a clone of the public `mattpocock/skills` collection. A throwaway script
compared word shingles between paragraph blocks of different skills.

- The public collection has 11 clusters of near-duplicate text. The largest is a
  tracker precondition repeated in six skills. The personal repository has almost
  none. One of its skills restates a step from a part it already includes, and
  another restates a step from a part it could include.
- `triage`, `wayfinder`, and `improve-codebase-architecture` declare both of the
  `uses` edges that make up `grill-with-docs`, and `triage` and `wayfinder`
  restate its one-line body four times between them. They can't invoke it,
  because `grill-with-docs` sets `disable-model-invocation: true`.
- Include paths break in one of two layouts. The personal repository's
  `../_shared/` links resolve only when the path follows the installed symlink.
  The public collection's `../retro/SKILL.md` link resolves only from the
  installed directory, because the source tree keeps the two skills in different
  buckets. `ubiq check` passes both.
- Several skills mention other skills they don't declare in `uses`. Some of those
  mentions are dependencies. Others are routing, such as "not for X; use Y".

A trial on a copy of the public collection registered `skills/_shared/*.md` with
`ns: part` and extracted two parts. No code changed. The six include links became
checked references that fail with `E002` when the part moves, `ubiq refs
part:tracker-setup` listed every caller, and the overlap clusters dropped from 11
to 7.

## Register shared parts

A glossary rule registers parts, with a naming field and a namespace such as
`part`. Every link to a part is then a checked reference. This works today and
needs a regression test so it stays true.

Some parts take an input. `pr-checkout.md`, for example, runs in `new`,
`existing`, or `branch` mode. The part lists its enumerated inputs in frontmatter
(`inputs: {mode: [new, existing, branch]}`), and each include names one value as a
code span followed by the input name, the way callers already wrote it: ``Follow
[PR checkout](../_shared/pr-checkout.md) in `existing` mode.`` A missing or
undeclared value is E012. Ubiq checks the field's shape itself; a repository
that wants more, such as required inputs or descriptions, binds a frontmatter
schema to its parts through the [schema change workflow](../schema-workflow.md) like
any other [[domain-schema]].

## Show one graph with typed edges

Invoke edges come from `uses` and any other field configured for invocation.
Route edges come from fields configured for routing. Include edges come from links
to part records. Authors shouldn't declare an
include twice, once as a link and once in metadata, because the two copies drift.

Each edge kind is a policy: what declares the edge, how its target resolves, and
which constraints apply. Kinds compose the same way reference kinds do, so a
repository can add a kind without new branching in the checker. Queries return
dependencies and callers, filtered by kind, with the declaration location of each
edge.

Cycles follow the edge's meaning. An include cycle sends the agent around the
same files forever, so it is an error. An invoke cycle can be legitimate, as when
two workflows hand off to each other, so ubiq allows it. A route edge is not a
dependency, so graph walks show it but do not follow it.

## Find overlap

A new advisory command, tentatively `ubiq overlap`, reports repeated text and
never fails the check, like `candidates`. It splits skill files into blocks,
skips frontmatter and fenced code, and compares word shingles between blocks from
different skills. Similar blocks form clusters, and each cluster lists its
locations and the number of skills it spans. The algorithm uses only the standard
library, gives the same output for the same input, and has configurable
thresholds with defaults.

Overlap labels two cases separately. A block that restates text from a part its
skill already includes is the strongest signal, since the fix is to delete it. A skill
whose invoke edges contain all of a composite skill's edges, and whose text
repeats that composite, should probably invoke the composite.

## Check that edges can be followed

An invoke edge fails when the target can't be invoked by the caller, for example
a model-reachable skill that uses a skill marked user-invoked only. Harnesses name
this setting differently, so the field comes from configuration.

An include edge must resolve from where the skill is installed as well as from
the source tree. That needs a declared install layout, for instance "each
`skills/*/` directory becomes a sibling under one root, and parts install at
`<root>/_shared/`". Ubiq reports links that resolve in only one layout.

A skill can also include part of another repository's skill. `breakdown` in the
personal repository applies section 3 of `to-tickets` from the public collection,
which it cannot invoke because `to-tickets` is user-invoked only. With
`edges.external` naming the other checkout, a link such as
`../to-tickets/SKILL.md#3-draft-vertical-slices` resolves through that
repository's installed directories, its heading is checked, and a missing checkout
in CI leaves such links unchecked instead of failing. The link is also an include
edge to that repository's record, so `ubiq graph` shows
`skill:breakdown -include-> skills/skill:to tickets` with its file and line.
Four decisions shape that edge:

- Names. Both repositories define `code-review`, and the installer lets the local
  one win the directory. The other repository's records are therefore named
  `<repository>/<ns>:<term>`, and a query resolves a bare name here first, the
  same way the installer does.
- Fragments. Across repositories, every link to a record is an include, because
  no field here can name that record. Inside one repository, a `#fragment` does
  not make a link to a skill an include. In the personal repository,
  `triage-pr-comments/gh-commands.md` and `live-input.md` link each other's
  sections, which E011 would read as a cycle between two records. Also,
  `idea-to-pr` links the post-comment review section of `triage-pr-comments` and
  repeats a line from another section, which overlap would label as restating an
  include.
- Callers and drift. `--callers` from the other repository's record lists the
  skills here that include it. A walk ends there, because ubiq does not read that
  repository's edges. W005 counts the edge as declared, but it never asks for an
  edge to that record, because references here resolve only to records here.
- Cost. Ubiq reads the other repository's glossary rules and overlays, one
  frontmatter per record. It does not scan its other documents.

Severity is configurable per edge kind. `edges.include.severity`,
`edges.invoke.severity`, and `edges.route.severity` set the severity of that
kind's constraints: E011 and E012, W003, and W005 for a declared edge. An include
link that resolves nowhere still fails under any configuration. The spec states
this as a guarantee, enforced like the existing ones: the link is E002 at the
`markdown` kind's severity, so `references.markdown.severity: warn` reports
`E008` while a glossary rule sets an include namespace. Another repository's
directories do not excuse it either, even when that repository is unreadable.

## Detect drift

W005 warns when a skill references another skill without an edge, and when it
declares an edge it never names. It depends on typed relations: without route
edges, routing text ("not for X; use Y") reads as a missing dependency and buries
the real findings. Only explicit references can be missing an edge, because plain
words such as "research" match skill names; any mention satisfies a declared edge.
Both records must be in `edges.drift.ns`, and an edge in either direction counts,
so a skill may name its callers.

On a scratch copy of the personal repository at the surveyed commit, a first
version reported 32 findings, 26 of them from glossary definitions and rules
rather than skills. Scoped to skills, with reverse edges counting, it reports 4:
one routing reference, two caller references with no edge either way, and one
declared edge the text never names. On the refactor branch of the public
collection it reports 38 (43 at the surveyed commit, before five references to
`/setup-matt-pocock-skills` moved into the extracted part): 26 from `ask-matt`, a
router that names every skill and would declare them as routes, and 6 edges
named only inside code spans, which `references.mention.scans: [inline_code]`
resolves.

## Support the refactor loop

The maintenance skill drives the change, and ubiq supplies the evidence:

1. Run overlap and pick clusters that hold a rule which must change together.
2. Extract a part, or replace the copies with an invoke edge when the shared text
   only composes other skills.
3. Replace each copy with an include link. Keep caller-specific differences in
   the caller.
4. Run `ubiq check`, then overlap again to confirm the cluster is gone, and
   inspect the new edges in the graph.
5. Report clusters left alone, with the reason: coincidental similarity, or
   repetition the author wants.

Extraction has a cost. Every include is one more file the agent has to read, so
a one-line composition is usually better as an edge than as a new part. Text that
matches by accident should stay where it is.

## Refactor of the public collection

On a branch of the public collection, the loop ran on the six clusters that
`ubiq overlap` reports. The configuration added `edges.install` and a part rule,
`skills/*/*/parts/*.md`. Each cluster was reviewed:

| Cluster | Decision | Reason |
| --- | --- | --- |
| Tracker precondition in six engineering skills, three wordings | Extracted `setup-matt-pocock-skills/parts/tracker-setup.md` with `mode: [tracker, labels]` | One rule that must change together, already drifting. Callers keep their own additions. |
| Prototype snippets in `to-spec` and `to-tickets` | Left | Two callers and no directory both install; the include would cost a read. |
| `grill-with-docs` restated in `triage` and `wayfinder` | Left | A one-line composition, and the composite is user-invoked only (W003). |
| `handoff` and `claude-handoff` | Left | Different buckets, so no relative link resolves in both layouts; one is in progress. |
| `writing-beats` and `writing-shape` | Left | In progress, and their terms differ on purpose. |
| ADR and learning-record numbering | Left | Coincidental. |

The part lives inside the skill that all six callers already send the user to,
because installers copy or link only skill directories; a top-level `_shared/`
would resolve only in the source tree. Check results stayed the same except for
the new part record and six include edges. Paragraph overlap fell from 6 clusters
and 27 blocks to 5 and 21; line overlap from 8 and 35 to 7 and 29. The first
pass raised line overlap instead, because the six new include lines matched each
other. Overlap now blanks links to parts before comparing, since an include is
the call and not repeated prose.

## Make quality measurable

Report each measure with its denominator:

- Overlap: clusters that span two or more skills, and the blocks inside them, out
  of all blocks in live skill docs.
- Edge coverage: skills with declared invoke metadata, separate from skills whose
  metadata is missing.
- Edge integrity: edges that resolve, can be invoked, and resolve in the installed
  layout.
- Drift: mentions without edges, and edges without mentions.
- Extraction cost: parts with a single caller and the deepest include chain.

A falling overlap count alone isn't success. A repository can reach zero overlap
by dropping the shared rules instead of extracting them.

## Relation to explicit domain models

This goal uses the contracts from [explicit domain models](domain-schema-goal.md). A shared
part is a record type. Invoke and include edges are typed relationships in the
knowledge tree, and part inputs become schema fields.

## Acceptance evidence

The goal is achieved when:

1. AC1: Registering shared parts needs configuration only, and every link to a part is
   a checked reference.
2. AC2: Graph queries return invoke and include edges with their kind, direction, and
   declaration location.
3. AC3: Overlap reports the same clusters for the same input on both surveyed
   repositories.
4. AC4: Fixtures reproduce each defect found in the survey: an invoke edge to a
   user-only skill, and include links that resolve in only one layout. The edge
   checks report each one.
5. AC5: Refactoring a representative skill repository through the loop reduces overlap
   without changing check results beyond the intended new edges, and the
   maintainer reviews each extraction.
6. AC6: Tests cover nested includes, an include cycle, a legitimate invoke cycle, and
   near-duplicate blocks just below and just above the threshold.

7. AC7: A representative repository composes non-skill records through typed relationships with checked targets and declaration locations.
8. AC8: Examples distinguish subgoal decomposition, principle constraints, required qualities, motivation, evidence, and procedural contribution without treating them as equivalent dependencies.
9. AC9: Tests enforce declared relationship semantics, including cycle rules and parent completion conditions, without inferring completion from links alone.

Criteria 1, 2, 4, and 6 have tests in `tests/test_graph.py`. Criterion 3 has
pinned results in `tests/test_survey.py`: the public collection is vendored at the
surveyed commit, and the personal repository is read through git at its surveyed
commit when present, pinning locations without its text. Criterion 5 is the
reviewed refactor above.

Open: a field such as `uses` cannot name another repository's record, so
invoking an upstream skill still needs a glossary stub here, and E012 does not
read the inputs of another repository's parts. Paths written in code spans, such
as the public collection's `` `../retro/SKILL.md` ``, are not links, so W004 does
not check them.
