"""Composition edges between records, and the checks that edges can be followed.

Edge kinds:
  invoke   — a configured frontmatter field (default: ref_fields) names a record
             to run as its own step. Declared in the record or its overlay.
  include  — a Markdown link to a record in a shared-part namespace. Derived from
             the link, so authors don't declare the dependency twice.
"""
from __future__ import annotations

import os
from collections import Counter
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from .check import Diagnostic
from .config import EdgeConfig
from .records import Glossary, Term, parse_frontmatter
from .scan import Ref, _doc_link_path, _interpret_markdown, _line_index

KINDS = ("invoke", "include")


@dataclass(frozen=True)
class Edge:
    kind: str
    source: Term
    target: Term
    file: Path  # where the edge is declared or linked
    line: int


def owners(glossary: Glossary, root: Path, installed: list[Path] = ()):
    """Return path -> owning record: the record itself, its overlay, or the
    single record defined directly in an enclosing directory (a skill's siblings).

    The root never owns by directory. With `edges.install` set, only installed
    directories do, so a lone record in a shared folder such as docs/ owns nothing else.
    """
    by_file = {t.file.resolve(): t for t in glossary.terms}
    for source, overlay in glossary.overlay_sources.items():
        term = by_file.get(Path(source).resolve())
        if term is not None:
            by_file[Path(overlay).resolve()] = term
    records = [t.file.resolve() for t in glossary.terms]
    per_dir = Counter(f.parent for f in records)
    root = root.resolve()
    allowed = {f.resolve().parent for f in installed}
    by_dir = {f.parent: by_file[f] for f in records
              if per_dir[f.parent] == 1 and f.parent != root
              and (not allowed or f.parent in allowed)}

    def owner(path: Path) -> Term | None:
        p = path.resolve()
        if p in by_file:
            return by_file[p]
        for d in p.parents:
            if d in by_dir:
                return by_dir[d]
            if d == root:
                return None
        return None
    return owner


def _kind(r: Ref, edges: EdgeConfig) -> str | None:
    if r.kind == "field" and r.raw.split(":", 1)[0] in edges.invoke_fields:
        return "invoke"
    if r.kind == "markdown":
        return "include"
    return None


def build_edges(glossary: Glossary, refs: list[Ref], edges: EdgeConfig, root: Path,
                installed: list[Path] = ()) -> list[Edge]:
    owner = owners(glossary, root, installed)
    found: dict[tuple, Edge] = {}
    for r in refs:
        kind = _kind(r, edges)
        if kind is None or r.historical:
            continue
        targets = r.resolve(glossary)
        if len(targets) != 1:
            continue  # unresolved or ambiguous: E002/E003/E006 already report it
        target = targets[0]
        if kind == "include" and target.ns not in edges.include_ns:
            continue
        source = owner(r.file)
        if source is None or source is target:
            continue
        key = (kind, id(source), id(target), r.file, r.line)
        found.setdefault(key, Edge(kind, source, target, r.file, r.line))
    return list(found.values())


def _include_cycles(edges: list[Edge]) -> list[Diagnostic]:
    """E011: a part that includes itself, directly or through other parts."""
    out: dict[int, list[Edge]] = {}
    for e in edges:
        if e.kind == "include":
            out.setdefault(id(e.source), []).append(e)
    state: dict[int, int] = {}  # 1 = on the current path, 2 = done
    diags: list[Diagnostic] = []

    def visit(node: int, path: list[Edge]) -> None:
        state[node] = 1
        for e in out.get(node, []):
            nxt = id(e.target)
            if state.get(nxt) == 1:
                start = next(i for i, p in enumerate(path + [e]) if id(p.source) == nxt)
                loop = " -> ".join(p.source.qualified for p in (path + [e])[start:])
                diags.append(Diagnostic(
                    "E011", f"include cycle {loop} -> {e.target.qualified}", e.file, e.line))
            elif nxt not in state:
                visit(nxt, path + [e])
        state[node] = 2

    for node in list(out):
        if node not in state:
            visit(node, [])
    return diags


def _blocked_invokes(edges: list[Edge], cfg: EdgeConfig) -> list[Diagnostic]:
    """W003: an invoke edge to a record that the model cannot invoke."""
    if cfg.blocked_by is None:
        return []
    diags = []
    for e in edges:
        if e.kind != "invoke":
            continue
        try:
            meta, _ = parse_frontmatter(e.target.file, lenient=True)
        except (OSError, ValueError):
            continue
        if str(meta.get(cfg.blocked_by)).lower() == "true":
            diags.append(Diagnostic(
                "W003", f"{e.source.qualified} invokes {e.target.qualified}, which sets "
                f"{cfg.blocked_by}: true — include its file or allow model invocation",
                e.file, e.line))
    return diags


def _install_layout(docs: list[Path], installed: list[Path], root: Path) -> list[Diagnostic]:
    """W004: a link that leaves an installed directory resolves in only one layout.

    Installed directories become siblings under one root, keeping their names.
    Agents normalize `..` against the installed path, so the link must land in
    another installed directory there and in a real file in the source tree.
    """
    dirs = {f.resolve().parent for f in installed}
    by_name: dict[str, Path] = {}
    diags = []
    for d in sorted(dirs):
        if d.name in by_name:
            # Both would install at the same path; links to that name are ambiguous.
            diags.append(Diagnostic("W004", f"installed directories {by_name[d.name]} and {d} "
                                    f"share the name {d.name}/", d))
        by_name.setdefault(d.name, d)
    for doc in docs:
        doc = doc.resolve()
        home = next((d for d in doc.parents if d in dirs), None)
        if home is None:
            continue
        text = doc.read_text(encoding="utf-8")
        line_of = _line_index(text)
        for start, _, spec in _interpret_markdown(text).links:
            source = _doc_link_path(doc, spec)
            if source is None:
                continue
            if source.is_relative_to(home):
                continue  # same file in both layouts
            rel = os.path.relpath(source, doc.parent)
            within = PurePosixPath(home.name) / doc.parent.relative_to(home).as_posix()
            # ("/", "<install root>", "<directory name>", ...rest)
            parts = PurePosixPath(os.path.normpath(str(PurePosixPath("/i") / within / rel))).parts
            target = by_name.get(parts[2]) if len(parts) > 3 and parts[1] == "i" else None
            in_install = target is not None and target.joinpath(*parts[3:]).is_file()
            in_source = source.is_file()
            if in_install != in_source:
                where = "the source tree" if in_source else "the installed layout"
                diags.append(Diagnostic(
                    "W004", f"link {spec} leaves {home.name}/ and resolves only in {where}",
                    doc, line_of(start)))
    return diags


def check_edges(glossary: Glossary, refs: list[Ref], cfg: EdgeConfig, root: Path,
                docs: list[Path], installed: list[Path]) -> list[Diagnostic]:
    edges = build_edges(glossary, refs, cfg, root, installed)
    return (_include_cycles(edges) + _blocked_invokes(edges, cfg)
            + _install_layout(docs, installed, root))


def walk(edges: list[Edge], start: Term | None, callers: bool, depth: int | None) -> list[Edge]:
    """Edges reachable from `start` (all edges when None), following callers when asked."""
    if start is None:
        return edges
    step = (lambda e: id(e.target)) if callers else (lambda e: id(e.source))
    nxt = (lambda e: e.source) if callers else (lambda e: e.target)
    frontier, seen, shown = [start], {id(start)}, []
    level = 0
    while frontier and (depth is None or level < depth):
        ids = {id(t) for t in frontier}
        hop = [e for e in edges if step(e) in ids]
        shown += hop
        frontier = []
        for e in hop:
            if id(nxt(e)) not in seen:
                seen.add(id(nxt(e)))
                frontier.append(nxt(e))
        level += 1
    return shown
