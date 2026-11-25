"""The three skills install together without repository-level documentation."""

import shutil
from pathlib import Path

from ubiq.scan import _doc_link_path, _interpret_markdown


def test_installed_skill_documentation_links(tmp_path):
    source = Path(__file__).resolve().parents[1] / "skills"
    installed = tmp_path / "installed"
    for name in ("apply-ubiq", "maintain-ubiq", "upgrade-ubiq", "references"):
        shutil.copytree(source / name, installed / name)

    for document in installed.rglob("*.md"):
        for _, _, link in _interpret_markdown(document.read_text(encoding="utf-8")).links:
            target = _doc_link_path(document, link)
            if target is not None:
                assert target.is_relative_to(installed), (document, link)
                assert target.is_file(), (document, link)


def test_skills_link_bundled_skills_by_file():
    """Bundled skills name each other with a SKILL.md link, which readers can click."""
    source = Path(__file__).resolve().parents[1] / "skills"
    for document in source.rglob("*.md"):
        assert "[[skill:" not in document.read_text(encoding="utf-8"), document
