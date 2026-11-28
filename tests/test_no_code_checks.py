"""The no-code checks sample passes ubiq check, and ubiq check can fail it."""
import shutil
from pathlib import Path

from ubiq.cli import main

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / 'examples/no-code-checks'


def test_sample_passes_ubiq_check(capsys):
    assert main(['check', '--root', str(SAMPLE)]) == 0
    assert '0 errors, 0 warnings' in capsys.readouterr().out


def test_sample_fails_ubiq_check_on_invalid_frontmatter(tmp_path, capsys):
    copy = tmp_path / 'sample'
    shutil.copytree(SAMPLE, copy, ignore=shutil.ignore_patterns('node_modules'))
    spec = copy / 'specs/reservation.md'
    spec.write_text(spec.read_text().replace('status: accepted', 'status: unknown'))
    assert main(['check', '--root', str(copy)]) == 1
    assert 'reservation.md' in capsys.readouterr().out


def test_sample_fails_ubiq_check_on_broken_link(tmp_path, capsys):
    copy = tmp_path / 'sample'
    shutil.copytree(SAMPLE, copy, ignore=shutil.ignore_patterns('node_modules'))
    readme = copy / 'README.md'
    readme.write_text(readme.read_text().replace('specs/reservation.md', 'specs/missing.md'))
    assert main(['check', '--root', str(copy)]) == 1
    capsys.readouterr()
