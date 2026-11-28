Feature: Composable knowledge
  Scenarios that accept criteria of the composable knowledge goal
  (composable-knowledge-goal.md). A scenario tagged @ACn accepts that criterion:
  the criterion is met when every scenario tagged with it passes on main.
  Steps: tests/scenarios/test_goal_scenarios.py.

  Background:
    Given a skill repository that registers parts with this glossary rule:
      """
      - {glob: "skills/_shared/*.md", term_field: name, ns: part}
      """

  @AC1
  Scenario: A part registered by configuration alone is a checked reference
    Given the part "checkout" in "skills/_shared/checkout.md"
    And the skill "push" in "skills/push/SKILL.md" says:
      """
      Follow [checkout](../_shared/checkout.md).
      """
    And the skill "ship" in "skills/ship/SKILL.md" says:
      """
      Then [checkout](../_shared/checkout.md) again.
      """
    When I run "ubiq refs part:checkout"
    Then the references come from:
      | file                 |
      | skills/push/SKILL.md |
      | skills/ship/SKILL.md |
    When "skills/_shared/checkout.md" moves to "skills/_shared/checkout-branch.md"
    And I run "ubiq check"
    Then it fails with:
      | code | file                 |
      | E002 | skills/push/SKILL.md |
      | E002 | skills/ship/SKILL.md |

  @AC2
  Scenario: Graph queries return each edge with its kind, direction, and declaration
    Given the part "checkout" in "skills/_shared/checkout.md"
    And the skill "push" in "skills/push/SKILL.md" says:
      """
      Follow [checkout](../_shared/checkout.md).
      """
    And the skill "ship" in "skills/ship/SKILL.md" uses "push"
    When I run "ubiq graph ship"
    Then the edges are:
      | kind    | source     | target        | file                 | line |
      | invoke  | skill:ship | skill:push    | skills/ship/SKILL.md | 3    |
      | include | skill:push | part:checkout | skills/push/SKILL.md | 5    |
    When I run "ubiq graph part:checkout --callers"
    Then the edges are:
      | kind    | source     | target        | file                 | line |
      | include | skill:push | part:checkout | skills/push/SKILL.md | 5    |
      | invoke  | skill:ship | skill:push    | skills/ship/SKILL.md | 3    |

  @AC4
  Scenario: Invoking a skill that only a user may invoke is reported
    Given the skill "spec" in "skills/spec/SKILL.md" is user-invoked only
    And the skill "lead" in "skills/lead/SKILL.md" uses "spec"
    When I run "ubiq check"
    Then it passes with the warning "W003" in "skills/lead/SKILL.md"

  @AC4
  Scenario: A link that resolves only in the source tree is reported
    Given the part "checkout" in "skills/_shared/checkout.md"
    And the skill "push" in "skills/push/SKILL.md" says:
      """
      Follow [checkout](../_shared/checkout.md).
      """
    When I run "ubiq check"
    Then it passes with the warning "W004" in "skills/push/SKILL.md"

  @AC6
  Scenario: A part that includes another part is followed, not a cycle
    Given the part "checkout" in "skills/_shared/checkout.md"
    And the part "publish" in "skills/_shared/publish.md" says:
      """
      Follow [checkout](checkout.md), then push.
      """
    And the skill "ship" in "skills/ship/SKILL.md" says:
      """
      Follow [publish](../_shared/publish.md).
      """
    When I run "ubiq check"
    Then it passes
    When I run "ubiq graph ship"
    Then the edges go:
      | source       | target        |
      | skill:ship   | part:publish  |
      | part:publish | part:checkout |

  @AC6
  Scenario: Parts that include each other fail as an include cycle
    Given the part "a" in "skills/_shared/a.md" says:
      """
      Then [b](b.md).
      """
    And the part "b" in "skills/_shared/b.md" says:
      """
      Then [a](a.md).
      """
    When I run "ubiq check"
    Then it fails with the error "E011"

  @AC6
  Scenario: Skills that hand off to each other are an allowed invoke cycle
    Given the skill "plan" in "skills/plan/SKILL.md" uses "build"
    And the skill "build" in "skills/build/SKILL.md" uses "plan"
    When I run "ubiq check"
    Then it passes

  @AC6
  Scenario Outline: Overlap reports near-duplicate text only at or above its threshold
    Given the skills "a" and "b" share 19 of 20 words
    When I run "ubiq overlap --min-similarity <threshold>"
    Then overlap reports <clusters> cluster(s)

    Examples:
      | threshold | clusters |
      | 0.61      | 1        |
      | 0.62      | 0        |
