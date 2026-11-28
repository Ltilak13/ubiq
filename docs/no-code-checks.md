# No-code checks

[Back to the guide](guide.md)

Run `ubiq check`, `cue vet`, `vale`, and `cucumber` in pre-commit and in CI. No
check needs an agent: each is a command that exits non-zero on failure. Agents can
help write records, but a human or a CI runner can reproduce every result.

This recipe serves the [no-code specs goal](goals/no-code-spec-goal.md). The
[sample repository](../examples/no-code-checks/README.md) applies it, and this
repository's CI runs the sample (`.github/workflows/no-code-checks.yml`).

## What each tool checks

| Tool | Checks | Reads |
| --- | --- | --- |
| `ubiq check` | Vocabulary references, schema bindings for frontmatter | `ubiq.yaml`, Markdown records |
| `cue vet` | Cross-field rules JSON Schema cannot state | `.cue` rules and YAML or JSON data |
| `vale` | Writing rules for prose | `.vale.ini` and a styles directory |
| `cucumber` | Behavior written as Gherkin scenarios | `.feature` files and step definitions |

Ubiq runs only the first. It does not wrap the others. Keep each tool's own
configuration in your repository and pin its version.

## Pinned versions

| Tool | Version | Install |
| --- | --- | --- |
| ubiq | a release tag such as `v0.13.0` | `pip install git+https://github.com/Ltilak13/ubiq@v0.13.0` |
| cue | 0.12.1 | release archive from `cue-lang/cue`, verified by checksum |
| vale | 3.9.1 | release archive from `errata-ai/vale`, verified by checksum |
| @cucumber/cucumber | 12.8.2 | `npm ci` from a committed `package-lock.json` |

When you upgrade a tool, change its version and checksum together. Compute the
checksum of the archive you downloaded with `sha256sum`.

## Pre-commit

Install [pre-commit](https://pre-commit.com), install `cue` and `vale` on your
`PATH`, and run `npm ci`. Then add this `.pre-commit-config.yaml`. Adjust the
paths to your layout.

```yaml
repos:
  - repo: https://github.com/Ltilak13/ubiq
    rev: v0.13.0
    hooks:
      - id: ubiq-check

  - repo: local
    hooks:
      - id: cue-vet
        name: cue vet (cross-field rules)
        entry: cue vet -d '#Limits' limits/limits.cue limits/limits.yaml
        language: system
        pass_filenames: false
        files: ^limits/
      - id: vale
        name: vale (writing rules)
        entry: vale --config .vale.ini specs
        language: system
        pass_filenames: false
        types: [markdown]
      - id: cucumber
        name: cucumber (scenarios)
        entry: npm run --silent cucumber
        language: system
        pass_filenames: false
        files: ^(features/|specs/|package)
```

Run `pre-commit install` once. Run `pre-commit run --all-files` to check the
whole repository. The `ubiq-check` hook comes from this repository's
`.pre-commit-hooks.yaml`. The other three use `language: system`, so they run the
tools you installed rather than fetching their own.

## GitHub Actions

Pre-commit can be skipped, so CI runs the same commands. This workflow needs no
secrets and no agent:

```yaml
name: checks
on:
  push:
    branches: [main]
  pull_request:

permissions:
  contents: read

jobs:
  checks:
    runs-on: ubuntu-latest
    timeout-minutes: 10
    env:
      CUE_VERSION: "0.12.1"
      CUE_SHA256: "40ef0a84594494c953945fb297842d3168c92170694928c9565cc0b581235ac5"
      VALE_VERSION: "3.9.1"
      VALE_SHA256: "fbc2eb47d0b8c50220ed1a2c5c611fbe0904ed567d638143d482016a18fd2db0"
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - uses: actions/setup-node@v4
        with:
          node-version: "22"
      - run: python -m pip install git+https://github.com/Ltilak13/ubiq@v0.13.0
      - name: Install cue and vale at pinned versions
        run: |
          mkdir -p "$RUNNER_TEMP/bin"
          curl --fail --silent --show-error --location \
            "https://github.com/cue-lang/cue/releases/download/v${CUE_VERSION}/cue_v${CUE_VERSION}_linux_amd64.tar.gz" \
            --output "$RUNNER_TEMP/cue.tgz"
          echo "$CUE_SHA256  $RUNNER_TEMP/cue.tgz" | sha256sum --check
          tar -xzf "$RUNNER_TEMP/cue.tgz" -C "$RUNNER_TEMP/bin" cue
          curl --fail --silent --show-error --location \
            "https://github.com/errata-ai/vale/releases/download/v${VALE_VERSION}/vale_${VALE_VERSION}_Linux_64-bit.tar.gz" \
            --output "$RUNNER_TEMP/vale.tgz"
          echo "$VALE_SHA256  $RUNNER_TEMP/vale.tgz" | sha256sum --check
          tar -xzf "$RUNNER_TEMP/vale.tgz" -C "$RUNNER_TEMP/bin" vale
          echo "$RUNNER_TEMP/bin" >> "$GITHUB_PATH"
      - run: npm ci
      - run: ubiq check
      - run: cue vet -d '#Limits' limits/limits.cue limits/limits.yaml
      - run: vale --config .vale.ini specs
      - run: npm run cucumber
```

Make the `checks` job a required status check for `main` so a skipped hook cannot
reach it.

## Limits

- The recipe covers Linux runners. Other platforms need a different release archive.
- `cue vet` reads YAML or JSON, not Markdown frontmatter. Keep values that need a
  CUE rule in a data file and link to it from the record, as the sample does with
  its limits. JSON Schema bindings in `ubiq.yaml` check frontmatter itself.
- `vale` and `cucumber` have no link to the criteria they test yet. Linking spec
  criteria to scenarios is tracked in the goal as AC4.
