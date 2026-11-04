"""Doc scanning: find references in markdown files.

Five kinds of reference:
  explicit  — [[term]] / [[ns:term]], plus configured delimiters (e.g. /term)
              (must resolve, else E002/E003)
  id        — matches of configured id_patterns  (must resolve to a record id, else E004)
  field     — values of configured ref_fields in a doc's frontmatter, e.g.
              solves: [T1] (must resolve by id or name, else E006)
  catalog   — values from a configured JSON/YAML inventory (must resolve, else E006)
  mention   — plain-prose occurrence of a defined term or alias (indexed for
              `ubiq refs` and orphan detection; never an error)

Refs from `historical` files still index mentions and resolved refs, but
unresolved explicit/id/field refs do not fail the build.

Fenced code blocks are never scanned. Inline code is ignored for wiki-links,
id patterns, and mentions — but configured delimiters *do* match inside
backticks, because that is how slash-commands are written (`/tdd`).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import yaml

from .records import FRONTMATTER_RE, Glossary, _parse_lenient, normalize

# field values that are placeholders, not references
SKIP_FIELD_VALUES = {"", "-", "—", "na", "n/a", "none", "no", "yes"}

# (?<!!) skips ![[...]] embeds/transclusions (Obsidian-style includes, not term refs)
EXPLICIT_RE = re.compile(r"(?<!!)\[\[([^\[\]|]+?)(?:\|[^\[\]]*)?\]\]")
FENCE_RE = re.compile(r"^(```|~~~).*?^\1\s*$", re.DOTALL | re.MULTILINE)
INLINE_CODE_RE = re.compile(r"`[^`\n]*`")
# GLOSSARY.md, SKILL.md, foo.json — wiki-link targets that are filenames, not terms
FILE_EXT_RE = re.compile(r"\.[A-Za-z][A-Za-z0-9]{0,7}$")
# [label](./file.md) — skip images ![alt](x)
MD_LINK_RE = re.compile(r"(?<!!)\[(?:[^\]]*)\]\(([^)]+)\)")
DOC_SUFFIXES = {".md", ".markdown"}

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
    spec = spec.strip().split()[0].strip("'\"")
    spec = spec.split("#")[0]
    if not spec or "://" in spec or spec.startswith(("mailto:", "#")):
        return None
    if not (_looks_like_path(spec) or FILE_EXT_RE.search(spec)):
        return None
    cand = Path(spec) if Path(spec).is_absolute() else (source.parent / spec)
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
    text = path.read_text(encoding="utf-8")
    fm = FRONTMATTER_RE.match(text)
    if fm:
        pad = "".join(c if c == "\n" else " " for c in fm.group(0))
        text = pad + text[fm.end():]
    clean = _blank_out(text)
    found: list[Path] = []
    seen: set[Path] = set()
    specs: list[str] = []
    for m in EXPLICIT_RE.finditer(clean):
        target = m.group(1).strip()
        if _looks_like_path(target):
            specs.append(target)
    for m in MD_LINK_RE.finditer(clean):
        specs.append(m.group(1))
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
    kind: str  # "explicit" | "id" | "field" | "mention" | "catalog"
    raw: str   # text as written
    name: str  # normalized term (explicit/mention) or the id string
    ns: str | None
    file: Path
    line: int
    target: str = ""  # explicit refs: the target as written (for id fallback, e.g. [[T5]])
    historical: bool = False  # historical docs: unresolved explicit/id/field do not fail


def _blank_out(text: str) -> str:
    """Replace code regions with spaces, preserving offsets/line numbers."""

    def blank(m: re.Match) -> str:
        return "".join(c if c == "\n" else " " for c in m.group(0))

    return INLINE_CODE_RE.sub(blank, FENCE_RE.sub(blank, text))


def _blank_fences(text: str) -> str:
    """Blank fenced blocks only — inline code stays, for delimiter matching."""

    def blank(m: re.Match) -> str:
        return "".join(c if c == "\n" else " " for c in m.group(0))

    return FENCE_RE.sub(blank, text)


def _line_of(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


def _field_refs(fm_text: str, path: Path, ref_fields: list[str],
                lenient: bool) -> list[Ref]:
    try:
        meta = yaml.load(fm_text, Loader=yaml.BaseLoader) or {}
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
              delimiters: list[Delimiter] | None = None) -> list[Ref]:
    text = path.read_text(encoding="utf-8")
    refs: list[Ref] = []
    fm = FRONTMATTER_RE.match(text)
    if fm and ref_fields:
        refs += _field_refs(fm.group(1), path, ref_fields, lenient)
    if skip_frontmatter and fm:
        pad = "".join(c if c == "\n" else " " for c in fm.group(0))
        text = pad + text[fm.end():]
    clean = _blank_out(text)
    for_delim = _blank_fences(text)

    for m in EXPLICIT_RE.finditer(clean):
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
    for delim in delimiters or []:
        for m in delim.regex.finditer(for_delim):
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
        skip_spans = explicit_spans + delim_spans
        for m in mention_re.finditer(clean):
            if any(a <= m.start() < b for a, b in skip_spans):
                continue  # already counted as explicit
            refs.append(Ref("mention", m.group(0), normalize(m.group(0)), None,
                            path, _line_of(clean, m.start())))
    return refs


def scan_docs(paths: list[Path], glossary: Glossary, id_patterns: list[str],
              ref_fields: list[str] | None = None,
              lenient: bool = False,
              delimiters: list[Delimiter] | None = None,
              historical: set[Path] | None = None) -> list[Ref]:
    hist = {p.resolve() for p in (historical or [])}
    refs: list[Ref] = []
    for p in sorted(paths):
        found = scan_file(p, glossary, id_patterns,
                          ref_fields=ref_fields, lenient=lenient,
                          delimiters=delimiters)
        if p.resolve() in hist:
            for r in found:
                r.historical = True
        refs.extend(found)
    return refs
