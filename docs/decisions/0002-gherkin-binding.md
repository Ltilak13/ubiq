---
name: gherkin-binding
question: 139
status: accepted
decided: 2026-11-27
by: research (AFK), recorded by the coordinator
options: [pytest-bdd, behave, Cucumber]
outcome:
  - Scenarios run with pytest-bdd inside pytest, so existing CI jobs and fixtures keep working.
  - Each step phrase is a literal string on one function.
  - ubiq check reads step definitions and feature files statically and reports duplicate phrases, unmatched steps, unapproved words, and unknown field names.
  - Record-owned step phrases are deferred until literal phrases prove too weak.
---

# Binding Gherkin steps to records and code

pytest-bdd keeps one test runner. It silently lets the last of two identical
phrases win, so Ubiq's duplicate check is required. A `conftest.py` hook adds
the scenario name to JUnit output for `ubiq verify` (#67).

Findings: [gherkin-step-binding.md](https://github.com/Ltilak13/ubiq/blob/claude/ecstatic-mendel-nkgz6t-research-gherkin-binding/docs/research/gherkin-step-binding.md).
