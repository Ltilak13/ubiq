"""Composition follows each repository's declarations, including diamonds and cycles."""

import json

import yaml
from test_graph import CFG, repo, skill

from ubiq.cli import _composition, build, main


def node(root, name, dependencies=(), uses=(), body="", fields="uses"):
    root.mkdir(exist_ok=True)
    config = yaml.safe_load(CFG)
    config["ref_fields"] = [fields]
    config["edges"]["external"] = [
        {"name": dep, "path": "../" + dep, "required": True} for dep in dependencies]
    repo(root, {f"skills/{name}/SKILL.md": skill(name, body, uses).replace("uses:", fields + ":")},
         yaml.safe_dump(config))


def graph(root, capsys, target):
    assert main(["graph", target, "--callers", "--root", str(root), "--json"]) == 0
    return json.loads(capsys.readouterr().out)


def test_three_repository_chain_uses_source_fields(tmp_path, capsys):
    node(tmp_path / "c", "leaf")
    node(tmp_path / "b", "middle", ["c"], ["c/skill:leaf"], fields="invokes")
    node(tmp_path / "a", "local", ["b"], ["b/skill:middle"])
    root = tmp_path / "a"
    first = graph(root, capsys, "b/c/skill:leaf")
    assert first == graph(root, capsys, "b/c/skill:leaf")
    assert {(e["source"], e["target"]) for e in first["edges"]} == {
        ("skill:local", "b/skill:middle"), ("b/skill:middle", "b/c/skill:leaf")}
    assert first["edges"][0]["file"] == "b/skills/middle/SKILL.md"
    assert main(["refs", "b/c/skill:leaf", "--root", str(root), "--json"]) == 0
    refs = json.loads(capsys.readouterr().out)
    assert refs["count"] == 1
    assert refs["references"][0]["file"] == "b/skills/middle/SKILL.md"


def test_diamond_reuses_record_identity(tmp_path, capsys):
    node(tmp_path / "d", "leaf")
    node(tmp_path / "b", "left", ["d"], ["d/skill:leaf"])
    node(tmp_path / "c", "right", ["d"], ["d/skill:leaf"])
    node(tmp_path / "a", "local", ["b", "c"], ["b/skill:left", "c/skill:right"])
    root = tmp_path / "a"
    built = build(root)
    assert len(_composition(built)) == 4
    assert built.glossary.resolve("b/d/skill:leaf")[0] is built.glossary.resolve("c/d/skill:leaf")[0]
    assert len(graph(root, capsys, "c/d/skill:leaf")["edges"]) == 4


def test_repository_and_invocation_cycles_terminate(tmp_path, capsys):
    node(tmp_path / "a", "local", ["b"], ["b/skill:other"])
    node(tmp_path / "b", "other", ["a"], ["a/skill:local"])
    root = tmp_path / "a"
    assert len(_composition(build(root))) == 2
    assert len(graph(root, capsys, "skill:local")["edges"]) == 2
    assert main(["check", "--root", str(root), "--json"]) == 0
    capsys.readouterr()


def test_cross_repository_include_cycle_fails(tmp_path, capsys):
    node(tmp_path / "a", "local", ["b"], body="[other](../other/SKILL.md)")
    node(tmp_path / "b", "other", ["a"], body="[local](../local/SKILL.md)")
    assert main(["check", "--root", str(tmp_path / "a"), "--json"]) == 1
    assert any(d["code"] == "E011" for d in json.loads(capsys.readouterr().out)["diagnostics"])


def test_transitive_invocation_uses_target_configuration(tmp_path, capsys):
    node(tmp_path / "c", "leaf")
    config_path = tmp_path / "c/ubiq.yaml"
    config = yaml.safe_load(config_path.read_text())
    config["edges"]["invoke"] = {"blocked_by": "manual"}
    config_path.write_text(yaml.safe_dump(config))
    path = tmp_path / "c/skills/leaf/SKILL.md"
    path.write_text(path.read_text().replace("name: leaf", "name: leaf\nmanual: true"))
    node(tmp_path / "b", "middle", ["c"])
    node(tmp_path / "a", "local", ["b"], ["b/c/skill:leaf"])
    assert main(["check", "--root", str(tmp_path / "a"), "--json"]) == 0
    diags = json.loads(capsys.readouterr().out)["diagnostics"]
    assert any(d["code"] == "W003" and "manual: true" in d["message"] for d in diags)
