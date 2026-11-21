"""Doc scanning: find references in markdown files.

Six kinds of reference:
  explicit  — [[term]] / [[ns:term]], plus configured delimiters (e.g. /term)
              (must resolve, else E002/E003)
  id        — matches of configured id_patterns  (must resolve to a record id, else E004)
  field     — values of configured ref_fields in a doc's frontmatter, e.g.
              solves: [T1] (must resolve by id or name, else E006)
  catalog   — values from a configured JSON/YAML inventory (must resolve, else E006)
  mention   — plain-prose occurrence of a defined term or alias (indexed for
              `ubiq refs` and orphan detection; never an error)
  markdown  — Markdown link to a record or configured glossary location
              (must resolve by destination, else E002/E003)

Refs from `historical` files still index mentions and resolved refs, but
unresolved explicit/id/field refs do not fail the build.

Fenced code blocks are never scanned. Inline code is ignored for wiki-links,
id patterns, and mentions — but configured delimiters *do* match inside
backticks, because that is how slash-commands are written (`/tdd`).
"""

from __future__ import annotations

import fnmatch
import os
import re
from bisect import bisect_right
from dataclasses import dataclass
from pathlib import Path
from string import punctuation
from urllib.parse import unquote, urlsplit

import yaml

from .records import (
    FRONTMATTER_RE, Glossary, Term, _parse_lenient, load_vocabulary_yaml, normalize,
)

# field values that are placeholders, not references
SKIP_FIELD_VALUES = {"", "-", "—", "na", "n/a", "none", "no", "yes"}

# (?<!!) skips ![[...]] embeds/transclusions (Obsidian-style includes, not term refs)
EXPLICIT_RE = re.compile(r"(?<!!)\[\[([^\[\]|]+?)(?:\|[^\[\]]*)?\]\]")
FENCE_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")
# GLOSSARY.md, SKILL.md, foo.json — wiki-link targets that are filenames, not terms
FILE_EXT_RE = re.compile(r"\.[A-Za-z][A-Za-z0-9]{0,7}$")
MD_DESTINATION = r"<[^>\n]*>|(?:\\.|[^()\s]|\([^()\n]*\))+"
MD_TITLE = r"(?:[ \t]+(?:\"[^\"\n]*\"|'[^'\n]*'|\([^()\n]*\)))?"
MD_DEFINITION_RE = re.compile(
    r"^ {0,3}\[(?P<label>(?:\\.|[^\[\]\n])+)\]:[ \t]*"
    r"(?P<destination>" + MD_DESTINATION + r")" + MD_TITLE + r"[ \t]*$",
    re.MULTILINE,
)
# Consume images and complete reference usages too, so their suffixes cannot
# become accidental shortcut links. Nested labels are outside this grammar.
MD_LINK_RE = re.compile(
    r"(?P<image>!)?\[(?P<label>(?:\\.|[^\[\]\n])*)\]"
    r"(?:\([ \t]*(?P<destination>" + MD_DESTINATION + r")" + MD_TITLE
    + r"[ \t]*\)|\[(?P<reference>(?:\\.|[^\[\]\n])*)\])?"
)
MD_ESCAPE_RE = re.compile(r"\\([" + re.escape(punctuation) + r"])")
# ATX headings start sections for unlinked-mention checks (W002).
HEADING_RE = re.compile(r"^ {0,3}#{1,6}(?=[ \t]|$)", re.MULTILINE)
# Raw HTML open/close tags, including attributes that may span lines.
HTML_TAG_RE = re.compile(r"</?[A-Za-z][A-Za-z0-9-]*(?:\s[^<>]*)?/?>")
DOC_SUFFIXES = {".md", ".markdown"}


def _matches_glob(parts: tuple[str, ...], pattern: tuple[str, ...]) -> bool:
    """Match path segments. ** consumes zero or more directories."""
    if not pattern:
        return not parts
    if pattern[0] == "**":
        return (_matches_glob(parts, pattern[1:])
                or bool(parts) and _matches_glob(parts[1:], pattern))
    return (bool(parts) and fnmatch.fnmatchcase(parts[0], pattern[0])
            and _matches_glob(parts[1:], pattern[1:]))


def _doc_link_path(source: Path, spec: str, root: Path | None = None) -> Path | None:
    """Return a local Markdown destination, including missing files."""
    try:
        destination = spec.strip().removeprefix("<").removesuffix(">")
        url = urlsplit(MD_ESCAPE_RE.sub(r"\1", destination))
        if url.scheme or url.netloc or not url.path:
            return None
        candidate = Path(os.path.abspath(source.parent / unquote(url.path)))
        if candidate.suffix.lower() not in DOC_SUFFIXES:
            return None
        if root is not None and not candidate.is_relative_to(root.absolute()):
            return None
        return candidate
    except ValueError:
        return None


def _looks_like_path(target: str) -> bool:
    """Obsidian-style file link, not a term: `[[GLOSSARY.md]]`, `[[./x]]`, `[[dir/x]]`."""
    t = target.strip()
    if "/" in t or "\\" in t:
        return True
    if t.startswith("."):
        return True
    return bool(FILE_EXT_RE.search(t))


def resolve_doc_link(source: Path, spec: str, root: Path) -> Path | None:
    """Resolve a relative file link against `source`, staying inside `root`.

    Missing files (a teaching-workspace `[[MISSION.md]]`) return None — not an error.
    """
    cand = _doc_link_path(source, spec, root)
    if cand is None:
        return None
    try:
        resolved = cand.resolve()
        if not resolved.is_file() or resolved.suffix.lower() not in DOC_SUFFIXES:
            return None
        if not resolved.is_relative_to(root.resolve()):
            return None
        return resolved
    except (OSError, ValueError):
        return None


def file_link_targets(path: Path, root: Path) -> list[Path]:
    """Existing markdown files this doc points at via path wiki-links or relative md links."""
    document = _interpret_markdown(path.read_text(encoding="utf-8"))
    found: list[Path] = []
    seen: set[Path] = set()
    specs: list[str] = []
    for m in EXPLICIT_RE.finditer(document.prose):
        target = m.group(1).strip()
        if not _escaped(document.prose, m.start()) and _looks_like_path(target):
            specs.append(target)
    specs.extend(destination for _, _, destination in document.links)
    for spec in specs:
        hit = resolve_doc_link(path, spec, root)
        if hit and hit not in seen:
            seen.add(hit)
            found.append(hit)
    return found


# Slash-command / wiki-token: one identifier, hyphens ok. Trailing `/` rejected so
# `/skills/engineering/tdd` is a path, not a `/skills` ref.
TERM_TOKEN = r"[A-Za-z][A-Za-z0-9_-]*"


@dataclass
class Delimiter:
    """An extra explicit-ref wrapper. `pattern` contains `{term}` or is a prefix."""
    regex: re.Pattern
    except_names: frozenset[str]
    only_known: bool = False


def compile_delimiter(spec: str | dict) -> Delimiter:
    """`"/"` or `"/{term}"` or `{pattern: "/", except: [plugin], only_known: true}`.

    `only_known: true` matches a token only if it is already a glossary name, so
    `/tmp` and `/clear` are silent; typos of unknown names are also invisible.
    Default is strict: every `/slug` is an explicit ref (typos fail the build).
    """
    except_raw: list[str]
    if isinstance(spec, str):
        pattern, except_raw, only_known = spec, [], False
    else:
        pattern = spec.get("pattern") or spec.get("prefix") or ""
        except_raw = spec.get("except") or []
        only_known = bool(spec.get("only_known"))
    if not pattern:
        raise ValueError("delimiter needs `pattern` or `prefix`")
    if "{term}" not in pattern:
        pattern = f"{pattern}{{term}}"
    prefix, _, suffix = pattern.partition("{term}")
    # Not a URL (`//host`, `/tmp/foo`), relative path (`./file.md`), or HTML
    # close tag (`</picture>`). Slash-commands sit after whitespace, backticks,
    # or markdown punctuation.
    regex = re.compile(
        r"(?<![A-Za-z0-9/.<>])"
        + re.escape(prefix)
        + r"(" + TERM_TOKEN + r")"
        + re.escape(suffix)
        + r"(?![A-Za-z0-9_/-])"
    )
    return Delimiter(
        regex,
        frozenset(normalize(str(x)) for x in except_raw),
        only_known,
    )


@dataclass
class Ref:
    kind: str  # "explicit" | "id" | "field" | "mention" | "catalog" | "markdown"
    raw: str   # text as written
    name: str  # normalized term (explicit/mention) or the id string
    ns: str | None
    file: Path
    line: int
    target: str = ""  # explicit refs: the target as written (for id fallback, e.g. [[T5]])
    historical: bool = False  # historical docs: unresolved explicit/id/field do not fail
    destination: Path | None = None  # Markdown links resolve by file, not label
    section: int = 0  # ATX headings seen at or before this line (0 = before the first)
    heading: bool = False  # the reference sits on a heading line

    def resolve(self, glossary: Glossary) -> list[Term]:
        """Resolve consistently for checks, usage tracking, and refs queries."""
        if self.kind == "markdown":
            return list(glossary.by_file.get(self.destination, []))
        if self.kind == "id":
            return glossary.by_id.get(self.name, [])
        if self.kind in ("field", "catalog"):
            return (glossary.by_id.get(self.target, [])
                    or glossary.resolve(self.name, self.ns))
        matches = glossary.resolve(self.name, self.ns)
        if not matches and self.kind == "explicit" and self.ns is None:
            matches = glossary.by_id.get(self.target, [])
        return matches


def _blank(text: str) -> str:
    """Keep source offsets and line numbers while hiding syntax."""
    return "".join(c if c == "\n" else " " for c in text)


def _mask(text: str, spans: list[tuple[int, int]]) -> str:
    parts: list[str] = []
    end = 0
    for start, stop in sorted(spans):
        if start < end:
            continue
        parts.extend((text[end:start], _blank(text[start:stop])))
        end = stop
    parts.append(text[end:])
    return "".join(parts)


def _escaped(text: str, pos: int) -> bool:
    start = pos
    while start and text[start - 1] == "\\":
        start -= 1
    return (pos - start) % 2 == 1


def _blank_fences(text: str) -> str:
    """Mask fenced blocks, including unmatched openers through EOF."""
    fence = ""
    lines: list[str] = []
    for line in text.splitlines(keepends=True):
        match = FENCE_RE.match(line.rstrip("\r\n"))
        if fence:
            lines.append(_blank(line))
            if (match and match[1][0] == fence[0] and len(match[1]) >= len(fence)
                    and not match[2].strip()):
                fence = ""
        elif match and not (match[1][0] == "`" and "`" in match[2]):
            fence = match[1]
            lines.append(_blank(line))
        else:
            lines.append(line)
    return "".join(lines)


def _blank_inline(text: str) -> str:
    ticks = list(re.finditer(r"`+", text))
    spans: list[tuple[int, int]] = []
    following: dict[str, int] = {}
    closers: dict[int, int] = {}
    for index in range(len(ticks) - 1, -1, -1):
        marker = ticks[index].group()
        if marker in following:
            closers[index] = following[marker]
        following[marker] = index
    i = 0
    while i < len(ticks):
        opener = ticks[i]
        if _escaped(text, opener.start()):
            i += 1
            continue
        closer = closers.get(i)
        if closer is None:
            i += 1
        else:
            spans.append((opener.start(), ticks[closer].end()))
            i = closer + 1
    return _mask(text, spans)


def _reference_label(label: str) -> str:
    return " ".join(MD_ESCAPE_RE.sub(r"\1", label).split()).casefold()


@dataclass
class _Markdown:
    prose: str
    delimiters: str
    links: list[tuple[int, int, str]]
    # Inline link and image destinations, `(here)`. Paths, not prose, so a
    # `/` delimiter must not read `[guide](/setup.md)` as the command `/setup`.
    destinations: list[tuple[int, int]]


def _interpret_markdown(text: str, skip_frontmatter: bool = True) -> _Markdown:
    """Interpret the supported Markdown subset once for both scan consumers."""
    fm = FRONTMATTER_RE.match(text)
    if fm and skip_frontmatter:
        text = _blank(fm.group()) + text[fm.end():]
    fenced = _blank_fences(text)
    outside_inline = _blank_inline(fenced)
    definitions: dict[str, str] = {}
    definition_spans: list[tuple[int, int]] = []
    for m in MD_DEFINITION_RE.finditer(fenced):
        if outside_inline[m.start("label") - 1] != "[":
            continue
        definitions.setdefault(_reference_label(m['label']), m['destination'])
        definition_spans.append(m.span())
    delimiters = _mask(fenced, definition_spans)
    prose = _blank_inline(delimiters)
    links: list[tuple[int, int, str]] = []
    destinations: list[tuple[int, int]] = []
    for m in MD_LINK_RE.finditer(prose):
        if m["destination"] is not None:
            destinations.append(m.span("destination"))
        start = m.start()
        if m["image"] and _escaped(prose, start):
            start += 1  # An escaped exclamation mark is prose, not an image.
        elif m["image"] or _escaped(prose, start):
            continue
        if start and prose[start - 1] == "[":
            continue
        destination = m['destination']
        if destination is None:
            label = m['reference'] if m['reference'] else m['label']
            destination = definitions.get(_reference_label(label))
        if destination is not None:
            links.append((start, m.end(), destination))
    return _Markdown(prose, delimiters, links, destinations)


def _line_of(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


def _field_refs(fm_text: str, path: Path, ref_fields: list[str],
                lenient: bool) -> list[Ref]:
    try:
        meta = load_vocabulary_yaml(fm_text) or {}
    except yaml.YAMLError:
        meta = _parse_lenient(fm_text) if lenient else {}
    refs: list[Ref] = []
    if not isinstance(meta, dict):
        return refs
    lines = fm_text.splitlines()
    for fld in ref_fields:
        vals = meta.get(fld)
        if vals is None:
            continue
        vals = vals if isinstance(vals, list) else [vals]
        line = next((i + 2 for i, ln in enumerate(lines)
                     if re.match(rf"^{re.escape(fld)}\s*:", ln)), 1)
        for v in vals:
            if not isinstance(v, str):
                continue
            v = v.strip().strip("'\"")
            if not v or v.lower() in SKIP_FIELD_VALUES:
                continue
            refs.append(Ref("field", f"{fld}: {v}", normalize(v), None, path,
                            line, target=v))
    return refs


def scan_file(path: Path, glossary: Glossary, id_patterns: list[str],
              skip_frontmatter: bool = True,
              ref_fields: list[str] | None = None,
              lenient: bool = False,
              delimiters: list[Delimiter] | None = None,
              root: Path | None = None,
              glossary_patterns: list[str] | None = None) -> list[Ref]:
    text = path.read_text(encoding="utf-8")
    refs: list[Ref] = []
    fm = FRONTMATTER_RE.match(text)
    if fm and ref_fields:
        refs += _field_refs(fm.group(1), path, ref_fields, lenient)
    document = _interpret_markdown(text, skip_frontmatter)
    clean = document.prose
    for_delim = document.delimiters

    link_spans: list[tuple[int, int]] = []
    record_files = glossary.by_file
    for start, end, spec in document.links:
        destination = _doc_link_path(path, spec, root)
        if destination is None:
            continue
        registered = destination.resolve() in record_files
        configured = root is not None and any(
            _matches_glob(destination.parts, (root / pattern).parts)
            for pattern in glossary_patterns or []
        )
        if not (registered or configured):
            continue
        refs.append(Ref("markdown", text[start:end], "", None, path,
                        _line_of(clean, start), target=spec,
                        destination=destination.resolve()))
        link_spans.append((start, end))

    clean = _mask(clean, link_spans)
    for_delim = _mask(for_delim, link_spans)

    for m in EXPLICIT_RE.finditer(clean):
        if _escaped(clean, m.start()):
            continue
        target = m.group(1).strip()
        ns, _, name = target.rpartition(":")
        # Path-shaped wiki-links are file refs, not terms — unless the name is
        # actually a defined term (`[[SKILL.md]]` in a repo that named that file).
        if _looks_like_path(target) and not glossary.resolve(
                name, normalize(ns) if ns else None):
            continue
        refs.append(Ref("explicit", m.group(0), normalize(name),
                        normalize(ns) if ns else None, path, _line_of(clean, m.start()),
                        target=name.strip()))

    delim_spans: list[tuple[int, int]] = []
    # Link destinations and HTML tag attributes hold paths (`(/setup.md)`,
    # `href="/install"`). Skip matches that start inside them rather than
    # masking, so blanked text cannot create new token boundaries.
    not_prose = document.destinations + [m.span() for m in HTML_TAG_RE.finditer(for_delim)]
    for delim in delimiters or []:
        for m in delim.regex.finditer(for_delim):
            if any(a <= m.start() < b for a, b in not_prose):
                continue
            raw_term = m.group(1)
            name = normalize(raw_term)
            if name in delim.except_names:
                continue
            if delim.only_known and name not in glossary.by_name:
                continue
            refs.append(Ref("explicit", m.group(0), name, None, path,
                            _line_of(for_delim, m.start()), target=raw_term))
            delim_spans.append((m.start(), m.end()))

    for pat in id_patterns:
        for m in re.finditer(pat, clean):
            refs.append(Ref("id", m.group(0), m.group(0), None, path,
                            _line_of(clean, m.start())))

    # Plain mentions of known terms/aliases (longest-first so multiword terms win).
    names = sorted(glossary.by_name, key=len, reverse=True)
    if names:
        mention_re = re.compile(
            r"\b(" + "|".join(re.escape(n).replace(r"\ ", r"[\s_-]+") for n in names) + r")\b",
            re.IGNORECASE,
        )
        explicit_spans = [(m.start(), m.end()) for m in EXPLICIT_RE.finditer(clean)]
        skip_spans = explicit_spans + delim_spans + link_spans
        for m in mention_re.finditer(clean):
            if any(a <= m.start() < b for a, b in skip_spans):
                continue  # already counted as explicit
            refs.append(Ref("mention", m.group(0), normalize(m.group(0)), None,
                            path, _line_of(clean, m.start())))

    # Fences, inline code, and frontmatter are already blank in `clean`.
    heading_lines = [_line_of(clean, m.start()) for m in HEADING_RE.finditer(clean)]
    headings = set(heading_lines)
    for ref in refs:
        ref.section = bisect_right(heading_lines, ref.line)
        ref.heading = ref.line in headings
    return refs


def scan_docs(paths: list[Path], glossary: Glossary, id_patterns: list[str],
              ref_fields: list[str] | None = None,
              lenient: bool = False,
              delimiters: list[Delimiter] | None = None,
              historical: set[Path] | None = None,
              root: Path | None = None,
              glossary_patterns: list[str] | None = None,
              invalid: list[tuple[Path, str]] | None = None) -> list[Ref]:
    hist = {p.resolve() for p in (historical or [])}
    refs: list[Ref] = []
    for p in sorted(paths):
        try:
            found = scan_file(p, glossary, id_patterns,
                              ref_fields=ref_fields, lenient=lenient,
                              delimiters=delimiters, root=root,
                              glossary_patterns=glossary_patterns)
        except (OSError, UnicodeError) as exc:
            if invalid is None:
                raise
            if not any(path.resolve() == p.resolve() for path, _ in invalid):
                invalid.append((p, f"cannot read document: {exc}"))
            continue
        if p.resolve() in hist:
            for r in found:
                r.historical = True
        refs.extend(found)
    return refs
