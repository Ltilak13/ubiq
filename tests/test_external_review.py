"""Historical review reads exact dependency commits without touching checkouts."""

import json

import pytest
import yaml
from test_dependencies import git
from test_external_traversal import node

from ubiq.cli import _layout, main
from ubiq.config import InvalidConfig, load_config


def commit(root):
    git(root, "add", ".")
    git(root, "-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "-qm", "snapshot")
    return git(root, "rev-parse", "HEAD")


def pin(root, sha):
    path = root / "ubiq.yaml"
    config = yaml.safe_load(path.read_text())
    config["edges"]["external"][0]["revision"] = sha
    path.write_text(yaml.safe_dump(config))


def setup(tmp_path):
    upstream, consumer = tmp_path / "shared", tmp_path / "consumer"
    node(upstream, "leaf")
    git(upstream, "init", "-q")
    old = commit(upstream)
    node(consumer, "local", ["shared"], ["shared/skill:leaf"])
    pin(consumer, old)
    git(consumer, "init", "-q")
    commit(consumer)
    return consumer, upstream


def run(root, capsys, command):
    status = main([command, "--since", "HEAD", "--root", str(root), "--json"])
    return status, json.loads(capsys.readouterr().out)


def test_pin_upgrade_reports_local_callers_and_preserves_checkout(tmp_path, capsys):
    consumer, upstream = setup(tmp_path)
    leaf = upstream / "skills/leaf/SKILL.md"
    leaf.write_text(leaf.read_text() + "Updated behavior.\n")
    new = commit(upstream)
    pin(consumer, new)
    before = (git(upstream, "rev-parse", "HEAD"), leaf.read_bytes(), git(upstream, "status", "--porcelain"))
    status, report = run(consumer, capsys, "impact")
    assert status == 0 and report["complete"]
    assert report["changed"] == [{"record": "shared/skill:leaf", "change": "dependency", "files": ["ubiq.yaml"]}]
    assert [row["record"] for row in report["affected"]] == ["skill:local"]
    assert before == (git(upstream, "rev-parse", "HEAD"), leaf.read_bytes(), git(upstream, "status", "--porcelain"))
    status, report = run(consumer, capsys, "compare")
    assert status == 0 and report["status"] == "ok"
    assert report["counts"]["new"] == 0


def test_missing_historical_commit_is_explicit(tmp_path, capsys):
    consumer, upstream = setup(tmp_path)
    pin(consumer, "0" * 40)
    commit(consumer)
    pin(consumer, git(upstream, "rev-parse", "HEAD"))
    status, report = run(consumer, capsys, "impact")
    assert status == 0 and not report["complete"]
    assert any("unavailable" in gap["reason"] for gap in report["incomplete"])
    status, report = run(consumer, capsys, "compare")
    assert status == 2 and report["status"] == "unavailable"


def test_old_dependency_edges_remain_available(tmp_path, capsys):
    consumer, upstream = setup(tmp_path)
    # Remove the old target from the upgraded dependency. Its baseline callers still matter.
    old = upstream / "skills/leaf/SKILL.md"
    old.unlink()
    (upstream / "README.md").write_text("No leaf in this revision.\n")
    pin(consumer, commit(upstream))
    status, report = run(consumer, capsys, "impact")
    assert status == 0 and report["complete"]
    assert [row["record"] for row in report["affected"]] == ["skill:local"]
    assert report["affected"][0]["via"][0]["side"] == "baseline"


def test_compare_uses_old_target_policy(tmp_path, capsys):
    consumer, upstream = setup(tmp_path)
    leaf = upstream / "skills/leaf/SKILL.md"
    leaf.write_text(leaf.read_text().replace("name: leaf", "name: leaf\ndisable-model-invocation: true"))
    pin(consumer, commit(upstream))
    status, report = run(consumer, capsys, "compare")
    assert status == 0 and report["status"] == "ok"
    assert any(item["code"] == "W003" for item in report["new"])
    assert not any(item["code"] == "W003" for item in report["unchanged"])


def test_transitive_pin_upgrade_reaches_local_caller(tmp_path, capsys):
    leaf, middle, consumer = (tmp_path / name for name in ("leaf", "middle", "consumer"))
    node(leaf, "leaf")
    git(leaf, "init", "-q")
    old = commit(leaf)
    node(middle, "middle", ["leaf"], ["leaf/skill:leaf"])
    pin(middle, old)
    git(middle, "init", "-q")
    old_middle = commit(middle)
    node(consumer, "local", ["middle"], ["middle/skill:middle"])
    pin(consumer, old_middle)
    git(consumer, "init", "-q")
    commit(consumer)
    path = leaf / "skills/leaf/SKILL.md"
    path.write_text(path.read_text() + "Updated.\n")
    pin(middle, commit(leaf))
    pin(consumer, commit(middle))
    status, report = run(consumer, capsys, "impact")
    assert status == 0 and report["complete"]
    assert [item["record"] for item in report["affected"]] == ["skill:local"]
    assert any(item["record"] == "middle/leaf/skill:leaf" for item in report["changed"])


def test_adding_unpinned_dependency_reports_new_callers(tmp_path, capsys):
    upstream, consumer = tmp_path / "shared", tmp_path / "consumer"
    node(upstream, "leaf")
    node(consumer, "local", uses=["shared/skill:leaf"])
    git(consumer, "init", "-q")
    commit(consumer)
    path = consumer / "ubiq.yaml"
    config = yaml.safe_load(path.read_text())
    config["edges"]["external"] = [{"name": "shared", "path": "../shared", "required": True}]
    path.write_text(yaml.safe_dump(config))
    status, report = run(consumer, capsys, "impact")
    assert status == 0 and report["complete"]
    assert [item["record"] for item in report["affected"]] == ["skill:local"]


def test_missing_transitive_legacy_dependency_is_incomplete(tmp_path, capsys):
    consumer, upstream = setup(tmp_path)
    path = upstream / "ubiq.yaml"
    config = yaml.safe_load(path.read_text())
    config["edges"]["external"] = ["../absent"]
    path.write_text(yaml.safe_dump(config))
    pin(consumer, commit(upstream))
    commit(consumer)
    status, report = run(consumer, capsys, "impact")
    assert status == 0 and not report["complete"]
    assert any("absent" in item["file"] for item in report["incomplete"])


def test_staged_rename_cannot_hide_dirty_pinned_input(tmp_path):
    consumer, upstream = setup(tmp_path)
    git(upstream, "mv", "skills/leaf/SKILL.md", "unrelated.txt")
    with pytest.raises(InvalidConfig, match="dirty.*skills/leaf/SKILL.md"):
        _layout(load_config(consumer))
