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
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, replace
from pathlib import Path

import yaml

from . import __version__, review
from .candidates import find_candidates
from .catalog import CatalogError, catalog_cover_gaps, catalog_refs
from .check import Diagnostic, run_checks
from .config import Config, InvalidConfig, load_config
from .discovery import discover, init_assets
from .globs import Glob, GlobError, first_match
from .graph import KINDS as GRAPH_KINDS
from .graph import (
    Layout,
    Repository,
    across_repositories,
    build_edges,
    check_edges,
    cross_edges,
    owners,
    walk,
)
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


def build(root: Path, trace: ScanTrace | None = None, cfg: Config | None = None) -> Build:
    root = root.resolve()
    cfg = cfg or load_config(root)
    glossary, overlay_files = _glossary(cfg, trace)

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
            entry_errors: list[str] = []
            catalog_entries = catalog_refs(spec, catalog, entry_errors)
            extra.extend(Diagnostic("E005", msg, spec.file) for msg in entry_errors)
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
    diags, terms, refs = _check(root)
    return _report(diags, root, args.json, terms, refs)


def _check(root: Path, cfg: Config | None = None) -> tuple[list[Diagnostic], int, int]:
    """Every check diagnostic, with the term and reference counts."""
    result = build(root, cfg=cfg)
    glossary, cfg = result.glossary, result.config
    layout = _layout(cfg)
    refs = across_repositories(result.refs, layout, tuple(r.glob for r in cfg.part_rules))
    skip_mentions = {path.resolve() for path in glossary.overlay_sources.values()}
    # A consuming repository does not own dependency prose reached through links.
    # Keep explicit references checked; only plain-mention suggestions stay local.
    skip_mentions.update(path.resolve() for path in result.docs
                         if not path.resolve().is_relative_to(root))
    diags = result.diagnostics + run_checks(
        glossary, refs, cfg.external_id_patterns,
        skip_unlinked=skip_mentions, unlinked_except=cfg.unlinked_except)
    if cfg.schemas:
        from .schemas import check_schemas
        diags.extend(check_schemas(cfg, glossary))
    live = [path for path in result.docs if path not in result.historical]
    diags.extend(check_edges(glossary, refs, cfg.edges, root, live, layout))
    return diags, len(glossary.terms), len(result.refs)


def _installed(cfg: Config) -> list[Path]:
    return _expand(cfg.edges.install, cfg.ignore, None, "install")


def _layout(cfg: Config) -> Layout:
    """This repository's installed files, plus each edges.external repository's
    installed files and records. Only that repository's glossary is read: one
    frontmatter per record, none of its other documents."""
    external, unread = [], []
    names = Counter(repo.resolve().name for repo in cfg.edges.external)
    for repo in cfg.edges.external:
        if not repo.is_dir():
            unread.append((repo, "was not found"))
            continue
        try:
            other = load_config(repo)
            glossary, _ = _glossary(other)
            files = _installed(other)
        except GlobError as exc:
            unread.append((repo, f"cannot be scanned ({exc})"))
            continue
        except (InvalidConfig, ConflictingGlossary) as exc:
            unread.append((repo, f"has invalid configuration ({exc})"))
            continue
        if not files:
            unread.append((repo, "installs nothing (no edges.install match)"))
        # Records take the directory name, or the full path when two repositories share it.
        name = repo.resolve().name
        external.append(Repository(name if names[name] == 1 else str(repo.resolve()),
                                   repo, files, glossary))
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
        find(glossary, query) or [t for r in others for t in find(r.glossary, query)])
    matches = list({id(t): t for t in matches}.values())
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
    layout = _layout(built.config)
    live = [path for path in built.docs if path not in built.historical]
    edges = (build_edges(built.glossary, built.refs, built.config.edges, root, layout.local)
             + cross_edges(live, layout, owners(built.glossary, root, layout.local)))
    if args.kind:
        edges = [e for e in edges if e.kind in args.kind]
    try:
        start = (_resolve_one(built.glossary, args.target, layout.repositories)
                 if args.target else None)
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


def _side(name: str, root: Path, cfg: Config | None = None) -> review.Side:
    """One side of a change review: its records, dependency edges, and gaps."""
    built = build(root, cfg=cfg)
    layout = _layout(built.config)
    live = [path for path in built.docs if path not in built.historical]
    owner = owners(built.glossary, root, layout.local)
    edges = (build_edges(built.glossary, built.refs, built.config.edges, root, layout.local)
             + cross_edges(live, layout, owner))
    side = review.Side(name, root.resolve(), {t.qualified: t for t in built.glossary.terms},
                       owner, edges, {}, layout.unread)
    for diag in _assembly_errors(built.glossary, built.diagnostics):
        side.invalid.setdefault(side.rel(diag.file), diag.message)
    return side


def _baseline_config(base_root: Path, head_root: Path) -> Config:
    """The baseline's configuration, reading edges.external from the real checkout:
    other repositories are read in their current state on both sides."""
    try:
        cfg = load_config(base_root)
    except (InvalidConfig, ConflictingGlossary) as exc:
        raise review.BaselineError(f"baseline configuration cannot load: {exc}") from exc
    external = tuple(head_root / p.relative_to(base_root) if p.is_relative_to(base_root) else p
                     for p in cfg.edges.external)
    return replace(cfg, edges=replace(cfg.edges, external=external))


def _review_error(message: str, as_json: bool) -> int:
    print(json.dumps({"error": message}, indent=2) if as_json else f"error: {message}")
    return 2


def cmd_impact(args) -> int:
    root = Path(args.root).resolve()
    try:
        baseline = review.resolve_baseline(root, args.since)
        files = review.changed_files(baseline)
        with review.checkout(baseline) as base_root:
            try:
                base = _side("baseline", base_root, _baseline_config(base_root, root))
            except (GlobError, ConflictingGlossary) as exc:
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
    """Findings keyed for comparison: a path outside the root is resolved, so
    `root/../other` names the same file from either side."""
    def where(path: Path) -> str:
        resolved = path.resolve() if path.is_absolute() else (root / path).resolve()
        return _display_path(resolved, root) if resolved.is_relative_to(root) else str(resolved)
    return [{"code": d.code, "severity": d.severity, "file": where(d.file),
             "line": d.line, "message": d.message} for d in diags]


def cmd_compare(args) -> int:
    root = Path(args.root).resolve()
    try:
        baseline = review.resolve_baseline(root, args.since)
        renamed = {c.source: c.file for c in review.changed_files(baseline) if c.source}
        with review.checkout(baseline) as base_root:
            try:
                base_diags, _, _ = _check(base_root, _baseline_config(base_root, root))
            except (GlobError, ConflictingGlossary) as exc:
                raise review.BaselineError(f"baseline cannot be checked: {exc}") from exc
            base = _findings(base_diags, base_root)
            for f in base:
                f["file"] = renamed.get(f["file"], f["file"])
                f["message"] = f["message"].replace(str(base_root), str(root))
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

    g = sub.add_parser("graph", help="show composition edges: invoke, include, route, and reference")
    g.add_argument("target", nargs="?", help="start from this record (default: all edges)")
    g.add_argument("--root", default=".")
    g.add_argument("--json", action="store_true")
    g.add_argument("--callers", action="store_true", help="follow incoming edges")
    g.add_argument("--kind", action="append", choices=GRAPH_KINDS,
                   help="include this edge kind (repeat to select several)")
    g.add_argument("--depth", type=_positive, default=None,
                   help="stop after this many hops from the target (default: no limit)")
    g.set_defaults(fn=cmd_graph)

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
