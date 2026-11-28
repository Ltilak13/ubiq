"""Report `met` goal criteria whose cited evidence changed after their review.

A `review` records the commit the reviewer checked (`at`). When a file that the
criterion cites in `support` (an `implementation` or a `check`) differs between
that commit and HEAD, the review is stale: the criterion needs reassessment.
A review whose commit is not in the local history is reported as unknown.

The report is advisory. `--strict` exits 1 when any review is stale or unknown.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from ubiq.schemas import load_data

ROOT = Path(__file__).resolve().parents[1]


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, check=False)


def findings(root: Path) -> list[tuple[str, str, str, list[str]]]:
    """(goal, criterion, state, changed paths) for each `met` criterion; state is fresh, stale, or unknown."""
    found = []
    for path in sorted((root / "docs/goals").glob("*-goal.md")):
        goal = load_data(path, frontmatter=True)
        for ac, criterion in goal["criteria"].items():
            review = criterion.get("review")
            if criterion.get("assessment") != "met" or not review:
                continue
            cited = sorted({s[kind]["path"] for s in criterion["support"] for kind in ("implementation", "check")})
            if _git(root, "cat-file", "-e", f"{review['at']}^{{commit}}").returncode:
                found.append((goal["name"], ac, "unknown", cited))
                continue
            diff = _git(root, "diff", "--name-only", review["at"], "HEAD", "--", *cited)
            changed = [line for line in diff.stdout.splitlines() if line]
            found.append((goal["name"], ac, "stale" if changed else "fresh", changed))
    return found


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--strict", action="store_true", help="exit 1 when a review is stale or unknown")
    args = parser.parse_args(argv)
    results = findings(args.root)
    for goal, ac, state, paths in results:
        detail = f": {', '.join(paths)}" if state == "stale" else (" (commit not in history)" if state == "unknown" else "")
        print(f"{goal} {ac}: {state}{detail}")
    if not results:
        print("no met criteria")
    return 1 if args.strict and any(state != "fresh" for _, _, state, _ in results) else 0


if __name__ == "__main__":
    sys.exit(main())
