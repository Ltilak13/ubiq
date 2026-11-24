"""Directory scan failures must not produce a successful check."""

import errno
import json
import os
from pathlib import Path

import pytest

from ubiq.cli import main


@pytest.mark.parametrize("settings", [
    {"docs": ["docs/**/*.md"]},
    {"glossary": ["docs/**/*.md"]},
    {"historical": ["docs/**/*.md"]},
    {"overlays": ["docs/**/*.md"]},
    {"catalogs": [{"file": "catalog.json", "cover": ["docs/**/*.md"]}]},
    {"schemas": [{"schema": "schema.json", "files": ["docs/**/*.md"]}]},
    {"edges": {"install": ["docs/**/*.md"]}},
])
def test_unreadable_directory_fails_check(tmp_path, monkeypatch, capsys, settings):
    docs = tmp_path / 'docs'
    docs.mkdir()
    (docs / 'bad.md').write_text('[[missing]]\n')
    (tmp_path / "ubiq.yaml").write_text(json.dumps({"glossary": [], "docs": [], **settings}))
    (tmp_path / "catalog.json").write_text('{"skills": []}')
    (tmp_path / "schema.json").write_text("{}")
    scandir = os.scandir

    def denied(path):
        if Path(path) == docs:
            raise PermissionError(errno.EACCES, 'Permission denied', str(path))
        return scandir(path)

    monkeypatch.setattr(os, 'scandir', denied)
    status = main(['check', '--root', str(tmp_path), '--json'])
    result = json.loads(capsys.readouterr().out)
    assert status == 1
    assert result['diagnostics'][0]['code'] == 'E005'
    assert result['diagnostics'][0]['file'] == 'docs'
    assert 'Permission denied' in result['diagnostics'][0]['message']


def test_absent_optional_glob_roots_are_not_errors(tmp_path, capsys):
    status = main(['check', '--root', str(tmp_path), '--json'])
    result = json.loads(capsys.readouterr().out)
    assert status == 0 and result['errors'] == 0


@pytest.mark.parametrize("pattern", ["docs/**/*.md", "docs/ignored/**/*.md"])
def test_ignored_unreadable_directory_is_not_scanned(tmp_path, monkeypatch, capsys, pattern):
    ignored = tmp_path / 'docs' / 'ignored'
    ignored.mkdir(parents=True)
    (ignored / 'bad.md').write_text('[[missing]]\n')
    (tmp_path / 'ubiq.yaml').write_text(
        f'glossary: []\ndocs: ["{pattern}"]\nignore: ["docs/ignored/**"]\n')
    scandir = os.scandir

    def denied(path):
        if Path(path) == ignored:
            raise PermissionError(errno.EACCES, 'Permission denied', str(path))
        return scandir(path)

    monkeypatch.setattr(os, 'scandir', denied)
    status = main(['check', '--root', str(tmp_path), '--json'])
    result = json.loads(capsys.readouterr().out)
    assert status == 0 and result['errors'] == 0


@pytest.mark.parametrize('field', ['glossary', 'install'])
def test_unreadable_external_repository_stays_a_warning(tmp_path, monkeypatch, capsys, field):
    project = tmp_path / 'project'
    project.mkdir()
    external = tmp_path / 'external'
    docs = external / 'docs'
    docs.mkdir(parents=True)
    settings = ({'glossary': ['docs/**/*.md']} if field == 'glossary'
                else {'glossary': [], 'edges': {'install': ['docs/**/*.md']}})
    (external / 'ubiq.yaml').write_text(json.dumps(settings))
    (project / 'ubiq.yaml').write_text(
        'glossary: []\ndocs: []\nedges: {external: [../external]}\n')
    scandir = os.scandir

    def denied(path):
        if Path(path) == docs:
            raise PermissionError(errno.EACCES, 'Permission denied', str(path))
        return scandir(path)

    monkeypatch.setattr(os, 'scandir', denied)
    status = main(['check', '--root', str(project), '--json'])
    result = json.loads(capsys.readouterr().out)
    assert status == 0
    assert [d['code'] for d in result['diagnostics']] == ['W004']
    assert 'Permission denied' in result['diagnostics'][0]['message']
