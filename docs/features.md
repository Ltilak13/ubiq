# Features and adoption order

Ubiq describes its own features the way it asks you to describe yours: one record
per feature in [`src/ubiq/features/`](../src/ubiq/features/), checked by
[the feature schema](../.ubiq/schemas/feature.json). Each record names

- `requires`: the features it builds on. A name that is no feature fails `ubiq check` (E006).
- `codes`: the diagnostic codes the feature owns. A test keeps them equal to the
  [diagnostics list](spec.md#diagnostics), with each code owned once.
- `config`: the `ubiq.yaml` keys that show a repository uses the feature, such as `edges.external`.
- `docs` and `summary`: where it is specified, and one line for the plan.
- `status`: `shipped` (the default when absent) or `planned`. See [Planned features](#planned-features).
- `issue`, `priority`, `pr`: optional [tracking fields](spec.md#tracking-fields-and-x-ubiq-ref).

The records: [catalogs](../src/ubiq/features/catalogs.md), [change-review](../src/ubiq/features/change-review.md), [composition-edges](../src/ubiq/features/composition-edges.md), [criterion-scenarios](../src/ubiq/features/criterion-scenarios.md), [cross-repository-composition](../src/ubiq/features/cross-repository-composition.md), [feature-planning](../src/ubiq/features/feature-planning.md), [field-links](../src/ubiq/features/field-links.md), [field-refs](../src/ubiq/features/field-refs.md), [frontmatter-schemas](../src/ubiq/features/frontmatter-schemas.md), [github-sync](../src/ubiq/features/github-sync.md), [glossary](../src/ubiq/features/glossary.md), [graph-blocks](../src/ubiq/features/graph-blocks.md), [id-references](../src/ubiq/features/id-references.md), [markdown-references](../src/ubiq/features/markdown-references.md), [no-code-checks](../src/ubiq/features/no-code-checks.md), [overlap](../src/ubiq/features/overlap.md), [overlays](../src/ubiq/features/overlays.md), [plan-records](../src/ubiq/features/plan-records.md), [query](../src/ubiq/features/query.md), [record-graphs](../src/ubiq/features/record-graphs.md), [restated-values](../src/ubiq/features/restated-values.md), [symbol-records](../src/ubiq/features/symbol-records.md), [tracking-fields](../src/ubiq/features/tracking-fields.md), [typed-coverage](../src/ubiq/features/typed-coverage.md).

## `ubiq plan`

```bash
ubiq plan                  # every feature in adoption order
ubiq plan --next           # features this repository has not adopted whose requirements it meets
ubiq plan --next --used query   # also count a feature that `ubiq.yaml` cannot show
ubiq plan --json
ubiq plan --features DIR   # plan your own feature records instead of ubiq's
```

The order puts a feature after everything it requires; features that are ready
together list alphabetically. `ubiq plan` exits 1 and names the loop when
features require each other, or the name when a requirement is no feature.

`--next` reads `ubiq.yaml` in `--root`. A feature counts as used when one of its
`config` keys is set, when `--used` names it, when it is the glossary and the
repository has a glossary, or when a used feature requires it. Features with no
`config` key (such as `query`) are used only when named with `--used`.

## Planned features

A feature with `status: planned` is work in flight: its record exists so other
records can `requires` it and so the work has an issue, but nobody can adopt it yet.

- `ubiq plan` and `ubiq plan --next` leave planned features out of the adoption
  order and number only shipped features. `ubiq plan --json` lists the planned
  names under `planned`. `--used` may not name a planned feature.
- A planned feature may require planned or shipped features. A shipped feature
  that requires a planned one fails `ubiq plan`, because it could not be adopted.
  Cycles are still found across both statuses.
- `codes` stays required and keeps its pattern. A planned feature declares the
  codes it will own, and they need not be in the [diagnostics list](spec.md#diagnostics)
  yet. A test checks that the shipped features' codes match the list, so they must
  be documented when the record becomes `shipped`. No code may be owned twice.
- `docs` must still be a `docs/` path; point it at the nearest existing section
  until the feature's own section lands.
- With a `kind: feature` entry under `sync.records`, [`ubiq sync github`](github-sync.md#feature-records)
  gives a planned feature without `issue` an issue, and closes the issue of a
  shipped feature. Setting `status: shipped` is the whole release step.
