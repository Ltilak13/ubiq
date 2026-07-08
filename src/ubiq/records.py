"""Glossary record parsing.

A glossary record is a markdown file with YAML frontmatter defining exactly one term:

    ---
    term: glossary record
    ns: core            # namespace (default "core")
    aliases: [record]   # optional alternate spellings
    id: UB-1            # optional short ID (requirement-style)
    ---

    The definition lives in the body.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n?", re.DOTALL)

DEFAULT_NS = "core"


class InvalidRecord(ValueError):
    """A glossary record that exists but cannot be parsed (reported as E005)."""


@dataclass
class Term:
    term: str
    ns: str
    file: Path
    aliases: list[str] = field(default_factory=list)
    id: str | None = None
    definition: str = ""

    @property
    def qualified(self) -> str:
        return f"{self.ns}:{self.term}"

    def names(self) -> list[str]:
        # dedupe: an alias that normalizes to the term itself isn't a second claim
        return list(dict.fromkeys([self.term, *self.aliases]))


def normalize(name: str) -> str:
    """Canonical form for matching: lowercase, collapsed whitespace/hyphens."""
    return re.sub(r"[\s_-]+", " ", name.strip().lower())


def _parse_lenient(raw: str) -> dict:
    """Line-based `key: value` fallback for frontmatter dialects that aren't strict
    YAML (bare colons or quotes inside titles, etc.). Handles scalars and [a, b] lists."""
    data: dict = {}
    for line in raw.splitlines():
        m = re.match(r"^([A-Za-z0-9_]+):\s*(.*)$", line)
        if not m:
            continue
        k, v = m.group(1), m.group(2).strip()
        if v.startswith("[") and v.endswith("]"):
            data[k] = [x.strip().strip("'\"") for x in v[1:-1].split(",") if x.strip()]
        else:
            if len(v) >= 2 and v[0] == v[-1] and v[0] in "'\"":
                v = v[1:-1]
            data[k] = v
    return data


def parse_record(path: Path, term_fields: tuple[str, ...] = ("term",),
                 lenient: bool = False) -> Term | None:
    """Parse a glossary record. Returns None if no term field is present.

    `term_fields` lets existing repos keep their schema: e.g. ("name", "title")
    treats `name:` (falling back to `title:`) as the term.
    """
    text = path.read_text(encoding="utf-8")
    m = FRONTMATTER_RE.match(text)
    if not m:
        return None
    try:
        meta = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError as e:
        if lenient:
            meta = _parse_lenient(m.group(1))
        else:
            raise InvalidRecord(
                f"invalid YAML frontmatter: {str(e).splitlines()[0]}") from e
    field_name = next((f for f in term_fields
                       if isinstance(meta, dict) and meta.get(f)), None)
    if field_name is None:
        return None
    aliases = meta.get("aliases") or []
    if isinstance(aliases, str):
        aliases = [aliases]
    return Term(
        term=normalize(str(meta[field_name])),
        ns=normalize(str(meta.get("ns", DEFAULT_NS))),
        file=path,
        aliases=[normalize(str(a)) for a in aliases],
        id=str(meta["id"]) if meta.get("id") is not None else None,
        definition=text[m.end():].strip(),
    )


@dataclass
class Glossary:
    terms: list[Term] = field(default_factory=list)
    # normalized name -> list of Terms that claim it (canonical or alias)
    by_name: dict[str, list[Term]] = field(default_factory=dict)
    by_id: dict[str, list[Term]] = field(default_factory=dict)
    invalid: list[tuple[Path, str]] = field(default_factory=list)  # unparseable records

    def add(self, t: Term) -> None:
        self.terms.append(t)
        for name in t.names():
            self.by_name.setdefault(name, []).append(t)
        if t.id:
            self.by_id.setdefault(t.id, []).append(t)

    def resolve(self, name: str, ns: str | None = None) -> list[Term]:
        """All terms matching `name` (optionally restricted to namespace `ns`)."""
        candidates = self.by_name.get(normalize(name), [])
        if ns is not None:
            ns = normalize(ns)
            candidates = [t for t in candidates if t.ns == ns]
        return candidates


def load_glossary(paths: list[Path],
                  term_fields: tuple[str, ...] = ("term",),
                  lenient: bool = False) -> Glossary:
    g = Glossary()
    for p in sorted(paths):
        try:
            t = parse_record(p, term_fields, lenient)
        except InvalidRecord as e:
            g.invalid.append((p, str(e)))
            continue
        if t:
            g.add(t)
    return g
