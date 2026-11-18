"""ubiq CLI.

  ubiq init  [--root DIR]            scaffold ubiq.yaml + .ubiq/glossary/ with an example record
  ubiq check [--root DIR] [--json]   lint the vocabulary; exit 1 on errors
  ubiq terms [--root DIR] [--format list|context] [--ns NS]
  ubiq refs TERM [--root DIR]        every place a term is used (traceability = search)
"""

from __future__ import annotations

import argparse
import fnmatch
import glob as globlib
import json
import sys
from pathlib import Path

from . import __version__
from .catalog import CatalogError, catalog_cover_gaps, catalog_refs
from .check import Diagnostic, run_checks
from .config import InvalidConfig, load_config
from .records import (
    ConflictingGlossary, assemble_glossary, normalize,
)
from .scan import compile_delimiter, file_link_targets, scan_docs


def _display_path(path: Path, root: Path) -> str:
    return str(path.relative_to(root) if path.is_relative_to(root) else path)


def _expand(root: Path, patterns: list[str], ignore: list[str]) -> list[Path]:
    out: set[Path] = set()
    for pat in patterns:
        full = pat if Path(pat).is_absolute() else str(root / pat)
        for hit in globlib.glob(full, recursive=True):
            p = Path(hit)
            if not p.is_file():
                continue
            rel = str(p.relative_to(root)) if p.is_relative_to(root) else p.name
            if not any(fnmatch.fnmatch(rel, ig) for ig in ignore):
                out.add(p)
    return sorted(out)


def _close_docs(root: Path, seeds: list[Path], ignore: list[str]) -> list[Path]:
    """docs: globs are roots. Path wiki-links and relative markdown links to
    existing in-repo .md files are followed until the set is closed."""
    seen = {p.resolve() for p in seeds}
    queue = list(seeds)
    while queue:
        p = queue.pop()
        try:
            linked = file_link_targets(p, root)
        except (OSError, UnicodeError):
            continue
        for q in linked:
            key = q.resolve()
            if key in seen:
                continue
            rel = str(q.relative_to(root)) if q.is_relative_to(root) else q.name
            if any(fnmatch.fnmatch(rel, ig) for ig in ignore):
                continue
            seen.add(key)
            queue.append(q)
    return sorted(seen, key=lambda p: str(p))


def build(root: Path):
    root = root.resolve()
    cfg = load_config(root)
    term_fields = tuple(cfg["term_field"])
    lenient = cfg["frontmatter"] == "lenient"
    delimiters = [compile_delimiter(d) for d in cfg["delimiters"]]
    overlay_files = _expand(root, cfg["overlays"], cfg["ignore"])
    entries = cfg["glossary"]
    sources = [
        (path, tuple(entry["term_field"]), entry.get("ns"),
         f"glossary[{i}] ({entry['glob']})")
        for i, entry in enumerate(entries)
        for path in _expand(root, [entry["glob"]], cfg["ignore"])
    ]
    glossary = assemble_glossary(root, sources, overlay_files, term_fields, lenient)

    doc_files = _expand(root, cfg["docs"], cfg["ignore"])
    hist_files = _expand(root, cfg["historical"], cfg["ignore"])
    hist_set = {p.resolve() for p in hist_files}
    # Sidecars are docs too, so their ref_fields (uses: [...]) participate.
    for p in overlay_files:
        if p not in doc_files:
            doc_files.append(p)
    for p in hist_files:
        if p not in doc_files:
            doc_files.append(p)
    doc_files = _close_docs(root, doc_files, cfg["ignore"])
    refs = scan_docs(doc_files, glossary, cfg["id_patterns"],
                     ref_fields=cfg["ref_fields"], lenient=lenient,
                     delimiters=delimiters, historical=hist_set, root=root,
                     glossary_patterns=[entry["glob"] for entry in entries],
                     invalid=glossary.invalid)

    extra: list[Diagnostic] = []
    for spec in cfg.get("catalogs") or []:
        cfile = root / spec["file"]
        if not cfile.is_file():
            extra.append(Diagnostic("E005", f"catalog file not found: {spec['file']}", cfile))
            continue
        try:
            catalog_entries = catalog_refs(spec, cfile)
            refs.extend(catalog_entries)
            cover = _expand(root, spec["cover"], cfg["ignore"])
            extra.extend(catalog_cover_gaps(catalog_entries, cfile, glossary, set(cover)))
        except CatalogError as e:
            extra.append(Diagnostic("E005", str(e), cfile))

    return glossary, refs, cfg, extra


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
ignore:
  - ".git/**"
  - "node_modules/**"
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
    if cfg.exists():
        print(f"{cfg} already exists — not touching it", file=sys.stderr)
        return 1
    cfg.write_text(INIT_CONFIG, encoding="utf-8")
    gdir.mkdir(parents=True, exist_ok=True)
    example = gdir / "glossary-record.md"
    if not example.exists():
        example.write_text(INIT_RECORD, encoding="utf-8")
    print(f"wrote {cfg.relative_to(root)} and {example.relative_to(root)}")
    print("next: `ubiq check` — then add one record per term your docs rely on")
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
    glossary, refs, cfg, extra = build(root)
    diags = extra + run_checks(glossary, refs, cfg["external_id_patterns"])
    return _report(diags, root, args.json, len(glossary.terms), len(refs))


def cmd_terms(args) -> int:
    root = Path(args.root).resolve()
    glossary, _, _, extra = build(root)
    errors = _assembly_errors(glossary, extra)
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
    glossary, refs, _, extra = build(root)
    errors = _assembly_errors(glossary, extra)
    if errors:
        return _report(errors, root, False)
    wanted = glossary.resolve(args.term) or [
        t for t in glossary.terms if t.id == args.term]
    if not wanted:
        print(f"no record defines '{args.term}'", file=sys.stderr)
        return 1
    wanted_ids = {id(t) for t in wanted}
    hits = [r for r in refs if any(id(t) in wanted_ids for t in r.resolve(glossary))]
    for t in wanted:
        print(f"defined: {t.qualified} — {t.file}")
    for r in sorted(hits, key=lambda r: (str(r.file), r.line)):
        print(f"{r.file}:{r.line}: {r.kind} '{r.raw}'")
    print(f"{len(hits)} references")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="ubiq", description="A linker for prose.")
    p.add_argument("--version", action="version", version=f"ubiq {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    i = sub.add_parser("init", help="scaffold ubiq.yaml + .ubiq/glossary/")
    i.add_argument("--root", default=".")
    i.set_defaults(fn=cmd_init)

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
    r.set_defaults(fn=cmd_refs)

    args = p.parse_args(argv)
    try:
        return args.fn(args)
    except (InvalidConfig, ConflictingGlossary) as exc:
        root = Path(args.root).resolve()
        return _report([Diagnostic("E008", str(exc), root / "ubiq.yaml")],
                       root, getattr(args, "json", False))


if __name__ == "__main__":
    sys.exit(main())
