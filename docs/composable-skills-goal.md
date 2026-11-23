# Goal: composable skills

Status: in progress. Shared parts register as records with configuration alone.
`ubiq graph` shows invoke and include edges, `ubiq overlap` reports repeated text,
and `ubiq check` reports include cycles (E011), invokes the model can't follow
(W003), and links that break in the installed layout (W004). Typed relations,
drift detection, and part inputs remain open.

## Objective

Let a skill repository keep each rule in one place. Skills should build on other
skills and on shared parts instead of copying their text. Ubiq should find logic
that several skills repeat, show how skills depend on each other, and check that
the agent running a skill can follow each dependency.

Ubiq stays deterministic. It reports overlap and broken edges. The maintainer
decides what becomes a part, usually through the maintenance skill.

## Vocabulary

A skill reuses other logic in one of three ways:

| Way | Example | Ubiq today |
| --- | --- | --- |
| Invoke another skill | "call the Skill tool for `grilling`", `/commit-slices` | Edge only when an overlay declares it in `uses` |
| Include a shared part | `[PR scope](../_shared/pr-scope.md)` | Checked link when the part is a registered record; not a graph edge |
| Copy the text | the same precondition pasted into six skills | Not detected |

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

Some parts take an input. `pr-checkout.md`, for example, runs in `new` or
`existing` mode. A part schema should list its inputs so that ubiq can check that
each caller names a valid one. That schema goes through the
[schema change workflow](schema-workflow.md) like any other [[domain-schema]].

## Show one graph with typed edges

Invoke edges come from `uses` and any other field configured for invocation.
Include edges come from links to part records. Authors shouldn't declare an
include twice, once as a link and once in metadata, because the two copies drift.

Each edge kind is a policy: what declares the edge, how its target resolves, and
which constraints apply. Kinds compose the same way reference kinds do, so a
repository can add a kind without new branching in the checker. Queries return
dependencies and callers, filtered by kind, with the declaration location of each
edge.

Cycles follow the edge's meaning. An include cycle sends the agent around the
same files forever, so it is an error. An invoke cycle can be legitimate, as when
two workflows hand off to each other, so ubiq reports it without failing.

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

Severity is configurable per edge kind. An include link that resolves nowhere
should still fail under any configuration. That belongs in the spec as a
guarantee, enforced like the existing ones: a setting that would break it
reports `E008`.

## Detect drift

Ubiq should warn when a skill mentions another skill without declaring an edge,
and when it declares an edge it never mentions. This check depends on typed
relations. Without them, routing text ("not for X; use Y") reads as a missing
dependency and buries the real findings.

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

## Relation to the domain schema goal

This goal specializes the [domain schema goal](domain-schema-goal.md). A shared
part is a record type. Invoke and include edges are typed relationships in the
knowledge tree, and part inputs become schema fields.

## Acceptance evidence

The goal is achieved when:

1. Registering shared parts needs configuration only, and every link to a part is
   a checked reference.
2. Graph queries return invoke and include edges with their kind, direction, and
   declaration location.
3. Overlap reports the same clusters for the same input on both surveyed
   repositories.
4. Fixtures reproduce each defect found in the survey: an invoke edge to a
   user-only skill, and include links that resolve in only one layout. The edge
   checks report each one.
5. Refactoring a representative skill repository through the loop reduces overlap
   without changing check results beyond the intended new edges, and the
   maintainer reviews each extraction.
6. Tests cover nested includes, an include cycle, a legitimate invoke cycle, and
   near-duplicate blocks just below and just above the threshold.

Criteria 1, 2, and 4 have tests in `tests/test_graph.py`. Criteria 3 and 6 are
partly covered: the tests lack an invoke cycle, nested includes, and pinned
results for the surveyed repositories. Criterion 5 needs a reviewed refactor of a
real repository. Remaining order: typed relations, then
drift, then part inputs. The status line lists what is available today.
