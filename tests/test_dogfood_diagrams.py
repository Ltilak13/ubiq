"""The pilot diagrams stay in sync with their source records."""

import subprocess
import sys
from pathlib import Path


def test_dogfood_diagrams_match_records():
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, str(root / "scripts/dogfood_diagrams.py")],
        cwd=root, capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_dependency_change_requires_regeneration(tmp_path):
    from shutil import copyfile

    root = Path(__file__).resolve().parents[1]
    files = ("scripts/dogfood_diagrams.py", "docs/plans/no-code-dogfood.md",
             "docs/goals/no-code-spec-goal.md")
    for name in files:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        copyfile(root / name, path)

    plan = tmp_path / files[1]
    text = plan.read_text()
    plan.write_text(text.replace("requires: [frontmatter-tracking/mermaid-blocks, cli-spec-slice]", "requires: [cli-spec-slice]"))
    command = [sys.executable, str(tmp_path / files[0])]
    stale = subprocess.run(command, capture_output=True, text=True, check=False)
    assert stale.returncode == 1, stale.stdout + stale.stderr
    assert "no-code-dogfood.md: stale diagram" in stale.stdout
    subprocess.run([*command, "--write"], check=True)
    subprocess.run(command, check=True)
