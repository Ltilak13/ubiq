---
name: checkable-contracts-evidence-goal
status: in-progress
criteria:
  AC1:
    assessment: partial
    support:
    - feature: Separate conformance, evidence status, and provenance
      implementation:
        path: src/ubiq/query.py
        anchor: def select(
      check:
        path: tests/test_query.py
        anchor: def test_select_complete_record_and_provenance(
    - feature: Registered policy governing a goal
      implementation:
        path: .ubiq/knowledge/goal-governance.yaml
        anchor: 'id: goal-evidence-policy--governs--domain-schema-goal'
      check:
        path: tests/test_goal_governance.py
        anchor: def test_registered_goal_governance_queries(
    gap: Reports distinguish conformance and evidence status, with relationship resolution and
      declaration pointers. Evidence coverage metrics and semantic assessment remain outside this
      example.
  AC2:
    assessment: partial
    support:
    - feature: Field-level schema failure locations
      implementation:
        path: src/ubiq/schemas.py
        anchor: def assess_schemas(
      check:
        path: tests/test_schemas.py
        anchor: def test_native_schema_validates_domain_contract_and_reports_pointer(
    - feature: Policy-to-goal endpoint and cardinality constraints
      implementation:
        path: .ubiq/schemas/goal-governance.json
        anchor: '"governs": {'
      check:
        path: tests/test_goal_governance.py
        anchor: def test_goal_governance_rejects_invalid_declarations(
    gap: Schema errors identify files and field pointers, and the example rejects invalid relationships.
      This review does not establish reporting for every unsupported check or contract.
  AC3:
    assessment: unassessed
    support: []
    gap: Criterion needs implementation evidence and a recorded review.
  AC4:
    assessment: partial
    support:
    - feature: Missing and changed source evidence remains visible
      implementation:
        path: src/ubiq/integrity.py
        anchor: def assess_integrity(
      check:
        path: tests/test_query.py
        anchor: def test_evidence_failure_is_visible_without_losing_records(
    - feature: Policy-to-goal endpoint and cardinality constraints
      implementation:
        path: .ubiq/schemas/goal-governance.json
        anchor: '"governs": {'
      check:
        path: tests/test_goal_governance.py
        anchor: def test_goal_governance_rejects_invalid_declarations(
    gap: Changed or missing bytes and anchors produce freshness findings. Conflicting evidence,
      review provenance, and a reassessment workflow remain unverified.
  AC5:
    assessment: partial
    support:
    - feature: Registered policy governing a goal
      implementation:
        path: .ubiq/knowledge/goal-governance.yaml
        anchor: 'id: goal-evidence-policy--governs--domain-schema-goal'
      check:
        path: tests/test_goal_governance.py
        anchor: def test_registered_goal_governance_queries(
    gap: A policy constrains a goal without proving behavioral or moral correctness. Required
      qualities and motivating ideas are not represented in this example.
  AC6:
    assessment: unassessed
    support: []
    gap: Criterion needs implementation evidence and a recorded review.
---

# Goal: checkable contracts and evidence

Status: in progress. The policy/goal example provides partial evidence, not goal completion.

See the [bounded evidence review](evidence-review-2026-11-25.md) for the scope
and checks behind the current partial assessments.

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
define the current provisional schema and its limits. The frontmatter records which criteria have partial evidence and which remain
unassessed. Full acceptance still requires the outstanding scope.

## Acceptance evidence

The goal is achieved when:

1. AC1: Checks distinguish record conformance, relationship integrity, evidence coverage, and semantic assessment in representative reports.
2. AC2: Invalid records and relationships produce actionable locations and contract failures, while unsupported checks remain visible.
3. AC3: Each completion claim identifies its criteria, evidence sources, scope, unresolved gaps, and review provenance.
4. AC4: Changed or missing evidence triggers reassessment under explicit freshness rules, with tests for stale and conflicting evidence.
5. AC5: Examples connect goals to principles, qualities, and ideas while distinguishing structural validity from behavioral or moral judgment.
6. AC6: Parent completion follows an explicit aggregation rule and checks applicable constraints, with adverse cases for incomplete or conflicting subgoals.
