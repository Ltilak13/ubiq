# Research: binding Gherkin steps to records and code symbols

Ticket: [#139](https://github.com/Ltilak13/ubiq/issues/139) on wayfinder map [#137](https://github.com/Ltilak13/ubiq/issues/137).
Goal served: AC2 and AC3 of the [code-records goal](https://github.com/Ltilak13/ubiq/pull/136).
Researched 2026-11-27. Package facts come from the PyPI and npm registries and the projects' own repositories. Behavior claims marked "tried" were run in a scratch environment (pytest-bdd 9.0.1, behave 1.3.3, pytest 9.2.0, Python 3.13).

## Recommendation

- **Runner: pytest-bdd.** It runs inside the existing `pytest tests/` command, so CI, the minimum-dependency job, the wheel job, and every `tmp_path` and `capsys` test keep working. Cucumber would add a second runtime (Node) and a second process; behave would add a second runner that cannot share pytest fixtures.
- **Binding scheme: the phrase is a string literal in the step decorator, and records own the words in it.** Each phrase is one `parse`-style string such as `the record "{id}" with {field:Field} {value:d}`. A static check in `ubiq check` reads the decorators and the `.feature` text, and enforces: one phrase maps to one function, each feature step matches exactly one phrase, and every word in a phrase is an approved vocabulary term (#68) or a parameter. Parameter names must be frontmatter fields (#66's `value_refs`).
- **Do not make records generate or look up the decorator phrases at import time yet.** Start with the literal-plus-check form. Move to record-owned phrases (a `step` record that the decorator references by id) only if the check proves too weak.
- **JUnit (#67):** pytest-bdd's default JUnit names a test `test_<scenario slug>[<example values>]`, which loses the scenario's exact text. A 3-line `conftest.py` hook adds the real scenario name as a JUnit property. `ubiq verify` should read that property first and fall back to `name` for Cucumber and behave reports.

## Comparison

| Concern | pytest-bdd 9.0.1 | behave 1.3.3 | @cucumber/cucumber 13.3.0 |
| --- | --- | --- | --- |
| Runs inside `pytest tests/` | Yes. A scenario becomes a pytest test item. | No. Separate `behave` command and `features/steps/` layout. | No. Node process, separate install. |
| Python floor | 3.10 to 3.14 (9.0.0 changelog dropped 3.9) | Metadata says `>=2.7`; 1.4.0 (unreleased) targets 3.10+ | Node 22, 24, or 26+ |
| Last release | 9.0.1, 2026-10-31 | 1.3.3, 2025-09-04 | 13.3.0, 2026-10-05 |
| Fixtures (`tmp_path`, `capsys`) | Native, plus `target_fixture` to pass values between steps | None. Uses a `context` object. | None. Uses a `World` object. |
| Scenario outlines | `Scenario Outline` with `<var>` and `Examples:` tables; multiple tables and tag filters since 8.0.0 | Supported; reports outline rows as `name -- @1.1` | Supported (Gherkin) |
| Step parameters | `string` (exact), `parse` (`{n:d}`), `cfparse` (cardinality), `re` (named groups), and custom `StepParser` classes | `parse` (default), `cfparse`, `re`, and `cucumber-expressions` via `use_step_matcher`; custom types via `register_type` | Cucumber Expressions (`{int}`, `{string}`) and regex; custom parameter types |
| Duplicate phrase | Not detected. Tried: two definitions of the same phrase register, and the later one silently wins. | Detected at load: `AmbiguousStep ... has already been defined` (tried) | Ambiguity reported at run time as a step status |
| JUnit | Built into pytest (`--junitxml`) | Built in (`--junit`, `--junit-directory`) | `junit` formatter |
| Gherkin parser | `gherkin-official` (Cucumber's own) | Own parser | Cucumber's own |

### What I tried

A scenario outline with three steps and a two-row example table, bound with `parsers.parse` and `target_fixture`.

- `pytest --junitxml=r.xml` gave `testcase name="test_percentage_coupon[10-100-90]"` and `[50-80-40]`. The scenario text "percentage coupon" appears only as a slug, and the example values are in brackets.
- A conftest hook `pytest_bdd_before_scenario(request, feature, scenario)` that appends `("scenario", scenario.name)` to `request.node.user_properties` put `<property name="scenario" value="percentage coupon"/>` in the XML. This needs `junit_family=xunit2`. The pytest default is already xunit2, so no setting was needed (the run set it explicitly; I did not test the default).
- Two `@given` definitions with the same phrase: pytest-bdd ran the suite and the second body won (assertion messages showed the second body's value). No warning.
- behave rejected the same duplicate at import with `AmbiguousStep`, naming the file and line of the first definition.
- behave's JUnit reports each outline row as `name="o -- @1.1 "` with `classname` set to the feature module, so matching a criterion to a scenario needs a prefix match.
- Reading the registry: in a `pytest_sessionfinish` hook, `pytest_bdd.steps.step_function_context_registry` lists every step definition with its type and `parser.name` (the phrase). Built-in "trace" steps appear too and must be skipped. The 9.0.0 changelog calls this registry internal, so do not depend on it from `ubiq check`.

## Sources

- pytest-bdd README (step arguments, parsers, scenario outlines, reporting, `scenarios()` binding): <https://github.com/pytest-dev/pytest-bdd/blob/master/README.rst>
- pytest-bdd changelog (9.0.0 drops Python 3.9, multiple example tables in 8.0.0, registries now internal): <https://github.com/pytest-dev/pytest-bdd/blob/master/CHANGES.rst>
- pytest-bdd on PyPI (version, `Requires-Python >=3.10`, requires `pytest>=7.0.0`, `gherkin-official>=29.0.0`): <https://pypi.org/project/pytest-bdd/>
- pytest-bdd source, `StepFunctionContext` and `step_function_context_registry`: `pytest_bdd/steps.py` in the 9.0.1 release.
- behave API (step matchers, `use_step_matcher`, `register_type`): <https://github.com/behave/behave/blob/main/docs/api.rst>
- behave command line and JUnit options: <https://github.com/behave/behave/blob/main/docs/behave.rst>
- behave changelog (1.4.0 unreleased, targets Python 3.10+): <https://github.com/behave/behave/blob/main/CHANGES.rst>
- behave on PyPI: <https://pypi.org/project/behave/>
- Cucumber Expressions: <https://github.com/cucumber/cucumber-expressions> and <https://cucumber.io/docs/cucumber/cucumber-expressions>
- cucumber-js formatters (`junit`): <https://github.com/cucumber/cucumber-js/blob/main/docs/formatters.md>
- @cucumber/cucumber on npm (version, `engines.node`): <https://www.npmjs.com/package/@cucumber/cucumber>
- Gherkin reference (Scenario Outline, Examples): <https://cucumber.io/docs/gherkin/reference/>

I did not confirm cucumber-js's ambiguity behavior from its docs in this pass; the table cell reflects the documented Cucumber model of an ambiguous status at run time and should be treated as unverified.

## How Ubiq's tests run today

- CI (`.github/workflows/ci.yml`): the `test` job runs `python -m pytest tests/ -q` on Python 3.10 to 3.14 on Ubuntu, plus 3.14 on macOS (Intel). The `minimum-dependencies` job installs `pytest>=7.0` on Python 3.10 with pinned PyYAML and jsonschema. The `package` job installs the built wheel and `pytest>=7.0` in a clean venv and runs `pytest tests/ -q` against it. All three then run `ubiq check` as a dogfood step.
- `pyproject.toml`: `pytest>=7.0` is in the `dev` extra. `requires-python >=3.10`. mypy covers `src/ubiq` only; ruff covers `src tests`.
- `tests/run_tests.py` is a zero-dependency runner that emulates only `tmp_path` and `capsys`. It is documented as a fallback; pytest is canonical. It cannot run pytest-bdd scenarios and would skip or drop them.
- Suite size: 33 files, about 6,350 lines, 404 `test_` functions; 31 files use `tmp_path` or `capsys`. Some tests use `pytest.mark.parametrize` (for example `tests/test_coverage.py`). There is no `conftest.py`; shared helpers are imported across test files (`from test_ubiq import make_repo`).
- The Cucumber sample from PR #115 (`examples/no-code-checks`) is JavaScript: `features/reservation.feature`, `features/steps/reservation.js` with `Given("the limits are {int} to {int}", ...)`, `cucumber.js`, and `@cucumber/cucumber` pinned at 12.8.2 through `package-lock.json`. It runs in its own workflow (`no-code-checks.yml`), not in the main suite. It shows the Cucumber model works, but a Node toolchain would be a second runtime for a Python project.

## What a migration needs (pytest-bdd)

1. Add `pytest-bdd` to the `dev` extra. Use an upper bound on the minor version if the check touches internals. Add the same dependency to the `minimum-dependencies` and `package` job installs (they install `pytest>=7.0` by hand and would not see the `dev` extra). Pin the floor to a version compatible with `pytest>=7.0`; 9.0.1 declares `pytest>=7.0.0`, but I did not run it against pytest 7.
2. Add `tests/conftest.py` with the scenario-name JUnit hook and, later, any collection-time audit.
3. Put `.feature` files under `tests/features/` and bind them with `scenarios("features/...")` in thin `test_*.py` modules. Existing tests keep working; migrate public-seam tests first (AC3 covers tests at public seams only).
4. Decide the fate of `tests/run_tests.py`. Options: keep it as a fallback that skips scenario modules, or retire it. Keeping it means the Gherkin tests are not run in the no-pytest environment it was built for.
5. Make `ubiq check` read step decorators statically (Python `ast`, no pytest import) and `.feature` files (Gherkin text, which #66 already proposes scanning). This avoids making the zero-dependency core import pytest or pytest-bdd. Matching a feature step against a `parse` phrase needs a `parse`-compatible matcher; either add the `parse` package as a dependency of that check, or do the match at pytest collection time in the conftest audit instead.
6. Add a CI step for the check results so a duplicate phrase or an unmatched step fails the build with no agent involved.

## Binding scheme detail

One phrase, one function, one set of terms:

| Link | How it is enforced |
| --- | --- |
| Phrase to function | Phrase is the decorator's literal argument. The check normalizes parameters (`{n:d}` to `{}`) and fails on two definitions with the same normalized phrase. This closes the silent last-wins gap. |
| Feature step to phrase | Every step line in every `.feature` must match exactly one phrase; zero is a missing definition (pytest-bdd only reports this when the scenario runs), two is ambiguity. |
| Phrase to terms | Words outside `{...}` are checked against vocabulary records (#68). Unapproved words follow `use_instead`. |
| Parameter to record field | Parameter names, and `<column>` names in outlines, must name frontmatter fields (#66 `value_refs`). |
| Function to symbol | Function name is derived from the phrase terms, and the check compares them. This is the Bound form in the goal. The exact naming rule is a design decision for the vocabulary ticket, not settled here. |
| Scenario to criterion | `ubiq verify --junit` (#67) matches the `scenario` JUnit property (pytest-bdd), `name` (Cucumber), or the `name` prefix before ` -- @` (behave). |

## Risks and open points

- **pytest-bdd's duplicate handling is silent.** The scheme depends on the Ubiq-side check; without it, a copied step overrides the original.
- **Internal registry.** The only runtime view of step definitions is a registry that the project labels internal. Use the static scan for `ubiq check`; use the registry only in an optional conftest audit, behind a version pin.
- **Fast release cadence.** pytest-bdd 9.0.0 and 9.0.1 shipped a month apart, and 9.0.1 fixed a break with pytest 9.2.0. Pin and upgrade deliberately, as `pyproject.toml` already does for ruff and mypy.
- **Dependency drift.** pytest-bdd pulls in `gherkin-official`, `parse`, `parse-type`, `mako`, `packaging`, and `typing-extensions`. Versions 31.0.0 and 32.0.0 of `gherkin-official` are excluded because they crash on empty descriptions. The `minimum-dependencies` job must still resolve.
- **Static phrase extraction limits.** Phrases built from variables, `parsers.re` patterns, or custom `StepParser` classes cannot be read from the AST. Restrict the scheme to literal `parsers.parse` or plain-string phrases, and have the check fail on anything else.
- **JUnit property is not portable.** Other runners will not set it. `ubiq verify` needs a per-runner matching rule, which #67 should list.
- **`run_tests.py` gap.** If it stays, it silently runs fewer tests than CI.
- **Not evaluated:** pytest-bdd-ng (a fork; last release 2.3.1 on 2024-11-26, so not a maintenance risk-free choice), Behat-style tools, and non-Python code.
- **Not tested:** pytest-bdd against pytest 7.0 and Python 3.10 (the repo's lower bounds), and the cucumber-js duplicate-step behavior.
