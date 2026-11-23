---
term: composition edge
ns: core
---

A typed dependency from a skill or [[shared part]] to what it reuses. An invoke
edge runs another skill as its own step and is declared in `uses`; the target's
invocation policy applies. An include edge tells the agent to read a part and
follow it in place; it comes from a link to the part's record and must resolve
where the skill is installed. Ubiq does not build include edges yet; see
[composable skills](../docs/composable-skills-goal.md).
