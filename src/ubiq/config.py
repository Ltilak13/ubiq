"""Validate repository configuration into one typed `Config` before discovery."""

from __future__ import annotations

import math
import os
import re
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
from difflib import get_close_matches
from pathlib import Path

import yaml

from .candidates import Shape
from .globs import Glob
from .kinds import POLICIES, Context, Policies, Severity, broken_guarantees
from .scan import Delimiter, compile_delimiter


class InvalidConfig(ValueError):
    """Invalid configuration, reported as E008."""


DEFAULT_CONFIG: dict = {
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
    # Patterns start at the root, so `**/` ignores nested copies too.
    "ignore": ["**/.git/**", "**/node_modules/**", "**/.venv/**"],
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
    "delimiters": [],
    # Sidecar records that attach frontmatter to a source file they do not own.
    # Each overlay is markdown with `source: path/to/source.md` plus optional ns,
    # aliases, id, and any ref_fields. The source file is not edited.
    "overlays": [".ubiq/overlays/**/*.md"],
    # JSON/YAML inventories of terms. Each item must resolve (E006). Optional
    # `cover` globs: every matching record must appear in the inventory (E007).
    "catalogs": [],
    # Explicit JSON Schema contracts for structured files or Markdown frontmatter.
    "schemas": [],
    # Per-kind overrides: {kind: {severity: error|warn|off, scans: [...]}}.
    # Kinds: wiki, delimiter, markdown, id, field, catalog, mention.
    "references": {},
    # W002 shorthand for `references.mention.severity`. Off by default: on a
    # 39-skill repo it reported 820 warnings on first run, and still 111 after
    # excepting 18 ordinary or ubiquitous terms.
    "unlinked_mentions": "off",
    # Terms whose plain mentions are ordinary words here (`pr` vs "PR"), by name
    # or qualified name. Explicit references to them are still checked.
    "unlinked_except": [],
    # Markup that `ubiq candidates` reads as possible vocabulary: `code` spans
    # that are hyphenated identifiers, and `bold` names for repos that bold
    # their terms. Bold is off by default because most bold is emphasis.
    "candidate_shapes": ["code"],
    # Composition edges between records (`ubiq graph`, E011, E012, W003-W005).
    # invoke.fields: frontmatter fields whose values invoke another record
    #   (default: ref_fields minus route.fields and reference.fields). invoke.blocked_by: a boolean
    #   field that, when true on the target, means the model cannot invoke it (W003).
    # route.fields: fields that point elsewhere without depending on the target
    #   ("not for X; use Y"). Walks show route edges but don't follow them.
    # reference.fields: informational examples and comparisons; these are validated
    #   relationships, but graph walks do not follow them as dependencies.
    # include.ns: namespaces of shared parts; a Markdown link to one is an include.
    # include.inputs: the part field listing enumerated inputs ({mode: [new, existing]});
    #   each include names one value as "`new` mode" after the link (E012).
    # install: globs of files whose directory installs as a sibling under one
    #   root (skills/*/SKILL.md); links that leave such a directory must resolve
    #   both there and in the source tree (W004).
    # external: other repositories whose own edges.install joins the same root.
    # drift.ns: namespaces whose explicit references and declared edges must agree (W005).
    # invoke.severity, route.severity, include.severity: error|warn|off for what
    #   checks of that kind's edges report; unset, each code keeps its letter.
    "edges": {},
    # Typed-metadata coverage (`ubiq coverage`). Unset: the command reports
    # setup guidance and exits 2. `files` selects the denominator; each
    # `exclude` entry needs a `reason`.
    "coverage": None,
    # Mirror records to GitHub issues (`ubiq sync github`). Unset: the command
    # reports setup guidance and exits 2.
    # repo: owner/name of the issue tracker (default: $GITHUB_REPOSITORY).
    # label_prefix: prefix of the labels the sync owns (default "priority: ").
    # records: the record files to mirror, each a `glob` and its `kind` (goal).
    "sync": None,
}


@dataclass(frozen=True)
class GlossaryRule:
    glob: Glob
    term_field: tuple[str, ...]
    ns: str | None
    label: str  # names the rule in E008 conflicts: "glossary[0] (glossary/*.md)"


@dataclass(frozen=True)
class CatalogSpec:
    file: Path
    path: str  # as written, for messages
    items: str
    term: str  # basename | name | literal
    cover: tuple[Glob, ...]


@dataclass(frozen=True)
class SchemaSpec:
    schema: str
    files: tuple[Glob, ...]
    format: str


@dataclass(frozen=True)
class Exclusion:
    glob: Glob
    reason: str


@dataclass(frozen=True)
class CoverageSpec:
    files: tuple[Glob, ...]
    exclude: tuple[Exclusion, ...]
    min_typed_percent: int | float | None
    no_regression: bool


SYNC_KINDS = ("goal", "plan", "decision")
REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


@dataclass(frozen=True)
class SyncRecord:
    glob: Glob
    kind: str


@dataclass(frozen=True)
class SyncSpec:
    records: tuple[SyncRecord, ...]
    repo: str | None = None
    label_prefix: str = "priority: "


@dataclass(frozen=True)
class Config:
    root: Path
    glossary: tuple[GlossaryRule, ...]
    docs: tuple[Glob, ...]
    historical: tuple[Glob, ...]
    ignore: tuple[Glob, ...]
    overlays: tuple[Glob, ...]
    term_field: tuple[str, ...]
    lenient: bool
    ref_fields: tuple[str, ...]
    id_patterns: tuple[re.Pattern, ...]
    external_id_patterns: tuple[re.Pattern, ...]
    delimiters: tuple[Delimiter, ...]
    catalogs: tuple[CatalogSpec, ...]
    schemas: tuple[SchemaSpec, ...]
    policies: Policies
    unlinked_except: tuple[str, ...]
    candidate_shapes: Shape
    edges: EdgeConfig
    coverage: CoverageSpec | None = None
    sync: SyncSpec | None = None

    @property
    def part_rules(self) -> tuple[GlossaryRule, ...]:
        """Rules whose files are shared parts: a Markdown link into one is an include link."""
        return tuple(rule for rule in self.glossary if rule.ns in self.edges.include_ns)


@dataclass(frozen=True)
class Dependency:
    name: str | None
    path: Path
    revision: str | None = None
    required: bool = False
    snapshot: bool = False  # internal: files were extracted from revision by review


@dataclass(frozen=True)
class EdgeConfig:
    invoke_fields: tuple[str, ...]
    route_fields: tuple[str, ...]
    reference_fields: tuple[str, ...]
    blocked_by: str | None
    include_ns: tuple[str, ...]
    inputs: str  # part frontmatter field: {input name: [allowed values]}
    install: tuple[Glob, ...]
    external: tuple[Dependency, ...]
    drift_ns: tuple[str, ...]  # namespaces whose mentions and edges must agree (W005)
    # Edge kind -> configured severity; a kind left out keeps each code's default.
    severity: Mapping[str, Severity]


def _section(raw: dict, key: str, allowed) -> dict:
    value = raw.get(key) or {}
    if not isinstance(value, dict):
        raise InvalidConfig(f"edges.{key}: expected a mapping")
    _known(value, f"edges.{key}", allowed)
    return value


def _edges(raw, ref_fields: tuple[str, ...], root: Path) -> EdgeConfig:
    if not isinstance(raw, dict):
        raise InvalidConfig("edges: expected a mapping")
    _known(raw, "edges", ("invoke", "route", "reference", "include", "install", "external", "drift"))
    invoke = _section(raw, "invoke", ("fields", "blocked_by", "severity"))
    route = _section(raw, "route", ("fields", "severity"))
    reference = _section(raw, "reference", ("fields", "severity"))
    include = _section(raw, "include", ("ns", "inputs", "severity"))
    drift = _section(raw, "drift", ("ns",))
    severity = {kind: _severity(section["severity"], f"edges.{kind}.severity")
                for kind, section in (("invoke", invoke), ("route", route),
                                      ("reference", reference), ("include", include))
                if section.get("severity") is not None}
    routes = tuple(_strings(route.get("fields", []), "edges.route.fields", scalar=True))
    references = tuple(_strings(reference.get("fields", []), "edges.reference.fields", scalar=True))
    default = [f for f in ref_fields if f not in (*routes, *references)]
    fields = tuple(_strings(invoke.get("fields", default), "edges.invoke.fields", scalar=True))
    # An edge must resolve, and only ref_fields are resolved (E006).
    for name, values in (("invoke", fields), ("route", routes), ("reference", references)):
        if set(values) - set(ref_fields):
            raise InvalidConfig(f"edges.{name}.fields: each field must also be in ref_fields")
    if set(fields) & set(routes):
        raise InvalidConfig("edges.route.fields: a field cannot both invoke and route")
    if set(references) & (set(fields) | set(routes)):
        raise InvalidConfig("edges.reference.fields: a field cannot also invoke or route")
    blocked = invoke.get("blocked_by")
    external = []
    declarations = raw.get("external", [])
    if isinstance(declarations, str):
        declarations = [declarations]
    if not isinstance(declarations, list):
        raise InvalidConfig("edges.external: expected a list")
    names: set[str] = set()
    for i, value in enumerate(declarations):
        label = f"edges.external[{i}]"
        dependency_name: str | None = None
        revision = None
        required = False
        if isinstance(value, dict):
            _known(value, label, ("name", "path", "revision", "required"))
            dependency_name = _string(value.get("name"), f"{label}.name")
            if not re.fullmatch(r"[a-z][a-z0-9-]*", dependency_name):
                raise InvalidConfig(f"{label}.name: expected lowercase letters, digits, or hyphens")
            if dependency_name in names:
                raise InvalidConfig(f"{label}.name: duplicate dependency name {dependency_name!r}")
            names.add(dependency_name)
            if not isinstance(value.get("required"), bool):
                raise InvalidConfig(f"{label}.required: expected an explicit boolean")
            required = value["required"]
            revision = value.get("revision")
            if "revision" in value and (not isinstance(revision, str)
                                       or not re.fullmatch(r"[0-9a-fA-F]{40}|[0-9a-fA-F]{64}", revision)):
                raise InvalidConfig(f"{label}.revision: expected a full commit SHA")
            value = value.get("path")
        path = Path(os.path.expanduser(_string(value, f"{label}.path")))
        external.append(Dependency(dependency_name, path if path.is_absolute() else root / path,
                                   revision.lower() if revision else None, required))
    return EdgeConfig(
        invoke_fields=fields,
        route_fields=routes,
        reference_fields=references,
        blocked_by=None if blocked is None else _string(blocked, "edges.invoke.blocked_by"),
        include_ns=tuple(_strings(include.get("ns", ["part"]), "edges.include.ns", scalar=True)),
        inputs=_string(include.get("inputs", "inputs"), "edges.include.inputs"),
        install=tuple(Glob.parse(g, root) for g in _strings(raw.get("install", []), "edges.install")),
        external=tuple(external),
        drift_ns=tuple(_strings(drift.get("ns", []), "edges.drift.ns", scalar=True)),
        severity=severity,
    )


def _relative(pattern: str, field: str) -> str:
    if os.path.isabs(pattern) or ".." in Path(pattern).parts:
        raise InvalidConfig(f"{field}: expected a repository-relative pattern")
    return pattern


def _sync(raw, root: Path) -> SyncSpec | None:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise InvalidConfig("sync: expected a mapping")
    _known(raw, "sync", ("repo", "label_prefix", "records"))
    repo = raw.get("repo")
    if repo is not None and (not isinstance(repo, str) or not REPO_RE.match(repo)):
        raise InvalidConfig("sync.repo: expected owner/name")
    prefix = raw.get("label_prefix", "priority: ")
    if not isinstance(prefix, str):
        raise InvalidConfig("sync.label_prefix: expected a string")
    if not prefix.strip():
        raise InvalidConfig("sync.label_prefix: must not be empty (the sync owns every label with it)")
    entries = raw.get("records")
    if not isinstance(entries, list) or not entries:
        raise InvalidConfig("sync.records: list the record files to mirror")
    records: list[SyncRecord] = []
    for i, entry in enumerate(entries):
        field = f"sync.records[{i}]"
        if not isinstance(entry, dict):
            raise InvalidConfig(f"{field}: expected a mapping with glob and kind")
        _known(entry, field, ("glob", "kind"))
        pattern = _relative(_string(entry.get("glob"), f"{field}.glob"), f"{field}.glob")
        kind = entry.get("kind")
        if kind not in SYNC_KINDS:
            raise InvalidConfig(f"{field}.kind: expected one of {', '.join(SYNC_KINDS)}")
        records.append(SyncRecord(Glob.parse(pattern, root), kind))
    return SyncSpec(tuple(records), repo, prefix)


def _coverage(raw, root: Path) -> CoverageSpec | None:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise InvalidConfig("coverage: expected a mapping")
    _known(raw, "coverage", ("files", "exclude", "min_typed_percent", "no_regression"))
    if "files" not in raw:
        raise InvalidConfig("coverage.files: list the repository files to measure")
    files = _strings(raw["files"], "coverage.files")
    if not files:
        raise InvalidConfig("coverage.files: expected at least one pattern")
    exclude = raw.get("exclude") or []
    if not isinstance(exclude, list):
        raise InvalidConfig("coverage.exclude: expected a list")
    exclusions: list[Exclusion] = []
    for i, item in enumerate(exclude):
        field = f"coverage.exclude[{i}]"
        if not isinstance(item, dict):
            raise InvalidConfig(f"{field}: expected a mapping with glob and reason")
        _known(item, field, ("glob", "reason"))
        pattern = _relative(_string(item.get("glob"), f"{field}.glob"), f"{field}.glob")
        if item.get("reason") is None:
            raise InvalidConfig(f"{field}.reason: explain why {pattern} is excluded")
        exclusions.append(Exclusion(Glob.parse(pattern, root),
                                    _string(item["reason"], f"{field}.reason")))
    patterns = [e.glob.pattern for e in exclusions]
    if len(set(patterns)) != len(patterns):
        raise InvalidConfig("coverage.exclude: each glob may appear once")
    floor = raw.get("min_typed_percent")
    if floor is not None and (isinstance(floor, bool) or not isinstance(floor, (int, float))
                              or not math.isfinite(floor) or not 0 <= floor <= 100):
        raise InvalidConfig("coverage.min_typed_percent: expected a number from 0 through 100")
    no_regression = raw.get("no_regression", False)
    if not isinstance(no_regression, bool):
        raise InvalidConfig("coverage.no_regression: expected true or false")
    return CoverageSpec(tuple(Glob.parse(_relative(f, "coverage.files"), root) for f in files),
                        tuple(exclusions), floor, no_regression)


def _strings(value, field: str, scalar: bool = False) -> list[str]:
    values = [value] if scalar and isinstance(value, str) else value
    if not isinstance(values, list) or any(
            not isinstance(v, str) or not v.strip() for v in values):
        raise InvalidConfig(f"{field}: expected {'a string or ' if scalar else ''}a list of nonempty strings")
    return values


def _string(value, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InvalidConfig(f"{field}: expected a nonempty string")
    return value


def _known(mapping: dict, field: str, allowed) -> None:
    """E008 for a key the schema does not define, with a likely-typo hint."""
    unknown = sorted(str(key) for key in mapping if key not in allowed)
    if unknown:
        near = get_close_matches(unknown[0], list(allowed), n=1)
        hint = f"; did you mean {near[0]}?" if near else ""
        prefix = f"{field}: " if field else ""
        raise InvalidConfig(f"{prefix}unknown setting {unknown[0]}{hint}")


def _severity(value, field: str) -> Severity:
    # ubiq.yaml uses YAML 1.1 typing, where bare `off` loads as False.
    if value is False:
        value = "off"
    try:
        return Severity(value)
    except ValueError:
        raise InvalidConfig(f"{field}: expected error, warn, or off") from None


def _regexes(values: list[str], field: str) -> tuple[re.Pattern, ...]:
    compiled = []
    for i, pattern in enumerate(values):
        try:
            compiled.append(re.compile(pattern))
        except (re.error, OverflowError, RecursionError) as exc:
            raise InvalidConfig(f"{field}[{i}]: {exc}") from exc
    return tuple(compiled)


def _policies(raw, unlinked) -> Policies:
    """Compose `references:` overrides onto the default policy table."""
    if not isinstance(raw, dict):
        raise InvalidConfig("references: expected a mapping of kind to settings")
    if isinstance(unlinked, bool):
        unlinked = "warn" if unlinked else "off"
    if unlinked not in ("warn", "off"):
        raise InvalidConfig("unlinked_mentions: expected warn or off")
    policies = dict(POLICIES)
    policies["mention"] = policies["mention"].override(severity=Severity(unlinked))
    for name, settings in raw.items():
        field = f"references.{name}"
        if name not in policies:
            raise InvalidConfig(f"{field}: unknown kind; expected one of {', '.join(policies)}")
        if not isinstance(settings, dict):
            raise InvalidConfig(f"{field}: expected a mapping")
        _known(settings, field, ("severity", "scans"))
        severity = (_severity(settings["severity"], f"{field}.severity")
                    if settings.get("severity") is not None else None)
        scans = None
        if settings.get("scans") is not None:
            regions = _strings(settings["scans"], f"{field}.scans", scalar=True)
        try:
            if settings.get("scans") is not None:
                scans = Context.parse(regions)
            policies[name] = policies[name].override(severity=severity, scans=scans)
        except ValueError as exc:
            raise InvalidConfig(f"{field}.scans: {exc}") from None
    return policies


def load_config(root: Path) -> Config:
    cfg: dict = deepcopy(DEFAULT_CONFIG)
    path = root / "ubiq.yaml"
    if path.exists():
        try:
            user = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (yaml.YAMLError, OSError, UnicodeError) as exc:
            raise InvalidConfig(f"cannot read configuration: {exc}") from exc
        if user is None:
            user = {}
        if not isinstance(user, dict):
            raise InvalidConfig("expected a YAML mapping")
        _known(user, "", DEFAULT_CONFIG)
        cfg.update({k: v for k, v in user.items() if v is not None})

    for key in ("docs", "ignore", "id_patterns", "ref_fields", "external_id_patterns",
                "unlinked_except"):
        cfg[key] = _strings(cfg[key], key)
    for key in ("term_field", "overlays", "historical", "candidate_shapes"):
        cfg[key] = _strings(cfg[key], key, scalar=True)
    try:
        shapes = Shape.parse(cfg["candidate_shapes"])
    except ValueError as exc:
        raise InvalidConfig(f"candidate_shapes: {exc}") from None
    if not cfg["term_field"]:
        raise InvalidConfig("term_field: expected at least one field")
    if cfg["frontmatter"] not in ("strict", "lenient"):
        raise InvalidConfig("frontmatter: expected strict or lenient")
    for key in ("glossary", "catalogs", "delimiters", "schemas"):
        if not isinstance(cfg[key], list):
            raise InvalidConfig(f"{key}: expected a list")

    def globs(patterns: list[str]) -> tuple[Glob, ...]:
        return tuple(Glob.parse(pattern, root) for pattern in patterns)

    rules: list[GlossaryRule] = []
    for i, entry in enumerate(cfg["glossary"]):
        field = f"glossary[{i}]"
        if isinstance(entry, str):
            entry = {"glob": entry}
        if not isinstance(entry, dict):
            raise InvalidConfig(f"{field}: expected a glob string or mapping")
        _known(entry, field, ("glob", "term_field", "ns"))
        pattern = _string(entry.get("glob"), f"{field}.glob")
        term_field = _strings(entry.get("term_field", cfg["term_field"]),
                              f"{field}.term_field", scalar=True)
        if not term_field:
            raise InvalidConfig(f"{field}.term_field: expected at least one field")
        if entry.get("ns") is not None:
            _string(entry["ns"], f"{field}.ns")
        rules.append(GlossaryRule(Glob.parse(pattern, root), tuple(term_field),
                                  entry.get("ns"), f"{field} ({pattern})"))

    catalogs: list[CatalogSpec] = []
    for i, spec in enumerate(cfg["catalogs"]):
        field = f"catalogs[{i}]"
        if not isinstance(spec, dict):
            raise InvalidConfig(f"{field}: expected a mapping")
        _known(spec, field, ("file", "items", "term", "cover"))
        file = _string(spec.get("file"), f"{field}.file")
        items = _string(spec.get("items") or "skills", f"{field}.items")
        term = spec.get("term") or "basename"
        if term not in ("basename", "name", "literal"):
            raise InvalidConfig(f"{field}.term: expected basename, name, or literal")
        cover = _strings(spec.get("cover", []), f"{field}.cover", scalar=True)
        catalogs.append(CatalogSpec(root / file, file, items, term, globs(cover)))

    schemas: list[SchemaSpec] = []
    for i, spec in enumerate(cfg["schemas"]):
        field = f"schemas[{i}]"
        if not isinstance(spec, dict):
            raise InvalidConfig(f"{field}: expected a mapping")
        _known(spec, field, ("schema", "files", "format"))
        schema = _string(spec.get("schema"), f"{field}.schema")
        filename = schema.split("#", 1)[0]
        if not filename or ":" in filename:
            raise InvalidConfig(f"{field}.schema: expected a local schema file path")
        patterns = _strings(spec.get("files"), f"{field}.files")
        if not patterns:
            raise InvalidConfig(f"{field}.files: expected at least one pattern")
        mode = spec.get("format", "document")
        if mode not in ("document", "frontmatter"):
            raise InvalidConfig(f"{field}.format: expected document or frontmatter")
        schemas.append(SchemaSpec(schema, globs(patterns), mode))

    delimiters = []
    for i, spec in enumerate(cfg["delimiters"]):
        field = f"delimiters[{i}]"
        if isinstance(spec, str):
            pattern = _string(spec, field)
        elif isinstance(spec, dict):
            _known(spec, field, ("pattern", "prefix", "except", "only_known"))
            pattern = _string(spec.get("pattern") or spec.get("prefix"), field)
            _strings(spec.get("except", []), f"{field}.except")
            if not isinstance(spec.get("only_known", False), bool):
                raise InvalidConfig(f"{field}.only_known: expected a boolean")
        else:
            raise InvalidConfig(f"{field}: expected a string or mapping")
        if pattern.count("{term}") > 1:
            raise InvalidConfig(f"{field}: use at most one {{term}} placeholder")
        try:
            delimiters.append(compile_delimiter(spec))
        except (ValueError, re.error) as exc:
            raise InvalidConfig(f"{field}: {exc}") from exc

    config = Config(
        root=root,
        glossary=tuple(rules),
        docs=globs(cfg["docs"]),
        historical=globs(cfg["historical"]),
        ignore=globs(cfg["ignore"]),
        overlays=globs(cfg["overlays"]),
        term_field=tuple(cfg["term_field"]),
        lenient=cfg["frontmatter"] == "lenient",
        ref_fields=tuple(cfg["ref_fields"]),
        id_patterns=_regexes(cfg["id_patterns"], "id_patterns"),
        external_id_patterns=_regexes(cfg["external_id_patterns"], "external_id_patterns"),
        delimiters=tuple(delimiters),
        catalogs=tuple(catalogs),
        schemas=tuple(schemas),
        policies=_policies(cfg["references"], cfg["unlinked_mentions"]),
        unlinked_except=tuple(cfg["unlinked_except"]),
        candidate_shapes=shapes,
        edges=_edges(cfg["edges"], tuple(cfg["ref_fields"]), root),
        coverage=_coverage(cfg["coverage"], root),
        sync=_sync(cfg["sync"], root),
    )
    broken = broken_guarantees(config)
    if broken:
        raise InvalidConfig("; ".join(broken))
    return config
