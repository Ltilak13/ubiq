"""`acyclic` from `x-ubiq-ref`: a cycle among records fails `ubiq check` (E014).

A schema property annotated `{"ns": ..., "edge": ..., "acyclic": true}` at the top
of a record (for example a feature's `requires`) makes the edges of that kind among
the records of `ns` a graph that must have no cycle. The check reads the bound
frontmatter files, so it needs no glossary. A nested annotation (a goal criterion's
`requires`) has a source that is not a record of `ns`, so it cannot close a loop.
"""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import yaml

from . import xref
from .check import Diagnostic
from .globs import GlobError
from .records import FRONTMATTER_RE, Glossary, normalize
from .scan import Ref
from .schemas import _annotations, _in_namespace, load_data

READ_ERRORS = (OSError, UnicodeError, ValueError, TypeError, KeyError, yaml.YAMLError, RecursionError)


def check_cycles(cfg, glossary: Glossary) -> list[Diagnostic]:
    """E014 for each cycle among records through an `acyclic` edge."""
    graphs: dict[tuple[str, str], dict[str, list[str]]] = {}
    where: dict[tuple[str, str], dict[str, tuple[Path, int]]] = {}
    shown: dict[str, str] = {}
    policy = replace(cfg.policies["field"], resolve=_in_namespace)
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
                line = xref.line_of(match.group(1) if match else "", annotation.steps[0][1:2])
                targets = graphs.setdefault(key, {}).setdefault(node, [])
                for _, raw in xref.values(data, annotation.steps):
                    value = raw.strip().strip("'\"")
                    if not value or xref.pr_entry(value) is not None:
                        continue
                    ref = Ref(policy, raw, normalize(value), annotation.ref.ns, path, line, target=value)
                    resolved = ref.resolve(glossary)
                    if len(resolved) == 1:
                        targets.append(resolved[0].term)
                    elif not resolved:
                        targets.append(ref.name)
                where.setdefault(key, {}).setdefault(node, (path, line))
    diagnostics = []
    for (ns, edge), edges in sorted(graphs.items()):
        for loop in xref.find_cycles(edges):
            file, line = where[(ns, edge)][loop[0]]
            names = " -> ".join(shown.get(n, n) for n in loop)
            diagnostics.append(Diagnostic("E014", f"{edge} cycle: {names}", file, line))
    return diagnostics
