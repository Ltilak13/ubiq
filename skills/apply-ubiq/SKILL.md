---
name: apply-ubiq
description: Wire ubiq into a repo — glossary, overlays, delimiters, catalogs, and CI — without editing files the repo already owns.
disable-model-invocation: true
---

# Apply ubiq

ubiq is a **linter, not a migrator**. It never rewrites docs. Linker metadata lives in `ubiq.yaml` and `.ubiq/`. Owned files (`SKILL.md`, `plugin.json`, published docs) stay as the repo already writes them — glob `term_field` / `ns` and overlays attach meaning without a patch.

Install: `pip install ubiq` (or `pip install -e <path-to-ubiq>`). Run `python3 -m ubiq.cli` if the script is not on `PATH`.

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

## 1. Discover the vocabulary

Run `ubiq discover --json` before you select record families.
The command reports asset groups by source directory, schema proposals, and candidate domain contexts.
It preserves source paths and does not edit files.
Read existing `GLOSSARY-MAP.md` and context glossaries before you interpret directory candidates.
Inspect representative files in each group, including files with different metadata fields.

1. If meanings, relationships, or context boundaries need clarification, use /domain-modeling when installed.
2. Read that skill before you continue the domain review.
3. Supply the repository, source evidence, disputed meanings, and permitted edit scope.
4. If the skill is unavailable, inspect the glossary and relevant code directly.
5. Test proposed meanings and relationships with concrete scenarios.
6. Ask the owner to resolve competing meanings that the evidence cannot settle.
7. Record agreed definitions and unresolved questions within the permitted edit scope.
8. Reuse established definitions when this review finds no conflict.

Design each group's schema from those files:

- Select the existing naming field, such as `term`, `name`, or `title`.
- Preserve explicit namespaces, aliases, and IDs when their meaning is consistent.
- Keep mixed formats in separate glossary rules. Do not force one field onto every file in a folder.
- Use an overlay when the source has no suitable naming field.
- Keep inventories in separate arrays, such as `skills`, `rules`, `scripts`, and `hooks`.
- Map each array to its own `catalogs` entry and coverage paths.
- Add other record families when the repository provides evidence for them.

Use directory structure to propose groups. Confirm domain boundaries through vocabulary, ownership, and code dependencies.
Technical categories describe asset types. Business contexts describe where a term has one meaning.
A `scripts` folder is not evidence for a business context.
The CLI does not infer domain semantics or relationships from directory names.
Treat `directory-candidate` namespaces and unknown naming fields as proposals that need inspection.

Keep a single glossary when the repository has one context.
For established multiple contexts, group records under `.ubiq/glossary/<context>/` and assign the corresponding namespace.
Preserve existing context glossaries and their map instead of creating duplicate definitions.
Record cross-context relationships only when code or documentation supports them.
Ask the owner when competing meanings leave a boundary unresolved.

Walk the repo for words that should be load-bearing:

- Existing frontmatter that already names things (`name:` on `SKILL.md`, `title:`, …)
- Slash-commands (`/tdd`) and wiki-links (`[[term]]`)
- A human glossary (`CONTEXT.md` Language section, `GLOSSARY.md`)
- JSON/YAML inventories (`.claude-plugin/plugin.json` `skills` arrays)

**Done when:** each group has a source path, naming field or overlay strategy, namespace rationale, and inventory requirement. Unresolved domain boundaries remain explicit.

## 2. Write `ubiq.yaml`

Start from `ubiq init` or copy the starter.
Initialization detects recognizable assets and writes separate arrays in `.ubiq/catalogs/assets.json`.
It reuses suitable frontmatter fields and creates sidecars for other assets.
Sidecar paths preserve the source directory structure under `.ubiq/overlays/assets/<family>/`.
The discovery snapshot is `.ubiq/discovery.json`. Review its context and schema proposals before assigning domain namespaces.
Initialization refuses to overwrite existing configuration or generated metadata paths.
For an existing configuration, use `ubiq discover --json` and update its metadata through this workflow. Keep docs **narrow** — do not use `**/*.md`.

```yaml
glossary:
  - glob: ".ubiq/glossary/**/*.md"
    term_field: term
    ns: repo
  # Existing files are records without editing them:
  - glob: "skills/**/SKILL.md"
    term_field: name
    ns: skill
docs:
  - "README.md"
  - "AGENTS.md"
  - "CLAUDE.md"
  - "CONTEXT.md"
  - "GLOSSARY.md"
  - "GLOSSARY-MAP.md"
  - ".agents/**/*.md"
  - ".ubiq/**/*.md"
  - "docs/**/*.md"
  - "skills/**/*.md"          # add globs the repo actually writes
historical:
  - "CHANGELOG.md"            # scanned; unresolved [[old]] / /old-name do not fail
overlays:
  - ".ubiq/overlays/**/*.md"
ref_fields: [uses]
delimiters:
  - pattern: "/"
    only_known: true          # only glossary names; /tmp and /clear are silent
    except: [plugin]          # collisions with a *known* term that isn't a slash-command
catalogs:
  - file: ".claude-plugin/plugin.json"
    items: skills
    term: basename            # ./skills/engineering/tdd → tdd
    cover:                    # every matching record must appear in the inventory
      - "skills/engineering/**/SKILL.md"
      - "skills/productivity/**/SKILL.md"
```

- **`[[term]]`** — wiki-link; always explicit; typos fail. File-shaped targets (`[[GLOSSARY.md]]`, `[[dir/x]]`, `[[./x]]`) are not terms unless that name is a defined term (`[[SKILL.md]]` still counts if you named it). If the file exists in-repo, ubiq **follows** it into the scan — `docs:` are roots, not a closed list. A missing file (a teaching-workspace `[[MISSION.md]]`) is not an error. Relative markdown links (`[x](./a.md)`) are followed the same way. Do not rewrite `ubiq.yaml` to list every reachable file; widen `docs:` only for scan *roots* that nothing already links to.
- **`/` delimiter** — slash-commands, including inside backticks. Default is strict (every `/slug` is a ref). `only_known: true` is quieter; `except` is only for tokens that *are* glossary names but must not count (`/plugin` vs a term named `plugin`).
- **`historical`** — mentions and resolved refs still count; E002/E003/E004/E006 on unresolved refs do not.
- **`catalogs`** — an inventory is not a glossary. Do not glob `plugin.json` as records (duplicate definition vs the real file). Missing entry → E006; a `cover` record not listed → E007. Coverage applies to registered records only. Compare discovery results with the inventory to find files without records.

**Done when:** `ubiq.yaml` names every record family, the docs the linker should read, and any catalog/historical/delimiter rules.

## 3. Records and overlays

| Kind | Where | When |
| --- | --- | --- |
| Org / domain term | `.ubiq/glossary/<context>/<term>.md` with `term:` | No existing file already defines it. Omit the context directory for a single context. |
| Existing file as record | glossary glob + `term_field` / `ns` | Frontmatter already has the name |
| Alias, `uses:`, extra `ns` | `.ubiq/overlays/<name>.md` with `source:` | The source file must not be edited |

Overlay key is `source:` (not `on:` — YAML 1.1 loads `on:` as boolean `True`). Overlay files are scanned as docs so `ref_fields` on them participate.

`CONTEXT.md` is a **view**, not a second glossary. Keep Relationships and flagged ambiguities there; leave definitions in records. Dump a Language section with `ubiq terms --format context --ns repo` when a readable copy helps — then trim it; do not maintain two definitions.

**Done when:** every load-bearing name has exactly one defining record, and no owned file was patched for the linker.

## 4. Check, then CI

1. Use /validate-change when installed after changes to configuration, records, overlays, schemas, or migrations.
2. Read that skill before you select checks.
3. Supply the repository, changed paths, acceptance criteria, and current check evidence.
4. If the skill is unavailable, inspect repository instructions and run the relevant checks directly.
5. Always run `ubiq check`, including for a read-only inspection.
6. For schema or migration changes, also test affected records and invalid cases through the schema change workflow.
7. Repair failures within the authorized scope before you report success.
8. Report unavailable checks as validation gaps.
9. The companion skill does not authorize commits or publication.

```bash
python3 -m ubiq.cli check
python3 -m ubiq.cli terms
python3 -m ubiq.cli refs "<term>"
```

Fix loop: unresolved ref → add a record, an overlay alias, or (delimiter only) `except` / `only_known`. Duplicate definition → stop globbing the copy; use a catalog or delete the extra record. Orphans (W001) are warnings. A path wiki-link to an existing file is already reachable — do not add it to `docs:` and re-run; ubiq followed it. Widen `docs:` only when a file should be a root (nothing scanned links to it).

CI — GitHub Action:

```yaml
- uses: Ltilak13/ubiq@main
```

Or `ubiq check` in any job that already has Python. Gate merges on exit 1.

**Done when:** `ubiq check` exits 0 on this repo, and CI runs it on every PR.

Unlinked mentions (W002) are off by default. When `ubiq check` exits 0, offer to turn them on. If the owner agrees, set `unlinked_mentions: warn`, run `ubiq check --json`, count the warnings per term, and propose an `unlinked_except` list of ordinary words and core nouns. Expect hundreds of warnings on a first run.

Ongoing upkeep — unlinked mentions, orphans, and new terms — is the `maintain-ubiq` skill.
