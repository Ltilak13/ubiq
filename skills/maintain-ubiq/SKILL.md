---
name: maintain-ubiq
description: Keep a ubiq-wired repo healthy — fix failing references, link unlinked mentions (W002), review orphans, propose new glossary terms, and extract repeated skill text into shared parts.
disable-model-invocation: true
---

# Maintain ubiq

The recurring pass after `apply-ubiq`. ubiq reports; this skill decides. Never weaken a check to reach green.

**Editing docs is opt-in.** Link mentions inside docs only when the repo owner wants ubiq links in their prose. Otherwise, fix through `ubiq.yaml`, `.ubiq/glossary/`, and `.ubiq/overlays/` alone, and list doc changes for a human. If you can't tell which applies, ask once.

Run `python3 -m ubiq.cli` if `ubiq` is not on `PATH`.

## 0. Check for an upgrade

1. Compare the installed CLI, repository pins, CI revisions, and installed ubiq skill sources.
2. Inspect relevant history for a pin change since the previous maintenance pass, when that baseline is available.
3. Route to [upgrade-ubiq](../upgrade-ubiq/SKILL.md) when revisions disagree, a pin changed, or the owner requested an upgrade.
4. Read that skill before the handoff. Supply the repository, observed revisions, target, baseline diagnostics, and authorized edit scope.
5. Read-only assessment is allowed. Changing pins or installations requires upgrade authorization beyond routine maintenance.
6. If the skill is unavailable, report how to obtain it from the repository's trusted ubiq source.
7. If the upgrade is blocked, keep dependent maintenance pending. Continue only checks supported by the current version.
8. After a successful return, continue at section 1, Discover groups and run the check.
   Reuse current evidence and do not repeat the upgrade in this pass.

A consistent installation continues directly to section 1. Routine maintenance does not require a remote latest-version lookup.

Done: upgrade work is completed, unnecessary, or reported as a blocker with its next action.

## Schema changes

For maintenance tasks that add or revise a type or domain schema, follow the [schema change workflow](../references/schema-workflow.md).

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

Follow the [domain review procedure](../references/domain-review.md), which uses /domain-modeling when installed, for changed concepts, relationships, or context boundaries.

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
- **E013 field value** — set the link label to the value the message names, or fix the field in frontmatter. When the fragment names no field or heading, fix its spelling.
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

Run `ubiq candidates --json` for names used in two or more docs with no record. It reports backticked identifiers. It also reports bold names when `candidate_shapes` in `ubiq.yaml` includes `bold`. For each one, decide:

- **A retired name of a term** (`to-prd` after a rename to `to-spec`) — add it as an alias.
- **A real concept** — propose a record.
- **A literal, not vocabulary** (a label string, a package or config name, bold emphasis, a bold list label) — reject it.

If most bold candidates are emphasis, propose to remove `bold` from `candidate_shapes`.

Then scan the files changed since the last pass (`git diff --name-only <base>`) for what `candidates` can't see:

- New asset groups, including skills, rules, scripts, hooks, and domain records
- New naming fields or metadata formats reported by `ubiq discover --json`
- Bold definitions (`**Term**:`) when `candidate_shapes` does not include `bold`
- `CONTEXT.md` / `GLOSSARY.md` entries with no record

Propose each candidate with where it appears. Create a record only for a name used in two or more files or defined in a human glossary. Confirm the rest first.

**Done when:** each candidate is created, rejected, or listed for a human.

## 6. Composition

Use this step in a skill repository that sets `edges` in `ubiq.yaml`. Skip it in other repositories.
Report overlap and drift in each pass. Change skill text only when the owner asked for a refactor.

1. Run `ubiq check --json`. Keep the result as the baseline.
2. Run `ubiq overlap --json`. Add `--unit line` for prose with one sentence on each line.
3. Record one decision for each cluster in a table with three columns: cluster, decision, and reason.
   - **Extract a part** when the cluster holds one rule that must change together.
     An example is a precondition that six skills repeat in different words.
   - **Invoke the composite skill** when the repeated text only calls other skills.
     If the composite blocks model invocation (W003), keep the text and record that reason.
   - **Keep the copies** when one of these conditions is true. Record the condition.
     - The match is coincidental.
     - The text is one line, and an include costs one more file read.
     - No directory that all callers install can hold the part.
     - The author wants the repetition.
4. Put each new part where every caller can reach it after installation.
   Use an installed shared directory when the repository has one. Otherwise put
   it in `parts/` inside the skill directory that owns its subject.
   A top-level `_shared/` folder omitted from installation resolves only in the source tree (W004).
5. Give the part a naming field. If callers use the part in different modes, list the modes in `inputs`.
   Register its path with a glossary rule in a namespace from `edges.include.ns` (default: `part`).
   Use the repository's schema workflow if registration needs a schema change.
6. Replace each copy with an include link. Write the mode after the link:
   ``Follow the [tracker setup](../setup/parts/tracker-setup.md) in `labels` mode.``
7. Keep text that only one caller needs in that caller.
8. Run `ubiq check`. Compare the result with the baseline.
   The only differences must be the new part records and their include edges. Fix E002, E012, and W004.
9. Run `ubiq overlap` again. Check that each extracted cluster is gone.
   Run `ubiq graph <part> --callers` to see the new edges.
10. For each W005, declare the reference in one edge field.
    Use the invoke field (`uses`) for a dependency. Use the route field (`routes`) for `not for X; use Y` text.
    If the reference is wrong, fix the text. Do not add an edge only to remove a warning.

A smaller overlap count alone does not show success. Removing shared rules also makes the count smaller.

**Done when:** each cluster has a decision, and `ubiq check` matches the baseline except for the new parts and edges.
The report lists each cluster that you kept, with its reason.

## 7. Re-check and report

Follow the [validation procedure](../references/validate-changes.md), which uses /validate-change when installed.

Run `ubiq check` again. Report what you fixed, linked, excepted, created, and left for a human. Include schema changes, group coverage, composition decisions, and unresolved context candidates.

**Done when:** `ubiq check` exits 0 and the summary lists everything not resolved.
