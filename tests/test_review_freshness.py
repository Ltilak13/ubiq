"""A met criterion's review goes stale when its cited files change after the reviewed commit."""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import review_freshness

GOAL = """---
name: demo-goal
status: active
criteria:
  AC1:
    assessment: met
    support:
    - feature: demo
      implementation: {{path: src.py, anchor: def run(}}
      check: {{path: test.py, anchor: def test_run(}}
    gap: None.
    review: {{by: R, note: Checked., at: {at}, date: 2026-11-28}}
---
"""


def git(root, *args):
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, check=True).stdout.strip()


def repo(tmp_path):
    git(tmp_path, "init", "-q")
    git(tmp_path, "config", "user.email", "t@example.com")
    git(tmp_path, "config", "user.name", "t")
    (tmp_path / "src.py").write_text("def run(): pass\n")
    (tmp_path / "test.py").write_text("def test_run(): pass\n")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-qm", "base")
    reviewed = git(tmp_path, "rev-parse", "HEAD")
    (tmp_path / "docs/goals").mkdir(parents=True)
    (tmp_path / "docs/goals/demo-goal.md").write_text(GOAL.format(at=reviewed))
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-qm", "record review")
    return tmp_path


def test_review_is_fresh_until_a_cited_file_changes(tmp_path):
    root = repo(tmp_path)
    assert review_freshness.findings(root) == [("demo-goal", "AC1", "fresh", [])]
    (root / "src.py").write_text("def run(): return 1\n")
    git(root, "commit", "-qam", "change")
    assert review_freshness.findings(root) == [("demo-goal", "AC1", "stale", ["src.py"])]
    assert review_freshness.main(["--root", str(root)]) == 0
    assert review_freshness.main(["--root", str(root), "--strict"]) == 1


def test_a_review_commit_missing_from_history_is_unknown(tmp_path):
    root = repo(tmp_path)
    goal = root / "docs/goals/demo-goal.md"
    goal.write_text(GOAL.format(at="b" * 40))
    [(_, _, state, _)] = review_freshness.findings(root)
    assert state == "unknown"


def test_scenario_criteria_carry_no_review_and_are_skipped(tmp_path):
    root = repo(tmp_path)
    goal = root / "docs/goals/demo-goal.md"
    goal.write_text(goal.read_text().replace("criteria:\n", "criteria:\n  AC0:\n    scenario: true\n"))
    assert review_freshness.findings(root) == [("demo-goal", "AC1", "fresh", [])]
