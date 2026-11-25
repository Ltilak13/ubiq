---
term: composition edge
ns: core
---

A typed edge from a skill or [[shared part]] to another record. An invoke edge
runs another skill as its own step and is declared in `uses`; the target's
invocation policy applies. An include edge tells the agent to read a part and
follow it in place; it comes from a link to the part's record and must resolve
where the skill is installed. Both are dependencies. A route edge, declared in a
field such as `routes`, points elsewhere without depending on the target ("not
for X; use Y"), so graph walks show it but do not follow it.
A reference edge describes an informational example or comparison. Its target
must resolve, but it is not a dependency or route. See
[composable skills](../docs/goals/composable-skills-goal.md).
