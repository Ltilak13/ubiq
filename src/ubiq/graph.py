"""Composition edges between records, and the checks that edges can be followed.

Edge kinds:
  invoke   — a configured frontmatter field (default: ref_fields) names a record
             to run as its own step. Declared in the record or its overlay.
  route    — a configured field names a record the text points to without
             depending on it ("not for X; use Y"). Walks show it but stop there.
  reference — a configured field names an informational example or comparison.
              Walks show it but stop there.
  <edge>   — a schema property annotated `x-ubiq-ref` names a record in a namespace;
             the edge kind is the annotation's `edge` name (xref.py). Shown in walks,
             not followed.
  include  — a Markdown link to a record in a shared-part namespace, or one that
             lands, once installed, on another repository's record. Derived from
             the link, so authors don't declare the dependency twice.
"""
from __future__ import annotations

import os
import re
from collections import Counter
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import NamedTuple
from urllib.parse import unquote, urlsplit

from .check import Diagnostic, at
from .config import EdgeConfig
from .globs import Glob
from .records import Glossary, InvalidRecord, Term, parse_frontmatter
from .scan import (
    Ref,
    _blank_fences,
    _doc_link_path,
    _interpret_markdown,
    _line_index,
)

KINDS = ("invoke", "include", "route", "reference")
# Only invocation and inclusion require the target to run.
DEPENDS = frozenset({"invoke", "include"})


@dataclass(frozen=True)
class Edge:
    kind: str
    source: Term
    target: Term
    file: Path  # where the edge is declared or linked
    line: int
    name: str = ""  # the frontmatter field that declares it, when one does


def owners(glossary: Glossary, root: Path,
           installed: Sequence[Path] = ()) -> Callable[[Path], Term | None]:
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
    if r.edge:
        return r.edge
    if r.kind == "field":
        name = r.raw.split(":", 1)[0]
        if name in edges.invoke_fields:
            return "invoke"
        if name in edges.route_fields:
            return "route"
        if name in edges.reference_fields:
            return "reference"
        return None
    if r.kind == "markdown":
        return "include"
    return None


def build_edges(glossary: Glossary, refs: list[Ref], edges: EdgeConfig, root: Path,
                installed: Sequence[Path] = ()) -> list[Edge]:
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
        if source is None or (source is target and kind != "include"):
            continue
        name = r.raw.split(":", 1)[0] if r.kind == "field" else ""
        key = (kind, id(source), id(target), r.file, r.line, name)
        found.setdefault(key, Edge(kind, source, target, r.file, r.line, name))
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


def _meta(term: Term) -> dict:
    try:
        return parse_frontmatter(term.file, lenient=True)[0]
    except (OSError, InvalidRecord):
        return {}  # an unreadable record is already E005


def blocks_invoke(term: Term, blocked_by: str | None) -> bool:
    """True when the record sets its `edges.invoke.blocked_by` field: the model cannot invoke it."""
    return blocked_by is not None and str(_meta(term).get(blocked_by)).lower() == "true"


def _blocked_invokes(edges: list[Edge], cfg: EdgeConfig,
                     layout: Layout | None = None) -> list[Diagnostic]:
    """W003: an invoke edge to a record that the model cannot invoke."""
    diags = []
    for e in edges:
        target_cfg = layout.settings(e.target, cfg) if layout else cfg
        if e.kind == "invoke" and blocks_invoke(e.target, target_cfg.blocked_by):
            diags.append(Diagnostic(
                "W003", f"{e.source.qualified} invokes {e.target.qualified}, which sets "
                f"{target_cfg.blocked_by}: true — include its file or allow model invocation",
                e.file, e.line))
    return diags


def _drift(glossary: Glossary, refs: list[Ref], edges: list[Edge], cfg: EdgeConfig,
           owner) -> list[Diagnostic]:
    """W005: a record links another record without an edge, or declares one it never names.

    Both records must be in a `drift.ns` namespace: a glossary definition that
    contrasts two skills is not a skill depending on one. An edge in either
    direction counts, so a skill may name the skills that call it. Only explicit
    references (links, wiki-links, delimiters) count as undeclared: plain words
    such as "research" match skill names too often. Any reference, plain mentions
    included, satisfies a declared edge. Overlay prose describes the edges, so it
    is not the record's own text and counts for neither.
    """
    if not cfg.drift_ns:
        return []
    sidecars = {Path(p).resolve() for p in glossary.overlay_sources.values()}
    named: set[tuple[int, int]] = set()
    linked: dict[tuple[int, int], tuple[Ref, Term, Term]] = {}
    for r in refs:
        if r.kind in ("field", "catalog") or r.historical or r.file.resolve() in sidecars:
            continue
        source = owner(r.file)
        if source is None or source.ns not in cfg.drift_ns:
            continue
        matches = r.resolve(glossary)
        named.update((id(source), id(t)) for t in matches)
        if r.policy.links and len(matches) == 1:
            target = matches[0]
            if target is not source and target.ns in cfg.drift_ns:
                linked.setdefault((id(source), id(target)), (r, source, target))
    declared = {pair for e in edges for pair in ((id(e.source), id(e.target)),
                                                (id(e.target), id(e.source)))}
    fields = " or ".join((*cfg.invoke_fields, *cfg.route_fields, *cfg.reference_fields)) or "an edge field"
    diags = [Diagnostic("W005", f"{s.qualified} references {t.qualified} but declares no "
                        f"edge to it — add it to {fields}", r.file, r.line)
             for key, (r, s, t) in linked.items() if key not in declared]
    # A declared edge that drifts is about that edge, so its kind sets the severity.
    for e in edges:
        if (e.kind != "include" and e.source.ns in cfg.drift_ns and e.target.ns in cfg.drift_ns
                and (id(e.source), id(e.target)) not in named):
            diags += at(cfg.severity.get(e.kind), [Diagnostic(
                "W005", f"{e.source.qualified} declares {e.kind} {e.target.qualified} "
                "but never names it", e.file, e.line)])
    return sorted(diags, key=lambda d: (str(d.file), d.line, d.message))


def _declared_inputs(term: Term, name: str) -> dict[str, list[str]] | None:
    raw = _meta(term).get(name)
    if raw is None:
        return {}
    if not isinstance(raw, dict) or not raw or any(
            not isinstance(k, str) or not k.strip() or not isinstance(v, list) or not v
            or any(not isinstance(x, str) or not x.strip() for x in v)
            for k, v in raw.items()):
        return None
    return raw


def _part_inputs(glossary: Glossary, edges: list[Edge], cfg: EdgeConfig,
                 layout: Layout | None = None) -> list[Diagnostic]:
    """E012: an include names a declared value for each input of its part.

    A part lists enumerated inputs in frontmatter (`inputs: {mode: [new, existing]}`).
    The caller names a value as a code span followed by the input name, after the
    link and before the next link or line end: "Follow [x](x.md) in `new` mode."
    """
    diags: list[Diagnostic] = []
    declared: dict[int, dict[str, list[str]]] = {}
    terms = {id(t): t for t in [*glossary.terms, *(e.target for e in edges)]}
    for t in terms.values():
        target_cfg = layout.settings(t, cfg) if layout else cfg
        if t.ns not in target_cfg.include_ns:
            continue
        inputs = _declared_inputs(t, target_cfg.inputs)
        if inputs is None:
            diags.append(Diagnostic("E012", f"{t.qualified} {target_cfg.inputs}: expected a mapping "
                                    "of input names to lists of values", t.file))
        elif inputs:
            declared[id(t)] = inputs
    docs: dict[Path, tuple] = {}
    for e in edges:
        inputs = declared.get(id(e.target))
        if e.kind != "include" or not inputs:
            continue
        if e.file not in docs:
            text = e.file.read_text(encoding="utf-8")
            docs[e.file] = (text, _interpret_markdown(text).links, _line_index(text))
        text, links, line_of = docs[e.file]
        target = e.target.file.resolve()
        for start, end, spec in links:
            dest = _doc_link_path(e.file, spec)
            if line_of(start) != e.line or dest is None:
                continue
            matches = dest.resolve() == target
            if not matches and layout is not None and (home := layout.home(e.file)):
                landed, directory = layout.land(e.file, home, dest)
                owner = layout.external.get(directory) if directory is not None else None
                matches = landed is not None and owner is not None and owner(landed) is e.target
            if not matches:
                continue
            stop = min([s for s, _, _ in links if s >= end]
                       + [i if (i := text.find("\n", end)) >= 0 else len(text)])
            tail = text[end:stop]
            for name, values in inputs.items():
                m = re.search(rf"`([^`\n]+)`\s+{re.escape(name)}(?!\w)", tail)
                choices = ", ".join(values)
                if m is None:
                    diags.append(Diagnostic(
                        "E012", f"{e.source.qualified} includes {e.target.qualified} without "
                        f"a {name}; write `<value>` {name} after the link: {choices}",
                        e.file, e.line))
                elif m.group(1) not in values:
                    diags.append(Diagnostic(
                        "E012", f"{e.source.qualified} includes {e.target.qualified} with "
                        f"{name} `{m.group(1)}`; expected one of {choices}", e.file, e.line))
    return diags


@dataclass
class Repository:
    """An `edges.external` repository: its installed record files and its records.

    Its records are named `<name>/<ns>:<term>`, so they never collide with
    records here. Only its glossary is read, not its documents or edges.
    """
    name: str
    root: Path
    installed: list[Path]
    glossary: Glossary
    named: bool = False
    config: EdgeConfig | None = None
    qualify: bool = True

    def __post_init__(self):
        if self.qualify:
            for t in self.glossary.terms:
                t.repository = self.name


@dataclass
class Layout:
    """Where links land once installed.

    Each installed directory becomes a sibling under one root, keeping its name.
    Directories from `edges.external` repositories join the same root; a local
    directory wins a name, the way installers let a personal skill override a clone.
    """
    local: list[Path]  # installed record files in this repository
    homes: set[Path] = field(default_factory=set)
    by_name: dict[str, Path] = field(default_factory=dict)
    # Another repository's installed directory -> the owner of its files there.
    external: dict[Path, Callable[[Path], Term | None]] = field(default_factory=dict)
    repositories: list[Repository] = field(default_factory=list)
    # An external repository could not be read, so unknown names may live there.
    partial: bool = False
    unread: list[tuple[Path, str]] = field(default_factory=list)
    problems: list[Diagnostic] = field(default_factory=list)
    configurations: dict[int, EdgeConfig] = field(default_factory=dict)

    def settings(self, term: Term, default: EdgeConfig) -> EdgeConfig:
        if id(term) in self.configurations:
            return self.configurations[id(term)]
        return next((repo.config for repo in self.repositories
                     if repo.config is not None and any(t is term for t in repo.glossary.terms)), default)

    @classmethod
    def build(cls, local: list[Path], external: Sequence[Repository] = (),
              unread: Sequence[tuple[Path, str]] = ()) -> Layout:
        layout = cls(list(local), repositories=list(external))
        for d in sorted({f.resolve().parent for f in local}):
            if d.name in layout.by_name:
                # Both would install at the same path; links to that name are ambiguous.
                layout.problems.append(Diagnostic(
                    "W004", f"installed directories {layout.by_name[d.name]} and {d} "
                    f"share the name {d.name}/", d))
            layout.by_name.setdefault(d.name, d)
            layout.homes.add(d)
        dirs: dict[Path, Callable[[Path], Term | None]] = {}
        for repo in external:
            owner = owners(repo.glossary, repo.root, repo.installed)
            for f in repo.installed:
                dirs.setdefault(f.resolve().parent, owner)
        for d in sorted(dirs):
            if d.name not in layout.by_name:
                layout.by_name[d.name] = d
                layout.external[d] = dirs[d]
        layout.problems += [Diagnostic("W004", f"external repository {repo} {reason}; "
                                       "links into it are not checked", repo)
                            for repo, reason in unread]
        layout.partial, layout.unread = bool(unread), list(unread)
        return layout

    def home(self, doc: Path) -> Path | None:
        return next((d for d in doc.parents if d in self.homes), None)

    def covers_missing_link(self, doc: Path, spec: str) -> bool:
        """Whether W004 handles a destination missing from the source tree."""
        doc = doc.resolve()
        home, source = self.home(doc), _doc_link_path(doc, spec)
        if home is None or source is None or source.is_relative_to(home):
            return False
        landed, target = self.land(doc, home, source)
        return target in self.external or (landed is not None and landed.is_file())

    def land(self, doc: Path, home: Path, source: Path) -> tuple[Path | None, Path | None]:
        """The file a link from `doc` reaches once installed, and its installed directory.

        Agents normalize `..` against the installed path, so the link is resolved
        textually from `<root>/<home name>/...`.
        """
        rel = os.path.relpath(source, doc.parent)
        within = PurePosixPath(home.name) / doc.parent.relative_to(home).as_posix()
        # ("/", "<install root>", "<directory name>", ...rest)
        parts = PurePosixPath(os.path.normpath(str(PurePosixPath("/i") / within / rel))).parts
        target = self.by_name.get(parts[2]) if len(parts) > 3 and parts[1] == "i" else None
        return (target.joinpath(*parts[3:]) if target else None), target


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


class _Link(NamedTuple):
    """A Markdown link that leaves an installed directory."""
    doc: Path
    line: int
    spec: str
    home: Path  # the installed directory it leaves
    source: Path  # where it lands in the source tree
    landed: Path | None  # where it lands once installed
    target: Path | None  # the installed directory it lands in


def _leaving(docs: list[Path], layout: Layout) -> Iterator[_Link]:
    for doc in docs:
        doc = doc.resolve()
        home = layout.home(doc)
        if home is None:
            continue
        text = doc.read_text(encoding="utf-8")
        line_of = _line_index(text)
        for start, _, spec in _interpret_markdown(text).links:
            source = _doc_link_path(doc, spec)
            if source is None or source.is_relative_to(home):
                continue  # same file in both layouts
            yield _Link(doc, line_of(start), spec, home, source, *layout.land(doc, home, source))


def _install_layout(docs: list[Path], layout: Layout) -> list[Diagnostic]:
    """W004: a link that leaves an installed directory must land on a file in both
    layouts, or, for another repository's directory, in the installed one. A
    `#fragment` must name a heading in the file the agent reads once installed.
    """
    diags = list(layout.problems)
    for link in _leaving(docs, layout):
        landed, target = link.landed, link.target
        in_install = landed is not None and landed.is_file()
        in_source = link.source.is_file()
        where = None
        if target in layout.external:
            # A relative link can reach another repository only once installed.
            if not in_install:
                where = "resolves in neither layout"
        elif in_install != in_source:
            where = f"resolves only in {'the source tree' if in_source else 'the installed layout'}"
        if where:
            diags.append(Diagnostic("W004", f"link {link.spec} leaves {link.home.name}/ "
                                    f"and {where}", link.doc, link.line))
            continue
        fragment = unquote(urlsplit(link.spec.strip().strip("<>")).fragment)
        if (fragment and in_install and landed is not None and target is not None
                and fragment.lower() not in _slugs(landed)):
            diags.append(Diagnostic("W004", f"link {link.spec} names no heading in "
                                    f"{target.name}/{landed.relative_to(target).as_posix()}",
                                    link.doc, link.line))
    return diags


def cross_edges(docs: list[Path], layout: Layout, owner) -> list[Edge]:
    """Include edges for links that land, once installed, on another repository's record.

    No field here can name that record, so the link is the only declaration, and
    a relative link into another repository resolves only once installed, where
    the agent reads the text in place. That repository's own edges are not read,
    so a walk ends at its record.
    """
    found: dict[tuple, Edge] = {}
    for link in _leaving(docs, layout):
        other = layout.external.get(link.target) if link.target is not None else None
        if other is None or link.landed is None or not link.landed.is_file():
            continue  # a link that resolves nowhere is W004
        source, target = owner(link.doc), other(link.landed)
        if source is not None and target is not None:
            found.setdefault((id(source), id(target), link.doc, link.line),
                             Edge("include", source, target, link.doc, link.line))
    return list(found.values())


def across_repositories(refs: list[Ref], layout: Layout,
                        parts: tuple[Glob, ...] = ()) -> list[Ref]:
    """`refs` without Markdown links that only another repository resolves.

    The source tree cannot resolve a relative link into another repository, so
    W004 checks those links instead of E002. While an external repository is
    unreadable, a link to a directory name nobody here installs is unchecked too.
    An include link into `parts` stays unless it resolves once installed: one
    that resolves nowhere fails as E002 under any configuration.
    """
    if not layout.external and not layout.partial:
        return refs
    kept = []
    for r in refs:
        if r.kind == "markdown" and r.destination is not None and not r.destination.exists():
            doc = r.file.resolve()
            home = layout.home(doc)
            source = _doc_link_path(doc, r.target) if home else None
            if source is not None and home is not None and not source.is_relative_to(home):
                landed, target = layout.land(doc, home, source)
                include = any(glob.matches(r.destination) for glob in parts)
                if (target in layout.external or (target is None and layout.partial)) and (
                        not include or (landed is not None and landed.is_file())):
                    continue
        kept.append(r)
    return kept


def check_edges(glossary: Glossary, refs: list[Ref], cfg: EdgeConfig, root: Path,
                docs: list[Path], layout: Layout) -> list[Diagnostic]:
    owner = owners(glossary, root, layout.local)
    edges = build_edges(glossary, refs, cfg, root, layout.local) + cross_edges(docs, layout, owner)
    # W004 and a missing-edge W005 check links, not edges, so no edge kind sets them.
    return (at(cfg.severity.get("include"),
               _include_cycles(edges) + _part_inputs(glossary, edges, cfg, layout))
            + at(cfg.severity.get("invoke"), _blocked_invokes(edges, cfg, layout))
            + _install_layout(docs, layout)
            + _drift(glossary, refs, edges, cfg, owner))


def walk(edges: list[Edge], start: Term | None, callers: bool, depth: int | None) -> list[Edge]:
    """Edges reachable from `start` (all edges when None), following callers when asked.

    Route and reference edges are shown but not followed. Neither declares
    a dependency on the target.
    """
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
            if e.kind in DEPENDS and id(nxt(e)) not in seen:
                seen.add(id(nxt(e)))
                frontier.append(nxt(e))
        level += 1
    return shown
