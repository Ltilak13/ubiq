"""Candidate terms: backticked identifiers used across docs with no record.

Deterministic and read-only. It reports a signal; deciding which names become
records, aliases, or nothing is the maintain-ubiq skill's job.
"""

from __future__ import annotations

import re
from pathlib import Path

from .records import Glossary
from .scan import inline_code

# A whole code span that is a hyphenated lowercase identifier: `ready-for-agent`.
# Paths, flags, and single words are too noisy to report.
IDENTIFIER_RE = re.compile(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)+")


def find_candidates(paths: list[Path], glossary: Glossary,
                    min_files: int = 2) -> list[dict]:
    """Identifiers no term or alias resolves, used in at least `min_files` docs.

    Sorted by file count (descending), then name. `locations` lists each
    (file, line) once; `occurrences` counts every use.
    """
    uses: dict[str, list[tuple[Path, int]]] = {}
    for path in sorted(paths):
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            continue
        for line, code in inline_code(text):
            name = code.strip()
            if IDENTIFIER_RE.fullmatch(name) and not glossary.resolve(name):
                uses.setdefault(name, []).append((path, line))
    found = []
    for name, hits in uses.items():
        files = {path for path, _ in hits}
        if len(files) >= min_files:
            found.append({"name": name, "files": len(files), "occurrences": len(hits),
                          "locations": sorted(set(hits), key=lambda h: (str(h[0]), h[1]))})
    return sorted(found, key=lambda c: (-c["files"], c["name"]))
