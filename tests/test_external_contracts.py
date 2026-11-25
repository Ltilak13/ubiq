"""Include contracts use the target repository's configuration."""

import json

import pytest
import yaml
from test_graph import CFG, repo, skill

from ubiq.cli import main


def setup(tmp_path, tail, inputs="options: {mode: [new, existing]}", fragment=""):
    upstream = tmp_path / "upstream"
    upstream.mkdir()
    config = yaml.safe_load(CFG)
    config["glossary"][0]["ns"] = "piece"
    config["edges"]["include"] = {"ns": ["piece"], "inputs": "options"}
    config["edges"]["invoke"] = {"blocked_by": "manual"}
    repo(upstream, {"skills/shared/SKILL.md": skill("shared", "# Contract").replace(
        "name: shared", "name: shared\nmanual: true\n" + inputs)}, yaml.safe_dump(config))
    consumer = tmp_path / "consumer"
    consumer.mkdir()
    config = yaml.safe_load(CFG)
    config["edges"]["external"] = [{"name": "shared", "path": "../upstream", "required": True}]
    repo(consumer, {"skills/local/SKILL.md": skill(
        "local", f"Follow [shared](../shared/SKILL.md{fragment}) {tail}.", uses=["shared/piece:shared"])},
        yaml.safe_dump(config))
    return consumer


@pytest.mark.parametrize("tail, inputs, expected", [
    ("in `new` mode", "options: {mode: [new, existing]}", None),
    ("", "options: {mode: [new, existing]}", "without a mode"),
    ("in `bad` mode", "options: {mode: [new, existing]}", "expected one of"),
    ("in `new` mode", "options: wrong", "expected a mapping"),
])
def test_external_include_contract(tmp_path, capsys, tail, inputs, expected):
    root = setup(tmp_path, tail, inputs)
    status = main(["check", "--root", str(root), "--json"])
    diags = json.loads(capsys.readouterr().out)["diagnostics"]
    assert status == (1 if expected else 0)
    contracts = [d for d in diags if d["code"] == "E012"]
    assert (any(expected in d["message"] for d in contracts) if expected else not contracts)
    assert any(d["code"] == "W003" and "manual: true" in d["message"] for d in diags)


def test_external_fragment_is_checked(tmp_path, capsys):
    root = setup(tmp_path, "in `new` mode", fragment="#absent")
    main(["check", "--root", str(root), "--json"])
    diags = json.loads(capsys.readouterr().out)["diagnostics"]
    assert any(d["code"] == "W004" and "no heading" in d["message"] for d in diags)
