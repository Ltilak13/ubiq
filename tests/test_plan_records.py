"""Plan records: the schema, step `requires` (x-ubiq-ref `within`), and the step sync."""
import json
from pathlib import Path

import pytest
from test_sync import Fake, issue

from ubiq import xref
from ubiq.cli import main
from ubiq.config import load_config
from ubiq.sync import (
    GitHub,
    SyncError,
    desired_from_config,
    drift,
    load_plan,
    plan,
    plan_desired,
)

ROOT = Path(__file__).resolve().parents[1]
PLAN_SCHEMA = (ROOT / ".ubiq/schemas/plan.json").read_text()

# -- the schema and the two repository plans ---------------------------------------


TRACKING = (ROOT / ".ubiq/schemas/tracking.json").read_text()


def test_plan_schema_references_the_tracking_fields_instead_of_copying_them():
    schema = json.loads(PLAN_SCHEMA)
    step = schema["properties"]["steps"]["patternProperties"]["^[a-z0-9]+(-[a-z0-9]+)*$"]
    assert schema["properties"]["status"] == {"$ref": "tracking.json#/properties/status"}
    assert step["properties"]["pr"] == {"$ref": "tracking.json#/properties/pr"}
    assert "$defs" not in schema


def test_step_requires_is_annotated_within_steps():
    found = [a for a in xref.collect(json.loads(PLAN_SCHEMA)) if a.ref.edge == "requires"]
    assert [a.ref for a in found] == [xref.XRef("plan-step", "requires", True, False, "steps")]
    assert found[0].steps[0] == ("key", "steps") and found[0].steps[-1] == ("key", "requires")


def test_within_must_be_a_name():
    with pytest.raises(TypeError):
        xref.parse({"ns": "plan-step", "edge": "requires", "within": 3})


def test_repository_plans_validate(capsys):
    assert main(["check", "--root", str(ROOT), "--json"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["diagnostics"] == []


def test_repository_plans_are_in_the_glossary_namespace_and_sync_records():
    cfg = load_config(ROOT)
    assert any(r.kind == "plan" for r in cfg.sync.records)
    assert {d.ident["plan"] for d in desired_from_config(cfg) if d.kind == "plan-step"} == {"frontmatter-tracking"}


def test_repository_step_requires_resolve_to_issue_numbers():
    steps = {d.ident["step"]: d for d in desired_from_config(load_config(ROOT)) if d.kind == "plan-step"}
    assert steps["requires-links"].requires == (120,)
    assert steps["sync-github"].requires == (70,)  # `goal-issue-hardening` has a pr and no issue


# -- ubiq check over a plan --------------------------------------------------------

PLAN = """---
name: demo
status: active
issue: 10
trunk: main
steps:
  first:
    issue: 11
    requires: []
  second:
    requires: [first]
---

Demo.
"""


def repo(root, text, schema=PLAN_SCHEMA, others=()):
    (root / "schema.json").write_text(schema)
    (root / "tracking.json").write_text(TRACKING)
    (root / "plans").mkdir()
    (root / "plans/demo.md").write_text(text)
    for index, other in enumerate(others):
        (root / f"plans/other-{index}.md").write_text(other)
    (root / "ubiq.yaml").write_text(
        'glossary:\n  - {glob: "plans/*.md", term_field: name, ns: plan}\ndocs: ["plans/*.md"]\n'
        'schemas:\n  - schema: schema.json\n    files: ["plans/*.md"]\n    format: frontmatter\n')


def check(root, capsys):
    status = main(["check", "--root", str(root), "--json"])
    return status, json.loads(capsys.readouterr().out)["diagnostics"]


def test_valid_plan_passes(tmp_path, capsys):
    repo(tmp_path, PLAN)
    status, found = check(tmp_path, capsys)
    assert status == 0 and [d for d in found if d["severity"] == "error"] == []


def test_unknown_step_in_requires_is_e006_at_the_field(tmp_path, capsys):
    repo(tmp_path, PLAN.replace("[first]", "[first, third]"))
    status, found = check(tmp_path, capsys)
    [error] = [d for d in found if d["code"] == "E006"]
    assert status == 1 and "'third'" in error["message"] and error["line"] == 11


def test_requires_does_not_resolve_to_another_plans_step_or_plan_name(tmp_path, capsys):
    repo(tmp_path, PLAN.replace("[first]", "[demo]"))
    _status, found = check(tmp_path, capsys)
    assert [d["code"] for d in found if d["severity"] == "error"] == ["E006"]


OTHER = "---\nname: shared\nstatus: proposed\nissue: 20\ntrunk: main\nsteps:\n  base-step:\n    requires: []\n---\n"


def test_requires_resolves_a_step_of_another_plan_by_its_qualified_name(tmp_path, capsys):
    repo(tmp_path, PLAN.replace("[first]", "[shared/base-step]"), others=[OTHER])
    status, found = check(tmp_path, capsys)
    assert status == 0, found


@pytest.mark.parametrize("value", ["shared/missing", "missing/base-step", "demo/first"])
def test_a_qualified_name_must_name_a_step_of_another_plan(tmp_path, capsys, value):
    repo(tmp_path, PLAN.replace("[first]", f"[{value}]"), others=[OTHER])
    _status, found = check(tmp_path, capsys)
    assert [d["code"] for d in found if d["severity"] == "error"] == ["E006"]


def test_a_step_pr_may_be_one_number_or_a_list(tmp_path, capsys):
    repo(tmp_path, PLAN.replace("    requires: [first]", "    requires: [first]\n    pr: [3, 4]"))
    status, found = check(tmp_path, capsys)
    assert status == 0, found


@pytest.mark.parametrize("old, new", [("status: active", "status: wip"), ("trunk: main\n", ""),
                                      ("    requires: [first]", "    branch: x"),
                                      ("issue: 11", "issue: 0"), ("  first:", "  First:")])
def test_schema_rejects_bad_plans(tmp_path, capsys, old, new):
    repo(tmp_path, PLAN.replace(old, new))
    status, found = check(tmp_path, capsys)
    assert status == 1 and any(d["code"] == "E009" for d in found)


# -- the step sync -----------------------------------------------------------------


def record(**overrides):
    base = {"name": "demo", "path": "plans/demo.md", "status": "active", "issue": 10,
            "steps": {"first": {"issue": 11, "requires": []},
                      "second": {"requires": ["first"], "branch": "b", "base": "a"},
                      "shipped": {"requires": [], "pr": 9}}}
    return {**base, **overrides}


def bot_issue(number, step, state="open"):
    return {**issue(number, state), "body": f"x\n<!-- ubiq-plan: demo {step} -->"}


def plan_parent(*children):
    return {**issue(10), "sub_issues": list(children)}


def test_each_step_is_an_item_with_its_links():
    first, second = plan_desired(record())
    assert (first.kind, first.ident) == ("plan-step", {"plan": "demo", "step": "first"})
    assert first.listed == (11,) and first.parent_issue == 10 and first.requires_markers == ()
    assert second.requires_markers == (first.marker,) and second.marker == "ubiq-plan: demo second"
    assert "`b`" in second.body and "<!-- ubiq-plan: demo second -->" in second.body


def test_step_with_only_a_pr_is_tracked_by_the_pr():
    assert [d.ident["step"] for d in plan_desired(record())] == ["first", "second"]
    steps = record()["steps"] | {"after": {"requires": ["shipped"]}}
    [after] = [d for d in plan_desired(record(steps=steps)) if d.ident["step"] == "after"]
    assert after.requires_markers == ()


def blocked_step(number, *links):
    return {**bot_issue(number, "second" if number == 12 else "first"), "id": 1000 + number,
            "blocked_by": [{"number": n, "id": 1000 + n} for n in links]}


def test_step_requires_become_blocked_by_links_through_fact_requires():
    first, second = plan_desired(record())
    assert first.requires == () and second.requires == (11,)
    issues = [plan_parent(11, 12), {**issue(11), "id": 1011}, {**bot_issue(12, "second"), "id": 1012}]
    [link] = [a for a in plan([first, second], issues) if a["action"] == "link"]
    assert link == {"action": "link", "plan": "demo", "step": "second", "issue": 12,
                    "blocked_by": 11, "issue_id": 1011}
    synced = [plan_parent(11, 12), {**issue(11), "id": 1011}, blocked_step(12, 11)]
    assert {a["action"] for a in plan([first, second], synced)} == {"noop"}


def test_a_hand_added_blocked_by_link_on_a_step_is_drift():
    first, second = plan_desired(record())
    synced = [plan_parent(11, 12), {**issue(11), "id": 1011}, blocked_step(12, 11, 99)]
    [unlink] = [a for a in plan([first, second], synced) if a["action"] == "unlink"]
    assert (unlink["step"], unlink["blocked_by"]) == ("second", 99) and drift([unlink])


def test_a_step_requiring_a_step_of_another_plan_resolves_its_issue():
    steps = {"only": {"issue": 11, "requires": ["other/done"]}}
    [step] = plan_desired(record(steps=steps), step_issues={"other/done": 42, "other/x": 43})
    assert step.requires == (42,)
    [unresolved] = plan_desired(record(steps=steps))
    assert unresolved.requires == ()


def test_step_without_an_issue_is_created_once():
    [noop, create] = plan(plan_desired(record()), [plan_parent(11), issue(11)])
    assert create["action"] == "create" and create["step"] == "second"
    assert "<!-- ubiq-plan: demo second -->" in create["body"] and noop["action"] == "noop"
    assert [a["action"] for a in plan(plan_desired(record()), [plan_parent(11, 12), {**issue(11), "id": 1011},
                                                        blocked_step(12, 11)])] == ["noop", "noop"]


def test_proposed_and_abandoned_plans_mirror_nothing():
    for status in ("proposed", "abandoned"):
        assert plan_desired(record(status=status)) == []


def test_done_plan_closes_open_issues_only():
    found = plan(plan_desired(record(status="done")), [plan_parent(11, 12), issue(11), bot_issue(12, "second", "closed")])
    assert [(a["action"], a.get("issue")) for a in found] == [("close", 11), ("noop", None)]
    assert "ubiq-plan-closed: demo first" in found[0]["comment"]


def test_active_plan_never_closes_or_reopens():
    found = plan(plan_desired(record()), [plan_parent(11, 12), issue(11, "closed"), bot_issue(12, "second", "closed")])
    assert drift(found) == []


def test_apply_creates_the_step_issue():
    fake = Fake({("POST", ""): {"number": 12, "id": 1012}})
    [create] = [a for a in plan(plan_desired(record()), [plan_parent(11), issue(11)]) if a["action"] == "create"]
    GitHub("o/r", "t", fake, 0).apply([create], [])
    assert fake.calls[0][3]["title"] == "demo: second"
    assert fake.calls[1][1] == "/10/sub_issues"
    assert fake.calls[1][3]["sub_issue_id"] == 1012


def test_load_plan_reads_frontmatter_and_rejects_unreadable(tmp_path):
    (tmp_path / "demo.md").write_text(PLAN)
    loaded = load_plan(tmp_path / "demo.md", tmp_path)
    assert loaded["path"] == "demo.md" and loaded["issue"] == 10 and set(loaded["steps"]) == {"first", "second"}
    (tmp_path / "bad.md").write_text("---\nname: bad\n---\n")
    with pytest.raises(SyncError):
        load_plan(tmp_path / "bad.md", tmp_path)
