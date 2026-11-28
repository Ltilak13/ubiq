"""`x-ubiq-ref` with `within`: names that resolve inside the same file.

A plan's steps are keys of its `steps` mapping, not records of their own, so a
step's `requires` cannot resolve through the glossary. An annotation
`{"ns": "plan-step", "edge": "requires", "within": "steps"}` instead requires each
value to be a key of the file's top-level `steps` mapping. A miss is E006 at the
line of the field. These links make no composition edge: the steps are not nodes.

A value `<name>/<key>` names an entry of another file bound to the same schema:
the file whose `name` is `<name>`. A shared step is then defined once, in one plan,
and other plans require it by that qualified name.
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
        loaded: list[tuple[Path, object, str]] = []
        for path in sorted(paths):
            try:
                data = load_data(path, frontmatter=True)
                match = FRONTMATTER_RE.match(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, ValueError, TypeError, yaml.YAMLError, RecursionError):
                continue  # E005 and E009 report it
            loaded.append((path, data, match.group(1) if match else ""))
        for path, data, text in loaded:
            for annotation in annotations:
                ref = annotation.ref
                known = _keys(data, ref.within)
                qualified = {f"{other['name']}/{key}"
                             for _, other, _ in loaded
                             if other is not data and isinstance(other, Mapping)
                             and isinstance(other.get("name"), str)
                             for key in _keys(other, ref.within)}
                for keys, value in xref.values(data, annotation.steps):
                    if value.strip() not in known | qualified:
                        found.append(Diagnostic(
                            "E006", f"{ref.edge}: '{value}' names no entry of {ref.within} "
                                    f"(expected a {ref.ns})", path, xref.line_of(text, keys)))
    return found


def _keys(data: object, within: str) -> set[str]:
    """The keys of the top-level mapping `within` in `data`, or none."""
    names = data.get(within) if isinstance(data, Mapping) else None
    return set(names) if isinstance(names, Mapping) else set()
