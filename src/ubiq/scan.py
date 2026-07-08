"""Doc scanning: find references in markdown files.

Three kinds of reference:
  explicit  — [[term]] or [[ns:term]]           (must resolve, else E002/E003)
  id        — matches of configured id_patterns  (must resolve to a record id, else E004)
  mention   — plain-prose occurrence of a defined term or alias (indexed for
              `ubiq refs` and orphan detection; never an error)

Code spans and fenced code blocks are ignored so examples don't trip the linker.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .records import Glossary, normalize

# (?<!!) skips ![[...]] embeds/transclusions (Obsidian-style includes, not term refs)
EXPLICIT_RE = re.compile(r"(?<!!)\[\[([^\[\]|]+?)(?:\|[^\[\]]*)?\]\]")
FENCE_RE = re.compile(r"^(```|~~~).*?^\1\s*$", re.DOTALL | re.MULTILINE)
INLINE_CODE_RE = re.compile(r"`[^`\n]*`")


@dataclass
class Ref:
    kind: str  # "explicit" | "id" | "mention"
    raw: str   # text as written
    name: str  # normalized term (explicit/mention) or the id string
    ns: str | None
    file: Path
    line: int
    target: str = ""  # explicit refs: the target as written (for id fallback, e.g. [[T5]])


def _blank_out(text: str) -> str:
    """Replace code regions with spaces, preserving offsets/line numbers."""

    def blank(m: re.Match) -> str:
        return "".join(c if c == "\n" else " " for c in m.group(0))

    return INLINE_CODE_RE.sub(blank, FENCE_RE.sub(blank, text))


def _line_of(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


def scan_file(path: Path, glossary: Glossary, id_patterns: list[str],
              skip_frontmatter: bool = True) -> list[Ref]:
    text = path.read_text(encoding="utf-8")
    if skip_frontmatter:
        m = re.match(r"\A---\s*\n.*?\n---\s*\n?", text, re.DOTALL)
        if m:
            pad = "".join(c if c == "\n" else " " for c in m.group(0))
            text = pad + text[m.end():]
    clean = _blank_out(text)
    refs: list[Ref] = []

    for m in EXPLICIT_RE.finditer(clean):
        target = m.group(1).strip()
        if "/" in target:
            continue  # path-style link (file ref/transclusion), not a term reference
        ns, _, name = target.rpartition(":")
        refs.append(Ref("explicit", m.group(0), normalize(name),
                        normalize(ns) if ns else None, path, _line_of(clean, m.start()),
                        target=name.strip()))

    for pat in id_patterns:
        for m in re.finditer(pat, clean):
            refs.append(Ref("id", m.group(0), m.group(0), None, path,
                            _line_of(clean, m.start())))

    # Plain mentions of known terms/aliases (longest-first so multiword terms win).
    id_spans = [(r.file, r.line) for r in refs]  # cheap dedupe guard not needed; mentions never error
    names = sorted(glossary.by_name, key=len, reverse=True)
    if names:
        mention_re = re.compile(
            r"\b(" + "|".join(re.escape(n).replace(r"\ ", r"[\s_-]+") for n in names) + r")\b",
            re.IGNORECASE,
        )
        explicit_spans = [(m.start(), m.end()) for m in EXPLICIT_RE.finditer(clean)]
        for m in mention_re.finditer(clean):
            if any(a <= m.start() < b for a, b in explicit_spans):
                continue  # already counted as explicit
            refs.append(Ref("mention", m.group(0), normalize(m.group(0)), None,
                            path, _line_of(clean, m.start())))
    return refs


def scan_docs(paths: list[Path], glossary: Glossary,
              id_patterns: list[str]) -> list[Ref]:
    refs: list[Ref] = []
    for p in sorted(paths):
        refs.extend(scan_file(p, glossary, id_patterns))
    return refs
