"""The three skills install together without repository-level documentation."""

import shutil
from pathlib import Path

from ubiq.scan import _doc_link_path, _interpret_markdown


def test_installed_skill_documentation_links(tmp_path):
    source = Path(__file__).resolve().parents[1] / "skills"
    installed = tmp_path / "installed"
    for name in ("apply-ubiq", "maintain-ubiq", "upgrade-ubiq"):
        shutil.copytree(source / name, installed / name)

    for document in installed.rglob("*.md"):
        for _, _, link in _interpret_markdown(document.read_text()).links:
            target = _doc_link_path(document, link)
            if target is not None:
                assert target.is_relative_to(installed), (document, link)
                assert target.is_file(), (document, link)
