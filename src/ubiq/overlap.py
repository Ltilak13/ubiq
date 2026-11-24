"""Near-duplicate prose across records: candidates for a shared part.

Each live doc that a record owns (see graph.owners) splits into blocks:
paragraphs, or single lines for one-sentence-per-line prose. Blocks compare by
word shingles across different owners, and similar blocks join one cluster.
Advisory only: it never fails the check and never writes.
"""
from __future__ import annotations

import re
from collections import defaultdict
from itertools import combinations
from pathlib import Path

from .graph import Edge
from .scan import (
    FRONTMATTER_RE,
    _blank,
    _blank_fences,
    _doc_link_path,
    _interpret_markdown,
)

SHINGLE = 4
# A short block fully inside a longer one is a restatement even when Jaccard
# is low, so containment has its own bar.
CONTAINMENT = 0.8
# Shingles shared by more blocks than this are boilerplate, not evidence.
COMMON = 40
LIST_MARK = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")
LINK_TARGET = re.compile(r"\]\([^)]*\)")


def _blocks(text: str, unit: str):
    fm = FRONTMATTER_RE.match(text)
    if fm:
        text = _blank(fm.group()) + text[fm.end():]
    buf: list[str] = []
    start = 0
    for i, line in enumerate(_blank_fences(text).splitlines(), 1):
        if not line.strip() or line.lstrip().startswith("#"):
            if buf:
                yield start, " ".join(buf)
            buf = []
            continue
        if not buf:
            start = i
        buf.append(line.strip())
        if unit == "line":
            yield start, buf.pop()
    if buf:
        yield start, " ".join(buf)


def _words(block: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", LIST_MARK.sub("", LINK_TARGET.sub("]", block)).lower())


def _without_includes(path: Path, text: str, parts: set[Path]) -> str:
    """Blank links to shared parts: an include is the call, not repeated prose,
    so callers of one part are not near-duplicates of each other."""
    for start, end, spec in _interpret_markdown(text).links:
        dest = _doc_link_path(path, spec)
        if dest is not None and dest.resolve() in parts:
            text = text[:start] + _blank(text[start:end]) + text[end:]
    return text


def find_overlap(docs: list[Path], owner, edges: list[Edge], similarity: float = 0.5,
                 unit: str = "paragraph", min_words: int | None = None,
                 parts: set[Path] = frozenset()) -> list[dict]:
    if min_words is None:
        min_words = 7 if unit == "line" else 10
    units = []  # (owner, path, line, text, shingles)
    for path in docs:
        term = owner(path)
        if term is None:
            continue
        text = path.read_text(encoding="utf-8")
        for line, block in _blocks(_without_includes(path, text, parts) if parts else text, unit):
            words = _words(block)
            if len(words) >= min_words:
                grams = {tuple(words[i:i + SHINGLE]) for i in range(len(words) - SHINGLE + 1)}
                units.append((term, path, line, block, grams))

    index: dict[tuple, set[int]] = defaultdict(set)
    for n, u in enumerate(units):
        for g in u[4]:
            index[g].add(n)
    pairs = {(a, b) for ids in index.values() if 1 < len(ids) <= COMMON
             for a, b in combinations(sorted(ids), 2) if units[a][0] is not units[b][0]}

    parent = list(range(len(units)))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    linked: set[int] = set()
    for a, b in sorted(pairs):
        sa, sb = units[a][4], units[b][4]
        shared = len(sa & sb)
        if shared / len(sa | sb) >= similarity or shared / min(len(sa), len(sb)) >= CONTAINMENT:
            parent[find(a)] = find(b)
            linked.update((a, b))

    groups: dict[int, list[int]] = defaultdict(list)
    for n in sorted(linked):
        groups[find(n)].append(n)
    # One cluster per set of records: two skills that share ten lines are one
    # finding, not ten.
    by_records: dict[tuple, list[int]] = defaultdict(list)
    for members in groups.values():
        key = tuple(sorted({units[n][0].qualified for n in members}))
        by_records[key].extend(members)
    includes = {(id(e.source), id(e.target)) for e in edges if e.kind == "include"}
    clusters = []
    for members in by_records.values():
        members.sort(key=lambda n: (str(units[n][1]), units[n][2]))
        owners = list({id(units[n][0]): units[n][0] for n in members}.values())
        # The strongest signal: a record restates a part it already includes.
        restates = any((id(a), id(b)) in includes for a in owners for b in owners)
        clusters.append({
            "records": sorted(t.qualified for t in owners),
            "restates_include": restates,
            "blocks": [{"record": units[n][0].qualified, "file": units[n][1],
                        "line": units[n][2], "text": units[n][3]} for n in members],
        })
    clusters.sort(key=lambda c: (-len(c["records"]), -len(c["blocks"]), c["records"]))
    return clusters
