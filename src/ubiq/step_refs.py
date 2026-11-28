"""`x-ubiq-ref` with `within`: names that resolve inside the same file.

A plan's steps are keys of its `steps` mapping, not records of their own, so a
step's `requires` cannot resolve through the glossary. An annotation
`{"ns": "plan-step", "edge": "requires", "within": "steps"}` instead requires each
value to be a key of the file's top-level `steps` mapping. A miss is E006 at the
line of the field. These links make no composition edge: the steps are not nodes.
"""
from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

import yaml

from . import xref
from .check import Diagnostic
from .globs import GlobError
from .records import FRONTMATTER_RE
from .schemas import _annotations, load_data


def within_diagnostics(cfg) -> list[Diagnostic]:
    """E006 for each `within` value that is not a key of its mapping, in every bound frontmatter file."""
    found: list[Diagnostic] = []
    for spec in cfg.schemas:
        try:
            annotations = [a for a in _annotations(cfg.root, spec.schema) if a.ref.within]
        except (OSError, UnicodeError, ValueError, TypeError, KeyError, yaml.YAMLError, RecursionError):
            continue  # an unreadable schema is E008
        if not annotations or spec.format != "frontmatter":
            continue
        paths: set[Path] = set()
        for pattern in spec.files:
            try:
                paths.update(p for p in pattern.walk(cfg.ignore)
                             if not any(g.matches(p) for g in cfg.ignore))
            except GlobError:
                continue
        for path in sorted(paths):
            try:
                data = load_data(path, frontmatter=True)
                match = FRONTMATTER_RE.match(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, ValueError, TypeError, yaml.YAMLError, RecursionError):
                continue  # E005 and E009 report it
            text = match.group(1) if match else ""
            for annotation in annotations:
                ref = annotation.ref
                names = data.get(ref.within) if isinstance(data, Mapping) else None
                known = set(names) if isinstance(names, Mapping) else set()
                for keys, value in xref.values(data, annotation.steps):
                    if value.strip() not in known:
                        found.append(Diagnostic(
                            "E006", f"{ref.edge}: '{value}' names no entry of {ref.within} "
                                    f"(expected a {ref.ns})", path, xref.line_of(text, keys)))
    return found


def step_cycle_diagnostics(cfg) -> list[Diagnostic]:
    """E014 for each `acyclic` loop among the steps of one plan file.

    Each file is its own graph, so equal step names in different plans never join.
    The message names every step on the loop with its line; the diagnostic sits at
    the first step.
    """
    found: list[Diagnostic] = []
    for spec in cfg.schemas:
        try:
            annotations = [a for a in _annotations(cfg.root, spec.schema) if a.ref.within and a.ref.acyclic]
        except (OSError, UnicodeError, ValueError, TypeError, KeyError, yaml.YAMLError, RecursionError):
            continue  # an unreadable schema is E008
        if not annotations or spec.format != "frontmatter":
            continue
        paths: set[Path] = set()
        for pattern in spec.files:
            try:
                paths.update(p for p in pattern.walk(cfg.ignore)
                             if not any(g.matches(p) for g in cfg.ignore))
            except GlobError:
                continue
        for path in sorted(paths):
            try:
                data = load_data(path, frontmatter=True)
                match = FRONTMATTER_RE.match(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, ValueError, TypeError, yaml.YAMLError, RecursionError):
                continue  # E005 and E009 report it
            text = match.group(1) if match else ""
            for annotation in annotations:
                ref = annotation.ref
                members = data.get(ref.within) if isinstance(data, Mapping) else None
                if not isinstance(members, Mapping):
                    continue
                edges: dict[str, list[str]] = {}
                for keys, value in xref.values(data, annotation.steps):
                    # keys are (within, step, ...); a value naming no step is E006, not an edge
                    if len(keys) > 1 and value.strip() in members:
                        edges.setdefault(keys[1], []).append(value.strip())
                for loop in xref.find_cycles(edges):
                    lines = {n: xref.line_of(text, (ref.within, n)) for n in loop}
                    names = " -> ".join(f"{n} (line {lines[n]})" for n in loop)
                    found.append(Diagnostic("E014", f"{ref.edge} cycle: {names}", path, lines[loop[0]]))
    return found
