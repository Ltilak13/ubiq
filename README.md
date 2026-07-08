# ubiq

**A linker for prose.** Every domain term used in your docs must resolve to exactly one
defining record — or the build fails. Unresolved-import semantics for markdown.

Docs rot because nothing depends on them. ubiq makes your vocabulary load-bearing: terms are
defined once in glossary records, referenced everywhere else, and checked in CI like any other
build artifact. Think `eslint` for your ubiquitous language.

ubiq is a **linter, not a migrator**. It never moves, merges, or rewrites your docs. It reports
duplicate definitions, unresolved references, and ambiguous terms — you (or your agent) do the
consolidating once; ubiq keeps it clean forever after.

## Quick start

```bash
pip install -e .
ubiq check          # lint the current repo (reads ubiq.yaml)
ubiq terms          # list the glossary
ubiq refs "term"    # every place a term is used — traceability is just search
ubiq check --json   # machine-readable, for CI and agents
```

Exit code 0 = vocabulary resolves. Exit code 1 = broken — gate your merges on it.

## How it works

1. **Glossary records** — one markdown file per term, YAML frontmatter (`term`, `ns`,
   `aliases`, optional `id`), definition in the body. See `glossary/`.
2. **References** — write `[[term]]` or `[[ns:term]]` in any doc. Configured `id_patterns`
   (e.g. requirement IDs like `R3`) must also resolve. Plain mentions of defined terms are
   indexed too, so `ubiq refs` finds everything.
3. **Checks** — `E001` duplicate definition, `E002` unresolved reference, `E003` ambiguous
   reference (needs a namespace qualifier), `E004` unresolved ID, `W001` orphan term
   (defined, never used).

Full spec: `docs/spec.md`. ubiq lints its own docs — this repo passes `ubiq check`.

## Roadmap (staged; a stage must earn its keep before the next starts)

- **Stage 1 — deterministic linker** (this repo). Success metric: runs clean on its own docs
  and produces useful findings on a real docs-heavy repo.
- **Stage 2 — code walk.** AST pass verifying code identifiers are built from glossary terms;
  ref map (record ↔ symbol) emitted as a build artifact.
- **Stage 3 — LLM judge.** Semantic check per diff: flags term *misuse*, not just undefined
  terms. Advisory first, gating when precision earns it.
- **Stage 4 — adapters & editor.** Confluence/Notion pull-and-lint adapters; LSP hover =
  jump from any term to its defining record.
