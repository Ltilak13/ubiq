"""Typed-metadata coverage of explicitly selected repository files.

`coverage.files` selects the denominator. A file is typed when a schema binding
selects it directly, or when a record in an `x-ubiq` collection names it as its
`source`. See "Coverage" in docs/spec.md.
"""

from __future__ import annotations

import json
import subprocess
from fractions import Fraction
from math import floor
from pathlib import Path

from .check import Diagnostic
from .config import Config, CoverageSpec
from .integrity import Finding
from .records import Glossary, InvalidRecord
from .schemas import Binding, Target, assess_schemas, check_schemas

VERSION = 1
GUIDANCE = ('add a coverage section to ubiq.yaml, for example: coverage: '
            '{files: ["src/**/*.py"], exclude: [{glob: "src/vendor/**", reason: "upstream copy"}]}')


class MeasurementError(RuntimeError):
    """The selected scope cannot be read, so no coverage can be reported."""


def unavailable(reason: str, guidance: str | None = None) -> dict:
    out: dict = {"version": VERSION, "status": "unavailable", "reason": reason}
    return {**out, "guidance": guidance} if guidance else out


def finding(d: Diagnostic, root: Path) -> dict:
    """A diagnostic keyed for comparison: a path outside the root is resolved, so
    `root/../other` names the same file from either side."""
    return {"code": d.code, "severity": d.severity, "file": _display(root / d.file, root),
            "line": d.line, "message": d.message}


def _display(path: Path, root: Path) -> str:
    real = path.resolve()
    return real.relative_to(root).as_posix() if real.is_relative_to(root) else str(real)


def git_ignored(root: Path, files: list[str]) -> set[str]:
    """The files among `files` (root-relative) that git ignores; none outside git."""
    if not files:
        return set()
    probe = subprocess.run(["git", "rev-parse", "--is-inside-work-tree"], cwd=root,
                           capture_output=True, text=True, check=False)
    if probe.returncode or probe.stdout.strip() != "true":
        return set()
    proc = subprocess.run(["git", "check-ignore", "-z", "--stdin"], cwd=root,
                          input="".join(f"{f}\0" for f in files),
                          capture_output=True, text=True, check=False)
    if proc.returncode not in (0, 1):  # 1: nothing ignored
        raise MeasurementError(f"git check-ignore failed: {proc.stderr.strip()}")
    return {f for f in proc.stdout.split("\0") if f}


def percent(typed: int, eligible: int) -> float | None:
    """Truncated to two decimals, so 99.999% never displays as 100%."""
    if not eligible:
        return None
    return floor(Fraction(typed * 10000, eligible)) / 100


class _Scope:
    """Selected files minus ignores, then exclusions, keyed by resolved relative path."""

    def __init__(self, cfg: Config, spec: CoverageSpec, git: bool):
        root = cfg.root
        candidates: dict[str, set[str]] = {}
        outside: dict[str, str] = {}
        for glob in spec.files:
            for path in glob.walk(cfg.ignore):
                if not path.is_file() or any(g.matches(path) for g in cfg.ignore):
                    continue
                real = path.resolve()
                if real.is_relative_to(root):
                    candidates.setdefault(real.relative_to(root).as_posix(), set()).add(glob.pattern)
                else:
                    outside[path.relative_to(root).as_posix()] = str(real)
        ignored = git_ignored(root, sorted(candidates)) if git else set()
        self.selected = {f: p for f, p in candidates.items() if f not in ignored}
        matched = {p for patterns in self.selected.values() for p in patterns}
        self.unmatched = [g.pattern for g in spec.files if g.pattern not in matched]
        self.outside = outside
        self.exclusions: dict[str, list[dict]] = {}
        used: set[str] = set()
        for file in self.selected:
            hits = [e for e in spec.exclude if e.glob.matches(root / file)]
            if hits:
                used.update(e.glob.pattern for e in hits)
                self.exclusions[file] = [{"glob": e.glob.pattern, "reason": e.reason} for e in hits]
        self.unused = [e.glob.pattern for e in spec.exclude if e.glob.pattern not in used]
        self.eligible = sorted(f for f in self.selected if f not in self.exclusions)


_EVIDENCE = ("invalid", "missing", "stale")  # worst first
_RELATIONSHIPS = {"unresolved": "unresolved", "incompatible": "invalid", "undeclared": "invalid"}


def _assessed(t: Target, b: Binding) -> list[Finding] | None:
    """Integrity findings for a target, or None when integrity was not assessed:
    no x-ubiq extension, nonconforming data, or a graph shape failure."""
    if b.extension is None or t.integrity is None:
        return None
    return None if any(f.category == "shape" for f in t.integrity) else t.integrity


def _typing(cfg: Config, bindings: list[Binding], eligible: set[str]):
    """(file -> supporting locations, file -> integrity checks, incompleteness reasons).

    A check is (data file, findings), with None findings when not assessed."""
    root = cfg.root
    via: dict[str, list[dict]] = {}
    checks: dict[str, list[tuple[str, list[Finding] | None]]] = {}
    gaps: list[dict] = []

    def local(path: Path) -> str | None:
        real = path.resolve()
        if not real.is_relative_to(root):
            return None
        rel = real.relative_to(root).as_posix()
        return rel if rel in eligible else None

    for b in bindings:
        label = f"schemas[{b.index}]"
        if b.error is not None:
            gaps.append({"file": "ubiq.yaml",
                         "reason": f"{label} ({b.spec.schema}) cannot load, so its files are unknown: {b.error}"})
            continue
        for t in b.targets:
            # x-ubiq shape failures are nonconformance too: the graph contract is part of the schema.
            shape = any(f.category == "shape" for f in t.integrity or [])
            conformance = "invalid" if t.errors or shape else "valid"
            data_file = _display(t.path, root)
            findings = _assessed(t, b)
            if (rel := local(t.path)) is not None:
                via.setdefault(rel, []).append({"kind": "schema", "binding": label,
                                                "schema": b.spec.schema, "conformance": conformance})
                checks.setdefault(rel, []).append((data_file, findings))
            if b.extension is None:
                continue
            if not t.loaded:
                gaps.append({"file": data_file, "reason": f"x-ubiq data cannot load: {t.errors[0]}"})
                continue
            for collection in sorted(b.extension["collections"]):
                items = t.data.get(collection) if isinstance(t.data, dict) else None
                if not isinstance(items, list):
                    gaps.append({"file": data_file,
                                 "reason": f"x-ubiq collection {collection} is not a list"})
                    continue
                for i, record in enumerate(items):
                    source = record.get("source") if isinstance(record, dict) else None
                    if not isinstance(source, str) or not source.strip():
                        gaps.append({"file": data_file,
                                     "reason": f"x-ubiq record /{collection}/{i} has no source path"})
                        continue
                    path = Path(source)
                    if path.is_absolute() or ".." in path.parts:
                        continue  # E010 reports it; such a source is never in scope
                    if (rel := local(root / path)) is not None:
                        ident = record.get("id")
                        via.setdefault(rel, []).append({
                            "kind": "record", "file": data_file, "pointer": f"/{collection}/{i}",
                            "id": ident if isinstance(ident, str) else None,
                            "conformance": conformance})
                        mine = None if findings is None or not isinstance(ident, str) else [
                            f for f in findings if ident in f.records]
                        checks.setdefault(rel, []).append((data_file, mine))
    return via, checks, gaps


def _integrity(checks: list[tuple[str, list[Finding] | None]]) -> tuple[str, str, list[dict]]:
    """(evidence status, relationship status, findings) from a file's checks."""
    assessed = [(data, found) for data, found in checks if found is not None]
    if not assessed:
        return "not_assessed", "not_assessed", []
    findings = sorted({(data, f.category, f.kind, f.message, f.records)
                       for data, found in assessed for f in found})
    kinds = {(category, kind) for _, category, kind, _, _ in findings}
    evidence = next((k for k in _EVIDENCE if ("evidence", k) in kinds), "ok")
    relationships = {_RELATIONSHIPS[k] for c, k in kinds if c == "relationship"}
    relation = next((k for k in ("unresolved", "invalid") if k in relationships), "ok")
    return evidence, relation, [{"file": data, "category": c, "kind": k, "message": m,
                                 "records": list(r)} for data, c, k, m, r in findings]


def _suggestions(root: Path, scope: _Scope, git: bool) -> list[str]:
    """Discovered assets outside the selected scope. Advisory only."""
    from .discovery import discover
    try:
        report = discover(root)
    except (InvalidRecord, OSError):
        return []
    found = {f for group in report["groups"].values() for files in group.values() for f in files}
    found |= {f for schema in report["schemas"] for f in schema["files"]}
    found -= scope.selected.keys()
    found -= git_ignored(root, sorted(found)) if git else set()
    return sorted(found)


def measure(cfg: Config, glossary: Glossary, *, git: bool = True,
            suggest: bool = True) -> dict:
    """The coverage report for one side. `git` filters files git ignores."""
    spec = cfg.coverage
    if spec is None:
        raise MeasurementError("coverage is not configured")
    root = cfg.root
    scope = _Scope(cfg, spec, git)
    bindings = assess_schemas(cfg, glossary)
    via, checks, gaps = _typing(cfg, bindings, set(scope.eligible))

    files = []
    for file in sorted(scope.selected):
        if file in scope.exclusions:
            files.append({"file": file, "classification": "excluded",
                          "exclusions": scope.exclusions[file]})
            continue
        support = sorted(via.get(file, []), key=lambda v: json.dumps(v, sort_keys=True))
        entry: dict = {"file": file, "classification": "typed" if support else "untyped",
                       "via": support, "conformance": None}
        if support:
            entry["conformance"] = ("invalid" if any(v["conformance"] == "invalid" for v in support)
                                    else "valid")
            evidence, relationships, findings = _integrity(checks.get(file, []))
            entry.update(evidence=evidence, relationships=relationships, findings=findings)
        files.append(entry)

    typed = sum(f["classification"] == "typed" for f in files)
    eligible = len(scope.eligible)
    diagnostics = [finding(d, root) for d in check_schemas(cfg, glossary, bindings)]
    diagnostics += [finding(Diagnostic("W006", f"coverage pattern matched no files: {p}",
                                       root / "ubiq.yaml"), root) for p in scope.unmatched]
    diagnostics += [finding(Diagnostic("W006", f"coverage exclusion matched no selected file: {p}",
                                       root / "ubiq.yaml"), root) for p in scope.unused]
    gaps = sorted({json.dumps(g, sort_keys=True): g for g in gaps}.values(),
                  key=lambda g: (g["file"], g["reason"]))
    return {
        "version": VERSION,
        "status": "incomplete" if gaps else "ok",
        "complete": not gaps,
        "incomplete": gaps,
        "scope": {
            "files": [g.pattern for g in spec.files],
            "exclude": [{"glob": e.glob.pattern, "reason": e.reason,
                         "files": sum(any(x["glob"] == e.glob.pattern for x in xs)
                                      for xs in scope.exclusions.values())}
                        for e in spec.exclude],
            "outside": [{"file": f, "target": t} for f, t in sorted(scope.outside.items())],
        },
        "counts": {
            "selected": len(scope.selected), "excluded": len(scope.exclusions),
            "eligible": eligible, "typed": typed, "untyped": eligible - typed,
            "nonconforming": sum(f.get("conformance") == "invalid" for f in files),
        },
        "assessments": {
            name: {status: sum(f.get(name) == status for f in files) for status in statuses}
            for name, statuses in (("evidence", ("ok", *_EVIDENCE, "not_assessed")),
                                   ("relationships", ("ok", "unresolved", "invalid", "not_assessed")))
        },
        "ratio": {"typed": typed, "eligible": eligible},
        "typed_percent": percent(typed, eligible),
        "files": files,
        "suggestions": _suggestions(root, scope, git) if suggest else [],
        "diagnostics": sorted(diagnostics, key=lambda f: (f["file"], f["line"], f["code"], f["message"])),
    }


def _shown(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.2f}%"


def render(report: dict) -> str:
    """Readable report: problems first, then one summary line."""
    if report["status"] == "unavailable":
        lines = [f"coverage unavailable: {report['reason']}"]
        return "\n".join([*lines, f"hint: {report['guidance']}"] if report.get("guidance") else lines)
    lines = []
    for f in report["files"]:
        if f["classification"] == "untyped":
            lines.append(f"untyped {f['file']}")
        elif f["classification"] == "typed" and f["conformance"] == "invalid":
            lines.append(f"invalid {f['file']} (typed, but its metadata does not conform)")
        elif f["classification"] == "typed":
            problems = [f"{name} {f[name]}" for name in ("evidence", "relationships")
                        if f[name] not in ("ok", "not_assessed")]
            if problems:
                lines.append(f"failing {f['file']} ({', '.join(problems)})")
    for o in report["scope"]["outside"]:
        lines.append(f"outside {o['file']} -> {o['target']} (not counted)")
    for d in report["diagnostics"]:
        where = f"{d['file']}:{d['line']}" if d["line"] else d["file"]
        lines.append(f"{where}: {d['code']} {d['message']}")
    for gap in report["incomplete"]:
        lines.append(f"incomplete {gap['file']}: {gap['reason']}")
    c = report["counts"]
    a = report["assessments"]
    unassessed = a["evidence"]["not_assessed"]
    lines.append(f"{'INCOMPLETE' if report['incomplete'] else 'coverage'}: "
                 f"{c['typed']} of {c['eligible']} eligible files typed "
                 f"({_shown(report['typed_percent'])}); {c['selected']} selected, "
                 f"{c['excluded']} excluded, {c['nonconforming']} nonconforming"
                 + (f", evidence not assessed for {unassessed}" if unassessed else ""))
    return "\n".join(lines)
