---
name: symbol-records
question: 140
status: accepted
decided: 2026-11-27
by: Ltilak13
options: [extract symbol facts from code, declare contracts in frontmatter]
outcome:
  - Everything is a schema or data.
  - A symbol record declares its contract in frontmatter as JSON Schema in an OpenRPC-style shape (params, result, errors), with term, form, and scenarios. The Python signature is a generated or checked view.
  - Each namespace is a registry. A symbol is public when its record is registered with an ID; anything else is private, and a link to it from outside its module fails ubiq check.
  - IDs take the form symbol:<qualified name>, exported as $id with the package version.
  - Python comes first; shell scripts follow (#151).
  - Each module has one sidecar record (for example src/ubiq/sync.md) whose frontmatter holds a symbols map keyed by name, with a prose section per symbol. A symbol that needs long prose may move to its own file.
  - The export version is the package version. Removing a registered symbol, adding a required param, narrowing a param, widening a result, or adding an error is a breaking change, reported by ubiq export schema --since <tag>.
  - Imports pin a version through the exported $id. upgrade-ubiq moves pins and runs the breaking-change report.
  - Records are required for modules in a coverage glob that widens module by module, starting with sync.py and plan.py.
---

# Symbol records

Declaring contracts keeps frontmatter the single source; extracting them from
code would make the record a view of the code instead. OpenRPC and MCP tool
definitions already describe functions with JSON Schema, and Zod 4 registries
exchange through JSON Schema, so the shape is shared beyond Ubiq.

A sidecar per module repeats the plan-steps pattern (`within: symbols`) and keeps
each contract next to the code it governs.
