# Schema change workflow

Use this workflow to develop a [[domain-schema]] through [[schema-staging]] and
[[schema-promotion]]. The CLI provides discovery, linker checks, and
[native schema validation](schema-validation.md) through `ubiq check`.
Register active schema bindings in `ubiq.yaml`. Keep candidate bindings separate until promotion.

## Select the workflow

| Task | Skill or check | Result |
| --- | --- | --- |
| Adopt Ubiq in a repository | apply-ubiq | Initial discovery, configuration, and schema candidates |
| Upgrade an existing installation | [[skill:upgrade-ubiq]] | Compatible pins, skill revisions, and capability decisions |
| Reconcile an existing repository | maintain-ubiq | Evidence-backed changes to existing records or staged schemas |
| Resolve domain language or boundaries | domain-modeling, when installed, or direct glossary/code inspection | Proposed domains, responsibilities, interactions, and unresolved meanings |
| Stage a candidate | The calling [[skill:apply-ubiq]], [[skill:maintain-ubiq]], or [[skill:upgrade-ubiq]] skill | Schema diff, record migration, evidence, and tests in one bundle |
| Validate | Native repository checks and the candidate's documented schema tests; validate-change when installed | Passing and failing cases, compatibility results, and coverage limits |
| Review and finish | The host's review/closeout workflow, when available | Requirement-to-evidence assessment |
| Publish | commit-slices or push-slices when installed and authorized | Separate, explicit commit or commit-and-push action |

Optional host skills are adapters. Their absence does not remove the required
analysis or validation. Do not assume those skills ship with Ubiq.

## Stage a useful change

1. Inspect changed files and existing staged candidates before creating another proposal.
2. Record the active schema version, repository revision, affected record types, and source evidence.
3. Identify the new information the change captures or the ambiguity it resolves.
4. Infer fields from representative files and exceptional cases. Preserve explicit domain meaning.
5. Stage the schema diff and corresponding record migrations under `.ubiq/staging/<change>/`.
6. Include type-specific tests, domain constraints, compatibility cases, and invalid examples.
7. Record proposed destinations and any missing migration or validation capability.

A new field needs a meaning, a type, an applicability rule, and evidence.
Do not add fields solely because a parser found metadata keys. Do not treat
unknown values as complete answers. Preserve the distinction between record
type, domain context, and folder location.

Use JSON Schema as the portable contract and YAML for readable frontmatter.
A TypeScript authoring tool may export JSON Schema from Zod. Keep one canonical
definition and reject lossy exports for required constraints.

## Test and repair

1. Validate the schema itself.
2. Validate the candidate records and the affected existing records.
3. Test required fields, value types, allowed values, and domain-specific conditions.
4. Check relationship targets, target types, cardinality, and cross-record invariants.
5. Confirm that evidence still matches the inspected source state.
6. Verify that invalid cases fail for the expected reason.
7. Compare coverage and unknown values with the recorded baseline.
8. Repair or reject unsupported and incompatible candidates within the host's retry limits.

State the tested denominator. Sample conformance does not establish corpus-wide
compatibility or semantic completeness. Report a missing validator or migration
as a promotion blocker, even when the sample checks pass.

## Promote a passing candidate

1. Confirm that promotion is inside the user's authorized scope.
2. Resolve competing meanings that affect the schema or leave the candidate staged.
3. Require passing checks for the affected corpus and a tested migration.
4. Require the normal validation command to consume the promoted schema.
5. Apply the schema selection and record migration together. Preserve the prior version for recovery.
6. Re-run the normal checks against the active state.
7. Mark promotion complete only after the active state passes.

A manifest or a successful staging run is not evidence of promotion. If the
normal checker cannot enforce the new schema, keep the candidate staged and
report the missing integration. Do not silently replace active records.

Publication is a separate action. A request to inspect or stage schema changes
does not authorize a remote push.
