---
name: maintain-ubiq
description: Keep a ubiq-wired repo healthy — fix failing references, link unlinked mentions (W002), review orphans, and propose new glossary terms.
disable-model-invocation: true
---

# Maintain ubiq

The recurring pass after `apply-ubiq`. ubiq reports; this skill decides. Never weaken a check to reach green.

**Editing docs is opt-in.** Link mentions inside docs only when the repo owner wants ubiq links in their prose. Otherwise, fix through `ubiq.yaml`, `.ubiq/glossary/`, and `.ubiq/overlays/` alone, and list doc changes for a human. If you can't tell which applies, ask once.

Run `python3 -m ubiq.cli` if `ubiq` is not on `PATH`.

## 1. Run the check

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

Never delete a failing reference, mark a live doc `historical`, or widen a delimiter `except` just to pass.

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

- New skill directories or `name:` fields
- Bold definitions (`**Term**:`) and `CONTEXT.md` / `GLOSSARY.md` entries with no record

Propose each candidate with where it appears. Create a record only for a name used in two or more files or defined in a human glossary. Confirm the rest first.

**Done when:** each candidate is created, rejected, or listed for a human.

## 6. Re-check and report

Run `ubiq check` again. Report what you fixed, linked, excepted, created, and left for a human.

**Done when:** `ubiq check` exits 0 and the summary lists everything not resolved.
