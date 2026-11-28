# Ubiq goals

Ubiq helps repositories make their knowledge explicit, connected, and checkable.

| Goal | Owns |
| --- | --- |
| [Explicit domain models](domain-schema-goal.md) | Concepts, identities, types, schemas, and supported formats |
| [Composable knowledge](composable-knowledge-goal.md) | Reuse and relationships with explicit semantics |
| [Checkable contracts and evidence](checkable-contracts-evidence-goal.md) | Validation outcomes, assessment evidence, and limits of judgment |
| [Human and agent usability](human-agent-readability-goal.md) | Finding, understanding, navigating, and correctly using information |
| [Safe adoption and evolution](safe-adoption-evolution-goal.md) | Setup, migration, maintenance, and recovery |
| [No-code specs](no-code-spec-goal.md) | Records that are the spec, docs, and tests, checked with no agent |
| [Code as records](code-records-goal.md) | One rule defined as data (AC4) and change impact derived from records (AC9) |

## Adding goals and limiting work in progress

New goals are paused until at least one criterion is `met` through a recorded review,
and the goal or feature starter (#111) has been tried outside this repository. Until then:

- Add a criterion to an existing goal instead of a new goal, and only when it names
  evidence a reviewer could check.
- Keep at most one plan `active` per goal, and at most five open implementation pull
  requests at a time. Close or merge a pull request that has had no activity for two
  days, with a comment that says which.
- Move a speculative outcome to the goal's Exploration section and the wayfinder map,
  not to its criteria.

## Organization and dependencies

These are product outcomes, not five required domains or folder hierarchies.
Keep their records together in `docs/goals/`. A repository defines its own domains
from evidence about responsibilities and interactions.

Explicit domain models provide contracts for composition and validation. Adoption
uses those contracts and checks to introduce changes safely. Usability evaluates
all of them from the reader's perspective. These relationships describe the roadmap.
They do not declare executable dependencies or automatic completion propagation.

Skills are one record type. File formats are storage choices. Principles, qualities,
and ideas can also become record types when a repository needs them. The
[composition goal](composable-knowledge-goal.md#scope-and-relationship-semantics)
defines how their relationships differ.

## Acceptance continuity

Existing criterion labels, acceptance text, assessments, and evidence locations
remain in their original records. The composition record is renamed from
`composable-skills-goal` to `composable-knowledge-goal`. The other existing record
names remain stable even where their display titles broaden.

| Existing criteria | Outcome owner | Authoritative assessment |
| --- | --- | --- |
| Domain schema AC1–AC2, AC6, AC9 | Explicit domain models | [Domain model criteria](domain-schema-goal.md#acceptance-evidence) |
| Domain schema AC4–AC5 | Checkable contracts and evidence | [Domain model criteria](domain-schema-goal.md#acceptance-evidence) |
| Domain schema AC3, AC7–AC8, AC10 | Safe adoption and evolution | [Domain model criteria](domain-schema-goal.md#acceptance-evidence) |
| Composable skills AC1–AC6 | Composable knowledge | [Composition criteria](composable-knowledge-goal.md#acceptance-evidence) |
| Human and agent readability AC1–AC7 | Human and agent usability | [Usability criteria](human-agent-readability-goal.md#acceptance-evidence) |

Domain schema AC9 also supplies mixed-format and ambiguous-case obligations for
adoption. Shared obligations retain one assessment. New criteria extend coverage
and start unassessed. Historical skill evidence does not establish broader composition.

## Assessment and evidence

Each goal is a [[glossary record]] in the `goal` namespace. Its frontmatter
connects acceptance criteria to supporting features and evidence. The body
explains the objective and defines each criterion with a stable `AC` label.
Preserve those labels when reordering criteria.

Frontmatter owns the current assessment. `unassessed` means no criterion review
is recorded. `partial` means supporting evidence is identified but a gap remains.
Neither value asserts that the criterion passed. `met` records that a reviewer
checked the cited evidence against the acceptance text and found that it holds.
A `met` criterion needs at least one supporting feature and a `review` record
with a non-empty `by` (who reviewed), `note` (what they checked), `at` (the full
commit SHA they checked), and `date`. Only a `met` criterion can carry `review`.
`python scripts/review_freshness.py` reports a review as stale when a file its
criterion cites changed after `at`; CI prints the report on every run.

A criterion that restates another goal's criterion sets `assessed_in` to it
(`goal` and `criterion`). It keeps its label, stays `unassessed` with no support,
and the sync opens no issue for it.

For each supporting feature, `feature` names a [feature record](../features.md)
(`ubiq check` fails with E006 when it names none), `implementation` identifies its
source, and `check` identifies a test. Each location uses a repository-relative `path` and an exact
text `anchor`. The `gap` states what those locations do not establish. Existing
narrative evidence remains useful context, including past acceptance claims.

`python3 -m ubiq.cli check` validates the frontmatter shape and registered
references. `python3 -m pytest tests/test_goals.py` checks criterion labels and
source locations. Neither command proves that a feature satisfies a goal.
Run the cited tests and review their assertions against the criterion before
claiming corroboration. Anchors detect missing evidence, but do not detect every
semantic change within a feature or test.

Use the [GitHub preview check](github-preview.md) to read canonical metadata
through the native frontmatter display or Code/Raw. The procedure separates
source integrity from observed preview access.

## Criterion issues

Each criterion can list the GitHub issues that track it in `issues:`, as issue
numbers. When a change reaches `main`, the `github-sync` workflow
runs `ubiq sync github --apply` on every goal ([GitHub sync](../github-sync.md)):

- A criterion that is not `met`, lists no `issues`, has no issue with the
  marker `<!-- ubiq-goal: <name> <AC> -->`, and has a `priority` (its own or its
  goal's) gets a new issue. This repository sets `sync.create: prioritized`, so a
  criterion without a priority waits until someone decides to schedule it. Its body quotes the
  criterion, its `gap`, and its cited checks, and gives the commands to verify it.
- A criterion that is `met` closes its listed and marked issues that are still
  open, with a comment that names the review and the commit.
- A listed number that is not an issue, such as a pull request or a typo, is
  reported as a warning, and the workflow run fails after the other actions.

Only markers in issues opened by `github-actions[bot]` count, because anyone can
write a marker into an issue. The sync never reopens an issue, edits a title,
or touches other issues. On a pull request, CI prints the same plan
read-only. Run `ubiq sync github --dry-run`
to see it locally.

Limits: deleting a goal file leaves its issues open. If someone closes a marked
issue while its criterion is not `met`, the sync does not open a replacement.
