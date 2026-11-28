# ubiq

**Make your repo's rules checkable.**

“This word has one meaning.” “This record needs an owner.” “This skill uses
those instructions.” Your project depends on rules like these.

Ubiq checks the definitions, record fields, and links you register. When
something breaks, it reports where to fix it. Run it locally or on every pull
request, so people and agents can catch mistakes before they spread.

## How it works

1. **Define** a term or a rule for your records.
2. **Connect** it to the files it applies to.
3. **Check** changes with `ubiq check` locally or in CI.

| Your rule | What ubiq catches |
| --- | --- |
| A linked word has one definition. | Missing or ambiguous names. |
| Every task record needs an owner. | A missing field, when your schema requires it. |
| A skill uses shared instructions. | Broken include links, include cycles, or missing part inputs. |

You and your agents decide what the rules should be. Ubiq checks the structure
you declare; it cannot judge whether the prose is true or run your agents.
The checks need no AI model.

## Start with your agent

Use the [apply-ubiq skill](skills/apply-ubiq/SKILL.md) to add ubiq to a project.
It walks through the setup with you:

1. Find the words and definitions your project already uses.
2. Resolve unclear meanings with you and add the checks.
3. Run `ubiq check` and add it to your automated checks.

Ask your agent:

> Read the [apply-ubiq instructions](skills/apply-ubiq/SKILL.md) and follow them
> for this project. Keep existing source files intact. Ask me about unclear terms.

### Install the skills

The skills, each described by its own `description` field:

<!-- ubiq:readme:start -->
- **apply-ubiq**: [Wire ubiq into a repo — glossary, overlays, delimiters, catalogs, and CI — without editing files the repo already owns.](skills/apply-ubiq/SKILL.md#description)
- **maintain-ubiq**: [Keep a ubiq-wired repo healthy — fix failing references, link unlinked mentions (W002), review orphans, propose new glossary terms, and extract repeated skill text into shared parts.](skills/maintain-ubiq/SKILL.md#description)
- **upgrade-ubiq**: [Upgrades ubiq pins and installed skills, resolves compatibility changes, and assesses new capabilities against a repository's needs. Use for a requested upgrade, changed version pins, or mismatched CLI, CI, and skill revisions. Not for first-time adoption or routine reference repairs on a consistent version.](skills/upgrade-ubiq/SKILL.md#description)
<!-- ubiq:readme:end -->

Install `apply-ubiq`, `maintain-ubiq`, `upgrade-ubiq`, and the shared `references` directory together from the same
Ubiq revision. Copy or link their complete directories from `skills/` into one
skill root, keeping their names and subdirectories. For example:

```text
<skill-root>/
  apply-ubiq/
    SKILL.md
    references/
      schema-validation.md
  references/
    domain-review.md
    schema-workflow.md
    validate-changes.md
  maintain-ubiq/
    SKILL.md
  upgrade-ubiq/
    SKILL.md
    examples/
      upgrade-report.md
```

The skills link to the shared workflow in `references/`. Keep all four directories as siblings when
installing or upgrading. A standalone copy of `SKILL.md` is incomplete.
Installing the CLI alone does not install the skills.

You can also give your agent this checkout and ask it to follow the linked
instructions directly.

When the project changes, use [maintain-ubiq](skills/maintain-ubiq/SKILL.md) to
find new terms, repair references, and check the result.

Changing ubiq versions? Use [upgrade-ubiq](skills/upgrade-ubiq/SKILL.md) to update pins and skills,
check compatibility, and assess useful new features. Maintenance routes there when versions need attention.

Prefer to do it yourself? Follow the steps below.

## Quick start with the CLI

You need Python 3.10 or later and Git. Run these commands in a terminal.

### 1. Install ubiq

```bash
python -m pip install 'git+https://github.com/Ltilak13/ubiq.git@v0.14.0'
```

### 2. Open your project and start

Replace `/path/to/your/project` with your project's folder.

```bash
cd /path/to/your/project
ubiq init
ubiq check
```

`init` creates the configuration. It keeps your existing source files intact.
Review the files it finds. If you already have `ubiq.yaml`, skip `init`.

### 3. Give a word a home

Create `.ubiq/glossary/session.md` with this text:

```markdown
---
term: session
---

A period of play.
```

This is a definition: a name at the top, its meaning below.

### 4. Use the word in your docs

Add this line to your project's `README.md`:

```markdown
Start a [session](.ubiq/glossary/session.md).
```

Then check it:

```bash
ubiq check
```

A passing check reports `0 errors`. Your link has a home.

### 5. See it catch a mistake

Change the link's destination from `session.md` to `sesion.md`. Run `ubiq check`
again. It reports `E002` at the broken reference. Fix the spelling and check again.

That's the same check you can run on every pull request.

## Keep your docs connected

| I want to… | Run this |
| --- | --- |
| Check references | `ubiq check` |
| List defined words | `ubiq terms` |
| Find uses of a word | `ubiq refs session` |
| Find possible new words | `ubiq candidates` |
| See why a file is included | `ubiq explain` |
| See what a change affects | `ubiq impact --since main` |
| Summarize new and resolved findings | `ubiq compare --since main --markdown` |
| Measure typed metadata coverage | `ubiq coverage` |
| Select declared records with source evidence | `ubiq query --kind KIND --json` |

For automated checks, use the [GitHub Action](action.yml) or the
[pre-commit hook](.pre-commit-hooks.yaml). The
[setup skill](skills/apply-ubiq/SKILL.md) helps wire them into your project.

## Runnable example

The [inventory example](examples/inventory/README.md) connects ubiq requirements to Drizzle contracts, Zod validation, and Gherkin acceptance tests.

## Go further

Keep the first setup small. Add these when your project needs them:

- [Repository discovery](docs/guide.md#repository-groups-and-schemas): find existing files and definitions.
- [Schema validation](docs/schema-validation.md): check required fields and relationships between records.
- [Composable skills](docs/guide.md#composable-skills): share instructions, inspect dependencies, and find repeated text.
- [Typed queries](docs/query.md): record selection and evidence; relationship and dependency queries are unreleased.
- [Full guide](docs/guide.md): setup choices, reference rules, configuration, and all commands.
- [Contributing checks](docs/guide.md#pr-validation): test a change to ubiq itself.
- [Specification](docs/spec.md): exact rules and error codes.
