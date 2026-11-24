"""Release versions have one source and updates preserve unrelated metadata."""

import os
import subprocess
import sys
from importlib.metadata import version
from pathlib import Path

import pytest
import yaml

import ubiq


def test_runtime_version_uses_package_metadata(monkeypatch):
    import importlib
    import importlib.metadata

    monkeypatch.setattr(importlib.metadata, "version", lambda name: "9.8.7")
    try:
        assert importlib.reload(ubiq).__version__ == "9.8.7"
    finally:
        monkeypatch.undo()
        importlib.reload(ubiq)
    assert ubiq.__version__ == version("ubiq")


@pytest.mark.parametrize("tag", ["v1.2.3", "1.2.3", "v1.2.3rc1", "v01.2.3", "v1.2.3\nignored"])
@pytest.mark.skipif(sys.version_info < (3, 11), reason="The workflow uses Python 3.12 and tomllib.")
def test_release_version_update(tmp_path, tag):
    workflow = Path(__file__).resolve().parents[1] / ".github/workflows/release-version.yml"
    steps = yaml.safe_load(workflow.read_text())["jobs"]["sync"]["steps"]
    script = next(step["run"] for step in steps if step.get("name") == "Update the package version")
    source = '[project]\nname = "ubiq"\nversion = "0.7.1"\n\n[tool.example]\nvalue = "0.7.1"\n'
    path = tmp_path / "pyproject.toml"
    path.write_text(source)
    result = subprocess.run(
        ["bash", "-c", script.replace("python -", f'"{sys.executable}" -')],
        cwd=tmp_path,
        env={**os.environ, "RELEASE_TAG": tag},
        capture_output=True,
        text=True,
        check=False,
    )
    valid = tag in {"v1.2.3", "1.2.3"}
    assert (result.returncode == 0) == valid, result.stderr
    expected = source.replace('version = "0.7.1"', 'version = "1.2.3"') if valid else source
    assert path.read_text() == expected
