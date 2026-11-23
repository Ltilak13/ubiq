---
name: maintain-ubiq
description: Keep a ubiq-wired repo healthy — fix failing references, link unlinked mentions (W002), review orphans, and propose new glossary terms.
disable-model-invocation: true
---

# Maintain ubiq

The recurring pass after `apply-ubiq`. ubiq reports; this skill decides. Never weaken a check to reach green.

**Editing docs is opt-in.** Link mentions inside docs only when the repo owner wants ubiq links in their prose. Otherwise, fix through `ubiq.yaml`, `.ubiq/glossary/`, and `.ubiq/overlays/` alone, and list doc changes for a human. If you can't tell which applies, ask once.

Run `python3 -m ubiq.cli` if `ubiq` is not on `PATH`.

## Schema changes

Read [the schema change workflow](../../docs/schema-workflow.md) when the task adds or changes type/domain schemas.
Inspect `.ubiq/staging/` for existing candidates before creating a new one.
Stage useful schema changes with their record migrations, evidence, and tests.
Test affected existing records and invalid cases. Repair or reject unsupported candidates.
Register promoted contracts with `schemas:` bindings in `ubiq.yaml`.
Use the [native schema contract](../../docs/schema-validation.md) for file selection, type validation, and graph integrity.
Verify that local hooks and CI use the validator revision that supports those bindings.
Promote only within the authorized scope after the normal checker can enforce the schema and the migration passes.
If enforcement or migration is unavailable, keep the candidate staged and report the promotion blocker.
Do not describe a passing sample check as an active schema change.

## 1. Discover groups and run the check

Run `ubiq discover --json` before the check.
Compare the current groups and schema proposals with `ubiq.yaml`, overlays, catalogs, and existing context glossaries.
The report is read-only. `.ubiq/discovery.json`, when present, is the initialization snapshot and can be stale.

Inspect new, moved, and renamed files in each group.
Choose naming fields from actual frontmatter. Preserve aliases, IDs, and explicit namespaces.
Keep different formats separate when one naming rule would change their meaning.
Use sidecars for scripts, hooks, or rules without suitable frontmatter.
Maintain separate inventory arrays for each asset family and matching catalog coverage.
Compare discovered paths with registered records because catalog coverage cannot detect files without records.
Exclude generated copies and dependencies after you identify their canonical sources.

Read `GLOSSARY-MAP.md` and context glossaries when they exist.

1. If changed concepts, relationships, or context boundaries need clarification, use /domain-modeling when installed.
2. Read that skill before you continue the domain review.
3. Supply the repository, changed concepts, source evidence, and permitted edit scope.
4. If the skill is unavailable, inspect the glossary and relevant code directly.
5. Test proposed meanings and relationships with concrete scenarios.
6. Ask the owner to resolve competing meanings that the evidence cannot settle.
7. Record agreed definitions and unresolved questions within the permitted edit scope.
8. Reuse established definitions for routine reference repairs that do not change meaning.

Use directory candidates to investigate domain boundaries through vocabulary, ownership, and dependencies.
A technical folder does not establish a business context.
Do not rename a namespace solely because a directory moved.
Preserve qualified references when reorganizing records, and check every affected reference.
Keep one glossary for a single context. Group records by established context when meanings differ across domains.
Ask the owner if the evidence cannot resolve competing meanings.
Apply the new-vocabulary criteria in step 5 before adding records.


```bash
ubiq check --json
```

Group diagnostics by code. Fix errors before warnings.

**Done when:** you have the list of errors and warnings to work through.

## 2. Fix errors

- **E002 unresolved** — a typo: fix the reference (if editing is allowed) or add an overlay alias. A rename: add the old name as an alias, or update the references.
- **E003 ambiguous** — qualify it: `[[ns:term]]`.
- **E001 duplicate** — keep one record; move the other name into its `aliases`.
- **E006 / E007 catalog** — bring the inventory and the records back in sync.
- **E005 / E008** — fix the file or setting the message names.

Never delete a failing reference, mark a live doc `historical`, widen a delimiter `except`, or lower a kind's severity or `scans` under `references:` just to pass.

**Done when:** `ubiq check` reports no errors.

## 3. Unlinked mentions (W002)

Requires `unlinked_mentions: warn` in `ubiq.yaml`. First count the warnings per term. Then decide each term before its lines:

- **The word is ordinary here** (`PR` for a skill named `pr`, "implement" for a skill named `implement`) — add the term to `unlinked_except` once. Don't link around it file by file.
- **The term is the repo's core noun** (`skill` in a skills repo, `record` in ubiq) and warns in most sections — add it to `unlinked_except`. A link in every section is noise.

For each remaining warning:

- **The mention means the term** — link it at the reported line, in the style the repo already uses: a Markdown link to the record, `[[term]]`, or `/slug`. Link only the first mention in the section and leave the rest plain.
- **The mention is a literal the reader must keep as written** — leave it. Examples: a quoted name in an agent instruction (`call the Skill tool with "tdd"`), a command argument, a label string.
- **Unclear** — leave it and list it in the summary.

Don't add links inside headings, code, or quoted text. A SKILL.md body is an agent prompt: link there only where the link helps the agent find the record.

**Done when:** every W002 is linked, excepted, or listed for a human.

## 4. Orphans (W001)

A new term not yet used is fine; leave it. A term whose concept is gone: propose deleting the record, and delete it only after confirmation.

## 5. New vocabulary

Run `ubiq candidates --json` for backticked identifiers used in two or more docs with no record. For each one, decide:

- **A retired name of a term** (`to-prd` after a rename to `to-spec`) — add it as an alias.
- **A real concept** — propose a record.
- **A literal, not vocabulary** (a label string, a package or config name) — reject it.

Then scan the files changed since the last pass (`git diff --name-only <base>`) for what `candidates` can't see:

- New asset groups, including skills, rules, scripts, hooks, and domain records
- New naming fields or metadata formats reported by `ubiq discover --json`
- Bold definitions (`**Term**:`) and `CONTEXT.md` / `GLOSSARY.md` entries with no record

Propose each candidate with where it appears. Create a record only for a name used in two or more files or defined in a human glossary. Confirm the rest first.

**Done when:** each candidate is created, rejected, or listed for a human.

## 6. Re-check and report

1. Use /validate-change when installed after changes to configuration, records, overlays, schemas, or migrations.
2. Read that skill before you select checks.
3. Supply the repository, changed paths, acceptance criteria, and current check evidence.
4. If the skill is unavailable, inspect repository instructions and run the relevant checks directly.
5. For schema or migration changes, also test affected records and invalid cases through the schema change workflow.
6. Repair failures within the authorized scope before you report success.
7. Report unavailable checks as validation gaps.
8. The companion skill does not authorize commits or publication.

Run `ubiq check` again. Report what you fixed, linked, excepted, created, and left for a human. Include schema changes, group coverage, and unresolved context candidates.

**Done when:** `ubiq check` exits 0 and the summary lists everything not resolved.
