# GitHub sync

`ubiq sync github` mirrors records to GitHub issues. The records are the source;
the issues are a checked copy. It generalizes the goal-issue script, so a
repository chooses which records sync and where in `ubiq.yaml`.

```yaml
sync:
  repo: owner/name          # default: $GITHUB_REPOSITORY
  label_prefix: "priority: " # labels the sync owns; reserved, not used yet
  records:
    - glob: "docs/goals/*-goal.md"
      kind: goal             # the only kind today
```

```bash
ubiq sync github             # same as --dry-run: print the plan as JSON, write nothing
ubiq sync github --apply     # perform the plan; needs GITHUB_TOKEN with issues: write
ubiq sync github --check     # exit 1 when GitHub differs from the records
ubiq sync github --repo o/n  # override sync.repo
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
| `create` | A record that is not done has no issue; open one. |
| `close` | A record that is done still has an open issue; close it with a comment. |
| `warn` | A record lists a number that is not an issue (a pull request, a typo). |
| `noop` | The issue already matches. |

Everything except `noop` is drift. `--check` exits 1 on any drift, and
`--apply` removes it, so planning again after `--apply` returns only `noop`.
Each mirrored fact is one small function in `FACTS` (`src/ubiq/sync.py`); a new
fact adds a function and an adapter handler, and the planner, drift check, and
command stay as they are.

## Goal behavior

- A criterion that is not `met`, lists no `issues`, and has no issue with the
  marker `<!-- ubiq-goal: <name> <AC> -->` gets a new issue.
- A criterion that is `met` closes its listed and marked issues that are open,
  with a comment that names the review and the commit.
- Only markers in issues opened by `github-actions[bot]` count, because anyone
  can write a marker into an issue. Listed issues are trusted.
- The sync never reopens an issue, edits a title, or touches other issues.

Limits: a pull request that sets a criterion to `met` shows a pending `close`
as drift until it merges, because the merge is what closes the issue. Deleting
a record leaves its issues open. An issue created with a personal token has no
bot author, so list its number in `issues:` to track it.
