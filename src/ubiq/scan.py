"""Doc scanning: find references in markdown files.

What each kind matches, where, how it resolves, and what it reports lives in
the policy table in `kinds.py`; this module extracts candidate matches and asks
each kind's policy which document regions it may match in.

  wiki      — [[term]] / [[ns:term]]                       (E002/E003)
  delimiter — configured wrappers such as /term             (E002/E003)
  markdown  — Markdown link to a record or glossary path    (E002/E003, by destination)
  id        — matches of configured id_patterns             (E004)
  field     — values of configured ref_fields in frontmatter (E006)
  catalog   — values from a JSON/YAML inventory (catalog.py) (E006)
  value     — link whose #fragment names a frontmatter field   (E013)
  mention   — plain-prose occurrence of a known name        (never an error; W002)
  link      — relative link to a missing file, not a record  (W007)

Fenced code, frontmatter, and reference definitions are never scanned as prose.
Refs from `historical` files are indexed, but unresolved ones do not fail.
"""

from __future__ import annotations

import os
import re
from bisect import bisect_left, bisect_right
from collections import Counter
from dataclasses import dataclass
from html import unescape
from html.entities import html5
from pathlib import Path
from string import punctuation
from typing import TYPE_CHECKING
from urllib.parse import quote, unquote, urlsplit

import yaml

from .kinds import Context, Policy
from .records import (
    FRONTMATTER_RE,
    Glossary,
    InvalidRecord,
    Term,
    _parse_lenient,
    field_value,
    frontmatter_fields,
    load_vocabulary_yaml,
    normalize,
)

if TYPE_CHECKING:
    from .config import Config

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
MD_ENTITY_RE = re.compile(
    r"&(?:#[0-9]{1,7}|#[xX][0-9a-fA-F]{1,6}|[A-Za-z][A-Za-z0-9]{1,31});")
# ATX headings start sections for unlinked-mention checks (W002).
HEADING_RE = re.compile(r"^ {0,3}#{1,6}(?=[ \t]|$)", re.MULTILINE)
# Raw HTML open/close tags, per the CommonMark grammar: attributes may span
# lines and need no value (`<details open>`). "x < y" is prose: no tag name.
HTML_TAG_RE = re.compile(
    r"</[A-Za-z][A-Za-z0-9-]*\s*>"
    r"|<[A-Za-z][A-Za-z0-9-]*"
    r"(?:\s+[A-Za-z_:][A-Za-z0-9_.:-]*"
    r"(?:\s*=\s*(?:[^\s\"'=<>`]+|'[^']*'|\"[^\"]*\"))?)*\s*/?>")
# Bare URLs (`scheme://`, `www.`), emails, and `<scheme:...>` / `<a@b.c>`
# autolinks: addresses, not prose mentions.
URL_RE = re.compile(r"<[A-Za-z][A-Za-z0-9+.-]*:[^\s<>]*>|<[^\s<>@]+@[^\s<>]+>"
                    # Lookbehinds, not `\b`: `\b` re-enters every dotted run (quadratic).
                    r"|(?:(?<![A-Za-z0-9+.-])[A-Za-z][A-Za-z0-9+.-]*://|\bwww\.)"
                    r"[^\s<>()\[\]`]+"  # a closing backtick ends a URL in code
                    # The domain ends in a letter TLD, so `tdd@2.0` is a pin, not an email.
                    r"|(?<![\w.+-])[\w.+-]+@[\w-]+(?:\.[\w-]+)*\.[A-Za-z]{2,}\b")
# HTML comments are not rendered, so their words are not prose mentions.
HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
DOC_SUFFIXES = {".md", ".markdown"}


def _local_path(source: Path, spec: str, root: Path | None = None) -> Path | None:
    """Return a relative link's local destination, including missing files.

    URLs, anchor-only links, and root-relative paths (`/x`) have none.
    """
    try:
        destination = spec.strip().removeprefix("<").removesuffix(">")
        url = urlsplit(MD_ESCAPE_RE.sub(r"\1", destination))
        if url.scheme or url.netloc or not url.path or url.path.startswith("/"):
            return None
        candidate = Path(os.path.abspath(source.parent / unquote(url.path)))
        if root is not None and not candidate.is_relative_to(root.absolute()):
            return None
        return candidate
    except ValueError:
        return None


def _doc_link_path(source: Path, spec: str, root: Path | None = None) -> Path | None:
    """Return a local Markdown destination, including missing files."""
    candidate = _local_path(source, spec, root)
    return candidate if candidate and candidate.suffix.lower() in DOC_SUFFIXES else None


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
    policy: Policy  # what this kind matches, how it resolves, and what it reports
    raw: str   # text as written
    name: str  # normalized term (explicit/mention) or the id string
    ns: str | None
    file: Path
    line: int
    target: str = ""  # as written: a name, an id, a field value, or a value link's label
    historical: bool = False  # historical docs: unresolved refs do not fail
    destination: Path | None = None  # Markdown links resolve by file, not label
    section: int = 0  # ATX headings seen at or before this line (0 = before the first)
    heading: bool = False  # the reference sits on a heading line
    linked: bool = False  # mention inside a non-vocabulary link label (author linked it)
    field: str = ""  # value refs: the frontmatter field the fragment names

    @property
    def kind(self) -> str:
        return self.policy.kind

    def resolve(self, glossary: Glossary) -> list[Term]:
        """Resolve consistently for checks, usage tracking, and refs queries."""
        return self.policy.resolve(glossary, self)


def frontmatter_keys(path: Path, glossary: Glossary | None = None,
                     lenient: bool = False) -> dict:
    """`frontmatter_fields`, or none when the file cannot be read."""
    try:
        return frontmatter_fields(path, glossary, lenient)
    except InvalidRecord:
        return {}


def value_of(glossary: Glossary, ref: Ref, lenient: bool = False) -> str:
    """The text of the frontmatter field a `value` ref names, for checks and renderers.

    A list of strings reads as its items joined by ", ". Raises LookupError with
    the reason when the field is absent, null, or not text. Another repository's record
    reads that repository's overlays.
    """
    path = ref.destination
    assert path is not None, "value refs always have a destination"
    owner = next((g for g in glossary.external.values() if path in g.by_file), glossary)
    where = Path(os.path.relpath(path, ref.file.resolve().parent)).as_posix()
    try:
        if ref.field not in frontmatter_fields(path, owner, lenient):
            raise LookupError(f"no field or heading '{ref.field}' in {where}")
        value = field_value(path, ref.field, owner, lenient)
    except KeyError:
        raise LookupError(f"{where} has no value for field '{ref.field}'") from None
    except InvalidRecord as exc:
        raise LookupError(f"{where}: {exc}") from None
    if isinstance(value, str):
        return value
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return ", ".join(value)
    raise LookupError(f"field '{ref.field}' in {where} is not text or a list of "
                      "text; link a scalar field")


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
    return _mask(text, _inline_spans(text))


def _inline_spans(text: str) -> list[tuple[int, int]]:
    """Inline code spans, backticks included: matching runs, unescaped openers."""
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
    return spans


def inline_code(text: str) -> list[tuple[int, str]]:
    """(line, content) of each inline code span outside frontmatter and fences."""
    fm = FRONTMATTER_RE.match(text)
    if fm:
        text = _blank(fm.group()) + text[fm.end():]
    text = _blank_fences(text)
    line_of = _line_index(text)
    out = []
    for start, end in _inline_spans(text):
        span = text[start:end]
        ticks = len(span) - len(span.lstrip("`"))
        out.append((line_of(start), span[ticks:len(span) - ticks]))
    return out


# One-line **strong** or __strong__ text; ***both*** is strong too. `__` that
# touches a word character on the outside is literal (snake__case__).
BOLD_RE = re.compile(r"\*\*(?!\s)([^*\n]+?)(?<!\s)\*\*"
                     r"|(?<!\w)__(?!\s)([^_\n]+?)(?<!\s)__(?!\w)")


def bold_spans(text: str) -> list[tuple[int, str]]:
    """(line, content) of each bold span in prose: outside frontmatter, fences,
    reference definitions, and inline code."""
    prose = _interpret_markdown(text).prose
    line_of = _line_index(prose)
    return [(line_of(m.start()), m[1] or m[2]) for m in BOLD_RE.finditer(prose)
            if not _escaped(prose, m.start())]


def _reference_label(label: str) -> str:
    return " ".join(MD_ESCAPE_RE.sub(r"\1", label).split()).casefold()


@dataclass
class _Markdown:
    prose: str
    delimiters: str
    # Original source offsets plus normalized URL destinations.
    links: list[tuple[int, int, str]]
    # Spans that hold addresses, not prose: link and image destinations, bare
    # URLs and emails, and HTML tags (`(/setup.md)`, `?next=/home`,
    # `href="/install"`). Neither delimiters nor mentions match inside them.
    addresses: list[tuple[int, int]]
    # HTML comments: not rendered, so no mentions. Delimiters still match there.
    comments: list[tuple[int, int]]


def _interpret_markdown(text: str) -> _Markdown:
    """Interpret the supported Markdown subset once for both scan consumers."""
    fm = FRONTMATTER_RE.match(text)
    if fm:
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
            if destination.startswith("<") and destination.endswith(">"):
                destination = destination[1:-1]
            # Decode complete entities once. html.unescape alone also consumes
            # unterminated entities and valid prefixes of unknown entity names.
            destination = MD_ENTITY_RE.sub(
                lambda m: unescape(m[0]) if m[0].startswith("&#")
                else html5.get(m[0][1:], m[0]), destination)
            # Preserve decoded brackets and whitespace as URL data. Consumers
            # must not mistake them for source delimiters or discard controls.
            destination = quote(MD_ESCAPE_RE.sub(r"\1", destination), safe="/:?#[]@!$&'()*+,;=%")
            links.append((start, m.end(), destination))
    # Found in `delimiters`, which keeps inline code, because delimiters match
    # there; comments in `prose`, so a code span such as `<!--` opens none.
    addresses = (destinations + [m.span() for m in URL_RE.finditer(delimiters)]
                 + [m.span() for m in HTML_TAG_RE.finditer(delimiters)])
    comments = [m.span() for m in HTML_COMMENT_RE.finditer(prose)]
    return _Markdown(prose, delimiters, links, addresses, comments)


def _slugs(path: Path) -> set[str]:
    """GitHub-style anchors for the ATX headings of a Markdown file."""
    seen: Counter[str] = Counter()
    slugs = set()
    for line in _blank_fences(path.read_text(encoding="utf-8")).splitlines():
        m = re.match(r" {0,3}#{1,6}\s+(.*?)\s*#*\s*$", line)
        if not m:
            continue
        text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", m.group(1)).strip().lower()
        slug = re.sub(r"[^\w\- ]", "", text).replace(" ", "-")
        slugs.add(f"{slug}-{seen[slug]}" if seen[slug] else slug)
        seen[slug] += 1
    return slugs


def _line_index(text: str):
    """Return pos -> one-based line number. Masked copies keep every newline."""
    newlines = [m.start() for m in re.finditer("\n", text)]
    return lambda pos: bisect_left(newlines, pos) + 1


def _covers(spans: list[tuple[int, int]]):
    """Return pos -> whether any half-open span holds pos. Spans may overlap."""
    starts: list[int] = []
    ends: list[int] = []
    for start, end in sorted(spans):
        if ends and start <= ends[-1]:
            ends[-1] = max(ends[-1], end)
        else:
            starts.append(start)
            ends.append(end)
    return lambda pos: (i := bisect_right(starts, pos) - 1) >= 0 and pos < ends[i]


def _field_refs(fm_text: str, path: Path, ref_fields: tuple[str, ...],
                lenient: bool, policy: Policy, errors: list[str]) -> list[Ref]:
    """Field refs, appending malformed declarations to `errors` (E005)."""
    refs: list[Ref] = []
    try:
        meta = load_vocabulary_yaml(fm_text) or {}
    except yaml.YAMLError as exc:
        if not lenient:
            errors.append(f"invalid YAML frontmatter: {str(exc).splitlines()[0]}")
            return refs
        meta = _parse_lenient(fm_text)
    if not isinstance(meta, dict):
        errors.append("frontmatter must be a mapping")
        return refs
    lines = fm_text.splitlines()
    for fld in ref_fields:
        vals = meta.get(fld)
        if vals is None:
            continue
        vals = vals if isinstance(vals, list) else [vals]
        if not all(isinstance(v, str) for v in vals):
            errors.append(f"{fld}: expected a string or list of strings")
            continue
        line = next((i + 2 for i, ln in enumerate(lines)
                     if re.match(rf"^{re.escape(fld)}\s*:", ln)), 1)
        for v in vals:
            v = v.strip().strip("'\"")
            if not v or v.lower() in SKIP_FIELD_VALUES:
                continue
            refs.append(Ref(policy, f"{fld}: {v}", normalize(v), None, path,
                            line, target=v))
    return refs


def _mention_pattern(name: str) -> str:
    """Regex for a name as written: a name with no spaces needs `-` or `_`."""
    words = re.split(r"[\s_-]+", name.strip())
    slug = len(name.split()) == 1
    return (r"[_-]+" if slug else r"[\s_-]+").join(re.escape(w) for w in words if w)


def scan_file(path: Path, glossary: Glossary, cfg: Config,
              invalid: list[tuple[Path, str]] | None = None) -> list[Ref]:
    text = path.read_text(encoding="utf-8")
    policies = cfg.policies
    refs: list[Ref] = []
    fm = FRONTMATTER_RE.match(text)
    if fm and cfg.ref_fields:
        errors: list[str] = []
        refs += _field_refs(fm.group(1), path, cfg.ref_fields, cfg.lenient,
                            policies["field"], errors)
        if invalid is not None:
            # A record's own parse error is already reported once.
            reported = {(p.resolve(), msg) for p, msg in invalid}
            invalid += [(path, msg) for msg in errors if (path.resolve(), msg) not in reported]
    document = _interpret_markdown(text)
    line_of = _line_index(document.prose)

    def view(policy: Policy, claimed: list[tuple[int, int]]):
        """The text a kind searches, and whether a match start is admitted.

        Code a kind does not scan is masked, since it must not form tokens.
        Addresses and comments are skipped by match start instead, so blanked
        text cannot create new token boundaries.
        """
        source = document.delimiters if Context.INLINE_CODE in policy.scans else document.prose
        blocked = [*([] if Context.ADDRESS in policy.scans else document.addresses),
                   *([] if Context.COMMENT in policy.scans else document.comments)]
        covered = _covers(blocked)
        return _mask(source, claimed), lambda pos: not covered(pos)

    markdown, link = policies["markdown"], policies["link"]
    _, admits = view(markdown, [])
    _, link_admits = view(link, [])
    value = policies["value"]
    _, value_admits = view(value, [])
    link_spans: list[tuple[int, int]] = []
    for start, end, spec in document.links:
        url = urlsplit(spec)
        fragment = unquote(url.fragment)
        if fragment and value_admits(start) and not (url.scheme or url.netloc or url.query):
            # A fragment that names a frontmatter field wins over a heading slug.
            # In a file with frontmatter, one naming neither is a misspelled field.
            file = path if not url.path else _doc_link_path(path, spec, cfg.root)
            fields = frontmatter_keys(file, glossary, cfg.lenient) if (
                file is not None and file.is_file()) else {}
            if file is not None and fields and (
                    fragment in fields or fragment.lower() not in _slugs(file)):
                found = MD_LINK_RE.match(document.delimiters, start)
                label = found["label"].strip() if found else ""
                refs.append(Ref(value, text[start:end], "", None, path, line_of(start),
                                target=label, field=fragment, destination=file.resolve()))
        destination = _doc_link_path(path, spec, cfg.root)
        if destination is not None and (
                destination.resolve() in glossary.by_file
                or any(rule.glob.matches(destination) for rule in cfg.glossary)):
            if admits(start):
                refs.append(Ref(markdown, text[start:end], "", None, path, line_of(start),
                                target=spec, destination=destination.resolve()))
                link_spans.append((start, end))
            continue
        local = _local_path(path, spec, cfg.root)
        if (local is not None and link_admits(start) and not local.exists()
                and local.resolve().is_relative_to(cfg.root.resolve())):
            refs.append(Ref(link, text[start:end], "", None, path, line_of(start),
                            target=spec, destination=local))

    wiki = policies["wiki"]
    source, admits = view(wiki, link_spans)
    for m in EXPLICIT_RE.finditer(source):
        if _escaped(source, m.start()) or not admits(m.start()):
            continue
        target = m.group(1).strip()
        ns, name = glossary.split(target)
        # Path-shaped wiki-links are file refs, not terms — unless the name is
        # actually a defined term (`[[SKILL.md]]` in a repo that named that file).
        if _looks_like_path(target) and not (ns and "/" in ns) and not glossary.resolve(name, ns):
            continue
        refs.append(Ref(wiki, m.group(0), normalize(name), ns, path,
                        line_of(m.start()), target=name.strip()))

    delimiter = policies["delimiter"]
    source, admits = view(delimiter, link_spans)
    delim_spans: list[tuple[int, int]] = []
    for delim in cfg.delimiters:
        for m in delim.regex.finditer(source):
            if not admits(m.start()):
                continue
            raw_term = m.group(1)
            name = normalize(raw_term)
            if name in delim.except_names:
                continue
            if delim.only_known and name not in glossary.by_name:
                continue
            refs.append(Ref(delimiter, m.group(0), name, None, path,
                            line_of(m.start()), target=raw_term))
            delim_spans.append((m.start(), m.end()))

    # A ticket URL (`https://tracker/UB-9`) is an address, not an id reference.
    id_policy = policies["id"]
    source, admits = view(id_policy, link_spans)
    for pattern in cfg.id_patterns:
        for m in pattern.finditer(source):
            if admits(m.start()):
                refs.append(Ref(id_policy, m.group(0), m.group(0), None, path,
                                line_of(m.start()), target=m.group(0)))

    # Plain mentions of known terms/aliases (longest-first so multiword terms win).
    # A slug name (`grill-me`) needs a hyphen or underscore, so the phrase
    # "grill me" is prose; a spaced name (`issue tracker`) takes any separator.
    # Lookarounds, not `\b`, so names that start or end in punctuation (`C++`,
    # `.NET`) still match as whole words.
    names = sorted({_mention_pattern(n) for t in glossary.terms
                    for n in t.spellings or t.names()},
                   key=len, reverse=True)
    if names:
        mention = policies["mention"]
        mention_re = re.compile(r"(?<!\w)(" + "|".join(names) + r")(?!\w)", re.IGNORECASE)
        source, admits = view(mention, link_spans)
        explicit_spans = [(m.start(), m.end()) for m in EXPLICIT_RE.finditer(source)]
        claimed = _covers(explicit_spans + delim_spans + link_spans)
        # Labels of other links stay mentions (they still count as use) but
        # are linked.
        vocabulary = set(link_spans)
        in_label = _covers([(a, b) for a, b, _ in document.links if (a, b) not in vocabulary])
        for m in mention_re.finditer(source):
            if claimed(m.start()) or not admits(m.start()):
                continue
            refs.append(Ref(mention, m.group(0), normalize(m.group(0)), None,
                            path, line_of(m.start()), linked=in_label(m.start())))

    # Fences, inline code, and frontmatter are already blank in `prose`.
    heading_lines = [line_of(m.start()) for m in HEADING_RE.finditer(document.prose)]
    headings = set(heading_lines)
    for ref in refs:
        ref.section = bisect_right(heading_lines, ref.line)
        ref.heading = ref.line in headings
    return refs


def scan_docs(paths: list[Path], glossary: Glossary, cfg: Config,
              historical: set[Path] | None = None,
              invalid: list[tuple[Path, str]] | None = None) -> list[Ref]:
    hist = {p.resolve() for p in (historical or [])}
    refs: list[Ref] = []
    for p in sorted(paths):
        try:
            found = scan_file(p, glossary, cfg, invalid)
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
