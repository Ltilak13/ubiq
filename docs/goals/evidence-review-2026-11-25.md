# Policy/goal evidence review

Reviewed baseline: `1290f08c4aca051f717683157239eafaa7dab4a2` on November 25, 2026.
The review compares the merged policy/goal example with existing acceptance text.
Criterion IDs and acceptance text remain unchanged. Assessments remain provisional.

## Findings

| Goal and criteria | Observed support | Remaining scope |
| --- | --- | --- |
| [Composable knowledge](composable-knowledge-goal.md), AC7 | Two real records and one typed `governs` edge, with queries in both directions, source evidence, and declaration pointers | One bounded relationship does not establish general composition across arbitrary types |
| Composable knowledge, AC8 | A policy constraint is distinct from source freshness and goal completion | Examples for decomposition, qualities, motivation, and procedural contribution |
| Composable knowledge, AC9 | Wrong endpoint types, missing targets, and missing required edges fail | Non-skill cycle rules and parent completion conditions |
| [Checkable contracts and evidence](checkable-contracts-evidence-goal.md), AC1 | Query results separate conformance, evidence status, relationship resolution, and provenance | Evidence coverage metrics and semantic assessments |
| Checkable contracts and evidence, AC2 | Schema failures identify a file and field pointer; invalid policy relationships fail | Reporting for every unsupported check and contract |
| Checkable contracts and evidence, AC4 | Missing or changed sources and absent anchors produce freshness findings | Conflicting evidence, review provenance, and demonstrated reassessment |
| Checkable contracts and evidence, AC5 | A policy governs a goal without establishing behavioral or moral correctness | Qualities and motivating ideas |
| [Explicit domain models](domain-schema-goal.md), AC4 | Field-level schema diagnostics | Authoring usability of schema descriptions as a form |
| Explicit domain models, AC5 | Reproducible record and relationship checks in a real repository | Agreed quality measurements and semantic completeness |

These criteria have partial evidence. Completion claims and parent aggregation
remain unassessed under contracts/evidence AC3 and AC6. Domain AC6 remains
unassessed: queries return declared YAML records, but this review does not measure
whether frontmatter captures most agreed facts about each file.

The evidence paths and test anchors live in each goal's frontmatter. The policy's
snapshot of the domain goal is refreshed after reviewing these assessment changes.
The governing policy and the goal's acceptance conditions do not change.

## Reuse of the inventory example

[PR #52](https://github.com/Ltilak13/ubiq/pull/52) is merged in this baseline.
Its successful CI supplies separate evidence for the
[inventory example](../../examples/inventory/README.md), including requirement-to-artifact
relationships, scenario execution, and deliberate failure demonstrations.

This review inspected its documented scope and checker entry point. It does not
rerun the Node suite or convert its reported results into broader goal acceptance.
The inventory example remains a useful second domain without duplicating its
contracts or tests here. It does not supply the missing policy/goal usability or
recovery observations, nor parent-goal completion semantics.

## Validation and limits

Run from the repository root with this checkout's CLI:

```sh
python3 -m ubiq.cli check
python3 -m pytest tests/test_goals.py tests/test_goal_governance.py tests/test_query.py tests/test_schemas.py tests/test_integrity.py -q
```

Observed result: 60 tests passed. Ubiq reported 24 terms, 523 references, zero
errors, and zero warnings. A baseline comparison preserved all 38 acceptance
criteria and their IDs.

The checks validate source anchors, provisional assessment shape, query output,
invalid declarations, freshness failures, and field-level schema diagnostics.
They do not prove comprehension or semantic truth. Human/agent usability and
recovery exercises run as separate tracks and contribute no results to this review.
