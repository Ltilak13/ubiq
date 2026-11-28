"""Check the membership declared by records against their README field links."""

from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

import yaml

from .check import Diagnostic
from .config import Config
from .globs import first_match
from .records import (
    FRONTMATTER_RE,
    Glossary,
    InvalidRecord,
    parse_frontmatter,
    shared_fields,
)
from .scan import DOC_SUFFIXES, Ref


@dataclass(frozen=True)
class Membership:
    readme: Path
    record: Path
    source: Path
    line: int


def _declaration_line(path: Path, field: str) -> int:
    text = path.read_text(encoding="utf-8")
    match = FRONTMATTER_RE.match(text)
    if match is None:
        return 1
    first_line = text.count("\n", 0, match.start(1)) + 1
    try:
        node = yaml.compose(match[1], Loader=yaml.SafeLoader)
    except yaml.YAMLError:
        # Lenient frontmatter uses one key per line.
        return next((i for i, line in enumerate(match[1].splitlines(), first_line)
                     if line.partition(":")[0].strip() == field), 1)
    if isinstance(node, yaml.MappingNode):
        for key, _ in reversed(node.value):
            if isinstance(key, yaml.ScalarNode) and key.value == field:
                return key.start_mark.line + first_line
    return 1


def _target(cfg: Config, record: Path, scope: str) -> Path | None:
    root = cfg.root
    if scope == "root":
        candidates = (root / "README.md",)
    elif scope == "parent":
        # Start above the record's containing folder and stop at the checkout root.
        candidates = tuple(directory / "README.md" for directory in record.parents[1:]
                           if directory.is_relative_to(root))
    else:
        path = Path(scope)
        if path.is_absolute() or ".." in path.parts or path.suffix.lower() not in DOC_SUFFIXES:
            return None
        candidates = (root / path,)
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
            if (resolved.is_relative_to(root) and not first_match(cfg.ignore, candidate)
                    and not first_match(cfg.ignore, resolved) and candidate.is_file()):
                return candidate
        except (OSError, RuntimeError, ValueError):
            continue
    return None


def declarations(cfg: Config, glossary: Glossary) -> tuple[list[Membership], list[Diagnostic]]:
    memberships: list[Membership] = []
    diagnostics: list[Diagnostic] = []
    field = cfg.readme_field
    paths = sorted({term.file.resolve() for term in glossary.terms
                    if term.file.resolve().is_relative_to(cfg.root)})
    for record in paths:
        try:
            value = shared_fields(record, glossary, cfg.lenient).get(field)
            if value is None:
                continue
            sidecar = glossary.overlay_sources.get(record)
            source = (sidecar if sidecar and parse_frontmatter(sidecar, cfg.lenient)[0].get(field)
                      is not None else record)
            line = _declaration_line(source, field)
        except InvalidRecord:
            continue  # Record parsing reports its own diagnostics.
        scopes = value if isinstance(value, list) else [value]
        if any(not isinstance(scope, str) or not scope.strip() for scope in scopes):
            diagnostics.append(Diagnostic(
                "E015", f"{field} must be a string or a list of nonempty strings", source, line))
            continue
        for scope in dict.fromkeys(scopes):
            readme = _target(cfg, record, scope)
            if readme is None:
                diagnostics.append(Diagnostic(
                    "E015", f"{field} target {scope!r} does not resolve to a repository README",
                    source, line))
                continue
            memberships.append(Membership(readme, record, source, line))
    return memberships, diagnostics


def check_membership(cfg: Config, glossary: Glossary, declarations: list[Membership],
                     refs: list[Ref]) -> list[Diagnostic]:
    expected: dict[Path, dict[Path, Membership]] = defaultdict(dict)
    for declaration in declarations:
        expected[declaration.readme.resolve()][declaration.record] = declaration

    linked: set[tuple[Path, Path]] = set()
    diagnostics: list[Diagnostic] = []
    for ref in refs:
        record = ref.destination
        if (ref.kind != "value" or not ref.readme_entry or ref.historical
                or record is None or record not in glossary.by_file):
            continue
        readme = ref.file
        if not readme.is_relative_to(cfg.root):
            continue
        linked.add((readme, record))
        if record not in expected.get(readme, {}):
            name = record.relative_to(cfg.root) if record.is_relative_to(cfg.root) else record
            diagnostics.append(Diagnostic(
                "E015", f"{name} does not declare this README in {cfg.readme_field}",
                readme, ref.line))

    for readme, records in expected.items():
        for record, declaration in records.items():
            if (readme, record) not in linked:
                name = declaration.readme.relative_to(cfg.root)
                diagnostics.append(Diagnostic(
                    "E015", f"{name} has no field link to this record in a managed section",
                    declaration.source, declaration.line))
    return diagnostics
