# Ubiq goals

| Goal | Focus |
| --- | --- |
| [Domain schema](domain-schema-goal.md) | Describe domains through typed facts and checked relationships |
| [Composable skills](composable-skills-goal.md) | Reuse rules and check that their dependencies can be followed |
| [Human and agent readability](human-agent-readability-goal.md) | Make source and preview useful to both audiences |

Each goal is a [[glossary record]] in the `goal` namespace. Its frontmatter
connects acceptance criteria to supporting features and evidence. The body
explains the objective and defines each criterion with a stable `AC` label.
Preserve those labels when reordering criteria.

Frontmatter owns the current assessment. `unassessed` means no criterion review
is recorded. `partial` means supporting evidence is identified but a gap remains.
Neither value asserts that the criterion passed. The initial schema deliberately
supports these provisional assessments only. A verified state needs a defined
review record before it can be added.

For each supporting feature, `implementation` identifies its source and `check`
identifies a test. Each location uses a repository-relative `path` and an exact
text `anchor`. The `gap` states what those locations do not establish. Existing
narrative evidence remains useful context, including past acceptance claims.

`python3 -m ubiq.cli check` validates the frontmatter shape and registered
references. `python3 -m pytest tests/test_goals.py` checks criterion labels and
source locations. Neither command proves that a feature satisfies a goal.
Run the cited tests and review their assertions against the criterion before
claiming corroboration. Anchors detect missing evidence, but do not detect every
semantic change within a feature or test.

Use the [GitHub preview check](github-preview.md) to read canonical metadata
through the native frontmatter display or Code/Raw. The procedure separates
source integrity from observed preview access.
