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


class _VocabularyLoader(yaml.SafeLoader):
    """SafeLoader that keeps scalars as written.

    Vocabulary is text: `term: No`, `id: 007`, and `id: 1.10` must not become
    False, 7, and 1.1 (YAML 1.1 implicit typing). Null and merge keys still
    resolve, so an empty field reads as absent.
    """


_KEEP_IMPLICIT = {"tag:yaml.org,2002:null", "tag:yaml.org,2002:merge"}
_VocabularyLoader.yaml_implicit_resolvers = {
    first: [(tag, regexp) for tag, regexp in resolvers if tag in _KEEP_IMPLICIT]
    for first, resolvers in yaml.SafeLoader.yaml_implicit_resolvers.items()
}


def load_vocabulary_yaml(text: str):
    """Parse record, overlay, reference-field, and catalog YAML without type coercion."""
    return yaml.load(text, Loader=_VocabularyLoader)


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
    # Term and aliases as written, before normalize: `grill-me` vs `grill me`.
    spellings: list[str] = field(default_factory=list)
    # Set on another repository's records (edges.external): that repository's name.
    repository: str | None = None

    @property
    def qualified(self) -> str:
        here = f"{self.ns}:{self.term}"
        return f"{self.repository}/{here}" if self.repository else here

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
        meta = load_vocabulary_yaml(m.group(1)) or {}
    except yaml.YAMLError as e:
        if lenient:
            meta = _parse_lenient(m.group(1))
        else:
            raise InvalidRecord(
                f"invalid YAML frontmatter: {str(e).splitlines()[0]}") from e
    if not isinstance(meta, dict):
        raise InvalidRecord("frontmatter must be a mapping")
    return meta, text[m.end():]


def _name(value, field: str) -> str:
    """A term or alias as written. `term: [a, b]` or a blank name is E005."""
    if not isinstance(value, str) or not value.strip():
        raise InvalidRecord(f"{field}: expected a nonempty string")
    return value.strip()


def _optional_name(meta: dict, field: str) -> str | None:
    """`id` or `ns` as written; null reads as absent. `id: [a, b]` is E005."""
    value = meta.get(field)
    return None if value is None else _name(value, field)


def _aliases(meta: dict, label: str = "aliases") -> list[str]:
    aliases = meta.get("aliases") or []
    if isinstance(aliases, str):
        aliases = [aliases]
    if not isinstance(aliases, list):
        raise InvalidRecord(f"{label} must be a string or list")
    return [_name(a, label) for a in aliases]


def parse_record(path: Path, term_fields: tuple[str, ...] = ("term",),
                 lenient: bool = False, default_ns: str | None = None) -> Term | None:
    """Parse a glossary record. Returns None if no term field is present.

    `term_fields` lets existing repos keep their schema: e.g. ("name", "title")
    treats `name:` (falling back to `title:`) as the term.
    `default_ns` is used when the file itself has no `ns:` (glob-level overlay).
    """
    meta, body = parse_frontmatter(path, lenient)
    # A null field reads as absent; any other value must be a nonempty string.
    field_name = next((f for f in term_fields if meta.get(f) is not None), None)
    if field_name is None:
        return None
    term = _name(meta[field_name], field_name)
    aliases = _aliases(meta)
    # An empty `ns:` loads as null, which reads as absent.
    ns = _optional_name(meta, "ns") or default_ns or DEFAULT_NS
    return Term(
        term=normalize(term),
        ns=normalize(ns),
        file=path,
        aliases=[normalize(a) for a in aliases],
        id=_optional_name(meta, "id"),
        definition=body.strip(),
        spellings=[term, *aliases],
    )


def overlay_onto(term: Term, meta: dict) -> Term:
    """Merge sidecar frontmatter onto a record. Overlay wins for ns/id; aliases union."""
    extra = _aliases(meta, "overlay aliases")
    aliases = list(dict.fromkeys([*term.aliases, *map(normalize, extra)]))
    ns_ = _optional_name(meta, "ns")
    ns = normalize(ns_) if ns_ else term.ns
    id_ = _optional_name(meta, "id") or term.id
    term_name, spellings = term.term, list(term.spellings)
    if meta.get("term") is not None:
        # An overlay `term:` replaces the record's own spelling, which comes first.
        written = _name(meta["term"], "overlay term")
        term_name = normalize(written)
        spellings = [written, *term.spellings[1:]]
    spellings += extra
    return Term(term=term_name, ns=ns, file=term.file, aliases=aliases,
                id=id_, definition=term.definition, spellings=spellings)


def field_value(path: Path, name: str, glossary: Glossary | None = None,
                lenient: bool = False):
    """Frontmatter field `name` of the file at `path`, as written.

    An overlay sidecar's fields win over the record's own, as in `overlay_onto`.
    A null field reads as absent. Raises KeyError when the field is absent and
    InvalidRecord when the frontmatter cannot be read.
    """
    meta, _ = parse_frontmatter(path, lenient)
    sidecar = glossary.overlay_sources.get(path.resolve()) if glossary else None
    if sidecar is not None:
        extra, _ = parse_frontmatter(sidecar, lenient)
        meta = {**meta, **{k: v for k, v in extra.items() if k not in ("source", "on")}}
    if meta.get(name) is None:
        raise KeyError(name)
    return meta[name]


@dataclass
class Glossary:
    terms: list[Term] = field(default_factory=list)
    # normalized name -> list of Terms that claim it (canonical or alias)
    by_name: dict[str, list[Term]] = field(default_factory=dict)
    by_id: dict[str, list[Term]] = field(default_factory=dict)
    # resolved record path -> Terms defined there. Markdown links resolve by
    # destination, so this keeps lookups O(1) instead of a filesystem call per term.
    by_file: dict[Path, list[Term]] = field(default_factory=dict)
    overlay_sources: dict[Path, Path] = field(default_factory=dict)
    invalid: list[tuple[Path, str]] = field(default_factory=list)  # unparseable records
    namespaces: set[str] = field(default_factory=set)
    external: dict[str, Glossary] = field(default_factory=dict)

    def add_external(self, name: str, glossary: Glossary) -> None:
        self.external[name] = glossary
        for path, terms in glossary.by_file.items():
            self.by_file.setdefault(path, terms)

    def add(self, t: Term) -> None:
        self.terms.append(t)
        self.namespaces.add(t.ns)
        for name in t.names():
            self.by_name.setdefault(name, []).append(t)
        if t.id:
            self.by_id.setdefault(t.id, []).append(t)
        self.by_file.setdefault(t.file.resolve(), []).append(t)

    def split(self, target: str) -> tuple[str | None, str]:
        """`ns:name` when `ns` is a namespace here; otherwise the colon is part
        of the name, so a term such as `ratio:2` stays linkable."""
        ns, _, name = target.partition(":")
        if name and normalize(ns) in self.namespaces:
            return normalize(ns), name
        if name and "/" in ns and normalize(target) not in self.by_name:
            return ns, name
        return None, target

    def resolve(self, name: str, ns: str | None = None) -> list[Term]:
        """All terms matching `name` (optionally restricted to namespace `ns`)."""
        if ns is None:
            ns, name = self.split(name)
        if ns is not None and "/" in ns and normalize(ns) not in self.namespaces:
            dependency, _, namespace = ns.partition("/")
            other = self.external.get(dependency)
            return other.resolve(name, namespace) if other is not None else []
        candidates = self.by_name.get(normalize(name), [])
        if ns is not None:
            ns = normalize(ns)
            candidates = [t for t in candidates if t.ns == ns]
        return candidates


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
                if term is None and meta.get("term") is not None:
                    written = _name(meta["term"], "overlay term")
                    term = Term(normalize(written), ns, source, spellings=[written])
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
