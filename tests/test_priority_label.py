"""The priority label: `fact_priority` plans it and one GitHub handler performs it."""
import urllib.error

import pytest
from test_sync import Fake, goal, issue, met, unmet

from ubiq.config import InvalidConfig, load_config
from ubiq.sync import GitHub, drift, goal_desired, plan


def labelled(number, *names, **kwargs):
    return {**issue(number, marker="AC1", **kwargs), "labels": [{"name": n} for n in names]}


def run_plan(criterion, existing):
    return plan(goal_desired(goal(AC1=criterion)), existing)


def test_new_issue_is_created_with_its_priority_label():
    [action] = run_plan(unmet(priority="P1"), [])
    assert action["action"] == "create" and action["labels"] == ["priority: P1"]


def test_no_priority_creates_without_labels_and_leaves_labels_alone():
    [action] = run_plan(unmet(), [])
    assert "labels" not in action
    found = run_plan(unmet(), [labelled(7, "priority: P3", "bug")])
    assert [a["action"] for a in found] == ["noop"]


def test_changing_priority_is_one_label_change_that_leaves_other_labels():
    existing = [labelled(7, "priority: P2", "bug", "priority-ish")]
    [action] = run_plan(unmet(priority="P1"), existing)
    assert action == {"action": "label", "goal": "demo-goal", "criterion": "AC1", "issue": 7,
                      "add": ["priority: P1"], "remove": ["priority: P2"]}
    assert drift([action]) == [action]


def test_matching_label_is_noop_and_case_does_not_matter():
    for name in ("priority: P2", "Priority: p2"):
        assert [a["action"] for a in run_plan(unmet(priority="P2"), [labelled(7, name)])] == ["noop"]


def test_hand_edited_label_is_drift_and_extra_priority_labels_are_removed():
    [added] = run_plan(unmet(priority="P2"), [labelled(7, "bug")])
    assert added["add"] == ["priority: P2"] and added["remove"] == []
    [extra] = run_plan(unmet(priority="P2"), [labelled(7, "priority: P2", "priority: P1", "priority: P3")])
    assert extra["add"] == [] and extra["remove"] == ["priority: P1", "priority: P3"]


def test_closed_issue_and_met_criterion_are_not_relabelled():
    assert [a["action"] for a in run_plan(unmet(priority="P1"), [labelled(7, state="closed")])] == ["noop"]
    found = run_plan(met(priority="P1"), [labelled(7, "priority: P2")])
    assert [a["action"] for a in found] == ["close"]


def test_custom_prefix_owns_only_labels_with_that_prefix():
    desired = goal_desired(goal(AC1=unmet(priority="P1")), label_prefix="prio/")
    [action] = plan(desired, [labelled(7, "prio/P3", "priority: P2")])
    assert action["add"] == ["prio/P1"] and action["remove"] == ["prio/P3"]


def test_criterion_issue_field_is_tracked_like_issues():
    [action] = plan(goal_desired(goal(AC1=unmet(issue=7, priority="P1"))),
                    [{**issue(7), "labels": []}])
    assert action["action"] == "label" and action["issue"] == 7


def test_planning_is_idempotent_after_applying_the_labels():
    existing = [labelled(7, "priority: P2", "bug")]
    desired = goal_desired(goal(AC1=unmet(priority="P1")))
    [action] = plan(desired, existing)
    after = [{**existing[0], "labels": [{"name": "bug"}, {"name": "priority: P1"}]}]
    assert [a["action"] for a in plan(desired, after)] == ["noop"]
    assert action["remove"] == ["priority: P2"]


def test_adapter_deletes_old_labels_then_adds_the_new_one():
    fake = Fake()
    GitHub("o/r", "t", fake, 0).apply(
        [{"action": "label", "issue": 7, "add": ["priority: P1"], "remove": ["priority: P2"]}], [])
    assert fake.calls == [
        ("DELETE", "/7/labels/priority%3A%20P2", "t", None),
        ("POST", "/7/labels", "t", {"labels": ["priority: P1"]})]


def test_adapter_ignores_a_label_that_is_already_gone():
    def gone(method, url, token, payload=None):
        if method == "DELETE":
            raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)
        return {}
    done = []
    GitHub("o/r", "t", gone, 0).apply(
        [{"action": "label", "issue": 7, "add": [], "remove": ["priority: P2"]}], done)
    assert len(done) == 1


def test_adapter_creates_an_issue_with_labels():
    fake = Fake({("POST", ""): {"number": 9}})
    GitHub("o/r", "t", fake, 0).apply(
        [{"action": "create", "title": "t", "body": "b", "labels": ["priority: P1"]}], [])
    assert fake.calls[0][3] == {"title": "t", "body": "b", "labels": ["priority: P1"]}


def test_empty_label_prefix_is_rejected(tmp_path):
    (tmp_path / "ubiq.yaml").write_text(
        'sync:\n  label_prefix: " "\n  records:\n    - {glob: "g/*.md", kind: goal}\n')
    with pytest.raises(InvalidConfig, match="label_prefix"):
        load_config(tmp_path)
