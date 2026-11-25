---
name: upgrade-ubiq
description: >-
  Upgrades ubiq pins and installed skills, resolves compatibility changes, and
  assesses new capabilities against a repository's needs. Use for a requested
  upgrade, changed version pins, or mismatched CLI, CI, and skill revisions.
  Not for first-time adoption or routine reference repairs on a consistent version.
---

# Upgrade ubiq

Inputs: target repository, requested version when supplied, observed revisions, and authorized edit scope.
Use the caller's checkout. A CLI version pin does not update installed agent skills.
Example result: [upgrade report](examples/upgrade-report.md).

## 1. Establish the upgrade

1. Inspect the repository's ubiq configuration and installation instructions.
2. Locate package requirements, lockfiles, pre-commit revisions, CI Action pins, and local executable sources.
3. Run `ubiq --version`, or `python3 -m ubiq.cli --version` when the command is unavailable.
4. Inspect installed ubiq skills separately. Resolve symlink targets and identify their source revisions or local modifications.
5. Record each surface's configured revision, observed revision, and evidence. Use commit identities to resolve SHA pins.
6. Use history to identify the previous version when a pin already changed. Mark an unavailable baseline as unknown.
7. Use the requested target. Otherwise resolve the stable release from the configured upstream's release metadata.
8. Distinguish a routine maintenance request from authorization to upgrade. Ask for upgrade scope only when it is missing.
9. Run the existing checker before changes when available. Preserve its diagnostics as the baseline.

A newer release alone does not authorize changing pins. Read-only assessment can continue while authorization is missing.
Keep existing package sources and pin styles. Check repository identity before selecting releases or installing packages with similar names.

Done: the baseline, target, revision mismatches, and edit scope have evidence or explicit gaps.

## 2. Review compatibility and new capabilities

1. Read upstream release notes and migration instructions across the version interval.
2. Inspect target-version documentation or source when release notes omit a relevant behavior.
3. When the old revision is unknown, assess the current configuration against target documentation. Report the comparison limit.
4. Map required compatibility changes to the repository's actual files and configured guarantees.
5. Identify new capabilities relevant to those files, including features that need configuration before diagnostics appear.
6. Run relevant read-only analysis supported by the target version in an isolated environment when necessary.
7. Give each relevant capability a decision: adopt, defer, or not applicable. Record repository evidence and a reason.

For example, assess composition checks in a skill repository even when `edges` is absent.
Consider bold vocabulary discovery only when bold text names concepts. Check schema needs against actual record constraints.
New release features do not automatically become project requirements. Apply optional features only within the authorized scope.

Done: the migration list is complete, and each relevant new capability has an evidence-backed decision.

## 3. Apply the authorized upgrade

1. Preserve the original pins and affected configuration for recovery. Keep unrelated work intact.
2. Update each in-scope execution surface to the selected release or its equivalent commit.
3. Use the repository's package manager to update affected lockfiles and the intended local environment.
4. Refresh installed ubiq skills through their existing installer or links. Preserve local customizations and unrelated skills.
5. Check skill sources against the target release. Record any deliberate compatible revision difference with supporting evidence.
6. Check refreshed skill files and links directly. Report when skill discovery needs a new agent session.
7. Apply required compatibility fixes. Preserve documented guarantees instead of weakening checks to obtain a pass.
8. Enable approved optional capabilities and check their configuration against the target version.
9. For schema or record migrations, follow the [schema change workflow](../references/schema-workflow.md).

If a shared installation affects other repositories, check that the existing authorization covers them before changing it.
When a target release lacks a required skill, report that gap. Keep the existing skill until you identify a compatible source.
If installation or migration fails, stop dependent edits. Restore only this upgrade's changes when recovery is safe.
For partial work, record completed steps, remaining mismatches, and the recovery action. Reinspect that state before resuming.
Commits, pushes, and releases require separate authorization.

Done: each authorized surface matches the target, or its blocker has a recovery action.

## 4. Check and return

1. Check the local runtime version and every configured execution revision against the selected target.
2. Run `ubiq check` with the target validator. Compare diagnostics with the baseline.
3. Use /validate-change when installed. Supply changed paths, acceptance criteria, and existing check evidence.
4. Otherwise run the repository's documented checks directly, including affected schema and migration tests.
5. Exercise the local commands used by hooks and CI where available. Distinguish configuration inspection from remote execution.
6. Check that adopted capabilities are active and detect their intended invalid cases. Report checks that could not run.
7. Report old and new revisions, compatibility fixes, capability decisions, validation evidence, and remaining gaps.
8. If maintenance called this skill, return the result to that invocation. Resume its discovery step only after validation passes.

On a repeated failure, stop after three fix attempts and report the failing check with the remaining recovery steps.
Keep the retry count across continuation. Do not restart the upgrade during the same maintenance pass.

Done: the repository passes on the target version. Each revision matches the target or comes with compatibility evidence.
Each relevant capability has an adoption result or an explicit deferral.
Use an incomplete result when required validation, installation, or migration remains blocked.
