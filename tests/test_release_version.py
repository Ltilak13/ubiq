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


@pytest.mark.parametrize("bump, expected_version", [("patch", "0.7.2"), ("minor", "0.8.0"),
                                                   ("major", "1.0.0"), ("invalid", None)])
@pytest.mark.skipif(sys.version_info < (3, 11), reason="The workflow uses Python 3.12 and tomllib.")
def test_release_version_update(tmp_path, bump, expected_version):
    workflow = Path(__file__).resolve().parents[1] / ".github/workflows/release-version.yml"
    steps = yaml.safe_load(workflow.read_text())["jobs"]["release"]["steps"]
    script = next(step["run"] for step in steps if step.get("name") == "Update the package version")
    source = '[project]\nname = "ubiq"\nversion = "0.7.1"\n\n[tool.example]\nvalue = "0.7.1"\n'
    path = tmp_path / "pyproject.toml"
    path.write_text(source)
    subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True)
    _git(tmp_path, "add", "pyproject.toml")
    _git(tmp_path, "-c", "user.name=Test", "-c", "user.email=test@example.invalid",
         "commit", "-m", "Initial")
    result = subprocess.run(
        ["bash", "-c", script.replace("python -", f'"{sys.executable}" -')],
        cwd=tmp_path,
        env={**os.environ, "RELEASE_BUMP": bump, "RELEASE_BASE_SHA": "HEAD", "GITHUB_OUTPUT": str(tmp_path / "output")},
        capture_output=True,
        text=True,
        check=False,
    )
    valid = expected_version is not None
    assert (result.returncode == 0) == valid, result.stderr
    expected = source.replace('version = "0.7.1"', f'version = "{expected_version}"') if valid else source
    assert path.read_text() == expected


def _git(root, *args):
    return subprocess.check_output(['git', '-C', str(root), *args], text=True).strip()


def _release_repo(tmp_path):
    remote = tmp_path / 'remote.git'
    subprocess.run(['git', 'init', '--bare', str(remote)], check=True, capture_output=True)
    repo = tmp_path / 'repo'
    subprocess.run(['git', 'init', '-b', 'main', str(repo)], check=True, capture_output=True)
    _git(repo, 'config', 'user.name', 'Release test')
    _git(repo, 'config', 'user.email', 'release@example.invalid')
    (repo / 'pyproject.toml').write_text('[project]\nname = "ubiq"\nversion = "0.7.3"\n')
    _git(repo, 'add', 'pyproject.toml')
    _git(repo, 'commit', '-m', 'Initial version')
    _git(repo, 'remote', 'add', 'origin', str(remote))
    _git(repo, 'push', '-u', 'origin', 'main')
    binaries = tmp_path / 'bin'
    binaries.mkdir()
    gh = binaries / 'gh'
    gh.write_text('#!/bin/sh\n'
                  'if [ "$1" = api ]; then echo 1; exit 0; fi\n'
                  'if [ "$2" = view ]; then exit 1; fi\n'
                  'printf "%s\\n" "$*" >> "$GH_LOG"\n')
    gh.chmod(0o755)
    env = {**os.environ, 'PATH': f'{binaries}{os.pathsep}{os.environ["PATH"]}',
           'RELEASE_TAG': 'v0.7.4', 'RELEASE_BUMP': 'patch',
           'RELEASE_BASE_SHA': _git(repo, 'rev-parse', 'HEAD'), 'DEFAULT_BRANCH': 'main',
           'GH_REPO': 'example/ubiq', 'GH_LOG': str(tmp_path / 'gh.log'),
           'GITHUB_OUTPUT': str(tmp_path / 'output'), 'RUNNER_TEMP': str(tmp_path)}
    return repo, remote, env


def _release_step(repo, env, prefix):
    workflow = Path(__file__).resolve().parents[1] / '.github/workflows/release-version.yml'
    jobs = yaml.safe_load(workflow.read_text())['jobs']
    steps = next(iter(jobs.values()))['steps']
    step = next(s for s in steps if s.get('name', '').startswith(prefix))
    script = step['run'].replace('python -', f'"{sys.executable}" -')
    return subprocess.run(['bash', '-e', '-o', 'pipefail', '-c', script], cwd=repo,
                          env=env, capture_output=True, text=True, check=False)


@pytest.mark.skipif(sys.version_info < (3, 11), reason='The workflow uses Python 3.12 and tomllib.')
def test_release_tags_the_version_commit_before_publication(tmp_path):
    repo, remote, env = _release_repo(tmp_path)
    original = _git(repo, 'rev-parse', 'HEAD')
    for prefix in ('Update the package version', 'Commit and push'):
        result = _release_step(repo, env, prefix)
        assert result.returncode == 0, result.stderr
    tagged = _git(remote, 'rev-parse', 'refs/tags/v0.7.4^{commit}')
    assert tagged == _git(remote, 'rev-parse', 'refs/heads/main')
    assert tagged != original
    assert 'version = "0.7.4"' in _git(remote, 'show', f'{tagged}:pyproject.toml')
    result = _release_step(repo, env, 'Publish GitHub release')
    assert result.returncode == 0, result.stderr
    assert 'release create v0.7.4 --verify-tag' in Path(env['GH_LOG']).read_text()


@pytest.mark.skipif(sys.version_info < (3, 11), reason='The workflow uses Python 3.12 and tomllib.')
def test_release_retry_keeps_existing_tag_and_newer_main(tmp_path):
    repo, remote, env = _release_repo(tmp_path)
    for prefix in ('Update the package version', 'Commit and push'):
        result = _release_step(repo, env, prefix)
        assert result.returncode == 0, result.stderr
    tagged = _git(remote, 'rev-parse', 'refs/tags/v0.7.4')
    (repo / 'next.md').write_text('Next change\n')
    _git(repo, 'add', 'next.md')
    _git(repo, 'commit', '-m', 'Next change')
    _git(repo, 'push', 'origin', 'main')
    newer = _git(remote, 'rev-parse', 'main')
    result = _release_step(repo, env, 'Update the package version')
    assert result.returncode == 0, result.stderr
    assert Path(env['GITHUB_OUTPUT']).read_text().endswith('existing=true\n')
    assert _git(repo, 'rev-parse', 'HEAD') == tagged
    assert _git(remote, 'rev-parse', 'main') == newer
    assert _git(remote, 'rev-parse', 'refs/tags/v0.7.4') == tagged
    result = _release_step(repo, env, 'Publish GitHub release')
    assert result.returncode == 0, result.stderr
    assert 'release create v0.7.4 --verify-tag' in Path(env['GH_LOG']).read_text()


@pytest.mark.skipif(sys.version_info < (3, 11), reason='The workflow uses Python 3.12 and tomllib.')
def test_release_rejects_a_tag_with_wrong_package_version(tmp_path):
    repo, remote, env = _release_repo(tmp_path)
    original = _git(repo, 'rev-parse', 'HEAD')
    _git(repo, 'tag', 'v0.7.4')
    _git(repo, 'push', 'origin', 'refs/tags/v0.7.4')
    result = _release_step(repo, env, 'Update the package version')
    assert result.returncode != 0
    assert 'Refusing to move' in result.stderr
    assert _git(remote, 'rev-parse', 'refs/tags/v0.7.4') == original
    assert _git(repo, 'status', '--porcelain') == ''


@pytest.mark.skipif(sys.version_info < (3, 11), reason='The workflow uses Python 3.12 and tomllib.')
def test_release_does_not_push_tag_when_main_advances(tmp_path):
    repo, remote, env = _release_repo(tmp_path)
    result = _release_step(repo, env, 'Update the package version')
    assert result.returncode == 0, result.stderr
    other = tmp_path / 'other'
    subprocess.run(['git', 'clone', '--branch', 'main', str(remote), str(other)],
                   check=True, capture_output=True)
    _git(other, 'config', 'user.name', 'Release test')
    _git(other, 'config', 'user.email', 'release@example.invalid')
    (other / 'new.md').write_text('Concurrent update\n')
    _git(other, 'add', 'new.md')
    _git(other, 'commit', '-m', 'Concurrent update')
    _git(other, 'push', 'origin', 'main')
    advanced = _git(remote, 'rev-parse', 'main')
    result = _release_step(repo, env, 'Commit and push')
    assert result.returncode != 0
    assert _git(remote, 'rev-parse', 'main') == advanced
    assert _git(remote, 'tag', '--list', 'v0.7.4') == ''
    assert not Path(env['GH_LOG']).exists()


@pytest.mark.parametrize("messages, expected", [
    (["fix(parser): handle empty input"], "0.7.4"),
    (["fix: bug", "feat: option", "fix: another bug"], "0.8.0"),
    (["feat!: remove old API", "fix: bug"], "1.0.0"),
    (["refactor(api)!: remove old API"], "1.0.0"),
    (["chore: cleanup\n\nBREAKING CHANGE: remove old API"], "1.0.0"),
    (["fix: cleanup\n\nBREAKING-CHANGE: remove old API"], "1.0.0"),
    (["FEAT(parser): option"], "0.8.0"),
    (["docs: clarify usage", "ci: checks", "ordinary commit"], None),
    ([], None),
])
@pytest.mark.skipif(sys.version_info < (3, 11), reason="Requires tomllib.")
def test_conventional_commit_selection(tmp_path, messages, expected):
    repo, _, env = _release_repo(tmp_path)
    _git(repo, "tag", "v0.7.3")
    for message in messages:
        _git(repo, "commit", "--allow-empty", "-m", message)
    env.update(RELEASE_BUMP="auto", RELEASE_TAG="", RELEASE_BASE_SHA=_git(repo, "rev-parse", "HEAD"))
    result = _release_step(repo, env, "Update the package version")
    assert result.returncode == 0, result.stderr
    output = Path(env["GITHUB_OUTPUT"]).read_text()
    if expected:
        assert f"tag=v{expected}\n" in output
        assert f'version = "{expected}"' in (repo / "pyproject.toml").read_text()
    else:
        assert output == "release=false\n"
        assert _git(repo, "status", "--porcelain") == ""


@pytest.mark.parametrize("requested, valid", [
    ("v1.2.3", True), ("1.2.3", True), ("v01.2.3", False),
    ("1.2.3rc1", False), ("1.2.3\nignored", False), ("0.7.2", False),
])
@pytest.mark.skipif(sys.version_info < (3, 11), reason="Requires tomllib.")
def test_exact_version_override(tmp_path, requested, valid):
    repo, _, env = _release_repo(tmp_path)
    # Exact versions take precedence, including when auto has no baseline tag.
    env.update(RELEASE_TAG=requested, RELEASE_BUMP="auto")
    result = _release_step(repo, env, "Update the package version")
    assert (result.returncode == 0) == valid, result.stderr
    if valid:
        assert "tag=v1.2.3\n" in Path(env["GITHUB_OUTPUT"]).read_text()
    else:
        assert _git(repo, "status", "--porcelain") == ""


@pytest.mark.skipif(sys.version_info < (3, 11), reason="Requires tomllib.")
def test_auto_retry_uses_dispatch_commit(tmp_path):
    repo, remote, env = _release_repo(tmp_path)
    _git(repo, "tag", "v0.7.3")
    _git(repo, "commit", "--allow-empty", "-m", "fix: regression")
    env.update(RELEASE_BUMP="auto", RELEASE_TAG="", RELEASE_BASE_SHA=_git(repo, "rev-parse", "HEAD"))
    result = _release_step(repo, env, "Update the package version")
    assert result.returncode == 0, result.stderr
    env["RELEASE_TAG"] = "v0.7.4"
    result = _release_step(repo, env, "Commit and push")
    assert result.returncode == 0, result.stderr
    tagged = _git(remote, "rev-parse", "refs/tags/v0.7.4")
    _git(repo, "commit", "--allow-empty", "-m", "feat!: next release")
    env["RELEASE_TAG"] = ""
    result = _release_step(repo, env, "Update the package version")
    assert result.returncode == 0, result.stderr
    assert _git(repo, "rev-parse", "HEAD") == tagged
    assert Path(env["GITHUB_OUTPUT"]).read_text().endswith("tag=v0.7.4\nexisting=true\n")


def test_release_inputs_and_skip_conditions():
    workflow = Path(__file__).resolve().parents[1] / ".github/workflows/release-version.yml"
    config = yaml.safe_load(workflow.read_text())
    inputs = config[True]["workflow_dispatch"]["inputs"]
    assert set(inputs) == {"bump", "version"}
    assert inputs["bump"]["default"] == "auto"
    assert inputs["bump"]["options"] == ["auto", "patch", "minor", "major"]
    steps = config["jobs"]["release"]["steps"]
    for name in ("Validate the release", "Commit and push", "Publish GitHub release"):
        step = next(step for step in steps if step.get("name", "").startswith(name))
        assert "steps.version.outputs.release == 'true'" in step["if"]
