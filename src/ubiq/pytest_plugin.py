"""Pytest plugin: write the outcome of each Gherkin scenario for `ubiq sync github --results`.

Inert unless `--ubiq-results PATH` is given. It reads the scenario that
pytest-bdd attaches to each test function, so it imports nothing from pytest-bdd.
Each result names the feature file, the scenario, its criterion labels (`@AC1`
tags), and the outcome; a scenario outline contributes one result per example.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from .scenarios import RESULTS_VERSION, TAG_RE

_KEY = pytest.StashKey[list]()


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.getgroup("ubiq").addoption(
        "--ubiq-results", metavar="PATH", default=None,
        help="write Gherkin scenario outcomes as JSON for `ubiq sync github --results`")


def pytest_configure(config: pytest.Config) -> None:
    config.stash[_KEY] = []


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo) -> Any:
    outcome = yield
    report = outcome.get_result()
    scenario = getattr(getattr(item, "obj", None), "__scenario__", None)
    if scenario is None or not item.config.getoption("ubiq_results"):
        return
    # One result per test: the call phase, or the phase that stopped it first.
    if report.when == "call" or (report.when == "setup" and report.outcome != "passed"):
        labels = sorted({m for tag in scenario.tags for m in TAG_RE.findall("@" + tag)}
                        | {m for tag in scenario.feature.tags for m in TAG_RE.findall("@" + tag)})
        item.config.stash[_KEY].append({
            "feature": str(Path(scenario.feature.filename).resolve()),
            "scenario": scenario.name, "labels": labels, "test": item.nodeid,
            "outcome": report.outcome if report.when == "call" else "error"})


def pytest_sessionfinish(session: pytest.Session) -> None:
    target = session.config.getoption("ubiq_results")
    if target:
        Path(target).write_text(json.dumps(
            {"version": RESULTS_VERSION, "results": session.config.stash[_KEY]}, indent=2) + "\n",
            encoding="utf-8")
