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

A criterion's `issue` number, like each number in `issues`, names an issue the sync tracks.

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
- A step has no priority, so no label is managed.

## What the sync writes

The sync never writes to git: no commits, no branches, no pull requests. It
reads records (from the working tree, or from a revision with `--ref`, through a
read-only `git archive`) and writes only to GitHub issues, and only with
`--apply`. Changing a fact means a pull request that edits the record.

## Drift and pending changes

Drift is GitHub disagreeing with the records on the base branch. On a pull
request, CI therefore runs `--check --ref origin/<base>` and fails only on that.
What the pull request itself changes (a criterion set to `met` whose issue is
still open) is not drift; CI prints the head's plan as "Pending on merge" in the
step summary, read-only, and never fails on it.

## Workflow

`.github/workflows/github-sync.yml` runs `--apply` on every push to `main` and on
manual dispatch. It has no `paths:` filter, because GitHub path filters cannot
read `sync.records` from `ubiq.yaml`, and a plan with nothing to do is cheap. A
daily schedule runs `--check` against `main`, reports edits made on GitHub in
the step summary, and may fail the run; it never applies.
