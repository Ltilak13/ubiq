---
name: code-records-goal
status: proposed
criteria:
  AC4:
    assessment: unassessed
    support: []
    gap: Every diagnostic is implemented in Python. No rule is defined as record data.
  AC9:
    assessment: unassessed
    support: []
    gap: Feature interactions, change impact, and collisions between open pull requests are not derived from records.
    issues: [156]
---

# Goal: code as records

This goal defines outcomes and acceptance evidence. It does not claim that Ubiq
supports these outcomes today. It extends the [no-code specs goal](no-code-spec-goal.md)
from specs and tests to the code itself.

The [[plan:code-records-decisions]] plan tracks the open design questions.
The [[plan:feature-interactions]] plan tracks implementation of AC9.

## Objective

Everything is a schema or data. Types, contracts, functions, commands, and
scripts are schemas. Records (goals, features, plans, symbols, diagnostics,
decisions) and rules are data that a schema checks. Relationships are schema
annotations. The only thing that is neither is a function body, and it is held
to its schema and scenarios.

Every unit of code is defined by a record. Frontmatter holds what a unit is:
its name, signature, vocabulary term, rules, and the scenarios that test it.
A small, generic engine holds how it runs. One controlled vocabulary names the
records, the prose, the Gherkin steps, and the code symbols, one to one.

A record defines its code in one of three forms:

| Form | The record holds | The code |
| --- | --- | --- |
| Interpreted | The whole behavior as data, such as a check's pattern, scope, code, severity, and message | None per unit. A generic engine runs the record. |
| Generated | A contract, such as a schema or a command's arguments and exit codes | Generated from the record and kept current by `ubiq check` |
| Bound | The name, signature, term, and scenarios | A small hand-written function, checked against the record |

A symbol record declares its contract in frontmatter as JSON Schema, in an
OpenRPC-style shape: `params`, `result`, and `errors`, plus its `term`, `form`,
and `scenarios`. The Python signature is a generated or checked view of that
contract. The same shape covers CLI commands (options as params, exit codes as
errors) and skill scripts.

Records belong to registries, one per namespace. A record in a registry with an
ID is public and exported; anything else is private. `ubiq export schema`
writes a registry as one versioned JSON Schema bundle, and another repository
imports it by `$ref` to its IDs. Registries in other tools, such as Zod 4's
`z.registry()` and `z.toJSONSchema`, exchange through the same JSON Schema.

GitHub issues and comments are views too. An issue's body and its bot-written
comments (resolutions, decisions, closing notes) are generated from records;
discussion written by people stays on GitHub.

Work moves up the table over time. A behavior change should need only a record
edit wherever the engine supports it.

## Scope

In scope: Ubiq's own Python source, diagnostics, CLI commands, and tests, then
the pattern as something other repositories can adopt. Other languages, starting
with the shell scripts in skills, follow once the Python form is proven.

Out of scope: algorithm bodies written in frontmatter. A record names and
constrains a bound function; it does not contain a programming language.

Open decisions are tracked on the wayfinder map for this goal (#137). Accepted
decisions are records in [docs/decisions](../decisions/README.md).

## Acceptance evidence

The goal is achieved when:

1. AC4: At least one diagnostic's rule is defined entirely as record data, and a change to that record changes `ubiq check` behavior with no code edit, shown by a failing and then passing CI run.
2. AC9: Feature interactions are derived from shared symbols, configuration keys, diagnostic codes, and record kinds; every pull request reports the features it involves and breaks; and collisions between open pull requests are reported. Only semantic conflicts are declared.

## Exploration

On 2026-11-28 the goal was narrowed to AC4 and AC9. These two prove the pattern
on one rule and on change impact, which other repositories can use without
adopting the rest. The outcomes below are not acceptance criteria. They stay
open questions on the [wayfinder map](https://github.com/Ltilak13/ubiq/issues/137)
until AC4 is `met` and a decision record promotes one of them back to a
criterion. Their old labels (AC1–AC3 and AC5–AC8) are retired, not reused.

- Symbol records (#155): Every public symbol in Ubiq's source has a record that declares its contract as JSON Schema and names its form (interpreted, generated, or bound), and `ubiq check` reports a public symbol with no record, a record with no symbol, and a signature that differs from its contract.
- Code vocabulary (#68, #141): A controlled vocabulary maps one to one onto code symbols and Gherkin step phrases. Each code term names exactly one symbol, each public symbol name uses approved terms, and each step definition matches one step phrase.
- Gherkin behavior tests (#66, #67, #143): All behavior tests at public seams are Gherkin scenarios bound to records and run in CI with no agent.
- Generated code (#142): Generated code (types from schemas, CLI parsers from command records) is kept current by `ubiq check`, and a stale generated file is reported with its location.
- Rename sync (#134): Renaming a term in its record carries the rename to prose, step phrases, and code symbols through `ubiq sync`, and a dry run shows every edit first.
- Registries and schema export: Each namespace is a registry. Public records are exactly the registered ones, a link from outside a module to a private symbol fails `ubiq check`, and `ubiq export schema` writes a versioned JSON Schema bundle that another repository can import by `$ref`.
- Decision records (#152): Decisions, including wayfinder resolutions, are records, and the GitHub comments that announce them are generated from those records.
