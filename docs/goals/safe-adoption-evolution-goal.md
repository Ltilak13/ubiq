---
name: safe-adoption-evolution-goal
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

# Goal: safe adoption and evolution

Status: proposed. Existing related evidence does not establish completion of this goal.

## Objective

Let existing repositories adopt and revise explicit domain models without losing
content, identities, aliases, or references. Keep uncertain classifications visible
and make migrations reviewable and recoverable.

The [domain model goal](domain-schema-goal.md) owns the model and supported formats.
This goal owns the process for introducing and changing that model. The
[contracts and evidence goal](checkable-contracts-evidence-goal.md) owns validation claims.

## Setup and maintenance

Inspect representative files and exceptions before proposing types or boundaries.
Use existing vocabulary, ownership, and interfaces as evidence. Keep inferred
classifications separate from observed facts. Let maintainers review uncertain proposals.

Adopt only the structure the repository needs. A folder can group related files,
but it does not define a domain by itself. Extract a shared part when it has a
coherent responsibility or useful reuse. Account for navigation and maintenance costs.

Use the [schema change workflow](../schema-workflow.md)
for [[schema-staging]] and [[schema-promotion]]. Preserve prior versions for recovery.
Detect new record types, missing records, and drift without silently reclassifying files.
Report unsupported formats and migrations before changing affected records.

Ubiq's own goals provide an adoption example. Other repositories choose their own
domains, record types, and layouts. Setup should reuse the method without requiring
them to copy this repository's taxonomy.

## Existing obligations and evidence

[Domain model AC3 and AC7–AC10](domain-schema-goal.md#acceptance-evidence) retain the
requirements for review, drift detection, preservation, mixed cases, and staged changes.
Their current assessments remain authoritative there. This goal adds end-to-end
adoption and recovery evidence without duplicating those assessments.

## Acceptance evidence

The goal is achieved when:

1. AC1: A representative existing repository adopts a reviewed model incrementally, with observed facts separated from uncertain classifications.
2. AC2: A migration preserves content, identities, aliases, and references, and reports unsupported cases before modifying affected records.
3. AC3: A failed migration can restore the prior model and records through a demonstrated recovery procedure.
4. AC4: Maintenance detects new types, missing records, and schema or relationship drift without silently reclassifying existing records.
5. AC5: Staged changes include migrations and adverse checks, and reports distinguish rejected, staged, and successfully promoted candidates.
6. AC6: Two repositories with different domains and layouts adopt the same method without copying each other's taxonomy.
