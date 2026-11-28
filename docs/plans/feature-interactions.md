---
name: feature-interactions
status: proposed
issue: 156
trunk: main
steps:
  derive-interactions:
    issue: 157
    requires: []
  report-change-impact:
    issue: 158
    requires: [derive-interactions]
  detect-pr-collisions:
    issue: 159
    requires: [report-change-impact]
  map-breaking-changes:
    issue: 160
    requires: [report-change-impact]
  declare-feature-conflicts:
    issue: 161
    requires: []
---

# Feature interactions and change impact

AC9 of the [[goal:code-records-goal]] covers interactions derived from
records. The [feature interactions decision](../decisions/0004-feature-interactions.md)
distinguishes derived interactions from declared conflicts.

Dependencies outside this plan are symbol ownership (#155) for deriving
interactions, PR tracking (#125) for collision detection, scenario results
(#67) for mapping breaking changes, and tracking fields (#120) for declaring
feature conflicts.
