"""Priority inheritance: an item without its own `priority` takes its plan's or goal's."""
import json
from pathlib import Path

import pytest
from test_priority_label import labelled
from test_sync import goal, unmet

from ubiq.cli import main
from ubiq.config import load_config
from ubiq.sync import (
    desired_from_config,
    goal_desired,
    load_goal,
    load_plan,
    plan,
    plan_desired,
    resolve_priority,
)

ROOT = Path(__file__).resolve().parents[1]


def plan_record(priority="", **step_priority):
    steps = {name: {"issue": n, "requires": [], **({"priority": step_priority[name]} if name in step_priority else {})}
             for n, name in ((11, "first"), (12, "second"))}
    return {"name": "demo", "path": "docs/plans/demo.md", "status": "active", "issue": 10,
            "steps": steps, "priority": priority}


def step_issue(number, step, *labels):
    return {"number": number, "state": "open", "user": {"login": "github-actions[bot]"},
            "body": f"<!-- ubiq-plan: demo {step} -->", "labels": [{"name": n} for n in labels]}


def test_resolve_priority_prefers_the_item():
    assert resolve_priority({"priority": "P3"}, {"priority": "P1"}) == "P3"
    assert resolve_priority({}, {"priority": "P1"}) == "P1"
    assert resolve_priority({}, {}) == ""


def test_steps_inherit_the_plan_priority_and_an_own_value_wins():
    items = {d.ident["step"]: d.priority for d in plan_desired(plan_record("P1", second="P3"))}
    assert items == {"first": "P1", "second": "P3"}


def test_plan_without_priority_leaves_steps_unmanaged():
    assert {d.priority for d in plan_desired(plan_record())} == {""}


def test_dry_run_labels_each_inheriting_step_and_respects_overrides():
    existing = [{"number": 10, "sub_issues": [11, 12]},
                step_issue(11, "first", "bug"), step_issue(12, "second", "priority: P2")]
    actions = plan(plan_desired(plan_record("P1", second="P2")), existing)
    labels = [(a["issue"], a["add"], a["remove"]) for a in actions if a["action"] == "label"]
    assert labels == [(11, ["priority: P1"], [])]
    assert [a["action"] for a in actions] == ["label", "noop"]


def test_turning_inheritance_on_shows_every_label_change():
    existing = [{"number": 10, "sub_issues": [11, 12]},
                step_issue(11, "first", "priority: P3"), step_issue(12, "second")]
    assert {a["action"] for a in plan(plan_desired(plan_record()), existing)} == {"noop"}
    with_p1 = plan(plan_desired(plan_record("P1")), existing)
    assert [(a["issue"], a["add"], a["remove"]) for a in with_p1] == [
        (11, ["priority: P1"], ["priority: P3"]), (12, ["priority: P1"], [])]


def test_new_step_issue_is_created_with_the_inherited_label():
    record = plan_record("P2")
    record["steps"]["third"] = {"requires": []}
    [create] = [a for a in plan(plan_desired(record), []) if a["action"] == "create"]
    assert create["step"] == "third" and create["labels"] == ["priority: P2"]


def test_goal_criteria_inherit_the_goal_priority_and_an_own_value_wins():
    g = {**goal(AC1=unmet(), AC2=unmet(priority="P3")), "priority": "P1"}
    assert {d.ident["criterion"]: d.priority for d in goal_desired(g)} == {"AC1": "P1", "AC2": "P3"}
    [action] = plan(goal_desired({**goal(AC1=unmet()), "priority": "P1"}), [labelled(7, "priority: P2")])
    assert action["add"] == ["priority: P1"] and action["remove"] == ["priority: P2"]


def test_goal_without_priority_is_unchanged():
    assert {d.priority for d in goal_desired(goal(AC1=unmet()))} == {""}


def test_loaders_read_the_container_priority(tmp_path):
    (tmp_path / "plan.md").write_text("---\nname: demo\nstatus: active\nissue: 1\npriority: P2\ntrunk: main\n"
                                      "steps:\n  a:\n    requires: []\n---\n")
    assert load_plan(tmp_path / "plan.md", tmp_path)["priority"] == "P2"
    (tmp_path / "goal.md").write_text("---\nname: g\nstatus: proposed\npriority: P3\ncriteria: {}\n---\n")
    assert load_goal(tmp_path / "goal.md", tmp_path)["priority"] == "P3"


def test_goal_schema_has_priority_and_its_tracking_copy_still_matches():
    schema = json.loads((ROOT / ".ubiq/schemas/goal.json").read_text())
    fragment = json.loads((ROOT / ".ubiq/schemas/tracking.json").read_text())
    assert schema["properties"]["priority"] == {"$ref": "#/$defs/tracking/properties/priority"}
    assert schema["$defs"]["tracking"]["properties"] == fragment["properties"]


def test_repository_frontmatter_tracking_steps_would_all_be_labelled_p1():
    items = [d for d in desired_from_config(load_config(ROOT)) if d.kind == "plan-step"]
    assert items and {d.priority for d in items} == {"P1"}


@pytest.mark.parametrize("where, text", [("plan", "priority: P9\n"), ("step", "    priority: P9\n")])
def test_invalid_priority_is_a_schema_error(tmp_path, capsys, where, text):
    body = "name: demo\nstatus: active\nissue: 10\ntrunk: main\nsteps:\n  first:\n    requires: []\n"
    body = body.replace("trunk", text + "trunk") if where == "plan" else body + text
    (tmp_path / "schema.json").write_text((ROOT / ".ubiq/schemas/plan.json").read_text())
    (tmp_path / "plans").mkdir()
    (tmp_path / "plans/demo.md").write_text(f"---\n{body}---\n")
    (tmp_path / "ubiq.yaml").write_text(
        'glossary:\n  - {glob: "plans/*.md", term_field: name, ns: plan}\ndocs: ["plans/*.md"]\n'
        'schemas:\n  - schema: schema.json\n    files: ["plans/*.md"]\n    format: frontmatter\n')
    assert main(["check", "--root", str(tmp_path), "--json"]) == 1
    capsys.readouterr()
