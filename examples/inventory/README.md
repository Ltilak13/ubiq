# Inventory contracts and behavior

This example connects written requirements to a small inventory service. Drizzle defines the database, Zod validates commands, and Gherkin scenarios exercise the service. Ubiq checks the declared relationships and source evidence.

## Run it

Use Node.js 24 and Python 3.10 or later. From the repository root:

```sh
python3 -m venv .venv
. .venv/bin/activate
python3 -m pip install -e .
cd examples/inventory
npm ci
npm run check
```

The check runs type checking, lint, ubiq validation, unit tests, and all acceptance scenarios. Tests use temporary SQLite databases. No server, credentials, model provider, or network access is needed after installation.

`npm run generate` creates migrations from the Drizzle schema. With unchanged inputs, it must report no schema changes. Migrations and the lockfile are committed. Zod validators derive their fields from Drizzle through `drizzle-zod`, with command-specific restrictions in `src/contracts.ts`.

## Contracts

`openInventory()` provides `reserve(input)` and `release(input)`. Both return `{ ok: true }` or `{ ok: false, error }`. Validation errors use `invalid_input`. Business errors are `unknown_item`, `unknown_reservation`, `duplicate_reservation`, and `insufficient_stock`.

Identifiers are trimmed before use. Reservation IDs remain unique after release. Release is idempotent: a second release succeeds without restoring stock again. Both operations run in immediate SQLite transactions. Unexpected database errors, including lock contention, throw and roll back. This example has no retry policy.

The database enforces integer quantity bounds, valid statuses, unique identifiers, and item references. It does not enforce every business transition against arbitrary SQL clients. Call the service for reservation and release behavior.

## Follow a requirement

The controlled requirements are in `requirements/`. They use ASD-STE-inspired clarity rules and a local vocabulary. No checker claims certified STE compliance.

```sh
python3 -m ubiq.cli query --root . --id REQ-RELEASE --json
python3 -m ubiq.cli query --root . --id REQ-RELEASE --outgoing --relation implemented_by --json
python3 -m ubiq.cli query --root . --id REQ-RELEASE --outgoing --relation verified_by --json
```

These queries use typed record and relationship support on ubiq main. Install ubiq from this checkout rather than an older release.

`.ubiq/trace.json` declares requirement, implementation, acceptance, contract, and vocabulary records. Its schema requires each requirement to link to implementation and acceptance artifacts. Ubiq checks endpoint types, source coverage, exact excerpts, and SHA-256 digests. Sources are file-level artifacts, not verified TypeScript symbols.

`scripts/trace.ts` uses the Gherkin parser to match feature files and requirement tags to those declarations. Every scenario needs one `@SCN-` tag and one inherited or local `@REQ-` tag. The example supports top-level `features/*.feature` files and ordinary scenarios. Scenario outlines are outside its scope. The execution check requires every expected scenario to run exactly once, with all steps and hooks passing.

Each check deletes old reports before running Cucumber. `reports/cucumber.ndjson` is transient execution evidence. It is not included in the source snapshots. A matching snapshot shows source freshness, not semantic correctness. A passing scenario shows the tested behavior, not exhaustive correctness.

## Agent walkthrough

Use an existing coding agent in this checkout. No new agent runtime is required.

1. Query `REQ-RELEASE` and its outgoing relationships.
2. Read the returned source files and acceptance scenarios.
3. Search the example for callers, expectations, and descriptions of the changed behavior. The declared graph does not include every dependency.
   For release changes, inspect `tests/inventory.test.ts`, this README, and `scripts/mutations.ts` in addition to the linked files.
4. Ask the owner to resolve contradictory requirements before changing behavior.
5. For an approved change, update the requirement and scenarios before the implementation.
6. Run the affected scenarios directly from `examples/inventory/`:

   ```sh
   node --import tsx node_modules/@cucumber/cucumber/bin/cucumber.js --import 'features/steps/*.ts' features/release.feature
   ```

   Check that the old implementation fails the new behavior assertion. `npm run check` stops at stale evidence before executing behavior tests.
   The direct command tests behavior without refreshing evidence. It does not replace the full check.
7. Update the implementation and affected tests, documentation, and mutation targets for the approved change.
8. Run the affected scenarios again. Run `npm run check` and inspect every failure.
9. Review source changes before running `npm run evidence`.
10. Run `npm run check` and `npm run test:mutations`. Review the metadata diff with the code diff.

The evidence command refreshes declared snapshots. It cannot decide whether a relationship is true. Never refresh evidence merely to hide a failing check. Do not weaken expected results to match an implementation.

For a practice task, request an explicit change to repeated-release behavior. Follow the linked requirement to the service and scenario. Keep that exercise on a disposable branch. The committed example retains idempotent release.

## Failure demonstrations

`npm run test:mutations` works in temporary copies and proves that these faults fail:

- A broken requirement-to-implementation reference.
- Changed source content with stale evidence.
- A removed acceptance feature.
- A release implementation that restores stock twice.

The unit tests also reject missing or unknown tags, duplicate scenario IDs, empty coverage, and skipped or incomplete execution reports. The database tests bypass Zod, induce transaction failures, and hold a write lock across two connections. The Gherkin competing-reservations scenario itself is sequential.

All application code remains reviewable. There is no English-to-code compiler, formal proof, or claim that ubiq understands SQL or TypeScript semantics.
