"""Goal criteria bound to Gherkin scenarios, and their results.

A goal criterion with `scenario: true` is accepted by the scenarios tagged with
its label (`@AC1`) in the feature file beside the goal (`<goal>.feature`). The
scenario is the acceptance criterion: a person approves its text in review, and a
run decides whether it holds. The criterion stores no assessment. `ubiq sync
github --results FILE` reads a results file (written by the ubiq pytest plugin) and
treats the criterion as met exactly when every scenario tagged with it passed.

`ubiq check` reports E016 when a bound criterion has no tagged scenario, and when a
scenario is tagged with a label that names no bound criterion of the goal.
"""
from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .check import Diagnostic

TAG_RE = re.compile(r"@(AC[1-9][0-9]*)(?![\w-])")
SCENARIO_RE = re.compile(r"^\s*(?:Scenario|Scenario Outline|Scenario Template|Example):\s*(.+?)\s*$")
FEATURE_RE = re.compile(r"^\s*Feature:")
RESULTS_VERSION = 1


@dataclass(frozen=True)
class Scenario:
    name: str
    labels: tuple[str, ...]  # criterion labels from its tags and the feature's tags
    line: int


def feature_of(goal_path: Path) -> Path:
    """The feature file that holds a goal's scenarios: the goal path with `.feature`."""
    return goal_path.with_suffix(".feature")


def parse(text: str) -> list[Scenario]:
    """The scenarios of a feature file, each with the criterion labels it is tagged with."""
    found: list[Scenario] = []
    pending: list[str] = []
    feature_labels: list[str] = []
    for number, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        if stripped.startswith("@"):
            pending += TAG_RE.findall(stripped.split("#", 1)[0])
        elif FEATURE_RE.match(line):
            feature_labels, pending = pending, []
        elif match := SCENARIO_RE.match(line):
            labels = tuple(dict.fromkeys([*feature_labels, *pending]))
            found.append(Scenario(match.group(1), labels, number))
            pending = []
        elif stripped and not stripped.startswith("#"):
            pending = []
    return found


def bound(criteria: Mapping[str, Any]) -> list[str]:
    """The labels of the criteria that a scenario accepts."""
    return [ac for ac, c in criteria.items() if isinstance(c, Mapping) and c.get("scenario") is True]


def diagnostics(goals: Iterable[tuple[Path, Mapping[str, Any]]]) -> list[Diagnostic]:
    """E016 for each bound criterion without a scenario, and each tag that names no bound criterion."""
    found: list[Diagnostic] = []
    for path, data in goals:
        criteria = data.get("criteria") if isinstance(data, Mapping) else None
        if not isinstance(criteria, Mapping):
            continue
        want = bound(criteria)
        feature = feature_of(path)
        if not feature.is_file():
            found += [Diagnostic("E016", f"criterion {ac} sets scenario: true, but {feature.name} "
                                         f"does not exist", path, 1) for ac in want]
            continue
        scenarios = parse(feature.read_text(encoding="utf-8"))
        tagged = {label for s in scenarios for label in s.labels}
        found += [Diagnostic("E016", f"criterion {ac} sets scenario: true, but no scenario in "
                                     f"{feature.name} is tagged @{ac}", path, 1)
                  for ac in want if ac not in tagged]
        for scenario in scenarios:
            for label in scenario.labels:
                if label not in want:
                    reason = ("names no criterion of" if label not in criteria
                              else "names a criterion without scenario: true in")
                    found.append(Diagnostic("E016", f"scenario '{scenario.name}' is tagged @{label}, "
                                                    f"which {reason} {path.name}", feature, scenario.line))
    return found


def load_results(path: Path, root: Path) -> dict[tuple[str, str], str]:
    """(feature path relative to root, label) -> `passed` or `failed`, from a results file.

    A label passes only when every result tagged with it passed; any other outcome
    (failed, skipped, error) fails it. A label with no result is absent: not run.
    """
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, Mapping) or data.get("version") != RESULTS_VERSION:
        raise ValueError(f"{path}: not a ubiq scenario results file (version {RESULTS_VERSION})")
    outcomes: dict[tuple[str, str], str] = {}
    root = Path(root).resolve()
    for result in data.get("results", []):
        feature = Path(result["feature"])
        try:
            rel = (feature if feature.is_absolute() else root / feature).resolve().relative_to(root).as_posix()
        except ValueError:
            continue  # a feature outside this repository
        for label in result.get("labels", []):
            key = (rel, label)
            ok = result.get("outcome") == "passed"
            outcomes[key] = "passed" if ok and outcomes.get(key, "passed") == "passed" else "failed"
    return outcomes
