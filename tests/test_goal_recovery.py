"""Recover a disposable copy of the accepted policy/goal corpus without data loss."""

import hashlib
import json
import shutil
from pathlib import Path

from test_goal_governance import GOAL, MODEL, ROOT
from test_query import run

from ubiq.cli import main
from ubiq.schemas import load_data


def copy_repository(source, target):
    shutil.copytree(source, target, symlinks=True, ignore=shutil.ignore_patterns(
        '.git', '.venv', '.pytest_cache', '.mypy_cache', '.ruff_cache',
        '__pycache__', 'node_modules', '.claude', '*.egg-info'))


def test_recovery_copy_preserves_dangling_symlinks(tmp_path):
    source = tmp_path / 'source'
    source.mkdir()
    (source / 'tool').symlink_to('missing-tool')
    target = tmp_path / 'copy'
    copy_repository(source, target)
    assert (target / 'tool').is_symlink()
    assert (target / 'tool').readlink() == Path('missing-tool')


def test_goal_evidence_repair_and_rollback(tmp_path, capsys):
    root = tmp_path / 'repository'
    copy_repository(ROOT, root)
    source = Path('docs/goals/domain-schema-goal.md')
    originals = {path: (ROOT / path).read_bytes() for path in (source, Path(MODEL))}

    def check():
        code = main(['check', '--root', str(root), '--json'])
        return code, json.loads(capsys.readouterr().out)

    baseline_check = check()
    baseline_query = run(root, capsys, '--domain', 'goal-assessment')
    assert baseline_check[0] == baseline_query[0] == 0
    assert baseline_check[1]['diagnostics'] == []
    baseline_records = [item['record'] for item in baseline_query[1]['results']]
    assert len(baseline_records) == 2

    # Reject an unreviewed candidate and restore it before trying an accepted edit.
    (root / source).write_bytes(originals[source] + b'\nUnreviewed completion claim.\n')
    code, result = check()
    assert code == 1
    assert any(d['code'] == 'E010' and 'evidence drift' in d['message']
               for d in result['diagnostics'])
    code, result = run(root, capsys, '--id', GOAL)
    assert code == 0 and result['results'][0]['evidence_status'] == 'stale'
    (root / source).write_bytes(originals[source])
    assert check() == baseline_check
    assert run(root, capsys, '--domain', 'goal-assessment') == baseline_query

    # This fixture accepts only a blank-line edit: no words, anchors, or criteria change.
    candidate = originals[source] + b'\n'
    assert candidate.split() == originals[source].split()
    (root / source).write_bytes(candidate)
    assert check()[0] == 1
    before = load_data(root / MODEL)
    old_digest = hashlib.sha256(originals[source]).hexdigest()
    new_digest = hashlib.sha256(candidate).hexdigest()
    model_bytes = originals[Path(MODEL)]
    assert model_bytes.count(old_digest.encode()) == 1
    (root / MODEL).write_bytes(model_bytes.replace(old_digest.encode(), new_digest.encode()))
    after = load_data(root / MODEL)
    before['goals'][0]['evidence'][0]['sha256'] = new_digest
    assert after == before
    assert check()[0] == 0
    code, result = run(root, capsys, '--id', GOAL)
    assert code == 0 and result['results'][0]['evidence_status'] == 'fresh'
    assert result['results'][0]['record']['id'] == GOAL

    # Roll back the accepted edit and its snapshot together, byte for byte.
    for path, contents in originals.items():
        (root / path).write_bytes(contents)
    assert check() == baseline_check
    assert run(root, capsys, '--domain', 'goal-assessment') == baseline_query
    for path, contents in originals.items():
        assert (root / path).read_bytes() == contents
        assert (ROOT / path).read_bytes() == contents
