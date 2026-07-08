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
        return [self.term, *self.aliases]


def normalize(name: str) -> str:
    """Canonical form for matching: lowercase, collapsed whitespace/hyphens."""
    return re.sub(r"[\s_-]+", " ", name.strip().lower())


def parse_record(path: Path) -> Term | None:
    """Parse a glossary record. Returns None if the file has no `term:` frontmatter."""
    text = path.read_text(encoding="utf-8")
    m = FRONTMATTER_RE.match(text)
    if not m:
        return None
    meta = yaml.safe_load(m.group(1)) or {}
    if not isinstance(meta, dict) or "term" not in meta:
        return None
    aliases = meta.get("aliases") or []
    if isinstance(aliases, str):
        aliases = [aliases]
    return Term(
        term=normalize(str(meta["term"])),
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


def load_glossary(paths: list[Path]) -> Glossary:
    g = Glossary()
    for p in sorted(paths):
        t = parse_record(p)
        if t:
            g.add(t)
    return g
