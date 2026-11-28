"""Derived `status: in progress` (a branch exists) and the priority of a plan's own issue."""
from ubiq.sync import GitHub, drift, plan, plan_desired, plan_issue_desired

BRANCH = "claude/work-step"


def record(status="active", priority="", **steps):
    return {"name": "demo", "path": "docs/plans/demo.md", "status": status, "issue": 1,
            "priority": priority, "steps": steps or {"step": {"issue": 7, "branch": BRANCH}}}


def issue(number, *labels, state="open"):
    return {"number": number, "state": state, "body": "", "user": {"login": "someone"},
            "labels": [{"name": n} for n in labels]}


def label_actions(plan_record, issues, **kwargs):
    return [a for a in plan(plan_issue_desired(plan_record) + plan_desired(plan_record), issues, **kwargs) if a["action"] == "label"]


def test_a_pushed_step_branch_marks_its_open_issue_in_progress():
    [action] = label_actions(record(), [issue(1), issue(7)], branches=[BRANCH])
    assert action["issue"] == 7 and action["add"] == ["status: in progress"] and action["remove"] == []
    assert drift([action]) == [action]


def test_the_label_goes_when_the_branch_is_gone_or_the_issue_closed():
    [stale] = label_actions(record(), [issue(1), issue(7, "status: in progress")], branches=["other"])
    assert stale["add"] == [] and stale["remove"] == ["status: in progress"]
    [closed] = label_actions(record(), [issue(1), issue(7, "status: in progress", state="closed")], branches=[BRANCH])
    assert closed["remove"] == ["status: in progress"]
    assert label_actions(record(), [issue(1), issue(7, "status: in progress")], branches=[BRANCH]) == []


def test_an_open_pull_request_replaces_in_progress_with_in_review_in_one_action():
    pull = {"number": 30, "head": BRANCH, "base": "main", "closes": (7,)}
    [action] = label_actions(record(), [issue(1), issue(7, "status: in progress", "bug")], pulls=[pull], branches=[BRANCH])
    assert action["add"] == ["status: in review"] and action["remove"] == ["status: in progress"]


def test_an_issue_branch_marks_an_issue_no_record_tracks():
    [action] = plan([], [issue(9)], branches=["fix/issue-9-typo"])[0:1]
    assert action["add"] == ["status: in progress"] and action["issue"] == 9


def test_a_plans_own_issue_follows_the_plans_priority_even_when_proposed():
    for status in ("proposed", "active"):
        [action] = label_actions(record(status, "P2"), [issue(1, "priority: P1"), issue(7, "priority: P2")])
        assert action["issue"] == 1 and action["add"] == ["priority: P2"] and action["remove"] == ["priority: P1"]
        assert label_actions(record(status, "P2"), [issue(1, "priority: P2"), issue(7, "priority: P2")]) == []
    assert label_actions(record("proposed"), [issue(1, "priority: P1")]) == []


def test_branches_pages():
    calls = []

    def transport(method, url, token, payload=None):
        calls.append(url.rsplit("?", 1)[-1])
        return [{"name": f"b{n}"} for n in range(100)] if url.endswith("&page=1") else [{"name": "last"}]

    names = GitHub("o/r", "t", transport, 0).branches()
    assert len(names) == 101 and names[-1] == "last"
    assert calls == ["per_page=100&page=1", "per_page=100&page=2"]


def test_an_issue_two_records_track_gets_one_status_label_action():
    shared = {"first": {"issue": 7, "branch": BRANCH}, "second": {"issue": 7}}
    [action] = label_actions(record(**shared), [issue(1), issue(7)], branches=[BRANCH])
    assert action["issue"] == 7 and action["add"] == ["status: in progress"]


def test_a_steps_open_pull_request_puts_its_issue_in_review_not_in_progress():
    pull = {"number": 30, "head": BRANCH, "base": "main", "closes": ()}
    steps = {"step": {"issue": 7, "branch": BRANCH, "pr": 30}}
    [action] = label_actions(record(**steps), [issue(1), issue(7)], pulls=[pull], branches=[BRANCH])
    assert action["issue"] == 7 and action["add"] == ["status: in review"] and action["remove"] == []
