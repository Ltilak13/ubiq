# Recover the policy/goal example

The [goal evidence policy](policies/goal-evidence.md) requires explicit evidence
without treating a fresh snapshot as proof of goal completion. This exercise
checks recovery after a cited file changes. It uses the accepted repository
configuration and the existing check and query commands.

Run from the repository root with the development dependencies installed:

```sh
PYTHONPATH=src python -m pytest tests/test_goal_recovery.py -q
```

The [test](../tests/test_goal_recovery.py) copies the repository into pytest's
temporary directory. It excludes Git state, caches, installed dependencies, and
local agent worktrees. All edits occur in that copy. The original source and
metadata must remain unchanged.

## Acceptance sequence

| Step | Expected observation |
| --- | --- |
| Check and query the copied model | No diagnostics and two declared records |
| Append an unreviewed completion claim to the goal source | Check exits nonzero with evidence drift; the goal query reports stale evidence |
| Reject that candidate and restore the source | Check and query results equal the baseline |
| Add a reviewed blank line | Check detects drift although the words and criteria are unchanged |
| Refresh only that source's SHA-256 | Check passes and the goal query reports fresh evidence |
| Restore the source and metadata together | Original bytes, identities, declarations, and query results return |

The accepted edit is deliberately limited to a blank line. The test verifies
that its word sequence is unchanged before refreshing the snapshot. A maintainer
must review meaning, applicability, and evidence before accepting a substantive
edit. The test does not automate that judgment.

## Scope and limits

This is a local recovery example for one goal source and its evidence snapshot.
It exercises a rejected candidate, a narrowly accepted candidate, and rollback.
It does not establish arbitrary schema migration, concurrent editing, crash
recovery, or goal completion. It does not change the live model or refresh
snapshots automatically.

The inventory example has separate behavioral and traceability mutations. This
exercise adds restoration checks for the policy/goal corpus rather than repeating
inventory reservation or release tests.
