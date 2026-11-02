---
name: apply-ubiq
description: Wire ubiq into a repo — glossary, overlays, delimiters, catalogs, and CI — without editing files the repo already owns.
disable-model-invocation: true
---

# Apply ubiq

ubiq is a **linter, not a migrator**. It never rewrites docs. Linker metadata lives in `ubiq.yaml` and `.ubiq/`. Owned files (`SKILL.md`, `plugin.json`, published docs) stay as the repo already writes them — glob `term_field` / `ns` and overlays attach meaning without a patch.

Install: `pip install ubiq` (or `pip install -e <path-to-ubiq>`). Run `python3 -m ubiq.cli` if the script is not on `PATH`.

## 1. Discover the vocabulary

Walk the repo for words that should be load-bearing:

- Existing frontmatter that already names things (`name:` on `SKILL.md`, `title:`, …)
- Slash-commands (`/tdd`) and wiki-links (`[[term]]`)
- A human glossary (`CONTEXT.md` Language section, `GLOSSARY.md`)
- JSON/YAML inventories (`.claude-plugin/plugin.json` `skills` arrays)

**Done when:** you can name the record families (what is already a file vs what needs a new record) and any inventory that must stay in sync with those files.

## 2. Write `ubiq.yaml`

Start from `ubiq init` or copy the starter. Keep docs **narrow** — do not use `**/*.md`.

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
- **`catalogs`** — an inventory is not a glossary. Do not glob `plugin.json` as records (duplicate definition vs the real file). Missing entry → E006; a `cover` record not listed → E007.

**Done when:** `ubiq.yaml` names every record family, the docs the linker should read, and any catalog/historical/delimiter rules.

## 3. Records and overlays

| Kind | Where | When |
| --- | --- | --- |
| Org / domain term | `.ubiq/glossary/<term>.md` with `term:` | No existing file already defines it |
| Existing file as record | glossary glob + `term_field` / `ns` | Frontmatter already has the name |
| Alias, `uses:`, extra `ns` | `.ubiq/overlays/<name>.md` with `source:` | The source file must not be edited |

Overlay key is `source:` (not `on:` — YAML 1.1 loads `on:` as boolean `True`). Overlay files are scanned as docs so `ref_fields` on them participate.

`CONTEXT.md` is a **view**, not a second glossary. Keep Relationships and flagged ambiguities there; leave definitions in records. Dump a Language section with `ubiq terms --format context --ns repo` when a readable copy helps — then trim it; do not maintain two definitions.

**Done when:** every load-bearing name has exactly one defining record, and no owned file was patched for the linker.

## 4. Check, then CI

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
