"""Feature lifecycle: `status: planned | shipped`, feature issues, and `ubiq plan`."""
import json
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_sync import READ, Fake

from ubiq.cli import main
from ubiq.config import load_config
from ubiq.plan import BUNDLED, PlanError, load_features, order
from ubiq.sync import (
    GitHub,
    cmd_sync,
    desired_from_config,
    drift,
    feature_desired,
    plan,
)

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ('glossary:\n  - {glob: "features/*.md", term_field: name, ns: feature}\n'
          'docs: ["features/*.md"]\nref_fields: [requires]\n'
          'schemas:\n  - schema: ".ubiq/schemas/feature.json"\n    files: ["features/*.md"]\n'
          '    format: frontmatter\n'
          'sync:\n  repo: o/r\n  records:\n    - {glob: "features/*.md", kind: feature}\n')


def record(root, name, status=None, issue=None, requires=(), codes=(), extra=""):
    (root / "features").mkdir(exist_ok=True)
    lines = [f"name: {name}", f"requires: [{', '.join(requires)}]", f"codes: [{', '.join(codes)}]",
             "config: []", "docs: docs/spec.md", f"summary: The {name} feature."]
    if status:
        lines.append(f"status: {status}")
    if issue:
        lines.append(f"issue: {issue}")
    (root / "features" / f"{name}.md").write_text("---\n" + "\n".join(lines) + f"\n{extra}---\n\nBody.\n")


def repo(root):
    (root / ".ubiq" / "schemas").mkdir(parents=True)
    shutil.copy(ROOT / ".ubiq" / "schemas" / "feature.json", root / ".ubiq" / "schemas")
    (root / "ubiq.yaml").write_text(CONFIG)
    return root


def sync_plan(root, existing):
    return plan(desired_from_config(load_config(root)), existing)


def issue(number, state="open", name="beta"):
    return {"number": number, "state": state, "user": {"login": "github-actions[bot]"},
            "body": f"text\n<!-- ubiq-feature: {name} -->"}


# -- sync: a planned feature creates, a shipped one closes ----------------------------

def test_planned_feature_without_an_issue_yields_a_create(tmp_path):
    record(repo(tmp_path), "beta", status="planned")
    [action] = sync_plan(tmp_path, [])
    assert action["action"] == "create" and action["feature"] == "beta"
    assert action["title"] == "beta: The beta feature."
    assert "<!-- ubiq-feature: beta -->" in action["body"]
    assert drift([action]) == [action]


def test_created_issue_is_found_again_by_its_marker(tmp_path):
    record(repo(tmp_path), "beta", status="planned")
    [action] = sync_plan(tmp_path, [])
    again = sync_plan(tmp_path, [{**issue(9), "body": action["body"]}])
    assert [a["action"] for a in again] == ["noop"]


def test_planned_feature_with_an_issue_is_noop(tmp_path):
    record(repo(tmp_path), "beta", status="planned", issue=7)
    found = sync_plan(tmp_path, [{"number": 7, "state": "open", "body": "", "user": {"login": "x"}}])
    assert [a["action"] for a in found] == ["noop"]


def test_marking_it_shipped_yields_a_close_and_never_a_reopen(tmp_path):
    root = repo(tmp_path)
    record(root, "beta", status="shipped", issue=7)
    [close] = sync_plan(root, [{"number": 7, "state": "open", "body": "", "user": {"login": "x"}}])
    assert close["action"] == "close" and close["issue"] == 7 and close["feature"] == "beta"
    assert "shipped" in close["comment"] and "ubiq-feature-closed: beta" in close["comment"]
    closed = {"number": 7, "state": "closed", "body": "", "user": {"login": "x"}}
    assert [a["action"] for a in sync_plan(root, [closed])] == ["noop"]
    record(root, "beta", status="planned", issue=7)  # planned again: still never reopened
    assert [a["action"] for a in sync_plan(root, [closed])] == ["noop"]


def test_shipped_feature_closes_its_marked_issue_and_creates_nothing(tmp_path):
    root = repo(tmp_path)
    record(root, "beta")  # no status: shipped
    assert [a["action"] for a in sync_plan(root, [])] == ["noop"]
    assert [a["action"] for a in sync_plan(root, [issue(3)])] == ["close"]


def test_feature_priority_is_mirrored_as_a_label(tmp_path):
    record(repo(tmp_path), "beta", status="planned", extra="priority: P2\n")
    [action] = sync_plan(tmp_path, [])
    assert action["labels"] == ["priority: P2"]


def test_apply_creates_the_issue_through_the_adapter(tmp_path):
    record(repo(tmp_path), "beta", status="planned")
    [create] = sync_plan(tmp_path, [])
    fake = Fake({("POST", ""): {"number": 42}})
    done = []
    GitHub("o/r", "t", fake, 0).apply([create], done)
    assert done == [create] and create["issue"] == 42


def test_feature_kind_runs_through_the_command(tmp_path, monkeypatch, capsys):
    record(repo(tmp_path), "beta", status="planned")
    monkeypatch.setenv("GITHUB_TOKEN", "t")
    flags = SimpleNamespace(root=str(tmp_path), repo=None, apply=False, check=True, dry_run=False)
    assert cmd_sync(flags, Fake({READ: []}), 0) == 1
    assert json.loads(capsys.readouterr().out)[0]["action"] == "create"


def test_feature_without_a_summary_is_not_readable(tmp_path):
    root = repo(tmp_path)
    (root / "features").mkdir()
    (root / "features" / "bad.md").write_text("---\nname: bad\n---\n\nBody.\n")
    with pytest.raises(Exception, match="not a readable feature"):
        desired_from_config(load_config(root))


def test_feature_desired_defaults_to_shipped():
    [item] = feature_desired({"name": "a", "summary": "s", "path": "f/a.md"})
    assert item.state == "closed" and item.listed == ()


# -- ubiq check: the schema --------------------------------------------------------

def check(root, capsys):
    status = main(["check", "--root", str(root), "--json"])
    return status, {d["code"] for d in json.loads(capsys.readouterr().out)["diagnostics"]}


def test_schema_accepts_planned_shipped_and_no_status(tmp_path, capsys):
    root = repo(tmp_path)
    record(root, "alpha")
    record(root, "beta", status="planned", issue=7, requires=["alpha"], codes=["E999"])
    record(root, "gamma", status="shipped")
    status, codes = check(root, capsys)
    assert status == 0, codes


def test_schema_rejects_an_unknown_status(tmp_path, capsys):
    root = repo(tmp_path)
    record(root, "beta", status="done")
    status, _ = check(root, capsys)
    assert status == 1


# -- ubiq plan -------------------------------------------------------------------

def write(directory, name, status="shipped", requires=()):
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{name}.md").write_text(
        f"---\nname: {name}\nstatus: {status}\nrequires: [{', '.join(requires)}]\ncodes: []\nconfig: []\n"
        f"docs: docs/spec.md\nsummary: {name} summary\n---\n\nBody.\n")


def run_plan(capsys, *argv):
    status = main(["plan", *argv])
    return status, capsys.readouterr().out


def test_plan_leaves_planned_features_out_of_the_order(tmp_path, capsys):
    features = tmp_path / "features"
    write(features, "alpha")
    write(features, "beta", requires=["alpha"])
    write(features, "future", status="planned", requires=["beta"])
    status, out = run_plan(capsys, "--features", str(features), "--json")
    result = json.loads(out)
    assert status == 0
    assert [f["name"] for f in result["features"]] == ["alpha", "beta"]
    assert result["planned"] == ["future"]
    assert "future" not in run_plan(capsys, "--features", str(features))[1]
    nxt = run_plan(capsys, "--features", str(features), "--root", str(tmp_path), "--next", "--json")[1]
    assert "future" not in [f["name"] for f in json.loads(nxt)["features"]]


def test_plan_keeps_positions_of_shipped_features_dense(tmp_path, capsys):
    features = tmp_path / "features"
    write(features, "alpha", status="planned")
    write(features, "beta")
    result = json.loads(run_plan(capsys, "--features", str(features), "--json")[1])
    assert [(f["position"], f["name"]) for f in result["features"]] == [(1, "beta")]


def test_a_shipped_feature_cannot_require_a_planned_one(tmp_path, capsys):
    features = tmp_path / "features"
    write(features, "alpha", status="planned")
    write(features, "beta", requires=["alpha"])
    status, out = run_plan(capsys, "--features", str(features))
    assert status == 1 and "shipped feature beta requires alpha, which is only planned" in out


def test_planned_features_still_detect_cycles(tmp_path):
    features = tmp_path / "features"
    write(features, "a", status="planned", requires=["b"])
    write(features, "b", status="planned", requires=["a"])
    with pytest.raises(PlanError, match="requires cycle"):
        order(load_features(features))


def test_used_cannot_name_a_planned_feature(tmp_path, capsys):
    features = tmp_path / "features"
    write(features, "alpha", status="planned")
    status, out = run_plan(capsys, "--features", str(features), "--used", "alpha", "--next")
    assert status == 1 and "--used names a planned feature: alpha" in out


def test_bad_status_is_a_plan_error(tmp_path):
    features = tmp_path / "features"
    write(features, "alpha", status="done")
    with pytest.raises(PlanError, match="status must be one of"):
        load_features(features)


# -- the records ubiq ships --------------------------------------------------------

def test_restated_values_and_field_links_are_planned_records():
    by_name = {f.name: f for f in load_features(BUNDLED)}
    assert by_name["restated-values"].status == "planned" and by_name["restated-values"].codes == ("W008",)
    assert by_name["field-links"].status == "planned" and by_name["field-links"].codes == ("E013",)
    shipped = {f.name for f in order(by_name.values())}
    assert not shipped & {"restated-values", "field-links"}


def test_every_shipped_record_is_synced_as_a_feature():
    desired = desired_from_config(load_config(ROOT))
    open_ = {d.ident["feature"] for d in desired if d.kind == "feature" and d.state == "open"}
    assert open_ == {"restated-values", "field-links"}
