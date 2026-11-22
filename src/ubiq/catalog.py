"""JSON/YAML catalogs: an inventory of terms that must resolve, and optionally
cover a set of records (every matching record must appear in the inventory).

E006 — catalog entry with no defining record
E007 — a record in `cover` is missing from the catalog
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

import yaml

from .check import Diagnostic, reported
from .kinds import Policy
from .records import Glossary, load_vocabulary_yaml, normalize
from .scan import Ref

if TYPE_CHECKING:
    from .config import CatalogSpec


class CatalogError(ValueError):
    """A catalog file that exists but cannot be read (reported as E005)."""


def _dotted(obj, path: str):
    cur = obj
    for part in path.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def _load(path: Path):
    try:
        text = path.read_text(encoding="utf-8")
        if path.suffix in {".yaml", ".yml"}:
            return load_vocabulary_yaml(text)
        return json.loads(text)
    except (OSError, UnicodeError, json.JSONDecodeError, yaml.YAMLError) as e:
        raise CatalogError(f"invalid catalog: {str(e).splitlines()[0]}") from e


def _term_of(item, mode: str) -> str:
    s = str(item).rstrip("/")
    if mode == "basename":
        return Path(s).name
    return s


def _items(spec: CatalogSpec) -> list:
    items = _dotted(_load(spec.file), spec.items)
    if not isinstance(items, list):
        raise CatalogError(f"catalog '{spec.items}' is not an array")
    return items


def catalog_refs(spec: CatalogSpec, policy: Policy) -> list[Ref]:
    """Each inventory value is a catalog ref that must resolve (E006)."""
    refs: list[Ref] = []
    for i, item in enumerate(_items(spec)):
        # bool is an int: a JSON `true` is not a term.
        if not isinstance(item, (str, int)) or isinstance(item, bool):
            continue
        raw = str(item)
        name = _term_of(raw, spec.term)
        refs.append(Ref(policy, raw, normalize(name), None, spec.file, i + 1,
                        target=name))
    return refs


def catalog_cover_gaps(refs: list[Ref], file: Path, glossary: Glossary,
                       cover_files: set[Path], policy: Policy) -> list[Diagnostic]:
    """E007: a covered record has no uniquely resolving catalog entry."""
    listed: set[int] = set()
    for ref in refs:
        matches = ref.resolve(glossary)
        if len(matches) == 1:
            listed.add(id(matches[0]))
    cover_res = {p.resolve() for p in cover_files}
    diags: list[Diagnostic] = []
    for t in glossary.terms:
        if t.file.resolve() not in cover_res:
            continue
        if id(t) not in listed:
            diags += reported(policy, "E007",
                              f"'{t.qualified}' not listed in catalog {file.name}", file)
    return diags
