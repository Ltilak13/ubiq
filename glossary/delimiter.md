---
term: delimiter
ns: core
id: UB-6
---

A configured prefix or wrapper that marks an explicit [[reference]] besides
`[[term]]`. The usual form is a prefix (`/` → `/term`) so slash-commands are
load-bearing. Delimiters match inside inline code; fenced blocks are still
ignored. Tokens listed in `except` are not references. `only_known: true`
matches a token only when it is already a glossary name — quieter, and typos
of unknown names are invisible. The default is strict: every `/slug` is an
explicit ref.
