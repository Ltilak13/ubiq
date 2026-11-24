"""ubiq CLI.

  ubiq init  [--root DIR]            infer asset schemas and scaffold grouped glossary metadata
  ubiq check [--root DIR] [--json]   lint the vocabulary; exit 1 on errors
  ubiq terms [--root DIR] [--format list|context] [--ns NS]
  ubiq refs TERM [--root DIR]        every place a term is used (traceability = search)
  ubiq discover [--root DIR] [--json] groups, schema proposals, and candidate contexts
  ubiq candidates [--root DIR] [--json] [--min-files N]
                                     marked names (candidate_shapes) in N+ docs with no record
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

import yaml

from . import __version__
from .candidates import find_candidates
from .catalog import CatalogError, catalog_cover_gaps, catalog_refs
from .check import Diagnostic, run_checks
from .config import Config, InvalidConfig, load_config
from .discovery import discover, init_assets
from .globs import Glob, first_match
from .graph import KINDS as GRAPH_KINDS
from .graph import Layout, across_repositories, build_edges, check_edges, owners, walk
from .kinds import KINDS
from .overlap import find_overlap
from .records import (
    ConflictingGlossary,
    Glossary,
    InvalidRecord,
    assemble_glossary,
    normalize,
)
from .scan import Ref, file_link_targets, scan_docs


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


def build(root: Path, trace: ScanTrace | None = None) -> Build:
    root = root.resolve()
    cfg = load_config(root)
    overlay_files = _expand(cfg.overlays, cfg.ignore, trace, "overlay")
    sources = [
        (path, rule.term_field, rule.ns, rule.label)
        for rule in cfg.glossary
        for path in _expand((rule.glob,), cfg.ignore, trace, "glossary")
    ]
    glossary = assemble_glossary(root, sources, overlay_files, cfg.term_field, cfg.lenient,
                                 ref_fields=cfg.ref_fields)

    if trace is not None:
        for term in glossary.terms:
            trace.record(term.file, "record")
        for source, overlay in glossary.overlay_sources.items():
            trace.record(source, "overlay-source", source=overlay)

    doc_files = _expand(cfg.docs, cfg.ignore, trace, "docs")
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

    extra: list[Diagnostic] = []
    catalog = cfg.policies["catalog"]
    for spec in cfg.catalogs:
        if trace is not None:
            trace.record(spec.file, "catalog")
        if not spec.file.is_file():
            extra.append(Diagnostic("E005", f"catalog file not found: {spec.path}", spec.file))
            continue
        try:
            catalog_entries = catalog_refs(spec, catalog)
            refs.extend(catalog_entries)
            cover = _expand(spec.cover, cfg.ignore, trace, "cover")
            extra.extend(catalog_cover_gaps(catalog_entries, spec.file, glossary,
                                            set(cover), catalog))
        except CatalogError as e:
            extra.append(Diagnostic("E005", str(e), spec.file))

    return Build(glossary, refs, cfg, extra, doc_files, hist_set)


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
    result = build(root)
    glossary, cfg = result.glossary, result.config
    layout = _layout(cfg)
    refs = across_repositories(result.refs, layout)
    sidecars = {path.resolve() for path in glossary.overlay_sources.values()}
    diags = result.diagnostics + run_checks(
        glossary, refs, cfg.external_id_patterns,
        skip_unlinked=sidecars, unlinked_except=cfg.unlinked_except)
    if cfg.schemas:
        from .schemas import check_schemas
        diags.extend(check_schemas(cfg, glossary))
    live = [path for path in result.docs if path not in result.historical]
    diags.extend(check_edges(glossary, refs, cfg.edges, root, live, layout))
    return _report(diags, root, args.json, len(glossary.terms), len(result.refs))


def _installed(cfg: Config) -> list[Path]:
    return _expand(cfg.edges.install, cfg.ignore, None, "install")


def _layout(cfg: Config) -> Layout:
    """This repository's installed files plus those of each edges.external repository."""
    external, unread = [], []
    for repo in cfg.edges.external:
        if not repo.is_dir():
            unread.append((repo, "was not found"))
            continue
        try:
            other = load_config(repo)
        except InvalidConfig as exc:
            unread.append((repo, f"has invalid configuration ({exc})"))
            continue
        files = _installed(other)
        if not files:
            unread.append((repo, "installs nothing (no edges.install match)"))
        external += files
    return Layout.build(_installed(cfg), external, unread)


def _resolve_one(glossary, query: str):
    ns, name = glossary.split(query)
    matches = list({id(t): t for t in glossary.resolve(name, ns)}.values())
    if len(matches) != 1:
        found = ", ".join(t.qualified for t in matches) or "no record"
        raise LookupError(f"{query!r} must name one record ({found})")
    return matches[0]


def cmd_graph(args) -> int:
    root = Path(args.root).resolve()
    built = build(root)
    errors = _assembly_errors(built.glossary, built.diagnostics)
    if errors:
        return _report(errors, root, args.json)
    installed = _installed(built.config)
    edges = build_edges(built.glossary, built.refs, built.config.edges, root, installed)
    if args.kind:
        edges = [e for e in edges if e.kind in args.kind]
    try:
        start = _resolve_one(built.glossary, args.target) if args.target else None
    except LookupError as exc:
        print(json.dumps({"error": str(exc)}) if args.json else f"error: {exc}")
        return 1
    shown = walk(edges, start, args.callers, args.depth)
    if args.json:
        print(json.dumps({"target": start.qualified if start else None,
                          "view": "callers" if args.callers else "dependencies",
                          "count": len(shown), "edges": [
            {"kind": e.kind, "source": e.source.qualified, "target": e.target.qualified,
             "file": _display_path(e.file, root), "line": e.line} for e in shown]}, indent=2))
    else:
        for e in shown:
            print(f"{e.source.qualified} -{e.kind}-> {e.target.qualified}"
                  f"  {_display_path(e.file, root)}:{e.line}")
        print(f"{len(shown)} edge{'s' if len(shown) != 1 else ''}")
    return 0


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
    found = find_overlap(docs, owners(built.glossary, root, installed), edges,
                         args.min_similarity, args.unit, parts=parts)
    for c in found:
        for b in c["blocks"]:
            b["file"] = _display_path(b["file"], root)
    if args.json:
        print(json.dumps({"unit": args.unit, "min_similarity": args.min_similarity,
                          "count": len(found), "clusters": found}, indent=2))
    else:
        for c in found:
            note = " (restates an included part)" if c["restates_include"] else ""
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
    glossary, refs = built.glossary, built.refs
    errors = _assembly_errors(glossary, built.diagnostics)
    if errors:
        return _report(errors, root, args.json)
    wanted = glossary.resolve(args.term) or glossary.by_id.get(args.term, [])
    wanted_ids = {id(term) for term in wanted}
    # `--kind explicit` selects wiki-links and delimiters; `--kind wiki` one of them.
    hits = sorted(
        (ref for ref in refs
         if (not args.kind or ref.kind in args.kind or ref.policy.name in args.kind)
         and any(id(term) in wanted_ids for term in ref.resolve(glossary))),
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
                 "file": _display_path(ref.file, root),
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

    g = sub.add_parser("graph", help="show composition edges: invoke, include, and route")
    g.add_argument("target", nargs="?", help="start from this record (default: all edges)")
    g.add_argument("--root", default=".")
    g.add_argument("--json", action="store_true")
    g.add_argument("--callers", action="store_true", help="follow incoming edges")
    g.add_argument("--kind", action="append", choices=GRAPH_KINDS,
                   help="include this edge kind (repeat to select several)")
    g.add_argument("--depth", type=_positive, default=None,
                   help="stop after this many hops from the target (default: no limit)")
    g.set_defaults(fn=cmd_graph)

    o = sub.add_parser("overlap", help="list near-duplicate prose shared across records")
    o.add_argument("--root", default=".")
    o.add_argument("--json", action="store_true")
    o.add_argument("--unit", choices=["paragraph", "line"], default="paragraph",
                   help="compare paragraphs, or single lines for one-sentence-per-line prose")
    o.add_argument("--min-similarity", type=_fraction, default=0.5,
                   help="word-shingle Jaccard similarity to join a cluster (default 0.5)")
    o.set_defaults(fn=cmd_overlap)

    args = p.parse_args(argv)
    try:
        return args.fn(args)
    except (InvalidConfig, ConflictingGlossary) as exc:
        root = Path(args.root).resolve()
        return _report([Diagnostic("E008", str(exc), root / "ubiq.yaml")],
                       root, getattr(args, "json", False))


if __name__ == "__main__":
    sys.exit(main())
