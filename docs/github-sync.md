# GitHub sync

`ubiq sync github` mirrors records to GitHub issues. The records are the source;
the issues are a checked copy. It generalizes the goal-issue script, so a
repository chooses which records sync and where in `ubiq.yaml`.

```yaml
sync:
  repo: owner/name          # default: $GITHUB_REPOSITORY
  label_prefix: "priority: " # the sync owns labels that start with this; never empty
  create: always            # or `prioritized`: open goal-criterion issues only for priorities
  records:
    - glob: "docs/goals/*-goal.md"
      kind: goal             # goal, plan, feature, or decision
    - glob: "docs/plans/*.md"
      kind: plan
    - glob: "src/ubiq/features/*.md"
      kind: feature
```

```bash
ubiq sync github             # same as --dry-run: print the plan as JSON, write nothing
ubiq sync github --apply     # perform the plan; needs GITHUB_TOKEN with issues: write
ubiq sync github --check     # exit 1 when GitHub differs from the records
ubiq sync github --repo o/n  # override sync.repo
ubiq sync github --check --ref origin/main  # read the records as they are at a revision
ubiq sync github --check --ignore-derived   # do not count the derived status labels
```

A dry run needs only read access. It reads public repositories without a token.
`--check` needs a token to read reliably, so without `GITHUB_TOKEN` it prints
`skipped` and exits 0 instead of failing a pull request that cannot read issues.

## How it plans

Each sync is a difference between the desired state (the records) and the actual
state (a snapshot of the repository's issues). `plan(desired, snapshot)` is a
pure function that returns actions:

| Action | Meaning |
| --- | --- |
| `create` | A record that is not done has no issue; open one (with its priority label). |
| `label` | An open issue's priority label differs from the record; add and remove labels. |
| `link` | Add a missing blocked-by or sub-issue link. |
| `unlink` | Remove an unexpected blocked-by or sub-issue link. |
| `body` | The generated "Blocked by" section differs; rewrite it between its markers. |
| `decision-comment` | A decision's question issue has no generated comment; post one. |
| `decision-comment-update` | The generated comment differs from the record; PATCH it. |
| `stack` | A pull request is not based on the branch of its required record's pull request. Report only. |
| `close` | A record that is done still has an open issue; close it with a comment. |
| `warn` | A record lists a number that is not an issue (a pull request, a typo). |
| `noop` | The issue already matches. |

Everything except `noop` is drift. `--check` exits 1 on any drift, and
`--apply` removes it, so planning again after `--apply` returns only `noop`.
Each mirrored fact is one small function in `FACTS` (`src/ubiq/sync.py`); a new
fact adds a function and an adapter handler, and the planner, drift check, and
command stay as they are.

## Priority

A criterion's `priority` (`P1`, `P2`, or `P3`, one of the [[tracking field]]s) is
mirrored as the label `<label_prefix>Pn`, for example `priority: P1`. The `fact_priority`
function in `FACTS` plans it, and one `GitHub` handler performs it.

- An open issue that tracks the criterion carries exactly that label. A missing label
  is added, and any other label with the prefix is removed, in one `label` action
  for the issue.
- Only labels that start with the prefix are added or removed. Every other label is left alone.
  Names compare without regard to case, as GitHub does.
- Changing `priority` in the record is therefore one `label` action in the dry run. A
  label edited by hand on GitHub is the same action, so `--check` reports it as drift
  and `--apply` restores it.
- A criterion with no `priority` leaves labels unmanaged, so adopting the sync does not
  strip labels that were set by hand. A closed issue, or an issue whose criterion is
  `met`, is not relabelled.
- A new issue is created with its label.

## Priority inheritance

A plan's `priority`, and a goal's top-level `priority`, is the default for the items it
contains. A step or criterion without its own `priority` takes its container's; an
explicit value on the item wins. The resolved value (`resolve_priority` in
`src/ubiq/sync.py`) goes through the same `fact_priority` as any other priority, so the
dry run shows each resulting change as a `label` or `create` action.

- Adding `priority` to a plan or goal that already tracks issues relabels every
  open issue whose item has no own value. Read the dry run before `--apply`.
- A container with no `priority` changes nothing: items without their own value stay unmanaged.

A criterion's `issue` number, like each number in `issues`, names an issue the sync tracks.

## Sub-issues

A criterion is `part_of` one record, and the sync makes the criterion's issues
sub-issues of that record's issue. By default a criterion is part of its own goal.
An explicit `part_of` names the parent instead. A schema-bound record with an
`issue` can also declare `part_of` to link that issue to its parent.
`ubiq check` rejects more than one name for a field annotated with `single` (E009). `fact_part_of` in `FACTS` plans it, and two `GitHub`
handlers perform it.

- **The goal's issue.** A goal gets its own issue through a goal-level `issue` field
  (`issue: 118` beside `name` and `status` in the goal's frontmatter). This is the
  smallest design that works: the sync does not create goal issues, so a goal is
  opened by hand (or by an earlier tool) and named once. A goal with no `issue` has no
  parent issue, and its criteria's issues are not nested; nothing is planned or
  reported for them.
- **Which issues.** Every issue that tracks the criterion (its `issue`, its `issues`,
  and the marked issue), open or closed, except the parent itself.
- **`link`.** An issue missing from the parent's sub-issues is added with
  `POST repos/{o}/{r}/issues/{parent}/sub_issues` and the issue's numeric `id` as
  `sub_issue_id`. GitHub allows one parent per issue, so the request sets
  `replace_parent` and moves an issue that has another parent. A new issue is created
  and then attached in the same `--apply`.
- **`unlink`.** A sub-issue of the parent that no record asks for was added on GitHub.
  `--check` reports it as drift, and `--apply` removes it with
  `DELETE repos/{o}/{r}/issues/{parent}/sub_issue` and the `sub_issue_id` in the body.
  An issue that a record moves to a different parent is a `link`, not an `unlink`.
- **`warn`.** A parent `issue` that is not an issue in the repository.
- **Reading.** The snapshot reads `GET repos/{o}/{r}/issues/{parent}/sub_issues` for each
  parent issue, so the token needs `issues: read`, as before.

## Pull requests

A record's `pr` (one of the [[tracking field]]s) lists its implementing pull requests.
Each sync reads the open pull requests (`GET repos/{o}/{r}/pulls?state=open`): head
ref, base ref, and closing references from each PR body. REST has no closing-issues field, so the
sync reads the body for `Closes #n`, `Fixes #n`, or `Resolves #n` (also `closed`,
`fixed`, `resolved`, and `owner/repo#n` for this repository). The token needs
`pull-requests: read`.

### Stack check

When record X `requires` record Y, and Y has an open pull request, X's pull request must
target the head ref of Y's. A pull request whose base is anything else is a `stack`
action in the dry run, which is drift and fails `--check`. The sync only reports it and
never retargets a pull request.

This repository's stack is #116, #132, #135, #145: each pull request is based on the
head ref of the one before. Its records say so:

```yaml
# sync-github.md        (head: claude/..-sync-github, base: main)
name: sync-github
pr: [132]
# tracking-fields.md    (head: claude/..-tracking-fields, base: claude/..-sync-github)
name: tracking-fields
pr: [135]
requires: [sync-github]
# requires-links.md     (head: claude/..-requires-links, base: claude/..-tracking-fields)
name: requires-links
pr: [145]
requires: [tracking-fields]
```

With those records, #145 must target `claude/..-tracking-fields`, the head of #135. If
#145 were opened against `main`, the dry run reports:

```json
{"action": "stack", "record": "requires-links", "pr": 145, "base": "main",
 "expected": ["claude/..-tracking-fields"], "requires": ["tracking fields"],
 "reason": "pull request base is not the head branch of a required record's pull request"}
```

- The check covers every schema-bound frontmatter record with a `pr`, and every goal
  criterion the sync mirrors; the required record can be any record with a `pr`.
  `requires` names are shown normalized. `pr: <n>` entries in `requires` are not records.
- Only open pull requests count. When #135 merges it is no longer open, so #145 makes no
  claim until it is retargeted to the trunk; a merged or closed `pr` entry is ignored.
- A pull request has one base. A record that requires several records with open pull
  requests passes when its base is the head of any of them.
- `--apply` does nothing for a `stack` finding, prints it with the warnings, and exits 1.
- A pull request from a fork is compared by head ref name only.

### Derived status: in review

An open issue carries `status: in review` when an open pull request implements it.
Sync recognizes these kinds of evidence:

- `Refs #n` (or `Part of #n`) in a commit message of the pull request, or `issue-<n>`
  in its branch name (`claude/records-issue-70`). This is the preferred way to name the
  issue of a goal criterion, which the sync closes when the criterion is met.
- A closing reference on a pull request that targets the default branch.
- A closing reference on a stacked pull request that targets the branch of another
  open pull request in the repository. GitHub enables automatic closing by keyword
  when the pull request targets the default branch.
- A record whose tracked issue and `pr` link it to an open implementing pull request.

Sync removes the label when the issue closes or the last evidence of an open
implementing pull request disappears. It derives the label on every sync.

- Adding it removes `status: in progress` in the same `label` action. Every other
  `status: ` label (`blocked`, `ready`, and so on) is left alone.
- It applies to all issues in the repository. A draft pull request counts. A hand-added or hand-removed label is drift that `--apply` restores.
- The label name is fixed (`STATUS_PREFIX` in `src/ubiq/sync.py`) and is independent of
  `sync.label_prefix`.
- The `github-sync` workflow also runs when a pull request opens, reopens, is edited,
  or closes (`pull_request_target`, always with the default branch checked out), so the
  label follows pull requests without waiting for a push to `main`.
- Pull request CI runs `--check --ignore-derived`: the label is the one fact that a
  pull request's own opening changes, so it can lag that check by a few seconds.
  The flag also skips a "met at" comment still owed to an issue that GitHub closed by
  keyword, which waits only for the next sync of `main`. The scheduled drift job
  counts both.

## Requires

A criterion's `requires` (one of the [[tracking field]]s) is mirrored two ways. A name
that resolves to a record with an `issue` (a feature record, for example) becomes a
native GitHub blocked-by link on the criterion's open issue. An entry `"pr: <n>"`
cannot be a link, because GitHub rejects a pull request as a blocker ("Target issue may
only be an issue"), so it becomes text.

- `fact_requires` plans `link` (POST `issues/{n}/dependencies/blocked_by` with the
  blocker's numeric `issue_id`) for each missing link and `unlink` (DELETE
  `.../blocked_by/{issue_id}`) for each extra one. Both are drift, so adding or removing
  a `requires` entry is one action in the dry run, and a link added by hand is reported
  and removed by `--apply`.
- The snapshot reads an issue's links (GET `.../blocked_by`) only when its
  `issue_dependencies_summary.blocked_by` is above zero.
- `fact_blocked_line` plans a `body` action that writes one line, `Blocked by: #12, #15
  (pull requests, generated from requires)`, between `<!-- ubiq-blocked-by:begin -->` and
  `<!-- ubiq-blocked-by:end -->`. The section is appended when missing, replaced in
  place when it differs, and removed when no `pr:` entry remains. Text outside the
  markers is never changed.
- A criterion with no `requires` removes the generated section and leaves native links alone; `requires: []`
  removes every link. A name that resolves to no record with an `issue` makes no link. A
  required issue that is not in the repository is a `warn`.

## Goal behavior

- A criterion that is not `met`, lists no `issues`, and has no issue with the
  marker `<!-- ubiq-goal: <name> <AC> -->` gets a new issue. With
  `create: prioritized`, it gets one only when the criterion or its goal sets a
  `priority`; a criterion without one is still tracked through listed and marked issues.
- A criterion with `assessed_in` is assessed by the criterion it names, so it is not
  mirrored at all.
- A criterion that is `met` closes its listed and marked issues that are open,
  with a "met at `<commit>`" comment that names the scenarios or the review.
- An issue that closed before the sync could (a closing keyword on merge, or by hand)
  still gets that comment, once. The sync reads the bot's comments only for the closed
  issues of met criteria.
- A pull request that closes an unmet criterion's own issue (the one carrying its
  marker) by keyword, in its body or a commit message, is a `warn`, and fails
  `--check`: write `Refs #n` so that the issue closes when the criterion is met. Issues
  a criterion lists in `issues:` are work items, and their pull requests may close them.
- Only markers in issues opened by `github-actions[bot]` count, because anyone
  can write a marker into an issue. Listed issues are trusted.
- The sync never reopens an issue, edits a title, or touches other issues.

Limits: deleting
a record leaves its issues open. An issue created with a personal token has no
bot author, so list its number in `issues:` to track it.

## Criterion scenarios

A goal criterion can be accepted by Gherkin scenarios instead of a recorded review.
Its frontmatter sets `scenario: true` and stores nothing else about its state: no
`assessment`, `support`, `gap`, or `review`. The scenarios sit in the feature file
beside the goal, `<goal>.feature`, each tagged with the criterion's label:

```gherkin
@AC1
Scenario: A part registered by configuration alone is a checked reference
  Given the part "checkout" in "skills/_shared/checkout.md"
  ...
```

- `ubiq check` reports E016 when a `scenario: true` criterion has no tagged scenario,
  and when a tag names no such criterion. A tag on `Feature:` applies to every scenario.
- `pytest -p ubiq.pytest_plugin --ubiq-results FILE` writes each scenario's outcome.
  The plugin ships with the package but loads only when named with `-p`, so other
  test suites never see it; scenarios run with pytest-bdd
  ([decision 0002](decisions/0002-gherkin-binding.md)).
- `ubiq sync github --results FILE` treats the criterion as met exactly when every
  scenario tagged with it passed, and closes its issues with a comment naming the
  commit. Without `--results`, or when a scenario did not run, the criterion stays open.
- A scenario that fails after its criterion's issues closed opens a new
  `Regression:` issue. The sync still never reopens an issue.
- A goal's own `issue` closes when every criterion holds: a scenario criterion passed,
  any other criterion is `met`, and an `assessed_in` criterion holds when the one it
  names does. Nothing creates the goal issue.

The `github-sync` workflow runs `tests/scenarios` on each push to `main` and passes the
results to `--apply`, so a criterion is met only by a passing run of `main`. The approval
that matters is the review of the scenario text in the pull request that adds it.

## Plan behavior

A `plan` record (see [plan records](spec.md#plan-records)) syncs each of its steps as one
item, with the marker `<!-- ubiq-plan: <plan> <step> -->`.

- A step that lists an `issue` tracks that issue. A step with no `issue` and no `pr`, and
  no issue with its marker, gets a new issue. A step that names a `pr` and no `issue` is
  tracked by that pull request and gets no issue.
- A plan with status `proposed` or `abandoned` mirrors nothing. A `done` plan closes the
  open issues of its steps. An `active` plan never closes or reopens anything: a step's
  issue closes with its pull request.
- Each step's issue becomes a sub-issue of the plan's issue. The step's
  `requires_markers` identify the other steps it waits on.
- A step's `priority` is optional. A step without one takes the plan's (see
  [Priority inheritance](#priority-inheritance)).

## Feature records

A `kind: feature` entry mirrors [feature records](features.md) (`src/ubiq/features/*.md`),
one issue per feature, with the same actions as goals.

- A `planned` feature that has no `issue` and no issue marked
  `<!-- ubiq-feature: <name> -->` gets a new issue (a `create`), titled
  `<name>: <summary>`, with its `priority` label if it sets one.
- A feature with `issue: N` tracks that issue. Set `issue` to link work that already
  has one; leave it out to let the sync create one, then add the number if you want it listed.
- A `shipped` feature closes its open tracked issues with a comment (a `close`). A
  record with no `status` is shipped, so adopting the kind creates nothing for existing
  records and closes only issues they name.
- Nothing is reopened: setting a shipped feature back to `planned` leaves a closed
  issue closed.

## Decision behavior

A `decision` record (see [decision records](spec.md#decision-records)) is mirrored as one
comment on the issue its `question` names, and closes that issue.

- An `accepted` or `superseded` decision gets exactly one generated comment, which starts
  with `<!-- ubiq-decision: <name> -->` and ends with `<!-- /ubiq-decision: <name> -->`
  (`fact_comment` in `FACTS`; the `decision-comment` and `decision-comment-update` handlers).
  Editing the record changes the comment in place with
  `PATCH /repos/{owner}/{repo}/issues/comments/{id}`, so `--check` reports an edited record
  or an edited comment as drift.
- Only a comment written by `github-actions[bot]` that starts with the marker is read or
  edited. A person's comment, even one that copies the marker, is never touched and does not
  count; the sync then posts its own. A second generated comment is a `warn`. A comment made
  with a personal token has no bot author, so run `--apply` from the workflow.
- A `superseded` decision's comment says `superseded by <name>` with the replacement's
  question and date, taken from the record whose `supersedes` names it.
- An `accepted` or `superseded` decision closes its question issue if it is open, unless the
  record sets `closes: false` (default `true`), for a `question` that is a tracking issue with
  other work under it; the comment is still posted. The sync
  never reopens an issue, and a `proposed` decision mirrors nothing.
- A `question` that is not an issue (a pull request, a typo) is a `warn`, so
  `--check` fails.
- The sync reads the comments of the question issues only.

The map's "Decisions so far" list is generated as Markdown in `docs/decisions/README.md`
(`ubiq decisions --write`) and kept current by `ubiq check`. Mirroring that block into the
wayfinder map issue body is follow-up work: the sync has no fact for an issue body yet, and
the map issue is not a record.

## What the sync writes

The sync never writes to git: no commits, no branches, no pull requests. It
reads records (from the working tree, or from a revision with `--ref`, through a
read-only `git show`) and writes only to GitHub issues and their generated comments, and only with
`--apply`. Changing a fact means a pull request that edits the record.

## Drift and pending changes

Drift is GitHub disagreeing with the plan produced by the base revision's code
and records. On a pull request, CI runs the drift check in a separate worktree
at the event's base commit. If the base uses the older goal-issue script, CI
checks its dry-run plan for drift. A base revision without an issue mirror
skips the check.

The preview job uses the pull request's exact head commit and prints its plan
as "Pending on merge" in the job summary. The preview is read-only and does
not block the pull request.

The pull request checks use the current state of GitHub when the revision
supports pull request sync. Opening, editing, retargeting, or closing a pull
request can change review labels between pushes to `main`. Use the manual
`github-sync` workflow to apply those changes between pushes.

## Workflow

`.github/workflows/github-sync.yml` runs `--apply` on every push to `main` and on
manual dispatch. It has no `paths:` filter, because GitHub path filters cannot
read `sync.records` from `ubiq.yaml`, and a plan with nothing to do is cheap. A
daily schedule runs `--check` against `main`, reports edits made on GitHub in
the step summary, and may fail the run; it never applies.
