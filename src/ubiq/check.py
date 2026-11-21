"""Rules engine: glossary + refs -> diagnostics.

Errors (fail the build):
  E001 duplicate-definition   same name claimed by >1 record in one namespace
  E002 unresolved-reference   [[term]] with no defining record
  E003 ambiguous-reference    unqualified [[term]] defined in >1 namespace
  E004 unresolved-id          id-pattern match with no record carrying that id
  E005 invalid-record         a record file exists but its frontmatter cannot be parsed
  E006 unresolved-field-ref   a frontmatter ref_fields value or catalog entry with no
                              defining record (external_id_patterns whitelists ids
                              defined outside records)
  E007 catalog-cover-gap      a record matching a catalog's `cover` globs is not listed
  E008 invalid-configuration  invalid settings or conflicting glossary selection rules

Warnings (reported, exit 0):
  W001 orphan-term            defined but never referenced or mentioned outside its own record
  W002 unlinked-mention       a section mentions a term but never links it (once per
                              term per section; `unlinked_mentions: off` disables it)
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import get_close_matches
from pathlib import Path

from .records import Glossary, normalize
from .scan import Ref

ERROR_CODES = {"E001", "E002", "E003", "E004", "E005", "E006", "E007", "E008"}


@dataclass
class Diagnostic:
    code: str
    message: str
    file: Path
    line: int = 0

    @property
    def is_error(self) -> bool:
        return self.code in ERROR_CODES

    def render(self) -> str:
        loc = f"{self.file}:{self.line}" if self.line else str(self.file)
        return f"{loc}: {self.code} {self.message}"


LINKING_KINDS = ("explicit", "markdown", "id")


def unlinked_mentions(glossary: Glossary, refs: list[Ref],
                      skip_files: set[Path] | None = None,
                      except_names: list[str] | None = None) -> list[Diagnostic]:
    """W002: the first plain mention of a term in a section that never links it.

    A section starts at an ATX heading (or the top of the file). Any wiki-link,
    delimiter, Markdown vocabulary link, or id reference to the term in that
    section counts as linked. Headings, historical docs, the term's own record,
    files in `skip_files` (overlay sidecars), and terms named in `except_names`
    are not checked.
    """
    skip = skip_files or set()
    excepted = {normalize(n) for n in except_names or []}
    term_files = {id(t): path for path, ts in glossary.by_file.items() for t in ts}
    linked: set[tuple[Path, int, int]] = set()
    for r in refs:
        if r.kind in LINKING_KINDS:
            linked.update((r.file, r.section, id(t)) for t in r.resolve(glossary))

    resolved_files: dict[Path, Path] = {}
    reported: set[tuple[Path, int, frozenset[int]]] = set()
    diags: list[Diagnostic] = []
    for r in refs:
        if r.kind != "mention" or r.historical or r.heading:
            continue
        matches = [t for t in r.resolve(glossary)
                   if t.term not in excepted and normalize(t.qualified) not in excepted]
        if not matches or any((r.file, r.section, id(t)) in linked for t in matches):
            continue
        if r.file not in resolved_files:
            resolved_files[r.file] = r.file.resolve()
        source = resolved_files[r.file]
        if source in skip or any(term_files[id(t)] == source for t in matches):
            continue
        key = (r.file, r.section, frozenset(id(t) for t in matches))
        if key in reported:
            continue
        reported.add(key)
        names = " or ".join(t.qualified for t in matches)
        diags.append(Diagnostic(
            "W002", f"unlinked mention '{r.raw}' — this section never links {names}",
            r.file, r.line))
    return diags


def run_checks(glossary: Glossary, refs: list[Ref],
               external_id_patterns: list[str] | None = None, *,
               unlinked: bool = False,
               skip_unlinked: set[Path] | None = None,
               unlinked_except: list[str] | None = None) -> list[Diagnostic]:
    diags: list[Diagnostic] = []
    external = [re.compile(p) for p in (external_id_patterns or [])]

    # E005 — records that exist but cannot be parsed
    for path, msg in glossary.invalid:
        diags.append(Diagnostic("E005", msg, path))

    # E001 — duplicate definitions within a namespace (canonical names and aliases collide alike)
    for name, terms in sorted(glossary.by_name.items()):
        by_ns: dict[str, list] = {}
        for t in terms:
            by_ns.setdefault(t.ns, []).append(t)
        for ns, ts in by_ns.items():
            if len(ts) > 1:
                files = ", ".join(str(t.file) for t in ts)
                diags.append(Diagnostic(
                    "E001", f"'{name}' defined {len(ts)} times in namespace '{ns}' ({files})",
                    ts[0].file))

    # E001 — same id claimed twice
    for id_, terms in sorted(glossary.by_id.items()):
        if len(terms) > 1:
            files = ", ".join(str(t.file) for t in terms)
            diags.append(Diagnostic(
                "E001", f"id '{id_}' claimed by {len(terms)} records ({files})", terms[0].file))

    # E002/E003/E004/E006 — reference resolution
    for r in refs:
        if r.kind == "mention":
            continue
        matches = r.resolve(glossary)
        if matches:
            if len(matches) > 1 and not r.historical:
                options = ", ".join(f"[[{t.qualified}]]" for t in matches)
                diags.append(Diagnostic(
                    "E003", f"ambiguous reference {r.raw} — qualify as one of: {options}",
                    r.file, r.line))
            continue
        if r.historical:
            continue
        if r.kind in ("explicit", "markdown"):
            scope = f" in namespace '{r.ns}'" if r.ns else ""
            hint = ""
            if r.kind == "explicit":
                candidates = sorted(n for n in glossary.by_name
                                    if glossary.resolve(n, r.ns))
                near = get_close_matches(r.name, candidates, n=1)
                if near:
                    target = f"{r.ns}:{near[0]}" if r.ns else near[0]
                    hint = f". Did you mean [[{target}]]?"
            diags.append(Diagnostic(
                "E002", f"unresolved reference {r.raw}{scope} — no defining record{hint}",
                r.file, r.line))
        elif r.kind == "id":
            diags.append(Diagnostic(
                "E004", f"unresolved id '{r.name}' — no record carries id: {r.name}",
                r.file, r.line))
        elif r.kind in ("field", "catalog"):
            if any(p.fullmatch(r.target) for p in external):
                continue
            label = "catalog entry" if r.kind == "catalog" else "field ref"
            diags.append(Diagnostic(
                "E006", f"unresolved {label} '{r.raw}' — no record with that id or name",
                r.file, r.line))

    # W001 — orphan terms (no reference or mention outside the defining record)
    # Resolve each path once: per-ref filesystem calls dominate large repos.
    term_files = {id(t): path for path, ts in glossary.by_file.items() for t in ts}
    ref_files: dict[Path, Path] = {}
    used: set[int] = set()
    for r in refs:
        matches = r.resolve(glossary)
        if len(matches) == 1 or r.kind == "mention":
            if r.file not in ref_files:
                ref_files[r.file] = r.file.resolve()
            source = ref_files[r.file]
            used.update(id(t) for t in matches if source != term_files[id(t)])
    for t in glossary.terms:
        if id(t) not in used:
            diags.append(Diagnostic(
                "W001", f"orphan term '{t.qualified}' — defined but never used", t.file))

    if unlinked:
        diags.extend(unlinked_mentions(glossary, refs, skip_unlinked, unlinked_except))
    return diags
