---
term: registry
ns: core
id: UB-9
aliases: [registries]
---

The set of records in one namespace, together with the schema that checks them.
A record registered with an ID is public: other records and other repositories
may link to it, and `ubiq export schema` includes it in the registry's versioned
JSON Schema bundle. A record without an ID is private to where it is defined.
