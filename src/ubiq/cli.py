"""ubiq CLI.

  ubiq check [--root DIR] [--json]   lint the vocabulary; exit 1 on errors
  ubiq terms [--root DIR]            list the glossary
  ubiq refs TERM [--root DIR]        every place a term is used (traceability = search)
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import sys
from pathlib import Path

import yaml

from . import __version__
from .check import run_checks
from .records import load_glossary, normalize
from .scan import scan_docs

DEFAULT_CONFIG = {
    "glossary": ["glossary/**/*.md"],
    "docs": ["**/*.md"],
    "ignore": [".git/**", "node_modules/**", ".venv/**"],
    "id_patterns": [],
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
        for p in root.glob(pat):
            if p.is_file() and not any(
                fnmatch.fnmatch(str(p.relative_to(root)), ig) for ig in ignore
            ):
                out.add(p)
    return sorted(out)


def build(root: Path):
    cfg = load_config(root)
    glossary_files = _expand(root, cfg["glossary"], cfg["ignore"])
    glossary = load_glossary(glossary_files)
    doc_files = _expand(root, cfg["docs"], cfg["ignore"])
    refs = scan_docs(doc_files, glossary, cfg["id_patterns"])
    return glossary, refs


def cmd_check(args) -> int:
    root = Path(args.root).resolve()
    glossary, refs = build(root)
    diags = run_checks(glossary, refs)
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
    glossary, _ = build(Path(args.root).resolve())
    for t in sorted(glossary.terms, key=lambda t: t.qualified):
        id_ = f" [{t.id}]" if t.id else ""
        aliases = f" (aliases: {', '.join(t.aliases)})" if t.aliases else ""
        print(f"{t.qualified}{id_}{aliases} — {t.file}")
    return 0


def cmd_refs(args) -> int:
    root = Path(args.root).resolve()
    glossary, refs = build(root)
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

    c = sub.add_parser("check", help="lint the vocabulary")
    c.add_argument("--root", default=".")
    c.add_argument("--json", action="store_true")
    c.set_defaults(fn=cmd_check)

    t = sub.add_parser("terms", help="list the glossary")
    t.add_argument("--root", default=".")
    t.set_defaults(fn=cmd_terms)

    r = sub.add_parser("refs", help="find every use of a term")
    r.add_argument("term")
    r.add_argument("--root", default=".")
    r.set_defaults(fn=cmd_refs)

    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
