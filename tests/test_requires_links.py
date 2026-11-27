"""`requires`: blocked-by links, and the generated "Blocked by" section."""
import json
import urllib.error
from types import SimpleNamespace

from test_sync import Fake, goal, issue, unmet

from ubiq.config import load_config
from ubiq.sync import (
    BLOCKED_BEGIN,
    BLOCKED_END,
    GitHub,
    cmd_sync,
    desired_from_config,
    drift,
    goal_desired,
    plan,
    set_blocked_by,
)

# -- planning links ---------------------------------------------------------------------

def blocked(number, *links, **kwargs):
    return {**issue(number, marker="AC1", **kwargs), "id": 1000 + number,
            "blocked_by": [{"number": n, "id": 1000 + n} for n in links]}


def blocker(number, **kwargs):
    return {**issue(number, **kwargs), "id": 1000 + number}


def run_plan(criterion, existing, numbers):
    return plan(goal_desired(goal(AC1=criterion), numbers=numbers), existing)


NUMBERS = {"alpha": 11, "beta": 12, "plain": 13}


def test_adding_a_requires_entry_links_the_blocker_by_its_numeric_id():
    [link] = run_plan(unmet(requires=["alpha"]), [blocked(7), blocker(11)], NUMBERS)
    assert link == {"action": "link", "goal": "demo-goal", "criterion": "AC1", "issue": 7,
                    "blocked_by": 11, "issue_id": 1011}
    assert drift([link]) == [link]


def test_removing_a_requires_entry_unlinks_it_and_a_matching_link_is_noop():
    existing = [blocked(7, 11, 12), blocker(11), blocker(12)]
    [unlink] = run_plan(unmet(requires=["alpha"]), existing, NUMBERS)
    assert unlink["action"] == "unlink" and (unlink["blocked_by"], unlink["issue_id"]) == (12, 1012)
    assert [a["action"] for a in run_plan(unmet(requires=["alpha", "beta"]), existing, NUMBERS)] == ["noop"]


def test_an_extra_link_on_github_is_drift_even_with_an_empty_requires():
    [extra] = run_plan(unmet(requires=[]), [blocked(7, 99)], NUMBERS)
    assert extra["action"] == "unlink" and extra["blocked_by"] == 99 and drift([extra])


def test_no_requires_field_leaves_links_and_body_alone():
    assert [a["action"] for a in run_plan(unmet(), [blocked(7, 99)], NUMBERS)] == ["noop"]


def test_unknown_names_and_closed_issues_make_no_link():
    assert [a["action"] for a in run_plan(unmet(requires=["nobody"]), [blocked(7)], NUMBERS)] == ["noop"]
    assert [a["action"] for a in run_plan(unmet(requires=["alpha"]),
                                          [blocked(7, state="closed"), blocker(11)], NUMBERS)] == ["noop"]


def test_a_blocker_missing_from_the_snapshot_is_a_warning_not_a_link():
    [warn] = run_plan(unmet(requires=["alpha"]), [blocked(7)], NUMBERS)
    assert warn["action"] == "warn" and warn["issue"] == 11


# -- the generated "Blocked by" section ----------------------------------------------------

def test_pr_entries_are_a_marked_section_and_never_a_link():
    existing = [{**blocked(7), "body": "Intro.\n<!-- ubiq-goal: demo-goal AC1 -->\n"}]
    [action] = run_plan(unmet(requires=["pr: 21", "pr: 22"]), existing, NUMBERS)
    assert action["action"] == "body"
    new = action["body"]
    assert new.startswith(existing[0]["body"]) and "Blocked by: #21, #22" in new
    assert new.index(BLOCKED_BEGIN) < new.index("#21") < new.index(BLOCKED_END)
    settled = {**existing[0], "body": new}
    assert [a["action"] for a in run_plan(unmet(requires=["pr: 21", "pr: 22"]), [settled], NUMBERS)] == ["noop"]


def test_changing_and_dropping_a_pr_rewrites_only_between_the_markers():
    before = "Top text.\n\n" + BLOCKED_BEGIN + "\nold\n" + BLOCKED_END + "\n\nBottom text.\n"
    changed = set_blocked_by(before, [5])
    assert changed.startswith("Top text.\n\n" + BLOCKED_BEGIN) and "#5" in changed
    assert changed.endswith(BLOCKED_END + "\n\nBottom text.\n")
    assert set_blocked_by(changed, []) == "Top text.\n\nBottom text.\n"


def test_add_then_drop_restores_the_body_and_nothing_to_drop_is_unchanged():
    for body in ("text", "text\n", "a\n\nb\n"):
        assert set_blocked_by(body, []) == body
        assert set_blocked_by(set_blocked_by(body, [3]), []).rstrip("\n") == body.rstrip("\n")


def test_text_that_looks_like_a_marker_outside_the_pair_is_kept():
    body = f"{BLOCKED_BEGIN} unfinished\nstay"
    assert set_blocked_by(body, []) == body


def test_a_new_issue_is_created_with_its_section():
    [create] = run_plan(unmet(requires=["pr: 3"]), [], NUMBERS)
    assert create["action"] == "create" and create["body"].endswith(BLOCKED_END + "\n")


# -- the adapter ----------------------------------------------------------------------------

def test_snapshot_reads_links_only_for_issues_that_have_them():
    page = [{"number": 7, "issue_dependencies_summary": {"blocked_by": 1}},
            {"number": 8, "issue_dependencies_summary": {"blocked_by": 0}}, {"number": 9}]
    fake = Fake({("GET", "?state=all&per_page=100&page=1"): page,
                 ("GET", "/7/dependencies/blocked_by?per_page=100&page=1"):
                     [{"number": 11, "id": 1011, "title": "x"}]})
    found = GitHub("o/r", "t", fake, 0).snapshot()
    assert found[0]["blocked_by"] == [{"number": 11, "id": 1011}]
    assert "blocked_by" not in found[1] and "blocked_by" not in found[2]
    assert len(fake.calls) == 2


def test_apply_posts_and_deletes_links_and_patches_the_body():
    fake = Fake()
    done = []
    actions = [{"action": "link", "issue": 7, "issue_id": 1011},
               {"action": "unlink", "issue": 7, "issue_id": 1012},
               {"action": "body", "issue": 7, "body": "new"}]
    GitHub("o/r", "t", fake, 0).apply(actions, done)
    assert [(m, u, p) for m, u, _t, p in fake.calls] == [
        ("POST", "/7/dependencies/blocked_by", {"issue_id": 1011}),
        ("DELETE", "/7/dependencies/blocked_by/1012", None),
        ("PATCH", "/7", {"body": "new"})]
    assert done == actions


def test_unlinking_an_already_removed_link_is_not_an_error():
    def gone(method, url, token, payload=None):
        raise urllib.error.HTTPError(url, 404, "gone", {}, None)
    done = []
    GitHub("o/r", "t", gone, 0).apply([{"action": "unlink", "issue": 7, "issue_id": 1}], done)
    assert len(done) == 1


# -- from records ---------------------------------------------------------------------------

def write_records(root):
    (root / "goals").mkdir()
    (root / "f").mkdir()
    (root / "f/alpha.md").write_text("---\nname: alpha\nissue: 11\n---\n\nA.\n")
    (root / "f/untracked.md").write_text("---\nname: untracked\n---\n\nU.\n")
    (root / "goals/demo-goal.md").write_text(
        "---\nname: demo-goal\nstatus: proposed\ncriteria:\n  AC1:\n    assessment: unassessed\n"
        "    support: []\n    gap: g\n    requires: [alpha, untracked, 'pr: 30']\n---\n\n1. AC1: First.\n")
    (root / "schema.json").write_text(json.dumps({"type": "object"}))
    (root / "ubiq.yaml").write_text(
        'sync:\n  repo: o/r\n  records:\n    - {glob: "goals/*-goal.md", kind: goal}\n'
        'schemas:\n  - schema: schema.json\n    files: ["f/*.md"]\n    format: frontmatter\n')


def test_records_resolve_names_through_their_issue_and_pr_entries(tmp_path):
    write_records(tmp_path)
    [item] = desired_from_config(load_config(tmp_path))
    assert item.requires == (11,) and item.requires_prs == (30,)


def test_sync_check_reports_the_missing_link_end_to_end(tmp_path, monkeypatch, capsys):
    write_records(tmp_path)
    monkeypatch.setenv("GITHUB_TOKEN", "t")
    fake = Fake({("GET", "?state=all&per_page=100&page=1"): [blocked(7), blocker(11)]})
    args = SimpleNamespace(root=str(tmp_path), repo=None, apply=False, check=True, dry_run=False)
    assert cmd_sync(args, fake, 0) == 1
    assert {a["action"] for a in json.loads(capsys.readouterr().out)} == {"link", "body"}
