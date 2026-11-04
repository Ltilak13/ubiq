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

import yaml

from . import __version__
from .catalog import CatalogError, catalog_cover_gaps, catalog_refs
from .check import Diagnostic, run_checks
from .records import (
    DEFAULT_NS, Glossary, InvalidRecord, Term, normalize, overlay_onto,
    parse_frontmatter, parse_record,
)
from .scan import compile_delimiter, file_link_targets, scan_docs

DEFAULT_CONFIG = {
    "glossary": ["glossary/**/*.md", ".ubiq/glossary/**/*.md"],
    "docs": [
        "README.md",
        "AGENTS.md",
        "CLAUDE.md",
        "CONTEXT.md",
        ".agents/**/*.md",
        ".ubiq/**/*.md",
        "docs/**/*.md",
    ],
    "historical": ["CHANGELOG.md"],
    "ignore": [".git/**", "node_modules/**", ".venv/**"],
    "id_patterns": [],
    # Frontmatter field(s) holding the term, tried in order. Lets existing repos
    # keep their schema (e.g. [name, title]) instead of renaming to `term:`.
    "term_field": ["term"],
    # "strict" = invalid YAML frontmatter is an error (E005).
    # "lenient" = fall back to line-based key: value parsing for non-YAML dialects.
    "frontmatter": "strict",
    # Frontmatter fields in scanned docs whose values are references that must
    # resolve by record id or name (e.g. solves: [T1]) — E006 otherwise.
    "ref_fields": [],
    # Regexes for ids that are defined outside records (e.g. requirement ids that
    # live as headings in a research doc); matching field refs are accepted.
    "external_id_patterns": [],
    # Extra explicit wrappers besides [[term]]. A string is a prefix ("/" → /{term})
    # or a pattern containing {term}. Dict form adds `except` for tokens that look
    # like refs but aren't vocabulary (`/plugin` colliding with a term named plugin)
    # and `only_known: true` to match only glossary names (quieter; typos invisible).
    # Delimiters match inside inline code; fenced blocks are still ignored.
    "delimiters": [],
    # Sidecar records that attach frontmatter to a source file they do not own.
    # Each overlay is markdown with `source: path/to/source.md` plus optional ns,
    # aliases, id, and any ref_fields. The source file is not edited.
    "overlays": [".ubiq/overlays/**/*.md"],
    # JSON/YAML inventories of terms. Each item must resolve (E006). Optional
    # `cover` globs: every matching record must appear in the inventory (E007).
    "catalogs": [],
}


def load_config(root: Path) -> dict:
    cfg = dict(DEFAULT_CONFIG)
    f = root / "ubiq.yaml"
    if f.exists():
        user = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
        cfg.update({k: v for k, v in user.items() if v is not None})
    return cfg


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
        except OSError:
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


def _as_list(val) -> list:
    if val is None:
        return []
    return val if isinstance(val, list) else [val]


def _glossary_entries(cfg: dict) -> list[dict]:
    """Normalize glossary: strings stay globs; dicts may set glob/term_field/ns."""
    default_tf = _as_list(cfg["term_field"])
    out = []
    for item in cfg["glossary"]:
        if isinstance(item, str):
            out.append({"glob": item, "term_field": default_tf, "ns": None})
        else:
            tf = _as_list(item.get("term_field", default_tf))
            out.append({"glob": item["glob"], "term_field": tf, "ns": item.get("ns")})
    return out


def _load_overlays(root: Path, paths: list[Path], lenient: bool) -> dict[Path, dict]:
    """Map resolved source path -> overlay frontmatter (`source:` is the link)."""
    by_source: dict[Path, dict] = {}
    for p in paths:
        try:
            meta, _ = parse_frontmatter(p, lenient)
        except InvalidRecord:
            continue
        on = meta.get("source") or meta.get("on")
        # YAML 1.1: the key `on:` loads as boolean True.
        if on is None and True in meta:
            on = meta[True]
        if not on or on is True:
            continue
        src = Path(on)
        resolved = src.resolve() if src.is_absolute() else (root / src).resolve()
        by_source[resolved] = {**meta, "_overlay_file": p}
    return by_source


def build(root: Path):
    cfg = load_config(root)
    term_fields = tuple(_as_list(cfg["term_field"]))
    lenient = cfg["frontmatter"] == "lenient"
    delimiters = [compile_delimiter(d) for d in (cfg.get("delimiters") or [])]
    overlay_files = _expand(root, _as_list(cfg.get("overlays")), cfg["ignore"])
    overlay_by_source = _load_overlays(root, overlay_files, lenient)

    glossary = Glossary()
    seen: set[Path] = set()
    for entry in _glossary_entries(cfg):
        tf = tuple(entry["term_field"])
        for path in _expand(root, [entry["glob"]], cfg["ignore"]):
            seen.add(path.resolve())
            try:
                t = parse_record(path, tf, lenient, default_ns=entry["ns"])
            except InvalidRecord as e:
                glossary.invalid.append((path, str(e)))
                continue
            if t:
                ov = overlay_by_source.get(path.resolve())
                if ov:
                    t = overlay_onto(t, ov)
                glossary.add(t)

    # Overlays whose source was not in a glossary glob still define a record
    # from the source file's frontmatter plus the sidecar.
    for src, ov in overlay_by_source.items():
        if src in seen:
            continue
        overlay_path = ov["_overlay_file"]
        if not src.is_file():
            glossary.invalid.append(
                (overlay_path, f"overlay source: '{ov.get('source') or ov.get('on')}' does not exist"))
            continue
        try:
            t = parse_record(src, term_fields, lenient, default_ns=ov.get("ns"))
        except InvalidRecord as e:
            glossary.invalid.append((src, str(e)))
            continue
        if t:
            glossary.add(overlay_onto(t, ov))
        elif ov.get("term"):
            aliases = ov.get("aliases") or []
            if isinstance(aliases, str):
                aliases = [aliases]
            glossary.add(Term(
                term=normalize(str(ov["term"])),
                ns=normalize(str(ov.get("ns") or DEFAULT_NS)),
                file=src,
                aliases=[normalize(str(a)) for a in aliases],
                id=str(ov["id"]) if ov.get("id") is not None else None,
                definition="",
            ))

    doc_files = _expand(root, cfg["docs"], cfg["ignore"])
    hist_files = _expand(root, _as_list(cfg.get("historical")), cfg["ignore"])
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
                     delimiters=delimiters, historical=hist_set)

    extra: list[Diagnostic] = []
    for spec in cfg.get("catalogs") or []:
        if not isinstance(spec, dict) or not spec.get("file"):
            continue
        cfile = root / spec["file"]
        if not cfile.is_file():
            extra.append(Diagnostic("E005", f"catalog file not found: {spec['file']}", cfile))
            continue
        try:
            refs.extend(catalog_refs(spec, cfile))
            cover = _expand(root, _as_list(spec.get("cover")), cfg["ignore"])
            extra.extend(catalog_cover_gaps(spec, cfile, glossary, set(cover)))
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
Reference it anywhere as [[glossary record]] — unresolved references fail
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


def cmd_check(args) -> int:
    root = Path(args.root).resolve()
    glossary, refs, cfg, extra = build(root)
    diags = extra + run_checks(glossary, refs, cfg["external_id_patterns"])
    errors = [d for d in diags if d.is_error]
    if args.json:
        print(json.dumps({
            "terms": len(glossary.terms),
            "refs": len(refs),
            "errors": len(errors),
            "warnings": len(diags) - len(errors),
            "diagnostics": [
                {"code": d.code, "message": d.message,
                 "file": str(d.file.relative_to(root) if d.file.is_relative_to(root) else d.file),
                 "line": d.line, "severity": "error" if d.is_error else "warning"}
                for d in diags
            ],
        }, indent=2))
    else:
        for d in diags:
            print(d.render())
        status = "FAIL" if errors else "OK"
        print(f"{status}: {len(glossary.terms)} terms, {len(refs)} refs, "
              f"{len(errors)} errors, {len(diags) - len(errors)} warnings")
    return 1 if errors else 0


def cmd_terms(args) -> int:
    glossary, _, _, _ = build(Path(args.root).resolve())
    terms = glossary.terms
    if args.ns:
        terms = [t for t in terms if t.ns == normalize(args.ns)]
    terms = sorted(terms, key=lambda t: t.qualified)
    if args.format == "context":
        print("## Language\n")
        for t in terms:
            print(f"**[[{t.term}]]**:")
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
    glossary, refs, _, _ = build(root)
    wanted = glossary.resolve(args.term) or [
        t for t in glossary.terms if t.id == args.term]
    if not wanted:
        print(f"no record defines '{args.term}'", file=sys.stderr)
        return 1
    names = {n for t in wanted for n in t.names()} | {t.id for t in wanted if t.id}
    hits = [r for r in refs if r.name in names or normalize(r.raw) in names]
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
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
