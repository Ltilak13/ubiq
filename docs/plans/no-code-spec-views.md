---
name: no-code-spec-views
status: proposed
issue: 64
trunk: main
steps:
  check-authored-diagrams:
    issue: 128
    requires: []
  generate-record-diagrams:
    issue: 129
    requires: []
  generate-schema-diagrams:
    issue: 130
    requires: []
  diagnostic-table:
    issue: 144
    requires: []
  runtime-support-matrix:
    issue: 153
    requires: []
    pr: 164
---

# Checked views of repository facts

The [[goal:no-code-spec-goal]] calls for each fact to have one home.
The diagram work checks or generates Mermaid from record and schema data.
The diagnostic table and runtime support matrix apply the same rule to
Ubiq's specification, release metadata, and CI.
