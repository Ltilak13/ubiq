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


def test_plan_schema_carries_an_exact_copy_of_the_tracking_fragment():
    fragment = json.loads((ROOT / ".ubiq/schemas/tracking.json").read_text())
    schema = json.loads(PLAN_SCHEMA)
    assert schema["$defs"]["tracking"]["properties"] == fragment["properties"]


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


def repo(root, text, schema=PLAN_SCHEMA):
    (root / "schema.json").write_text(schema)
    (root / "plans").mkdir()
    (root / "plans/demo.md").write_text(text)
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


def test_step_without_an_issue_is_created_once():
    [noop, create] = plan(plan_desired(record()), [plan_parent(11), issue(11)])
    assert create["action"] == "create" and create["step"] == "second"
    assert "<!-- ubiq-plan: demo second -->" in create["body"] and noop["action"] == "noop"
    assert [a["action"] for a in plan(plan_desired(record()), [plan_parent(11, 12), issue(11), bot_issue(12, "second")])] \
        == ["noop", "noop"]


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
