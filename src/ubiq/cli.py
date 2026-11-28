"""ubiq CLI.

  ubiq init  [--root DIR]            infer asset schemas and scaffold grouped glossary metadata
  ubiq check [--root DIR] [--json]   lint the vocabulary; exit 1 on errors
  ubiq terms [--root DIR] [--format list|context] [--ns NS]
  ubiq refs TERM [--root DIR]        every place a term is used (traceability = search)
  ubiq discover [--root DIR] [--json] groups, schema proposals, and candidate contexts
  ubiq candidates [--root DIR] [--json] [--min-files N]
                                     marked names (candidate_shapes) in N+ docs with no record
  ubiq impact --since REV [--root DIR] [--json] [--depth N]
                                     changed records and the callers they affect
  ubiq compare --since REV [--root DIR] [--json | --markdown]
                                     new, resolved, and unchanged findings
  ubiq query [--kind KIND] [--domain DOMAIN] [--id ID] [--root DIR] [--json]
                                     select complete declared records with source evidence
  ubiq coverage [--since REV] [--root DIR] [--json | --markdown]
                                     how much selected content has typed metadata
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from collections.abc import Callable, Sequence
from contextlib import ExitStack
from dataclasses import dataclass, field, replace
from pathlib import Path

import yaml

from . import __version__, coverage, mermaid, query, readmes, review
from .candidates import find_candidates
from .catalog import CatalogError, catalog_cover_gaps, catalog_refs
from .check import Diagnostic, at, run_checks
from .config import Config, InvalidConfig, load_config
from .dependencies import Snapshots, validate_checkout
from .discovery import discover, init_assets
from .globs import Glob, GlobError, first_match
from .graph import KINDS as GRAPH_KINDS
from .graph import (
    Layout,
    Repository,
    _include_cycles,
    across_repositories,
    build_edges,
    check_edges,
    cross_edges,
    owners,
    walk,
)
from .kinds import KINDS
from .overlap import find_overlap
from .plan import cmd_plan
from .records import (
    ConflictingGlossary,
    Glossary,
    InvalidRecord,
    assemble_glossary,
    normalize,
)
from .scan import Ref, file_link_targets, scan_docs
from .schemas import assess_schemas
from .sync import cmd_sync


def _display_path(path: Path, root: Path) -> str:
    return str(path.relative_to(root) if path.is_relative_to(root) else path)


class ScanTrace:
    """Discovery evidence collected only when requested by explain."""

    def __init__(self, root: Path):
        self.root = root
        self.files: dict[str, dict] = {}
        self.unmatched: list[dict] = []

    def record(self, path: Path, role: str, *, pattern: str | None = None,
               source: Path | None = None, ignored_by: str | None = None):
        name = _display_path(path.resolve(), self.root)
        item = self.files.setdefault(name, {
            "file": name, "included": False, "historical": False,
            "exists": path.is_file(), "scanned": False, "reasons": []})
        reason = {"kind": role}
        if pattern is not None:
            reason["pattern"] = pattern
        if source is not None:
            reason["from"] = _display_path(source.resolve(), self.root)
        if ignored_by is not None:
            reason["ignored_by"] = ignored_by
        else:
            item["included"] = True
            item["historical"] |= role == "historical"
        if reason not in item["reasons"]:
            item["reasons"].append(reason)

    def result(self) -> dict:
        files = sorted(self.files.values(), key=lambda item: item["file"])
        for item in files:
            item["reasons"].sort(key=lambda reason: json.dumps(reason, sort_keys=True))
        return {"files": files, "unmatched": sorted(
            self.unmatched, key=lambda item: (item["kind"], item["pattern"]))}


def _ignored(path: Path, ignore: tuple[Glob, ...]) -> str | None:
    rule = first_match(ignore, path)
    return rule.pattern if rule else None


def _expand(globs: tuple[Glob, ...], ignore: tuple[Glob, ...],
            trace: ScanTrace | None = None, role: str = "docs") -> list[Path]:
    out: set[Path] = set()
    for glob in globs:
        matched = False
        # explain reports every ignored candidate, so it walks ignored directories.
        for path in glob.walk(ignore, prune=trace is None):
            if not path.is_file():
                continue
            matched = True
            ignored = _ignored(path, ignore)
            if trace is not None:
                trace.record(path, role, pattern=glob.pattern, ignored_by=ignored)
            if ignored is None:
                out.add(path)
        if not matched and trace is not None:
            item = {"kind": role, "pattern": glob.pattern}
            if item not in trace.unmatched:
                trace.unmatched.append(item)
    return sorted(out)


def _close_docs(root: Path, seeds: list[Path], ignore: tuple[Glob, ...],
                trace: ScanTrace | None = None) -> list[Path]:
    """Follow existing in-repo links while recording all encountered reasons."""
    seen = {path.resolve() for path in seeds}
    queue = sorted(seen)
    while queue:
        path = queue.pop()
        try:
            linked = file_link_targets(path, root)
        except (OSError, UnicodeError):
            continue
        for target in linked:
            key = target.resolve()
            ignored = _ignored(target, ignore)
            if trace is not None:
                trace.record(target, "link", source=path, ignored_by=ignored)
            if ignored is not None or key in seen:
                continue
            seen.add(key)
            queue.append(target)
    return sorted(seen, key=str)


@dataclass
class Build:
    glossary: Glossary
    refs: list[Ref]
    config: Config
    diagnostics: list[Diagnostic]  # assembly errors: catalogs, unreadable files
    docs: list[Path]               # every scanned document, resolved
    historical: set[Path]          # the historical subset of `docs`
    layout: Layout
    dependencies: list[Build] = field(default_factory=list)


def _glossary(cfg: Config, trace: ScanTrace | None = None) -> tuple[Glossary, list[Path]]:
    """The records that the glossary rules and overlays define, and the overlay files."""
    overlay_files = _expand(cfg.overlays, cfg.ignore, trace, "overlay")
    sources = [
        (path, rule.term_field, rule.ns, rule.label)
        for rule in cfg.glossary
        for path in _expand((rule.glob,), cfg.ignore, trace, "glossary")
    ]
    return assemble_glossary(cfg.root, sources, overlay_files, cfg.term_field, cfg.lenient,
                             ref_fields=cfg.ref_fields), overlay_files


def build(root: Path, trace: ScanTrace | None = None, cfg: Config | None = None, *,
          _loaded: dict[Path, Build] | None = None, _namespace: str | None = None,
          configs: dict[Path, Config] | None = None) -> Build:
    root = root.resolve()
    loaded = {} if _loaded is None else _loaded
    if root in loaded:
        return loaded[root]
    cfg = cfg or load_config(root)
    glossary, overlay_files = _glossary(cfg, trace)
    for term in glossary.terms:
        term.repository = _namespace
    result = Build(glossary, [], cfg, [], [], set(), Layout([]))
    loaded[root] = result

    def load_dependency(other: Config, name: str) -> Glossary:
        namespace = f"{_namespace}/{name}" if _namespace else name
        child = build(other.root, cfg=other, _loaded=loaded, _namespace=namespace, configs=configs)
        result.dependencies.append(child)
        return child.glossary

    layout = _layout(cfg, load_dependency, configs)
    result.layout = layout
    for repository in layout.repositories:
        glossary.add_external(repository.name, repository.glossary)

    if trace is not None:
        for term in glossary.terms:
            trace.record(term.file, "record")
        for source, overlay in glossary.overlay_sources.items():
            trace.record(source, "overlay-source", source=overlay)

    memberships, extra = readmes.declarations(cfg, glossary)
    doc_files = _expand(cfg.docs, cfg.ignore, trace, "docs")
    for membership in memberships:
        doc_files.append(membership.readme)
        if trace is not None:
            trace.record(membership.readme, "readme", source=membership.source)
    hist_files = _expand(cfg.historical, cfg.ignore, trace, "historical")
    hist_set = {p.resolve() for p in hist_files}
    # Sidecars are docs too, so their ref_fields (uses: [...]) participate.
    for p in [*overlay_files, *hist_files]:
        if p not in doc_files:
            doc_files.append(p)
    doc_files = _close_docs(root, doc_files, cfg.ignore, trace)
    if trace is not None:
        for path in doc_files:
            trace.files[_display_path(path, root)]["scanned"] = True
    refs = scan_docs(doc_files, glossary, cfg, historical=hist_set, invalid=glossary.invalid)

    extra.extend(readmes.check_membership(cfg, glossary, memberships, refs, hist_set))
    catalog = cfg.policies["catalog"]
    for spec in cfg.catalogs:
        if trace is not None:
            trace.record(spec.file, "catalog")
        if not spec.file.is_file():
            extra.append(Diagnostic("E005", f"catalog file not found: {spec.path}", spec.file))
            continue
        try:
            entry_errors: list[str] = []
            catalog_entries = catalog_refs(spec, catalog, entry_errors)
            extra.extend(Diagnostic("E005", msg, spec.file) for msg in entry_errors)
            refs.extend(catalog_entries)
            cover = _expand(spec.cover, cfg.ignore, trace, "cover")
            extra.extend(catalog_cover_gaps(catalog_entries, spec.file, glossary,
                                            set(cover), catalog))
        except CatalogError as e:
            extra.append(Diagnostic("E005", str(e), spec.file))

    if cfg.schemas:
        from .schemas import single_diagnostics, xref_refs
        refs.extend(xref_refs(cfg))
        from .step_refs import within_diagnostics
        extra.extend(within_diagnostics(cfg))
        extra.extend(single_diagnostics(cfg))
    if cfg.sync is not None:
        from .scenarios import diagnostics as scenario_diagnostics
        from .schemas import load_data as _load
        goals = []
        for record in cfg.sync.records:
            if record.kind != "goal":
                continue
            for path in sorted(record.glob.walk(cfg.ignore)):
                try:
                    goals.append((path, _load(path, frontmatter=True)))
                except (OSError, UnicodeError, ValueError, TypeError, yaml.YAMLError, RecursionError):
                    continue  # E009 reports it
        extra.extend(scenario_diagnostics(goals))
    result.refs.extend(refs)
    result.diagnostics.extend(extra)
    result.docs.extend(doc_files)
    result.historical.update(hist_set)
    if _loaded is None:
        configurations = {id(t): item.config.edges for item in loaded.values()
                          for t in item.glossary.terms}
        for item in loaded.values():
            item.layout.configurations = configurations
    return result


def _composition(built: Build) -> list[Build]:
    found: dict[Path, Build] = {}
    pending = [built]
    while pending:
        item = pending.pop()
        if item.config.root not in found:
            found[item.config.root] = item
            pending.extend(reversed(item.dependencies))
    return list(found.values())


def _composition_edges(built: Build) -> list:
    edges = []
    for item in _composition(built):
        layout, cfg = item.layout, item.config
        live = [path for path in item.docs if path not in item.historical]
        edges.extend(build_edges(item.glossary, item.refs, cfg.edges, cfg.root, layout.local))
        edges.extend(cross_edges(live, layout, owners(item.glossary, cfg.root, layout.local)))
    return edges


def _composition_path(path: Path, built: Build) -> str:
    for item in _composition(built):
        if path.is_relative_to(item.config.root):
            namespace = next((t.repository for t in item.glossary.terms), None)
            relative = path.relative_to(item.config.root).as_posix()
            return f"{namespace}/{relative}" if namespace else relative
    return str(path)


INIT_CONFIG = """\
# ubiq — a linker for prose. Docs: https://github.com/Ltilak13/ubiq
# Consuming repos keep linker files under .ubiq/ so they don't clutter the tree.
glossary:
  - ".ubiq/glossary/**/*.md"
docs:
  - "README.md"
  - "AGENTS.md"
  - "CLAUDE.md"
  - "CONTEXT.md"
  - ".agents/**/*.md"
  - ".ubiq/**/*.md"
  - "docs/**/*.md"
historical:
  - "CHANGELOG.md"
# Patterns start at the repo root; `**/` also ignores nested copies.
ignore:
  - "**/.git/**"
  - "**/node_modules/**"
  - "**/.venv/**"
id_patterns: []
ref_fields: []
overlays:
  - ".ubiq/overlays/**/*.md"
# catalogs:
#   - file: ".claude-plugin/plugin.json"
#     items: skills
#     term: basename
#     cover:
#       - "skills/engineering/**/SKILL.md"
# delimiters:
#   - pattern: "/"
#     only_known: true
#     except: [plugin]
# unlinked_mentions: warn     # W002: a section mentions a term but never links it
# unlinked_except: [pr]       # terms that are ordinary words in this repo
# references:                 # per-kind overrides: severity error|warn|off, scans
#   id: {severity: warn}      # report unknown ids without failing the check
#   wiki: {scans: [comment]}  # regions: inline_code, address, comment
"""

INIT_RECORD = """\
---
term: glossary record
aliases: [record]
---

A markdown file that defines exactly one term. The frontmatter carries `term`,
optional `aliases`, `ns` (namespace), and `id`; the body is the definition.
Link to this file from your docs, for example
`[glossary record](.ubiq/glossary/glossary-record.md)` from the repo root.
Wiki-links such as `[[glossary record]]` also work. Missing references fail
`ubiq check`. Delete this example once you have real terms.
"""


def cmd_init(args) -> int:
    root = Path(args.root).resolve()
    cfg = root / "ubiq.yaml"
    gdir = root / ".ubiq" / "glossary"
    if cfg.exists() or cfg.is_symlink():
        print(f"{cfg} already exists — not touching it", file=sys.stderr)
        return 1
    try:
        root.mkdir(parents=True, exist_ok=True)
        report = discover(root)
        config = yaml.safe_load(INIT_CONFIG)
        writes = init_assets(root, report, config)
        for path in writes:
            if path.exists() or path.is_symlink():
                print(f"{path} already exists — not touching it", file=sys.stderr)
                return 1
            if any(parent.is_symlink() for parent in path.parents if parent != root and parent.is_relative_to(root)):
                print(f"{path} has a symlink parent — not touching it", file=sys.stderr)
                return 1
        example = gdir / "glossary-record.md"
        if example.is_symlink() or gdir.is_symlink() or (root / ".ubiq").is_symlink():
            print("glossary path is a symlink — not touching it", file=sys.stderr)
            return 1
        if not example.exists():
            writes[example] = INIT_RECORD
        writes[cfg] = (yaml.safe_dump(config, sort_keys=False) if report['groups'] or report['glossaries']
                       else INIT_CONFIG)
        for path, content in writes.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
    except (OSError, InvalidRecord) as exc:
        print(f"cannot initialize: {exc}", file=sys.stderr)
        return 1
    print(f"wrote {cfg.relative_to(root)} and glossary metadata")
    if report['contexts']:
        print("review .ubiq/discovery.json: directory groups are candidate contexts, not confirmed domain boundaries")
    print("next: `ubiq check` — then add one record per term your docs rely on")
    return 0


def cmd_discover(args) -> int:
    root = Path(args.root).resolve()
    if not root.is_dir():
        print(f"repository directory does not exist: {root}", file=sys.stderr)
        return 1
    try:
        report = discover(root)
    except (OSError, InvalidRecord) as exc:
        print(f"cannot discover repository: {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        for path, families in report['groups'].items():
            print(f"{path}/")
            for family, sources in families.items():
                for source in sources:
                    print(f"  {family}: {source}")
        for schema in report['schemas']:
            field = schema["term_field"] or "review required"
            print(f"schema: {schema['path']} ({schema['storage']}, term_field={field}, ns={schema['ns']})")
        for context in report['contexts']:
            print(f"context candidate: {context['path']} ({context['evidence']})")
        print("Review candidates against domain language and ownership before assigning namespaces.")
    return 0


def _diagnostics_json(diags: list[Diagnostic], root: Path) -> list[dict]:
    return [{"code": d.code, "message": d.message,
             "file": _display_path(d.file, root), "line": d.line,
             "severity": "error" if d.is_error else "warning"} for d in diags]


def _report(diags: list[Diagnostic], root: Path, as_json: bool,
            terms: int = 0, refs: int = 0) -> int:
    errors = sum(d.is_error for d in diags)
    if as_json:
        print(json.dumps({
            "terms": terms, "refs": refs, "errors": errors,
            "warnings": len(diags) - errors,
            "diagnostics": _diagnostics_json(diags, root),
        }, indent=2))
    else:
        for diag in diags:
            print(diag.render())
        print(f"{'FAIL' if errors else 'OK'}: {terms} terms, {refs} refs, "
              f"{errors} errors, {len(diags) - errors} warnings")
    return 1 if errors else 0


def _assembly_errors(glossary, extra) -> list[Diagnostic]:
    return [*extra, *(Diagnostic("E005", message, path)
                      for path, message in glossary.invalid)]


def cmd_check(args) -> int:
    root = Path(args.root).resolve()
    diags, terms, refs = _check(root)
    return _report(diags, root, args.json, terms, refs)


def _check(root: Path, cfg: Config | None = None,
           configs: dict[Path, Config] | None = None) -> tuple[list[Diagnostic], int, int]:
    """Every check diagnostic, with the term and reference counts."""
    result = build(root, cfg=cfg, configs=configs)
    composition = _composition(result)
    diags = [diag for item in composition for diag in _check_build(item)]
    cycles = _include_cycles(_composition_edges(result))
    cycles = [diag for item in composition for diag in at(item.config.edges.severity.get("include"),
              [d for d in cycles if d.file in item.docs])]
    diags.extend(_graph_blocks(result))
    existing = {(d.code, d.message, d.file, d.line) for d in diags}
    diags.extend(d for d in cycles if (d.code, d.message, d.file, d.line) not in existing)
    return diags, len(result.glossary.terms), len(result.refs)


def _graph_blocks(built: Build) -> list[Diagnostic]:
    """W009: marked mermaid blocks in this repository's live docs that differ from its graph."""
    def select(attrs: dict[str, str]) -> list:
        kinds = [k for k in attrs.get("kind", "").split(",") if k]
        return _select_edges(built, attrs.get("target"), kinds, "callers" in attrs,
                             int(attrs["depth"]) if "depth" in attrs else None)[1]
    live = [p for p in built.docs if p not in built.historical and p.is_relative_to(built.config.root)]
    return mermaid.check(live, select)


def _check_build(result: Build) -> list[Diagnostic]:
    glossary, cfg = result.glossary, result.config
    root = cfg.root
    layout = result.layout
    refs = [r for r in across_repositories(result.refs, layout,
                                           tuple(r.glob for r in cfg.part_rules))
            if not (r.kind == "link" and layout.covers_missing_link(r.file, r.target))]
    skip_mentions = {path.resolve() for path in glossary.overlay_sources.values()}
    # A consuming repository does not own dependency prose reached through links.
    # Keep explicit references checked; only plain-mention suggestions stay local.
    skip_mentions.update(path.resolve() for path in result.docs
                         if not path.resolve().is_relative_to(root))
    diags = result.diagnostics + run_checks(
        glossary, refs, cfg.external_id_patterns,
        skip_unlinked=skip_mentions, unlinked_except=cfg.unlinked_except, lenient=cfg.lenient)
    if cfg.schemas:
        from .schemas import check_schemas
        diags.extend(check_schemas(cfg, glossary))
        from .cycles import check_cycles
        diags.extend(check_cycles(cfg, glossary))
    live = [path for path in result.docs if path not in result.historical]
    diags.extend(check_edges(glossary, refs, cfg.edges, root, live, layout))
    return diags


def _installed(cfg: Config) -> list[Path]:
    return _expand(cfg.edges.install, cfg.ignore, None, "install")


def _layout(cfg: Config, load: Callable[[Config, str], Glossary] | None = None,
            configs: dict[Path, Config] | None = None) -> Layout:
    """Assemble installed files and records, using the composition loader for named dependencies."""
    external, unread = [], []
    names = Counter(dep.path.resolve().name for dep in cfg.edges.external)
    for dependency in cfg.edges.external:
        repo = dependency.path
        name = dependency.name or repo.resolve().name
        name = name if dependency.name or names[name] == 1 else str(repo.resolve())
        if not repo.is_dir():
            if dependency.name is not None:
                if dependency.required or repo.exists():
                    raise InvalidConfig(f"dependency {dependency.name!r} at {repo}: checkout directory not found")
                continue
            unread.append((repo, "was not found"))
            continue
        try:
            other = (configs or {}).get(repo.resolve()) or load_config(repo.resolve())
            glossary = load(other, name) if load and dependency.name else _glossary(other)[0]
            if dependency.name is not None and glossary.invalid:
                raise InvalidConfig(f"dependency {dependency.name!r}: {glossary.invalid}")
            files = _installed(other)
            if dependency.revision:
                memberships, _ = readmes.declarations(other, glossary)
                readme_files = [membership.readme for membership in memberships]
                docs = _close_docs(other.root, [*_expand(other.docs, other.ignore), *readme_files],
                                   other.ignore)
                validate_checkout(dependency, other,
                                  [*docs, *readme_files, *files, *(t.file for t in glossary.terms),
                                   *glossary.overlay_sources, *glossary.overlay_sources.values()])
        except GlobError as exc:
            if dependency.name is not None:
                raise InvalidConfig(f"dependency {dependency.name!r} at {repo}: {exc}") from exc
            unread.append((repo, f"cannot be scanned ({exc})"))
            continue
        except (InvalidConfig, ConflictingGlossary) as exc:
            if dependency.name is not None:
                raise InvalidConfig(f"dependency {dependency.name!r} at {repo}: {exc}") from exc
            unread.append((repo, f"has invalid configuration ({exc})"))
            continue
        if not files and dependency.name is None:
            unread.append((repo, "installs nothing (no edges.install match)"))
        # Records take the directory name, or the full path when two repositories share it.
        external.append(Repository(name, repo, files, glossary, dependency.name is not None,
                                   other.edges, not (load and dependency.name)))
    return Layout.build(_installed(cfg), external, unread)


def _resolve_one(glossary, query: str, others: Sequence[Repository] = ()):
    """The one record `query` names. A name defined here wins, as its directory
    does once installed; `<repository>/<name>` names another repository's record."""
    def find(g: Glossary, q: str) -> list:
        ns, name = g.split(q)
        return g.resolve(name, ns)
    prefixed = [(r.glossary, query[len(r.name) + 1:]) for r in others
                if query.startswith(f"{r.name}/")]
    matches = find(*prefixed[0]) if prefixed else (
        find(glossary, query) or [t for r in others if not r.named for t in find(r.glossary, query)])
    matches = list({id(t): t for t in matches}.values())
    if len(matches) != 1:
        found = ", ".join(t.qualified for t in matches) or "no record"
        raise LookupError(f"{query!r} must name one record ({found})")
    return matches[0]


def _select_edges(built: Build, target, kinds, callers: bool, depth):
    """The walk's start record and the composition edges it shows."""
    edges = _composition_edges(built)
    if kinds:
        # A kind selects its edges, and a field name selects the edges that field declares.
        edges = [e for e in edges if e.kind in kinds
                 or (e.name in kinds and e.name not in GRAPH_KINDS)]
    start = _resolve_one(built.glossary, target, built.layout.repositories) if target else None
    return start, walk(edges, start, callers, depth)


def cmd_graph(args) -> int:
    root = Path(args.root).resolve()
    built = build(root)
    errors = _assembly_errors(built.glossary, built.diagnostics)
    if errors:
        return _report(errors, root, args.json)
    if args.kind:
        from .schemas import edge_names
        edges = _composition_edges(built)
        known = {*GRAPH_KINDS, *built.config.ref_fields, *edge_names(built.config),
                 *(e.kind for e in edges), *(e.name for e in edges if e.name)}
        unknown = sorted(set(args.kind) - known)
        if unknown:
            print(f"error: unknown edge kind {', '.join(unknown)}; expected one of "
                  f"{', '.join(sorted(known))}", file=sys.stderr)
            return 2
    try:
        start, shown = _select_edges(built, args.target, args.kind, args.callers, args.depth)
    except LookupError as exc:
        print(json.dumps({"error": str(exc)}) if args.json else f"error: {exc}")
        return 1
    if args.format == "mermaid":
        if args.json:
            print("error: --format mermaid cannot be combined with --json", file=sys.stderr)
            return 2
        print("\n".join(mermaid.render(shown)))
        return 0
    if args.json:
        print(json.dumps({"target": start.qualified if start else None,
                          "view": "callers" if args.callers else "dependencies",
                          "count": len(shown), "edges": [
            {"kind": e.kind, "source": e.source.qualified, "target": e.target.qualified,
             "file": _composition_path(e.file, built), "line": e.line} for e in shown]}, indent=2))
    else:
        for e in shown:
            print(f"{e.source.qualified} -{e.kind}-> {e.target.qualified}"
                  f"  {_composition_path(e.file, built)}:{e.line}")
        print(f"{len(shown)} edge{'s' if len(shown) != 1 else ''}")
    return 0


def _side(name: str, root: Path, cfg: Config | None = None,
          configs: dict[Path, Config] | None = None) -> review.Side:
    """One side of a change review: its records, dependency edges, and gaps."""
    built = build(root, cfg=cfg, configs=configs)
    layout = built.layout
    owner = owners(built.glossary, root, layout.local)
    edges = _composition_edges(built)
    composition = _composition(built)
    side = review.Side(name, root.resolve(), {t.qualified: t for item in composition for t in item.glossary.terms},
                       owner, edges, {}, [gap for item in composition for gap in item.layout.unread])
    for item in composition:
        namespace = next((t.repository for t in item.glossary.terms), None)
        if namespace:
            side.locations[item.config.root] = namespace
        for dependency in item.config.edges.external:
            if dependency.name:
                key = f"{namespace}/{dependency.name}" if namespace else dependency.name
                side.dependencies[key] = dependency.revision
    for item in composition:
        for diag in _assembly_errors(item.glossary, item.diagnostics):
            side.invalid.setdefault(side.rel(diag.file), diag.message)
    return side


def _baseline_config(base_root: Path, head_root: Path) -> Config:
    """Locate baseline dependency declarations relative to the original checkout.

    Historical review replaces named dependencies with snapshots after this step.
    """
    try:
        cfg = load_config(base_root)
    except (InvalidConfig, ConflictingGlossary) as exc:
        raise review.BaselineError(f"baseline configuration cannot load: {exc}") from exc
    external = tuple(replace(dep, path=head_root / dep.path.relative_to(base_root))
                     if dep.path.is_relative_to(base_root) else dep for dep in cfg.edges.external)
    return replace(cfg, edges=replace(cfg.edges, external=external))


def _review_error(message: str, as_json: bool) -> int:
    print(json.dumps({"error": message}, indent=2) if as_json else f"error: {message}")
    return 2


def cmd_impact(args) -> int:
    root = Path(args.root).resolve()
    try:
        baseline = review.resolve_baseline(root, args.since)
        files = review.changed_files(baseline)
        with ExitStack() as stack:
            base_root = stack.enter_context(review.checkout(baseline))
            snapshots = Snapshots(stack)
            try:
                cfg = snapshots.prepare(_baseline_config(base_root, root), root)
                base = _side("baseline", base_root, cfg, snapshots.configs)
                base.unread.extend(snapshots.unread)
            except (InvalidConfig, GlobError, ConflictingGlossary) as exc:
                raise review.BaselineError(f"baseline cannot be built: {exc}") from exc
            try:
                head = _side("head", root)
            except (InvalidConfig, ConflictingGlossary, GlobError) as exc:
                raise review.BaselineError(f"head cannot be built: {exc}") from exc
            changes = review.classify(files, base, head)
            affected = review.affected(changes, base, head, args.depth)
            gaps = review.incomplete(base, head)
    except review.BaselineError as exc:
        return _review_error(str(exc), args.json)
    if args.json:
        print(json.dumps({"baseline": baseline.as_json(), "complete": not gaps,
                          "incomplete": gaps,
                          "changed_files": [c.as_json() for c in files],
                          "changed": [c.as_json() for c in changes],
                          "affected": affected}, indent=2))
        return 0
    print(f"baseline {args.since} ({baseline.commit[:12]})")
    for c in changes:
        note = f" (from {c.source})" if c.source else ""
        print(f"{c.change} {c.record}{note}  {', '.join(c.files)}")
    for a in affected:
        chain = " ".join(f"-{e['kind']}-> {e['target']}" for e in a["via"])
        where = ", ".join(f"{e['file']}:{e['line']}" for e in a["via"])
        side = " (baseline)" if a["via"][0]["side"] == "baseline" else ""
        print(f"affected {a['record']} {chain}{side}  {where}")
    for gap in gaps:
        print(f"incomplete ({gap['side']}) {gap['file']}: {gap['reason']}")
    print(f"{len(files)} files, {len(changes)} records changed, {len(affected)} affected"
          + ("" if not gaps else f", INCOMPLETE: {len(gaps)} gap{'s' * (len(gaps) != 1)}"))
    return 0


def _findings(diags: list[Diagnostic], root: Path) -> list[dict]:
    return [coverage.finding(d, root) for d in diags]


def _as_head(findings: list[dict], base_root: Path, baseline: review.Baseline,
             root: Path, renamed: dict[str, str]) -> list[dict]:
    """Baseline findings named as the head names them. The temporary checkout
    stands for the real repository: its root and top level (reached through
    in-repo links) take the real paths, and renamed files take their head path."""
    tree = str(base_root)[:-len(baseline.prefix) - 1] if baseline.prefix else str(base_root)
    for f in findings:
        for temp, real in ((str(base_root), str(root)), (tree, str(baseline.toplevel))):
            f["message"] = f["message"].replace(temp, real)
            if f["file"].startswith(temp + "/"):
                f["file"] = _display_path(Path(real + f["file"][len(temp):]), root)
        f["file"] = renamed.get(f["file"], f["file"])
    return findings


def cmd_compare(args) -> int:
    root = Path(args.root).resolve()
    try:
        baseline = review.resolve_baseline(root, args.since)
        renamed = {c.source: c.file for c in review.changed_files(baseline) if c.source}
        with ExitStack() as stack:
            base_root = stack.enter_context(review.checkout(baseline))
            snapshots = Snapshots(stack)
            try:
                cfg = snapshots.prepare(_baseline_config(base_root, root), root)
                if snapshots.unread:
                    raise review.BaselineError("; ".join(reason for _, reason in snapshots.unread))
                base_diags, _, _ = _check(base_root, cfg, snapshots.configs)
            except (InvalidConfig, GlobError, ConflictingGlossary) as exc:
                raise review.BaselineError(f"baseline cannot be checked: {exc}") from exc
            findings = _findings(base_diags, base_root)
            for finding in findings:
                for temporary, original in snapshots.originals.items():
                    finding["file"] = finding["file"].replace(str(temporary), str(original))
                    finding["message"] = finding["message"].replace(str(temporary), str(original))
            base = _as_head(findings, base_root, baseline, root, renamed)
        try:
            head = _findings(_check(root)[0], root)
        except (InvalidConfig, ConflictingGlossary, GlobError) as exc:
            raise review.BaselineError(f"head cannot be checked: {exc}") from exc
    except review.BaselineError as exc:
        result = {"status": "unavailable", "reason": str(exc)}
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print(f"{'**ubiq:** ' if args.markdown else ''}comparison unavailable: {exc}")
        return 2
    new, resolved, unchanged = review.compare_findings(base, head)
    if args.json:
        print(json.dumps({"baseline": baseline.as_json(), "status": "ok",
                          "counts": {"new": len(new), "resolved": len(resolved),
                                     "unchanged": len(unchanged)},
                          "new": new, "resolved": resolved, "unchanged": unchanged}, indent=2))
    else:
        print(review.summary(new, resolved, unchanged, markdown=args.markdown))
    return 1 if any(f["severity"] == "error" for f in new) else 0


def _coverage_baseline(root: Path, rev: str) -> tuple[dict, dict | None]:
    """(baseline summary, baseline report). The report is None when the baseline
    has no coverage section; each side uses its own configuration."""
    baseline = review.resolve_baseline(root, rev)
    renamed = {c.source: c.file for c in review.changed_files(baseline) if c.source}
    summary = baseline.as_json()
    with review.checkout(baseline) as base_root:
        cfg = _baseline_config(base_root, root)
        if cfg.coverage is None:
            return {**summary, "status": "unconfigured"}, None
        try:
            built = build(base_root, cfg=replace(cfg, edges=replace(cfg.edges, external=())))
            report = coverage.measure(built.config, built.glossary, git=False, suggest=False)
        except (GlobError, ConflictingGlossary, coverage.MeasurementError) as exc:
            raise review.BaselineError(f"baseline cannot be measured: {exc}") from exc
        _as_head(report["diagnostics"], base_root, baseline, root, renamed)
        for f in report["files"]:
            f["file"] = renamed.get(f["file"], f["file"])
        for gap in report["incomplete"]:
            gap["file"] = renamed.get(gap["file"], gap["file"])
            gap["reason"] = gap["reason"].replace(str(base_root), str(root))
    return {**summary, "status": report["status"]}, report


def cmd_coverage(args) -> int:
    root = Path(args.root).resolve()
    code = 2
    try:
        cfg = load_config(root)
        if cfg.coverage is None:
            report = coverage.unavailable("coverage is not configured", coverage.GUIDANCE)
        else:
            built = build(root, cfg=replace(cfg, edges=replace(cfg.edges, external=())))
            report = coverage.measure(built.config, built.glossary)
            if args.since:
                summary, base = _coverage_baseline(root, args.since)
                coverage.attach_baseline(report, summary, base)
            code = coverage.evaluate(report, cfg.coverage, args.since)
    except (InvalidConfig, ConflictingGlossary, GlobError, coverage.MeasurementError) as exc:
        report = coverage.unavailable(f"{exc}")
    except review.BaselineError as exc:
        report = coverage.unavailable(f"baseline unavailable: {exc}")
    print(json.dumps(report, indent=2) if args.json
          else coverage.render(report, markdown=args.markdown))
    return code


def _query_repositories(cfg: Config, args) -> dict:
    loaded: dict[Path, query.Corpus] = {}
    load_errors: dict[Path, str] = {}
    accepted: dict[Path, query.Corpus] = {}
    entries: list[dict] = []
    failures: list[dict] = []

    def load(root: Path) -> query.Corpus:
        if root in load_errors:
            raise InvalidConfig(load_errors[root])
        if root not in loaded:
            try:
                other = cfg if root == cfg.root else load_config(root)
                glossary, overlays = _glossary(other)
                loaded[root] = query.Corpus(other, glossary,
                                           assess_schemas(other, glossary, retain_scan_errors=True), overlays)
            except (InvalidConfig, ConflictingGlossary, OSError, UnicodeError, RuntimeError) as exc:
                load_errors[root] = str(exc)
                raise
        return loaded[root]

    def unavailable(entry: dict, message: str) -> None:
        entry.update(status='unavailable', reason=message)
        failures.append({'code': 'Q001', 'repository': entry['root'], 'file': 'ubiq.yaml',
                         'name': entry['name'], 'message': message})

    declarations = list(cfg.edges.external)
    if args.repository is not None:
        declarations = [dep for dep in declarations if dep.name == args.repository]
        if not declarations:
            failures.append({'code': 'Q001', 'repository': str(cfg.root), 'file': 'ubiq.yaml',
                             'message': f'unknown configured repository: {args.repository}'})
    else:
        entry = {'name': None, 'root': str(cfg.root), 'local': True, 'required': True,
                 'revision': None, 'observed_revision': query._repository(cfg.root)['revision'],
                 'status': 'available'}
        entries.append(entry)
        try:
            accepted[cfg.root] = load(cfg.root)
        except (InvalidConfig, ConflictingGlossary, OSError, UnicodeError, RuntimeError) as exc:
            unavailable(entry, str(exc))
    for dependency in declarations:
        entry = {'name': dependency.name, 'root': str(dependency.path), 'local': False,
                 'required': dependency.required, 'revision': dependency.revision,
                 'observed_revision': None, 'status': 'available'}
        entries.append(entry)
        try:
            # Only a genuinely absent optional named checkout can be skipped.
            # Existing files, broken symlinks, and unreadable paths remain failures.
            try:
                dependency.path.lstat()
            except FileNotFoundError:
                entry['root'] = str(dependency.path.resolve())
                if dependency.name is not None and not dependency.required and args.repository is None:
                    entry.update(status='skipped_optional', reason='optional checkout is absent')
                    continue
                raise InvalidConfig(f'dependency {dependency.name!r}: checkout directory not found') from None
            root = dependency.path.resolve()
            entry['root'] = str(root)
            if not root.is_dir():
                raise InvalidConfig(f'dependency {dependency.name!r}: checkout directory not found')
            entry['observed_revision'] = query._repository(root)['revision']
            corpus = load(root)
            if corpus.glossary.invalid:
                raise InvalidConfig(f'dependency {dependency.name!r}: {corpus.glossary.invalid}')
            if dependency.revision is not None:
                other = corpus.config
                docs = _close_docs(root, [*_expand((*other.docs, *other.historical), other.ignore),
                                          *corpus.overlays], other.ignore)
                validate_checkout(dependency, other,
                                  [*docs, *_installed(other), *(t.file for t in corpus.glossary.terms),
                                   *corpus.glossary.overlay_sources, *corpus.glossary.overlay_sources.values(),
                                   *query.declared_inputs(corpus)])
            accepted[root] = corpus
        except (InvalidConfig, ConflictingGlossary, OSError, UnicodeError, RuntimeError) as exc:
            unavailable(entry, str(exc))
    entries.sort(key=lambda e: (not e['local'], e['name'] or '', e['root']))
    return query.select_repositories(cfg.root, accepted, entries, failures,
                                     requested_repository=args.repository, kind=args.kind,
                                     domain=args.domain, ident=args.id, document=args.document,
                                     direction=args.direction, relation=args.relation)


def cmd_query(args) -> int:
    root = Path(args.root).resolve()
    try:
        cfg = load_config(root)
        if args.repository is not None or args.all_repositories:
            report = _query_repositories(cfg, args)
        else:
            glossary, _ = _glossary(cfg)
            report = query.select(cfg, glossary, kind=args.kind, domain=args.domain,
                                  ident=args.id, document=args.document,
                                  direction=args.direction, relation=args.relation)
    except (InvalidConfig, ConflictingGlossary, GlobError, OSError, UnicodeError) as exc:
        report = query.unavailable(root, str(exc))
        if args.repository is not None or args.all_repositories:
            report['scope'].update(mode='repository' if args.repository is not None else 'all_repositories',
                                   requested_repository=args.repository, repositories=[])
            for diagnostic in report['diagnostics']:
                diagnostic['repository'] = str(root)
    if args.direction is not None or args.relation is not None:
        report.setdefault("relationships", [])
    print(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False)
          if args.json else query.render(report))
    return query.exit_code(report)


def cmd_overlap(args) -> int:
    root = Path(args.root).resolve()
    built = build(root)
    errors = _assembly_errors(built.glossary, built.diagnostics)
    if errors:
        return _report(errors, root, args.json)
    docs = [path for path in built.docs if path not in built.historical]
    installed = _installed(built.config)
    edges = build_edges(built.glossary, built.refs, built.config.edges, root, installed)
    parts = {t.file.resolve() for t in built.glossary.terms
             if t.ns in built.config.edges.include_ns}
    blocked_by = built.config.edges.blocked_by
    found = find_overlap(docs, owners(built.glossary, root, installed), edges,
                         args.min_similarity, args.unit, parts=parts, blocked_by=blocked_by)
    for c in found:
        for b in c["blocks"]:
            b["file"] = _display_path(b["file"], root)
    if args.json:
        print(json.dumps({"unit": args.unit, "min_similarity": args.min_similarity,
                          "count": len(found), "clusters": found}, indent=2))
    else:
        for c in found:
            note = " (restates an included part)" if c["restates_include"] else ""
            for r in c["restates_composite"]:
                why = f", but it sets {blocked_by}: true (W003)" if r["blocked"] else ""
                note += f" ({', '.join(r['records'])} could invoke {r['composite']}{why})"
            print(f"== {len(c['records'])} records: {', '.join(c['records'])}{note}")
            for b in c["blocks"]:
                print(f"   {b['file']}:{b['line']}  {b['text'][:120]}")
        print(f"{len(found)} cluster{'s' if len(found) != 1 else ''}")
    return 0


def cmd_explain(args) -> int:
    root = Path(args.root).resolve()
    trace = ScanTrace(root)
    built = build(root, trace)
    diags = _assembly_errors(built.glossary, built.diagnostics)
    result = trace.result()
    result["diagnostics"] = _diagnostics_json(diags, root)
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        for item in result["files"]:
            state = "included" if item["included"] else "ignored"
            if item["historical"]:
                state += ", historical"
            print(f"{item['file']}: {state}")
            for reason in item["reasons"]:
                detail = reason.get("pattern") or reason.get("from") or ""
                ignored = f" (ignored by {reason['ignored_by']})" if "ignored_by" in reason else ""
                print(f"  {reason['kind']}: {detail}{ignored}")
        for item in result["unmatched"]:
            print(f"unmatched {item['kind']}: {item['pattern']}")
        for diag in diags:
            print(diag.render())
    return int(any(d.is_error for d in diags))


def cmd_terms(args) -> int:
    root = Path(args.root).resolve()
    built = build(root)
    glossary = built.glossary
    errors = _assembly_errors(glossary, built.diagnostics)
    if errors:
        return _report(errors, root, False)
    terms = glossary.terms
    if args.ns:
        terms = [t for t in terms if t.ns == normalize(args.ns)]
    terms = sorted(terms, key=lambda t: t.qualified)
    if args.format == "context":
        print("## Language\n")
        for t in terms:
            label = t.qualified if len(glossary.resolve(t.term)) > 1 else t.term
            print(f"**[[{label}]]**:")
            para = (t.definition.split("\n\n")[0] if t.definition else "").strip()
            print(para or "_No definition._")
            print()
        return 0
    for t in terms:
        id_ = f" [{t.id}]" if t.id else ""
        aliases = f" (aliases: {', '.join(t.aliases)})" if t.aliases else ""
        print(f"{t.qualified}{id_}{aliases} — {t.file}")
    return 0


def cmd_refs(args) -> int:
    root = Path(args.root).resolve()
    built = build(root)
    glossary = built.glossary
    errors = _assembly_errors(glossary, built.diagnostics)
    if errors:
        return _report(errors, root, args.json)
    wanted = glossary.resolve(args.term) or glossary.by_id.get(args.term, [])
    wanted_ids = {id(term) for term in wanted}
    # `--kind explicit` selects wiki-links and delimiters; `--kind wiki` one of them.
    hits = sorted(
        (ref for item in _composition(built) for ref in item.refs
         if (not args.kind or ref.kind in args.kind or ref.policy.name in args.kind)
         and any(id(term) in wanted_ids for term in ref.resolve(item.glossary))),
        key=lambda ref: (str(ref.file), ref.line))
    if args.json:
        result = {
            "query": args.term,
            "definitions": [
                {"term": term.term, "namespace": term.ns, "qualified": term.qualified,
                 "id": term.id, "aliases": term.aliases,
                 "file": _display_path(term.file, root)}
                for term in sorted(wanted, key=lambda term: (term.qualified, str(term.file)))],
            "references": [
                {"kind": ref.kind, "policy": ref.policy.name,
                 "file": _composition_path(ref.file, built),
                 "line": ref.line, "raw": ref.raw, "target": ref.target,
                 "destination": _display_path(ref.destination, root) if ref.destination else None,
                 "historical": ref.historical} for ref in hits],
            "count": len(hits),
        }
        if not wanted:
            result["error"] = f"no record defines '{args.term}'"
        print(json.dumps(result, indent=2))
    elif not wanted:
        print(f"no record defines '{args.term}'", file=sys.stderr)
    else:
        for term in wanted:
            print(f"defined: {term.qualified} — {term.file}")
        for ref in hits:
            print(f"{ref.file}:{ref.line}: {ref.kind} '{ref.raw}'")
        print(f"{len(hits)} references")
    return 0 if wanted else 1


def cmd_candidates(args) -> int:
    root = Path(args.root).resolve()
    built = build(root)
    errors = _assembly_errors(built.glossary, built.diagnostics)
    if errors:
        return _report(errors, root, args.json)
    # Live docs only: historical docs keep retired names on purpose.
    docs = [path for path in built.docs if path not in built.historical]
    found = find_candidates(docs, built.glossary, args.min_files, built.config.candidate_shapes)
    if args.json:
        print(json.dumps({"min_files": args.min_files, "count": len(found), "candidates": [
            {"name": c["name"], "files": c["files"], "occurrences": c["occurrences"],
             "locations": [{"file": _display_path(path, root), "line": line}
                           for path, line in c["locations"]]}
            for c in found]}, indent=2))
    else:
        for c in found:
            where = ", ".join(f"{_display_path(path, root)}:{line}"
                              for path, line in c["locations"])
            files = f"{c['files']} file{'s' if c['files'] != 1 else ''}"
            uses = f"{c['occurrences']} use{'s' if c['occurrences'] != 1 else ''}"
            print(f"{c['name']} — {files}, {uses}: {where}")
        print(f"{len(found)} candidate{'s' if len(found) != 1 else ''}")
    return 0


def _positive(value: str) -> int:
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("expected 1 or more")
    return number


def _fraction(value: str) -> float:
    number = float(value)
    if not 0 < number <= 1:
        raise argparse.ArgumentTypeError("expected a number in (0, 1]")
    return number


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="ubiq", description="A linker for prose.")
    p.add_argument("--version", action="version", version=f"ubiq {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    i = sub.add_parser("init", help="infer asset schemas and scaffold grouped glossary metadata")
    i.add_argument("--root", default=".")
    i.set_defaults(fn=cmd_init)

    d = sub.add_parser("discover", help="group assets and propose contexts from repository structure")
    d.add_argument("--root", default=".")
    d.add_argument("--json", action="store_true")
    d.set_defaults(fn=cmd_discover)

    c = sub.add_parser("check", help="lint the vocabulary")
    c.add_argument("--root", default=".")
    c.add_argument("--json", action="store_true")
    c.set_defaults(fn=cmd_check)

    t = sub.add_parser("terms", help="list the glossary")
    t.add_argument("--root", default=".")
    t.add_argument("--format", choices=["list", "context"], default="list")
    t.add_argument("--ns", default=None, help="restrict to one namespace")
    t.set_defaults(fn=cmd_terms)

    r = sub.add_parser("refs", help="find every use of a term")
    r.add_argument("term")
    r.add_argument("--root", default=".")
    r.add_argument("--json", action="store_true")
    r.add_argument("--kind", action="append", choices=KINDS,
                   help="include this reference kind (repeat to select several)")
    r.set_defaults(fn=cmd_refs)

    e = sub.add_parser("explain", help="explain discovered files and their inclusion rules")
    e.add_argument("--root", default=".")
    e.add_argument("--json", action="store_true")
    e.set_defaults(fn=cmd_explain)

    k = sub.add_parser("candidates",
                       help="list names marked as vocabulary across docs with no record")
    k.add_argument("--root", default=".")
    k.add_argument("--json", action="store_true")
    k.add_argument("--min-files", type=_positive, default=2,
                   help="report names used in at least this many docs (default 2)")
    k.set_defaults(fn=cmd_candidates)

    g = sub.add_parser("graph", help="show composition edges: invoke, include, route, and reference")
    g.add_argument("target", nargs="?", help="start from this record (default: all edges)")
    g.add_argument("--root", default=".")
    g.add_argument("--json", action="store_true")
    g.add_argument("--callers", action="store_true", help="follow incoming edges")
    g.add_argument("--kind", action="append", metavar="KIND",
                   help="include this edge kind, a ref_fields field, or an x-ubiq-ref edge name "
                        "(repeat to select several)")
    g.add_argument("--depth", type=_positive, default=None,
                   help="stop after this many hops from the target (default: no limit)")
    g.add_argument("--format", choices=["text", "mermaid"], default="text",
                   help="mermaid prints a flowchart for `<!-- ubiq:graph -->` blocks")
    g.set_defaults(fn=cmd_graph)

    pl = sub.add_parser("plan", help="list ubiq's features in adoption order, or the next ones to adopt")
    pl.add_argument("--root", default=".")
    pl.add_argument("--json", action="store_true")
    pl.add_argument("--next", action="store_true",
                    help="only features not yet used whose requirements are met")
    pl.add_argument("--used", action="append", metavar="FEATURE",
                    help="count this feature as used (repeat); ubiq.yaml is read as well")
    pl.add_argument("--features", metavar="DIR", help="feature records (default: ubiq's own)")
    pl.set_defaults(fn=cmd_plan)

    sy = sub.add_parser("sync", help="mirror records to a tracker")
    targets = sy.add_subparsers(dest="target", required=True)
    gh = targets.add_parser("github", help="mirror records to GitHub issues, or check that they match")
    gh.add_argument("--root", default=".")
    mode = gh.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="print the plan as JSON (default)")
    mode.add_argument("--apply", action="store_true", help="perform the plan (needs GITHUB_TOKEN)")
    mode.add_argument("--check", action="store_true",
                      help="exit 1 when GitHub differs from the records; skips without GITHUB_TOKEN")
    gh.add_argument("--ref", metavar="REV",
                    help="read the records and ubiq.yaml as they are at REV (a pull request's base)")
    gh.add_argument("--ignore-derived", action="store_true",
                    help="with --check, do not count what waits only for the next sync of main: "
                         "the derived `status: in review`/`status: in progress` labels and "
                         "\"met at\" comments owed to issues closed by keyword")
    gh.add_argument("--repo", metavar="OWNER/NAME",
                    help="issue repository (default: sync.repo, then $GITHUB_REPOSITORY)")
    gh.add_argument("--results", metavar="FILE",
                    help="scenario outcomes from `pytest -p ubiq.pytest_plugin --ubiq-results FILE`; a criterion with "
                         "`scenario: true` is met when its tagged scenarios passed")
    gh.set_defaults(fn=cmd_sync)

    im = sub.add_parser("impact", help="records a change touches and the callers it affects")
    im.add_argument("--since", required=True, metavar="REV",
                    help="baseline: the merge base of REV and HEAD")
    im.add_argument("--root", default=".")
    im.add_argument("--json", action="store_true")
    im.add_argument("--depth", type=_positive, default=None,
                    help="stop after this many caller hops (default: no limit)")
    im.set_defaults(fn=cmd_impact)

    cp = sub.add_parser("compare", help="new, resolved, and unchanged findings since a baseline")
    cp.add_argument("--since", required=True, metavar="REV",
                    help="baseline: the merge base of REV and HEAD")
    cp.add_argument("--root", default=".")
    out = cp.add_mutually_exclusive_group()
    out.add_argument("--json", action="store_true")
    out.add_argument("--markdown", action="store_true", help="a PR-ready summary")
    cp.set_defaults(fn=cmd_compare)

    cv = sub.add_parser("coverage", help="how much selected repository content has typed metadata")
    cv.add_argument("--root", default=".")
    cv.add_argument("--since", metavar="REV", default=None,
                    help="compare with the merge base of REV and HEAD")
    cv_out = cv.add_mutually_exclusive_group()
    cv_out.add_argument("--json", action="store_true")
    cv_out.add_argument("--markdown", action="store_true", help="a PR-ready summary")
    cv.set_defaults(fn=cmd_coverage)

    q = sub.add_parser("query", help="select complete records from declared metadata collections")
    q.add_argument("--root", default=".")
    repositories = q.add_mutually_exclusive_group()
    repositories.add_argument("--repository", help="select a configured dependency by its declared name")
    repositories.add_argument("--all-repositories", action="store_true",
                              help="select local records and available direct dependencies")
    q.add_argument("--kind", help="match the exact declared record kind")
    q.add_argument("--domain", help="match the exact declared domain")
    q.add_argument("--id", help="resolve an exact record identity before applying other filters")
    q.add_argument("--document", help="match the exact repository-relative metadata document")
    direction = q.add_mutually_exclusive_group()
    direction.add_argument("--incoming", dest="direction", action="store_const", const="incoming",
                           help="return records with declared edges to the selected ID")
    direction.add_argument("--outgoing", dest="direction", action="store_const", const="outgoing",
                           help="return records with declared edges from the selected ID")
    q.add_argument("--relation", help="match an exact edge kind (default direction: outgoing)")
    q.add_argument("--json", action="store_true")
    q.set_defaults(fn=cmd_query)

    o = sub.add_parser("overlap", help="list near-duplicate prose shared across records")
    o.add_argument("--root", default=".")
    o.add_argument("--json", action="store_true")
    o.add_argument("--unit", choices=["paragraph", "line"], default="paragraph",
                   help="compare paragraphs, or single lines for one-sentence-per-line prose")
    o.add_argument("--min-similarity", type=_fraction, default=0.5,
                   help="word-shingle Jaccard similarity to join a cluster (default 0.5)")
    o.set_defaults(fn=cmd_overlap)

    args = p.parse_args(argv)
    if args.cmd == "query" and (args.direction is not None or args.relation is not None) and args.id is None:
        p.error("relationship queries require --id")
    try:
        return args.fn(args)
    except GlobError as exc:
        root = Path(args.root).resolve()
        return _report([Diagnostic("E005", f"cannot scan directory: {exc}",
                                   Path(exc.filename) if exc.filename else root)],
                       root, getattr(args, "json", False))
    except (InvalidConfig, ConflictingGlossary) as exc:
        root = Path(args.root).resolve()
        return _report([Diagnostic("E008", str(exc), root / "ubiq.yaml")],
                       root, getattr(args, "json", False))


if __name__ == "__main__":
    sys.exit(main())
