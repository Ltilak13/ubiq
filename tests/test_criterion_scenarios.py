"""Goal criteria accepted by tagged Gherkin scenarios (E016, `--results`, the pytest plugin)."""

import json
import subprocess
import sys
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, ValidationError

from ubiq.cli import main
from ubiq.scenarios import load_results, parse
from ubiq.schemas import load_schema
from ubiq.sync import goal_desired, goal_issue_desired, plan

ROOT = Path(__file__).resolve().parents[1]
FEATURE = "goals/demo-goal.feature"


# -- parsing -------------------------------------------------------------------------

def test_parse_reads_labels_from_scenario_and_feature_tags():
    found = parse("""@AC9 @wip
Feature: Demo
  # @AC7 in a comment is not a tag
  @AC1 @slow
  Scenario: one
    Given x

  Scenario Outline: two
    Given <v>

  @AC2
  Example: three
""")
    assert [(s.name, s.labels, s.line) for s in found] == [
        ("one", ("AC9", "AC1"), 5), ("two", ("AC9",), 8), ("three", ("AC9", "AC2"), 12)]


# -- E016 ----------------------------------------------------------------------------

GOAL = """---
name: demo-goal
status: active
criteria:
  AC1:
    scenario: true
  AC2:
    assessment: unassessed
    support: []
    gap: g
---

1. AC1: First.
2. AC2: Second.
"""


def repo(root, feature=None, goal=GOAL):
    (root / "goals").mkdir()
    (root / "goals/demo-goal.md").write_text(goal)
    if feature is not None:
        (root / FEATURE).write_text(feature)
    (root / "ubiq.yaml").write_text(
        'glossary:\n  - {glob: "goals/*-goal.md", term_field: name, ns: goal}\ndocs: ["goals/*.md"]\n'
        'sync:\n  repo: o/r\n  records:\n    - {glob: "goals/*-goal.md", kind: goal}\n')
    return root


def e016(root, capsys):
    status = main(["check", "--root", str(root), "--json"])
    out = json.loads(capsys.readouterr().out)
    return status, [(Path(d["file"]).name, d["message"]) for d in out["diagnostics"] if d["code"] == "E016"]


def test_a_bound_criterion_with_its_tagged_scenario_passes(tmp_path, capsys):
    repo(tmp_path, "Feature: Demo\n  @AC1\n  Scenario: first\n    Given x\n")
    assert e016(tmp_path, capsys) == (0, [])


@pytest.mark.parametrize("feature, expected", [
    (None, "criterion AC1 sets scenario: true, but demo-goal.feature does not exist"),
    ("Feature: Demo\n  Scenario: untagged\n", "no scenario in demo-goal.feature is tagged @AC1"),
])
def test_a_bound_criterion_without_a_scenario_is_e016(tmp_path, capsys, feature, expected):
    repo(tmp_path, feature)
    status, found = e016(tmp_path, capsys)
    assert status == 1 and len(found) == 1 and expected in found[0][1]


@pytest.mark.parametrize("tag, reason", [("AC2", "names a criterion without scenario: true in"),
                                         ("AC9", "names no criterion of")])
def test_a_tag_that_names_no_bound_criterion_is_e016_at_the_scenario(tmp_path, capsys, tag, reason):
    repo(tmp_path, f"Feature: Demo\n  @AC1\n  Scenario: first\n\n  @{tag}\n  Scenario: other\n")
    status, found = e016(tmp_path, capsys)
    message = f"scenario 'other' is tagged @{tag}, which {reason} demo-goal.md"
    assert status == 1 and found == [("demo-goal.feature", message)]


# -- the schema ----------------------------------------------------------------------

SCHEMA = load_schema(ROOT, ROOT / ".ubiq/schemas/goal.json")


def criterion(**fields):
    return {"name": "g", "status": "active", "criteria": {"AC1": fields}}


def test_a_bound_criterion_stores_no_assessment():
    Draft202012Validator(SCHEMA).validate(criterion(scenario=True, issues=[3], priority="P2"))
    for extra in ({"assessment": "met"}, {"support": []}, {"gap": "g"},
                  {"review": {"by": "a", "note": "b", "at": "a" * 40, "date": "2026-11-28"}}):
        with pytest.raises(ValidationError):
            Draft202012Validator(SCHEMA).validate(criterion(scenario=True, **extra))
    with pytest.raises(ValidationError):
        Draft202012Validator(SCHEMA).validate(criterion(scenario=False))


# -- results -------------------------------------------------------------------------

def results_file(tmp_path, *results):
    path = tmp_path / "results.json"
    path.write_text(json.dumps({"version": 1, "results": [
        {"feature": str(tmp_path / f), "scenario": s, "labels": labels, "outcome": o}
        for f, s, labels, o in results]}))
    return path


def test_a_label_passes_only_when_every_tagged_result_passed(tmp_path):
    path = results_file(tmp_path, (FEATURE, "a", ["AC1"], "passed"), (FEATURE, "b", ["AC1"], "failed"),
                        (FEATURE, "c", ["AC2"], "passed"), ("/elsewhere/x.feature", "d", ["AC3"], "passed"))
    assert load_results(path, tmp_path) == {(FEATURE, "AC1"): "failed", (FEATURE, "AC2"): "passed"}


def test_a_file_without_the_version_is_rejected(tmp_path):
    (tmp_path / "r.json").write_text('{"results": []}')
    with pytest.raises(ValueError, match="results file"):
        load_results(tmp_path / "r.json", tmp_path)


# -- derived state -------------------------------------------------------------------

def goal(issue=0, **criteria):
    return {"name": "demo-goal", "path": "goals/demo-goal.md", "issue": issue, "criteria": criteria,
            "text": {ac: f"{n}. {ac}: Text." for n, ac in enumerate(criteria, 1)}}


BOUND = {"scenario": True}
MARK = "<!-- ubiq-goal: demo-goal AC1 -->"


def gh(number, state="open", marker=MARK):
    return {"number": number, "state": state, "body": f"x\n{marker}", "user": {"login": "github-actions[bot]"}}


def actions(items, snapshot):
    return [(a["action"], a.get("issue"), a.get("title", "")) for a in plan(items, snapshot) if a["action"] != "noop"]


def test_a_passing_scenario_closes_the_criterion_issue():
    items = goal_desired(goal(AC1=BOUND), "abc", results={(FEATURE, "AC1"): "passed"})
    assert actions(items, [gh(5)]) == [("close", 5, "")]
    assert "every scenario tagged `@AC1`" in items[0].close_comment


@pytest.mark.parametrize("results", [None, {}, {(FEATURE, "AC1"): "failed"}])
def test_without_a_passing_result_the_criterion_stays_open(results):
    assert actions(goal_desired(goal(AC1=BOUND), results=results), [gh(5)]) == []


def test_a_failing_scenario_after_its_issue_closed_opens_a_regression():
    items = goal_desired(goal(AC1=BOUND), results={(FEATURE, "AC1"): "failed"}, prioritized_only=True)
    [(action, _, title)] = actions(items, [gh(5, state="closed")])
    assert action == "create" and title.startswith("Regression: ")
    assert "failed on `main`" in items[0].body
    # Not run is not a regression: nothing opens.
    assert actions(goal_desired(goal(AC1=BOUND), results={}), [gh(5, state="closed")]) == []


def test_the_goal_issue_closes_when_every_criterion_holds():
    met = {"assessment": "met", "support": [], "gap": "g", "review": {}}
    elsewhere = {"assessment": "unassessed", "support": [], "gap": "g",
                 "assessed_in": {"goal": "other-goal", "criterion": "AC1"}}
    other = {**goal(AC1=BOUND), "name": "other-goal", "path": "goals/other-goal.md"}
    goals = [goal(issue=9, AC1=BOUND, AC2=met, AC3=elsewhere), other]
    passed = {(FEATURE, "AC1"): "passed", ("goals/other-goal.feature", "AC1"): "passed"}
    [item] = goal_issue_desired(goals, "abc", passed)
    assert item.state == "closed" and actions([item], [gh(9, marker="")]) == [("close", 9, "")]
    for results in (None, {**passed, ("goals/other-goal.feature", "AC1"): "failed"}):
        [item] = goal_issue_desired(goals, "abc", results)
        assert item.state == "open"


# -- the pytest plugin ---------------------------------------------------------------

def test_the_plugin_writes_each_scenario_outcome_with_its_labels(tmp_path):
    pytest.importorskip("pytest_bdd")
    (tmp_path / "demo.feature").write_text(
        "Feature: Demo\n  @AC1\n  Scenario: one\n    Given x\n\n"
        "  @AC2 @slow\n  Scenario Outline: two\n    Given <v>\n\n    Examples:\n      | v |\n      | x |\n      | y |\n")
    (tmp_path / "test_demo.py").write_text(
        "from pytest_bdd import given, scenarios\nscenarios('demo.feature')\n"
        "@given('x')\ndef _x(): pass\n@given('y')\ndef _y(): raise AssertionError\n")
    out = tmp_path / "results.json"
    subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", f"--ubiq-results={out}"],
                   cwd=tmp_path, capture_output=True, check=False)
    assert load_results(out, tmp_path) == {("demo.feature", "AC1"): "passed", ("demo.feature", "AC2"): "failed"}
