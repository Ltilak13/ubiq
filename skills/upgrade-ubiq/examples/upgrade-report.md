# Example upgrade report

Illustrative result for a skill repository upgrading from v0.5.0 to v0.6.0.

| Surface | Before | After | Evidence |
| --- | --- | --- | --- |
| Local CLI | v0.5.0 | v0.6.0 | Runtime version output |
| CI Action | v0.5.0 | v0.6.0 | Workflow pin inspection |
| Installed ubiq skills | v0.5.0 source | v0.6.0 source | Installer revision and resolved files |

Compatibility: existing configuration passes with the target validator.

| Capability | Decision | Reason |
| --- | --- | --- |
| Composition checks | Adopt | Shared skill parts have declared dependencies. Owner authorized configuration changes. |
| Bold candidates | Defer | Most bold text marks emphasis. |
| Typed-record schemas | Not applicable | This repository has no additional record-field constraints to enforce. |

Validation: target checker passes. An isolated broken-include example fails for the expected reason.
The local CI command passes. Remote CI has not run, and agent skill discovery requires a new session.

Result: local upgrade complete. Return to the caller's maintenance discovery step.
