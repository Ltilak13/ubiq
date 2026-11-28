---
term: contract
ns: core
id: UB-10
aliases: [contracts]
---

The schema part of a symbol record: `params`, `result`, and `errors`, each as
JSON Schema. Code that implements the symbol is checked against its contract or
generated from it. A CLI command and a script have contracts too: options are
params and exit codes are errors.
