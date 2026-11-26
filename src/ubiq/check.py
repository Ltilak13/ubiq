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
  E011 include-cycle          a shared part includes itself through other parts (graph.py)
  E012 part-input             an include names no value, or an undeclared one, for a part input
  E013 field-value            a link to #field whose field is absent, null, not text, or not
                              its label (in any file with frontmatter, a fragment that names
                              no heading or anchor names a field)

Warnings (reported, exit 0):
  W001 orphan-term            defined but never referenced or mentioned outside its own record
  W002 unlinked-mention       a section mentions a term but never links it (once per
                              term per section; `unlinked_mentions: warn` enables it)
  W003 blocked-invoke         an invoke edge the model cannot follow (graph.py)
  W004 install-layout         a link that resolves in only one of source tree and install
  W005 drift                  a reference without an edge, or an edge the text never names
  W006 coverage-scope         a coverage pattern or exclusion matches nothing (coverage.py)
  W007 broken-link            a relative link to a missing file that is not a record

A reference kind's policy (kinds.py) sets the severity of what its refs report:
`references.id.severity: warn` keeps E004 visible without failing the build.
`edges.<kind>.severity` does the same for an edge kind's constraints (graph.py).
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, replace
from difflib import get_close_matches
from pathlib import Path

from .kinds import Policy, Severity
from .records import Glossary, normalize
from .scan import Ref, value_of


@dataclass
class Diagnostic:
    code: str
    message: str
    file: Path
    line: int = 0
    severity: str = ""  # "error" or "warning"; defaults from the code's letter

    def __post_init__(self):
        self.severity = self.severity or ("error" if self.code.startswith("E") else "warning")

    @property
    def is_error(self) -> bool:
        return self.severity == "error"

    def render(self) -> str:
        loc = f"{self.file}:{self.line}" if self.line else str(self.file)
        # Configuration can move a code off its letter's default; say so next to it.
        note = f" ({self.severity})" if self.is_error != self.code.startswith("E") else ""
        return f"{loc}: {self.code}{note} {self.message}"


def at(severity: Severity | None, diags: list[Diagnostic]) -> list[Diagnostic]:
    """`diags` at a configured severity: none when off, unchanged when unset."""
    if severity is None:
        return diags
    if severity is Severity.OFF:
        return []
    level = "error" if severity is Severity.ERROR else "warning"
    return [replace(d, severity=level) for d in diags]


def reported(policy: Policy, code: str, message: str, file: Path,
             line: int = 0) -> list[Diagnostic]:
    """The diagnostic at the policy's severity, or none when it is off."""
    return at(policy.severity, [Diagnostic(code, message, file, line)])


def _term_files(glossary: Glossary) -> dict[int, Path]:
    """Each term's resolved record path, keyed by `id(term)`."""
    return {id(t): path for path, ts in glossary.by_file.items() for t in ts}


def _resolver():
    """Memoized `Path.resolve`: per-ref filesystem calls dominate large repos."""
    cache: dict[Path, Path] = {}

    def resolve(path: Path) -> Path:
        if path not in cache:
            cache[path] = path.resolve()
        return cache[path]
    return resolve


def unlinked_mentions(glossary: Glossary, refs: list[Ref],
                      skip_files: set[Path] | None = None,
                      except_names: Sequence[str] | None = None) -> list[Diagnostic]:
    """W002: the first plain mention of a term in a section that never links it.

    A section starts at an ATX heading (or the top of the file). Any wiki-link,
    delimiter, Markdown vocabulary link, id reference, or other link whose label
    names the term in that section counts as linked. Headings, historical docs,
    the term's own record, files in `skip_files` (overlay sidecars), and terms
    named in `except_names` are not checked.
    """
    if not any(r.policy.name == "mention" and r.policy.severity is not Severity.OFF
               for r in refs):
        return []
    skip = skip_files or set()
    excepted = {normalize(n) for n in except_names or []}
    term_files = _term_files(glossary)
    linked: set[tuple[Path, int, int]] = set()
    for r in refs:
        if r.policy.links or r.linked:
            linked.update((r.file, r.section, id(t)) for t in r.resolve(glossary))

    resolved = _resolver()
    warned: set[tuple[Path, int, int]] = set()
    diags: list[Diagnostic] = []
    for r in refs:
        if r.policy.name != "mention" or r.historical or r.heading:
            continue
        matches = [t for t in r.resolve(glossary)
                   if t.term not in excepted and normalize(t.qualified) not in excepted]
        if not matches or any((r.file, r.section, id(t)) in linked for t in matches):
            continue
        source = resolved(r.file)
        if source in skip or any(term_files[id(t)] == source for t in matches):
            continue
        # Once per term: a mention matching several terms reports those not yet seen.
        fresh = [t for t in matches if (r.file, r.section, id(t)) not in warned]
        if not fresh:
            continue
        warned.update((r.file, r.section, id(t)) for t in fresh)
        names = " or ".join(t.qualified for t in fresh)
        diags += reported(r.policy, r.policy.code,
                          f"unlinked mention '{r.raw}' — this section never links {names}",
                          r.file, r.line)
    return diags


def run_checks(glossary: Glossary, refs: list[Ref],
               external_id_patterns=(), *,
               skip_unlinked: set[Path] | None = None,
               unlinked_except: Sequence[str] | None = None,
               lenient: bool = False) -> list[Diagnostic]:
    diags: list[Diagnostic] = []
    external = [re.compile(p) for p in external_id_patterns]

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

    # E002/E003/E004/E006/E013 — reference resolution, at each kind's severity
    for r in refs:
        if r.kind == "mention":
            continue
        if r.kind == "value":
            try:
                value = "" if r.historical else " ".join(value_of(glossary, r, lenient).split())
                if not r.historical and r.target != value:
                    raise LookupError(f"label '{r.target}' ≠ {r.field} '{value}' — "
                                      "update the label")
            except LookupError as exc:
                diags += reported(r.policy, r.policy.code,
                                  f"field value {r.raw} — {exc}", r.file, r.line)
            continue
        matches = r.resolve(glossary)
        if matches:
            # Records that share one qualified name are a duplicate, already E001;
            # qualifying cannot pick between them.
            qualified = list(dict.fromkeys(t.qualified for t in matches))
            if len(qualified) > 1 and not r.historical:
                options = ", ".join(f"[[{name}]]" for name in qualified)
                diags += reported(r.policy, "E003",
                                  f"ambiguous reference {r.raw} — qualify as one of: {options}",
                                  r.file, r.line)
            continue
        if r.historical:
            continue
        if r.kind in ("field", "catalog") and any(p.fullmatch(r.target) for p in external):
            continue
        diags += reported(r.policy, r.policy.code, _unresolved(glossary, r), r.file, r.line)

    # W001 — orphan terms (no reference or mention outside the defining record)
    term_files = _term_files(glossary)
    resolved = _resolver()
    used: set[int] = set()
    for r in refs:
        matches = r.resolve(glossary)
        if len(matches) == 1 or r.kind == "mention":
            source = resolved(r.file)
            used.update(id(t) for t in matches if source != term_files[id(t)])
    for t in glossary.terms:
        if id(t) not in used:
            diags.append(Diagnostic(
                "W001", f"orphan term '{t.qualified}' — defined but never used", t.file))

    diags.extend(unlinked_mentions(glossary, refs, skip_unlinked, unlinked_except))
    return diags


def _unresolved(glossary: Glossary, r: Ref) -> str:
    if r.kind == "link":
        return f"broken link {r.raw} — no file at {r.target}"
    if r.kind == "id":
        return f"unresolved id '{r.name}' — no record carries id: {r.name}"
    if r.kind in ("field", "catalog"):
        label = "catalog entry" if r.kind == "catalog" else "field ref"
        return f"unresolved {label} '{r.raw}' — no record with that id or name"
    scope = f" in namespace '{r.ns}'" if r.ns else ""
    hint = ""
    if r.kind == "explicit":
        candidates = sorted(n for n in glossary.by_name if glossary.resolve(n, r.ns))
        near = get_close_matches(r.name, candidates, n=1)
        if near:
            target = f"{r.ns}:{near[0]}" if r.ns else near[0]
            hint = f". Did you mean [[{target}]]?"
    return f"unresolved reference {r.raw}{scope} — no defining record{hint}"
