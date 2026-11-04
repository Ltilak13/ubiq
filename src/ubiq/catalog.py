"""JSON/YAML catalogs: an inventory of terms that must resolve, and optionally
cover a set of records (every matching record must appear in the inventory).

E006 — catalog entry with no defining record
E007 — a record in `cover` is missing from the catalog
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from .check import Diagnostic
from .records import Glossary, normalize
from .scan import Ref


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
    text = path.read_text(encoding="utf-8")
    try:
        if path.suffix in {".yaml", ".yml"}:
            return yaml.safe_load(text)
        return json.loads(text)
    except (json.JSONDecodeError, yaml.YAMLError) as e:
        raise CatalogError(f"invalid catalog: {str(e).splitlines()[0]}") from e


def _term_of(item, mode: str) -> str:
    s = str(item).rstrip("/")
    if mode == "basename":
        return Path(s).name
    return s


def _items(spec: dict, file: Path) -> list:
    data = _load(file)
    key = spec.get("items") or "skills"
    items = _dotted(data, key)
    if not isinstance(items, list):
        raise CatalogError(f"catalog '{key}' is not an array")
    return items


def catalog_refs(spec: dict, file: Path) -> list[Ref]:
    """Each inventory value is a catalog ref that must resolve (E006)."""
    mode = spec.get("term") or "basename"
    refs: list[Ref] = []
    for i, item in enumerate(_items(spec, file)):
        if not isinstance(item, (str, int)):
            continue
        raw = str(item)
        name = _term_of(raw, mode)
        refs.append(Ref("catalog", raw, normalize(name), None, file, i + 1,
                        target=name))
    return refs


def catalog_cover_gaps(spec: dict, file: Path, glossary: Glossary,
                       cover_files: set[Path]) -> list[Diagnostic]:
    """E007: a record whose file is in `cover` is not listed in the catalog."""
    mode = spec.get("term") or "basename"
    listed = {normalize(_term_of(str(i), mode))
              for i in _items(spec, file) if isinstance(i, (str, int))}
    cover_res = {p.resolve() for p in cover_files}
    diags: list[Diagnostic] = []
    for t in glossary.terms:
        if t.file.resolve() not in cover_res:
            continue
        if t.term not in listed and not any(a in listed for a in t.aliases):
            diags.append(Diagnostic(
                "E007",
                f"'{t.qualified}' not listed in catalog {file.name}",
                file))
    return diags
