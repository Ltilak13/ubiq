"""Validate repository configuration into one typed `Config` before discovery."""

from __future__ import annotations

import re
from copy import deepcopy
from dataclasses import dataclass
from difflib import get_close_matches
from pathlib import Path

import yaml

from .globs import Glob
from .kinds import POLICIES, Context, Policies, Severity, broken_guarantees
from .scan import Delimiter, compile_delimiter


class InvalidConfig(ValueError):
    """Invalid configuration, reported as E008."""


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
    policies: Policies
    unlinked_except: tuple[str, ...]


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
    broken = broken_guarantees(policies)
    if broken:
        raise InvalidConfig("; ".join(broken))
    return policies


def load_config(root: Path) -> Config:
    cfg = deepcopy(DEFAULT_CONFIG)
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
    for key in ("term_field", "overlays", "historical"):
        cfg[key] = _strings(cfg[key], key, scalar=True)
    if not cfg["term_field"]:
        raise InvalidConfig("term_field: expected at least one field")
    if cfg["frontmatter"] not in ("strict", "lenient"):
        raise InvalidConfig("frontmatter: expected strict or lenient")
    for key in ("glossary", "catalogs", "delimiters"):
        if not isinstance(cfg[key], list):
            raise InvalidConfig(f"{key}: expected a list")

    def globs(patterns: list[str]) -> tuple[Glob, ...]:
        return tuple(Glob.parse(pattern, root) for pattern in patterns)

    rules = []
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

    catalogs = []
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

    return Config(
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
        policies=_policies(cfg["references"], cfg["unlinked_mentions"]),
        unlinked_except=tuple(cfg["unlinked_except"]),
    )
