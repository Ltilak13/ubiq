---
name: rule-language
question: 138
status: accepted
decided: 2026-11-27
by: research (AFK), recorded by the coordinator
options: [JSON Schema plus selectors, JSONPath, jq, CUE, Semgrep, regular expressions]
outcome:
  - Interpreted checks use JSON Schema 2020-12 plus a small selector form (unique-by, resolves-to, absent-in) over an engine-built facts document.
  - E008, E009, and the shape half of E010 are pure JSON Schema.
  - E002, E005, E011, W001, W002, W004, W006, W007, and E010 evidence hashes stay bound code.
  - W003 or E006 is the first rule defined as data.
---

# Rule language for interpreted checks

`jsonschema` is already a dependency and already runs E009, so the choice adds
no dependency. Plain JSON Schema cannot read other records, so a small selector
form supplies the joins. jq is a full language with a C extension, CUE needs a
Go binary, `jsonpath-ng` needs Python 3.11, and Semgrep is large and aimed at
code.

Open follow-up: compare `python-jsonpath` (RFC 9535) and JsonLogic for selection
and rule evaluation, since both are pure Python data forms.

Findings: [rule-language-for-interpreted-checks.md](https://github.com/Ltilak13/ubiq/blob/claude/ecstatic-mendel-nkgz6t-research-rule-language/docs/research/rule-language-for-interpreted-checks.md).
