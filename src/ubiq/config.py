"""Validate and normalize repository configuration before discovery."""

from __future__ import annotations

import re
from copy import deepcopy
from pathlib import Path

import yaml

from .scan import compile_delimiter


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
    # W002: warn once per term per section when a term is mentioned but never
    # linked there. "warn" or "off". Warnings never fail the check. Off by
    # default: on a 39-skill repo it reported 505 warnings on first run.
    "unlinked_mentions": "off",
    # Terms whose plain mentions are ordinary words here (`pr` vs "PR"), by name
    # or qualified name. Explicit references to them are still checked.
    "unlinked_except": [],
}


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


def load_config(root: Path) -> dict:
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
    # ubiq.yaml uses YAML 1.1 typing, where bare `off` loads as False.
    if isinstance(cfg["unlinked_mentions"], bool):
        cfg["unlinked_mentions"] = "warn" if cfg["unlinked_mentions"] else "off"
    if cfg["unlinked_mentions"] not in ("warn", "off"):
        raise InvalidConfig("unlinked_mentions: expected warn or off")
    for key in ("id_patterns", "external_id_patterns"):
        for i, pattern in enumerate(cfg[key]):
            try:
                re.compile(pattern)
            except (re.error, OverflowError, RecursionError) as exc:
                raise InvalidConfig(f"{key}[{i}]: {exc}") from exc

    for key in ("glossary", "catalogs", "delimiters"):
        if not isinstance(cfg[key], list):
            raise InvalidConfig(f"{key}: expected a list")
    entries = []
    for i, entry in enumerate(cfg["glossary"]):
        field = f"glossary[{i}]"
        if isinstance(entry, str):
            entry = {"glob": entry}
        if not isinstance(entry, dict):
            raise InvalidConfig(f"{field}: expected a glob string or mapping")
        entry = dict(entry)
        entry["glob"] = _string(entry.get("glob"), f"{field}.glob")
        entry["term_field"] = _strings(entry.get("term_field", cfg["term_field"]),
                                       f"{field}.term_field", scalar=True)
        if not entry["term_field"]:
            raise InvalidConfig(f"{field}.term_field: expected at least one field")
        if entry.get("ns") is not None:
            _string(entry["ns"], f"{field}.ns")
        entries.append(entry)
    cfg["glossary"] = entries

    for i, spec in enumerate(cfg["catalogs"]):
        field = f"catalogs[{i}]"
        if not isinstance(spec, dict):
            raise InvalidConfig(f"{field}: expected a mapping")
        _string(spec.get("file"), f"{field}.file")
        _string(spec.get("items", "skills"), f"{field}.items")
        if spec.get("term", "basename") not in ("basename", "name", "literal"):
            raise InvalidConfig(f"{field}.term: expected basename, name, or literal")
        spec["cover"] = _strings(spec.get("cover", []), f"{field}.cover", scalar=True)

    for i, spec in enumerate(cfg["delimiters"]):
        field = f"delimiters[{i}]"
        if isinstance(spec, str):
            pattern = _string(spec, field)
        elif isinstance(spec, dict):
            pattern = _string(spec.get("pattern") or spec.get("prefix"), field)
            _strings(spec.get("except", []), f"{field}.except")
            if not isinstance(spec.get("only_known", False), bool):
                raise InvalidConfig(f"{field}.only_known: expected a boolean")
        else:
            raise InvalidConfig(f"{field}: expected a string or mapping")
        if pattern.count("{term}") > 1:
            raise InvalidConfig(f"{field}: use at most one {{term}} placeholder")
        try:
            compile_delimiter(spec)
        except (ValueError, re.error) as exc:
            raise InvalidConfig(f"{field}: {exc}") from exc
    return cfg
