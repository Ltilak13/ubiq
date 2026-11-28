---
name: checkable-contracts-evidence-goal
status: proposed
criteria:
  AC1:
    assessment: unassessed
    support: []
    gap: Criterion needs implementation evidence and a recorded review.
  AC2:
    assessment: unassessed
    support: []
    gap: Criterion needs implementation evidence and a recorded review.
  AC3:
    assessment: unassessed
    support: []
    gap: Criterion needs implementation evidence and a recorded review.
  AC4:
    assessment: unassessed
    support: []
    gap: Criterion needs implementation evidence and a recorded review.
  AC5:
    assessment: unassessed
    support: []
    gap: Criterion needs implementation evidence and a recorded review.
  AC6:
    assessment: unassessed
    support: []
    gap: Criterion needs implementation evidence and a recorded review.
---

# Goal: checkable contracts and evidence

Existing related evidence does not establish completion of this goal.

## Objective

Make declared contracts checkable and assessments traceable to evidence. Report
structural conformance separately from semantic correctness, completeness, and judgment.

The [domain model goal](domain-schema-goal.md) owns the contracts. This goal owns
what validation establishes and what remains unknown. It uses typed relationships
from [composable knowledge](composable-knowledge-goal.md).

## Validation and judgment

Check required fields, allowed values, references, target types, and declared
relationship constraints. Identify the source location and the failed contract.
Report unsupported checks explicitly. A valid record does not establish a true claim.

Goals, principles, traits, and ideas can have their own schemas. Observable criteria
make some claims testable. A principle such as preserving ownership needs concrete
policies and evidence. Its existence in the graph does not prove compliance.

Evidence must identify the claim it supports, its source, its scope, and remaining gaps.
Separate deterministic results from human or model assessments. Record uncertainty
and the conditions under which evidence becomes stale. An unchanged anchor cannot
prove unchanged behavior. Conflicting judgments require an explicit resolution.

Define parent completion rules before aggregating subgoal assessments. A motivation
link or a completed child cannot establish that the parent's constraints are satisfied.

## Existing obligations and evidence

[Domain model AC4–AC5](domain-schema-goal.md#acceptance-evidence) retain the requirements
for actionable errors and reproducible validation. Their assessments and implementation
references remain authoritative there. [Goal assessment conventions](README.md#assessment-and-evidence)
define the current provisional schema and its limits. The new criteria below remain
unassessed until their full scope receives review.

## Acceptance evidence

The goal is achieved when:

1. AC1: Checks distinguish record conformance, relationship integrity, evidence coverage, and semantic assessment in representative reports.
2. AC2: Invalid records and relationships produce actionable locations and contract failures, while unsupported checks remain visible.
3. AC3: Each completion claim identifies its criteria, evidence sources, scope, unresolved gaps, and review provenance.
4. AC4: Changed or missing evidence triggers reassessment under explicit freshness rules, with tests for stale and conflicting evidence.
5. AC5: Examples connect goals to principles, qualities, and ideas while distinguishing structural validity from behavioral or moral judgment.
6. AC6: Parent completion follows an explicit aggregation rule and checks applicable constraints, with adverse cases for incomplete or conflicting subgoals.
