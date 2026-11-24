"""Glob discovery must retain matching paths through directory aliases."""

import json
import os

import pytest

from ubiq.cli import main


@pytest.mark.parametrize("reverse", [False, True])
def test_check_finds_matching_directory_alias(tmp_path, capsys, monkeypatch, reverse):
    (tmp_path / "actual").mkdir()
    (tmp_path / "actual/a.md").write_text("[[missing]]\n")
    (tmp_path / "selected").symlink_to(tmp_path / "actual", target_is_directory=True)
    (tmp_path / "ubiq.yaml").write_text(
        'glossary: []\ndocs: ["**/selected/*.md"]\n')
    walk = os.walk

    def ordered_walk(*args, **kwargs):
        for directory, dirs, files in walk(*args, **kwargs):
            dirs.sort(reverse=reverse)
            yield directory, dirs, files

    monkeypatch.setattr(os, "walk", ordered_walk)
    status = main(["check", "--root", str(tmp_path), "--json"])
    result = json.loads(capsys.readouterr().out)
    assert status == 1
    assert [(d["code"], d["file"]) for d in result["diagnostics"]] == [
        ("E002", "actual/a.md")]
