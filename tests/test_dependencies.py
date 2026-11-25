"""Named dependency declarations and read-only checkout validation."""

import subprocess

import pytest
import yaml

from ubiq.cli import _layout
from ubiq.config import InvalidConfig, load_config


def git(root, *args):
    return subprocess.check_output(["git", "-C", str(root), *args], text=True).strip()


def configure(root, declarations):
    root.mkdir(exist_ok=True)
    (root / "ubiq.yaml").write_text(yaml.safe_dump({"edges": {"external": declarations}}))
    return load_config(root)


@pytest.mark.parametrize("entry, message", [
    ({"name": "shared", "path": "../shared"}, "required"),
    ({"name": "shared", "path": "../shared", "required": "yes"}, "required"),
    ({"name": "a/b", "path": "../shared", "required": True}, "name"),
    ({"name": "shared", "path": "../shared", "required": True, "revision": "main"}, "SHA"),
    ({"name": "shared", "path": "../shared", "required": True, "typo": 1}, "typo"),
    (12, "path"),
])
def test_malformed_declarations(tmp_path, entry, message):
    with pytest.raises(InvalidConfig, match=message):
        configure(tmp_path, [entry])


def test_duplicate_names(tmp_path):
    entry = {"name": "shared", "path": "../shared", "required": True}
    with pytest.raises(InvalidConfig, match="duplicate"):
        configure(tmp_path, [entry, entry])


def test_required_optional_and_legacy_absence(tmp_path):
    entry = {"name": "shared", "path": "absent", "required": True}
    with pytest.raises(InvalidConfig, match="shared.*not found"):
        _layout(configure(tmp_path, [entry]))
    assert not _layout(configure(tmp_path, [{**entry, "required": False}])).partial
    assert _layout(configure(tmp_path, ["absent"])).partial


def test_optional_present_invalid_fails(tmp_path):
    other = tmp_path / "shared"
    other.mkdir()
    (other / "ubiq.yaml").write_text("glossary: 12")
    with pytest.raises(InvalidConfig, match="shared"):
        _layout(configure(tmp_path, [{"name": "shared", "path": "shared", "required": False}]))


def test_pins_and_dirty_inputs(tmp_path):
    other = tmp_path / "shared"
    other.mkdir()
    (other / "glossary").mkdir()
    record = other / "glossary/part.md"
    record.write_text("---\nterm: part\n---\n")
    git(other, "init", "-q")
    git(other, "add", "glossary/part.md")
    git(other, "-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "-qm", "initial")
    sha = git(other, "rev-parse", "HEAD")
    entry = {"name": "stable", "path": "shared", "revision": sha, "required": True}
    assert _layout(configure(tmp_path, [entry])).repositories[0].name == "stable"
    with pytest.raises(InvalidConfig, match="revision mismatch"):
        _layout(configure(tmp_path, [{**entry, "revision": "0" * 40}]))
    record.write_text("---\nterm: changed\n---\n")
    with pytest.raises(InvalidConfig, match="dirty.*glossary/part.md"):
        _layout(configure(tmp_path, [entry]))
    git(other, "checkout", "--", "glossary/part.md")
    (other / "glossary/new.md").write_text("---\nterm: new\n---\n")
    with pytest.raises(InvalidConfig, match="dirty.*glossary/new.md"):
        _layout(configure(tmp_path, [entry]))
    (other / "glossary/new.md").unlink()
    (other / "unrelated.txt").write_text("unrelated")
    other.rename(tmp_path / "relocated")
    assert _layout(configure(tmp_path, [{**entry, "path": "relocated"}])).repositories


@pytest.mark.parametrize("mode", ["symlink", "ignored", "subdirectory", "linked"])
def test_dirty_pin_boundary_cases(tmp_path, mode):
    other = tmp_path / "shared"
    other.mkdir()
    git(other, "init", "-q")
    root = other / "nested" if mode == "subdirectory" else other
    root.mkdir(exist_ok=True)
    (root / "glossary").mkdir()
    record = root / "glossary/part.md"
    record.write_text("---\nterm: part\n---\n")
    (root / ".gitignore").write_text("glossary/new.md\n")
    (root / "README.md").write_text("[extra](extra.md)\n")
    (root / "extra.md").write_text("Original\n")
    git(other, "add", ".")
    git(other, "-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "-qm", "initial")
    sha = git(other, "rev-parse", "HEAD")
    if mode == "symlink":
        (tmp_path / "alias").symlink_to(root, target_is_directory=True)
        root = tmp_path / "alias"
    if mode == "ignored":
        (root / "glossary/new.md").write_text("---\nterm: new\n---\n")
    elif mode == "linked":
        (root / "extra.md").write_text("Changed\n")
    else:
        record.write_text("---\nterm: changed\n---\n")
    entry = {"name": "shared", "path": str(root), "required": True, "revision": sha}
    with pytest.raises(InvalidConfig, match="dirty"):
        _layout(configure(tmp_path, [entry]))


def test_pinned_installed_inputs_cannot_leave_checkout(tmp_path):
    other = tmp_path / "shared"
    other.mkdir()
    (tmp_path / "outside.md").write_text("outside")
    (other / "ubiq.yaml").write_text("glossary: []\ndocs: []\nedges:\n  install: ['../outside.md']\n")
    git(other, "init", "-q")
    git(other, "add", "ubiq.yaml")
    git(other, "-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "-qm", "initial")
    entry = {"name": "shared", "path": "shared", "required": True,
             "revision": git(other, "rev-parse", "HEAD")}
    with pytest.raises(InvalidConfig, match="leave checkout"):
        _layout(configure(tmp_path, [entry]))
