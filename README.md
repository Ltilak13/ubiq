# ubiq

**Make your repo's rules checkable.**

“This word has one meaning.” “This record needs an owner.” “This skill uses
those instructions.” Your project depends on rules like these.

Ubiq checks the definitions, record fields, and links you register. When
something breaks, it reports where to fix it. Run it locally or on every pull
request, so people and agents can catch mistakes before they spread.

## How it works

Write down a rule. Connect it to your files. Check it when things change.

```mermaid
flowchart LR
    accTitle: Define, connect, check
    accDescr: Define vocabulary or record rules, connect your files, then check changes with ubiq.
    A["1. Define"] --> B["2. Connect"] --> C["3. Check"]
```

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

These skills live in this repository. Give your agent this checkout or the linked
instructions. Installing the CLI alone does not install the skills.

When the project changes, use [maintain-ubiq](skills/maintain-ubiq/SKILL.md) to
find new terms, repair references, and check the result.

Changing ubiq versions? Use [upgrade-ubiq](skills/upgrade-ubiq/SKILL.md) to update pins and skills,
check compatibility, and assess useful new features. Maintenance routes there when versions need attention.

Prefer to do it yourself? Follow the steps below.

## Quick start with the CLI

You need Python 3.10 or later and Git. Run these commands in a terminal.

### 1. Install ubiq

```bash
python -m pip install 'git+https://github.com/Ltilak13/ubiq.git@v0.7.0'
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

For automated checks, use the [GitHub Action](action.yml) or the
[pre-commit hook](.pre-commit-hooks.yaml). The
[setup skill](skills/apply-ubiq/SKILL.md) helps wire them into your project.

## Go further

Keep the first setup small. Add these when your project needs them:

- [Repository discovery](docs/guide.md#repository-groups-and-schemas): find existing files and definitions.
- [Schema validation](docs/schema-validation.md): check required fields and relationships between records.
- [Composable skills](docs/guide.md#composable-skills): share instructions, inspect dependencies, and find repeated text.
- [Full guide](docs/guide.md): setup choices, reference rules, configuration, and all commands.
- [Contributing checks](docs/guide.md#pr-validation): test a change to ubiq itself.
- [Specification](docs/spec.md): exact rules and error codes.
