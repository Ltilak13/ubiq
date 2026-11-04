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

Warnings (reported, exit 0):
  W001 orphan-term            defined but never referenced or mentioned outside its own record
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .records import Glossary
from .scan import Ref

ERROR_CODES = {"E001", "E002", "E003", "E004", "E005", "E006", "E007"}


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


def run_checks(glossary: Glossary, refs: list[Ref],
               external_id_patterns: list[str] | None = None) -> list[Diagnostic]:
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
        if r.kind == "explicit":
            matches = glossary.resolve(r.name, r.ns)
            if not matches and r.ns is None and r.target:
                matches = glossary.by_id.get(r.target, [])  # [[T5]] resolves by record id
            if not matches:
                if r.historical:
                    continue
                scope = f" in namespace '{r.ns}'" if r.ns else ""
                diags.append(Diagnostic(
                    "E002", f"unresolved reference {r.raw}{scope} — no defining record",
                    r.file, r.line))
            elif len(matches) > 1:
                if r.historical:
                    continue
                options = ", ".join(f"[[{t.qualified}]]" for t in matches)
                diags.append(Diagnostic(
                    "E003", f"ambiguous reference {r.raw} — qualify as one of: {options}",
                    r.file, r.line))
        elif r.kind == "id":
            if r.name not in glossary.by_id:
                if r.historical:
                    continue
                diags.append(Diagnostic(
                    "E004", f"unresolved id '{r.name}' — no record carries id: {r.name}",
                    r.file, r.line))
        elif r.kind in ("field", "catalog"):
            # ids first (field values are usually ids), then names, then external allowlist
            if r.target in glossary.by_id or glossary.resolve(r.name):
                continue
            if any(p.fullmatch(r.target) for p in external):
                continue
            if r.historical:
                continue
            label = "catalog entry" if r.kind == "catalog" else "field ref"
            diags.append(Diagnostic(
                "E006", f"unresolved {label} '{r.raw}' — no record with that id or name",
                r.file, r.line))

    # W001 — orphan terms (no reference or mention outside the defining record)
    for t in glossary.terms:
        used = any(
            r.file != t.file and (
                (r.kind in ("explicit", "mention", "field", "catalog") and r.name in t.names())
                or (r.kind == "id" and t.id and r.name == t.id)
                or (r.kind in ("explicit", "field", "catalog") and t.id and r.target == t.id)
            )
            for r in refs
        )
        if not used:
            diags.append(Diagnostic(
                "W001", f"orphan term '{t.qualified}' — defined but never used", t.file))

    return diags
