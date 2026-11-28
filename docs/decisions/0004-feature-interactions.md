---
name: feature-interactions
question: 156
closes: false
status: accepted
decided: 2026-11-27
by: Ltilak13
options: [declare interactions on feature records, derive interactions from shared data]
outcome:
  - Feature interactions are derived, not declared. Two features interact when they share a symbol, a configuration key, a diagnostic code, or a record kind.
  - Symbol records name their owning feature; that field is the one new input.
  - ubiq impact --features maps a change to the features it involves, directly and through requires and interactions, with the scenarios and tests to run. CI reports it on every pull request.
  - Collisions between open pull requests (shared features, symbols, or new diagnostic codes) are reported from the open pull-request snapshot.
  - Breakage is mapped to features from breaking contract changes and failing scenarios.
  - Only semantic conflicts are declared, through a symmetric conflicts_with on feature records.
---

# Feature interactions and change impact

A relationship the records already imply is not written down again, so it
cannot go stale. Declaring interactions by hand would duplicate facts that
symbol ownership, `config` keys, and diagnostic codes already hold.

The collision check is motivated by this repository's own history: W008 was
claimed by #60 and #117, and E013 by #61 and #145, before either merged.
