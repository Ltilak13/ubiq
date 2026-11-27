"""Mermaid output for `ubiq graph --format mermaid` and `<!-- ubiq:graph -->` blocks (W009).

A document keeps a generated diagram between markers:

    <!-- ubiq:graph target=apply-ubiq kind=include -->
    ```mermaid
    flowchart LR
      apply-ubiq --> schema-workflow
    ```
    <!-- /ubiq:graph -->

`ubiq check` compares the fenced block with what `ubiq graph` would print for the same
selection and reports W009 where they differ. Markers inside fenced code blocks are
examples, not blocks to check.
"""

from __future__ import annotations

import re
import shlex
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from .check import Diagnostic
from .graph import KINDS, Edge

_OPEN = re.compile(r"^\s*<!--\s*ubiq:graph(?P<attrs>(?:\s[^>]*?)?)\s*-->\s*$")
_CLOSE = re.compile(r"^\s*<!--\s*/ubiq:graph\s*-->\s*$")
_FENCE = re.compile(r"^\s{0,3}(?P<mark>`{3,}|~{3,})\s*(?P<info>[^`]*)$")
_ATTRS = ("target", "kind", "depth", "callers")
_UNSAFE = re.compile(r"[^A-Za-z0-9_-]")
_LABEL_SPECIAL = re.compile(r'[#"&<>\r\n]')


def _node_ids(edges: list[Edge]) -> tuple[dict[str, str], list[str]]:
    """A Mermaid id per record, plus the records whose id differs from their name."""
    terms = {t.qualified: t for e in edges for t in (e.source, e.target)}
    ids: dict[str, str] = {}
    taken: set[str] = set()
    for qualified in sorted(terms):
        candidates = [_UNSAFE.sub("_", terms[qualified].term), _UNSAFE.sub("_", qualified)]
        # `end` closes a Mermaid subgraph, so it cannot name a node.
        pick = next((c for c in candidates if c and c.lower() != "end" and c not in taken), None)
        if pick is None:
            base, n = candidates[-1] or "node", 2
            pick = f"{base}_{n}"
            while pick in taken:
                n += 1
                pick = f"{base}_{n}"
        taken.add(pick)
        ids[qualified] = pick
    labelled = [q for q in sorted(ids) if ids[q] != terms[q].term]
    return ids, labelled


def _label(name: str) -> str:
    """Quote Mermaid label delimiters and preserve special characters as entities."""
    return _LABEL_SPECIAL.sub(lambda match: f"#{ord(match[0])};", name)


def render(edges: list[Edge]) -> list[str]:
    """A flowchart of `edges`: nodes and edges sorted, duplicates dropped.

    The edge kind labels an arrow only when the selection mixes kinds.
    """
    ids, labelled = _node_ids(edges)
    unique = sorted({(e.source.qualified, e.target.qualified, e.kind) for e in edges})
    mixed = len({kind for _, _, kind in unique}) > 1
    lines = ["flowchart LR"]
    lines += [f'  {ids[q]}["{_label(q)}"]' for q in labelled]
    for source, target, kind in unique:
        arrow = f"-->|{kind}|" if mixed else "-->"
        lines.append(f"  {ids[source]} {arrow} {ids[target]}")
    return lines


@dataclass
class Marker:
    line: int                       # the opening marker's line
    attrs: dict[str, str]
    problem: str = ""               # why the block cannot be checked
    body: list[str] = field(default_factory=list)  # the fenced block's lines
    body_line: int = 0              # the block's opening fence


def _attrs(raw: str) -> tuple[dict[str, str], str]:
    attrs: dict[str, str] = {}
    try:
        words = shlex.split(raw)
    except ValueError as exc:
        return attrs, f"unreadable attributes ({exc})"
    for word in words:
        key, sep, value = word.partition("=")
        if not sep or key not in _ATTRS or not value:
            return attrs, f"unknown attribute {word!r} (use {', '.join(f'{a}=' for a in _ATTRS)})"
        if key in attrs:
            return attrs, f"attribute {key!r} given twice"
        attrs[key] = value
    for kind in attrs.get("kind", "").split(","):
        if kind and kind not in KINDS:
            return attrs, f"unknown kind {kind!r} (use {', '.join(KINDS)})"
    if "depth" in attrs and not (attrs["depth"].isdigit() and int(attrs["depth"]) > 0):
        return attrs, "depth must be a positive integer"
    if attrs.get("callers", "true") != "true":
        return attrs, "callers takes only the value true"
    return attrs, ""


def _closes(line: str, opening: str) -> bool:
    m = _FENCE.match(line)
    return bool(m and not m["info"].strip() and m["mark"][0] == opening[0]
                and len(m["mark"]) >= len(opening))


def parse(text: str) -> list[Marker]:
    """Every `ubiq:graph` block outside fenced code, with its mermaid fence."""
    lines = text.splitlines()
    markers: list[Marker] = []
    fence: str | None = None
    i = 0
    while i < len(lines):
        line = lines[i]
        if fence is not None:
            if _closes(line, fence):
                fence = None
        elif (m := _FENCE.match(line)):
            fence = m["mark"]
        elif (opening := _OPEN.match(line)):
            attrs, problem = _attrs(opening["attrs"])
            marker = Marker(i + 1, attrs, problem)
            markers.append(marker)
            i = _read_block(lines, i, marker)
        i += 1
    return markers


def _read_block(lines: list[str], start: int, marker: Marker) -> int:
    """Fill `marker` from the lines after its opening marker; return the last line read."""
    end = next((j for j in range(start + 1, len(lines)) if _CLOSE.match(lines[j])), None)
    stop = next((j for j in range(start + 1, len(lines)) if _OPEN.match(lines[j])), None)
    if end is None or (stop is not None and stop < end):
        marker.problem = marker.problem or "no closing <!-- /ubiq:graph --> marker"
        return start
    block = lines[start + 1:end]
    first = next((n for n, text in enumerate(block) if text.strip()), None)
    opening = _FENCE.match(block[first]) if first is not None else None
    if first is None or not opening or opening["info"].strip() != "mermaid":
        marker.problem = marker.problem or "the marker must enclose a fenced mermaid block"
        return end
    tail = next((n for n in range(first + 1, len(block))
                 if _closes(block[n], opening["mark"])), None)
    if tail is None or any(text.strip() for text in block[tail + 1:]):
        marker.problem = marker.problem or "the marker must enclose exactly one fenced mermaid block"
        return end
    marker.body = block[first + 1:tail]
    marker.body_line = start + 1 + first + 1
    return end


def command(attrs: dict[str, str]) -> str:
    """The `ubiq graph` invocation that prints a marker's expected block."""
    parts = ["ubiq graph"]
    if "target" in attrs:
        parts.append(shlex.quote(attrs["target"]))
    parts += [f"--kind {k}" for k in attrs.get("kind", "").split(",") if k]
    if "depth" in attrs:
        parts.append(f"--depth {attrs['depth']}")
    if "callers" in attrs:
        parts.append("--callers")
    return " ".join(parts + ["--format mermaid"])


def check(docs: list[Path], select: Callable[[dict[str, str]], list[Edge]]) -> list[Diagnostic]:
    """W009 for each marked block that is unreadable or differs from the generated one.

    `select` returns the edges a marker's attributes pick, or raises LookupError.
    """
    diags: list[Diagnostic] = []
    for path in docs:
        if path.suffix.lower() not in (".md", ".markdown"):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if "ubiq:graph" not in text:
            continue
        for marker in parse(text):
            if marker.problem:
                diags.append(Diagnostic("W009", f"graph marker: {marker.problem}", path, marker.line))
                continue
            try:
                expected = render(select(marker.attrs))
            except LookupError as exc:
                diags.append(Diagnostic("W009", f"graph marker: {exc}", path, marker.line))
                continue
            if [s.rstrip() for s in marker.body] != expected:
                diags.append(Diagnostic(
                    "W009", "graph block differs from the records — replace it with the output of "
                    f"`{command(marker.attrs)}`", path, marker.body_line or marker.line))
    return diags
