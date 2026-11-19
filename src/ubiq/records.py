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


def parse_frontmatter(path: Path, lenient: bool = False) -> tuple[dict, str]:
    """Return (frontmatter dict, body). Empty dict if the file has no frontmatter."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise InvalidRecord(f"cannot read record: {exc}") from exc
    m = FRONTMATTER_RE.match(text)
    if not m:
        return {}, text
    try:
        meta = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError as e:
        if lenient:
            meta = _parse_lenient(m.group(1))
        else:
            raise InvalidRecord(
                f"invalid YAML frontmatter: {str(e).splitlines()[0]}") from e
    if not isinstance(meta, dict):
        raise InvalidRecord("frontmatter must be a mapping")
    return meta, text[m.end():]


def parse_record(path: Path, term_fields: tuple[str, ...] = ("term",),
                 lenient: bool = False, default_ns: str | None = None) -> Term | None:
    """Parse a glossary record. Returns None if no term field is present.

    `term_fields` lets existing repos keep their schema: e.g. ("name", "title")
    treats `name:` (falling back to `title:`) as the term.
    `default_ns` is used when the file itself has no `ns:` (glob-level overlay).
    """
    meta, body = parse_frontmatter(path, lenient)
    field_name = next((f for f in term_fields if meta.get(f)), None)
    if field_name is None:
        return None
    aliases = meta.get("aliases") or []
    if isinstance(aliases, str):
        aliases = [aliases]
    if not isinstance(aliases, list):
        raise InvalidRecord("aliases must be a string or list")
    ns = meta.get("ns", default_ns or DEFAULT_NS)
    return Term(
        term=normalize(str(meta[field_name])),
        ns=normalize(str(ns)),
        file=path,
        aliases=[normalize(str(a)) for a in aliases],
        id=str(meta["id"]) if meta.get("id") is not None else None,
        definition=body.strip(),
    )


def overlay_onto(term: Term, meta: dict) -> Term:
    """Merge sidecar frontmatter onto a record. Overlay wins for ns/id; aliases union."""
    extra = meta.get("aliases") or []
    if isinstance(extra, str):
        extra = [extra]
    if not isinstance(extra, list):
        raise InvalidRecord("overlay aliases must be a string or list")
    aliases = list(dict.fromkeys(
        [*term.aliases, *[normalize(str(a)) for a in extra]]))
    ns = normalize(str(meta["ns"])) if meta.get("ns") else term.ns
    id_ = str(meta["id"]) if meta.get("id") is not None else term.id
    if meta.get("term"):
        term_name = normalize(str(meta["term"]))
    else:
        term_name = term.term
    return Term(term=term_name, ns=ns, file=term.file, aliases=aliases,
                id=id_, definition=term.definition)


@dataclass
class Glossary:
    terms: list[Term] = field(default_factory=list)
    # normalized name -> list of Terms that claim it (canonical or alias)
    by_name: dict[str, list[Term]] = field(default_factory=dict)
    by_id: dict[str, list[Term]] = field(default_factory=dict)
    overlay_sources: dict[Path, Path] = field(default_factory=dict)
    invalid: list[tuple[Path, str]] = field(default_factory=list)  # unparseable records

    def add(self, t: Term) -> None:
        self.terms.append(t)
        for name in t.names():
            self.by_name.setdefault(name, []).append(t)
        if t.id:
            self.by_id.setdefault(t.id, []).append(t)

    def resolve(self, name: str, ns: str | None = None) -> list[Term]:
        """All terms matching `name` (optionally restricted to namespace `ns`)."""
        if ns is None and ":" in name:
            ns, _, name = name.rpartition(":")
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


class ConflictingGlossary(ValueError):
    """One source was selected by incompatible glossary rules."""


def assemble_glossary(root: Path, sources: list[tuple[Path, tuple[str, ...], str | None, str]],
                      overlay_paths: list[Path], term_fields: tuple[str, ...],
                      lenient: bool = False, *, ref_fields: tuple[str, ...] = ()) -> Glossary:
    """Build one glossary from discovered sources and sidecar records."""
    glossary = Glossary()
    overlays: dict[Path, tuple[Path, dict]] = {}
    seen_overlays: set[Path] = set()
    duplicate_sources: set[Path] = set()
    for path in overlay_paths:
        if path.resolve() in seen_overlays:
            continue
        seen_overlays.add(path.resolve())
        try:
            meta, _ = parse_frontmatter(path, lenient)
            source = meta.get("source") or meta.get("on")
            if source is None:
                source = meta.get(True)  # YAML 1.1 compatibility for on:
            if not isinstance(source, str) or not source.strip():
                raise InvalidRecord("overlay source: expected a nonempty path string")
            try:
                resolved = (root / source).resolve()
            except (ValueError, OSError, RuntimeError) as exc:
                raise InvalidRecord(f"invalid overlay source path: {exc}") from exc
            if resolved in overlays:
                duplicate_sources.add(resolved)
                raise InvalidRecord(
                    f"duplicate overlays for {resolved}: {overlays[resolved][0]} and {path}")
            overlays[resolved] = (path, meta)
        except InvalidRecord as exc:
            glossary.invalid.append((path, str(exc)))
    for source in duplicate_sources:
        overlays.pop(source, None)

    glossary.overlay_sources = {source: path for source, (path, _) in overlays.items()}

    selected: dict[Path, tuple[tuple[str, ...], str, str]] = {}
    for path, fields, ns, rule in sources:
        source = path.resolve()
        settings = (fields, normalize(ns or DEFAULT_NS))
        previous = selected.get(source)
        if previous:
            if previous[:2] != settings:
                raise ConflictingGlossary(
                    f"conflicting glossary rules for {source}: {previous[2]} and {rule}")
            continue
        selected[source] = (*settings, rule)

    for source, (path, meta) in overlays.items():
        selected.setdefault(source, (term_fields, normalize(str(meta.get("ns") or DEFAULT_NS)),
                                     f"overlay {path}"))

    for source, (fields, ns, _) in selected.items():
        try:
            if source in overlays and not source.is_file():
                raise InvalidRecord(f"overlay source: '{source}' does not exist")
            term = parse_record(source, fields, lenient, default_ns=ns)
            if source in overlays:
                _, meta = overlays[source]
                if term is None and meta.get("term"):
                    term = Term(normalize(str(meta["term"])), ns, source)
                if term is None:
                    if (any(field in meta for field in ref_fields)
                            and not any(field in meta for field in ("term", "ns", "aliases", "id"))):
                        # Document dependencies are scanned from the sidecar, without a term.
                        continue
                    raise InvalidRecord(f"overlay source: '{source}' has no defining term")
                term = overlay_onto(term, meta)
            if term:
                glossary.add(term)
        except InvalidRecord as exc:
            location = overlays[source][0] if source in overlays else source
            glossary.invalid.append((location, str(exc)))
    return glossary
