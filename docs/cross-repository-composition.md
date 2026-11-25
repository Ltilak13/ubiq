# Cross-repository composition

A repository can refer to skills and shared parts defined in another checkout.
Declare each dependency in `ubiq.yaml`:

```yaml
edges:
  external:
    - name: shared
      path: ../shared-skills
      revision: "0123456789abcdef0123456789abcdef01234567"
      required: true
```

Replace the example revision with the dependency's full commit SHA. Ubiq reads
existing checkouts. It does not clone, fetch, install, or modify them.

`name` is a stable dependency namespace. Names start with a lowercase letter
and contain lowercase letters, digits, or hyphens. Names are exact: `shared-tools`
and `shared--tools` identify different dependencies. Duplicate names fail.
`path` is relative to the repository that declares it, or an absolute path.
Moving a checkout does not change its namespace.

Structured declarations require an explicit boolean `required`. A missing
required checkout fails. A missing optional checkout is allowed, but a present
dependency with invalid configuration or a mismatched revision fails. A reference
to a missing optional record still fails resolution.

`revision` is optional. When present, it must equal the checkout's HEAD. Tracked
and untracked ubiq inputs must be clean, including Git-ignored files that ubiq
reads, linked documents, overlays, catalogs, schemas, and installed files.
Pinned inputs cannot resolve outside the dependency checkout through symlinks
or configured paths.

Existing string declarations keep their previous installed-link behavior and
warnings. They do not acquire a revision pin or recursive composition semantics.

## References and contracts

Use qualified names in configured reference fields and explicit prose references:

```markdown
---
name: release
uses: [shared/skill:publish-pr]
---

Run [[shared/skill:publish-pr]].
```

The upstream record's aliases also work. Unqualified names keep local resolution;
an upstream addition does not replace a local record. External records do not
join the local typed-metadata coverage inventory.

Installed Markdown links can include upstream parts. Each part's repository
defines its part namespaces, input field, and invocation restriction field.
For example, a part with `inputs: {mode: [new, existing]}` requires a value after
the include link:

```markdown
Follow [checkout](../checkout/SKILL.md#prepare) in `new` mode.
```

Missing or invalid values and malformed contracts produce E012. Fragment and
installed-layout checks still apply. Invocation restrictions produce W003 at
the calling repository's configured invocation severity.

## Traversal and review

Each named dependency loads its own declarations relative to its own root.
For a dependency named `shared` that declares `base`, use
`shared/base/skill:publish-pr`. Graph and reference output identify external
records and declaration paths through dependency namespaces. Diamond paths
reuse record identity. Repository and invocation cycles terminate; include
cycles fail with E011.

```sh
ubiq check
ubiq refs shared/skill:publish-pr --json
ubiq graph shared/base/skill:publish-pr --callers --json
ubiq impact --since main --json
ubiq compare --since main --json
```

Impact reports seed affected local callers when named dependencies are added or
removed, or their revision pins change. A `dependency` change includes the dependency's records;
it does not claim that every upstream file changed. Caller paths can pass through
external records, including paths that existed only before an upgrade.

Historical review extracts exact dependency revisions from locally available
Git objects into temporary snapshots. It does not substitute the current
checkout for a missing historical commit. Missing commits or missing historical
pins make impact incomplete and comparison unavailable. Legacy string
dependencies retain their current-checkout comparison behavior.

Coverage measures local assets separately. Dependency availability and external
typed inventories do not change its selected local files.

## Adoption and recovery

Adopt structured declarations only after a release containing this feature is
available. Local and CI setup must provide the same declared commit and clean
ubiq inputs before running checks. CI checkout or installation belongs to the
consumer's setup, outside ubiq's dependency loader.

Replace a local stand-in and its references together. To recover, restore the
previous dependency configuration and affected references together. Keep the
previous dependency commit available locally when reviewing the rollback.
