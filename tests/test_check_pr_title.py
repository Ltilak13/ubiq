"""Pull request titles must follow Conventional Commits."""

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "check_pr_title.py"
_spec = importlib.util.spec_from_file_location("check_pr_title", SCRIPT)
assert _spec is not None and _spec.loader is not None
check_pr_title = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(check_pr_title)


@pytest.mark.parametrize("title", [
    "ci: require conventional commit pull request titles",
    "feat(sync): add retries",
    "feat!: drop Python 3.9",
    "fix(cli)!: rename the --strict flag",
    "docs(skills/upgrade-ubiq): describe pins",
    "chore(release,ci): bump to 0.8.0",
    "test(goals): Cover uppercase descriptions",
    "revert: feat(sync): add retries",
])
def test_valid_titles(title):
    assert check_pr_title.is_valid(title)


@pytest.mark.parametrize("title", [
    "",
    "add retries to sync",  # no type
    "feature: add retries",  # unknown type
    "feat:add retries",  # missing space after colon
    "feat: ",  # empty description
    "feat:",  # empty description
    "Feat: add retries",  # uppercase type
    "feat(Sync): add retries",  # uppercase scope
    "feat(): add retries",  # empty scope
    "feat!!: add retries",  # doubled breaking marker
    "feat !: add retries",  # space before marker
])
def test_invalid_titles(title):
    assert not check_pr_title.is_valid(title)


def run(args, env_title=None):
    env = {k: v for k, v in os.environ.items() if k != "PR_TITLE"}
    if env_title is not None:
        env["PR_TITLE"] = env_title
    return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True,
                          env=env, check=False)


def test_cli_reads_title_from_environment():
    assert run([], env_title="fix(sync): handle empty files").returncode == 0
    result = run([], env_title="Update stuff")
    assert result.returncode == 1
    assert "type(optional-scope)!: description" in result.stderr
    assert "feat, fix, docs, test, ci, chore, refactor, perf, build, style, revert" in result.stderr


def test_cli_argument_takes_precedence():
    assert run(["docs: explain the check"], env_title="bad title").returncode == 0
    assert run(["bad title"], env_title="docs: explain the check").returncode == 1


def test_cli_rejects_missing_title():
    assert run([]).returncode == 1
