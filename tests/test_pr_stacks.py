"""Pull requests: the stack check and the derived `status: in review` label."""
import json
from types import SimpleNamespace

from test_sync import Fake, goal, issue, unmet

from ubiq.config import load_config
from ubiq.sync import (
    GitHub,
    Stack,
    closing_numbers,
    cmd_sync,
    desired_from_config,
    drift,
    goal_desired,
    plan,
    record_stacks,
    tracked_records,
)


def pull(number, head, base="main", closes=()):
    return {"number": number, "head": head, "base": base, "closes": tuple(closes)}


def labelled(number, *names, **kwargs):
    return {**issue(number, marker="AC1", **kwargs), "labels": [{"name": n} for n in names]}


def run_plan(criterion, existing, pulls, pulls_by_name=None):
    return plan(goal_desired(goal(AC1=criterion), pulls=pulls_by_name), existing, pulls)


# -- the stack check ------------------------------------------------------------------

# The real stack: #116 <- #132 <- #135 <- #145.
STACK = [pull(132, "sync-github", base="main"), pull(135, "tracking-fields", base="sync-github"),
         pull(145, "requires-links", base="tracking-fields")]
PULLS = {"tracking fields": (135,)}
EXISTING = [issue(7, marker="AC1")]


def test_a_pr_that_targets_the_required_records_branch_is_noop():
    found = run_plan(unmet(pr=[145], requires=["tracking-fields"]), EXISTING, STACK, PULLS)
    assert [a["action"] for a in found] == ["noop"]


def test_a_wrong_base_is_a_stack_finding_and_drift():
    pulls = [*STACK[:2], pull(145, "requires-links", base="main")]
    [finding] = run_plan(unmet(pr=[145], requires=["tracking-fields"]), EXISTING, pulls, PULLS)
    assert finding["action"] == "stack"
    assert (finding["pr"], finding["base"], finding["expected"], finding["requires"]) == (
        145, "main", ["tracking-fields"], ["tracking fields"])
    assert finding["goal"] == "demo-goal" and drift([finding]) == [finding]


def test_no_claim_when_the_required_record_has_no_open_pr_or_the_pr_is_not_open():
    merged = [pull(145, "requires-links", base="main")]
    assert [a["action"] for a in run_plan(unmet(pr=[145], requires=["tracking-fields"]), EXISTING, merged, PULLS)] == ["noop"]
    assert [a["action"] for a in run_plan(unmet(pr=[145], requires=["tracking-fields"]), EXISTING, [], PULLS)] == ["noop"]


def test_the_base_may_be_any_open_required_branch_and_pr_entries_are_ignored():
    pulls = [pull(1, "a"), pull(2, "b"), pull(9, "x", base="b")]
    by_name = {"one": (1,), "two": (2,)}
    criterion = unmet(pr=[9], requires=["one", "two", "pr: 40"])
    assert [a for a in run_plan(criterion, EXISTING, pulls, by_name) if a["action"] == "stack"] == []
    [finding] = [a for a in run_plan(criterion, EXISTING, [*pulls[:2], pull(9, "x", base="main")], by_name) if a["action"] == "stack"]
    assert finding["expected"] == ["a", "b"] and finding["requires"] == ["one", "two"]


def test_record_stacks_cover_records_that_mirror_no_issue():
    stack = Stack({"record": "requires-links"}, (145,), (("tracking-fields", (135,)),))
    [finding] = plan([], [], [*STACK[:2], pull(145, "requires-links")], [stack])
    assert finding["action"] == "stack" and finding["record"] == "requires-links"
    assert plan([], [], STACK, [stack]) == []


# -- the in-review label --------------------------------------------------------------

def test_an_open_closing_pr_adds_the_label_and_drops_in_progress_only():
    existing = [labelled(7, "status: in progress", "status: blocked", "bug")]
    [action] = run_plan(unmet(), existing, [pull(30, "w", closes=[7])])
    assert action == {"action": "label", "goal": "demo-goal", "criterion": "AC1", "issue": 7,
                      "add": ["status: in review"], "remove": ["status: in progress"]}
    assert drift([action]) == [action]


def test_the_label_is_removed_when_no_open_pr_closes_the_issue():
    for pulls in ([], [pull(30, "w", closes=[8])]):
        [action] = run_plan(unmet(), [labelled(7, "Status: In Review", "bug")], pulls)
        assert action["add"] == [] and action["remove"] == ["Status: In Review"]
    [closed] = run_plan(unmet(), [labelled(7, "status: in review", state="closed")], [])
    assert closed["remove"] == ["status: in review"]


def test_a_matching_label_state_is_noop_and_a_closed_issue_is_never_labelled():
    pulls = [pull(30, "w", closes=[7])]
    assert [a["action"] for a in run_plan(unmet(), [labelled(7, "status: in review")], pulls)] == ["noop"]
    assert [a["action"] for a in run_plan(unmet(), [labelled(7)], [])] == ["noop"]
    assert [a["action"] for a in run_plan(unmet(), [labelled(7, state="closed")], pulls)] == ["noop"]


def test_untracked_issues_get_and_lose_the_derived_status():
    untracked = issue(8)
    [add] = plan([], [untracked], [pull(30, "w", closes=[8])])
    assert add == {"action": "label", "issue": 8, "add": ["status: in review"], "remove": []}
    [remove] = plan([], [{**untracked, "labels": add["add"]}], [])
    assert remove["remove"] == ["status: in review"]


def test_applying_the_label_plan_converges():
    existing = [labelled(7, "status: in progress")]
    pulls = [pull(30, "w", closes=[7])]
    [action] = run_plan(unmet(), existing, pulls)
    after = [labelled(7, *action["add"])]
    assert [a["action"] for a in run_plan(unmet(), after, pulls)] == ["noop"]


# -- closing keywords and the adapter ---------------------------------------------------

def test_closing_keywords_in_the_body():
    body = "Closes #1, fixes: #2\nResolved #3 and RESOLVES o/r#4, closes x/y#5, see #6, closes #1"
    assert closing_numbers(body, "o/r") == (1, 2, 3, 4)
    assert closing_numbers(None) == ()
    examples = "> fixes #1\n<!-- closes #2 -->\n`fixes #3`\n```\nfixes #4\n```\nCloses #5"
    assert closing_numbers(examples) == (5,)


def test_pulls_reads_open_pull_requests_with_head_base_and_closed_issues():
    page = [{"number": 5, "head": {"ref": "h"}, "base": {"ref": "b"}, "body": "Closes #7"},
            {"number": 6, "head": {"ref": "i"},
             "base": {"ref": "h", "repo": {"default_branch": "main"}}, "body": "Closes #8"}]
    seen = []

    def transport(method, url, token, payload=None):
        seen.append((method, url))
        return page

    found = GitHub("o/r", "t", transport, 0).pulls()
    assert found == [{"number": 5, "head": "h", "base": "b", "closes": (7,)},
                     {"number": 6, "head": "i", "base": "h", "closes": ()}]
    assert seen == [("GET", "https://api.github.com/repos/o/r/pulls?state=open&per_page=100&page=1")]


def test_apply_has_no_handler_for_a_stack_finding():
    done = []
    GitHub("o/r", "t", Fake(), 0).apply([{"action": "stack"}], done)
    assert done == []


# -- records ---------------------------------------------------------------------------

def test_tracked_records_read_pr_and_requires(tmp_path):
    (tmp_path / "ubiq.yaml").write_text(
        "schemas:\n  - files: [\"f/*.md\"]\n    schema: .ubiq/schemas/feature.json\n    format: frontmatter\n")
    schemas = tmp_path / ".ubiq" / "schemas"
    schemas.mkdir(parents=True)
    (schemas / "feature.json").write_text(json.dumps({
        "type": "object", "properties": {"name": {"type": "string"}}}))
    (tmp_path / "f").mkdir()
    (tmp_path / "f" / "a.md").write_text("---\nname: a\nissue: 4\npr: [10, 11]\nrequires: [b, 'pr: 3']\n---\n")
    (tmp_path / "f" / "b.md").write_text("---\nname: b\npr: [9]\n---\n")
    records = tracked_records(load_config(tmp_path))
    assert (records["a"].issue, records["a"].prs, records["a"].requires) == (4, (10, 11), ("b", "pr: 3"))
    [stack] = [s for s in record_stacks(records) if s.ident == {"record": "a"}]
    assert stack.required == (("b", (9,)),)


def test_the_command_dry_run_reports_a_stack_finding(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "t")
    (tmp_path / "ubiq.yaml").write_text(
        "schemas:\n  - files: [\"f/*.md\"]\n    schema: .ubiq/schemas/f.json\n    format: frontmatter\n"
        "sync:\n  repo: o/r\n  records:\n    - {glob: \"g/*-goal.md\", kind: goal}\n")
    (tmp_path / ".ubiq" / "schemas").mkdir(parents=True)
    (tmp_path / ".ubiq" / "schemas" / "f.json").write_text(json.dumps({"type": "object"}))
    (tmp_path / "f").mkdir()
    (tmp_path / "f" / "a.md").write_text("---\nname: a\npr: [2]\nrequires: [b]\n---\n")
    (tmp_path / "f" / "b.md").write_text("---\nname: b\npr: [1]\n---\n")

    def transport(method, url, token, payload=None):
        if "/pulls" in url:
            return [{"number": 1, "head": {"ref": "bb"}, "base": {"ref": "main"}, "body": ""},
                    {"number": 2, "head": {"ref": "aa"}, "base": {"ref": "main"}, "body": ""}]
        return []

    args = SimpleNamespace(root=str(tmp_path), repo=None, apply=False, check=True, ref=None)
    assert cmd_sync(args, transport, 0) == 1
    out = json.loads(capsys.readouterr().out)
    assert [(a["action"], a["record"], a["pr"], a["expected"]) for a in out] == [("stack", "a", 2, ["bb"])]
    args.check = False
    assert cmd_sync(args, transport, 0) == 0
    assert desired_from_config(load_config(tmp_path)) == []
