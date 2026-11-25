"""Pinned `ubiq overlap` results for the two repositories surveyed for the
composable knowledge goal (docs/goals/composable-knowledge-goal.md).

mattpocock/skills is vendored (MIT) under fixtures/mattpocock-skills at the
surveyed commit, so CI pins its clusters, text included. The personal skill
repository is not vendored: its test reads the surveyed commit through git,
pins only records and locations, and skips where the repository is absent.
"""

import io
import json
import os
import subprocess
import tarfile
from pathlib import Path
from unittest import SkipTest

from ubiq.cli import main

FIXTURES = Path(__file__).parent / "fixtures"
UNITS = ("paragraph", "line")
PERSONAL = os.environ.get("UBIQ_SURVEY_PERSONAL", "~/ai")
PERSONAL_COMMIT = "f32c791fe2bef61a30b9c681cbdc6a9ed4537b43"


def overlap(root, unit, capsys):
    assert main(["overlap", "--root", str(root), "--unit", unit, "--json"]) == 0
    return json.loads(capsys.readouterr().out)


def test_public_collection_overlap_is_pinned(capsys):
    root = FIXTURES / "mattpocock-skills"
    for unit in UNITS:
        pinned = json.loads((root / f"overlap-{unit}.json").read_text(encoding="utf-8"))
        assert overlap(root, unit, capsys) == pinned
        assert overlap(root, unit, capsys) == pinned  # same input, same clusters


def locations(report):
    return [{"records": c["records"], "restates_include": c["restates_include"],
             "blocks": [f"{b['file']}:{b['line']}" for b in c["blocks"]]}
            for c in report["clusters"]]


def test_personal_repository_overlap_is_pinned(tmp_path, capsys):
    repo = Path(os.path.expanduser(PERSONAL))
    found = subprocess.run(["git", "-C", str(repo), "cat-file", "-e", f"{PERSONAL_COMMIT}^{{commit}}"],
                           capture_output=True, check=False)
    if found.returncode:
        raise SkipTest(f"surveyed commit {PERSONAL_COMMIT[:7]} not in {repo} (set UBIQ_SURVEY_PERSONAL)")
    data = subprocess.run(["git", "-C", str(repo), "archive", PERSONAL_COMMIT],
                          capture_output=True, check=True).stdout
    with tarfile.open(fileobj=io.BytesIO(data)) as archive:
        # Symlinked skills point at other checkouts whose text moves on; the
        # pinned input is this commit's own files.
        members = [m for m in archive.getmembers() if m.isfile() or m.isdir()]
        extra = {"filter": "data"} if hasattr(tarfile, "data_filter") else {}
        archive.extractall(tmp_path, members=members, **extra)
    pinned = json.loads((FIXTURES / "survey-personal.json").read_text(encoding="utf-8"))
    for unit in UNITS:
        assert locations(overlap(tmp_path, unit, capsys)) == pinned[unit]
