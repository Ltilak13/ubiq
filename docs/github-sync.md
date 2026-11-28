# GitHub sync

`ubiq sync github` mirrors records to GitHub issues. The records are the source;
the issues are a checked copy. It generalizes the goal-issue script, so a
repository chooses which records sync and where in `ubiq.yaml`.

```yaml
sync:
  repo: owner/name          # default: $GITHUB_REPOSITORY
  label_prefix: "priority: " # the sync owns labels that start with this; never empty
  records:
    - glob: "docs/goals/*-goal.md"
      kind: goal             # goal or plan
    - glob: "docs/plans/*.md"
      kind: plan
```

```bash
ubiq sync github             # same as --dry-run: print the plan as JSON, write nothing
ubiq sync github --apply     # perform the plan; needs GITHUB_TOKEN with issues: write
ubiq sync github --check     # exit 1 when GitHub differs from the records
ubiq sync github --repo o/n  # override sync.repo
ubiq sync github --check --ref origin/main  # read the records as they are at a revision
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
| `link` | A required issue is not yet a blocker; add the blocked-by link. |
| `unlink` | An issue blocks this one but `requires` does not name it; remove the link. |
| `body` | The generated "Blocked by" section differs; rewrite it between its markers. |
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
Sync recognizes three kinds of evidence:

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
  marker `<!-- ubiq-goal: <name> <AC> -->` gets a new issue.
- A criterion that is `met` closes its listed and marked issues that are open,
  with a comment that names the review and the commit.
- Only markers in issues opened by `github-actions[bot]` count, because anyone
  can write a marker into an issue. Listed issues are trusted.
- The sync never reopens an issue, edits a title, or touches other issues.

Limits: deleting
a record leaves its issues open. An issue created with a personal token has no
bot author, so list its number in `issues:` to track it.

## Plan behavior

A `plan` record (see [plan records](spec.md#plan-records)) syncs each of its steps as one
item, with the marker `<!-- ubiq-plan: <plan> <step> -->`.

- A step that lists an `issue` tracks that issue. A step with no `issue` and no `pr`, and
  no issue with its marker, gets a new issue. A step that names a `pr` and no `issue` is
  tracked by that pull request and gets no issue.
- A plan with status `proposed` or `abandoned` mirrors nothing. A `done` plan closes the
  open issues of its steps. An `active` plan never closes or reopens anything: a step's
  issue closes with its pull request.
- Each item carries the links the sync will mirror once the link facts land:
  `Desired.parent_issue` is the plan's `issue` (the sub-issue parent) and
  `Desired.requires_markers` holds the markers of the steps it waits on (the blocked-by
  targets). `plan()` resolves a marker to an issue number through the same marker index it
  uses to find an item's issues. No fact reads these fields yet; the blocked-by and
  sub-issue facts (#121, #122) each add one function to `FACTS` and one handler.
- A step's `priority` is optional. A step without one takes the plan's (see
  [Priority inheritance](#priority-inheritance)).

## What the sync writes

The sync never writes to git: no commits, no branches, no pull requests. It
reads records (from the working tree, or from a revision with `--ref`, through a
read-only `git show`) and writes only to GitHub issues, and only with
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
