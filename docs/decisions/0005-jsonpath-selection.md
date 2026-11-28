---
name: jsonpath-selection
question: 154
status: accepted
decided: 2026-11-27
by: research (AFK), recorded by the coordinator
options: [jsonpath-ng, python-jsonpath, JsonLogic, keep the selector form from decision 0001]
outcome:
  - Decision 0001 stands. None of the three expresses the joins behind E006 or E007 portably; all three handle a plain filter such as W003.
  - No runtime restriction is needed, and Ubiq keeps requires-python >=3.10.
  - If a JSONPath node selector for a rule's scope is wanted later, use python-jsonpath in RFC 9535 strict mode under an optional extra ubiq[jsonpath], with no runtime restriction. That amends decision 0001; it does not supersede it.
---

# JSONPath and JsonLogic for rule selection

Tested hands-on over a sample facts document:

- `python-jsonpath` 2.3.0 expresses the joins only through its non-standard
  `in` extension, which strict RFC 9535 mode rejects. The RFC-only nested filter
  returns wrong results because `@` rebinds inside nested filters.
- `jsonpath-ng` 1.16.0 does not parse `in`. Its Python 3.11 floor starts at
  1.9.1, so on 3.10 pip resolves 1.8.0, which lacks root-path comparison; an
  extra would install different features per Python version.
- JsonLogic (`panzi-json-logic` 1.0.1) rebinds data inside `filter`, works only
  if the engine pre-joins facts, and has had no release since 2021.

Unverified: the RFC 9535 text and jsonlogic.com were unreachable, and the
compliance test suite was not run.

Findings: [jsonpath-and-jsonlogic-for-rule-selection.md](https://github.com/Ltilak13/ubiq/blob/claude/ecstatic-mendel-nkgz6t-research-jsonpath/docs/research/jsonpath-and-jsonlogic-for-rule-selection.md).
