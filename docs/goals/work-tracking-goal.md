---
name: work-tracking-goal
status: proposed
criteria:
  AC1:
    assessment: partial
    support:
    - feature: tracking-fields
      implementation:
        path: .ubiq/schemas/tracking.json
        anchor: '"part_of"'
      check:
        path: tests/test_part_of.py
        anchor: def test_more_than_one_part_of_target_fails_check_with_its_location(
    gap: The tracking fields have one schema home and `ubiq check` rejects a missing target, a cycle, and a second parent. No reviewer has checked this evidence against the criterion.
    issues: [120]
  AC2:
    assessment: partial
    support:
    - feature: github-sync
      implementation:
        path: src/ubiq/sync.py
        anchor: def plan(
      check:
        path: tests/test_sync.py
        anchor: def test_planning_is_idempotent_after_its_own_actions(
    gap: The sync mirrors priority, native blocked-by links, sub-issues, and state from records. Plan-step `requires` is not mirrored as blocked-by links yet, so a hand-added link on a plan step's issue is not compared.
    issues: [119, 121, 122, 123, 124, 150]
  AC3:
    assessment: partial
    support:
    - feature: github-sync
      implementation:
        path: src/ubiq/sync.py
        anchor: def drift(
      check:
        path: tests/test_sync.py
        anchor: def test_check_exits_nonzero_on_drift_and_zero_when_in_sync(
    gap: A mirrored fact edited on GitHub is reported as drift by `--check`, on every pull request against the base revision and nightly on main. Facts the sync does not mirror (see AC2) are not compared.
    issues: [171]
  AC4:
    assessment: partial
    support:
    - feature: tracking-fields
      implementation:
        path: src/ubiq/sync.py
        anchor: def stack_findings(
      check:
        path: tests/test_pr_stacks.py
        anchor: def test_a_wrong_base_is_a_stack_finding_and_drift(
    gap: A pull request whose base is not the head branch of a required record's open pull request is reported. The sync reports only and never retargets a pull request.
    issues: [125]
  AC5:
    assessment: partial
    support:
    - feature: github-sync
      implementation:
        path: src/ubiq/sync.py
        anchor: def backed_issue_numbers(
      check:
        path: tests/test_sync.py
        anchor: def test_open_issues_that_no_record_names_are_listed_as_unbacked_and_are_not_drift(
    gap: Each open issue is named by a record, or the dry run lists it as unbacked. An unbacked issue is listed, not drift, so `--check` still passes when someone files an issue that no record names.
    issues: [127]
---

# Goal: work tracking from frontmatter

This goal defines outcomes and acceptance evidence for issue #118, whose spec
says it becomes a goal record so that it tracks itself. The
[[plan:frontmatter-tracking]] plan sequences the work. Facts about the work
(its issue, priority, order, parent, and pull requests) live in frontmatter, and
GitHub issues are a checked mirror.

This record is `proposed` because the [goals README](README.md#adding-goals-and-limiting-work-in-progress)
pauses new goals; #127 asks for this record, and the criteria carry no `priority`, so the sync opens
no issue for them. See [GitHub sync](../github-sync.md) for the mirror.

## Objective

An agent reads what to do next from the repository alone, and a maintainer reading
GitHub sees only facts that a record states.

## Acceptance evidence

The goal is achieved when:

1. AC1: Each tracking fact (`issue`, `priority`, `requires`, `part_of`, `pr`) has one home in a record's frontmatter, and `ubiq check` rejects a missing target, a `requires` cycle, and a second `part_of` target.
2. AC2: `ubiq sync github` mirrors priority, order, containment, and state from records to issues, and a second run makes no change.
3. AC3: A mirrored fact edited on GitHub is reported as drift on every pull request and on main.
4. AC4: A pull request that implements a record is stacked on the pull request of each record it requires, and a mismatch is reported.
5. AC5: Every open issue is backed by a record, or the dry run lists it as unbacked, and `ubiq sync github --check` passes on main.
