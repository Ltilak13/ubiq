---
name: code-records-goal
status: proposed
criteria:
  AC1:
    assessment: unassessed
    support: []
    gap: Public symbols have no records, and nothing reports a symbol without one.
  AC2:
    assessment: unassessed
    support: []
    gap: No controlled vocabulary record type exists (#68), and no check reads code identifiers or step phrases against it.
    issues: [68]
  AC3:
    assessment: unassessed
    support: []
    gap: Behavior tests are Python tests. No Gherkin scenario binds to a record, and step names are not checked (#66, #67).
    issues: [66, 67]
  AC4:
    assessment: unassessed
    support: []
    gap: Every diagnostic is implemented in Python. No rule is defined as record data.
  AC5:
    assessment: unassessed
    support: []
    gap: No code is generated from schemas or command records.
  AC6:
    assessment: unassessed
    support: []
    gap: No command carries a term rename from its record to prose, steps, and code (#134).
    issues: [134]
  AC7:
    assessment: unassessed
    support: []
    gap: Records are not grouped into registries, and nothing exports or imports a registry as a JSON Schema bundle.
  AC8:
    assessment: unassessed
    support: []
    gap: Decisions and wayfinder resolutions live only as GitHub comments, not as records the comments mirror.
    issues: [152]
---

# Goal: code as records

This goal defines outcomes and acceptance evidence. It does not claim that Ubiq
supports these outcomes today. It extends the [no-code specs goal](no-code-spec-goal.md)
from specs and tests to the code itself.

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

Open decisions, such as the rule language for interpreted checks and how step
definitions bind to symbols, are tracked on the wayfinder map for this goal.

## Acceptance evidence

The goal is achieved when:

1. AC1: Every public symbol in Ubiq's source has a record that declares its contract as JSON Schema and names its form (interpreted, generated, or bound), and `ubiq check` reports a public symbol with no record, a record with no symbol, and a signature that differs from its contract.
2. AC2: A controlled vocabulary maps one to one onto code symbols and Gherkin step phrases. Each code term names exactly one symbol, each public symbol name uses approved terms, and each step definition matches one step phrase.
3. AC3: All behavior tests at public seams are Gherkin scenarios bound to records and run in CI with no agent.
4. AC4: At least one diagnostic's rule is defined entirely as record data, and a change to that record changes `ubiq check` behavior with no code edit, shown by a failing and then passing CI run.
5. AC5: Generated code (types from schemas, CLI parsers from command records) is kept current by `ubiq check`, and a stale generated file is reported with its location.
6. AC6: Renaming a term in its record carries the rename to prose, step phrases, and code symbols through `ubiq sync`, and a dry run shows every edit first.
7. AC7: Each namespace is a registry. Public records are exactly the registered ones, a link from outside a module to a private symbol fails `ubiq check`, and `ubiq export schema` writes a versioned JSON Schema bundle that another repository can import by `$ref`.
8. AC8: Decisions, including wayfinder resolutions, are records, and the GitHub comments that announce them are generated from those records.
