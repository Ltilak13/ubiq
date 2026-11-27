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
---

# Goal: code as records

This goal defines outcomes and acceptance evidence. It does not claim that Ubiq
supports these outcomes today. It extends the [no-code specs goal](no-code-spec-goal.md)
from specs and tests to the code itself.

## Objective

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

Work moves up the table over time. A behavior change should need only a record
edit wherever the engine supports it.

## Scope

In scope: Ubiq's own source, diagnostics, CLI commands, and tests, then the
pattern as something other repositories can adopt.

Out of scope: algorithm bodies written in frontmatter. A record names and
constrains a bound function; it does not contain a programming language.

Open decisions, such as the rule language for interpreted checks and how step
definitions bind to symbols, are tracked on the wayfinder map for this goal.

## Acceptance evidence

The goal is achieved when:

1. AC1: Every public symbol in Ubiq's source has a record that names its form (interpreted, generated, or bound), and `ubiq check` reports a public symbol with no record and a record with no symbol.
2. AC2: A controlled vocabulary maps one to one onto code symbols and Gherkin step phrases. Each code term names exactly one symbol, each public symbol name uses approved terms, and each step definition matches one step phrase.
3. AC3: All behavior tests at public seams are Gherkin scenarios bound to records and run in CI with no agent.
4. AC4: At least one diagnostic's rule is defined entirely as record data, and a change to that record changes `ubiq check` behavior with no code edit, shown by a failing and then passing CI run.
5. AC5: Generated code (types from schemas, CLI parsers from command records) is kept current by `ubiq check`, and a stale generated file is reported with its location.
6. AC6: Renaming a term in its record carries the rename to prose, step phrases, and code symbols through `ubiq sync`, and a dry run shows every edit first.
