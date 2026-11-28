# Features and adoption order

Ubiq describes its own features the way it asks you to describe yours: one record
per feature in [`src/ubiq/features/`](../src/ubiq/features/), checked by
[the feature schema](../.ubiq/schemas/feature.json). Each record names

- `requires`: the features it builds on. A name that is no feature fails `ubiq check` (E006).
- `codes`: the diagnostic codes the feature owns. A test keeps them equal to the
  [diagnostics list](spec.md#diagnostics), with each code owned once.
- `config`: the `ubiq.yaml` keys that show a repository uses the feature, such as `edges.external`.
- `docs` and `summary`: where it is specified, and one line for the plan.

The records: [catalogs](../src/ubiq/features/catalogs.md), [change-review](../src/ubiq/features/change-review.md), [composition-edges](../src/ubiq/features/composition-edges.md), [cross-repository-composition](../src/ubiq/features/cross-repository-composition.md), [field-refs](../src/ubiq/features/field-refs.md), [frontmatter-schemas](../src/ubiq/features/frontmatter-schemas.md), [glossary](../src/ubiq/features/glossary.md), [id-references](../src/ubiq/features/id-references.md), [markdown-references](../src/ubiq/features/markdown-references.md), [overlays](../src/ubiq/features/overlays.md), [query](../src/ubiq/features/query.md), [record-graphs](../src/ubiq/features/record-graphs.md), [typed-coverage](../src/ubiq/features/typed-coverage.md).

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
