"""Qualified references resolve without importing external coverage inventory."""

import json

import pytest
import yaml
from test_graph import CFG, repo, skill

from ubiq.cli import build, main
from ubiq.records import Glossary, Term


def repositories(tmp_path, target="shared-tools/skill:publish", body="[[shared-tools/skill:publish]]"):
    upstream = tmp_path / "upstream"
    upstream.mkdir()
    repo(upstream, {"skills/publish/SKILL.md": skill("publish").replace(
        "name: publish", "name: publish\naliases: [ship]")})
    consumer = tmp_path / "consumer"
    consumer.mkdir()
    config = yaml.safe_load(CFG)
    config["edges"]["external"] = [{"name": "shared-tools", "path": "../upstream", "required": True}]
    repo(consumer, {"skills/local/SKILL.md": skill("local", body, uses=[target]),
                    "skills/publish/SKILL.md": skill("publish")}, yaml.safe_dump(config))
    return consumer, upstream


@pytest.mark.parametrize("target", ["shared-tools/skill:publish", "shared-tools/skill:ship"])
def test_qualified_metadata_alias_and_explicit_refs(tmp_path, capsys, target):
    consumer, _ = repositories(tmp_path, target)
    assert main(["check", "--root", str(consumer), "--json"]) == 0
    capsys.readouterr()
    assert main(["refs", target, "--root", str(consumer), "--json"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["definitions"][0]["qualified"] == "shared-tools/skill:publish"
    assert {r["policy"] for r in result["references"]} == {"field", "wiki"}
    assert main(["graph", target, "--callers", "--root", str(consumer), "--json"]) == 0
    edges = json.loads(capsys.readouterr().out)["edges"]
    assert edges == [{"kind": "invoke", "source": "skill:local", "target": "shared-tools/skill:publish",
                      "file": "skills/local/SKILL.md", "line": 3}]
    assert len(build(consumer).glossary.terms) == 2


def test_unqualified_stays_local(tmp_path):
    consumer, _ = repositories(tmp_path, "publish")
    built = build(consumer)
    assert built.glossary.resolve("publish")[0].repository is None
    assert built.glossary.resolve("ship") == []


def test_missing_optional_explicit_reference_fails(tmp_path, capsys):
    consumer, upstream = repositories(tmp_path)
    config = yaml.safe_load((consumer / "ubiq.yaml").read_text())
    config["edges"]["external"][0]["required"] = False
    (consumer / "ubiq.yaml").write_text(yaml.safe_dump(config))
    upstream.rename(tmp_path / "absent")
    assert main(["check", "--root", str(consumer), "--json"]) == 1
    result = json.loads(capsys.readouterr().out)
    assert {d["code"] for d in result["diagnostics"]} >= {"E002", "E006"}


def test_dependency_names_are_exact_and_local_slash_names_keep_working(tmp_path):
    glossary = Glossary()
    first, second = Glossary(), Glossary()
    first.add(Term("first", "skill", tmp_path / "first.md"))
    second.add(Term("second", "skill", tmp_path / "second.md"))
    glossary.add_external("shared-tools", first)
    glossary.add_external("shared--tools", second)
    assert glossary.resolve("shared-tools/skill:first") == first.terms
    assert glossary.resolve("shared-tools/skill:second") == []
    assert glossary.resolve("shared--tools/skill:second") == second.terms
    literal = Term("foo/bar:baz", "core", tmp_path / "literal.md")
    namespaced = Term("baz", "foo/bar", tmp_path / "namespace.md")
    glossary.add(literal)
    assert glossary.resolve("foo/bar:baz") == [literal]
    glossary.add(namespaced)
    assert glossary.resolve("foo/bar:baz") == [namespaced]
