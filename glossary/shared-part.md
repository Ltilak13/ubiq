---
term: shared part
ns: core
---

A Markdown file that holds one procedure, policy, or precondition that several
skills follow. Skills include it by link and never invoke it on its own. Register
parts with a glossary rule, for example `skills/_shared/*.md` with `ns: part`, so
every link to a part is a checked [[reference]]. See
[composable skills](../docs/composable-skills-goal.md).
