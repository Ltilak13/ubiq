---
term: shared part
ns: core
---

A Markdown file that holds one procedure, policy, or precondition that several
skills follow. Skills include it by link and never invoke it on its own. Register
parts with a glossary rule, for example `skills/*/parts/*.md` with `ns: part`, so
every link to a part is a checked [[reference]]. A part may list enumerated
inputs, such as a mode, and each include names one. See
[composable skills](../docs/goals/composable-skills-goal.md).
