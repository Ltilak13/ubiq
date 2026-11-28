---
name: no-code-dogfood
status: proposed
issue: 113
priority: P2
trunk: main
steps:
  plan-record:
    issue: 124
    requires: []
    branch: claude/ecstatic-mendel-nkgz6t-plan-records
    base: claude/ecstatic-mendel-nkgz6t-tracking-fields
    pr: 147
  feature-records:
    issue: 70
    requires: []
    branch: claude/ecstatic-mendel-nkgz6t-issue-70
    base: main
    pr: 116
  release-adoption-smoke-test:
    issue: 163
    requires: [feature-records]
  mermaid-drift:
    issue: 59
    requires: [feature-records]
    branch: claude/ecstatic-mendel-nkgz6t-issue-59
    base: main
    pr: 117
  readme-membership:
    issue: 65
    requires: [feature-records]
  readme-generation:
    issue: 173
    requires: [readme-membership]
  cli-spec-slice:
    requires: [readme-membership]
  no-code-authoring-proof:
    requires: [cli-spec-slice]
  tracking-proof:
    requires: [mermaid-drift, cli-spec-slice]
  starter:
    issue: 111
    requires: [tracking-proof]
  reusable-issue-sync:
    issue: 112
    requires: [tracking-proof]
---

# Plan: no-code dogfood

This plan sequences issue #113: prove the no-code workflow in ubiq before
packaging it for other repositories. The [no-code specs goal](../goals/no-code-spec-goal.md)
owns the outcome and the acceptance criteria. This record owns the order, the
blockers, and the branch and pull request of each step, so an agent can check out
the repository and pick up the next step.

The plan is `proposed`: `ubiq sync github` mirrors nothing for it. Set it to `active`
to create issues for the steps that have none (`cli-spec-slice`,
`no-code-authoring-proof`, and `tracking-proof`) as sub-issues of #113.

## Steps

- `plan-record`: add this plan and link it from the goal and #113 (#124).
- `feature-records`: model one real ubiq feature and its prerequisite as records, and
  link a goal criterion to the feature, a test, and an issue (#70).
- `release-adoption-smoke-test`: install the built wheel and verify that `ubiq plan --next`
  advances after one adoption step (#163).
- `mermaid-drift` and `readme-membership`: generated Mermaid drift check (#59) and the
  README membership check (#65). Both need the feature relationships, and they can
  proceed independently.
- `readme-generation`: generate the managed feature list from checked frontmatter after
  the membership checks ship (#173).
- `cli-spec-slice`: convert one real CLI behavior and its acceptance scenarios into a
  Markdown spec, with the README membership check as the first slice. Reuse a test
  binding that builds a small repository, runs `ubiq check`, and asserts the diagnostic
  and exit status in CI. Lower-level Python tests keep the parser and engine edge cases.
- `no-code-authoring-proof`: change the expected behavior in the spec first. Capture the
  new scenario failing against the old CLI and passing after the change, and cite both CI
  runs on the criterion. Where the engine already supports the rule declaratively, also
  show a rule change that takes effect through records alone.
- `tracking-proof`: a documentation and tracking pull request that changes the feature
  summary and prerequisite through records. Show CI flagging the stale README and Mermaid
  views, refresh both, and verify the checks pass without Python or workflow edits. Record
  a reviewed assessment and verify that the linked issue closes on merge, and capture a
  case where missing review leaves the issue open.
- `starter` and `reusable-issue-sync`: link the proof pull requests and check results
  from this plan and the README, use the findings to scope the starter (#111) and the
  reusable issue sync (#112), then validate the workflow in a second repository.

## How to read the steps

`requires` names the steps that must finish first. `pr` is the pull request that
implements the step, once it is open. Workflow status is not stored here: an open pull
request means the step is in review, and a merged one means it is done. Record the current
blocker, next action, and evidence for a step in the pull request that changes them.

<details>
<summary>Dependency diagram</summary>

Arrows point from prerequisites to the steps they unlock. Ticketed steps link
to their GitHub issues. Refresh this view with
`python scripts/dogfood_diagrams.py --write`.

<!-- ubiq:dogfood-diagram -->
```mermaid
flowchart LR
  step_1["cli-spec-slice"]
  step_2["feature-records (#35;70)"]
  click step_2 "https://github.com/Ltilak13/ubiq/issues/70"
  step_3["mermaid-drift (#35;59)"]
  click step_3 "https://github.com/Ltilak13/ubiq/issues/59"
  step_4["no-code-authoring-proof"]
  step_5["plan-record (#35;124)"]
  click step_5 "https://github.com/Ltilak13/ubiq/issues/124"
  step_6["readme-generation (#35;173)"]
  click step_6 "https://github.com/Ltilak13/ubiq/issues/173"
  step_7["readme-membership (#35;65)"]
  click step_7 "https://github.com/Ltilak13/ubiq/issues/65"
  step_8["release-adoption-smoke-test (#35;163)"]
  click step_8 "https://github.com/Ltilak13/ubiq/issues/163"
  step_9["reusable-issue-sync (#35;112)"]
  click step_9 "https://github.com/Ltilak13/ubiq/issues/112"
  step_10["starter (#35;111)"]
  click step_10 "https://github.com/Ltilak13/ubiq/issues/111"
  step_11["tracking-proof"]
  step_7 --> step_1
  step_2 --> step_3
  step_1 --> step_4
  step_7 --> step_6
  step_2 --> step_7
  step_2 --> step_8
  step_11 --> step_9
  step_11 --> step_10
  step_1 --> step_11
  step_3 --> step_11
```
<!-- /ubiq:dogfood-diagram -->

</details>
