"""Candidate terms: names that docs mark as vocabulary but no record defines.

Deterministic and read-only. It reports a signal; deciding which names become
records, aliases, or nothing is the maintain-ubiq skill's job.
"""

from __future__ import annotations

import enum
import re
from collections.abc import Iterable
from difflib import get_close_matches
from pathlib import Path

from .records import Glossary, normalize
from .scan import bold_spans, inline_code

# A whole code span that is a hyphenated lowercase identifier: `ready-for-agent`.
# Paths, flags, and single words are too noisy to report.
IDENTIFIER_RE = re.compile(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)+")
# A whole bold span of one to four words, before a trailing colon or period:
# **Tracer bullet**. Sentences and symbols are emphasis, not names.
BOLD_NAME_RE = re.compile(r"[A-Za-z][A-Za-z0-9]*(?:[ -][A-Za-z0-9]+){0,3}")


class Shape(enum.Flag):
    """Markup that marks a name as possible vocabulary; combine with `|`."""
    CODE = enum.auto()  # `ready-for-agent`
    BOLD = enum.auto()  # **tracer bullet**: opt-in, because many repos bold for emphasis

    @classmethod
    def parse(cls, names: Iterable[str]) -> Shape:
        known = [shape.name.lower() for shape in cls]
        shapes = cls(0)
        for name in names:
            if name not in known:
                near = get_close_matches(name, known, n=1)
                hint = f"; did you mean {near[0]}?" if near else f"; expected {', '.join(known)}"
                raise ValueError(f"unknown shape {name}{hint}")
            shapes |= cls[name.upper()]
        if not shapes:
            raise ValueError("expected at least one shape")
        return shapes


def _code(text: str) -> list[tuple[int, str]]:
    return [(line, name) for line, code in inline_code(text)
            if IDENTIFIER_RE.fullmatch(name := code.strip())]


def _bold(text: str) -> list[tuple[int, str]]:
    return [(line, name) for line, span in bold_spans(text)
            if BOLD_NAME_RE.fullmatch(name := span.rstrip(":."))]


EXTRACTORS = {Shape.CODE: _code, Shape.BOLD: _bold}


def find_candidates(paths: list[Path], glossary: Glossary, min_files: int = 2,
                    shapes: Shape = Shape.CODE) -> list[dict]:
    """Names no term or alias resolves, marked by `shapes` in at least `min_files` docs.

    Spellings that normalize alike are one candidate, named by the first one
    found (by path, then shape). Sorted by file count (descending), then
    normalized name. `locations` lists each (file, line) once; `occurrences`
    counts every use.
    """
    extractors = [extract for shape, extract in EXTRACTORS.items() if shape in shapes]
    spelling: dict[str, str] = {}
    uses: dict[str, list[tuple[Path, int]]] = {}
    for path in sorted(paths):
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            continue
        for extract in extractors:
            for line, name in extract(text):
                if not glossary.resolve(name):
                    key = normalize(name)
                    spelling.setdefault(key, name)
                    uses.setdefault(key, []).append((path, line))
    found = []
    for key, hits in sorted(uses.items()):
        files = {path for path, _ in hits}
        if len(files) >= min_files:
            found.append({"name": spelling[key], "files": len(files), "occurrences": len(hits),
                          "locations": sorted(set(hits), key=lambda h: (str(h[0]), h[1]))})
    return sorted(found, key=lambda c: -c["files"])
