# Ubiq feature adoption

Which shipped ubiq features this repository uses on itself, and why it does not use the rest.
Downstream repositories adopt a feature after ubiq does. Re-run `ubiq plan --next` and
`ubiq plan --next --used <names>` after each release and update this table in the same pull request.

## 2026-11-28

Assessed against every record in [`src/ubiq/features/`](../../src/ubiq/features/) at `main` 37c2094.
The commands that gave the evidence are `ubiq plan --next`, `ubiq check`, `ubiq overlap`,
`ubiq candidates`, `ubiq compare --since origin/main`, and `ubiq coverage`.

| Feature | Used | Evidence or reason not used |
| --- | --- | --- |
| glossary | yes | Nine glossary rules in `ubiq.yaml`. |
| catalogs | yes | `.ubiq/catalogs/skills.json` covers `skills/**/SKILL.md`. |
| field-refs | yes | `ref_fields: [uses, requires, routes]`. |
| frontmatter-schemas | yes | Fourteen `schemas` bindings, including goals, features, plans, decisions, overlays. |
| feature-planning | yes | `ubiq plan --next` is the adoption check this table answers. |
| github-sync | yes | `sync.repo` and `.github/workflows/github-sync.yml`. |
| criterion-scenarios | yes | `docs/goals/composable-knowledge-goal.feature` accepts the criteria that set `scenario: true`. |
| decision-records | yes | Five records in `docs/decisions/`. |
| id-references | yes, new | `id_patterns: ["UB-[0-9]+"]`. Ten glossary records carry `id: UB-n` and `docs/spec.md` cites them; a mistyped id is now E004. |
| markdown-references | yes, extended | W007 is an error, `/command` delimiters resolve (`only_known`), E015 and E013 are in use (below). Not used: W002 `unlinked_mentions` (see below). |
| composition-edges | yes, extended | `edges.install` already; this pass adds `edges.route`, `edges.drift` (W005) for skills, and a declared `routes` edge from `apply-ubiq` to `maintain-ubiq`. |
| change-review | no | `ubiq compare --since origin/main` runs and reports `0 new, 0 resolved, 0 unchanged`, but using it means a CI step that posts the comparison on pull requests. That is a workflow change; left as a follow-up. |
| cross-repository-composition | no, not applicable | ubiq reuses no other repository's records: no `edges.external`, no named dependency. The pinned upstream repositories under `tests/fixtures/` are test inputs. |
| field-links | yes, new | The README's skills list links each skill's `description` field (E013, `references.value.severity: error`). Other prose that restates a value from another record was searched for by hand; the only candidates were generated lists (the decisions index and the support table), which are already single-sourced. |
| graph-blocks | yes, new | `docs/guide.md` holds a generated `ubiq:graph` block for `apply-ubiq`; W009 (always a warning) reports it when the records change. The example in `docs/spec.md` is inside a fence and is not checked. `ubiq plan --next` still lists the feature because it has no configuration key. |
| no-code-checks | no | It is a recipe for repositories without an agent (CUE, Vale, Cucumber in pre-commit and CI). ubiq already checks itself with `ubiq check`, JSON Schemas, scenario tags (E016), and pytest, and runs the recipe on `examples/no-code-checks` in its own CI. Vale and CUE rules for this repository's prose would be a style decision for the owner. |
| overlap | on demand | `ubiq overlap` reports one cluster: `checkable-contracts-evidence-goal` and `safe-adoption-evolution-goal` share a sentence. Goal records are being edited by open pull requests (#194 to #196), so it is not changed here. |
| overlays | yes | `.ubiq/overlays/` for the three skills; they now also declare `routes` and `readme`. |
| record-graphs | yes | `.ubiq/knowledge/goal-governance.yaml` with `goal-governance.json`; `ubiq query --kind goal` reads it. |
| query | on demand | `ubiq query --kind goal` and `--all-repositories`. No configuration key exists to show it. |
| support-matrix | yes | `.ubiq/support/*.md`, `requires-python`, the CI matrix, and the table in `docs/guide.md` (E017). |
| tracking-fields | yes | `issue`, `priority`, `pr`, `part_of` on features, goals, and plans. |
| plan-records | yes | Five records in `docs/plans/`. |
| symbol-records | partly | `symbols.coverage` lists `src/ubiq/sync.py` and `src/ubiq/plan.py`. The other modules have no symbol records. Each record is hand-written, and `sync.py` is being edited by #195 and #196, so widening it waits. |
| typed-coverage | yes | `coverage` in `ubiq.yaml`, and the `coverage` CI job with `--since`. |
| restated-values (W008) | yes, new | `restated_values: [description, question, decided, by, docs]`. Not yet listed: `summary` (the bodies of `decision-records`, `field-links`, and `restated-values` repeat it), `status` (goal and feature bodies), and `issue` (two plan bodies). Fixing those means editing records that #194 to #196 also edit. The record still says `planned` on `main`; #196 marks it shipped. |

### Capabilities that are not features

| Capability | Used | Reason |
| --- | --- | --- |
| README memberships (E015) | yes, new | The three skills declare `readme: root` in their overlays and the README lists them in a managed section. Not used: `docs/decisions/README.md` (its list is generated with wiki-links, so field links need a generator option), and `docs/goals/README.md` and the record list in `docs/features.md` (open pull requests edit them, and goal records have no display field). |
| Unlinked mentions (W002) | no | `unlinked_mentions: warn` reports 384 warnings, mostly the word "record" in `src/ubiq/sync.md` and the specs. It is off by default and a section-by-section linking pass is churn with no check behind it. |
| `ubiq candidates` | on demand | Four candidates (`requires-python`, `jsonpath-ng`, `python-jsonpath`, `to-spec`): package, tool, and file names, not vocabulary. |
| `ubiq coverage` | yes | 102 of 102 typed files, in CI. |

### Friction the adoption exposed

- **Per-record cost of E015.** A membership is one `readme` value per record, so a record whose frontmatter ubiq does not own, or a schema that forbids extra fields (goals), needs an overlay or a schema change. Twenty-five feature records would need twenty-five overlays for one list. A `readme` default on a glossary rule, with record and overlay values winning, would cut that to one line. It is a new configuration key and precedence rule, so it is proposed, not added.
- **Generated lists and field links.** `ubiq decisions --write` emits `[[decision:x]]`, so the decisions README cannot be a managed section. An opt-in setting for field-link output would let it be one.
- **`ubiq plan --next` cannot see use without a key.** `graph-blocks`, `record-graphs`, `query`, and `overlap` are in use or run on demand but have no `ubiq.yaml` key, so the plan keeps listing them. Only `--used` on the command line records it. A `features.used` list in `ubiq.yaml` would let the repository say so once.
- **W007 does not gate vendored text.** Raising it to an error was checked against the `ai` maintenance branch: no W007 appeared, because links in text that resolves outside the repository are never in scope. The pre-existing guarantee now has a test.
- **Drift needs the skill to name its callees.** With `edges.drift` on, a declared `uses` edge fails W005 when the skill's own text never names the target, even if the shared part it links does. Four edits to two skills named `/domain-modeling` and `/validate-change`; downstream skills copied from upstream will need the same or an overlay `uses` that matches their text.
