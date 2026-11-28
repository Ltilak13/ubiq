"""Check that a pull request title follows Conventional Commits.

Usage: check_pr_title.py [TITLE]. Without an argument, the title is read from
the PR_TITLE environment variable. Exits 1 when the title does not match.
"""

import os
import re
import sys

TYPES = ("feat", "fix", "docs", "test", "ci", "chore", "refactor", "perf", "build", "style", "revert")
PATTERN = re.compile(
    rf"^(?:{'|'.join(TYPES)})"  # type
    r"(?:\([a-z0-9_/,-]+\))?"  # optional scope
    r"!?"  # optional breaking-change marker
    r": \S.*$"  # description
)


def is_valid(title: str) -> bool:
    """Return whether the title has the form type(optional-scope)!: description."""
    return PATTERN.match(title) is not None


def main(argv: list[str]) -> int:
    title = argv[1] if len(argv) > 1 else os.environ.get("PR_TITLE", "")
    if is_valid(title):
        print(f"PR title follows Conventional Commits: {title}")
        return 0
    print(
        f"PR title does not follow Conventional Commits: {title!r}\n"
        "Expected: type(optional-scope)!: description, for example 'feat(sync): add retries'.\n"
        f"Allowed types: {', '.join(TYPES)}.\n"
        "The scope uses lowercase letters, digits, '-', '_', '/' and ','; '!' marks a breaking change.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
