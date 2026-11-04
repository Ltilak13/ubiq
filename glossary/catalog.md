---
term: catalog
ns: core
id: UB-8
---

A JSON or YAML inventory of [[term]]s that is not itself a glossary. Each entry
must resolve to a [[glossary record]] (E006). Optional `cover` globs require
every matching record to appear in the inventory (E007). Use this for files
like `plugin.json` that list a promoted set — do not glob them as records, or
they duplicate the real defining files.
