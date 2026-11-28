"""Pytest plugin: write the outcome of each Gherkin scenario for `ubiq sync github --results`.

Opt in per run, so it never loads into other test suites:

    pytest -p ubiq.pytest_plugin --ubiq-results results.json

It records the scenario through pytest-bdd's public `pytest_bdd_before_scenario`
hook (declared optional, so pytest without pytest-bdd accepts the plugin) and
imports nothing from pytest-bdd. Each result names the feature file, the scenario,
its criterion labels (`@AC1` tags), and the outcome; a scenario outline contributes
one result per example.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from .scenarios import RESULTS_VERSION, TAG_RE

_RESULTS = pytest.StashKey[list]()
_SCENARIO = pytest.StashKey[dict]()


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.getgroup("ubiq").addoption(
        "--ubiq-results", metavar="PATH", default=None,
        help="write Gherkin scenario outcomes as JSON for `ubiq sync github --results`")


def pytest_configure(config: pytest.Config) -> None:
    config.stash[_RESULTS] = []


def _labels(*groups: Any) -> list[str]:
    return sorted({label for tags in groups for tag in (tags or ()) for label in TAG_RE.findall("@" + tag)})


@pytest.hookimpl(optionalhook=True)
def pytest_bdd_before_scenario(request: pytest.FixtureRequest, feature: Any, scenario: Any) -> None:
    rule = getattr(scenario, "rule", None)
    request.node.stash[_SCENARIO] = {
        "feature": str(Path(feature.filename).resolve()), "scenario": scenario.name,
        "labels": _labels(getattr(scenario, "tags", ()), getattr(feature, "tags", ()),
                          getattr(rule, "tags", ()))}


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo) -> Any:
    outcome = yield
    report = outcome.get_result()
    if report.when != "call" or not item.config.getoption("ubiq_results"):
        return
    scenario = item.stash.get(_SCENARIO, None)
    if scenario is not None:
        item.config.stash[_RESULTS].append({**scenario, "test": item.nodeid, "outcome": report.outcome})


def pytest_sessionfinish(session: pytest.Session) -> None:
    target = session.config.getoption("ubiq_results")
    if target:
        Path(target).write_text(json.dumps(
            {"version": RESULTS_VERSION, "results": session.config.stash[_RESULTS]}, indent=2) + "\n",
            encoding="utf-8")
