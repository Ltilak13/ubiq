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
      kind: goal             # the only kind today
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
| `link` | An issue that tracks a record is not a sub-issue of its parent record's issue; add it. |
| `unlink` | A sub-issue of a parent issue that no record puts there (added on GitHub); remove it. |
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
