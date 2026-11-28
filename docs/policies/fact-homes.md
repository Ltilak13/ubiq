---
term: fact homes policy
ns: policy
---

# Fact homes policy

Each fact has one home. This policy says where a fact lives, when it gets its
own file, how derived copies stay current, and when a diagram belongs in a doc.
It applies the rule underneath the [no-code spec goal](../goals/no-code-spec-goal.md).

## Where a fact lives

| Fact | Home |
| --- | --- |
| Values and contracts | Frontmatter, checked by a schema binding |
| Behavior | Gherkin scenarios in the record |
| Rationale | Prose in the record or the document that owns it |
| Relationships between records | Reference fields such as `uses`, read by `ubiq graph` |
| Diagrams of those relationships | Generated from the records, never hand-drawn |

Prose may link to a fact. It does not restate it.

## Record or section

A fact gets its own Markdown file when it is a record. It is a record when any
of these is true:

- Other files link to it by name.
- It has fields that a schema checks.
- It has its own owner, status, or version.

Otherwise it is a section in the document that owns it. A section stays
linkable: Ubiq resolves links to GitHub heading slugs.

## Derived files

A derived file is any file a command writes from its sources, such as a
generated glossary view or a generated section between markers.

- Do not regenerate on save. Mid-edit output is noisy and unreviewed.
- Pre-commit runs each generator and fails when a derived file is stale.
- CI runs the same generators in check mode, so a stale file fails the pull request.
- Each generator writes every output it owns and gives the same output for the same input.
  This keeps all affected files current without a list of affected files.
- Mark each derived file or section as generated, and name the command that writes it.

## Diagrams

Use a diagram only for relationships or sequences that a table or list shows less clearly.

- When the nodes and arrows are records and their edges, generate the diagram.
  Until [#59](https://github.com/Ltilak13/ubiq/issues/59) adds generated Mermaid,
  such a diagram is unchecked and can go stale without warning.
- A hand-drawn diagram is acceptable only for an idea with no record counterpart,
  such as the define, connect, check flow in the [README](../../README.md).
- Give each Mermaid diagram `accTitle` and `accDescr`, so readers without the
  rendered image get the same account.

## What is checked today

`ubiq check` validates this record's frontmatter and its links. It does not
enforce the rules above. Schema bindings check frontmatter values. Generator
freshness and diagram agreement depend on each repository's pre-commit and CI
setup until Ubiq checks them directly.
