---
term: validate repository changes
---

# Validate repository changes

1. After changes to configuration, records, overlays, schemas, or migrations,
   use /validate-change if it is installed. Read that skill before selecting
   checks. Supply the repository, changed paths, acceptance criteria, and
   current check evidence.
2. When the skill is unavailable, inspect the repository instructions and run
   the relevant checks directly.
3. For schema or migration changes, use the [schema change workflow](schema-workflow.md)
   to test affected records and invalid cases.
4. Repair failures within the authorized scope before reporting success.
   Report unavailable checks as validation gaps. Obtain separate authorization
   for commits or publication.
