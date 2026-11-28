---
name: no-code-spec-goal
status: proposed
criteria:
  AC1:
    assessment: partial
    support:
    - feature: graph-blocks
      implementation:
        path: src/ubiq/mermaid.py
        anchor: def check(
      check:
        path: tests/test_mermaid.py
        anchor: def test_matching_block_is_clean_and_stale_block_warns_with_line(
    gap: Diagrams (#59), values and contracts (schema bindings), and relationships have a home and a named check. Behavior has no `.feature.md` home inside a record yet (goal scenarios sit in a `<goal>.feature` file beside the goal), and the rationale check (Vale) runs only on the sample repository, not on Ubiq's own prose. No review has judged the whole criterion.
    issues: [59]
  AC2:
    assessment: met
    support:
    - feature: no-code-checks
      implementation:
        path: docs/no-code-checks.md
        anchor: '## Pre-commit'
      check:
        path: tests/test_no_code_checks.py
        anchor: def test_sample_passes_ubiq_check(
    - feature: no-code-checks
      implementation:
        path: examples/no-code-checks/.pre-commit-config.yaml
        anchor: 'id: cue-vet'
      check:
        path: .github/workflows/no-code-checks.yml
        anchor: npm run cucumber
    gap: None remaining.
    review:
      by: Claude Code agent (automated review; no human has confirmed it)
      note: "Read docs/no-code-checks.md against examples/no-code-checks: the sample's .pre-commit-config.yaml is the recipe's, and the workflow runs ubiq check, cue vet, vale, npm run cucumber, then pre-commit run --all-files on the sample as a standalone repository, with no agent. The latest run of that workflow on main (160f1bf, the last commit to touch those files) succeeded at every step."
      at: 188779d886f4ce55829d05e17e1e764b48c9c7f6
      date: '2026-11-28'
    issues: [72]
  AC3:
    assessment: partial
    support:
    - feature: restated-values
      implementation:
        path: src/ubiq/overlap.py
        anchor: def find_overlap(
      check:
        path: tests/test_restated.py
        anchor: def test_reports_each_restated_field_once_outside_code_and_links(
    - feature: field-links
      implementation:
        path: src/ubiq/kinds.py
        anchor: 'Policy("value", "value", by_file, "E013", Context.COMMENT)'
      check:
        path: tests/test_field_values.py
        anchor: def test_stale_null_and_non_text_fields_fail(
    gap: Restated-value warnings (PR #60) and checked field links that fail when stale (PR #61) are merged. A field link cannot yet declare its own field (#63 is open), which the criterion requires.
    issues: [63, 65]
  AC4:
    assessment: met
    support:
    - feature: criterion-scenarios
      implementation:
        path: src/ubiq/scenarios.py
        anchor: def load_results(
      check:
        path: tests/test_criterion_scenarios.py
        anchor: def test_a_passing_scenario_closes_the_criterion_issue(
    - feature: field-links
      implementation:
        path: src/ubiq/scan.py
        anchor: def _blank_fences(
      check:
        path: tests/test_fences.py
        anchor: def test_configured_fences_check_field_names_and_count_term_uses(
    gap: None remaining.
    review:
      by: Claude Code agent (automated review; no human has confirmed it)
      note: "Goal criteria bind to tagged Gherkin scenarios and a missing or unknown tag is E016 (tests/test_criterion_scenarios.py); the sync meets a criterion only from passing scenario results on main (#67). Configured fences check field names (E013) and count term uses, and unconfigured fences stay unscanned (tests/test_fences.py, #66). Spec records other than goals have no scenario binding, which the criterion does not ask for."
      at: 188779d886f4ce55829d05e17e1e764b48c9c7f6
      date: '2026-11-28'
    issues: [66, 67]
  AC5:
    assessment: unassessed
    support: []
    gap: No controlled vocabulary record type or Vale rule export exists (#68).
    issues: [68]
  AC6:
    assessment: met
    support:
    - feature: feature-planning
      implementation:
        path: src/ubiq/plan.py
        anchor: def order(
      check:
        path: tests/test_plan.py
        anchor: def test_shipped_features_form_a_valid_order(
    - feature: feature-planning
      implementation:
        path: src/ubiq/plan.py
        anchor: def next_steps(
      check:
        path: tests/test_plan.py
        anchor: def test_plan_next_for_a_repo_using_some_features(
    gap: None remaining.
    review:
      by: Claude Code agent (automated review; no human has confirmed it)
      note: "Every Ubiq feature is a record in src/ubiq/features (name, requires, codes, docs, summary), checked by a schema; `ubiq plan` orders them by requires and `--next` lists the ones whose requirements a repository already meets (tests/test_plan.py). The shipped records form a valid order, a missing requirement or cycle fails, and each record's codes and docs match the spec."
      at: 188779d886f4ce55829d05e17e1e764b48c9c7f6
      date: '2026-11-28'
    issues: [70]
  AC7:
    assessment: unassessed
    support: []
    gap: No worked example repository exists (#69).
    issues: [69]
  AC8:
    assessment: unassessed
    support: []
    gap: No check compares a generated file or section with the output of the command that writes it.
  AC9:
    assessment: unassessed
    support: []
    gap: No check reports a section that should be its own record file.
---

# Goal: no-code specs

This goal defines outcomes and acceptance evidence. It replaces the tracking
issue #64. It does not claim that Ubiq supports these outcomes today.
The sequence of work that proves the outcomes, with each step's issue and
blockers, is in [[plan:no-code-dogfood]] (issue #113).

The [[plan:no-code-spec-views]] plan tracks checked diagrams and tables.

## Objective

Let a repository use each Markdown record as its spec, its docs, and its tests
at once. Every check runs in CI with no agent. The rule underneath: each fact has
one home.

| Fact | Home | Checked by |
| --- | --- | --- |
| Values and contracts | Frontmatter | `ubiq check` (JSON Schema bindings), CUE for cross-field rules |
| Behavior | Gherkin scenarios in the record (`.feature.md`) | Cucumber, with generic steps |
| Rationale | Prose | Vale for writing rules, plus Ubiq's own checks |
| Diagrams | Generated from records, or checked against them | Ubiq (#59) |

The [fact homes policy](../policies/fact-homes.md) states where each fact
lives, when it gets its own file, and how derived files and diagrams stay current.

Agents help write and maintain records. No check needs an agent to pass.

## Scope

Pre-commit hooks, CI, Vale, CUE, and Cucumber stay outside Ubiq. Ubiq documents
how to combine them as a recipe.

Out of scope: proving that prose is true. Ubiq makes risky sentences visible
(restated values, and claim-word rules in Vale) and moves facts into frontmatter
or scenarios. What remains is for review.

Tabled: a renderer for field references (PR #62). Checked links read well in
GitHub previews, so it is not needed now.

## Acceptance evidence

The goal is achieved when:

1. AC1: Each fact kind (values and contracts, behavior, rationale, and diagrams) has one home in a record, and a named check reads it there.
2. AC2: All checks (`ubiq check`, `cue vet`, `vale`, and `cucumber`) run in pre-commit and CI with no agent, following a documented recipe.
3. AC3: Prose cannot silently restate a frontmatter value. A restatement warns, a field link shows the value and fails when it is stale, and a field link can declare its field.
4. AC4: Spec criteria link to the Gherkin scenarios that test them, names inside configured fenced blocks are checked, and test results verify the criteria.
5. AC5: Controlled vocabulary lives in checkable records and exports Vale rules, so prose and step definitions use checked terms.
6. AC6: Ubiq's own features are records, and the adoption order derives from their declared dependencies.
7. AC7: A worked example repository applies this pattern, and all of its checks pass in CI.
8. AC8: Each generated file or section names the command that writes it, and pre-commit and CI fail when it is stale.
9. AC9: A check reports a section that other files link to by name, or that has checked fields, when it is not its own record file.

<details>
<summary>AC6 evidence diagram</summary>

The view shows what AC6 tracks and what evidence its record cites. The issue
link tracks the work. The criterion's assessment records whether it holds.

<!-- ubiq:dogfood-diagram -->
```mermaid
flowchart TD
  goal["no-code-spec-goal"]
  ac6["AC6 (met)"]
  goal -->|criterion| ac6
  issue_70["Tracking issue #35;70"]
  ac6 -->|tracked by| issue_70
  click issue_70 "https://github.com/Ltilak13/ubiq/issues/70"
  feature_1["feature-planning"]
  check_1["tests/test_plan.py#35;def test_shipped_features_form_a_valid_order("]
  ac6 -->|supported by| feature_1
  feature_1 -->|cites| check_1
  feature_2["feature-planning"]
  check_2["tests/test_plan.py#35;def test_plan_next_for_a_repo_using_some_features("]
  ac6 -->|supported by| feature_2
  feature_2 -->|cites| check_2
```
<!-- /ubiq:dogfood-diagram -->

</details>
