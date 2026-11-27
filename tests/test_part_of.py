"""`part_of`: `single` in `ubiq check`, and sub-issues in the sync (`fact_part_of`)."""
import json
import urllib.error
from types import SimpleNamespace

from test_sync import Fake, goal, issue, unmet, write_repo
from test_tracking import ROOT, errors, repo, run

from ubiq import xref
from ubiq.config import load_config
from ubiq.sync import GitHub, cmd_sync, desired_from_config, drift, goal_desired, plan

PART_OF = {"type": "array", "items": {"type": "string"},
           "x-ubiq-ref": {"ns": "feature", "edge": "part_of", "single": True}}


def with_part_of(root):
    schema = json.loads((root / "schema.json").read_text())
    schema["properties"]["criteria"]["patternProperties"]["^AC[0-9]+$"]["properties"]["part_of"] = PART_OF
    schema["properties"]["part_of"] = PART_OF
    (root / "schema.json").write_text(json.dumps(schema))


# -- ubiq check: single ---------------------------------------------------------------


def test_group_of_values_is_per_property():
    data = {"criteria": {"AC1": {"part_of": ["a", "b"]}, "AC2": {"part_of": ["a"]}}, "part_of": "c"}
    schema = {"properties": {"criteria": {"patternProperties": {"^AC": {"properties": {
        "part_of": {"x-ubiq-ref": {"ns": "g", "edge": "part_of", "single": True}}}}}}}}
    [annotation] = xref.collect(schema)
    assert list(xref.groups(data, annotation.steps)) == [
        (("criteria", "AC1", "part_of"), ["a", "b"]), (("criteria", "AC2", "part_of"), ["a"])]


def test_more_than_one_part_of_target_fails_check_with_its_location(tmp_path, capsys):
    repo(tmp_path, "---\nname: work\ncriteria:\n  AC1:\n    part_of: [alpha, beta]\n"
                   "  AC2:\n    part_of: [alpha]\n---\n\nWork.\n")
    with_part_of(tmp_path)
    status, report = run(tmp_path, capsys, "check")
    [error] = errors(report, "E009")
    assert status == 1
    assert error["file"].endswith("g/work.md") and error["line"] == 5
    assert "criteria.AC1.part_of" in error["message"] and "alpha, beta" in error["message"]


def test_one_target_or_an_unannotated_single_passes(tmp_path, capsys):
    repo(tmp_path, "---\nname: work\npart_of: [alpha]\ncriteria:\n  AC1:\n    part_of: [beta]\n---\n\nWork.\n")
    with_part_of(tmp_path)
    status, report = run(tmp_path, capsys, "check")
    assert status == 0 and not errors(report, "E009")
    repo_two = tmp_path / "two"
    repo_two.mkdir()
    repo(repo_two, "---\nname: work\ncriteria:\n  AC1:\n    requires: [alpha, beta]\n---\n\nWork.\n")
    _status, report = run(repo_two, capsys, "check")
    assert not errors(report, "E009")


def test_this_repository_marks_part_of_single():
    schema = json.loads((ROOT / ".ubiq/schemas/goal.json").read_text())
    [part] = [a for a in xref.collect(schema) if a.ref.edge == "part_of"]
    assert part.ref.single and part.ref.ns == "goal"


# -- planner --------------------------------------------------------------------------


def two_goals(**issues):
    return {"demo-goal": {**goal(AC1=unmet(), AC2=unmet(part_of=["other-goal"])), "issue": 1, **issues},
            "other-goal": {**goal(AC1=unmet()), "name": "other-goal", "issue": 2}}


def desired(goals):
    numbers = {name: g.get("issue", 0) for name, g in goals.items()}
    return [d for g in goals.values() for d in goal_desired(g, goal_issues=numbers)]


def gh(number, state="open", marker=None, goal_name="demo-goal", sub=None, id_=None):
    return {**issue(number, state, marker, goal_name), "id": id_ or 1000 + number,
            **({"sub_issues": sub} if sub is not None else {})}


def test_criterion_is_part_of_its_goal_or_of_the_goal_it_names():
    one, two = (d for d in desired(two_goals()) if d.parent_issue and d.ident["goal"] == "demo-goal")
    assert (one.parent, one.parent_issue) == ("demo-goal", 1)
    assert (two.parent, two.parent_issue) == ("other-goal", 2)


def test_goal_without_an_issue_plans_no_sub_issue_actions():
    [item] = goal_desired(goal(AC1=unmet()))
    assert item.parent_issue == 0
    assert [a["action"] for a in plan([item], [gh(5, marker="AC1")])] == ["noop"]


def test_tracked_issue_that_is_not_a_sub_issue_is_linked_and_it_is_drift():
    items = desired(two_goals())
    existing = [gh(1, sub=[]), gh(2, sub=[]), gh(5, marker="AC1"), gh(6, marker="AC2")]
    actions = [a for a in plan(items, existing) if a["action"] != "create"]
    assert [(x["action"], x["issue"], x["parent"], x["sub_issue_id"]) for x in actions] == [
        ("link", 5, 1, 1005), ("link", 6, 2, 1006)]
    assert drift(actions) == actions


def test_matching_sub_issues_are_noop():
    items = desired(two_goals())
    existing = [gh(1, sub=[5]), gh(2, sub=[6]), gh(5, marker="AC1"), gh(6, marker="AC2"),
                gh(7, marker="AC1", goal_name="other-goal")]
    actions = plan(items, existing)
    # 7 belongs to other-goal AC1 and is not a child of issue 2 yet: that is a link, nothing else.
    assert [a["issue"] for a in actions if a["action"] == "link"] == [7]


def test_sub_issue_added_on_github_is_drift_and_unlinked():
    items = desired({"demo-goal": two_goals()["demo-goal"]})
    existing = [gh(1, sub=[5, 99]), gh(2, sub=[]), gh(5, marker="AC1"), gh(99), gh(6, marker="AC2")]
    extra = [a for a in plan(items, existing) if a["action"] == "unlink"]
    assert extra == [{"action": "unlink", "issue": 99, "parent": 1, "sub_issue_id": 1099,
                      "reason": "sub-issue is not part_of the parent record"}]
    assert drift(extra) == extra


def test_issue_moved_to_another_parent_is_a_link_not_an_unlink():
    # AC2 now names other-goal, but GitHub still has issue 6 under demo-goal's issue 1.
    items = desired(two_goals())
    existing = [gh(1, sub=[5, 6]), gh(2, sub=[]), gh(5, marker="AC1"), gh(6, marker="AC2")]
    actions = plan(items, existing)
    assert [(a["action"], a["issue"], a["parent"]) for a in actions if a["action"] in ("link", "unlink")] \
        == [("link", 6, 2)]


def test_parent_that_is_not_an_issue_warns():
    [item] = goal_desired({**goal(AC1=unmet()), "issue": 42})
    [warning, *_] = plan([item], [gh(5, marker="AC1")])
    assert warning["action"] == "warn" and warning["issue"] == 42


def test_listed_issues_are_all_children_and_the_parent_itself_is_skipped():
    items = desired({"demo-goal": {**goal(AC1=unmet(issues=[5, 1])), "issue": 1}})
    actions = plan(items, [gh(1, sub=[]), gh(5)])
    assert [(a["action"], a["issue"]) for a in actions] == [("link", 5)]


def test_new_issue_carries_its_parent():
    [create] = plan(desired({"demo-goal": {**goal(AC1=unmet()), "issue": 1}}), [gh(1, sub=[])])
    assert create["action"] == "create" and create["parent_issue"] == 1


# -- adapter ----------------------------------------------------------------------------


def test_snapshot_reads_the_sub_issues_of_each_parent_with_paging():
    first = [{"number": n} for n in range(100)]
    fake = Fake({("GET", "?state=all&per_page=100&page=1"): [{"number": 1, "id": 11}, {"number": 2, "id": 22}],
                 ("GET", "/1/sub_issues?per_page=100&page=1"): first,
                 ("GET", "/1/sub_issues?per_page=100&page=2"): [{"number": 100}]})
    issues = GitHub("o/r", "t", fake, 0).snapshot([1, 1, 77])
    assert issues[0]["sub_issues"] == list(range(101)) and "sub_issues" not in issues[1]
    assert [c[1] for c in fake.calls].count("/1/sub_issues?per_page=100&page=1") == 1


def test_link_posts_the_numeric_id_and_replaces_another_parent():
    fake = Fake()
    done = []
    link = {"action": "link", "issue": 5, "parent": 1, "sub_issue_id": 1005}
    GitHub("o/r", "t", fake, 0).apply([link], done)
    assert [(m, u, p) for m, u, _t, p in fake.calls] == [
        ("POST", "/1/sub_issues", {"sub_issue_id": 1005, "replace_parent": True})]
    assert done == [link]


def test_unlink_deletes_with_a_body_and_ignores_a_missing_sub_issue():
    link = {"action": "unlink", "issue": 99, "parent": 1, "sub_issue_id": 1099}
    fake = Fake()
    GitHub("o/r", "t", fake, 0).apply([link], [])
    assert [(m, u, p) for m, u, _t, p in fake.calls] == [("DELETE", "/1/sub_issue", {"sub_issue_id": 1099})]

    def gone(method, url, token, payload=None):
        raise urllib.error.HTTPError(url, 404, "gone", None, None)
    GitHub("o/r", "t", gone, 0).apply([link], [])


def test_create_then_attach_in_one_apply():
    [create] = plan(desired({"demo-goal": {**goal(AC1=unmet()), "issue": 1}}), [gh(1, sub=[])])
    fake = Fake({("POST", ""): {"number": 42, "id": 4242}})
    GitHub("o/r", "t", fake, 0).apply([create], [])
    assert [(m, u) for m, u, *_ in fake.calls] == [("POST", ""), ("POST", "/1/sub_issues")]
    assert fake.calls[1][3] == {"sub_issue_id": 4242, "replace_parent": True}


# -- command: apply makes the sub-issues match, then plan is quiet ---------------------


class Hub:
    """A stateful stand-in for the repository: issues, parents, and the sub_issues API."""

    def __init__(self, issues, parents):
        self.issues = {i["number"]: i for i in issues}
        self.parents = dict(parents)  # child number -> parent number

    def by_id(self, ident):
        return next(i for i in self.issues.values() if i["id"] == ident)

    def __call__(self, method, url, token, payload=None):
        tail = url.split("/issues", 1)[-1]
        if method == "GET" and tail.startswith("?state=all"):
            return list(self.issues.values())
        if method == "GET" and tail.endswith("/sub_issues?per_page=100&page=1"):
            parent = int(tail.split("/")[1])
            return [self.issues[c] for c, p in sorted(self.parents.items()) if p == parent]
        if method == "POST" and tail.endswith("/sub_issues"):
            self.parents[self.by_id(payload["sub_issue_id"])["number"]] = int(tail.split("/")[1])
            return {}
        if method == "DELETE" and tail.endswith("/sub_issue"):
            self.parents.pop(self.by_id(payload["sub_issue_id"])["number"], None)
            return {}
        raise AssertionError((method, url))


def test_apply_converges_and_a_hand_added_sub_issue_is_drift(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("GITHUB_TOKEN", "t")
    root = write_repo(tmp_path)
    text = (root / "goals/demo-goal.md").read_text().replace("status: proposed", "status: proposed\nissue: 1")
    (root / "goals/demo-goal.md").write_text(text)
    hub = Hub([gh(1), gh(5, marker="AC1"), gh(9)], {})
    args = SimpleNamespace(root=str(root), repo=None, apply=False, check=True, dry_run=False)
    assert cmd_sync(args, hub, 0) == 1
    assert [a["action"] for a in json.loads(capsys.readouterr().out)] == ["link"]
    args.check, args.apply = False, True
    assert cmd_sync(args, hub, 0) == 0
    capsys.readouterr()
    assert hub.parents == {5: 1}
    args.check, args.apply = True, False
    assert cmd_sync(args, hub, 0) == 0
    capsys.readouterr()
    hub.parents[9] = 1  # someone adds issue 9 under the goal's issue on GitHub
    assert cmd_sync(args, hub, 0) == 1
    assert [a["action"] for a in json.loads(capsys.readouterr().out)] == ["unlink"]
    args.check, args.apply = False, True
    assert cmd_sync(args, hub, 0) == 0
    assert hub.parents == {5: 1}


def test_config_reads_the_goal_issue_and_part_of(tmp_path):
    root = write_repo(tmp_path)
    (root / "goals/demo-goal.md").write_text(
        "---\nname: demo-goal\nstatus: proposed\nissue: 11\ncriteria:\n  AC1:\n    assessment: unassessed\n"
        "    support: []\n    gap: g\n    part_of: [elsewhere]\n---\n\n1. AC1: First.\n")
    (root / "goals/elsewhere-goal.md").write_text(
        "---\nname: elsewhere\nstatus: proposed\nissue: 12\ncriteria:\n  AC1:\n    assessment: unassessed\n"
        "    support: []\n    gap: g\n---\n\n1. AC1: Second.\n")
    items = {(d.ident["goal"], d.ident["criterion"]): d for d in desired_from_config(load_config(root))}
    assert items[("demo-goal", "AC1")].parent_issue == 12
    assert items[("elsewhere", "AC1")].parent_issue == 12



def test_feature_part_of_links_its_issue_to_the_parent(tmp_path):
    root = write_repo(tmp_path)
    (root / "f").mkdir()
    (root / "f/parent.md").write_text("---\nname: parent-feature\nissue: 11\n---\n")
    (root / "f/child.md").write_text(
        "---\nname: child\nissue: 12\npart_of: [parent-feature]\n---\n")
    config = root / "ubiq.yaml"
    config.write_text(config.read_text() + (
        '\nschemas:\n  - schema: schema.json\n    files: ["f/*.md"]\n    format: frontmatter\n'))
    (root / "schema.json").write_text("{}")
    desired = desired_from_config(load_config(root))
    [link] = drift(plan(desired, [gh(5, marker="AC1"), gh(11), gh(12)]))
    assert (link["record"], link["issue"], link["parent"]) == ("child", 12, 11)
