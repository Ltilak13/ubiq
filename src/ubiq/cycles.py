"""`acyclic` from `x-ubiq-ref`: a cycle among records fails `ubiq check` (E013).

A schema property annotated `{"ns": ..., "edge": ..., "acyclic": true}` at the top
of a record (for example a feature's `requires`) makes the edges of that kind among
the records of `ns` a graph that must have no cycle. The check reads the bound
frontmatter files, so it needs no glossary. A nested annotation (a goal criterion's
`requires`) has a source that is not a record of `ns`, so it cannot close a loop.
"""
from __future__ import annotations

from pathlib import Path

import yaml

from . import xref
from .check import Diagnostic
from .globs import GlobError
from .records import FRONTMATTER_RE, normalize
from .schemas import _annotations, load_data

READ_ERRORS = (OSError, UnicodeError, ValueError, TypeError, KeyError, yaml.YAMLError, RecursionError)


def check_cycles(cfg) -> list[Diagnostic]:
    """E013 for each cycle among records through an `acyclic` edge."""
    graphs: dict[tuple[str, str], dict[str, list[str]]] = {}
    where: dict[tuple[str, str], dict[str, tuple[Path, int]]] = {}
    shown: dict[str, str] = {}
    for spec in cfg.schemas:
        if spec.format != "frontmatter":
            continue
        try:
            found = [a for a in _annotations(cfg.root, spec.schema)
                     if a.ref.acyclic and len(a.steps) == 1 and a.steps[0][0] == "key"]
        except READ_ERRORS:
            continue  # an unreadable schema is E008
        if not found:
            continue
        paths: set[Path] = set()
        for pattern in spec.files:
            try:
                paths.update(p for p in pattern.walk(cfg.ignore) if not any(g.matches(p) for g in cfg.ignore))
            except GlobError:
                continue
        for path in sorted(paths):
            try:
                data = load_data(path, frontmatter=True)
                match = FRONTMATTER_RE.match(path.read_text(encoding="utf-8"))
            except READ_ERRORS:
                continue
            name = data.get("name") if isinstance(data, dict) else None
            if not isinstance(name, str) or not name.strip():
                continue
            node = normalize(name)
            shown.setdefault(node, name.strip())
            for annotation in found:
                key = (annotation.ref.ns, annotation.ref.edge)
                targets = [normalize(v) for _, v in xref.values(data, annotation.steps)
                           if xref.pr_entry(v) is None and v.strip()]
                graphs.setdefault(key, {}).setdefault(node, []).extend(targets)
                line = xref.line_of(match.group(1) if match else "", annotation.steps[0][1:2])
                where.setdefault(key, {}).setdefault(node, (path, line))
    diagnostics = []
    for (ns, edge), edges in sorted(graphs.items()):
        for loop in xref.find_cycles(edges):
            file, line = where[(ns, edge)][loop[0]]
            names = " -> ".join(shown.get(n, n) for n in loop)
            diagnostics.append(Diagnostic("E013", f"{edge} cycle: {names}", file, line))
    return diagnostics
